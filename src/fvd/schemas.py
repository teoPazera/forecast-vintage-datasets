"""Schema definitions for every derived table, written next to each table.

Each column entry: (name, type, unit, description). Unit is "" for
non-numeric columns. Sign conventions are stated in the description.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml

SCHEMAS: dict[str, dict] = {
    "inventory/sources": {
        "description": "Provenance of every raw file and every refused or failed request.",
        "columns": [
            ("path", "string", "", "repository-relative path of the stored raw file; empty for failed requests"),
            ("url", "string", "", "the source's own URL for the file (obr.uk cache-buster query removed)"),
            ("via", "string", "", "direct | wayback | wayback-alternate (same document archived under another URL)"),
            ("fetched_url", "string", "", "URL actually requested (Wayback URL when via is not direct)"),
            ("capture_time", "datetime", "UTC", "Wayback capture time"),
            ("retrieved_at", "datetime", "UTC", "time of our download"),
            ("sha256", "string", "", "SHA-256 of the stored bytes"),
            ("bytes", "integer", "bytes", "size of the stored file"),
            ("last_modified", "string", "", "Last-Modified header of the original server (from the archive when archived)"),
            ("content_type", "string", "", "MIME type served"),
            ("status", "integer", "", "HTTP status; 200 for stored files"),
            ("note", "string", "", "free text: capture counts, alternate URL, refusal reason"),
        ],
    },
    "inventory/documents": {
        "description": "Every inventoried document (forecast narratives and tables, in-period "
                       "commentary, post-hoc evaluations, other forecaster text).",
        "columns": [
            ("doc_id", "string", "", "stable id: source prefix + SHA-1 of the URL"),
            ("source", "string", "", "OBR | CBO"),
            ("collection", "string", "", "efo | fer | psf_commentary | cbo_beo | cbo_apb | cbo_mbr | cbo_accuracy | cbo_evaluation | cbo_testimony"),
            ("doc_type", "string", "", "forecast_narrative | forecast_tables | in_period_commentary | post_hoc_evaluation | other"),
            ("title", "string", "", "title as listed by the source"),
            ("url", "string", "", "the source's own link to the document"),
            ("landing_url", "string", "", "page the document was listed on"),
            ("publication_date", "date", "", "exact date, or the last day of the month when only the month is known (D5); empty if unknown"),
            ("date_certainty", "string", "", "exact | month_only | unknown"),
            ("date_basis", "string", "", "where the date comes from"),
            ("related_date", "date", "", "not used for documents (see vintage_calendar)"),
            ("vintage_label", "string", "", "OBR vintage label ('Month YYYY') for EFO documents"),
            ("primary", "boolean", "", "true for the main report of an EFO, FER or CBO outlook"),
            ("notes", "string", "", "availability of the main report; data month of commentaries"),
        ],
    },
    "inventory/vintage_calendar": {
        "description": "Every forecast vintage with its publication date.",
        "columns": [
            ("source", "string", "", "OBR | CBO"),
            ("vintage_id", "string", "", "obr_YYYY-MM[_memo], hmt_YYYY-MM or cbo_YYYY-MM"),
            ("label", "string", "", "label as the source writes it (normalized 'Month YYYY'; memo type in brackets)"),
            ("forecaster", "string", "", "OBR | HM Treasury | CBO"),
            ("publication_date", "date", "", "exact, or last day of the month when month-only (D5)"),
            ("date_certainty", "string", "", "exact | month_only | unknown"),
            ("date_basis", "string", "", "where the date comes from"),
            ("landing_url", "string", "", "OBR EFO landing page"),
            ("primary_document_id", "string", "", "doc_id of the vintage's main report in inventory/documents"),
            ("flags", "string", "", "semicolon list: memo:<type>, hmt, june2010_budget_assumed, spring, winter, no_season_flag"),
            ("n_sheets", "integer", "sheets", "OBR: number of HOFD sheets carrying the vintage"),
            ("notes", "string", "", "free text"),
            ("components", "string", "", "CBO: components present in baselines.csv"),
            ("n_candidates", "integer", "documents", "CBO: listed outlook or budget-analysis reports in the baseline month"),
            ("related_date", "date", "", "CBO month-only vintages: earliest dated CBO statement or testimony on the outlook in that month (candidate proxy date, not used)"),
            ("document_url", "string", "", "CBO: URL of the matched report"),
        ],
    },
    "inventory/hofd_vintage_labels": {
        "description": "Every vintage row label found in the unsuffixed HOFD series sheets.",
        "columns": [
            ("sheet", "string", "", "HOFD sheet name"),
            ("row", "integer", "", "1-based Excel row"),
            ("raw", "string", "", "cell value as written"),
            ("label", "string", "", "normalized 'Month YYYY'"),
            ("kind", "string", "", "regular | memo"),
            ("memo_type", "string", "", "restated | supplementary for memo rows"),
            ("vintage_label", "string", "", "label plus memo type"),
            ("footnote", "string", "", "footnote marker stripped, '[year corrected]' or '[date cell]'"),
        ],
    },
    "inventory/e0_fact_checks": {
        "description": "Checks of the plan's section 5 source facts against the downloaded files.",
        "columns": [
            ("claim_id", "string", "", "H* HOFD, F* FRD, P* PMD, C* CBO"),
            ("section", "string", "", "plan section"),
            ("claim", "string", "", "the plan's statement"),
            ("status", "string", "", "confirmed | partly | discrepancy | deferred"),
            ("finding", "string", "", "what the file shows"),
            ("evidence", "string", "", "file, sheet, row or column"),
        ],
    },
}


def write_schema(table: str, root: Path) -> Path:
    spec = SCHEMAS[table]
    out = {"table": table, "description": spec["description"],
           "columns": [{"name": n, "type": t, "unit": u, "description": d}
                       for n, t, u, d in spec["columns"]]}
    path = root / f"{table}.schema.yaml"
    path.write_text(yaml.safe_dump(out, sort_keys=False, allow_unicode=True, width=100),
                    encoding="utf-8")
    return path


def check_columns(table: str, df: pd.DataFrame) -> None:
    want = [c[0] for c in SCHEMAS[table]["columns"]]
    missing, extra = set(want) - set(df.columns), set(df.columns) - set(want)
    if missing or extra:
        raise ValueError(f"{table}: columns differ from schema; missing {missing}, extra {extra}")
