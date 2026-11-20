"""Time logic shared by every component: date ranges, comparison windows and default ranges.

Ranges are inclusive [start, end] calendar dates. Month-aligned ranges shift by whole months, so
"previous period" of Jan-Mar is Oct-Dec (QoQ) and of March is February (MoM), not "the previous 90 days".
"""

from __future__ import annotations

from datetime import date

import pandas as pd

COMPARE_LABEL = {"previous_period": "vs previous period", "previous_year": "vs last year"}


def parse_range(date_range) -> tuple[pd.Timestamp, pd.Timestamp] | None:
    """Accept [start, end] as dates, datetimes or ISO strings (what the date picker sends)."""
    if not date_range or len(date_range) != 2 or not all(date_range):
        return None
    start, end = (pd.Timestamp(v).normalize() for v in date_range)
    return (start, end) if start <= end else (end, start)


def in_range(df: pd.DataFrame, field: str, rng: tuple[pd.Timestamp, pd.Timestamp] | None) -> pd.DataFrame:
    if rng is None or field not in df.columns:
        return df
    t = pd.to_datetime(df[field])
    return df[(t >= rng[0]) & (t < rng[1] + pd.Timedelta(days=1))]


def _month_aligned(start: pd.Timestamp, end: pd.Timestamp) -> int | None:
    """Number of whole months if [start, end] is exactly whole calendar months, else None."""
    if start.day != 1 or (end + pd.Timedelta(days=1)).day != 1:
        return None
    return (end.year - start.year) * 12 + end.month - start.month + 1


def comparison_range(rng, compare: str):
    if rng is None or compare in (None, "none"):
        return None
    start, end = rng
    if compare == "previous_year":
        return start - pd.DateOffset(years=1), end - pd.DateOffset(years=1)
    months = _month_aligned(start, end)
    if months:
        prev_start = start - pd.DateOffset(months=months)
        return prev_start, start - pd.Timedelta(days=1)
    length = end - start
    prev_end = start - pd.Timedelta(days=1)
    return prev_end - length, prev_end


def default_range(name: str, lo: date, hi: date) -> list[date]:
    """Resolve a named default range against the data's own latest date (not today), so demo data
    that stops in the past still opens on a meaningful window."""
    lo, hi = pd.Timestamp(lo), pd.Timestamp(hi)
    month_start = hi.to_period("M").start_time
    starts = {
        "all": lo,
        "last_12_months": month_start - pd.DateOffset(months=11),
        "last_24_months": month_start - pd.DateOffset(months=23),
        "year_to_date": pd.Timestamp(year=hi.year, month=1, day=1),
        "last_quarter": hi.to_period("Q").start_time,
        "last_month": month_start,
    }
    start = max(starts[name], lo)
    end = hi.to_period("M").end_time.normalize() if name != "all" else hi
    return [start.date(), end.date()]
