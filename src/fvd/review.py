"""Review workbook for Teo: the crosswalk rows that matter, and the open decisions.

    python -m fvd.review build   # writes review/review.xlsx
    python -m fvd.review apply   # writes the answers back into crosswalks/*.csv

Only rows that can change a result are listed. Attribution labels are ranked by
how much of the attributed revision they carry; labels whose default category
is uncertain are always listed. Every row in a sheet counts as reviewed when
the sheet is applied: an empty answer means the current mapping is right.
The workbook itself is not committed; the answers live in the crosswalk files
(`reviewed`, `comment`).
"""

from __future__ import annotations

import sys

import pandas as pd
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

from . import crosswalks as X
from .e2_efo_tables import driver_rows
from .paths import CROSSWALKS, ROOT, STATS, TABLES

OUT = ROOT / "review" / "review.xlsx"
COVER = 0.80   # list labels until they cover this share of the attributed revision

CATEGORIES = {
    "policy": "effect of government decisions (direct or indirect)",
    "economic_determinants": "changes to the economy forecast: earnings, employment, consumption, "
                             "prices, profits, asset prices, interest rates",
    "calibration_to_outturn": "new outturn or receipts data since the previous forecast",
    "classification_one_offs": "statistical classification changes and one-off items",
    "modelling_other": "modelling changes, judgement, other and residual items",
    "underlying_unsplit": "the whole non-policy change, not split by cause",
    "by_tax_head": "a split of the change by tax, not by cause",
}

INPUT = PatternFill("solid", fgColor="FFF2CC")
HEAD = PatternFill("solid", fgColor="D9E1F2")

START = [
    ("What this is", ""),
    ("", "Three crosswalks translate the OBR's own wording into the dataset's common terms. "
         "If one is wrong, a number lands in the wrong place: a policy effect counted as an "
         "economy revision, a tax measure applied to the wrong tax, a Budget matched to the "
         "wrong forecast. The review is a sense check by an economist, not a data check: I "
         "have already checked the numbers add up."),
    ("", "Only rows that can change a result are listed. Everything else is in crosswalks/*.csv."),
    ("How to fill it in", ""),
    ("", "Yellow columns are yours. Leave 'your answer' EMPTY if the current mapping is right. "
         "If it is wrong, pick the right one from the dropdown. Use 'comment' for anything "
         "unsure; a comment without a changed answer is fine."),
    ("", "Save the file and tell Claude which sheets are done. Every row of a finished sheet is "
         "then marked reviewed, and your answers stay fixed on every rerun."),
    ("Sheets (about 30-45 minutes in all)", ""),
    ("Labels", "OBR driver labels -> cause categories. Question for each row: reading this label in "
               "the OBR's table, which cause is it? Watch for: data or outturn labels filed under "
               "modelling ('Latest receipts', 'Receipts data' are probably calibration_to_outturn); "
               "economy labels filed under modelling; labels that mix two causes (pick the larger, "
               "write a comment). One row per wording: your answer applies wherever the wording "
               "appears. Sorted by weight, so the first rows matter most. The listed rows carry 85% "
               "of all attributed revision; each unlisted label is small."),
    ("Heads", "PMD tax/spending heads -> HOFD sheet. Question: does the head cover the same thing as "
              "the sheet? Watch for heads broader or narrower than the sheet (e.g. 'Stamp duty' "
              "covers property and shares; the HOFD splits them). A policy costing is only "
              "subtracted from a series if its head maps to that series."),
    ("Events", "PMD fiscal events -> the OBR forecast published with them. Question: is this the "
               "forecast of that event? Mostly a quick confirm. The 52 pre-2010 events are not "
               "listed: component forecasts start in June 2010, so they change nothing."),
    ("Decisions", "The open choices that must be fixed before case selection (E6) is pre-registered. "
                  "Each has my recommendation; answer 'agree' or 'change' and say how in the comment."),
    ("Categories", ""),
    *[(k, v) for k, v in CATEGORIES.items()],
]

DECISIONS = [
    ("E5 check", "Do the headline results look plausible to you?",
     "E5 note, section 3 table. Signs: error = forecast - outturn, so negative = the forecast was "
     "too low. E.g. OBR receipts and spending totals were ~5% too low at 1-2 years; the CBO "
     "deficit came out ~$210bn larger than projected; income-tax revisions tend to continue in "
     "the same direction (60% same sign), consumption and capital-tax revisions tend to reverse. "
     "Anything that contradicts what you know may be a sign or unit error.",
     "If nothing looks off: agree."),
    ("D2", "Case selection uses policy-adjusted errors (not raw)?",
     "Adjusted = the effect of policies announced after the forecast is removed, since the "
     "forecaster could not know them. Limits: OBR components lose only direct effects (PMD "
     "has no indirect effects); OBR aggregate classification changes can be removed only "
     "up to October 2021.",
     "Agree: policy-adjusted, raw kept for robustness."),
    ("D1", "Errors against the latest outturn (not the first estimate)?",
     "Latest = as published today; first estimate = first published after the year ended. "
     "Latest is what the forecaster aimed at in the long run but includes later revisions "
     "and classification changes.",
     "Agree: latest primary, first estimate as robustness."),
    ("D8 thresholds", "z* = 1.5, z_low = 0.5, K = 15 cases and M = 30 random trajectories per source?",
     "A case is a run of at least 2 forecasts of the same target that were all off in the same "
     "direction by more than 1.5 typical errors. Controls stayed within 0.5 typical errors. "
     "These cannot be tuned after seeing the selection.",
     "Agree with the plan defaults."),
    ("D8 episodes", "Episode windows (GFC, COVID, energy) tagged but not excluded, max 3 cases each?",
     "Without the cap, COVID-era errors would dominate the case list.",
     "Agree."),
    ("Scope", "Case selection only on OBR (not HM Treasury) vintages, excluding economy series "
              "and trajectories with classification breaks (D11, D12, D13)?",
     "HM Treasury forecasts have no matching OBR text; economy series are calendar-year context; "
     "classification breaks are measurement changes, not forecast errors.",
     "Agree."),
    ("Pooling", "Pool level series in log errors and keep balances (PSNB, deficit) separate in "
                "their own units?",
     "Logs make taxes of different size comparable. Balances change sign, so no logs.",
     "Agree."),
    ("Key tests", "Pre-specify these as the numbers-only baseline for the thesis: same-sign share "
                  "of consecutive revisions and the error-on-revision coefficient, by family, at "
                  "12-24 months?",
     "E5 ran 2,750 tests; with that many, some are significant by chance. Naming the few that "
     "matter in advance avoids that.",
     "Agree."),
    ("D5", "CBO baselines dated only to the month: use the last day of the month (plan default) "
           "or the date of CBO's testimony on the outlook that month (known for 34 of 64)?",
     "Matters only for which documents count as available before a CBO forecast (leakage rule). "
     "Month-end is conservative; the testimony date is more precise but a proxy.",
     "Month-end, testimony date kept as a column."),
    ("D3 FRD", "Keep the OBR revisions database's 'underlying' as one unsplit category, or split it "
               "using the EFO receipts tables where they exist?",
     "Splitting gives economy / calibration / modelling for receipts only, and only where the "
     "EFO table exists; spending stays unsplit.",
     "Keep unsplit; the EFO tables already give the split per tax."),
    ("CBO revenue", "CBO revenue changes are split into economic/technical only from 2024 "
                    "(legislative only before). Exclude CBO revenue from attribution-share "
                    "results, keep it for errors and cases?",
     "Otherwise the policy share for CBO revenue is overstated.",
     "Agree: exclude from attribution shares only."),
]


def _label_sheet() -> pd.DataFrame:
    """One row per label wording and current category, over all sections it appears in."""
    rows = driver_rows(pd.read_parquet(STATS / "e2_checks" / "efo_table_rows.parquet"))
    cw = pd.read_csv(CROSSWALKS / "attribution_labels.csv", dtype=str, keep_default_na=False)
    cw = cw[cw.source_table == "EFO"].set_index("label_key")
    rows["abs"] = rows.value.abs()
    w = rows.groupby("label_key").agg(weight=("abs", "sum")).join(cw)
    # a recent example of each label, for context
    ex = rows.sort_values("vintage_label", key=lambda s: pd.to_datetime("1 " + s)) \
        .groupby("label_key").last()
    w["example"] = ex.title + " (" + ex.vintage_label + ", " + ex.table + ")"
    w = w[w.category != "by_tax_head"].sort_values("weight", ascending=False).reset_index()
    w["wording"] = w.label.str.lower().str.strip()
    kinds = {"tax_drivers": "per-tax", "receipts_sources": "total receipts"}
    g = w.groupby(["wording", "category"], sort=False).agg(
        label=("label", "first"), weight=("weight", "sum"), example=("example", "first"),
        keys=("label_key", " || ".join),
        sections=("section", lambda s: "; ".join(dict.fromkeys(x or "(none)" for x in s))),
        table=("table_kind", lambda s: ", ".join(dict.fromkeys(kinds[x] for x in s))),
        note=("note", lambda s: next((x for x in s if x), ""))).reset_index()
    g["share"] = g.weight / g.weight.sum()
    g = g.sort_values("share", ascending=False)
    big = g.share.cumsum().shift(fill_value=0) < COVER
    flag = g.note.str.contains("no keyword|mixes|neutral|not split", case=False) & (g.share >= 0.001)
    g["why"] = [("large" if b else "") + ("; " if b and f else "") + (n if f else "")
                for b, f, n in zip(big, flag, g.note)]
    return g[big | flag]


def _head_sheet() -> pd.DataFrame:
    h = pd.read_csv(CROSSWALKS / "pmd_heads.csv", dtype=str, keep_default_na=False)
    h["n_measures"] = h.n_measures.astype(int)
    pm = pd.read_parquet(TABLES / "policy_measures" / "OBR.parquet")
    pm = pm[pm.vintage_id.fillna("").str.startswith("obr_")]
    top = (pm.assign(a=pm.value.abs()).groupby(["measure_type", "head_raw", "measure"]).a.sum()
           .reset_index().sort_values("a", ascending=False)
           .groupby(["measure_type", "head_raw"]).measure.apply(lambda s: " | ".join(s.head(3))))
    h = h.join(top.rename("examples"), on=["measure_type", "head_raw"])
    keep = (h.confidence == "assumed") | ((h.confidence == "none") & (h.n_measures >= 10))
    h = h[keep].sort_values(["confidence", "n_measures"], ascending=[True, False])
    h["why"] = h.confidence.map({"assumed": "assumed mapping: " , "none": "no HOFD sheet; many measures"}) \
        + h.note.where(h.confidence == "assumed", "")
    return h


def _event_sheet() -> pd.DataFrame:
    e = pd.read_csv(CROSSWALKS / "pmd_events.csv", dtype=str, keep_default_na=False)
    v = pd.read_parquet(TABLES / "vintages" / "OBR.parquet")
    e = e[e.vintage_id.str.startswith("obr_") | (e.confidence == "exact")]
    pub = dict(zip(v.vintage_id, v.publication_date.astype(str)))
    e["published"] = e.vintage_id.map(pub)
    return e


def _sheet(wb, title, frame, cols, answer, options=None, widths=None):
    ws = wb.create_sheet(title)
    heads = [c[0] for c in cols] + [answer, "comment", "key"]
    ws.append(heads)
    for _, r in frame.iterrows():
        ws.append([r[c[1]] for c in cols] + ["", "", r["_key"]])
    for c in ws[1]:
        c.font, c.fill = Font(bold=True), HEAD
    n = len(frame) + 1
    a_col, c_col = len(cols) + 1, len(cols) + 2
    for row in ws.iter_rows(min_row=2, max_row=n):
        for c in row:
            c.alignment = Alignment(wrap_text=True, vertical="top")
        row[a_col - 1].fill = row[c_col - 1].fill = INPUT
    if options is not None:
        dv = DataValidation(type="list", formula1=options, allow_blank=True)
        ws.add_data_validation(dv)
        L = ws.cell(1, a_col).column_letter
        dv.add(f"{L}2:{L}{n}")
    for i, wdt in enumerate((widths or [20] * len(cols)) + [24, 40, 10], start=1):
        ws.column_dimensions[ws.cell(1, i).column_letter].width = wdt
    ws.column_dimensions[ws.cell(1, len(heads)).column_letter].hidden = True
    ws.freeze_panes = "A2"
    return ws


def build() -> None:
    OUT.parent.mkdir(exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.title = "Start"
    for a, b in START:
        ws.append([a, b])
        ws.cell(ws.max_row, 1).font = Font(bold=not b)
        ws.cell(ws.max_row, 2).alignment = Alignment(wrap_text=True, vertical="top")
    ws.column_dimensions["A"].width, ws.column_dimensions["B"].width = 24, 110

    lists = wb.create_sheet("lists")
    series = pd.read_parquet(TABLES / "series" / "OBR.parquet")
    sheets = ["(none)"] + sorted(series.source_code.dropna().unique())
    vint = pd.read_parquet(TABLES / "vintages" / "OBR.parquet")
    labels = vint[vint.forecaster == "OBR"].sort_values("publication_date").label.tolist()
    for i, col in enumerate([list(CATEGORIES), sheets, labels, ["agree", "change"]], start=1):
        for j, v in enumerate(col, start=1):
            lists.cell(j, i, v)
    lists.sheet_state = "hidden"

    lab = _label_sheet().assign(_key=lambda d: d["keys"], pct=lambda d: (100 * d.share).round(1))
    lab.insert(0, "rank", range(1, len(lab) + 1))
    _sheet(wb, "Labels", lab,
           [("#", "rank"), ("why listed", "why"), ("tables", "table"), ("example table", "example"),
            ("section headings", "sections"), ("label", "label"), ("% of attributed revision", "pct"),
            ("current category", "category")],
           "your category", f"lists!$A$1:$A${len(CATEGORIES)}",
           [5, 22, 14, 44, 28, 36, 11, 20])

    hd = _head_sheet().assign(_key=lambda d: d.measure_type + "|" + d.head_raw)
    _sheet(wb, "Heads", hd,
           [("why listed", "why"), ("type", "measure_type"), ("PMD head", "head_raw"),
            ("measures", "n_measures"), ("largest measures (examples)", "examples"),
            ("current HOFD sheet", "hofd_sheet")],
           "your HOFD sheet", f"lists!$B$1:$B${len(sheets)}", [30, 9, 26, 9, 60, 16])

    ev = _event_sheet().assign(_key=lambda d: d.event_raw)
    _sheet(wb, "Events", ev,
           [("PMD event", "event_raw"), ("current forecast", "vintage_label"),
            ("forecast published", "published")],
           "your forecast", f"lists!$C$1:$C${len(labels)}", [26, 18, 18])

    dec = pd.DataFrame(DECISIONS, columns=["topic", "question", "context", "recommendation"])
    dec["_key"] = dec.topic
    _sheet(wb, "Decisions", dec,
           [("topic", "topic"), ("question", "question"), ("what it means", "context"),
            ("my recommendation", "recommendation")],
           "your answer", "lists!$D$1:$D$2", [14, 40, 70, 30])

    wb.move_sheet("lists", offset=len(wb.sheetnames))
    wb.save(OUT)
    print(f"{OUT.relative_to(ROOT)}: {len(lab)} labels, {len(hd)} heads, {len(ev)} events, "
          f"{len(dec)} decisions")


def _answers(ws) -> pd.DataFrame:
    rows = list(ws.values)
    return pd.DataFrame(rows[1:], columns=rows[0], dtype=object)


def _text(v) -> str:
    return "" if v is None or (isinstance(v, float) and pd.isna(v)) else str(v).strip()


def apply(sheets: list[str]) -> None:
    wb = load_workbook(OUT, data_only=True)
    plan = {"Labels": ("attribution_labels", "your category", "category",
                       lambda d, k: (d.source_table == "EFO") & d.label_key.isin(k.split(" || "))),
            "Heads": ("pmd_heads", "your HOFD sheet", "hofd_sheet",
                      lambda d, k: (d.measure_type + "|" + d.head_raw) == k),
            "Events": ("pmd_events", "your forecast", "vintage_label",
                       lambda d, k: d.event_raw == k)}
    for sheet in sheets:
        if sheet == "Decisions":
            print(_answers(wb["Decisions"])[["key", "your answer", "comment"]].to_string(index=False))
            continue
        name, answer, field, match = plan[sheet]
        p = CROSSWALKS / f"{name}.csv"
        d = pd.read_csv(p, dtype=str, keep_default_na=False)
        changed = 0
        for _, a in _answers(wb[sheet]).iterrows():
            m = match(d, a["key"])
            new = _text(a[answer])
            if new:
                d.loc[m, field] = "" if new == "(none)" else new
                changed += int(m.sum())
            d.loc[m, "reviewed"] = "True"
            if _text(a["comment"]):
                d.loc[m, "comment"] = _text(a["comment"])
        d.to_csv(p, index=False)
        print(f"{sheet}: {len(_answers(wb[sheet]))} rows marked reviewed, {changed} changed -> {p.name}")


if __name__ == "__main__":
    if sys.argv[1:2] == ["apply"]:
        apply(sys.argv[2:] or ["Labels", "Heads", "Events", "Decisions"])
    else:
        build()
