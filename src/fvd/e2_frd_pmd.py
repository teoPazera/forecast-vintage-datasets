"""Stage E2, part 1: OBR Forecast Revisions Database and Policy Measures Database.

Run:  python -m fvd.e2_frd_pmd

Writes:
  tables/attribution/OBR_FRD.parquet     aggregate attribution (PSNB, and PSCR/TME from its rows)
  tables/policy_measures/OBR.parquet     PMD tax and spending measures
  tables/vintages/OBR_intermediate.parquet   forecasts in the FRD that are not HOFD vintages
  crosswalks/pmd_events.csv, crosswalks/pmd_heads.csv, crosswalks/attribution_labels.csv
  stats/e2_checks/frd_vs_hofd.csv and summary_frd_pmd.json
"""

from __future__ import annotations

import json
import re

import openpyxl
import pandas as pd

from . import crosswalks as X
from . import obr_series as S
from .obr_web import walk_chain
from .paths import CROSSWALKS, ROOT, STATS, TABLES
from .periods import normalize_uk_fiscal
from .schemas import check_columns, write_schema

FRD = ROOT / "raw/obr/Fiscal_forecast_revisions_database_March_2026.xlsx"
PMD = ROOT / "raw/obr/Policy_measures_database_March_2026.xlsx"
CHECKS = STATS / "e2_checks"
EXTRAPOLATED_FILL = "FFE1E9EE"   # PMD Notes 'Shading key', row 11

_BLOCK = re.compile(r"^\s*((January|February|March|April|May|June|July|August|September|October|"
                    r"November|December) \d{4}( restated)?|FSR\+SEU 2020)\s*$")

# Row labels inside a block -> (level, name). Level "top" starts a new group.
_TOP = {"policy": "policy", "of which policy": "policy",
        "classifications and one-offs": "classification", "of which classification": "classification",
        "underlying": "underlying", "underlying1": "underlying", "underlying2": "underlying",
        "of which underlying": "underlying"}
_SUB = {"of which: receipts": "receipts", "of which receipts": "receipts",
        "of which: spending": "spending", "of which: debt interest": "debt_interest",
        "of which debt interest spending": "debt_interest",
        "of which: non-interest spending": "non_interest_spending",
        "of which non-interest spending": "non_interest_spending",
        "of which receipts policy": "policy/receipts", "of which spending policy": "policy/spending"}


def _cell(sheet, r0, c0):
    return f"FRD:{sheet}!{openpyxl.utils.get_column_letter(c0 + 1)}{r0 + 1}"


def parse_frd_sheet(wb, sheet: str) -> pd.DataFrame:
    rows = list(wb[sheet].iter_rows(values_only=True))
    periods = {j: normalize_uk_fiscal(v) for j, v in enumerate(rows[1]) if normalize_uk_fiscal(v)}
    out, block, top = [], None, None
    for i, r in enumerate(rows[2:], start=2):
        lab = r[0].strip() if isinstance(r[0], str) else None
        if lab is None:
            continue
        if _BLOCK.match(lab):
            block, top, path = lab, None, "total"
        elif block is None:
            continue
        else:
            key = lab.lower()
            if key in _TOP:
                top = _TOP[key]
                path = top
            elif key in _SUB:
                sub = _SUB[key]
                path = sub if "/" in sub else f"{top}/{sub}"
            else:
                continue   # "of which:" spacer rows and notes
        for j, tp in periods.items():
            v = r[j] if j < len(r) else None
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                out.append({"block": block, "row_label": lab, "path": path, "target_period": tp,
                            "value": float(v), "origin": _cell(sheet, i, j)})
    df = pd.DataFrame(out)
    # Policy values in years the block total does not cover are revisions relative to
    # the pre-measures forecast (FRD note *); flag them.
    tot = set(zip(df[df.path == "total"].block, df[df.path == "total"].target_period))
    df["pre_measures_year"] = [(b, t) not in tot for b, t in zip(df.block, df.target_period)]
    return df


def parse_frd_classifications(wb) -> pd.DataFrame:
    """PSCR and TME classification changes, each in its own sign convention."""
    rows = list(wb["Classifications and one-offs"].iter_rows(values_only=True))
    periods = {j: normalize_uk_fiscal(v) for j, v in enumerate(rows[1]) if normalize_uk_fiscal(v)}
    out, section = [], None
    for i, r in enumerate(rows[2:], start=2):
        a = r[0].strip() if isinstance(r[0], str) else None
        if a in ("Public Sector Current Receipts (PSCR)", "Total Managed Expenditure (TME)",
                 "Public Sector Net Borrowing (PSNB)"):
            section = {"Public Sector Current Receipts (PSCR)": "£PSCR",
                       "Total Managed Expenditure (TME)": "£TME",
                       "Public Sector Net Borrowing (PSNB)": "£PSNB"}[a]
            continue
        if section is None or a is None or a.startswith("Footnotes"):
            continue
        m = re.match(r"^(.*?)( \(\d\))?( forecast)?$", a)
        for j, tp in periods.items():
            v = r[j] if j < len(r) else None
            try:
                val = float(v)
            except (TypeError, ValueError):
                continue
            out.append({"sheet": section, "block": m.group(1), "entry": a,
                        "description": str(r[1] or "").strip(), "target_period": tp,
                        "value": val, "origin": _cell("Classifications and one-offs", i, j)})
    return pd.DataFrame(out)


# --- vintages --------------------------------------------------------------------

def intermediate_vintages() -> pd.DataFrame:
    """Forecasts in the FRD that are not HOFD vintages: the July 2020 fiscal
    sustainability report scenario ('FSR+SEU 2020'). Date from the OBR's own page."""
    pages = walk_chain("https://obr.uk/frs/fiscal-risks-and-sustainability-july-2025/", "Previous report")
    fsr = [p for p in pages if "2020" in p.title and "July" in p.title]
    d = fsr[0].publication_date.isoformat() if fsr and fsr[0].publication_date else None
    return pd.DataFrame([{
        "source": "OBR", "vintage_id": "obr_2020-07_fsr", "label": "FSR+SEU 2020",
        "publication_date": d, "date_certainty": "exact" if d else "unknown",
        "date_basis": f"landing page {fsr[0].url}" if fsr else "FSR July 2020 page not found",
        "forecaster": "OBR", "flags": "intermediate:frd_only", "primary_document_id": None,
    }])


def block_vintage_map(vint: pd.DataFrame) -> dict[str, str]:
    by_label = dict(zip(vint.label, vint.vintage_id))
    m = {}
    for lab in by_label:
        m[lab] = by_label[lab]
    m["March 2019 restated"] = "obr_2019-03_restated"
    m["FSR+SEU 2020"] = "obr_2020-07_fsr"
    return m


# --- attribution ---------------------------------------------------------------------

def frd_attribution(frd_gbp, frd_pct, cls, vmap) -> pd.DataFrame:
    order = list(dict.fromkeys(frd_gbp.block))
    prev = {b: (order[k - 1] if k else "June 2010") for k, b in enumerate(order)}
    rows = []

    def add(series_sheet, df, sign, keep):
        for _, r in df[df.path.isin(keep)].iterrows():
            cat, _ = X.FRD_PATHS[r.path]
            rows.append({"source": "OBR", "series_id": S.series_id(series_sheet),
                         "target_period": r.target_period, "vintage_id": vmap[r.block],
                         "previous_vintage_id": vmap[prev[r.block]],
                         "category_raw": f"FRD:{r.path} ({r.row_label})", "category": cat,
                         "value": sign * r.value,
                         "flags": "pre_measures_year" if r.pre_measures_year else "",
                         "origin": r.origin})

    all_paths = list(X.FRD_PATHS)
    add("£PSNB", frd_gbp, 1, all_paths)
    add("PSNB", frd_pct, 1, all_paths)
    # Receipts rows are revisions to PSNB: a receipts upgrade is negative. In the
    # receipts convention (positive = receipts raised) the sign flips (plan 4.2).
    add("£PSCR", frd_gbp, -1, ["policy/receipts", "underlying/receipts"])
    add("£TME", frd_gbp, 1, ["policy/spending", "underlying/debt_interest",
                             "underlying/non_interest_spending"])
    # Classification changes by aggregate, each in its own convention.
    for sheet, g in cls[cls.sheet.isin(["£PSCR", "£TME"])].groupby("sheet"):
        for _, r in g.iterrows():
            if r.block not in vmap:
                continue
            rows.append({"source": "OBR", "series_id": S.series_id(sheet), "target_period": r.target_period,
                         "vintage_id": vmap[r.block], "previous_vintage_id": vmap.get(prev.get(r.block, ""), None),
                         "category_raw": f"FRD classifications: {r.description}",
                         "category": "classification_one_offs", "value": r.value, "flags": "",
                         "origin": r.origin})
    return pd.DataFrame(rows)


def frd_vs_hofd(att: pd.DataFrame) -> pd.DataFrame:
    """FRD block total vs the HOFD £PSNB difference between the block's vintage and
    the previous one. Blocks around the FSR 2020 scenario are chained."""
    fc = pd.read_parquet(TABLES / "forecasts" / "OBR.parquet")
    psnb = fc[fc.series_id == "obr.psnb_gbp"].set_index(["vintage_id", "target_period"]).value
    tot = att[(att.series_id == "obr.psnb_gbp") & (att.category == "total")].copy()
    # chain FSR: March 2020 -> FSR -> November 2020 compared as one step
    fsr = tot[tot.vintage_id == "obr_2020-07_fsr"].set_index("target_period").value
    rows = []
    for _, r in tot.iterrows():
        if r.vintage_id == "obr_2020-07_fsr":
            continue
        prev, val = r.previous_vintage_id, r.value
        if prev == "obr_2020-07_fsr":
            prev, val = "obr_2020-03", val + fsr.get(r.target_period, float("nan"))
        a, b = psnb.get((r.vintage_id, r.target_period)), psnb.get((prev, r.target_period))
        if a is None or b is None:
            continue
        # Early OBR vintages are published to whole £ billion in the HOFD; allow for that.
        tol = 0.1 + half_unit(a) + half_unit(b)
        rows.append({"vintage_id": r.vintage_id, "previous_vintage_id": prev,
                     "target_period": r.target_period, "frd_total": val, "hofd_diff": a - b,
                     "abs_diff": abs(val - (a - b)), "tolerance": tol,
                     "note": ("FRD block is zero: the restatement is recorded on the FRD "
                              "Classifications sheet, not as a revision block"
                              if r.vintage_id == "obr_2019-03_restated" else "")})
    return pd.DataFrame(rows)


def half_unit(v: float) -> float:
    """Half the last published digit: 0.5 for whole numbers, 0.05 for one decimal."""
    for d, h in ((0, 0.5), (1, 0.05), (2, 0.005)):
        if abs(v - round(v, d)) < 1e-9:
            return h
    return 0.0


# --- PMD -------------------------------------------------------------------------------

def parse_pmd() -> pd.DataFrame:
    wb = openpyxl.load_workbook(PMD)   # not read-only: cell fills mark extrapolated costings
    out = []
    for sheet, mtype in (("Tax Measures", "tax"), ("Spending Measures", "spending")):
        ws = wb[sheet]
        header = [c.value for c in ws[3]]
        years = {j: normalize_uk_fiscal(v) for j, v in enumerate(header) if normalize_uk_fiscal(v)}
        for row in ws.iter_rows(min_row=4):
            event, measure, head = (row[1].value, row[2].value, row[3].value)
            if not event:
                continue
            for j, tp in years.items():
                c = row[j]
                if not isinstance(c.value, (int, float)) or isinstance(c.value, bool):
                    continue
                fill = c.fill.fgColor.rgb if c.fill and c.fill.fill_type else None
                out.append({"measure_type": mtype, "event_raw": str(event).strip(),
                            "measure": str(measure or "").strip(), "head_raw": str(head or "").strip(),
                            "target_period": tp, "value_gbp_m": float(c.value),
                            "extrapolated": fill == EXTRAPOLATED_FILL,
                            "origin": f"PMD:{sheet}!{c.coordinate}"})
    return pd.DataFrame(out)


def build_crosswalks(pmd: pd.DataFrame, vint: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    hmt = vint[vint.forecaster == "HM Treasury"].label.tolist()
    lab2id = dict(zip(vint.label, vint.vintage_id))
    ev = []
    for e in pd.unique(pmd.event_raw):
        lab, rule, conf = X.map_event(e, hmt)
        ev.append({"event_raw": e, "vintage_label": lab, "vintage_id": lab2id.get(lab),
                   "rule": rule, "confidence": conf, "reviewed": False})
    heads = []
    for (mt, h), g in pmd.groupby(["measure_type", "head_raw"]):
        sheet, conf = X.map_head(h, mt)
        heads.append({"measure_type": mt, "head_raw": h, "hofd_sheet": sheet,
                      "series_id": S.series_id(sheet) if sheet else None,
                      "aggregate_series_id": S.series_id("£PSCR" if mt == "tax" else "£TME"),
                      "confidence": conf.split(":")[0], "note": conf.partition(":")[2].strip(),
                      "n_measures": g.measure.nunique(), "reviewed": False})
    return pd.DataFrame(ev), pd.DataFrame(heads)


def policy_measures(pmd, events, heads) -> pd.DataFrame:
    df = pmd.merge(events[["event_raw", "vintage_id"]], on="event_raw", how="left") \
            .merge(heads[["measure_type", "head_raw", "series_id"]], on=["measure_type", "head_raw"], how="left")
    # PMD sign: positive = gain to the Exchequer. In the affected series' convention a
    # tax gain raises receipts (same sign) and a spending gain lowers spending (flip).
    sign = df.measure_type.map({"tax": 1, "spending": -1})
    df["value"] = sign * df.value_gbp_m / 1000.0
    df["source"] = "OBR"
    return df[["source", "measure_type", "event_raw", "vintage_id", "measure", "head_raw", "series_id",
               "target_period", "value_gbp_m", "value", "extrapolated", "origin"]]


def main() -> None:
    CHECKS.mkdir(parents=True, exist_ok=True)
    CROSSWALKS.mkdir(parents=True, exist_ok=True)
    vint = pd.read_parquet(TABLES / "vintages" / "OBR.parquet")
    inter = intermediate_vintages()
    inter.to_parquet(TABLES / "vintages" / "OBR_intermediate.parquet", index=False)
    vmap = block_vintage_map(pd.concat([vint, inter]))

    wb = openpyxl.load_workbook(FRD, read_only=True, data_only=True)
    gbp = parse_frd_sheet(wb, "Revisions (£ billion)")
    pct = parse_frd_sheet(wb, "Revisions (Per cent of GDP)")
    pct["block"] = pct.block.str.strip()
    cls = parse_frd_classifications(wb)
    att = frd_attribution(gbp, pct, cls, vmap)
    check_columns("tables/attribution", att)
    (TABLES / "attribution").mkdir(parents=True, exist_ok=True)
    att.to_parquet(TABLES / "attribution" / "OBR_FRD.parquet", index=False)
    write_schema("tables/attribution", ROOT)

    chk = frd_vs_hofd(att)
    chk.to_csv(CHECKS / "frd_vs_hofd.csv", index=False)

    # sums: policy + classification + underlying = total, per block and year
    t = att[att.series_id == "obr.psnb_gbp"]
    parts = t[t.category_raw.str.match(r"FRD:(policy|classification|underlying) \(")]
    s = parts.groupby(["vintage_id", "target_period"]).value.sum()
    tot = t[t.category == "total"].set_index(["vintage_id", "target_period"]).value
    both = pd.concat([tot.rename("total"), s.rename("parts")], axis=1).dropna()
    both["abs_diff"] = (both.total - both.parts).abs()
    both.to_csv(CHECKS / "frd_parts_sum.csv")

    pmd = parse_pmd()
    events, heads = build_crosswalks(pmd, pd.concat([vint, inter]))
    events.to_csv(CROSSWALKS / "pmd_events.csv", index=False)
    heads.to_csv(CROSSWALKS / "pmd_heads.csv", index=False)
    pm = policy_measures(pmd, events, heads)
    check_columns("tables/policy_measures", pm)
    (TABLES / "policy_measures").mkdir(parents=True, exist_ok=True)
    pm.to_parquet(TABLES / "policy_measures" / "OBR.parquet", index=False)
    write_schema("tables/policy_measures", ROOT)

    since2010 = events[events.vintage_id.fillna("").str.startswith("obr_")]
    summary = {
        "frd_blocks": gbp.block.nunique(), "frd_rows_gbp": len(gbp), "frd_rows_pct": len(pct),
        "attribution_rows": len(att),
        "attribution_rows_by_series": att.groupby("series_id").size().to_dict(),
        "frd_vs_hofd_cells": len(chk),
        "frd_vs_hofd_within_0.1": int((chk.abs_diff <= 0.1).sum()),
        "frd_vs_hofd_within_rounding_tolerance": int((chk.abs_diff <= chk.tolerance).sum()),
        "frd_vs_hofd_restated_block_cells": int((chk.note != "").sum()),
        "frd_vs_hofd_share_within_tolerance_excl_restated":
            round(float((chk[chk.note == ""].abs_diff <= chk[chk.note == ""].tolerance).mean()), 4),
        "frd_parts_sum_cells": len(both), "frd_parts_sum_within_0.1": int((both.abs_diff <= 0.1).sum()),
        "fsr_2020_vintage": inter.iloc[0].to_dict(),
        "pmd_rows": len(pm), "pmd_measures": int(pm.groupby(["measure_type", "event_raw", "measure", "head_raw"]).ngroups),
        "pmd_extrapolated_cells": int(pm.extrapolated.sum()),
        "pmd_events": len(events), "pmd_events_mapped": int(events.vintage_id.notna().sum()),
        "pmd_events_since_june_2010": len(since2010),
        "obr_vintages_without_event": sorted(set(vint[(vint.forecaster == "OBR") & (vint.flags == "")]
                                                .vintage_id) - set(since2010.vintage_id)),
        "pmd_heads": len(heads),
        "pmd_heads_by_confidence": {f"{a}/{b}": int(n) for (a, b), n in
                                    heads.groupby(["measure_type", "confidence"]).size().items()},
    }
    (CHECKS / "summary_frd_pmd.json").write_text(json.dumps(summary, indent=2, default=str))
    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()
