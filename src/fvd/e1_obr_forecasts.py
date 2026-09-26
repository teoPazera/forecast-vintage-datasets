"""Stage E1: OBR forecasts and outturns from the Historical Official Forecasts Database.

Run:  python -m fvd.e1_obr_forecasts

Writes (OBR partitions; E3 adds CBO):
  tables/series/OBR.parquet     tables/vintages/OBR.parquet
  tables/forecasts/OBR.parquet  tables/outturns/OBR.parquet
  stats/e1_checks/*.csv         cross-checks, hierarchy residuals, per-sheet counts
"""

from __future__ import annotations

import json
from datetime import date

import openpyxl
import pandas as pd

from . import obr_series as S
from .hofd import series_sheets, vintage_rows
from .http import fetch, mark_challenged
from .paths import INVENTORY, RAW_DOCS, ROOT, STATS, TABLES
from .periods import add_role_and_horizon, normalize_uk_fiscal
from .schemas import check_columns, write_schema

HOFD = ROOT / "raw/obr/Historical_official_forecasts_database_Spring_2026.xlsx"
CHECKS = STATS / "e1_checks"

# Memo vintages have no landing page date (E0 open question 3). Default: the
# earlier of the first Wayback capture and the Last-Modified date of the OBR's own
# download for that forecast; both are upper bounds on publication, so the date is
# conservative for leakage. The restated March 2024 forecast (PSNFL only) has no
# download and is dated to the first EFO that used PSNFL as a target, October 2024.
# All three are flagged.
MEMO_SOURCES = {
    "obr_2019-03_restated": "https://obr.uk/download/restated-march-2019-forecast/",
    "obr_2020-03_supplementary": "https://obr.uk/download/supplementary-forecast-march-2020/",
}
MEMO_ASSUMED = {"obr_2024-03_restated": ("2024-10-30", "assumed: first published with the "
                                         "October 2024 EFO (PSNFL target); no separate download")}


# --- vintages -------------------------------------------------------------------

def _memo_date(url: str) -> tuple[str, str]:
    from email.utils import parsedate_to_datetime

    from .http import load_sources, wayback_captures
    mark_challenged("obr.uk")
    path = fetch(url, RAW_DOCS / "obr", note="memo vintage document")
    rel = path.relative_to(ROOT).as_posix()
    lm = load_sources()[rel]["last_modified"]
    bounds = {}
    if lm:
        bounds["Last-Modified"] = parsedate_to_datetime(lm).date()
    caps = wayback_captures(url.split("://")[1].rstrip("/"), match="prefix",
                            filter="statuscode:[23]..")
    if caps:
        first = min(c["timestamp"] for c in caps)
        bounds["first Wayback capture"] = date(int(first[:4]), int(first[4:6]), int(first[6:8]))
    which, d = min(bounds.items(), key=lambda kv: kv[1])
    return d.isoformat(), f"upper bound: {which} of {url} " + \
        "; ".join(f"{k} {v}" for k, v in bounds.items())


def build_vintages() -> pd.DataFrame:
    cal = pd.read_csv(INVENTORY / "vintage_calendar.csv")
    v = cal[cal.source == "OBR"].copy()
    for vid, url in MEMO_SOURCES.items():
        d, basis = _memo_date(url)
        v.loc[v.vintage_id == vid, ["publication_date", "date_certainty", "date_basis"]] = \
            [d, "upper_bound", basis]
    for vid, (d, basis) in MEMO_ASSUMED.items():
        v.loc[v.vintage_id == vid, ["publication_date", "date_certainty", "date_basis"]] = \
            [d, "assumed", basis]
    v["flags"] = v["flags"].fillna("")
    return v[["source", "vintage_id", "label", "publication_date", "date_certainty", "date_basis",
              "forecaster", "flags", "primary_document_id"]].reset_index(drop=True)


# --- sheet parsing --------------------------------------------------------------

def _num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _period(v) -> tuple[str, str] | None:
    fy = normalize_uk_fiscal(v)
    if fy:
        return fy, "uk_fiscal_year"
    if isinstance(v, (int, float)) and 1900 < v < 2100 and float(v).is_integer():
        return str(int(v)), "calendar_year"
    if isinstance(v, str) and v.strip().isdigit() and len(v.strip()) == 4:
        return v.strip(), "calendar_year"
    return None


def _cell(sheet: str, row0: int, col0: int) -> str:
    return f"HOFD:{sheet}!{openpyxl.utils.get_column_letter(col0 + 1)}{row0 + 1}"


def parse_sheet(sheet: str, rows: list[tuple]) -> dict:
    hdr = next(i for i, r in enumerate(rows) if r and r[0] == "Back to contents")
    periods = {j: _period(v) for j, v in enumerate(rows[hdr]) if j > 0 and _period(v)}
    ptypes = {pt for _, pt in periods.values()}
    if len(ptypes) != 1:
        raise ValueError(f"{sheet}: mixed or missing period types {ptypes}")
    labels = [(i, lab) for i, lab in vintage_rows(rows) if i > hdr]
    out_row = next((i for i, r in enumerate(rows)
                    if i > hdr and r and isinstance(r[0], str) and r[0].strip().startswith("Outturn data")),
                   None)
    cells, skipped = [], []
    for i, lab in labels:
        for j, (tp, _) in periods.items():
            v = rows[i][j] if j < len(rows[i]) else None
            if _num(v) is None:
                if v not in (None, "") and not (isinstance(v, str) and not v.strip()):
                    skipped.append({"sheet": sheet, "cell": _cell(sheet, i, j), "raw": repr(v)})
                continue
            cells.append({"label": lab.vintage_label, "target_period": tp, "value_source_unit": float(v),
                          "origin": _cell(sheet, i, j)})
    outturns = []
    if out_row is not None:
        for j, (tp, _) in periods.items():
            v = rows[out_row][j] if j < len(rows[out_row]) else None
            if _num(v) is not None:
                outturns.append({"target_period": tp, "value_latest": float(v),
                                  "origin": _cell(sheet, out_row, j)})
    notes = [str(rows[r][1]).strip() for r in (1, 2) if len(rows[r]) > 1 and isinstance(rows[r][1], str)]
    after = out_row if out_row is not None else hdr
    notes += [str(r[0]).strip() for r in rows[after + 1:]
              if r and isinstance(r[0], str) and not r[0].startswith("Memo")]
    title = rows[0][1] if len(rows[0]) > 1 and isinstance(rows[0][1], str) else rows[0][0]
    return {"sheet": sheet, "title": str(title).strip(), "unit": str(rows[1][0] or "").strip(),
            "period_type": ptypes.pop(), "labels": labels, "cells": cells, "outturns": outturns,
            "non_numeric_cells": skipped, "notes": " | ".join(n for n in notes if n)}


# --- checks ---------------------------------------------------------------------

def cross_check_chart_copies(wb, parsed: dict[str, dict]) -> pd.DataFrame:
    """Compare each '(2)' chart-data sheet with its unsuffixed sheet on common cells."""
    out = []
    for name in wb.sheetnames:
        if not name.endswith(" (2)"):
            continue
        base = name[:-4]
        if base not in parsed:
            continue
        copy = parse_sheet(name, list(wb[name].iter_rows(values_only=True)))
        a = pd.DataFrame(parsed[base]["cells"]).set_index(["label", "target_period"]).value_source_unit
        b = pd.DataFrame(copy["cells"]).set_index(["label", "target_period"]).value_source_unit
        # A target period that appears twice in a header (a typo in the source) is not compared.
        for dup in sorted(set(b.index[b.index.duplicated()].get_level_values(1))):
            out.append({"sheet": base, "vintage_label": "", "target_period": dup, "value": None,
                        "chart_copy_value": None, "abs_diff": None,
                        "note": "period appears twice in the chart copy's header; not compared"})
        a = a[~a.index.duplicated(keep=False)]
        b = b[~b.index.duplicated(keep=False)]
        common = a.index.intersection(b.index)
        diff = (a[common] - b[common]).abs()
        for (lab, tp), d in diff.items():
            out.append({"sheet": base, "vintage_label": lab, "target_period": tp,
                        "value": a[(lab, tp)], "chart_copy_value": b[(lab, tp)], "abs_diff": d,
                        "note": ""})
    return pd.DataFrame(out)


def hierarchy_residuals(fc: pd.DataFrame, sheet_of: dict[str, str]) -> pd.DataFrame:
    """Parent minus the sum of listed children, per vintage and target period.

    Memo vintages are left out: they appear on a few sheets only, so most
    children are missing and the residual says nothing about the hierarchy.
    """
    fc = fc[~fc.vintage_id.str.contains("_restated|_supplementary")]
    by_sheet = fc.assign(sheet=fc.series_id.map(sheet_of))
    piv = by_sheet.pivot_table(index=["vintage_id", "target_period"], columns="sheet",
                               values="value", aggfunc="first")
    rows = []
    for parent, children in S.HIERARCHY.items():
        if parent not in piv:
            continue
        kids = [c for c in children if c in piv]
        sub = piv[[parent] + kids].dropna(subset=[parent])
        n_kids = sub[kids].notna().sum(axis=1)
        sub = sub[n_kids > 0]
        total = sub[kids].sum(axis=1, min_count=1)
        for (vid, tp), p in sub[parent].items():
            rows.append({"parent": parent, "vintage_id": vid, "target_period": tp, "parent_value": p,
                         "children_sum": total[(vid, tp)], "n_children": int(n_kids[(vid, tp)]),
                         "residual": p - total[(vid, tp)]})
    return pd.DataFrame(rows)


def residual_jumps(res: pd.DataFrame, vint: pd.DataFrame) -> pd.DataFrame:
    """Changes in the residual between consecutive vintages (same parent and target)
    larger than 1% of the parent value."""
    order = vint.set_index("vintage_id").publication_date
    r = res.assign(pub=res.vintage_id.map(order)).sort_values(["parent", "target_period", "pub"])
    r["residual_change"] = r.groupby(["parent", "target_period"]).residual.diff()
    r["prev_vintage_id"] = r.groupby(["parent", "target_period"]).vintage_id.shift()
    r["share_of_parent"] = (r.residual_change / r.parent_value).abs()
    return r[r.share_of_parent > 0.01].drop(columns="pub")


# --- main -----------------------------------------------------------------------

def main() -> None:
    wb = openpyxl.load_workbook(HOFD, read_only=True, data_only=True)
    names = wb.sheetnames
    economy = set(names[names.index("Economy") + 1:])
    vint = build_vintages()
    label_to_vid = dict(zip(vint.label, vint.vintage_id))

    parsed = {s: parse_sheet(s, list(wb[s].iter_rows(values_only=True))) for s in series_sheets(names)}

    series, fc_rows, out_rows, counts = [], [], [], []
    for s, p in parsed.items():
        sid = S.series_id(s)
        fam = S.ECONOMY_FAMILY if s in economy else S.SHEET_FAMILY.get(s)
        if fam is None:
            raise KeyError(f"no family for sheet {s}")
        for c in p["cells"]:
            fc_rows.append({"series_id": sid, "vintage_id": label_to_vid[c["label"]],
                            "period_type": p["period_type"], **c})
        for o in p["outturns"]:
            out_rows.append({"series_id": sid, **o})
        vids = sorted({label_to_vid[c["label"]] for c in p["cells"]},
                      key=lambda v: vint.set_index("vintage_id").publication_date.get(v) or "")
        series.append({
            "source": "OBR", "series_id": sid, "source_code": s, "name": p["title"],
            "parent_series_id": S.series_id(S.PARENT[s]) if s in S.PARENT else None,
            "family": fam, "unit": p["unit"], "unit_harmonized": S.harmonized_unit(p["unit"]),
            "kind": S.kind(s, p["unit"]), "period_type": p["period_type"],
            "first_vintage_id": vids[0] if vids else None, "last_vintage_id": vids[-1] if vids else None,
            "notes": p["notes"],
        })
        with_values = {c["label"] for c in p["cells"]}
        counts.append({"sheet": s, "series_id": sid, "label_rows": len(p["labels"]),
                       "label_rows_with_values": len(with_values),
                       "vintages_parsed": len({label_to_vid[l] for l in with_values}),
                       "cells": len(p["cells"]), "outturns": len(p["outturns"]),
                       "non_numeric_cells": len(p["non_numeric_cells"])})

    series = pd.DataFrame(series)
    fc = pd.DataFrame(fc_rows)
    fc["source"] = "OBR"
    fc = fc.merge(vint[["vintage_id", "publication_date"]], on="vintage_id", how="left")
    fc = add_role_and_horizon(fc)
    fc["value"] = fc.value_source_unit   # £ billion is already the harmonized unit
    fc = fc[["source", "series_id", "target_period", "vintage_id", "value_source_unit", "value",
             "cell_role", "horizon_months", "origin"]]
    dups = fc.duplicated(["series_id", "target_period", "vintage_id"]).sum()
    if dups:
        raise ValueError(f"{dups} duplicate forecast cells")

    out = pd.DataFrame(out_rows)
    out["source"] = "OBR"
    out["value_first_estimate"] = float("nan")   # reconstructed in E4 (D4)
    out["first_estimate_vintage_id"] = None
    out = out[["source", "series_id", "target_period", "value_latest", "value_first_estimate",
               "first_estimate_vintage_id", "origin"]]

    # checks
    CHECKS.mkdir(parents=True, exist_ok=True)
    cnt = pd.DataFrame(counts)
    cnt.to_csv(CHECKS / "sheet_counts.csv", index=False)
    pd.DataFrame([c for p in parsed.values() for c in p["non_numeric_cells"]]) \
        .to_csv(CHECKS / "non_numeric_cells.csv", index=False)
    xc = cross_check_chart_copies(wb, parsed)
    xc.to_csv(CHECKS / "chart_copy_crosscheck.csv", index=False)
    sheet_of = dict(zip(series.series_id, series.source_code))
    res = hierarchy_residuals(fc.assign(value=fc.value), sheet_of)
    res.to_csv(CHECKS / "hierarchy_residuals.csv", index=False)
    jumps = residual_jumps(res, vint)
    jumps.to_csv(CHECKS / "hierarchy_residual_jumps.csv", index=False)

    # write tables
    for name, df in [("series", series), ("vintages", vint), ("forecasts", fc), ("outturns", out)]:
        check_columns(f"tables/{name}", df)
        (TABLES / name).mkdir(parents=True, exist_ok=True)
        df.to_parquet(TABLES / name / "OBR.parquet", index=False)
        write_schema(f"tables/{name}", ROOT)

    res_summary = (res.assign(share=(res.residual / res.parent_value).abs())
                   .groupby("parent").share.describe()[["count", "50%", "max"]])
    summary = {
        "sheets": len(parsed), "series": len(series), "vintages": len(vint),
        "forecast_cells": len(fc), "outturn_cells": len(out),
        "cells_by_role": fc.cell_role.value_counts(dropna=False).to_dict(),
        "cells_by_forecaster": fc.merge(vint, on="vintage_id").forecaster.value_counts().to_dict(),
        "sheets_label_count_mismatch": cnt[cnt.label_rows_with_values != cnt.vintages_parsed].sheet.tolist(),
        "non_numeric_cells": int(cnt.non_numeric_cells.sum()),
        "chart_copy_cells_compared": len(xc),
        "chart_copy_cells_over_0.05": int((xc.abs_diff > 0.05).sum()) if len(xc) else 0,
        "chart_copy_share_within_0.05": round(float((xc.abs_diff <= 0.05).mean()), 4) if len(xc) else None,
        "residual_share_of_parent": res_summary.round(4).to_dict("index"),
        "residual_jumps_over_1pct": len(jumps),
        "residual_jumps_by_parent": jumps.groupby("parent").size().to_dict(),
    }
    (CHECKS / "summary.json").write_text(json.dumps(summary, indent=2, default=str))
    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()
