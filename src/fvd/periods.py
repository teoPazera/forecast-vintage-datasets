"""Target periods, horizons and cell roles (plan section 3)."""

from __future__ import annotations

import re
from datetime import date

import pandas as pd

DAYS_PER_MONTH = 365.25 / 12


def period_bounds(target_period: str, period_type: str) -> tuple[date, date]:
    """First and last day of a target period.

    uk_fiscal_year '2025-26': 1 April 2025 to 31 March 2026
    us_fiscal_year '2025':    1 October 2024 to 30 September 2025
    calendar_year  '2025':    1 January to 31 December 2025
    """
    if period_type == "uk_fiscal_year":
        y = int(target_period[:4])
        return date(y, 4, 1), date(y + 1, 3, 31)
    if period_type == "us_fiscal_year":
        y = int(target_period)
        return date(y - 1, 10, 1), date(y, 9, 30)
    if period_type == "calendar_year":
        y = int(target_period)
        return date(y, 1, 1), date(y, 12, 31)
    raise ValueError(period_type)


def normalize_uk_fiscal(v) -> str | None:
    """'2008-09' and '2008–09' -> '2008-09'; '1999-00' -> '1999-00'."""
    if not isinstance(v, str):
        return None
    m = re.fullmatch(r"\s*(\d{4})\s*[-–/]\s*(\d{2})\s*", v)
    return f"{m.group(1)}-{m.group(2)}" if m else None


def add_role_and_horizon(df: pd.DataFrame, pub_col: str = "publication_date") -> pd.DataFrame:
    """Add cell_role and horizon_months from target period bounds and publication date."""
    starts, ends = zip(*[period_bounds(tp, pt) for tp, pt in zip(df.target_period, df.period_type)])
    start = pd.to_datetime(pd.Series(starts, index=df.index))
    end = pd.to_datetime(pd.Series(ends, index=df.index))
    pub = pd.to_datetime(df[pub_col])
    df = df.copy()
    df["horizon_months"] = ((end - pub).dt.days / DAYS_PER_MONTH).round(2)
    role = pd.Series("in_progress", index=df.index, dtype=object)
    role[end < pub] = "past"
    role[pub < start] = "future"
    role[pub.isna()] = None
    df["cell_role"] = role
    return df
