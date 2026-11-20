"""KPI card: one headline number, optionally compared with a reference measure (e.g. a target).

Renders with Vizro's own KPI card CSS classes so it looks native, but aggregates through the
semantic layer (ratio measures are computed correctly).
"""

from __future__ import annotations

import dash_bootstrap_components as dbc
import pandas as pd
from dash import html
from vizro.models.types import capture

from rbc_bi.components.aggregate import aggregate_scalar
from rbc_bi.theme.theme import format_value


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
):
    value = aggregate_scalar(data_frame, agg, measure)
    header = dbc.CardHeader(html.H4(title, className="card-kpi-title"), className="card-kpi-header")
    body = dbc.CardBody(format_value(value, fmt))
    if not reference:
        return dbc.Card([header, body], class_name="card-kpi")

    ref = aggregate_scalar(data_frame, reference_agg, reference)
    delta = value - ref
    rel = delta / abs(ref) if ref else float("nan")
    good = (delta < 0) if lower_is_better else (delta > 0)
    cls = "" if delta == 0 else ("color-pos" if good else "color-neg")
    arrow = "arrow_circle_up" if delta > 0 else "arrow_circle_down" if delta < 0 else "do_not_disturb_on"
    word = "above" if delta > 0 else "below" if delta < 0 else "at"
    footer = dbc.CardFooter(
        [
            html.Span(
                [html.Span(arrow, className="material-symbols-outlined", **{"aria-hidden": "true"}),
                 html.Span(f"{rel:+.1%}" if rel == rel else "-")],
                className="card-kpi-delta-chip",
            ),
            # Words as well as colour: never colour alone.
            html.Span(f"{word} {format_value(ref, fmt)} ref.", className="card-kpi-reference-text"),
        ],
        class_name=cls,
    )
    return dbc.Card([header, body, footer], class_name="card-kpi")
