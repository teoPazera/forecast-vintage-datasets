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
            ("via", "string", "", "direct | wayback | wayback-alternate (same document archived under another URL) | manual (downloaded in a browser)"),
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
    "inventory/manual_checks": {
        "description": "Files downloaded in a browser from the source's own link and compared "
                       "byte for byte with the archive copy used in the pipeline.",
        "columns": [
            ("manual_file", "string", "", "repository-relative path of the browser download (raw/manual/)"),
            ("url", "string", "", "the source's own link it was downloaded from"),
            ("compared_with", "string", "", "repository-relative path of the raw file used in the pipeline"),
            ("downloaded_at", "datetime", "UTC", "file time of the browser download"),
            ("sha256_manual", "string", "", "SHA-256 of the browser download"),
            ("sha256_used", "string", "", "SHA-256 of the file used, as recorded in inventory/sources.csv"),
            ("identical", "boolean", "", "true if the two hashes are equal"),
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
    "tables/series": {
        "description": "One row per forecast series. Partitioned by source: tables/series/<SOURCE>.parquet.",
        "columns": [
            ("source", "string", "", "OBR | CBO"),
            ("series_id", "string", "", "source-prefixed identifier, e.g. obr.vat, obr.psnb_gbp"),
            ("source_code", "string", "", "the source's own code (HOFD sheet name; CBO component/category/subcategory)"),
            ("name", "string", "", "series title as the source writes it"),
            ("parent_series_id", "string", "", "parent in the hierarchy (components add up, with a residual, to the parent)"),
            ("family", "string", "", "pooling family (decision D7)"),
            ("unit", "string", "", "source unit as written"),
            ("unit_harmonized", "string", "", "harmonized unit: 'GBP bn' or 'USD bn' for money; otherwise the source unit"),
            ("kind", "string", "", "level (strictly positive, may be logged) | balance (can change sign, never logged) | rate (per cent)"),
            ("period_type", "string", "", "uk_fiscal_year | us_fiscal_year | calendar_year"),
            ("first_vintage_id", "string", "", "earliest vintage with a value"),
            ("last_vintage_id", "string", "", "latest vintage with a value"),
            ("notes", "string", "", "notes and footnotes carried by the source for this series"),
        ],
    },
    "tables/vintages": {
        "description": "One row per vintage (publication of a full set of forecasts). Partitioned by source.",
        "columns": [
            ("source", "string", "", "OBR | CBO"),
            ("vintage_id", "string", "", "obr_YYYY-MM[_memo], hmt_YYYY-MM, cbo_YYYY-MM"),
            ("label", "string", "", "label as the source writes it"),
            ("publication_date", "date", "", "publication day; last day of the month when month-only (D5)"),
            ("date_certainty", "string", "", "exact | month_only | upper_bound (publication no later than this date) | assumed | unknown"),
            ("date_basis", "string", "", "where the date comes from"),
            ("forecaster", "string", "", "OBR | HM Treasury | CBO"),
            ("flags", "string", "", "semicolon list: memo:<type> (D14), hmt (D11), june2010_budget_assumed, spring, winter, no_season_flag"),
            ("primary_document_id", "string", "", "doc_id of the vintage's main report (inventory/documents)"),
        ],
    },
    "tables/forecasts": {
        "description": "One row per forecast cell (source, series, target period, vintage). Partitioned by source.",
        "columns": [
            ("source", "string", "", "OBR | CBO"),
            ("series_id", "string", "", "see tables/series"),
            ("target_period", "string", "", "'2025-26' (UK fiscal year) or '2025' (US fiscal or calendar year; see series.period_type)"),
            ("vintage_id", "string", "", "see tables/vintages"),
            ("value_source_unit", "float", "series.unit", "value as published"),
            ("value", "float", "series.unit_harmonized", "value in the harmonized unit; same sign convention as the source series"),
            ("cell_role", "string", "", "past (target period ended before publication) | in_progress | future"),
            ("horizon_months", "float", "months", "months from publication date to the end of the target period (negative for past cells); 1 month = 365.25/12 days"),
            ("origin", "string", "", "file, sheet and cell (e.g. HOFD:VAT!C5)"),
        ],
    },
    "tables/outturns": {
        "description": "Realized values per series and target period. Partitioned by source.",
        "columns": [
            ("source", "string", "", "OBR | CBO"),
            ("series_id", "string", "", "see tables/series"),
            ("target_period", "string", "", "see tables/forecasts"),
            ("value_latest", "float", "series.unit_harmonized", "latest outturn as published at retrieval (OBR: 'Outturn data' row, as available at the last forecast)"),
            ("value_first_estimate", "float", "series.unit_harmonized", "first published estimate after the period ended (D4; filled in E4)"),
            ("first_estimate_vintage_id", "string", "", "vintage the first estimate is taken from (E4)"),
            ("origin", "string", "", "file, sheet and cell of value_latest"),
        ],
    },
    "tables/attribution": {
        "description": "The forecaster's own split of each revision into causes. Partitioned by "
                       "source and origin table: tables/attribution/<SOURCE>_<TABLE>.parquet.",
        "columns": [
            ("source", "string", "", "OBR | CBO"),
            ("series_id", "string", "", "series the revision applies to (component or aggregate)"),
            ("target_period", "string", "", "see tables/forecasts"),
            ("vintage_id", "string", "", "the vintage whose revision is attributed"),
            ("previous_vintage_id", "string", "", "the forecast the revision is measured against (may be an intermediate forecast, see vintages/OBR_intermediate)"),
            ("category_raw", "string", "", "label as published, prefixed with its table (e.g. 'FRD:policy/receipts (of which: receipts)')"),
            ("category", "string", "", "harmonized category (D3 default): total | policy | economic_determinants | calibration_to_outturn | classification_one_offs | modelling_other | underlying_unsplit (non-policy total not split by cause) | by_tax_head (a split of the change by tax head, not by cause)"),
            ("value", "float", "series.unit_harmonized", "revision in the series' own convention: positive = the series was revised up (receipts raised, spending raised, borrowing raised)"),
            ("flags", "string", "", "pre_measures_year: revision relative to the pre-measures forecast in a year the previous forecast did not cover (FRD note *)"),
            ("origin", "string", "", "file, sheet and cell"),
        ],
    },
    "crosswalks/pmd_events": {
        "description": "PMD fiscal events -> the vintage published with each event (reviewed by Teo). "
                       "A row with reviewed = true keeps its mapping on reruns.",
        "columns": [
            ("event_raw", "string", "", "event as the PMD writes it"),
            ("vintage_label", "string", "", "HOFD vintage label the event maps to"),
            ("vintage_id", "string", "", "see tables/vintages (derived from vintage_label)"),
            ("rule", "string", "", "how the mapping was made"),
            ("confidence", "string", "", "exact | assumed"),
            ("reviewed", "boolean", "", "true once Teo has checked the row"),
            ("comment", "string", "", "reviewer's comment"),
        ],
    },
    "crosswalks/pmd_heads": {
        "description": "PMD tax and spending heads -> HOFD series (reviewed by Teo). "
                       "A row with reviewed = true keeps its mapping on reruns.",
        "columns": [
            ("measure_type", "string", "", "tax | spending"),
            ("head_raw", "string", "", "head as the PMD writes it"),
            ("hofd_sheet", "string", "", "HOFD sheet the head maps to; empty if the HOFD has no such series"),
            ("series_id", "string", "", "see tables/series (derived from hofd_sheet)"),
            ("aggregate_series_id", "string", "", "the total the head belongs to (receipts or TME)"),
            ("confidence", "string", "", "exact | assumed | none (no HOFD series)"),
            ("note", "string", "", "why an assumed mapping was made"),
            ("n_measures", "integer", "", "number of distinct measures with this head"),
            ("reviewed", "boolean", "", "true once Teo has checked the row"),
            ("comment", "string", "", "reviewer's comment"),
        ],
    },
    "crosswalks/attribution_labels": {
        "description": "Attribution labels -> harmonized categories (D3; reviewed by Teo). EFO rows "
                       "with reviewed = true keep their category on reruns; FRD and CBO rows show "
                       "the D3 mapping set in code.",
        "columns": [
            ("source_table", "string", "", "EFO | FRD | CBO"),
            ("label_key", "string", "", "table kind | section | label, lower case"),
            ("table_kind", "string", "", "tax_drivers | receipts_sources | frd | baseline_changes"),
            ("section", "string", "", "heading the label sits under in its table"),
            ("label", "string", "", "label as published"),
            ("category", "string", "", "harmonized category; see tables/attribution"),
            ("note", "string", "", "why the default category was chosen, or what is uncertain"),
            ("n_rows", "integer", "", "attribution rows (label x target period x vintage) with this label"),
            ("reviewed", "boolean", "", "true once Teo has checked the row"),
            ("comment", "string", "", "reviewer's comment"),
        ],
    },
    "tables/policy_measures": {
        "description": "Costings of individual policy measures (OBR Policy Measures Database). Partitioned by source.",
        "columns": [
            ("source", "string", "", "OBR"),
            ("measure_type", "string", "", "tax | spending"),
            ("event_raw", "string", "", "fiscal event as the PMD writes it"),
            ("vintage_id", "string", "", "vintage the event maps to (crosswalks/pmd_events.csv)"),
            ("measure", "string", "", "measure description"),
            ("head_raw", "string", "", "tax or spending head as the PMD writes it"),
            ("series_id", "string", "", "HOFD series of the head (crosswalks/pmd_heads.csv); empty when the HOFD has no such series"),
            ("target_period", "string", "", "UK fiscal year"),
            ("value_gbp_m", "float", "GBP m", "costing as published: positive = gain to the Exchequer"),
            ("value", "float", "GBP bn", "costing in the affected series' convention: tax gain = receipts up (+), spending gain = spending down (-)"),
            ("extrapolated", "boolean", "", "true if extended beyond the original scorecard period with nominal GDP growth (PMD cell shading)"),
            ("origin", "string", "", "file, sheet and cell"),
        ],
    },
    "tables/cells": {
        "description": "Harmonized cell table (plan E4): every forecast cell with its previous "
                       "vintage, revision, outturns, raw and policy-adjusted errors and flags. "
                       "Partitioned by source.",
        "columns": [
            ("source", "string", "", "OBR | CBO"),
            ("series_id", "string", "", "see tables/series"),
            ("target_period", "string", "", "see tables/forecasts"),
            ("vintage_id", "string", "", "see tables/vintages"),
            ("publication_date", "date", "", "vintage publication date"),
            ("forecaster", "string", "", "OBR | HM Treasury | CBO"),
            ("cell_role", "string", "", "past | in_progress | future"),
            ("horizon_months", "float", "months", "publication date to end of target period"),
            ("value", "float", "series.unit_harmonized", "forecast F_v"),
            ("in_revision_chain", "boolean", "", "false for memo vintages (D14), which are kept but not chained"),
            ("prev_vintage_id", "string", "", "previous vintage in the chain for the same series and target"),
            ("prev_value", "float", "series.unit_harmonized", "F_prev(v)"),
            ("revision", "float", "series.unit_harmonized", "r_v = F_v - F_prev(v); positive = forecast raised"),
            ("log_revision", "float", "log points", "log(F_v / F_prev(v)); level series with both values > 0 only"),
            ("prev_forecaster_differs", "boolean", "", "the previous vintage was made by another forecaster (HM Treasury -> OBR in 2010)"),
            ("outturn_latest", "float", "series.unit_harmonized", "latest outturn (D1 primary)"),
            ("outturn_first", "float", "series.unit_harmonized", "first estimate (D4)"),
            ("error_latest", "float", "series.unit_harmonized", "e = F_v - outturn_latest; positive = over-forecast"),
            ("error_first", "float", "series.unit_harmonized", "F_v - outturn_first"),
            ("log_error_latest", "float", "log points", "log(F_v / outturn_latest); level series only"),
            ("log_error_first", "float", "log points", "log(F_v / outturn_first); level series only"),
            ("policy_effect_after", "float", "series.unit_harmonized", "effect of policy announced after the vintage, in the series convention (CBO: legislative changes; OBR aggregates: FRD policy and classification; OBR components: PMD direct effects); empty when not available"),
            ("policy_adjustment_basis", "string", "", "which source the policy effect comes from"),
            ("value_policy_adjusted", "float", "series.unit_harmonized", "F_v + policy_effect_after"),
            ("error_latest_pa", "float", "series.unit_harmonized", "policy-adjusted error vs latest outturn (CBO's definition)"),
            ("error_first_pa", "float", "series.unit_harmonized", "policy-adjusted error vs first estimate"),
            ("log_error_latest_pa", "float", "log points", "log of policy-adjusted forecast over latest outturn"),
            ("log_error_first_pa", "float", "log points", "log of policy-adjusted forecast over first estimate"),
            ("z", "float", "", "normalized error (E6); empty until E6"),
            ("classification_break", "boolean", "", "trajectory flagged for a classification break (E4 task 4)"),
            ("memo_vintage", "boolean", "", "memo or supplementary vintage (D14)"),
            ("episode", "string", "", "episode window of the target period (D8): gfc | covid | energy | empty"),
            ("origin", "string", "", "file, sheet and cell of the forecast value"),
        ],
    },
    "stats/stylized_facts": {
        "description": "Error moments by forecaster, family, unit of analysis and horizon bucket (E5).",
        "columns": [
            ("group", "string", "", "OBR | HMT | CBO (forecaster)"),
            ("family", "string", "", "series family (D7)"),
            ("unit", "string", "", "'pooled_levels' (log errors of the family's level series) or a series_id (balance/rate series, own unit)"),
            ("episodes", "string", "", "with | without (episode windows, D8)"),
            ("errors", "string", "", "raw | policy_adjusted"),
            ("bucket", "string", "months", "horizon bucket (D6): <0, 0-6, 6-12, 12-24, 24-36, 36+"),
            ("n_cells", "integer", "", "number of forecast cells"),
            ("n_targets", "integer", "", "number of distinct series x target period (clusters)"),
            ("n_series", "integer", "", "number of series"),
            ("mean_error", "float", "log points or series unit", "mean of e = F - A (positive = over-forecast)"),
            ("se_clustered", "float", "as mean_error", "standard error clustered by target"),
            ("p_bias", "float", "", "p-value of mean error = 0"),
            ("sd_error", "float", "as mean_error", "standard deviation of errors"),
            ("mae", "float", "as mean_error", "mean absolute error"),
            ("rmse", "float", "as mean_error", "root mean squared error"),
        ],
    },
    "stats/efficiency_tests": {
        "description": "Numbers-only predictability tests (E5).",
        "columns": [
            ("group", "string", "", "OBR | HMT | CBO"),
            ("family", "string", "", "series family"),
            ("unit", "string", "", "as in stats/stylized_facts"),
            ("episodes", "string", "", "with | without"),
            ("errors", "string", "", "raw | policy_adjusted | empty for revision tests"),
            ("bucket", "string", "months", "horizon bucket, or 'all'"),
            ("test", "string", "", "mincer_zarnowitz | error_on_revision | revision_autocorrelation | same_sign_share | calibration_on_previous_revision"),
            ("n_cells", "integer", "", "observations"),
            ("n_targets", "integer", "", "clusters (series x target period)"),
            ("coef", "float", "", "slope (MZ: forecast; CG: revision; autocorrelation: previous revision); same_sign_share: the share"),
            ("intercept", "float", "", "intercept where applicable"),
            ("se", "float", "", "clustered standard error of coef"),
            ("stat", "float", "", "MZ: Wald statistic; CG: t; autocorrelation: correlation; same_sign: count"),
            ("p_value", "float", "", "p-value of the test named in note"),
            ("note", "string", "", "hypothesis and sign convention"),
        ],
    },
    "stats/attribution_shares": {
        "description": "Share of the absolute revision by harmonized attribution category (E5).",
        "columns": [
            ("group", "string", "", "OBR | HMT | CBO"),
            ("series_id", "string", "", "series"),
            ("family", "string", "", "series family"),
            ("bucket", "string", "months", "horizon bucket"),
            ("category", "string", "", "harmonized category (D3)"),
            ("abs_sum", "float", "series unit", "sum of absolute attributed revisions"),
            ("n", "integer", "", "attribution rows"),
            ("total", "float", "series unit", "sum over categories"),
            ("share_of_abs_revision", "float", "", "abs_sum / total"),
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
