"""Parsing of obr.uk landing and listing pages (as served, or as archived)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime

from bs4 import BeautifulSoup

from .http import FetchError, fetch_page, normalize_url
from .paths import RAW_WEB

OBR = "https://obr.uk"


@dataclass
class Landing:
    url: str
    title: str
    publication_date: date | None
    date_text: str
    files: list[tuple[str, str]] = field(default_factory=list)  # (label, url)
    previous_url: str | None = None


def _abs(href: str) -> str:
    href = href.strip()
    m = re.match(r"https?://web\.archive\.org/web/\d+[a-z_]*/(.+)$", href)
    if m:
        href = m.group(1)
    if href.startswith("/"):
        href = OBR + href
    return normalize_url(href.replace("http://", "https://", 1))


def parse_date(text: str) -> date | None:
    text = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", text.strip())
    for fmt in ("%d %B %Y", "%d %b %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    return None


def _main(s: BeautifulSoup):
    """The page body without site navigation (header/footer menus link to the
    latest publications and would pollute every page's file list)."""
    for tag in s.find_all(["header", "footer", "nav"]):
        tag.decompose()
    return s.find("main") or s.find("article") or s.body or s


def parse_landing(url: str, previous_label: str) -> Landing:
    html = fetch_page(url, RAW_WEB)
    s = BeautifulSoup(html, "lxml")
    title = (s.find("h1").get_text(" ", strip=True) if s.find("h1")
             else (s.title.string or "").split(" - ")[0])
    prev = None
    for a in s.find_all("a", href=True):
        if a.get_text(" ", strip=True).lower() == previous_label.lower():
            prev = _abs(a["href"])
            break
    date_text = ""
    for t in s.find_all("time", class_="date"):
        if parse_date(t.get_text(" ", strip=True)):
            date_text = t.get_text(" ", strip=True)
            break
    main = _main(s)
    files: dict[str, str] = {}
    for a in main.find_all("a", href=True):
        h = _abs(a["href"])
        if "/download/" not in h and "/docs/" not in h:
            continue
        label = a.get_text(" ", strip=True)
        if label.lower() in ("pdf", "xlsx", "zip", "xls", "docx", "csv", ""):
            files.setdefault(h, "")
        else:
            files[h] = label
    return Landing(url=_abs(url), title=title, publication_date=parse_date(date_text),
                   date_text=date_text, files=[(lbl, h) for h, lbl in files.items()],
                   previous_url=prev)


def walk_chain(start_url: str, previous_label: str, limit: int = 80) -> list[Landing]:
    """Follow the 'Previous forecast' / 'Previous report' links from `start_url`."""
    out, seen, url = [], set(), start_url
    while url and url not in seen and len(out) < limit:
        seen.add(url)
        try:
            page = parse_landing(url, previous_label)
        except FetchError as exc:
            out.append(Landing(url=url, title=f"UNAVAILABLE: {exc}",
                               publication_date=None, date_text=""))
            break
        out.append(page)
        url = page.previous_url
    return out


FORMER_HOSTS = ("budgetresponsibility.org.uk", "budgetresponsibility.independent.gov.uk")
_PDF_INDEX: dict[str, list[dict]] = {}


def archived_pdfs() -> list[dict]:
    """Wayback index of PDFs on obr.uk and the OBR's former domains (cached)."""
    import json

    from .http import wayback_captures

    cache = RAW_WEB / "wayback_index_obr_pdfs.json"
    if not _PDF_INDEX:
        if cache.exists():
            _PDF_INDEX["all"] = json.loads(cache.read_text())
        else:
            rows = []
            for host in ("obr.uk",) + FORMER_HOSTS:
                rows += wayback_captures(f"{host}/", match="prefix", collapse="urlkey",
                                         filter=["mimetype:application/pdf", "statuscode:200"])
            cache.write_text(json.dumps(rows))
            _PDF_INDEX["all"] = rows
    return _PDF_INDEX["all"]


_SHEET_INDEX: dict[str, list[dict]] = {}


def archived_spreadsheets() -> list[dict]:
    """Wayback index of spreadsheets on obr.uk and the OBR's former domains (cached)."""
    import json

    from .http import wayback_captures

    cache = RAW_WEB / "wayback_index_obr_spreadsheets.json"
    if not _SHEET_INDEX:
        if cache.exists():
            _SHEET_INDEX["all"] = json.loads(cache.read_text())
        else:
            rows = []
            # obr.uk/ as a whole is too large for one index query; files live under /docs/
            for prefix in ("obr.uk/docs/",) + tuple(f"{h}/" for h in FORMER_HOSTS):
                for mt in ("mimetype:application/vnd.ms-excel",
                           "mimetype:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"):
                    rows += wayback_captures(prefix, match="prefix", collapse="urlkey",
                                             filter=[mt, "statuscode:200"])
            cache.write_text(json.dumps(rows))
            _SHEET_INDEX["all"] = rows
    return _SHEET_INDEX["all"]


def spreadsheet_candidates(month: str, year: int, words: tuple[str, ...],
                           exclude: tuple[str, ...]) -> list[dict]:
    """Archived spreadsheets whose file name names the month and year and a word."""
    m_abbr = month[:3].lower()
    out = []
    for c in archived_spreadsheets():
        name = c["original"].rsplit("/", 1)[-1].lower()
        if not any(w in name for w in words) or any(x in name for x in exclude):
            continue
        if str(year) not in name and str(year)[2:] not in name:
            continue
        if month.lower() not in name and not re.search(rf"{m_abbr}(?![a-z])", name):
            continue
        out.append(c)
    out.sort(key=lambda c: -int(c.get("length") or 0))
    return out


def report_candidates(month: str, year: int, words: tuple[str, ...],
                      exclude: tuple[str, ...], require_month: bool = True,
                      require_year: bool = True) -> list[dict]:
    """Archived PDFs whose file name names the year, the month (if required) and
    one of `words`. Dates in file names may be written 23032011 or 291110.

    Largest first: the full report is the largest file for a publication.
    """
    import calendar as _cal

    m = list(_cal.month_name).index(month)
    yy = str(year)[2:]
    pats = [rf"{month.lower()}", rf"{month[:3].lower()}(?![a-z])", rf"{m:02d}{year}",
            rf"(?<!\d)\d{{2}}{m:02d}{yy}(?!\d)"]
    out = []
    for c in archived_pdfs():
        name = c["original"].rsplit("/", 1)[-1].lower()
        if not any(w in name for w in words) or any(x in name for x in exclude):
            continue
        if require_year and str(year) not in name and not re.search(rf"{m:02d}{yy}(?!\d)", name):
            continue
        if require_month and not any(re.search(p, name) for p in pats):
            continue
        out.append(c)
    out.sort(key=lambda c: -int(c.get("length") or 0))
    return out


def listing_links(url: str, pattern: str) -> list[tuple[str, str]]:
    """(label, url) of links in a listing page's body whose URL matches `pattern`."""
    s = BeautifulSoup(fetch_page(url, RAW_WEB), "lxml")
    out: dict[str, str] = {}
    for a in _main(s).find_all("a", href=True):
        h = _abs(a["href"])
        if re.search(pattern, h):
            lbl = a.get_text(" ", strip=True)
            if lbl.lower() not in ("pdf", "xlsx", "zip", ""):
                out[h] = lbl
            else:
                out.setdefault(h, "")
    return [(lbl, h) for h, lbl in out.items()]
