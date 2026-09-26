"""Stage E4: harmonized cell table, policy adjustment, first estimates and checks.

Run:  python -m fvd.e4_cells

Reads the OBR and CBO partitions written by E1-E3 and writes
  tables/cells/<SOURCE>.parquet
  tables/outturns/<SOURCE>.parquet     (value_first_estimate filled, D4)
  stats/e4_checks/*.csv, summary.json

Conventions (plan section 4): error e = forecast - outturn (positive = over-
forecast); revision r_v = F_v - F_prev(v) (positive = raised). Logs only for
strictly positive level series. Policy-adjusted forecast = forecast + effect of
policy decisions announced after the vintage, so that the adjusted error removes
what the forecaster was not asked to predict (CBO's definition).
"""

from __future__ import annotations

import json
from datetime import date

import numpy as np
import pandas as pd

from . import obr_series as S
from .paths import STATS, TABLES
from .periods import period_bounds
from .schemas import SCHEMAS, check_columns, write_schema

CHECKS = STATS / "e4_checks"

# D8 default episode windows, in calendar time. A target period is tagged when
# its midpoint falls inside a window, which maps UK 2008-09 and US FY2009 alike.
EPISODES = {
    "gfc": (date(2008, 4, 1), date(2010, 3, 31)),
    "covid": (date(2020, 4, 1), date(2022, 3, 31)),
    "energy": (date(2022, 4, 1), date(2023, 3, 31)),
}
CLASSIFICATION_BREAK_K = 3.0   # plan E4 task 4


def load(source: str) -> dict[str, pd.DataFrame]:
    t = {n: pd.read_parquet(TABLES / n / f"{source}.parquet")
         for n in ("series", "vintages", "forecasts", "outturns")}
    t["attribution"] = pd.concat([pd.read_parquet(p) for p in (TABLES / "attribution").glob(f"{source}*.parquet")])
    return t


# --- revision chains ---------------------------------------------------------------

def in_chain(v: pd.DataFrame) -> pd.Series:
    """Vintages that enter revision chains: memo vintages are excluded (D14)."""
    return ~v["flags"].fillna("").str.contains("memo:")


def add_chain(fc: pd.DataFrame, vint: pd.DataFrame) -> pd.DataFrame:
    v = vint.set_index("vintage_id")
    fc = fc.merge(vint[["vintage_id", "publication_date", "forecaster"]], on="vintage_id", how="left")
    fc["in_revision_chain"] = fc.vintage_id.map(in_chain(vint).set_axis(vint.vintage_id)).fillna(False)
    fc["pub"] = pd.to_datetime(fc.publication_date)
    fc = fc.sort_values(["series_id", "target_period", "pub", "vintage_id"]).reset_index(drop=True)
    ch = fc[fc.in_revision_chain]
    g = ch.groupby(["series_id", "target_period"])
    prev = pd.DataFrame({"prev_vintage_id": g.vintage_id.shift(), "prev_value": g.value.shift(),
                         "prev_forecaster": g.forecaster.shift()})
    fc = fc.join(prev)
    fc["revision"] = fc.value - fc.prev_value
    fc["prev_forecaster_differs"] = fc.prev_forecaster.notna() & (fc.prev_forecaster != fc.forecaster)
    return fc.drop(columns=["prev_forecaster"])


# --- policy adjustment -------------------------------------------------------------------

def cbo_policy_effects(fc: pd.DataFrame, att: pd.DataFrame, vint: pd.DataFrame) -> pd.Series:
    """Sum of legislative changes dated after the vintage (CBO's rule). For debt,
    the cumulative deficit effects over the projection years, with the sign
    flipped (a deficit-raising law raises debt), as in CBO's replication code."""
    leg = att[att.category == "policy"].copy()
    # Change dates: the vintage label month (baseline or year-end record).
    leg["cdate"] = pd.to_datetime(leg.vintage_id.str.extract(r"cbo_(\d{4}-\d{2})")[0] + "-01")
    fc = fc.copy()
    fc["bdate"] = pd.to_datetime(fc.vintage_id.str.extract(r"cbo_(\d{4}-\d{2})")[0] + "-01")
    out = pd.Series(0.0, index=fc.index)
    by = {k: g for k, g in leg.groupby(["series_id", "target_period"])}
    for idx, r in fc[fc.series_id != "cbo.debt.total"].iterrows():
        g = by.get((r.series_id, r.target_period))
        if g is not None:
            out[idx] = g.value[g.cdate > r.bdate].sum()
    # debt: -(cumulative deficit changes) over years from the first projection year
    d = fc[fc.series_id == "cbo.debt.total"]
    if len(d):
        defl = leg[leg.series_id == "cbo.deficit.total"]
        for idx, r in d.iterrows():
            first_fy = r.bdate.year + (r.bdate.month >= 10)          # fiscal year in progress
            # from projection year -1 (two years back), as in CBO's code
            yrs = [str(y) for y in range(first_fy - 2, int(r.target_period) + 1)]
            sel = defl[defl.target_period.isin(yrs) & (defl.cdate > r.bdate)]
            out[idx] = -sel.value.sum()
    return out


def obr_policy_effects(fc: pd.DataFrame, vint: pd.DataFrame, series: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """Policy effects announced after each vintage, in each series' convention.

    Aggregates (PSNB, PSCR, TME, in £ and % of GDP where the FRD has them): the FRD
    'policy' and 'classification and one-offs' revisions of later vintages.
    Components: the PMD direct effects of measures from later events for the
    series' head (indirect effects are not in the PMD).
    """
    att = pd.read_parquet(TABLES / "attribution" / "OBR_FRD.parquet")
    pub = pd.concat([vint, pd.read_parquet(TABLES / "vintages" / "OBR_intermediate.parquet")]) \
        .set_index("vintage_id").publication_date
    # PSNB (£ and % of GDP): the block-level policy and classification rows.
    # PSCR/TME: the rows derived for them (receipts or spending policy, and their
    # own classification lines). From October 2021 the FRD folds classification
    # changes into 'Underlying2', so they cannot be removed after that date.
    psnb = att[att.series_id.isin(["obr.psnb_gbp", "obr.psnb"])
               & att.category_raw.str.match(r"FRD:(policy|classification) \(")]
    other = att[att.series_id.isin(["obr.pscr_gbp", "obr.tme_gbp"])
                & att.category.isin(["policy", "classification_one_offs"])]
    agg = pd.concat([psnb, other])
    agg = agg.assign(apub=pd.to_datetime(agg.vintage_id.map(pub)))

    pm = pd.read_parquet(TABLES / "policy_measures" / "OBR.parquet")
    pm = pm[pm.series_id.notna() & pm.vintage_id.notna()]
    pm = pm.assign(apub=pd.to_datetime(pm.vintage_id.map(pub)))
    # Series whose PMD head maps to a parent: children are adjusted for their own head
    # only; the IT total also receives PAYE/SA-specific measures via the head 'Income tax'.
    eff = pd.Series(np.nan, index=fc.index)
    basis = pd.Series("", index=fc.index, dtype=object)
    agg_by = {k: g for k, g in agg.groupby(["series_id", "target_period"])}
    pm_by = {k: g for k, g in pm.groupby(["series_id", "target_period"])}
    pmd_series = set(pm.series_id)
    for idx, r in fc.iterrows():
        if r.series_id in ("obr.psnb_gbp", "obr.psnb", "obr.pscr_gbp", "obr.tme_gbp"):
            g = agg_by.get((r.series_id, r.target_period))
            eff[idx] = g.value[g.apub > r.pub].sum() if g is not None else 0.0
            basis[idx] = "FRD policy + classifications after vintage"
        elif r.series_id in pmd_series:
            g = pm_by.get((r.series_id, r.target_period))
            eff[idx] = g.value[g.apub > r.pub].sum() if g is not None else 0.0
            basis[idx] = "PMD direct effects after vintage (indirect effects missing)"
    return eff, basis


# --- outturns, breaks, episodes ----------------------------------------------------------

def first_estimates(fc: pd.DataFrame) -> pd.DataFrame:
    """D4 default: the value in the `past` column of the first vintage published
    after the period ended (memo vintages excluded)."""
    past = fc[(fc.cell_role == "past") & fc.in_revision_chain].sort_values("pub")
    first = past.groupby(["series_id", "target_period"]).first()[["value", "vintage_id"]]
    return first.rename(columns={"value": "value_first_estimate",
                                 "vintage_id": "first_estimate_vintage_id"}).reset_index()


def episode_tag(target_period: str, period_type: str) -> str:
    a, b = period_bounds(target_period, period_type)
    mid = a + (b - a) / 2
    return next((k for k, (s, e) in EPISODES.items() if s <= mid <= e), "")


def classification_breaks(cells: pd.DataFrame, cls_events: pd.DataFrame) -> pd.DataFrame:
    """Plan E4 task 4: latest outturn outside the range of all vintages by more than
    3 x the series' median absolute revision, AND a recorded classification change
    for that series and period."""
    med = cells.groupby("series_id").revision.apply(lambda s: s.abs().median())
    rows = []
    for (sid, tp), g in cells[cells.in_revision_chain].groupby(["series_id", "target_period"]):
        a = g.outturn_latest.iloc[0]
        if pd.isna(a) or pd.isna(med.get(sid)) or med[sid] == 0:
            continue
        lo, hi = g.value.min(), g.value.max()
        gap = max(lo - a, a - hi, 0.0)
        if gap > CLASSIFICATION_BREAK_K * med[sid]:
            rec = cls_events[(cls_events.series_id == sid) & (cls_events.target_period == tp)]
            rows.append({"series_id": sid, "target_period": tp, "outturn_latest": a,
                         "forecast_min": lo, "forecast_max": hi, "gap": gap,
                         "median_abs_revision": med[sid], "gap_over_median": gap / med[sid],
                         "classification_change_recorded": len(rec) > 0,
                         "classification_events": "; ".join(sorted(set(rec.category_raw)))[:300]})
    return pd.DataFrame(rows)


def classification_events() -> pd.DataFrame:
    """Recorded classification changes by series and target period (FRD). Changes to
    PSCR/TME/PSNB in £ also mark their % of GDP versions."""
    att = pd.read_parquet(TABLES / "attribution" / "OBR_FRD.parquet")
    c = att[(att.category == "classification_one_offs") & (att.value.abs() > 0)]
    extra = c[c.series_id.isin(["obr.pscr_gbp", "obr.tme_gbp", "obr.psnb_gbp"])].copy()
    extra["series_id"] = extra.series_id.str.replace("_gbp", "", regex=False)
    return pd.concat([c, extra])[["series_id", "target_period", "category_raw"]]


# --- main ------------------------------------------------------------------------------------

def build(source: str) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    t = load(source)
    series, vint, fc, out = t["series"], t["vintages"], t["forecasts"], t["outturns"]
    fc = add_chain(fc, vint)
    kind = series.set_index("series_id").kind
    ptype = series.set_index("series_id").period_type
    fc["kind"] = fc.series_id.map(kind)

    # outturns: latest and first estimate
    fe = first_estimates(fc)
    out = out.drop(columns=["value_first_estimate", "first_estimate_vintage_id"]) \
             .merge(fe, on=["series_id", "target_period"], how="left")
    out = out[["source", "series_id", "target_period", "value_latest", "value_first_estimate",
               "first_estimate_vintage_id", "origin"]]
    fc = fc.merge(out[["series_id", "target_period", "value_latest", "value_first_estimate"]]
                  .rename(columns={"value_latest": "outturn_latest", "value_first_estimate": "outturn_first"}),
                  on=["series_id", "target_period"], how="left")

    # policy adjustment
    if source == "CBO":
        fc["policy_effect_after"] = cbo_policy_effects(fc, t["attribution"], vint)
        fc["policy_adjustment_basis"] = "CBO legislative changes after vintage"
    else:
        eff, basis = obr_policy_effects(fc, vint, series)
        fc["policy_effect_after"] = eff
        fc["policy_adjustment_basis"] = basis
    fc["value_policy_adjusted"] = fc.value + fc.policy_effect_after

    # errors
    for o in ("latest", "first"):
        A = fc[f"outturn_{o}"]
        fc[f"error_{o}"] = fc.value - A
        fc[f"error_{o}_pa"] = fc.value_policy_adjusted - A
        pos = (fc.kind == "level") & (fc.value > 0) & (A > 0)
        fc[f"log_error_{o}"] = np.where(pos, np.log(fc.value.where(pos) / A.where(pos)), np.nan)
        pos_pa = (fc.kind == "level") & (fc.value_policy_adjusted > 0) & (A > 0)
        fc[f"log_error_{o}_pa"] = np.where(pos_pa, np.log(fc.value_policy_adjusted.where(pos_pa) / A.where(pos_pa)), np.nan)
    posr = (fc.kind == "level") & (fc.value > 0) & (fc.prev_value > 0)
    fc["log_revision"] = np.where(posr, np.log(fc.value.where(posr) / fc.prev_value.where(posr)), np.nan)

    # flags
    fc["memo_vintage"] = ~fc.in_revision_chain
    fc["episode"] = [episode_tag(tp, ptype[s]) for s, tp in zip(fc.series_id, fc.target_period)]
    cells = fc
    if source == "OBR":
        breaks = classification_breaks(cells, classification_events())
    else:
        breaks = classification_breaks(cells, pd.DataFrame(columns=["series_id", "target_period", "category_raw"]))
    flagged = set(zip(breaks[breaks.classification_change_recorded].series_id,
                      breaks[breaks.classification_change_recorded].target_period)) if len(breaks) else set()
    cells["classification_break"] = [(s, tp) in flagged for s, tp in zip(cells.series_id, cells.target_period)]
    cells["z"] = np.nan   # normalized error, computed in E6

    # identity e_v = e_last - sum of later revisions, within each revision chain
    ch = cells[cells.in_revision_chain].sort_values(["series_id", "target_period", "pub"])
    g = ch.groupby(["series_id", "target_period"])
    later_rev = g.revision.transform(lambda s: s[::-1].cumsum()[::-1].shift(-1).fillna(0.0))
    e_last = g.error_latest.transform("last")
    ident = (ch.error_latest - (e_last - later_rev)).abs()
    ident = ident[ch.error_latest.notna()]

    cells = cells[[c[0] for c in SCHEMAS["tables/cells"]["columns"]]]
    stats = {
        "cells": len(cells), "cells_in_revision_chain": int(cells.in_revision_chain.sum()),
        "cells_with_revision": int(cells.revision.notna().sum()),
        "cells_with_outturn": int(cells.outturn_latest.notna().sum()),
        "cells_with_first_estimate": int(cells.outturn_first.notna().sum()),
        "cells_policy_adjusted": int((cells.policy_effect_after.notna()).sum()),
        "identity_cells_checked": int(len(ident)), "identity_max_abs_diff": float(ident.max()) if len(ident) else None,
        "classification_break_candidates": int(len(breaks)),
        "classification_breaks_flagged": int(len(flagged)),
        "episode_cells": cells.episode.value_counts().to_dict(),
    }
    return cells, out, {"stats": stats, "breaks": breaks}


def check_cbo_adjustment(cells: pd.DataFrame) -> pd.DataFrame:
    """Our policy-adjusted CBO errors must equal CBO's published projection errors
    (deficit: CBO flips the sign, since the series is the budget balance)."""
    from .e3_cbo import OUT, series_id
    rows = []
    for comp in ("revenue", "outlay", "deficit", "debt"):
        o = pd.read_csv(OUT / f"{comp}_projection_errors.csv")
        o["series_id"] = [series_id(c, s) for c, s in zip(o.component, o.subcategory)]
        o["vintage_id"] = "cbo_" + o.baseline_date.str[:7]
        o["target_period"] = o.projected_fiscal_year.astype(str)
        m = o.merge(cells[["series_id", "vintage_id", "target_period", "error_latest_pa"]],
                    on=["series_id", "vintage_id", "target_period"], how="left")
        sign = -1 if comp == "deficit" else 1
        m["abs_diff"] = (m.error_latest_pa * sign - m.projection_error).abs()
        rows.append(m[["series_id", "vintage_id", "target_period", "projection_error",
                       "error_latest_pa", "abs_diff"]])
    return pd.concat(rows)


def main() -> None:
    CHECKS.mkdir(parents=True, exist_ok=True)
    summary = {}
    for source in ("OBR", "CBO"):
        cells, out, info = build(source)
        check_columns("tables/cells", cells)
        (TABLES / "cells").mkdir(parents=True, exist_ok=True)
        cells.to_parquet(TABLES / "cells" / f"{source}.parquet", index=False)
        check_columns("tables/outturns", out)
        out.to_parquet(TABLES / "outturns" / f"{source}.parquet", index=False)
        info["breaks"].to_csv(CHECKS / f"classification_break_candidates_{source}.csv", index=False)
        flag_share = (cells.groupby("series_id")[["classification_break", "memo_vintage"]].mean()
                      .assign(episode=cells.assign(e=cells.episode != "").groupby("series_id").e.mean()))
        flag_share.to_csv(CHECKS / f"flag_shares_by_series_{source}.csv")
        info["stats"]["flag_shares"] = {c: round(float(cells[c].mean()), 4) for c in ("classification_break", "memo_vintage")}
        info["stats"]["flag_shares"]["episode"] = round(float((cells.episode != "").mean()), 4)
        if source == "CBO":
            chk = check_cbo_adjustment(cells)
            chk.to_csv(CHECKS / "cbo_policy_adjustment_vs_cbo_errors.csv", index=False)
            info["stats"]["cbo_adjusted_errors_vs_cbo"] = {
                "rows": len(chk), "within_0.01": int((chk.abs_diff <= 0.01).sum()),
                "missing": int(chk.error_latest_pa.isna().sum()),
                "max_abs_diff": float(chk.abs_diff.max())}
        summary[source] = info["stats"]
    write_schema("tables/cells", TABLES.parent)
    write_schema("tables/outturns", TABLES.parent)
    (CHECKS / "summary.json").write_text(json.dumps(summary, indent=2, default=str))
    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()
