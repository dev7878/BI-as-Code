"""Semantic-aware aggregation shared by KPIs, charts and tables.

Measures are described as {"agg": "...", "ratio": [num, den] | None}. Ratio measures are
re-computed at every grain as sum(num) / sum(den), never averaged.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

PANDAS_AGG = {"count_distinct": "nunique"}


def _series(df_or_group, column: str, agg: str):
    return df_or_group[column].agg(PANDAS_AGG.get(agg, agg))


def aggregate(df: pd.DataFrame, by: list[str], measures: dict[str, dict]) -> pd.DataFrame:
    """Group `df` by `by` and roll each measure up with its aggregation."""
    if not by:
        row = {name: aggregate_scalar(df, m) for name, m in measures.items()}
        return pd.DataFrame([row])
    g = df.groupby(by, dropna=False, observed=True, sort=True)
    out = {}
    for name, m in measures.items():
        if m["agg"] == "ratio":
            num, den = m["ratio"]
            out[name] = g[num].sum() / g[den].sum().replace(0, np.nan)
        else:
            out[name] = _series(g, name, m["agg"])
    return pd.DataFrame(out).reset_index()


def aggregate_scalar(df: pd.DataFrame, m: dict, column: str | None = None) -> float:
    if m["agg"] == "ratio":
        num, den = m["ratio"]
        d = df[den].sum()
        return float(df[num].sum() / d) if d else float("nan")
    return float(_series(df, column or m["column"], m["agg"]))


TIME_GRAIN = {"day": "D", "week": "W", "month": "M", "quarter": "Q", "year": "Y"}


def bucket_dates(s: pd.Series, grain: str) -> pd.Series:
    s = pd.to_datetime(s)
    if grain == "day":
        return s.dt.normalize()
    return s.dt.to_period(TIME_GRAIN[grain]).dt.start_time
