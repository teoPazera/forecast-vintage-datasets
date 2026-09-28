"""Stage E2, part 2: receipts attribution tables in the EFO charts-and-tables workbooks.

Run:  python -m fvd.e2_efo_tables   (after fvd.efo_tables has downloaded the workbooks)

Three kinds of table are located by title in every vintage:
  receipts_sources   sources of change to total receipts (by type: underlying
                     economy / outturn / modelling, policy, PSNB-neutral ...)
  receipts_by_head   change to current receipts by tax head
  tax_drivers        per-tax tables: key changes to VAT, onshore CT, income tax
                     and NICs, SA income tax, CGT, property transaction taxes ...

Every numeric row is kept with its raw label (stats/e2_checks/efo_table_rows.parquet).
Driver rows become attribution (tables/attribution/OBR_EFO.parquet) with the raw
label and a harmonized category from crosswalks/attribution_labels.csv (D3).

Checks (plan E2):
  - current-forecast rows vs the HOFD value of the same vintage (0.05 + 0.5%)
  - previous-forecast rows vs the HOFD value of the previous vintage
  - driver rows add up to the stated change (0.1 x number of rows)
"""

from __future__ import annotations

import calendar
import json
import re
from pathlib import Path

import pandas as pd

from . import crosswalks as X
from .efo_tables import contents_titles, workbook_sheets
from .paths import CROSSWALKS, ROOT, STATS, TABLES
from .periods import normalize_uk_fiscal
from .schemas import check_columns, write_schema

CHECKS = STATS / "e2_checks"
MONTHS = "|".join(calendar.month_name[1:])

# --- table classification -----------------------------------------------------------------

_TITLE = re.compile(r"^\s*Table\s+([A-Z0-9]+(?:\.[A-Z0-9]+)?)\s*:\s*(.+)$", re.IGNORECASE | re.DOTALL)
_SINCE = re.compile(rf"since\s+(?:the\s+)?((?:{MONTHS})(?:\s+\d{{4}})?)(?:\s+(?:and|&)\s+((?:{MONTHS})(?:\s+\d{{4}})?))?",
                    re.IGNORECASE)

TAX_TABLES = [  # (pattern on the table subject, series_id, note)
    (r"^(?:the\s+)?non-sa income tax,? (?:and )?nics(?:,? and health and social care levy)?$", "obr.nonsa_it_nics", "derived: IT - SA IT + NICs (+ HSC 2021-22)"),
    (r"^(?:the\s+)?(?:paye income tax and nics)$", "obr.nonsa_it_nics", "derived: IT - SA IT + NICs"),
    (r"^(?:the\s+)?(?:income tax and nics|it and nics)$", "obr.it_nics", "derived: IT + NICs"),
    (r"^(?:the\s+)?non-sa income tax$", "obr.nonsa_it", "derived: IT - SA IT"),
    (r"^(?:the\s+)?nics$", "obr.nics", ""),
    (r"^(?:the\s+)?sa income tax$", "obr.sa_it", ""),
    (r"^(?:the\s+)?vat$", "obr.vat", ""),
    (r"^(?:the\s+)?(?:onshore )?corporation tax$", "obr.onshore", ""),
    (r"^(?:the\s+)?capital gains tax$", "obr.cgt", ""),
    (r"^(?:the\s+)?(?:property transactions? taxes|stamp duty land tax)$", "obr.ptt", ""),
    (r"^(?:the\s+)?fuel duties$", "obr.fuel", ""),
]
# Tables about combined or differently defined taxes are checked against sums of
# HOFD series: non-SA income tax = income tax - SA income tax.
DERIVED = {"obr.nonsa_it_nics": [("obr.it", 1), ("obr.sa_it", -1), ("obr.nics", 1), ("obr.hsc", 1)],
           "obr.nonsa_it": [("obr.it", 1), ("obr.sa_it", -1)],
           "obr.it_nics": [("obr.it", 1), ("obr.nics", 1)]}


def classify(title: str) -> tuple[str, str, str]:
    """(kind, series_id, subject) for a table title, kind '' if not a receipts table."""
    t = re.sub(r"\s+", " ", title).strip()
    low = t.lower()
    if "since" not in low:
        return "", "", ""
    if re.search(r"sources of (change|difference) to the receipts|changes to the receipts forecast|"
                 r"breakdown of changes to the underlying receipts|receipts forecast: changes since|"
                 r"^(public sector )?receipts( \(excluding [^)]*\))?: changes since", low):
        return "receipts_sources", "obr.pscr_gbp", "receipts"
    if re.search(r"changes? to current receipts since|^current receipts: changes? since", low):
        return "receipts_by_head", "obr.pscr_gbp", "current receipts"
    m = re.match(r"^key changes to (.+?)(?: forecast| receipts| revenues)? since", low) or \
        re.match(r"^(.+?): changes since", low)
    if m:
        subject = m.group(1).strip()
        for pat, sid, _ in TAX_TABLES:
            if re.match(pat, subject):
                return "tax_drivers", sid, subject
        return "other_tax", "", subject
    return "", "", ""


# --- generic table reader --------------------------------------------------------------------

def _clean_label(s) -> str:
    if not isinstance(s, str):
        return ""
    s = re.sub(r"\s+", " ", s).strip()
    return re.sub(r"(?<=[A-Za-z\)])\d{1,2}$", "", s).strip()   # trailing footnote number


def read_table(rows: list[list]) -> tuple[str, list[dict]]:
    """Title and numeric rows of one sheet. Each row: label, sublabel, section,
    {target_period: value}. The label columns are those left of the first year
    column; a second label column holds 'of which' sub-items."""
    title = ""
    for r in rows[:6]:
        for v in r:
            if isinstance(v, str) and _TITLE.match(v.strip()):
                title = v.strip()
                break
        if title:
            break
    hdr_i, years = None, {}
    for i, r in enumerate(rows[:15]):
        ys = {j: normalize_uk_fiscal(v) for j, v in enumerate(r) if normalize_uk_fiscal(v)}
        if len(ys) >= 3:
            hdr_i, years = i, ys
            break
    if hdr_i is None:
        return title, []
    first_year_col = min(years)
    out, section = [], ""
    for i, r in enumerate(rows[hdr_i + 1:], start=hdr_i + 1):
        labels = [_clean_label(v) for v in r[:first_year_col]]
        texts = [x for x in labels if x]
        vals = {tp: float(r[j]) for j, tp in years.items()
                if j < len(r) and isinstance(r[j], (int, float)) and not pd.isna(r[j])}
        in_year_text = [v for j, v in enumerate(r) if j >= first_year_col and isinstance(v, str) and v.strip()]
        if not vals:
            if texts and texts[0].lower().startswith("of which") and out:
                out[-1]["group_header"] = True   # the row above has children
            elif in_year_text:
                section = _clean_label(in_year_text[0])
            elif texts and not texts[0].lower().startswith(("of which", "source", "note")) \
                    and not re.match(r"^\d", texts[0]):
                section = texts[0]
            continue
        label = texts[0] if texts else ""
        sub = ""
        if len(texts) > 1 or (label.lower().startswith("of which") and len(labels) > 1):
            label, sub = (texts[0], texts[-1]) if len(texts) > 1 else ("", labels[-1])
        if label.lower().startswith("of which") or not label:
            label, sub = "", sub or label
        out.append({"row": i, "label": label, "sublabel": sub, "section": section, "values": vals,
                    "group_header": False})
    return title, out


# --- row roles and categories ------------------------------------------------------------------

def row_role(label: str, sub: str, vintage_label: str) -> tuple[str, str]:
    """(role, forecast label) where role is level | change | subtotal | memo | component."""
    t = (sub or label).lower().strip()
    if not t:
        return "unlabelled", ""
    m = re.match(rf"^({MONTHS.lower()})(?: (\d{{4}}))? forecast(?: restated)?$", t)
    if m:
        return ("level", m.group(0).replace(" restated", "")) if "restated" not in t else ("adjustment", "")
    if t.startswith("memo"):
        return "memo", ""
    if re.match(r"^(change|difference|like-for-like change)\b", t):
        return "change", ""   # the drivers below explain the like-for-like change
    if re.match(r"^accounting treatment change", t):
        return "adjustment", ""
    if re.match(r"^(total|underlying forecast changes$|by tax head$)", t):
        return "subtotal", ""
    return "component", ""


def resolve_forecast_label(text: str, vintage_label: str, vint_labels: list[str]) -> str | None:
    """'November forecast' in a March 2026 table -> 'November 2025'; 'March 2020 forecast'
    -> 'March 2020'. A bare month is the latest vintage with that month not after this one."""
    m = re.match(rf"^({MONTHS.lower()})(?: (\d{{4}}))?", text.lower())
    if not m:
        return None
    month = m.group(1).capitalize()
    if m.group(2):
        return f"{month} {m.group(2)}"
    this = pd.Timestamp(f"1 {vintage_label}")
    cands = [l for l in vint_labels if l.startswith(month + " ") and pd.Timestamp(f"1 {l}") <= this]
    return max(cands, key=lambda l: pd.Timestamp(f"1 {l}")) if cands else None


def load_label_crosswalk() -> dict[str, dict]:
    """EFO rows of crosswalks/attribution_labels.csv by label key (reviewed or not)."""
    return {k[1]: r for k, r in X.previous_rows("attribution_labels", ["source_table", "label_key"]).items()
            if k[0] == "EFO"}


def default_category(label: str, section: str, table_kind: str) -> tuple[str, str]:
    """Default D3 category for an EFO driver label, by keyword. Written once from the
    label vocabulary, before any outcome is looked at (plan 8.6); reviewed by Teo."""
    lab = label.lower()
    # 'By tax head' and 'By policy and forecast differences' head alternative splits of
    # the same change: the heading names the split, not the cause of each row.
    if section.lower().startswith("by tax head"):
        return "by_tax_head", "split by tax head, not by cause"
    if section.lower().startswith("by "):
        section = ""
    if re.match(r"^underlying (obr )?forecast (differences|changes)\b", lab):
        return "underlying_unsplit", "the non-policy total, not split by cause in this block"
    t = f"{section} | {label}".lower()
    if re.search(r"government decisions|policy|measures|scorecard|sr20|budget|statement", t) and \
            not re.search(r"pre-measures", lab):
        return "policy", ""
    if re.search(r"classification|one-off|psnb.neutral", lab):
        return ("classification_one_offs" if "classification" in lab or "one-off" in lab
                else "modelling_other"), "PSNB-neutral items are pass-throughs, not forecast errors" if "neutral" in lab else ""
    if re.search(r"calibration|outturn", lab):
        mixed = re.search(r"modelling|other|economic", lab)
        return "calibration_to_outturn", "label mixes outturn with modelling or other" if mixed else ""
    if re.search(r"earnings|employ|consum|household|spending|profit|price|equit|interest rate|inflation|"
                 r"economic|economy|income and expenditure|market|property|investment|production|"
                 r"wages|gdp|oil and gas|house|nominal|incomes|labour|pay\b|real", lab):
        return "economic_determinants", ""
    if re.search(r"modelling|other|judgement|error|gap|litigation|exempt|re-allocation|reallocation|"
                 r"incorporation|timing|receipts$|assumption|base|share", lab):
        return "modelling_other", ""
    return "modelling_other", "no keyword matched; default"


# --- main ------------------------------------------------------------------------------------

def collect(located: pd.DataFrame, vint_labels: list[str]) -> pd.DataFrame:
    recs = []
    for _, f in located.dropna(subset=["path"]).iterrows():
        p = Path(f.path)
        try:
            sheets = workbook_sheets(p)
        except Exception:
            continue
        codes = contents_titles(sheets)
        for sheet, rows in sheets:
            title, trows = read_table(rows)
            # early workbooks title their sheets only on the Contents sheet ('t4.9')
            title = title or codes.get(re.sub(r"\s+", "", sheet).lower(), "")
            m = _TITLE.match(title) if title else None
            if not m:
                continue
            kind, sid, subject = classify(m.group(2))
            if not kind:
                continue
            since = _SINCE.search(m.group(2))
            prev = [resolve_forecast_label(s, f.vintage_label, vint_labels) for s in (since.groups() if since else []) if s]
            # Each change row governs the driver rows below it, up to the next change
            # row ('Change since March 2020' ... 'Change since October 2021' ...).
            block, block_prev = None, (prev[0] if prev else None)
            for tr in trows:
                role, flab = row_role(tr["label"], tr["sublabel"], f.vintage_label)
                if role == "change":
                    block = tr["row"]
                    ms = _SINCE.search(f"{tr['label']} {tr['sublabel']}")
                    if ms:
                        block_prev = resolve_forecast_label(ms.group(1), f.vintage_label, vint_labels)
                for tp, v in tr["values"].items():
                    recs.append({"vintage_label": f.vintage_label, "file": p.relative_to(ROOT).as_posix(),
                                 "sheet": sheet, "table": "T" + m.group(1).replace(" ", ""),
                                 "title": m.group(2).strip(),
                                 "kind": kind, "series_id": sid, "subject": subject,
                                 "previous_labels": ";".join(x for x in prev if x),
                                 "block": block, "block_previous": block_prev,
                                 "group_header": tr["group_header"],
                                 "row": tr["row"], "label": tr["label"], "sublabel": tr["sublabel"],
                                 "section": tr["section"], "role": role,
                                 "forecast_label": resolve_forecast_label(flab, f.vintage_label, vint_labels) if flab else None,
                                 "target_period": tp, "value": v})
    return pd.DataFrame(recs)


def hofd_values(series_id: str) -> pd.Series:
    fc = pd.read_parquet(TABLES / "forecasts" / "OBR.parquet")
    fc = fc.set_index(["series_id", "vintage_id", "target_period"]).value
    if series_id in DERIVED:
        parts = [sign * fc.xs(s, level="series_id") for s, sign in DERIVED[series_id]
                 if s in fc.index.get_level_values(0)]
        both = pd.concat(parts, axis=1)
        # the first two terms must be present; later ones (e.g. HSC) only where they exist
        return both.sum(axis=1, min_count=1).where(both.iloc[:, :2].notna().all(axis=1))
    return fc.xs(series_id, level="series_id") if series_id in fc.index.get_level_values(0) else pd.Series(dtype=float)


def level_checks(rows: pd.DataFrame, lab2vid: dict) -> pd.DataFrame:
    lv = rows[(rows.role == "level") & (rows.series_id != "") & rows.forecast_label.notna()].copy()
    out = []
    cache = {}
    for _, r in lv.iterrows():
        if r.series_id not in cache:
            cache[r.series_id] = hofd_values(r.series_id)
        h = cache[r.series_id]
        vid = lab2vid.get(r.forecast_label)
        hv = h.get((vid, r.target_period)) if vid is not None else None
        which = "current" if r.forecast_label == r.vintage_label else "previous"
        out.append({"vintage_label": r.vintage_label, "table": r.table, "series_id": r.series_id,
                    "forecast_label": r.forecast_label, "which": which, "target_period": r.target_period,
                    "efo_value": r.value, "hofd_value": hv,
                    "abs_diff": abs(r.value - hv) if hv is not None and not pd.isna(hv) else None,
                    "tolerance": 0.05 + 0.005 * abs(r.value)})
    return pd.DataFrame(out)


def sum_checks(rows: pd.DataFrame) -> pd.DataFrame:
    """Driver rows add up to the stated change (plan: within 0.1 x number of rows).

    Three layouts occur:
    - sections with a subtotal row: each section's rows sum to its subtotal, and the
      subtotals sum to the change;
    - sections titled 'By ...': alternative decompositions, each sums to the change;
    - otherwise ('(by economic determinant)', '(by other category)', ...) all rows
      of the table together sum to the change.
    Nested groups ('of which') are detected where a row equals the sum of the rows
    that follow it; their children are not counted twice.
    """
    out = []
    drv = rows[rows.kind.isin(["tax_drivers", "receipts_sources"]) & rows.block.notna()]

    def add(v, t, tp, what, part, target):
        top = _top_level(part)
        method = "marked groups"
        if abs(sum(top) - target) > 0.1 * len(top) + 1e-9:
            # Some tables indent sub-items by formatting only, which the values do
            # not carry; retry with groups inferred from sums, and say so.
            alt = _top_level(part, infer=True)
            if abs(sum(alt) - target) <= 0.1 * len(alt) + 1e-9:
                top, method = alt, "inferred groups"
        out.append({"vintage_label": v, "table": t, "target_period": tp, "check": what,
                    "n_rows": len(top), "stated_total": target, "sum_rows": sum(top),
                    "abs_diff": abs(sum(top) - target), "tolerance": 0.1 * len(top) + 1e-9,
                    "nesting": method})

    for (v, t, tp, blk), g in drv.groupby(["vintage_label", "table", "target_period", "block"]):
        g = g.sort_values("row")
        ch = g[(g.role == "change") & (g.row == blk)]
        change = float(ch.value.iloc[0]) if len(ch) else None
        comps = g[g.role == "component"]
        subs = g[g.role == "subtotal"]
        secs_all = g.section.fillna("")
        if len(subs):
            for sec, s in g.groupby(secs_all, sort=False):
                c, st = s[s.role == "component"], s[s.role == "subtotal"]
                if len(st) and len(c) >= 1:
                    add(v, t, tp, f"section '{sec}' vs its total", c, float(st.value.iloc[0]))
            if change is not None:
                loose = comps[~comps.section.fillna("").isin(set(subs.section.fillna("")))]
                add(v, t, tp, "section totals vs change", pd.concat([subs, loose]).sort_values("row"), change)
        elif change is not None and len(comps) >= 2:
            secs = list(dict.fromkeys(comps.section.fillna("")))
            if len(secs) > 1 and all(s.lower().startswith("by ") for s in secs):
                for sec in secs:
                    add(v, t, tp, f"decomposition '{sec}' vs change",
                        comps[comps.section.fillna("") == sec], change)
            else:
                add(v, t, tp, "all rows vs change", comps, change)
    return pd.DataFrame(out)


def _top_level(part: pd.DataFrame, tol: float = 0.051, infer: bool = False) -> list[float]:
    """Values of the top-level rows, children of groups removed.

    Groups are marked in the table itself: a row followed by an 'of which:' line
    (group_header), or indented rows in the second label column (label empty,
    sublabel set). A header's children are the shortest run of following rows
    that adds up to it; if no run does, nothing is removed. With infer=True every
    row may head a group (used only as a fallback, and reported as such).
    """
    part = part.sort_values("row")
    vals = part.value.tolist()
    hdr = [True] * len(vals) if infer else part.group_header.fillna(False).astype(bool).tolist()
    indented = ((part.label.fillna("") == "") & (part.sublabel.fillna("") != "")).tolist()
    top, i = [], 0
    while i < len(vals):
        if indented[i]:          # child of the labelled row above it
            i += 1
            continue
        top.append(vals[i])
        if hdr[i]:
            for k in range(2, len(vals) - i):
                if abs(sum(vals[i + 1:i + 1 + k]) - vals[i]) <= tol * k:
                    i += k
                    break
        i += 1
    return top


def driver_rows(rows: pd.DataFrame) -> pd.DataFrame:
    """Rows of efo_table_rows that become attribution, with their crosswalk key."""
    drv = rows[rows.kind.isin(["tax_drivers", "receipts_sources"]) & (rows.role == "component")
               & rows.block.notna()].copy()
    drv["text"] = drv.sublabel.where(drv.sublabel.fillna("") != "", drv.label)
    drv["section"] = drv.section.where(drv.section.map(lambda s: isinstance(s, str)), "")
    drv["label_key"] = drv.kind + "|" + drv.section.str.lower() + "|" + drv.text.str.lower()
    return drv


def attribution_rows(rows: pd.DataFrame, lab2vid: dict, cw: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    drv = driver_rows(rows)
    labels = []
    out = []
    for _, r in drv.iterrows():
        text, section, key = r.text, r.section, r.label_key
        old = cw.get(key, {})
        done = X.is_true(old.get("reviewed", ""))
        cat, note = (old["category"], old["note"]) if done else default_category(text, section, r.kind)
        labels.append({"source_table": "EFO", "label_key": key, "table_kind": r.kind, "section": section,
                       "label": text, "category": cat, "note": note, "reviewed": done,
                       "comment": old.get("comment", ""), **X.llm_fields(old)})
        prev = r.block_previous if isinstance(r.block_previous, str) else None
        out.append({"source": "OBR", "series_id": r.series_id, "target_period": r.target_period,
                    "vintage_id": lab2vid.get(r.vintage_label), "previous_vintage_id": lab2vid.get(prev),
                    "category_raw": f"EFO {r.table}: {section + ' / ' if section else ''}{text}",
                    "category": cat, "value": r.value,
                    "flags": "not_previous_vintage" if prev and lab2vid.get(prev) and
                             ";" in (r.previous_labels or "") else "",
                    "origin": f"{r.file}#{r.sheet}!row{r.row + 1}"})
    lab = pd.DataFrame(labels).drop_duplicates("label_key")
    lab["n_rows"] = lab.label_key.map(pd.Series([l["label_key"] for l in labels]).value_counts())
    lab = lab[["source_table", "label_key", "table_kind", "section", "label", "category", "note",
               "n_rows", "reviewed", "comment", *X.LLM_COLS]]
    return pd.DataFrame(out), lab


def derived_series() -> pd.DataFrame:
    """Series that EFO driver tables report but the HOFD does not hold as a sheet.
    They carry attribution only; their levels are sums of HOFD series."""
    names = {"obr.it_nics": "Income tax and NICs (derived: IT + NICs)",
             "obr.nonsa_it": "Non-SA income tax (derived: IT - SA IT)",
             "obr.nonsa_it_nics": "Non-SA income tax and NICs (derived: IT - SA IT + NICs, + HSC 2021-22)"}
    return pd.DataFrame([{
        "source": "OBR", "series_id": sid, "source_code": "derived", "name": name,
        "parent_series_id": "obr.pscr_gbp", "family": "income_taxes", "unit": "£ billion",
        "unit_harmonized": "GBP bn", "kind": "level", "period_type": "uk_fiscal_year",
        "first_vintage_id": None, "last_vintage_id": None,
        "notes": "derived for EFO attribution tables: " + " ".join(
            f"{'+' if s > 0 else '-'} {c}" for c, s in DERIVED[sid])} for sid, name in names.items()])


def policy_vs_pmd(att: pd.DataFrame) -> pd.DataFrame:
    """EFO 'direct effect of Government decisions' rows vs the PMD costings of the
    same event for the same tax (plan E4 task 2 cross-check)."""
    pm = pd.read_parquet(TABLES / "policy_measures" / "OBR.parquet")
    pm = pm.groupby(["series_id", "vintage_id", "target_period"]).value.sum()
    e = att[(att.category == "policy") & att.category_raw.str.contains(r"direct effect|scorecard", case=False)
            & ~att.category_raw.str.contains("indirect|non-scorecard|up to and including", case=False)]
    rows = []
    for _, r in e.iterrows():
        p = pm.get((r.series_id, r.vintage_id, r.target_period))
        if p is None:
            continue
        rows.append({"series_id": r.series_id, "vintage_id": r.vintage_id, "target_period": r.target_period,
                     "efo_direct_effect": r.value, "pmd_sum": p, "abs_diff": abs(r.value - p),
                     "category_raw": r.category_raw})
    return pd.DataFrame(rows)


def main() -> None:
    CHECKS.mkdir(parents=True, exist_ok=True)
    from .efo_tables import download
    located = download()   # cached after the first run
    located.assign(path=located.path.map(lambda p: Path(p).relative_to(ROOT).as_posix() if isinstance(p, Path) else p)) \
        [["vintage_label", "doc_id", "title", "url", "path", "status"]].to_csv(CHECKS / "efo_workbooks.csv", index=False)
    vint = pd.concat([pd.read_parquet(TABLES / "vintages" / "OBR.parquet"),
                      pd.read_parquet(TABLES / "vintages" / "OBR_intermediate.parquet")])
    reg = vint[vint.forecaster == "OBR"]
    lab2vid = dict(zip(reg.label, reg.vintage_id))
    rows = collect(located, list(reg[~reg["flags"].str.contains("memo|intermediate")].label))
    rows.to_parquet(CHECKS / "efo_table_rows.parquet", index=False)   # every parsed row, for review

    lc = level_checks(rows, lab2vid)
    lc.to_csv(CHECKS / "efo_vs_hofd_levels.csv", index=False)
    sc = sum_checks(rows)
    sc.to_csv(CHECKS / "efo_driver_sums.csv", index=False)

    att, lab = attribution_rows(rows, lab2vid, load_label_crosswalk())
    check_columns("tables/attribution", att)
    att.to_parquet(TABLES / "attribution" / "OBR_EFO.parquet", index=False)
    ds = derived_series()
    check_columns("tables/series", ds)
    ds.to_parquet(TABLES / "series" / "OBR_derived.parquet", index=False)
    pp = policy_vs_pmd(att)
    pp.to_csv(CHECKS / "efo_direct_effects_vs_pmd.csv", index=False)

    # attribution label crosswalk: FRD, CBO and EFO labels in one reviewed file. FRD
    # and CBO categories are the D3 mapping in code (crosswalks.FRD_PATHS, e3_cbo.D3);
    # their rows keep Teo's review flag and comment.
    old = X.previous_rows("attribution_labels", ["source_table", "label_key"])

    def kept(src, k):
        o = old.get((src, k), {})
        return {"reviewed": X.is_true(o.get("reviewed", "")), "comment": o.get("comment", ""),
                **dict.fromkeys(X.LLM_COLS, ""), "status": "fixed_in_code"}

    frd = pd.DataFrame([{"source_table": "FRD", "label_key": k, "table_kind": "frd", "section": "",
                         "label": k, "category": v[0], "note": v[1], "n_rows": None, **kept("FRD", k)}
                        for k, v in X.FRD_PATHS.items()])
    cbo = pd.DataFrame([{"source_table": "CBO", "label_key": k, "table_kind": "baseline_changes", "section": "",
                         "label": k, "category": v, "note": "D3 default", "n_rows": None, **kept("CBO", k)}
                        for k, v in {"Legislative": "policy", "Economic": "economic_determinants",
                                     "Technical": "modelling_other"}.items()])
    labels = pd.concat([frd, cbo, lab])
    check_columns("crosswalks/attribution_labels", labels)
    labels.to_csv(CROSSWALKS / "attribution_labels.csv", index=False)
    write_schema("crosswalks/attribution_labels", ROOT)

    coverage = (rows[rows.kind.isin(["tax_drivers", "receipts_sources", "receipts_by_head"])]
                .groupby(["vintage_label", "kind", "subject"]).table.first().unstack(["kind", "subject"]))
    coverage.to_csv(CHECKS / "efo_table_coverage.csv")
    lc_ok = lc.dropna(subset=["abs_diff"])
    summary = {
        "vintages_with_tables": int(rows.vintage_label.nunique()),
        "tables_by_kind": rows.groupby("kind").apply(lambda d: d[["vintage_label", "table"]].drop_duplicates().shape[0]).to_dict(),
        "tax_driver_tables_by_series": rows[rows.kind == "tax_drivers"].groupby("series_id")
            .apply(lambda d: d.vintage_label.nunique()).to_dict(),
        "level_cells_matched": len(lc_ok),
        "level_cells_pass": int((lc_ok.abs_diff <= lc_ok.tolerance).sum()),
        "level_share_pass": round(float((lc_ok.abs_diff <= lc_ok.tolerance).mean()), 4) if len(lc_ok) else None,
        "level_share_pass_by_which": lc_ok.assign(ok=lc_ok.abs_diff <= lc_ok.tolerance).groupby("which").ok.mean().round(4).to_dict(),
        "level_cells_unmatched": int(lc.abs_diff.isna().sum()),
        "sum_checks": len(sc), "sum_checks_pass": int((sc.abs_diff <= sc.tolerance).sum()),
        "sum_share_pass": round(float((sc.abs_diff <= sc.tolerance).mean()), 4) if len(sc) else None,
        "sum_checks_pass_with_marked_groups_only": int(((sc.abs_diff <= sc.tolerance) & (sc.nesting == "marked groups")).sum()),
        "efo_direct_effect_vs_pmd_cells": len(pp),
        "efo_direct_effect_vs_pmd_within_0.1": int((pp.abs_diff <= 0.1).sum()) if len(pp) else 0,
        "efo_direct_effect_vs_pmd_median_abs_diff": float(pp.abs_diff.median()) if len(pp) else None,
        "attribution_rows": len(att), "attribution_labels": len(lab),
        "attribution_labels_by_category": lab.category.value_counts().to_dict(),
    }
    (CHECKS / "summary_efo_tables.json").write_text(json.dumps(summary, indent=2, default=str))
    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()
