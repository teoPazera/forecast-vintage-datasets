"""Crosswalks reviewed by Teo (plan E2): PMD events -> vintages, PMD heads -> HOFD
series, attribution labels -> harmonized categories (D3).

The mappings below are defaults written before any outcome is looked at
(plan section 8, rule 6). `confidence` says how sure the mapping is:
exact (same concept, same name), assumed (same concept, needs checking) or
none (no HOFD series; the measure counts only towards the aggregate).

Each crosswalk file has `reviewed` and `comment` columns. A row marked
reviewed keeps its mapping on every rerun; other rows are rebuilt from the
rules here. Comments are kept either way.
"""

from __future__ import annotations

import calendar
import re

import pandas as pd

from .paths import CROSSWALKS


# Model-assisted labelling (crosswalks/codebook.md; plan D20, D21): written by
# fvd.jev_route, kept on every rerun. status: settled_agreement | pending |
# reviewed | fixed_in_code; empty until routed.
LLM_COLS = ["status", "labeller", "jev_choice", "jev_p1", "jev_second", "jev_p2", "jev_confidence",
            "route_reason"]


def llm_fields(old: dict) -> dict:
    return {c: old.get(c, "") for c in LLM_COLS}


def is_true(v) -> bool:
    return str(v).strip().lower() in ("true", "1", "yes", "y", "x")


def previous_rows(name: str, key: list[str]) -> dict[tuple, dict]:
    """Rows of crosswalks/<name>.csv as last written or edited, keyed by `key`."""
    p = CROSSWALKS / f"{name}.csv"
    if not p.exists():
        return {}
    d = pd.read_csv(p, dtype=str, keep_default_na=False)
    if "comment" not in d:
        d["comment"] = ""
    return {tuple(r[k] for k in key): r for r in d.to_dict("records")}

# --- PMD events -> vintage labels ------------------------------------------------
# From June 2010 each fiscal event maps to the OBR forecast published with it.
OBR_EVENTS = {
    "Budget 2010 #2": "June 2010", "Autumn 2010": "November 2010", "Budget 2011": "March 2011",
    "Autumn 2011": "November 2011", "Budget 2012": "March 2012", "Autumn 2012": "December 2012",
    "Budget 2013": "March 2013", "Autumn 2013": "December 2013", "Budget 2014": "March 2014",
    "Autumn 2014": "December 2014", "Budget 2015": "March 2015", "Budget 2015 #2": "July 2015",
    "Autumn 2015": "November 2015", "Budget 2016": "March 2016", "Autumn 2016": "November 2016",
    "Budget 2017": "March 2017", "Autumn Budget 2017": "November 2017",
    "Spring Statement 2018": "March 2018", "Budget 2018": "October 2018",
    "Spring Statement 2019": "March 2019", "Budget 2020": "March 2020",
    "Spending Review 2020": "November 2020", "Spring Budget 2021": "March 2021",
    "Autumn Budget 2021": "October 2021", "Spring Statement 2022": "March 2022",
    "Autumn Statement 2022": "November 2022", "Spring Budget 2023": "March 2023",
    "Autumn Statement 2023": "November 2023", "Spring Budget 2024": "March 2024",
    "Autumn Budget 2024": "October 2024", "Spring Statement 2025": "March 2025",
    "Autumn Budget 2025": "November 2025", "Spring Forecast 2026": "March 2026",
}


def map_event(event: str, hmt_labels: list[str]) -> tuple[str | None, str, str]:
    """(vintage label, rule, confidence). Pre-2010 events map to HM Treasury
    vintages: a Budget to the first spring/summer vintage of its year, a
    pre-Budget report (PBR) or a second Budget to the autumn vintage."""
    if event in OBR_EVENTS:
        return OBR_EVENTS[event], "OBR fiscal event -> EFO published with it", "exact"
    m = re.fullmatch(r"(Budget|PBR) (\d{4})( #2)?", event)
    if not m:
        return None, "unmatched", "none"
    kind, year, second = m.group(1), int(m.group(2)), bool(m.group(3))
    months = sorted(list(calendar.month_name).index(l.split()[0])
                    for l in hmt_labels if l.endswith(str(year)))
    if kind == "Budget" and not second:
        # Budgets fall in March-July; a January vintage is some other publication.
        pick = ([mo for mo in months if 3 <= mo <= 7] or [mo for mo in months if mo <= 2])[:1]
        rule = "Budget -> first HM Treasury vintage of the year in March-July"
    else:
        pick = [mo for mo in months if mo >= 9][:1]
        rule = f"{'PBR' if kind == 'PBR' else 'second Budget'} -> autumn HM Treasury vintage of the year"
    if not pick:
        return None, rule + ": no vintage found", "none"
    return f"{calendar.month_name[pick[0]]} {year}", rule, "assumed"


# --- PMD tax heads -> HOFD sheets ---------------------------------------------------
TAX_HEADS = {
    "income tax": ("IT", "exact"), "nics": ("NICS", "exact"), "vat": ("VAT", "exact"),
    "corporation tax (onshore)": ("Onshore", "exact"), "north sea taxes": ("Oilandgas", "exact"),
    "fuel duty": ("Fuel", "exact"), "business rates": ("Business", "exact"),
    "capital gains tax": ("CGT", "exact"), "inheritance tax": ("IHT", "exact"),
    "tobacco duty": ("Tobacco", "exact"), "alcohol duty": ("Alcohol", "exact"),
    "vehicle excise duty": ("VED", "exact"), "vat refunds": ("VATrefunds", "exact"),
    "council tax": ("Council", "exact"), "air passenger duty": ("APD", "exact"),
    "insurance premium tax": ("IPT", "exact"), "climate change levy": ("CCL", "exact"),
    "bank levy": ("Bank", "exact"), "licence fee receipts": ("Licence", "exact"),
    "emissions trading scheme": ("ETS", "exact"), "electricity generators levy": ("EGL", "exact"),
    "cbam": ("CBAM", "exact"), "vaping duty": ("Vapes", "exact"),
    "health and social care levy": ("HSC", "exact"),
    # same concept, but the HOFD series may be defined differently
    "stamp duty": ("PTT", "assumed: covers property and shares; HOFD splits PTT and Shares"),
    "bank surcharge": ("Onshore", "assumed: surcharge on bank profits, recorded in onshore CT"),
    "energy profits levy": ("Oilandgas", "assumed: levy on oil and gas profits"),
}

SPENDING_HEADS = {
    "psce in rdel": ("RDEL", "exact"), "psgi in cdel": ("CDEL", "exact"),
    "welfare inside cap": ("Welfare in", "exact"), "welfare outside cap": ("Welfare out", "exact"),
    "social security benefits": ("Total welfare", "assumed: benefits are part of welfare spending"),
    "tax credits": ("Total welfare", "assumed: tax credits are part of welfare spending"),
    "locally-financed current expenditure": ("LASFEcurr", "exact"),
    "locally-financed capital expenditure": ("LASFEcap", "exact"),
    "net public service pension payments": ("Pensions", "exact"),
    "bbc current expenditure": ("BBCcur", "exact"), "student loans": ("Studentloans", "exact"),
    "company and other credits": ("Ctaxcreds", "assumed: HOFD 'company tax credits'"),
    "public corporations capital expenditure": ("PCcapex", "exact"),
    "debt interest": ("Netdebtint", "assumed: central government debt interest net of APF"),
    "current vat refunds": ("VATrefunds", "assumed"),
    "vat refunds": ("VATrefunds", "assumed"),
}


def map_head(head: str, measure_type: str) -> tuple[str | None, str]:
    table = TAX_HEADS if measure_type == "tax" else SPENDING_HEADS
    key = re.sub(r"\s+", " ", head.strip().lower())
    sheet, conf = table.get(key, (None, "none"))
    return sheet, conf


# --- attribution labels -> harmonized categories (D3 default) ----------------------
# D3: policy / economic determinants / calibration to outturn / classification and
# one-offs / modelling and other. The FRD's "underlying" mixes the last three
# D3 categories and cannot be split; it gets its own value.
D3 = ["policy", "economic_determinants", "calibration_to_outturn", "classification_one_offs",
      "modelling_other"]
FRD_PATHS = {
    "total": ("total", "block total: the full revision"),
    "policy": ("policy", ""),
    "policy/receipts": ("policy", ""),
    "policy/spending": ("policy", ""),
    "classification": ("classification_one_offs", ""),
    "underlying": ("underlying_unsplit", "economic determinants, outturn calibration and modelling together"),
    "underlying/receipts": ("underlying_unsplit", ""),
    "underlying/debt_interest": ("underlying_unsplit", ""),
    "underlying/non_interest_spending": ("underlying_unsplit", ""),
    "underlying/spending": ("underlying_unsplit", ""),
}
