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


def download() -> pd.DataFrame:
    """Fetch every charts-and-tables file; unzip zips. Returns doc rows with local paths."""
    mark_challenged("obr.uk")
    docs = chart_table_documents()
    paths = []
    for _, r in docs.iterrows():
        try:
            p = fetch(r.url, DEST / r.vintage_label.replace(" ", "_"), note=f"EFO tables: {r.title}")
        except FetchError as exc:
            paths.append((r.doc_id, None, str(exc)))
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
    engine = "xlrd" if sniff(path) == "xls" else "openpyxl"
    sheets = pd.read_excel(path, sheet_name=None, header=None, nrows=200, engine=engine)
    return [(name, df.where(pd.notna(df), None).values.tolist()) for name, df in sheets.items()]


def first_text(rows: list[list], n: int = 6) -> str:
    """The first few text cells of a sheet: its table number and title."""
    out = []
    for r in rows[:n]:
        for v in r:
            if isinstance(v, str) and v.strip():
                out.append(v.strip())
    return " | ".join(out)[:300]


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
        for name, data in sheets:
            rows.append({"vintage_label": r.vintage_label, "file": p.relative_to(ROOT).as_posix(),
                         "sheet": name, "title": first_text(data)})
    return pd.DataFrame(rows)
