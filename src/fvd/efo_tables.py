"""EFO charts-and-tables workbooks: download and sheet index.

Formats differ over time: one workbook per chapter (2020 onward, also offered as
a zip), a fiscal and an economy workbook (November 2016 to March 2019), a single
workbook before that (.xls up to about 2015). Zips are used only when a vintage
offers no separate workbooks.
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path

import pandas as pd

from .http import FetchError, fetch, mark_challenged, sniff
from .paths import INVENTORY, RAW_DOCS, ROOT

DEST = RAW_DOCS / "obr" / "efo_tables"
_SKIP = re.compile(r"devolved|restated|welsh|scottish|long-term|briefing paper|executive summary",
                   re.IGNORECASE)


def chart_table_documents() -> pd.DataFrame:
    d = pd.read_csv(INVENTORY / "documents.csv")
    e = d[(d.collection == "efo") & (d.doc_type == "forecast_tables")]
    ct = e[e.title.str.contains("chart", case=False) & ~e.title.str.contains(_SKIP)].copy()
    ct["is_zip"] = ct.title.str.contains("zip", case=False)
    keep = []
    for _, g in ct.groupby("vintage_label"):
        files = g[~g.is_zip]
        keep.append(files if len(files) else g)
    return pd.concat(keep)


def _is_chart_workbook(path: Path) -> bool:
    """A charts-and-tables workbook: opens, and has several sheets titled 'Table ...'
    or 'Chart ...' in their first cells."""
    try:
        sheets = workbook_sheets(path)
    except Exception:
        return False
    titled = sum(bool(re.search(r"\b(table|chart)\s+[a-z]?\.?\d+(\.\d+)?", first_text(rows).lower()))
                 for name, rows in sheets)
    return titled >= 5


def _part_key(text: str) -> str:
    """Which part of an EFO a workbook covers: 'chapter 3', 'annex a', 'fiscal',
    'economy', or '' for a single workbook."""
    t = text.lower().replace("_", " ").replace("-", " ")
    t = re.sub(r"economic (and )?fiscal outlook", " ", t)
    m = re.search(r"chapters? (\d+)|annex (?:tables|[a-z]\b)|\b(fiscal|economy)\b", t)
    return re.sub(r"\s+", " ", m.group(0)) if m else ""


def _recover(r) -> Path | None:
    """The source link was never archived: look for the same workbook archived
    under another URL on obr.uk or the OBR's former domains (verified by content)."""
    from .http import fetch_capture
    from .obr_web import spreadsheet_candidates

    month, year = r.vintage_label.split()
    want = _part_key(r.title)
    cands = spreadsheet_candidates(month, int(year), ("chart",),
                                   ("supplementary", "devolved", "welsh", "scottish", "long-term",
                                    "data-sources", "data_sources", "fan", "fiscal-sustainability",
                                    "fsr", "fer", "evaluation", "welfare"))
    # the candidate must be the same part of the EFO (same chapter, annex or half)
    cands = [c for c in cands if _part_key(c["original"].rsplit("/", 1)[-1]) == want]
    for c in cands[:6]:
        try:
            p = fetch_capture(r.url, c["original"], DEST / r.vintage_label.replace(" ", "_"),
                              note=f"EFO tables: {r.title}; source link not archived",
                              verify=_is_chart_workbook)
        except FetchError:
            continue
        if p is not None:
            return p
    return None


def download() -> pd.DataFrame:
    """Fetch every charts-and-tables file; unzip zips. Returns doc rows with local paths."""
    mark_challenged("obr.uk")
    docs = chart_table_documents()
    paths = []
    for _, r in docs.iterrows():
        try:
            p = fetch(r.url, DEST / r.vintage_label.replace(" ", "_"), note=f"EFO tables: {r.title}")
        except FetchError as exc:
            p = _recover(r)
            if p is None:
                paths.append((r.doc_id, None, str(exc)))
                continue
            paths.append((r.doc_id, p, "alternate capture"))
            continue
        if sniff(p) == "zip":   # a real archive, not an .xlsx (which is also a zip)
            out = p.with_suffix("")
            if not out.exists():
                with zipfile.ZipFile(p) as z:
                    z.extractall(out)
            for f in sorted(out.rglob("*.xls*")):
                paths.append((r.doc_id, f, "from zip"))
        else:
            paths.append((r.doc_id, p, ""))
    loc = pd.DataFrame(paths, columns=["doc_id", "path", "status"])
    return docs.merge(loc, on="doc_id", how="right")


def workbook_sheets(path: Path) -> list[tuple[str, list[list]]]:
    """(sheet name, first 200 rows as lists) for .xlsx and .xls files."""
    import io

    engine = "xlrd" if sniff(path) == "xls" else "openpyxl"
    # read from bytes: openpyxl refuses paths without a spreadsheet extension
    sheets = pd.read_excel(io.BytesIO(path.read_bytes()), sheet_name=None, header=None,
                           nrows=200, engine=engine)
    return [(name, df.where(pd.notna(df), None).values.tolist()) for name, df in sheets.items()]


def first_text(rows: list[list], n: int = 6) -> str:
    """The first few text cells of a sheet: its table number and title."""
    out = []
    for r in rows[:n]:
        for v in r:
            if isinstance(v, str) and v.strip():
                out.append(v.strip())
    return " | ".join(out)[:300]


_NUMBERED = re.compile(r"^\s*(table|chart)\s+([a-z]?\d+\.\d+)\b", re.IGNORECASE)


def contents_titles(sheets: list[tuple[str, list[list]]]) -> dict[str, str]:
    """Sheet code ('t4.9', 'c2.1') -> 'Table 4.9: ...' from a Contents sheet.

    Some early workbooks (March 2011) name their sheets by code and give the
    titles only on the Contents sheet.
    """
    out = {}
    for name, data in sheets:
        if name.strip().lower() not in ("contents", "index"):
            continue
        for row in data:
            for v in row:
                m = _NUMBERED.match(v) if isinstance(v, str) else None
                if m:
                    out.setdefault(f"{m.group(1)[0].lower()}{m.group(2).lower()}", v.strip())
    return out


def sheet_index(located: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, r in located.dropna(subset=["path"]).iterrows():
        p = Path(r.path)
        try:
            sheets = workbook_sheets(p)
        except Exception as exc:   # corrupt or unsupported file: record and move on
            rows.append({"vintage_label": r.vintage_label, "file": p.relative_to(ROOT).as_posix(),
                         "sheet": None, "title": f"ERROR {type(exc).__name__}: {exc}"[:200]})
            continue
        codes = contents_titles(sheets)
        for name, data in sheets:
            title = first_text(data)
            code = re.sub(r"\s+", "", name).lower()
            if code in codes and not _NUMBERED.match(title):
                title = f"{codes[code]} | {title}"[:300]
            rows.append({"vintage_label": r.vintage_label, "file": p.relative_to(ROOT).as_posix(),
                         "sheet": name, "title": title})
    return pd.DataFrame(rows)
