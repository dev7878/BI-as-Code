"""KPI card: headline value, change vs a comparison period, optional reference (e.g. target), sparkline.

    SALES                                   ╱╲╱
    $2.30M                               ╱╲╱
    [▲ 4.5%] vs last year · 104% of target

Aggregation goes through the semantic layer, so ratio measures (margins, attainment) are computed
correctly for every window. Percent measures show change in percentage points.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from dash import dcc, html
from vizro.models.types import capture

from rbc_bi.components.aggregate import aggregate, aggregate_scalar, bucket_dates
from rbc_bi.components.timebar import COMPARE_LABEL, comparison_range, in_range, parse_range
from rbc_bi.theme.theme import format_value, tokens


def _sparkline(df: pd.DataFrame, measure: str, agg: dict, time_field: str, grain: str):
    if df.empty:
        return None
    s = aggregate(df.assign(**{time_field: bucket_dates(df[time_field], grain)}), [time_field], {measure: agg})
    if len(s) < 2:
        return None
    colour = tokens()["brand"]["chart_primary"]
    fig = go.Figure(go.Scatter(
        x=s[time_field], y=s[measure], mode="lines", line=dict(color=colour, width=2, shape="spline", smoothing=0.6),
        fill="tozeroy", fillcolor=tokens()["brand"]["chart_primary_fill"], hoverinfo="skip",
    ))
    fig.update_layout(
        template=None, margin=dict(l=0, r=0, t=2, b=0), height=48, showlegend=False,
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(visible=False), yaxis=dict(visible=False, rangemode="tozero"),
    )
    return dcc.Graph(figure=fig, config={"staticPlot": True, "displayModeBar": False}, className="rbc-kpi-spark")


def _delta(cur: float, prev: float, fmt: str, lower_is_better: bool):
    """(text, css class, arrow) for the change pill; percent measures change in percentage points."""
    if prev != prev or cur != cur:  # NaN
        return None
    if fmt == "percent":
        change = cur - prev
        text = f"{abs(change) * 100:.1f} pts"
    else:
        if not prev:
            return None
        change = (cur - prev) / abs(prev)
        text = f"{abs(change):.1%}"
    if abs(change) < 1e-12:
        return text, "flat", "→"
    good = (change < 0) if lower_is_better else (change > 0)
    return text, ("good" if good else "bad"), ("▲" if change > 0 else "▼")


@capture("figure")
def rbc_kpi(
    data_frame: pd.DataFrame,
    measure: str,
    agg: dict,
    fmt: str,
    title: str,
    reference: str | None = None,
    reference_agg: dict | None = None,
    lower_is_better: bool = False,
    time_field: str | None = None,
    date_range: list | None = None,
    compare: str = "none",
    time_grain: str = "month",
):
    rng = parse_range(date_range) if time_field else None
    cur = in_range(data_frame, time_field, rng)
    value = aggregate_scalar(cur, agg, measure)

    footer = []
    prev_rng = comparison_range(rng, compare)
    if prev_rng is not None:
        prev = in_range(data_frame, time_field, prev_rng)
        d = _delta(value, aggregate_scalar(prev, agg, measure) if not prev.empty else float("nan"), fmt, lower_is_better)
        if d:
            text, cls, arrow = d
            footer.append(html.Span([html.Span(arrow, **{"aria-hidden": "true"}), f" {text}"],
                                    className=f"rbc-pill rbc-pill-{cls}"))
            footer.append(html.Span(COMPARE_LABEL[compare], className="rbc-kpi-note"))
        else:
            footer.append(html.Span(f"no data {COMPARE_LABEL[compare]}", className="rbc-kpi-note"))
    if reference:
        ref = aggregate_scalar(cur, reference_agg, reference)
        if ref:
            ratio = value / ref
            good = (ratio <= 1) if lower_is_better else (ratio >= 1)
            if footer:
                footer.append(html.Span("·", className="rbc-kpi-note"))
            footer.append(html.Span(f"{ratio:.0%} of {format_value(ref, fmt)} target",
                                    className=f"rbc-kpi-note rbc-kpi-ref-{'good' if good else 'bad'}"))

    spark = _sparkline(cur, measure, agg, time_field, time_grain) if time_field else None
    return html.Div(
        [
            html.Div(title, className="rbc-kpi-title"),
            html.Div([html.Div(format_value(value, fmt), className="rbc-kpi-value"), spark], className="rbc-kpi-main"),
            html.Div(footer, className="rbc-kpi-footer") if footer else None,
        ],
        className="rbc-kpi",
        role="group",
        **{"aria-label": title},
    )
