"""Stage E6: case scoring and selection, pre-registered.

    python -m fvd.e6_cases register   # hash cases/preregistration.md and the input tables
    python -m fvd.e6_cases select     # check the hashes, then score and select

The rule and its parameters are in cases/preregistration.md; the parameters are
read from the yaml block in section 7 of that file, so the code cannot drift from
the text. `register` refuses to run once a selection exists (a change after that
is a deviation, logged in the file). `select` refuses to run if the file or any
input has changed since registration.

Writes cases/{scored_cells,trajectory_scores,cases,controls,random_sample}.parquet
with schema files, and cases/selection_run.json.
"""

from __future__ import annotations

import hashlib
import json
import random
import re
import subprocess
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import yaml

from .paths import CASES, RAW_CBO, ROOT, TABLES
from .schemas import check_columns, write_schema

PREREG = CASES / "preregistration.md"
REG = CASES / "preregistration.json"
GDP = RAW_CBO / "eval-projections-682559c" / "input_data" / "actual_GDP.csv"
ACTIVE = ["in_progress", "future"]


def _sha(path, text=False) -> str:
    b = path.read_bytes()
    if text:   # line endings do not change the registered text
        b = b.replace(b"\r\n", b"\n")
    return hashlib.sha256(b).hexdigest()


def _inputs() -> list:
    return sorted((TABLES / "cells").glob("*.parquet")) + sorted((TABLES / "series").glob("*.parquet")) + [GDP]


def params() -> dict:
    text = PREREG.read_text(encoding="utf-8")
    block = re.search(r"^## 7\..*?```yaml\n(.*?)```", text, flags=re.M | re.S)
    return yaml.safe_load(block.group(1))


def _rel(p) -> str:
    return p.relative_to(ROOT).as_posix()


def register() -> None:
    if (CASES / "cases.parquet").exists():
        sys.exit("A selection exists: log any change as a deviation in cases/preregistration.md.")
    params()   # the parameter block must parse
    reg = {"preregistration": _rel(PREREG), "sha256": _sha(PREREG, text=True),
           "registered_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "inputs": {_rel(p): _sha(p) for p in _inputs()}}
    REG.write_text(json.dumps(reg, indent=1) + "\n", encoding="utf-8")
    print(f"registered {reg['sha256'][:12]} at {reg['registered_at']}")


def verify() -> dict:
    reg = json.loads(REG.read_text(encoding="utf-8"))
    if _sha(PREREG, text=True) != reg["sha256"]:
        sys.exit("cases/preregistration.md has changed since registration.")
    now = {_rel(p): _sha(p) for p in _inputs()}
    if now != reg["inputs"]:
        changed = sorted(k for k in set(now) | set(reg["inputs"]) if now.get(k) != reg["inputs"].get(k))
        sys.exit(f"inputs changed since registration: {changed}")
    return reg


# --- scope and error basis -------------------------------------------------------

def load(p: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """In-scope chained cells with the error basis `e`, and the series left out
    because they have no policy-adjusted error (for the note)."""
    cells = pd.concat([pd.read_parquet(f) for f in sorted((TABLES / "cells").glob("*.parquet"))])
    series = pd.concat([pd.read_parquet(f) for f in sorted((TABLES / "series").glob("*.parquet"))])
    series = series.drop_duplicates("series_id")
    c = cells.merge(series[["series_id", "name", "family", "kind", "unit_harmonized"]], on="series_id", how="left")
    c = c[c.in_revision_chain & c.forecaster.isin(p["forecasters"]) & c.outturn_latest.notna()]
    c = c[~c.family.isin(p["not_scored_families"]) & ~c.kind.isin(p["not_scored_kinds"])
          & ~c.series_id.isin(p["not_scored_duplicates"])]
    has_pa = c.groupby("series_id").error_latest_pa.transform(lambda s: s.notna().any())
    no_pa = (c[~has_pa].groupby(["source", "series_id"])
             .agg(name=("name", "first"), family=("family", "first"), kind=("kind", "first"))
             .reset_index())
    c = c[has_pa & ~c.classification_break].copy()
    lvl = c.kind.eq("level")
    bal = c.kind.eq("balance")
    pct = c.unit_harmonized.fillna("").str.lower().str.contains("per cent of gdp")
    if (bal & ~pct & c.source.ne("CBO")).any():
        raise ValueError("an OBR balance series outside % of GDP is in scope")
    gdp = pd.read_csv(GDP).set_index("fiscal_year").GDP
    cbo_bal = bal & c.source.eq("CBO")
    c["error_basis"] = np.where(lvl, "log", "pct_gdp")
    c["error"] = np.where(lvl, c.log_error_latest_pa, c.error_latest_pa)
    # CBO's own conversion: error / actual GDP of the target fiscal year x 100
    g = c.loc[cbo_bal, "target_period"].astype(int).map(gdp)
    c.loc[cbo_bal, "error"] = c.loc[cbo_bal, "error_latest_pa"] / g * 100
    c = c[c.error.notna()]
    c["trajectory_id"] = c.series_id + "__" + c.target_period
    c["publication_date"] = pd.to_datetime(c.publication_date)
    return c.reset_index(drop=True), no_pa


def bucket(h: pd.Series, p: dict) -> pd.Series:
    out = pd.Series(pd.NA, index=h.index, dtype="object")
    for lo, hi, lab in p["buckets"]:
        out[(h >= lo) & (h < hi)] = lab
    return out


# --- scale and z ---------------------------------------------------------------

def scale(s: pd.DataFrame, p: dict) -> pd.DataFrame:
    """sigma per scored cell: leave-one-target-out MAD of its series and bucket,
    shrunk towards the family's when fewer than shrink_n targets remain."""
    def mad(x):
        return p["mad_scale"] * float(np.median(np.abs(x - np.median(x)))) if len(x) else np.nan
    s = s.copy()
    s["sigma"], s["sigma_own_n_targets"], s["sigma_own_weight"] = np.nan, 0, 0.0
    for _, g in s.groupby(["source", "family", "error_basis", "bucket"]):
        fam = {t: mad(g.error[g.target_period != t].to_numpy()) for t in g.target_period.unique()}
        for _, gs in g.groupby("series_id"):
            for t, gt in gs.groupby("target_period"):
                rest = gs[gs.target_period != t]
                n = rest.target_period.nunique()
                own = mad(rest.error.to_numpy())
                w = min(n / p["shrink_n"], 1.0) if own > 0 else 0.0
                sig = own if w == 1 else fam[t] if w == 0 else w * own + (1 - w) * fam[t]
                s.loc[gt.index, ["sigma", "sigma_own_n_targets", "sigma_own_weight"]] = [sig, n, w]
    ok = s.sigma > 0
    s["z"] = np.where(ok, s.error / s.sigma.where(ok), np.nan)
    return s


# --- runs, onset, correction ------------------------------------------------------

def runs(z: np.ndarray, z_star: float) -> list[tuple[int, int]]:
    """Maximal stretches [i, j] of consecutive cells with |z| >= z* and one sign."""
    out, start = [], None
    for i, v in enumerate(z):
        ok = np.isfinite(v) and abs(v) >= z_star
        if ok and start is not None and np.sign(v) == np.sign(z[i - 1]):
            continue
        if start is not None:
            out.append((start, i - 1))
        start = i if ok else None
    if start is not None:
        out.append((start, len(z) - 1))
    return out


def trajectory(chain: pd.DataFrame, scored: pd.DataFrame, p: dict) -> dict:
    scored = scored.sort_values("publication_date")
    chain = chain.sort_values("publication_date")
    z = scored.z.to_numpy(dtype=float)
    first = scored.iloc[0]
    rec = {"source": first.source, "trajectory_id": first.trajectory_id, "series_id": first.series_id,
           "family": first.family, "error_basis": first.error_basis, "target_period": first.target_period,
           "episode": first.episode, "n_scored_cells": len(scored),
           "max_horizon_months": float(scored.horizon_months.max()),
           "max_abs_z": float(np.nanmax(np.abs(z))) if np.isfinite(z).any() else np.nan,
           "n_cells_without_z": int((~np.isfinite(z)).sum())}
    rs = runs(z, p["z_star"])
    best = max(rs, key=lambda r: (r[1] - r[0] + 1, np.abs(z[r[0]:r[1] + 1]).sum(), -r[0]), default=None)
    if best is None:
        return {**rec, "run_length": 0, "run_sign": "", "score": 0.0, "eligible": False,
                "onset_vintage_id": "", "onset_date": pd.NaT, "onset_error": np.nan, "onset_z": np.nan,
                "corrected": False, "correction_vintage_id": "", "correction_date": pd.NaT,
                "lead_time_vintages": "", "lead_time_n": 0}
    i, j = best
    on = scored.iloc[i]
    later = chain[chain.publication_date > on.publication_date]
    hit = later[later.error / on.error <= p["correction_share"]]
    corr = hit.iloc[0] if len(hit) else None
    end = corr.publication_date if corr is not None else chain.publication_date.max()
    lead = chain[(chain.publication_date >= on.publication_date) & (chain.publication_date <= end)]
    return {**rec, "run_length": j - i + 1, "run_sign": "over" if z[i] > 0 else "under",
            "score": float(np.abs(z[i:j + 1]).sum()), "eligible": j - i + 1 >= p["min_run"],
            "onset_vintage_id": on.vintage_id, "onset_date": on.publication_date,
            "onset_error": float(on.error), "onset_z": float(on.z),
            "corrected": corr is not None,
            "correction_vintage_id": corr.vintage_id if corr is not None else "",
            "correction_date": corr.publication_date if corr is not None else pd.NaT,
            "lead_time_vintages": ";".join(lead.vintage_id), "lead_time_n": len(lead),
            "_run_vintages": set(scored.vintage_id.iloc[i:j + 1])}


# --- selection -----------------------------------------------------------------

def select_cases(t: pd.DataFrame, p: dict) -> pd.DataFrame:
    t = t.copy()
    t["selection"] = np.where(t.eligible, "", "not eligible")
    t["case_rank"] = pd.NA
    for src, g in t[t.eligible].groupby("source"):
        g = g.sort_values(["score", "series_id", "target_period"], ascending=[False, True, True])
        n, per_ep, per_ft = 0, {}, {}
        for i, r in g.iterrows():
            if n >= p["K"]:
                t.loc[i, "selection"] = "below top K"
                continue
            if r.episode and per_ep.get(r.episode, 0) >= p["max_cases_per_episode"]:
                t.loc[i, "selection"] = "cap: episode"
                continue
            ft = (r.family, r.target_period)
            if per_ft.get(ft, 0) >= p["max_cases_per_family_target"]:
                t.loc[i, "selection"] = "cap: family and target period"
                continue
            n += 1
            per_ep[r.episode] = per_ep.get(r.episode, 0) + 1
            per_ft[ft] = per_ft.get(ft, 0) + 1
            t.loc[i, ["selection", "case_rank"]] = ["case", n]
    t["case_rank"] = t.case_rank.astype("Int64")
    return t


def year(tp: pd.Series) -> pd.Series:
    return tp.str[:4].astype(int)


def select_controls(t: pd.DataFrame, p: dict) -> pd.DataFrame:
    cases = t[t.selection == "case"].sort_values(["source", "case_rank"])
    pool = t[t.max_abs_z < p["z_low"]].copy()
    pool["year"] = year(pool.target_period)
    used, rows = set(), []
    for _, c in cases.iterrows():
        cand = pool[(pool.source == c.source) & (pool.family == c.family) & (pool.error_basis == c.error_basis)
                    & ~pool.trajectory_id.isin(used)].copy()
        cand["d_year"] = (cand.year - int(c.target_period[:4])).abs()
        cand["d_max_horizon"] = (cand.max_horizon_months - c.max_horizon_months).abs()
        cand["d_n_cells"] = (cand.n_scored_cells - c.n_scored_cells).abs()
        cand = cand[(cand.d_year <= p["control_years"]) & (cand.d_max_horizon <= p["control_max_horizon_months"])]
        cand = cand.sort_values(["d_n_cells", "d_max_horizon", "d_year", "series_id", "target_period"])
        for k, (_, r) in enumerate(cand.head(p["controls_per_case"]).iterrows(), start=1):
            used.add(r.trajectory_id)
            rows.append({**r.drop(["year"]).to_dict(), "case_trajectory_id": c.trajectory_id,
                         "control_order": k})
    cols = list(t.columns) + ["d_year", "d_max_horizon", "d_n_cells", "case_trajectory_id", "control_order"]
    return pd.DataFrame(rows, columns=cols)


def random_sample(t: pd.DataFrame, p: dict) -> pd.DataFrame:
    out = []
    for src, g in t.groupby("source"):
        ids = sorted(g.trajectory_id)
        draw = random.Random(p["random_seed"]).sample(ids, min(p["M"], len(ids)))
        d = g.set_index("trajectory_id").loc[draw].reset_index()
        d["draw_order"] = range(1, len(d) + 1)
        out.append(d)
    return pd.concat(out, ignore_index=True)


TRAJ = ["source", "trajectory_id", "series_id", "family", "error_basis", "target_period", "episode",
        "n_scored_cells", "max_horizon_months", "max_abs_z", "n_cells_without_z", "run_length", "run_sign",
        "score", "eligible", "onset_vintage_id", "onset_date", "onset_error", "onset_z", "corrected",
        "correction_vintage_id", "correction_date", "lead_time_vintages", "lead_time_n"]


def select() -> None:
    reg = verify()
    p = params()
    c, no_pa = load(p)
    c["bucket"] = bucket(c.horizon_months, p)
    scored = c[c.cell_role.isin(ACTIVE) & c.bucket.notna()]
    scored = scale(scored, p)
    n_scored = scored.groupby("trajectory_id").size()
    scoreable = n_scored[n_scored >= 2].index
    chains = dict(tuple(c.groupby("trajectory_id")))
    recs = [trajectory(chains[tid], g, p)
            for tid, g in scored[scored.trajectory_id.isin(scoreable)].groupby("trajectory_id")]
    t = pd.DataFrame(recs)
    in_run = {(r.trajectory_id, v) for r in t.itertuples() if isinstance(r._run_vintages, set)
              for v in r._run_vintages}
    t = t.drop(columns="_run_vintages")
    t = select_cases(t, p)
    ctrl = select_controls(t, p)
    rnd = random_sample(t, p)
    case_ids = set(t[t.selection == "case"].trajectory_id)
    ctrl_ids = set(ctrl.trajectory_id) if len(ctrl) else set()
    rnd["is_case"] = rnd.trajectory_id.isin(case_ids)
    rnd["is_control"] = rnd.trajectory_id.isin(ctrl_ids)
    t["is_control"] = t.trajectory_id.isin(ctrl_ids)
    t["in_random_sample"] = t.trajectory_id.isin(set(rnd.trajectory_id))

    sc = scored[scored.trajectory_id.isin(scoreable)].copy()
    sc["in_qualifying_run"] = [(a, b) in in_run for a, b in zip(sc.trajectory_id, sc.vintage_id)]
    sc = sc[["source", "trajectory_id", "series_id", "target_period", "vintage_id", "publication_date",
             "cell_role", "horizon_months", "bucket", "error_basis", "error", "sigma", "sigma_own_n_targets",
             "sigma_own_weight", "z", "in_qualifying_run"]]
    cases = t[t.selection == "case"].sort_values(["source", "case_rank"])
    cases = cases[TRAJ + ["case_rank", "in_random_sample"]]
    ctrl = ctrl[TRAJ + ["case_trajectory_id", "control_order", "d_year", "d_max_horizon", "d_n_cells"]]
    rnd = rnd[TRAJ + ["draw_order", "is_case", "is_control"]]
    t = t[TRAJ + ["selection", "case_rank", "is_control", "in_random_sample"]]
    for name, df in [("scored_cells", sc), ("trajectory_scores", t), ("cases", cases),
                     ("controls", ctrl), ("random_sample", rnd)]:
        check_columns(f"cases/{name}", df)
        df.to_parquet(CASES / f"{name}.parquet", index=False)
        write_schema(f"cases/{name}", ROOT)

    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    run = {"run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "preregistration_sha256": reg["sha256"], "registered_at": reg["registered_at"],
           "git_head_at_run": head, "inputs_verified": True,
           "series_without_policy_adjustment": no_pa.to_dict("records"),
           "counts": {src: {"scored_cells": int((sc.source == src).sum()),
                            "scoreable_trajectories": int((t.source == src).sum()),
                            "eligible": int(((t.source == src) & t.eligible).sum()),
                            "cases": int((cases.source == src).sum()),
                            "controls": int((ctrl.source == src).sum()),
                            "random_sample": int((rnd.source == src).sum())}
                      for src in sorted(t.source.unique())}}
    (CASES / "selection_run.json").write_text(json.dumps(run, indent=1, default=str) + "\n", encoding="utf-8")
    print(json.dumps(run["counts"], indent=1))


if __name__ == "__main__":
    {"register": register, "select": select}[sys.argv[1]]()
