"""OBR Historical Official Forecasts Database (HOFD): sheet layout helpers.

Sheet layout (verified on the Spring 2026 edition): title row, unit row,
blank row, a header row starting "Back to contents" followed by the target
periods, one row per vintage, a blank row, an "Outturn data*" row, footnotes.
Some sheets carry memo rows ("Memo: restated March 2019 forecast").
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime

MONTHS = ("January|February|March|April|May|June|July|August|September|"
          "October|November|December")

# "March 2026", "March2026", "March -20141" (footnote 1), "December-20131",
# "November 2022**", "November 2017†"
_REGULAR = re.compile(rf"^({MONTHS})\s*-?\s*(\d{{4}})(\d?)\s*([*†]*)$")
_MEMO = re.compile(rf"^Memo:\s*(restated|supplementary)\s+({MONTHS})\s+(\d{{4}})(?:\s+forecast)?$",
                   re.IGNORECASE)

# Sheets that are not series: navigation, section headers and a helper grid.
NON_SERIES_SHEETS = {"Index", "Contents", "Aggregates", "Receipts", "Spending", "Economy"}


@dataclass(frozen=True)
class VintageLabel:
    raw: str
    label: str          # normalized "Month YYYY"
    kind: str           # "regular" or "memo"
    memo_type: str      # "", "restated" or "supplementary"
    footnote: str       # footnote marker stripped from the raw label, if any

    @property
    def vintage_label(self) -> str:
        return self.label if self.kind == "regular" else f"{self.label} ({self.memo_type})"


def parse_label(raw) -> VintageLabel | None:
    if isinstance(raw, (datetime, date)):
        # Some sheets (Taxlit, R&D, SUME) store the vintage label as a date
        return VintageLabel(raw=raw.isoformat(), label=f"{raw:%B} {raw.year}", kind="regular",
                            memo_type="", footnote="[date cell]")
    if not isinstance(raw, str):
        return None
    s = raw.strip()
    m = _REGULAR.match(s)
    if m:
        return VintageLabel(raw=raw, label=f"{m.group(1)} {m.group(2)}", kind="regular",
                            memo_type="", footnote=(m.group(3) or "") + (m.group(4) or ""))
    m = _MEMO.match(s)
    if m:
        return VintageLabel(raw=raw, label=f"{m.group(2).capitalize()} {m.group(3)}", kind="memo",
                            memo_type=m.group(1).lower(), footnote="")
    return None


def series_sheets(sheetnames: list[str], include_chart_copies: bool = False) -> list[str]:
    out = [n for n in sheetnames if n not in NON_SERIES_SHEETS]
    if not include_chart_copies:
        out = [n for n in out if not n.endswith(" (2)")]
    return out


def _key(label: str) -> tuple[int, int]:
    mon, yr = label.split()
    return int(yr), MONTHS.split("|").index(mon) + 1


def vintage_rows(rows: list[tuple]) -> list[tuple[int, VintageLabel]]:
    """(0-based row index, label) for every vintage or memo row in a sheet.

    Regular vintage rows are in date order. A label that breaks the order but
    fits it one year later is a typo in the source (the £PSCR and £PSNB sheets
    have "July 1996" between "November 1996" and "November 1997", which is the
    July 1997 Budget); it is corrected, with the raw label kept.
    """
    out = []
    for i, r in enumerate(rows):
        lab = parse_label(r[0] if r else None)
        if lab is not None:
            out.append((i, lab))
    regular = [k for k, (_, lab) in enumerate(out) if lab.kind == "regular"]
    for pos, k in enumerate(regular):
        lab = out[k][1]
        prev = out[regular[pos - 1]][1] if pos > 0 else None
        nxt = out[regular[pos + 1]][1] if pos + 1 < len(regular) else None
        if prev is not None and _key(lab.label) <= _key(prev.label):
            y, m = _key(lab.label)
            fixed = f"{lab.label.split()[0]} {y + 1}"
            if _key(fixed) > _key(prev.label) and (nxt is None or _key(fixed) < _key(nxt.label)):
                out[k] = (out[k][0], VintageLabel(raw=lab.raw, label=fixed, kind="regular",
                                                  memo_type="", footnote=lab.footnote + "[year corrected]"))
    return out
