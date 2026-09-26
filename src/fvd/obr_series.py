"""OBR HOFD series: identifiers, families (decision D7), kinds and hierarchy.

Sheet names are the source codes. Families follow the default in D7; the
hierarchy follows plan E1 task 5. Both are editable here and nowhere else.
"""

from __future__ import annotations

import re

# --- families (D7 default) ------------------------------------------------------
FAMILIES: dict[str, list[str]] = {
    "aggregate": ["£PSNB", "PSNB", "£PSCR", "PSCR", "£TME", "TME", "CACB", "CAPSNB", "PSNFL",
                  "PSND", "PSNI", "£CB", "CB"],
    "income_taxes": ["IT", "SA IT", "PAYE IT", "NICS", "HSC"],
    "consumption_taxes": ["VAT", "VATrefunds", "IPT"],
    "capital_taxes": ["CGT", "IHT", "PTT", "Shares"],
    "business_taxes": ["Onshore", "Business", "Bank", "Oilandgas", "EGL", "CCL"],
    "duties": ["Alcohol", "Spirits", "Wine", "Beercider", "Tobacco", "Fuel", "VED", "APD", "Vapes"],
    "other_receipts": ["Council", "Licence", "ETS", "CBAM", "Scotland"],
    "spending_del": ["RDEL", "CDEL", "R&D", "SUME"],
    "spending_welfare": ["Total welfare", "Welfare in", "Welfare out"],
    "spending_debt_interest": ["PSDebtint", "Debtint", "APF", "Netdebtint", "PCDebtint"],
    "spending_local": ["LASFEcurr", "LASFEcap", "Ctaxcreds"],
    "spending_other": ["Pensions", "EU", "PCcapex", "BBCcur", "Lotterycur", "Lotterycap",
                       "Studentloans", "Fundedpensions", "GGIpensions", "Taxlit", "GGdepreciation",
                       "NRcap", "NRcur"],
}
SHEET_FAMILY = {s: f for f, sheets in FAMILIES.items() for s in sheets}
ECONOMY_FAMILY = "economy"   # every sheet after the "Economy" section header (D12)

# Series that can change sign: never logged (plan 4.1).
BALANCES = {"£PSNB", "PSNB", "£CB", "CB", "CACB", "CAPSNB", "Currentacc£", "Currentacc%GDP",
            "Outputgap", "Inventories", "Taxlit", "APF"}

# --- hierarchy (plan E1 task 5) -------------------------------------------------
# parent -> children. Receipts: current receipts -> major heads; income tax ->
# PAYE and self-assessed; alcohol -> spirits, wine, beer and cider. Spending:
# TME -> the HOFD spending lines, welfare -> inside/outside the cap. The HOFD does
# not list every receipt or spending line, so every parent has a residual.
_RECEIPT_SUBS = {"PAYE IT", "SA IT", "Spirits", "Wine", "Beercider"}
HIERARCHY: dict[str, list[str]] = {
    "£PSCR": [s for f in ("income_taxes", "consumption_taxes", "capital_taxes", "business_taxes",
                          "duties", "other_receipts")
              for s in FAMILIES[f] if s not in _RECEIPT_SUBS],
    "IT": ["PAYE IT", "SA IT"],
    "Alcohol": ["Spirits", "Wine", "Beercider"],
    "£TME": ["RDEL", "CDEL", "Total welfare", "LASFEcurr", "LASFEcap", "Netdebtint", "PCDebtint",
             "Pensions", "EU", "PCcapex", "Ctaxcreds", "BBCcur", "Lotterycur", "Lotterycap",
             "Studentloans", "Fundedpensions", "GGIpensions", "Taxlit", "GGdepreciation",
             "NRcap", "NRcur", "R&D", "SUME"],
    "Total welfare": ["Welfare in", "Welfare out"],
}
PARENT = {c: p for p, cs in HIERARCHY.items() for c in cs}


def series_id(sheet: str) -> str:
    """Stable identifier from the sheet name: '£PSNB' -> 'obr.psnb_gbp', 'R&D' -> 'obr.r_d'."""
    s = sheet.strip()
    suffix = ""
    if "£" in s and s not in ("£€rate",):
        suffix = "_gbp"
    s = s.replace("£€", "gbp_eur_").replace("£", "").replace("$", "_usd").replace("%GDP", "_pct_gdp")
    s = re.sub(r"[^0-9A-Za-z]+", "_", s).strip("_").lower()
    return f"obr.{s}{suffix}"


def kind(sheet: str, unit: str) -> str:
    if sheet in BALANCES:
        return "balance"
    u = (unit or "").lower()
    if "per cent" in u or "percentage" in u:
        return "rate"
    return "level"


def harmonized_unit(unit: str) -> str:
    return "GBP bn" if (unit or "").strip().lower() == "£ billion" else (unit or "").strip()
