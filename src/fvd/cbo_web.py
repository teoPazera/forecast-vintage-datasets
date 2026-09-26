"""Parsing of cbo.gov listing pages (as archived by the Wayback Machine).

Two listings are used:
- the current "Major Recurring Reports" page (Drupal views; publications
  since 2000, each with a <time datetime> stamp);
- the pre-2012 site's "Publications by Subject" pages, which list reports
  back to 1975 with a title and a date that is either a full date
  ("January 26, 2000") or a month ("January 2000").
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime

from bs4 import BeautifulSoup

from .http import fetch_page
from .paths import RAW_WEB

CBO = "https://www.cbo.gov"
RECURRING = f"{CBO}/about/products/major-recurring-reports"
OLD_BY_SUBJECT = "http://www.cbo.gov/publications/bysubject.cfm?cat={cat}"
OLD_CATEGORIES = {0: "Budget and Economic Outlook",
                  1: "Analysis of the President's Budget",
                  35: "Monthly Budget Review"}


@dataclass
class Listed:
    section: str
    title: str
    url: str
    date_text: str
    pub_date: date | None      # full date if the listing gives one
    month: str                 # YYYY-MM
    day_is_placeholder: bool = False


def recurring_reports() -> list[Listed]:
    s = BeautifulSoup(fetch_page(RECURRING, RAW_WEB), "lxml")
    out = []
    for view in s.select("div.view-major-recurring-reports"):
        h = view.find("h4")
        section = h.get_text(" ", strip=True) if h else ""
        for a in view.find_all("a", href=True):
            t = a.find("time")
            if t is None or not t.get("datetime"):
                continue
            d = datetime.fromisoformat(t["datetime"].replace("Z", "+00:00")).date()
            # The listing stamps many pre-2008 items with day 01 (e.g. 2006-01-01);
            # those are month-level dates, not release days.
            placeholder = d.day == 1 and d.year < 2008
            out.append(Listed(section=section, title=f"{section} ({t.get_text(strip=True)})",
                              url=CBO + a["href"] if a["href"].startswith("/") else a["href"],
                              date_text=t["datetime"], pub_date=None if placeholder else d,
                              month=d.strftime("%Y-%m"), day_is_placeholder=placeholder))
    return out


def old_by_subject(cat: int) -> list[Listed]:
    url = OLD_BY_SUBJECT.format(cat=cat)
    s = BeautifulSoup(fetch_page(url, RAW_WEB), "lxml")
    out = []
    for a in s.select("a.doctitle"):
        title = a.get_text(" ", strip=True)
        span = a.find_next("span", class_="docdate")
        dt = span.get_text(" ", strip=True) if span else ""
        full = month = None
        for fmt in ("%B %d, %Y", "%B %Y"):
            try:
                parsed = datetime.strptime(dt, fmt).date()
            except ValueError:
                continue
            if fmt == "%B %d, %Y":
                full = parsed
            month = parsed.strftime("%Y-%m")
            break
        if month is None:
            continue
        href = a["href"]
        if href.startswith("/"):
            href = "http://www.cbo.gov" + href
        out.append(Listed(section=OLD_CATEGORIES.get(cat, str(cat)), title=re.sub(r"\s+", " ", title),
                          url=href, date_text=dt, pub_date=full, month=month))
    return out
