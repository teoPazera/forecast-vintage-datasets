"""Stage E5: stylized facts and numbers-only predictability tests.

Run:  python -m fvd.e5_stylized_facts

All statistics are per source (OBR, HM Treasury, CBO) and per series family, and
per series for balance and rate series, for raw and policy-adjusted errors, by
horizon bucket (D6), with and without the episode windows (D8).

Error basis, so that series can be pooled within a family:
  level series   log error log(F/A) and log revision (unitless);
  balance, rate  error and revision in the series' unit (per cent of GDP,
                 percentage points, or $/£ billion), never pooled across series.

Writes stats/stylized_facts.csv, stats/efficiency_tests.csv,
stats/attribution_shares.csv, stats/calibration_targets.json (+ schema files).
"""

from __future__ import annotations

import json
import warnings

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats as sps

from .paths import CROSSWALKS, STATS, TABLES

warnings.filterwarnings("ignore", category=RuntimeWarning)

BUCKETS = [(-np.inf, 0, "<0"), (0, 6, "0-6"), (6, 12, "6-12"), (12, 24, "12-24"),
           (24, 36, "24-36"), (36, np.inf, "36+")]   # D6 default, months
MIN_N = 8   # minimum observations to report a regression


def bucket(h: pd.Series) -> pd.Series:
    out = pd.Series(pd.NA, index=h.index, dtype="object")
    for lo, hi, lab in BUCKETS:
        out[(h >= lo) & (h < hi)] = lab
    return out


def load_cells() -> pd.DataFrame:
    cells = pd.concat([pd.read_parquet(p) for p in (TABLES / "cells").glob("*.parquet")])
    series = pd.concat([pd.read_parquet(p) for p in (TABLES / "series").glob("*.parquet")])
    series = series[~series.series_id.duplicated()]
    c = cells.merge(series[["series_id", "family", "kind", "unit"]], on="series_id", how="left")
    c["group"] = np.where(c.forecaster == "HM Treasury", "HMT", c.source)
    c["bucket"] = bucket(c.horizon_months)
    c = c[c.in_revision_chain]
    # error and revision on the pooled basis
    lvl = c.kind == "level"
    for sfx in ("", "_pa"):
        c[f"err{sfx}"] = np.where(lvl, c[f"log_error_latest{sfx}"], c[f"error_latest{sfx}"])
    c["rev"] = np.where(lvl, c.log_revision, c.revision)
    return c


def units_of_analysis(c: pd.DataFrame):
    """(group, family, series_id or 'pooled', frame). Level series are pooled within
    family; balance and rate series are analysed one series at a time."""
    for (g, fam), d in c.groupby(["group", "family"]):
        lv = d[d.kind == "level"]
        if len(lv):
            yield g, fam, "pooled_levels", lv
        for sid, ds in d[d.kind != "level"].groupby("series_id"):
            yield g, fam, sid, ds


def clustered_mean(y: pd.Series, clusters: pd.Series) -> tuple[float, float, float, int]:
    """Mean with standard error clustered by target period."""
    ok = y.notna()
    y, cl = y[ok].astype(float), clusters[ok]
    if len(y) < MIN_N or cl.nunique() < 2:
        return (float(y.mean()) if len(y) else np.nan, np.nan, np.nan, int(cl.nunique()))
    res = sm.OLS(y.values, np.ones(len(y))).fit(cov_type="cluster", cov_kwds={"groups": pd.factorize(cl)[0]})
    return float(res.params[0]), float(res.bse[0]), float(res.pvalues[0]), int(cl.nunique())


def ols_clustered(y, x, clusters):
    ok = y.notna() & x.notna()
    y, x, cl = y[ok].astype(float), x[ok].astype(float), clusters[ok]
    if len(y) < MIN_N or cl.nunique() < 3 or x.std() == 0:
        return None
    X = sm.add_constant(x.values)
    return sm.OLS(y.values, X).fit(cov_type="cluster", cov_kwds={"groups": pd.factorize(cl)[0]}), len(y), cl.nunique()


def target_key(d: pd.DataFrame) -> pd.Series:
    return d.series_id + "|" + d.target_period


def facts_and_tests(c: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    facts, tests, rev_rows = [], [], []
    for g, fam, unit, d in units_of_analysis(c):
        for episodes in ("with", "without"):
            dd = d if episodes == "with" else d[d.episode == ""]
            for pa in ("raw", "policy_adjusted"):
                ecol = "err" if pa == "raw" else "err_pa"
                for b, db in dd.groupby("bucket"):
                    e = db[ecol].dropna()
                    if not len(e):
                        continue
                    cl = target_key(db.loc[e.index])
                    mean, se, p, ncl = clustered_mean(e, cl)
                    facts.append({"group": g, "family": fam, "unit": unit, "episodes": episodes,
                                  "errors": pa, "bucket": b, "n_cells": len(e), "n_targets": ncl,
                                  "n_series": db.loc[e.index].series_id.nunique(),
                                  "mean_error": mean, "se_clustered": se, "p_bias": p,
                                  "sd_error": float(e.std()), "mae": float(e.abs().mean()),
                                  "rmse": float(np.sqrt((e ** 2).mean()))})
                    # Mincer-Zarnowitz: outturn on forecast (logs for levels)
                    if unit == "pooled_levels":
                        y = np.log(db.outturn_latest.where(db.outturn_latest > 0))
                        xf = db.value if pa == "raw" else db.value_policy_adjusted
                        x = np.log(xf.where(xf > 0))
                    else:
                        y = db.outturn_latest
                        x = db.value if pa == "raw" else db.value_policy_adjusted
                    r = ols_clustered(y, x, target_key(db))
                    if r is not None:
                        res, n, nt = r
                        w = res.wald_test("const = 0, x1 = 1", scalar=True)
                        tests.append({"group": g, "family": fam, "unit": unit, "episodes": episodes,
                                      "errors": pa, "bucket": b, "test": "mincer_zarnowitz",
                                      "n_cells": n, "n_targets": nt, "coef": float(res.params[1]),
                                      "intercept": float(res.params[0]), "se": float(res.bse[1]),
                                      "stat": float(w.statistic), "p_value": float(w.pvalue),
                                      "note": "H0: intercept 0 and slope 1 (joint Wald, clustered by target)"})
                    # Coibion-Gorodnichenko: e_v on r_v. Their error is actual - forecast, so
                    # their positive coefficient (under-reaction) is negative here.
                    r = ols_clustered(db[ecol], db.rev, target_key(db))
                    if r is not None:
                        res, n, nt = r
                        tests.append({"group": g, "family": fam, "unit": unit, "episodes": episodes,
                                      "errors": pa, "bucket": b, "test": "error_on_revision",
                                      "n_cells": n, "n_targets": nt, "coef": float(res.params[1]),
                                      "intercept": float(res.params[0]), "se": float(res.bse[1]),
                                      "stat": float(res.tvalues[1]), "p_value": float(res.pvalues[1]),
                                      "note": "e = F - A; a negative coefficient = CG's positive (under-reaction)"})
            # Nordhaus: consecutive revisions of the same target (not by bucket, not by error type)
            ch = dd.sort_values(["series_id", "target_period", "publication_date"])
            ch = ch.assign(rev_prev=ch.groupby(["series_id", "target_period"]).rev.shift())
            pair = ch.dropna(subset=["rev", "rev_prev"])
            pair = pair[(pair.rev != 0) & (pair.rev_prev != 0)]
            if len(pair) >= MIN_N:
                rho = float(np.corrcoef(pair.rev, pair.rev_prev)[0, 1])
                same = int((np.sign(pair.rev) == np.sign(pair.rev_prev)).sum())
                binom = sps.binomtest(same, len(pair), 0.5)
                r = ols_clustered(pair.rev, pair.rev_prev, target_key(pair))
                tests.append({"group": g, "family": fam, "unit": unit, "episodes": episodes,
                              "errors": "", "bucket": "all", "test": "revision_autocorrelation",
                              "n_cells": len(pair), "n_targets": int(target_key(pair).nunique()),
                              "coef": float(r[0].params[1]) if r else np.nan, "intercept": np.nan,
                              "se": float(r[0].bse[1]) if r else np.nan, "stat": rho,
                              "p_value": float(r[0].pvalues[1]) if r else np.nan,
                              "note": "stat = correlation of consecutive revisions; coef = slope, clustered by target"})
                tests.append({"group": g, "family": fam, "unit": unit, "episodes": episodes,
                              "errors": "", "bucket": "all", "test": "same_sign_share",
                              "n_cells": len(pair), "n_targets": int(target_key(pair).nunique()),
                              "coef": same / len(pair), "intercept": np.nan, "se": np.nan,
                              "stat": float(same), "p_value": float(binom.pvalue),
                              "note": "share of consecutive revisions with the same sign; H0: 0.5 (binomial)"})
                rev_rows.append({"group": g, "family": fam, "unit": unit, "episodes": episodes,
                                 "n_pairs": len(pair), "rho": rho, "same_sign_share": same / len(pair)})
    return pd.DataFrame(facts), pd.DataFrame(tests), pd.DataFrame(rev_rows)


def prespecified_tests(c: pd.DataFrame) -> pd.DataFrame:
    """D22: the numbers-only baseline, with episodes included. Same-sign share of
    consecutive revisions whose later revision is at 12-24 months; error on
    revision at 12-24 months, policy-adjusted (primary) and raw."""
    rows = []
    for g, fam, unit, d in units_of_analysis(c):
        ch = d.sort_values(["series_id", "target_period", "publication_date"])
        ch = ch.assign(rev_prev=ch.groupby(["series_id", "target_period"]).rev.shift())
        pair = ch[(ch.bucket == "12-24")].dropna(subset=["rev", "rev_prev"])
        pair = pair[(pair.rev != 0) & (pair.rev_prev != 0)]
        base = {"group": g, "family": fam, "unit": unit, "bucket": "12-24"}
        if len(pair) >= MIN_N:
            same = int((np.sign(pair.rev) == np.sign(pair.rev_prev)).sum())
            rows.append({**base, "test": "same_sign_share", "errors": "", "n_cells": len(pair),
                         "n_targets": int(target_key(pair).nunique()), "estimate": same / len(pair),
                         "se": np.nan, "p_value": float(sps.binomtest(same, len(pair), 0.5).pvalue),
                         "note": "later revision at 12-24 months; H0: 0.5 (binomial)"})
        db = d[d.bucket == "12-24"]
        for pa, ecol in (("policy_adjusted", "err_pa"), ("raw", "err")):
            r = ols_clustered(db[ecol], db.rev, target_key(db))
            if r is not None:
                res, n, nt = r
                rows.append({**base, "test": "error_on_revision", "errors": pa, "n_cells": n,
                             "n_targets": nt, "estimate": float(res.params[1]), "se": float(res.bse[1]),
                             "p_value": float(res.pvalues[1]),
                             "note": ("primary" if pa == "policy_adjusted" else "robustness")
                                     + "; e = F - A, a negative coefficient = CG's under-reaction"})
    return pd.DataFrame(rows)


def attribution_shares(c: pd.DataFrame) -> pd.DataFrame:
    """Share of the absolute revision coming from each harmonized category, by
    horizon bucket. Uses the category rows that add up to the revision (FRD block
    parts for OBR PSNB; CBO legislative/economic/technical)."""
    att = pd.concat([pd.read_parquet(p) for p in (TABLES / "attribution").glob("*.parquet")])
    att = att[att.category.isin(["policy", "economic_determinants", "calibration_to_outturn",
                                 "classification_one_offs", "modelling_other", "underlying_unsplit"])]
    # OBR FRD: only block-level parts for PSNB £ (sub-rows would double count).
    # OBR EFO: per-tax driver tables only; the receipts-sources tables nest sub-items
    # by formatting, so their rows would double count.
    frd = att.category_raw.str.startswith("FRD")
    att = att[~frd | (att.series_id.eq("obr.psnb_gbp") & att.category_raw.str.match(r"FRD:(policy|classification|underlying) \("))]
    att = att[~(att.category_raw.str.startswith("EFO") & att.series_id.eq("obr.pscr_gbp"))]
    # a group heading repeats the sum of the rows beneath it (rule A2); count the rows
    att = att[~att["flags"].fillna("").str.contains("group_heading")]
    h = c[["series_id", "target_period", "vintage_id", "horizon_months", "family", "group"]].drop_duplicates(
        ["series_id", "target_period", "vintage_id"])
    # derived income-tax series (EFO tables) have no cells: take horizons from IT
    der = att[att.series_id.isin(["obr.it_nics", "obr.nonsa_it", "obr.nonsa_it_nics"])]
    hd = h[h.series_id == "obr.it"].drop(columns="series_id")
    a = pd.concat([att.merge(h, on=["series_id", "target_period", "vintage_id"], how="inner"),
                   der.merge(hd, on=["target_period", "vintage_id"], how="inner")])
    # CBO revenue is split into economic and technical only from 2024 (legislative
    # only before), and so is the deficit, which includes it: their policy share
    # would be overstated (Teo, 29 September 2026). Outlays keep the full split.
    a = a[~(a.group.eq("CBO") & a.series_id.str.match(r"cbo\.(revenue|deficit)\."))]
    a["bucket"] = bucket(a.horizon_months)
    a["abs"] = a.value.abs()
    # D20: EFO rows whose label is still pending use the keyword category provisionally
    a["pending"] = a.origin.map(efo_label_status()).eq("pending")
    a["abs_pending"] = a["abs"].where(a.pending, 0.0)
    tot = a.groupby(["group", "series_id", "bucket"]).abs.sum().rename("total")
    s = a.groupby(["group", "series_id", "family", "bucket", "category"]).agg(
        abs_sum=("abs", "sum"), n=("abs", "size"), n_pending=("pending", "sum"),
        abs_pending=("abs_pending", "sum")).reset_index()
    s = s.merge(tot.reset_index(), on=["group", "series_id", "bucket"])
    s["share_of_abs_revision"] = s.abs_sum / s.total
    s["pending_share_of_abs"] = s.abs_pending / s.abs_sum.where(s.abs_sum > 0)
    return s.drop(columns="abs_pending")


def efo_label_status() -> dict[str, str]:
    """Origin of each EFO attribution row -> status of its label in
    crosswalks/attribution_labels.csv (settled_agreement | pending | reviewed)."""
    from .e2_efo_tables import driver_rows
    drv = driver_rows(pd.read_parquet(STATS / "e2_checks" / "efo_table_rows.parquet"))
    origin = drv.file + "#" + drv.sheet + "!row" + (drv.row + 1).astype(str)
    cw = pd.read_csv(CROSSWALKS / "attribution_labels.csv", dtype=str, keep_default_na=False)
    st = dict(zip(cw[cw.source_table == "EFO"].label_key, cw[cw.source_table == "EFO"].status))
    return dict(zip(origin, drv.label_key.map(st)))


def calibration_predictability(c: pd.DataFrame) -> pd.DataFrame:
    """Plan E5: are the 'calibration to outturn' revisions at vintage v predictable
    from the revisions at earlier vintages? y = calibration revision at v, x = the
    series' revision at the previous vintage, both scaled by the previous forecast
    level (so taxes of different size pool). OBR EFO driver tables only."""
    att = pd.read_parquet(TABLES / "attribution" / "OBR_EFO.parquet")
    att = att[~att["flags"].fillna("").str.contains("group_heading")]
    cal = (att[att.category == "calibration_to_outturn"]
           .groupby(["series_id", "target_period", "vintage_id"]).value.sum().rename("calib").reset_index())
    cells = c[c.source == "OBR"][["series_id", "target_period", "vintage_id", "prev_value", "revision",
                                  "publication_date", "bucket"]]
    cells = cells.sort_values(["series_id", "target_period", "publication_date"])
    cells["rev_prev"] = cells.groupby(["series_id", "target_period"]).revision.shift()
    m = cal.merge(cells, on=["series_id", "target_period", "vintage_id"], how="inner").dropna(
        subset=["prev_value", "rev_prev"])
    # the derived income-tax series have no forecasts of their own: they drop out here
    m = m[m.prev_value > 0]
    m["y"] = m.calib / m.prev_value
    m["x"] = m.rev_prev / m.prev_value
    rows = []
    for label, d in [("all", m)] + [(b, g) for b, g in m.groupby("bucket")]:
        r = ols_clustered(d.y, d.x, target_key(d))
        if r is None:
            continue
        res, n, nt = r
        rows.append({"group": "OBR", "family": "EFO driver tables", "unit": "scaled by previous forecast",
                     "episodes": "with", "errors": "", "bucket": label,
                     "test": "calibration_on_previous_revision", "n_cells": n, "n_targets": nt,
                     "coef": float(res.params[1]), "intercept": float(res.params[0]), "se": float(res.bse[1]),
                     "stat": float(res.tvalues[1]), "p_value": float(res.pvalues[1]),
                     "note": "y = calibration-to-outturn revision at v, x = revision at the previous vintage"})
    return pd.DataFrame(rows)


def calibration_targets(facts: pd.DataFrame, rev: pd.DataFrame) -> dict:
    f = facts[(facts.episodes == "with")]
    out = {}
    for (g, fam, unit), d in f.groupby(["group", "family", "unit"]):
        key = f"{g}/{fam}/{unit}"
        out[key] = {"error_basis": "log" if unit == "pooled_levels" else "level (series unit)"}
        for pa, dd in d.groupby("errors"):
            out[key][pa] = {row.bucket: {"sd_error": row.sd_error, "bias": row.mean_error,
                                         "n_cells": int(row.n_cells), "n_targets": int(row.n_targets)}
                            for row in dd.itertuples()}
        r = rev[(rev.group == g) & (rev.family == fam) & (rev.unit == unit) & (rev.episodes == "with")]
        if len(r):
            out[key]["revision_autocorrelation"] = float(r.rho.iloc[0])
            out[key]["same_sign_share"] = float(r.same_sign_share.iloc[0])
            out[key]["n_revision_pairs"] = int(r.n_pairs.iloc[0])
    return out


def main() -> None:
    c = load_cells()
    facts, tests, rev = facts_and_tests(c)
    tests = pd.concat([tests, calibration_predictability(c)], ignore_index=True)
    facts.to_csv(STATS / "stylized_facts.csv", index=False)
    tests.to_csv(STATS / "efficiency_tests.csv", index=False)
    shares = attribution_shares(c)
    shares.to_csv(STATS / "attribution_shares.csv", index=False)
    pre = prespecified_tests(c)
    pre.to_csv(STATS / "prespecified_tests.csv", index=False)
    targets = calibration_targets(facts, rev)
    (STATS / "calibration_targets.json").write_text(json.dumps(
        {"description": "Calibration targets for the synthetic generator (plan E5). Error basis: log "
                        "error for pooled level series, series unit otherwise. Buckets in months "
                        "to the end of the target period (D6). Episodes included.",
         "targets": targets}, indent=2, default=float))
    from .schemas import check_columns, write_schema
    for name, df in [("stats/stylized_facts", facts), ("stats/efficiency_tests", tests),
                     ("stats/attribution_shares", shares), ("stats/prespecified_tests", pre)]:
        check_columns(name, df)
        write_schema(name, STATS.parent)
    complete = (c[c.outturn_latest.notna()].groupby(["group", "series_id"]).target_period.nunique()
                .rename("complete_target_periods").reset_index())
    complete.to_csv(STATS / "complete_target_periods.csv", index=False)
    print(facts.groupby(["group", "errors"]).size())
    print(tests.groupby(["group", "test"]).size())


if __name__ == "__main__":
    main()
