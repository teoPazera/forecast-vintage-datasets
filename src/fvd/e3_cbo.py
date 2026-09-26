"""Stage E3: CBO forecasts, outturns and attribution, with replication of CBO's errors.

Run:  python -m fvd.e3_cbo

Writes (CBO partitions):
  tables/{series,vintages,forecasts,outturns}/CBO.parquet
  tables/attribution/CBO.parquet          legislative / economic / technical changes
  tables/vintages/CBO_intermediate.parquet   year-end change records without a baseline
  stats/cbo_replication/*.csv, summary.json
  stats/e3_checks/*.csv
"""

from __future__ import annotations

import json
import re

import numpy as np
import pandas as pd

from .paths import INVENTORY, ROOT, STATS, TABLES
from .periods import add_role_and_horizon
from .schemas import check_columns, write_schema

REPO = ROOT / "raw/cbo/eval-projections-682559c"
IN = REPO / "input_data"
OUT = REPO / "output_data"
REPL = STATS / "cbo_replication"
CHECKS = STATS / "e3_checks"

D3 = {"Legislative": "policy", "Economic": "economic_determinants", "Technical": "modelling_other"}

PARENTS = {  # (component, subcategory) -> parent subcategory, same component
    ("outlay", "Defense Discretionary"): "Total Discretionary",
    ("outlay", "Nondefense Discretionary"): "Total Discretionary",
    ("outlay", "Social Security"): "Total Mandatory", ("outlay", "Medicare"): "Total Mandatory",
    ("outlay", "Medicaid"): "Total Mandatory", ("outlay", "Other Mandatory"): "Total Mandatory",
    ("outlay", "Fannie Freddie"): "Total Mandatory",
    ("outlay", "Total Discretionary"): "Total", ("outlay", "Total Mandatory"): "Total",
    ("outlay", "Net Interest"): "Total",
}
REVENUE_CATS = ["Individual Income Taxes", "Payroll Taxes", "Corporate Income Taxes", "Excise Taxes",
                "Estate and Gift Taxes", "Customs Duties", "Miscellaneous Receipts"]


def series_id(component: str, subcategory: str) -> str:
    return f"cbo.{component}.{re.sub(r'[^0-9a-z]+', '_', subcategory.lower()).strip('_')}"


def family(component: str, category: str, subcategory: str) -> str:
    if subcategory == "Total" or component in ("deficit", "debt"):
        return "aggregate"
    if component == "revenue":
        return "revenue_" + re.sub(r"[^0-9a-z]+", "_", category.lower()).strip("_")
    return "outlay_" + re.sub(r"[^0-9a-z]+", "_", category.lower()).strip("_")


def load():
    b = pd.read_csv(IN / "baselines.csv")
    c = pd.read_csv(IN / "baseline_changes.csv")
    a = pd.read_csv(IN / "actuals.csv")
    g = pd.read_csv(IN / "actual_GDP.csv")
    return b, c, a, g


# --- common tables ----------------------------------------------------------------

def build_series(b: pd.DataFrame, a: pd.DataFrame, vint: pd.DataFrame) -> pd.DataFrame:
    keys = b[["component", "category", "subcategory"]].drop_duplicates()
    rows = []
    for _, k in keys.iterrows():
        sub = b[(b.component == k.component) & (b.subcategory == k.subcategory)]
        parent = None
        if k.component == "revenue" and k.subcategory != "Total":
            parent = series_id("revenue", "Total")
        elif (k.component, k.subcategory) in PARENTS:
            parent = series_id(k.component, PARENTS[(k.component, k.subcategory)])
        vals = pd.concat([sub.value, a[(a.component == k.component) & (a.subcategory == k.subcategory)].actual_value])
        kind = "balance" if k.component == "deficit" or (vals <= 0).any() else "level"
        dates = sorted(sub.baseline_date.unique())
        note = ""
        if k.component == "deficit":
            note = "budget balance: revenue minus outlays; negative = deficit"
        if k.subcategory == "Fannie Freddie":
            note = "removed from CBO's totals in its evaluations (README)"
        rows.append({"source": "CBO", "series_id": series_id(k.component, k.subcategory),
                     "source_code": f"{k.component}/{k.category}/{k.subcategory}",
                     "name": f"{k.component.capitalize()}: {k.subcategory}",
                     "parent_series_id": parent, "family": family(k.component, k.category, k.subcategory),
                     "unit": "$ billion", "unit_harmonized": "USD bn", "kind": kind,
                     "period_type": "us_fiscal_year",
                     "first_vintage_id": f"cbo_{dates[0][:7]}", "last_vintage_id": f"cbo_{dates[-1][:7]}",
                     "notes": note})
    return pd.DataFrame(rows)


def build_vintages() -> pd.DataFrame:
    cal = pd.read_csv(INVENTORY / "vintage_calendar.csv")
    v = cal[cal.source == "CBO"].copy()
    v["flags"] = v["flags"].fillna("")
    return v[["source", "vintage_id", "label", "publication_date", "date_certainty", "date_basis",
              "forecaster", "flags", "primary_document_id"]].reset_index(drop=True)


def build_forecasts(b: pd.DataFrame, vint: pd.DataFrame) -> pd.DataFrame:
    fc = b.reset_index().rename(columns={"index": "row"})
    fc["series_id"] = [series_id(c, s) for c, s in zip(fc.component, fc.subcategory)]
    fc["vintage_id"] = "cbo_" + fc.baseline_date.str[:7]
    fc["target_period"] = fc.projected_fiscal_year.astype(str)
    fc["period_type"] = "us_fiscal_year"
    fc = fc.merge(vint[["vintage_id", "publication_date"]], on="vintage_id", how="left")
    fc = add_role_and_horizon(fc)
    fc["source"] = "CBO"
    fc["value_source_unit"] = fc.value
    fc["origin"] = "CBO:baselines.csv#" + (fc.row + 2).astype(str)   # 1-based line incl. header
    return fc[["source", "series_id", "target_period", "vintage_id", "value_source_unit", "value",
               "cell_role", "horizon_months", "origin"]]


def build_outturns(a: pd.DataFrame, series_ids: set[str]) -> pd.DataFrame:
    o = a.reset_index().rename(columns={"index": "row"})
    o["series_id"] = [series_id(c, s) for c, s in zip(o.component, o.subcategory)]
    o = o[o.series_id.isin(series_ids)]   # drops the one-off student loan forgiveness line
    return pd.DataFrame({
        "source": "CBO", "series_id": o.series_id, "target_period": o.fiscal_year.astype(str),
        "value_latest": o.actual_value, "value_first_estimate": np.nan,
        "first_estimate_vintage_id": None,
        "origin": "CBO:actuals.csv#" + (o.row + 2).astype(str)})


# --- checks ----------------------------------------------------------------------------

def hierarchy_residuals(b: pd.DataFrame) -> pd.DataFrame:
    rows = []
    piv = b.pivot_table(index=["baseline_date", "projected_fiscal_year"],
                        columns=["component", "subcategory"], values="value", aggfunc="first")
    groups = [("revenue", "Total", [("revenue", c) for c in REVENUE_CATS]),
              ("outlay", "Total", [("outlay", "Total Discretionary"), ("outlay", "Total Mandatory"),
                                   ("outlay", "Net Interest")]),
              ("outlay", "Total Discretionary", [("outlay", "Defense Discretionary"),
                                                 ("outlay", "Nondefense Discretionary")]),
              ("outlay", "Total Mandatory", [("outlay", s) for s in
                                             ("Social Security", "Medicare", "Medicaid", "Other Mandatory")]),
              ("outlay", "Total Mandatory (incl. Fannie Freddie)",
               [("outlay", s) for s in ("Social Security", "Medicare", "Medicaid", "Other Mandatory",
                                        "Fannie Freddie")])]
    for comp, parent, kids in groups:
        pkey = (comp, parent.split(" (")[0])
        kids = [k for k in kids if k in piv]
        sub = piv[[pkey] + kids].dropna(subset=[pkey])
        sub = sub[sub[kids].notna().all(axis=1) if "Fannie" not in parent else sub[kids[:4]].notna().all(axis=1)]
        s = sub[kids].sum(axis=1, min_count=1)
        for (bd, fy), p in sub[pkey].items():
            rows.append({"identity": f"{comp}: {parent}", "baseline_date": bd, "projected_fiscal_year": fy,
                         "parent_value": p, "children_sum": s[(bd, fy)], "residual": p - s[(bd, fy)]})
    return pd.DataFrame(rows)


def changes_relation(b: pd.DataFrame, c: pd.DataFrame) -> pd.DataFrame:
    """Does previous baseline + (legislative + economic + technical) = current baseline?

    For every change date that is also a baseline date, the change is compared
    with the difference from the immediately preceding baseline of the same
    series. Year-end change dates without a baseline are reported separately.
    """
    bl = b.set_index(["component", "subcategory", "baseline_date", "projected_fiscal_year"]).value
    tot = (c.groupby(["component", "subcategory", "changes_baseline_date", "projected_fiscal_year"])
           .agg(total=("value", "sum"), types=("change_category", lambda s: ",".join(sorted(set(s))))))
    dates = b.groupby(["component", "subcategory"]).baseline_date.apply(lambda s: sorted(set(s)))
    rows = []
    for (comp, sub, cd, fy), r in tot.iterrows():
        ds = dates.get((comp, sub), [])
        prev = [d for d in ds if d < cd]
        cur = bl.get((comp, sub, cd, fy))
        prv = bl.get((comp, sub, prev[-1], fy)) if prev else None
        rows.append({"component": comp, "subcategory": sub, "changes_baseline_date": cd,
                     "projected_fiscal_year": fy, "change_types": r.types, "changes_total": r.total,
                     "previous_baseline": prev[-1] if prev else None,
                     "has_baseline": cd in ds, "baseline_diff": (cur - prv) if cur is not None and prv is not None else np.nan})
    df = pd.DataFrame(rows)
    df["abs_diff"] = (df.baseline_diff - df.changes_total).abs()
    return df


def build_attribution(c: pd.DataFrame, b: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    dates = b.groupby(["component", "subcategory"]).baseline_date.apply(lambda s: sorted(set(s)))
    all_baselines = set(b.baseline_date)
    df = c.reset_index().rename(columns={"index": "row"})
    prev = []
    for comp, sub, cd in zip(df.component, df.subcategory, df.changes_baseline_date):
        ds = [d for d in dates.get((comp, sub), []) if d < cd]
        prev.append(f"cbo_{ds[-1][:7]}" if ds else None)
    df["previous_vintage_id"] = prev
    df["vintage_id"] = ["cbo_" + d[:7] if d in all_baselines else f"cbo_{d[:7]}_yearend"
                        for d in df.changes_baseline_date]
    att = pd.DataFrame({
        "source": "CBO", "series_id": [series_id(a, s) for a, s in zip(df.component, df.subcategory)],
        "target_period": df.projected_fiscal_year.astype(str), "vintage_id": df.vintage_id,
        "previous_vintage_id": df.previous_vintage_id,
        "category_raw": "CBO:" + df.change_category, "category": df.change_category.map(D3),
        "value": df.value, "flags": np.where(df.vintage_id.str.endswith("_yearend"), "yearend_changes", ""),
        "origin": "CBO:baseline_changes.csv#" + (df.row + 2).astype(str)})
    # Year-end change records are not baselines: keep them as intermediate vintages.
    ye = sorted({d for d in c.changes_baseline_date if d not in all_baselines})
    inter = pd.DataFrame([{
        "source": "CBO", "vintage_id": f"cbo_{d[:7]}_yearend", "label": f"{d[:7]} (year-end changes)",
        "publication_date": None, "date_certainty": "unknown",
        "date_basis": "change record without a baseline (README: changes recorded after the last "
                      "outlook of the year)", "forecaster": "CBO", "flags": "intermediate:changes_only",
        "primary_document_id": None} for d in ye])
    return att, inter


# --- replication -----------------------------------------------------------------------

def replicate_errors(b, c, a, g, component: str) -> pd.DataFrame:
    """CBO's projection errors, reimplemented from the method in the repository's README
    and src/: projection + legislative changes dated after the baseline - actual."""
    if component == "revenue":
        sel = b[(b.component == component) & (b.Winter_flag | b.Spring_flag)]
    else:
        sel = b[(b.component == component) & b.Spring_flag]
    df = sel.merge(a.rename(columns={"fiscal_year": "projected_fiscal_year"}),
                   on=["component", "category", "subcategory", "projected_fiscal_year"], how="inner")
    df = df.merge(g.rename(columns={"fiscal_year": "projected_fiscal_year"}), on="projected_fiscal_year", how="left")
    chg_comp = "deficit" if component == "debt" else component
    leg = c[(c.component == chg_comp) & (c.change_category == "Legislative")].copy()
    leg["component"] = component
    m = df.merge(leg[["component", "category", "subcategory", "projected_fiscal_year",
                      "changes_baseline_date", "value"]].rename(columns={"value": "leg"}),
                 on=["component", "category", "subcategory", "projected_fiscal_year"], how="inner")
    m = m[pd.to_datetime(m.changes_baseline_date) > pd.to_datetime(m.baseline_date)]
    keys = ["component", "category", "subcategory", "baseline_date", "projected_fiscal_year",
            "projected_year_number"]
    agg = m.groupby(keys).leg.sum().rename("leg_change").reset_index()
    if component == "debt":
        agg["leg_change"] = -agg.leg_change
        agg = agg.sort_values(keys)
        agg["leg_change"] = agg.groupby(["baseline_date"]).leg_change.cumsum()
    out = df.merge(agg, on=keys, how="inner")
    out = out[(out.subcategory != "Fannie Freddie") & (out.projected_year_number != 0)]
    out["adjusted_projection"] = out.value + out.leg_change
    out["projection_error"] = out.adjusted_projection - out.actual_value
    if component == "deficit":
        out["projection_error"] *= -1
    if component in ("outlay", "revenue"):
        out["projection_error_pct_actual"] = out.projection_error / out.actual_value * 100
    out["projection_error_pct_GDP"] = out.projection_error / out.GDP * 100
    return out


def replicate_summary(err: pd.DataFrame, component: str) -> pd.DataFrame:
    col = "projection_error_pct_GDP" if component in ("deficit", "debt") else "projection_error_pct_actual"
    e = err[err.Winter_flag] if component == "revenue" else err
    g = e.groupby(["component", "category", "subcategory", "projected_year_number"])[col]
    return pd.DataFrame({
        "number_of_projections": g.count(), "average_error": g.mean(),
        "average_absolute_error": g.apply(lambda x: x.abs().mean()),
        "RMSE": g.apply(lambda x: np.sqrt((x ** 2).mean())),
        "two_thirds_spread": g.quantile(5 / 6) - g.quantile(1 / 6)}).reset_index()


def compare(mine: pd.DataFrame, cbo: pd.DataFrame, keys: list[str], cols: list[str], decimals: int) -> pd.DataFrame:
    """Compare after rounding ours as CBO rounds its files (%.3f rows, %.1f summaries)."""
    m = mine.copy()
    for k in keys:
        m[k] = m[k].astype(str)
        cbo[k] = cbo[k].astype(str)
    j = cbo.merge(m[keys + cols], on=keys, how="outer", suffixes=("_cbo", "_ours"), indicator=True)
    out = j[keys + ["_merge"]].copy()
    worst = pd.Series(0.0, index=j.index)
    for col in cols:
        d = (j[f"{col}_ours"].round(decimals) - j[f"{col}_cbo"]).abs()
        out[f"diff_{col}"] = d
        worst = np.fmax(worst, d.fillna(np.inf))
    out["max_abs_diff"] = worst
    return out


def main() -> None:
    REPL.mkdir(parents=True, exist_ok=True)
    CHECKS.mkdir(parents=True, exist_ok=True)
    b, c, a, g = load()
    vint = build_vintages()
    series = build_series(b, a, vint)
    fc = build_forecasts(b, vint)
    out = build_outturns(a, set(series.series_id))
    att, inter = build_attribution(c, b)

    for name, df in [("series", series), ("vintages", vint), ("forecasts", fc), ("outturns", out)]:
        check_columns(f"tables/{name}", df)
        (TABLES / name).mkdir(parents=True, exist_ok=True)
        df.to_parquet(TABLES / name / "CBO.parquet", index=False)
    check_columns("tables/attribution", att)
    att.to_parquet(TABLES / "attribution" / "CBO.parquet", index=False)
    check_columns("tables/vintages", inter)
    inter.to_parquet(TABLES / "vintages" / "CBO_intermediate.parquet", index=False)

    res = hierarchy_residuals(b)
    res.to_csv(CHECKS / "hierarchy_residuals.csv", index=False)
    rel = changes_relation(b, c)
    rel.to_csv(CHECKS / "baseline_changes_relation.csv", index=False)

    # replication
    rep = {}
    for comp in ("revenue", "outlay", "deficit", "debt"):
        err = replicate_errors(b, c, a, g, comp)
        cbo_err = pd.read_csv(OUT / f"{comp}_projection_errors.csv")
        keys = ["component", "category", "subcategory", "baseline_date", "projected_fiscal_year"]
        cols = ["projection_error", "projection_error_pct_GDP"] + \
            (["projection_error_pct_actual"] if comp in ("outlay", "revenue") else [])
        ce = compare(err, cbo_err, keys, cols, 3)
        ce.to_csv(REPL / f"{comp}_errors_comparison.csv", index=False)
        sm = replicate_summary(err, comp)
        cbo_sm = pd.read_csv(OUT / f"{comp}_projection_errors_summary_stats.csv")
        cs = compare(sm, cbo_sm, ["component", "category", "subcategory", "projected_year_number"],
                     ["number_of_projections", "average_error", "average_absolute_error", "RMSE",
                      "two_thirds_spread"], 1)
        cs.to_csv(REPL / f"{comp}_summary_comparison.csv", index=False)
        rep[comp] = {
            "error_rows_cbo": len(cbo_err), "error_rows_ours": len(err),
            "rows_only_in_one": int((ce._merge != "both").sum()),
            "error_rows_within_0.01": int((ce.max_abs_diff <= 0.01 + 1e-9).sum()),
            "error_max_abs_diff": float(ce.max_abs_diff.replace(np.inf, np.nan).max()),
            "summary_rows": len(cbo_sm), "summary_only_in_one": int((cs._merge != "both").sum()),
            "summary_rows_within_0.01": int((cs.max_abs_diff <= 0.01 + 1e-9).sum()),
        }

    # stats
    rel_b = rel[rel.has_baseline & rel.baseline_diff.notna()]
    full = rel_b[rel_b.change_types == "Economic,Legislative,Technical"]
    summary = {
        "series": len(series), "vintages": len(vint), "forecast_cells": len(fc), "outturns": len(out),
        "cells_by_role": fc.cell_role.value_counts().to_dict(),
        "attribution_rows": len(att), "intermediate_vintages": len(inter),
        "hierarchy_max_abs_residual": res.groupby("identity").residual.apply(lambda s: float(s.abs().max())).to_dict(),
        "hierarchy_share_within_0.5": res.groupby("identity").residual.apply(lambda s: round(float((s.abs() <= 0.5).mean()), 4)).to_dict(),
        "changes_relation": {
            "category_years_tested": len(rel_b),
            "with_all_three_types": len(full),
            "all_three_types_within_0.5": round(float((full.abs_diff <= 0.5).mean()), 4) if len(full) else None,
            "by_component_all_three_within_0.5": full.groupby("component").abs_diff.apply(lambda s: round(float((s <= 0.5).mean()), 4)).to_dict(),
            "legislative_only_within_0.5": round(float((rel_b[rel_b.change_types == "Legislative"].abs_diff <= 0.5).mean()), 4),
            "yearend_change_rows_without_baseline": int((~rel.has_baseline).sum()),
        },
        "replication": rep,
    }
    (REPL / "summary.json").write_text(json.dumps(summary["replication"], indent=2))
    (CHECKS / "summary.json").write_text(json.dumps(summary, indent=2, default=str))
    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()
