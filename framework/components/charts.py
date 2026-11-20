"""The approved chart set: line, bar, stacked_bar, area, scatter, donut.

Adding a chart type = add a branch here + the Literal in spec/models.py + a test. Specs never set
colours or fonts; series colours come from the theme in a fixed order.
"""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from vizro.models.types import capture

from rbc_bi.components.aggregate import aggregate, bucket_dates
from rbc_bi.components.timebar import in_range, parse_range
from rbc_bi.theme.theme import AXIS_FORMATS, D3_FORMATS, tokens

DATE_DTICK = {"quarter": "M3", "year": "M12"}
DATE_TICKS = {"day": "%d %b %Y", "week": "%d %b %Y", "month": "%b %Y", "quarter": "Q%q %Y", "year": "%Y"}


OTHER_COLOUR = "#9AA1AD"  # neutral grey for any series beyond the validated palette


def category_order(df: pd.DataFrame, x: str, y: str, measure: dict, top_n: int | None, sort: str | None) -> list:
    """x categories ranked by y, aggregated per x with the measure's own rule (so ratios and means rank by
    their true value, not a sum across split_by). top_n always keeps the N *largest*; sort only sets the
    display order of what is kept."""
    totals = aggregate(df, [x], {y: measure}).set_index(x)[y].sort_values(ascending=False)
    keep = list(totals.index[:top_n]) if top_n else list(totals.index)
    return keep[::-1] if sort == "asc" else keep


def colour_map(values, palette: list[str]) -> dict:
    """Fixed colour per entity: sorted full domain -> palette slots, never cycled."""
    ordered = sorted(v for v in set(values) if pd.notna(v))
    return {v: (palette[i] if i < len(palette) else OTHER_COLOUR) for i, v in enumerate(ordered)}


def _domain(source: str | None, column: str, fallback: pd.Series) -> list:
    """All values of `column` in the *unfiltered* dataset, so filtering never repaints the survivors."""
    if source:
        try:
            from vizro.managers import data_manager

            return data_manager[source].load()[column].dropna().unique().tolist()
        except Exception:  # noqa: BLE001 - fall back to what we have
            pass
    return fallback.dropna().unique().tolist()


@capture("graph")
def rbc_chart(
    data_frame: pd.DataFrame,
    chart_type: str,
    x: str,
    y: list[str],
    measures: dict,
    labels: dict,
    formats: dict,
    split_by: str | None = None,
    detail: str | None = None,
    time_grain: str | None = None,
    x_is_date: bool = False,
    sort: str | None = None,
    top_n: int | None = None,
    horizontal: bool = False,
    source: str | None = None,
    time_field: str | None = None,
    date_range: list | None = None,
) -> go.Figure:
    t = tokens()
    df = in_range(data_frame, time_field, parse_range(date_range)) if time_field else data_frame
    if x_is_date:
        df = df.assign(**{x: bucket_dates(df[x], time_grain or "month")})

    # 1. Aggregate to the chart's grain (the spec gives fields, the framework does the maths).
    if chart_type == "scatter":
        by = [c for c in (detail, split_by) if c]
        wanted = {m: measures[m] for m in dict.fromkeys([x, *y])}
        data = aggregate(df, by, wanted) if by else df[[*by, *wanted]]
    else:
        by = [x] + ([split_by] if split_by else [])
        data = aggregate(df, by, {m: measures[m] for m in y})

    # 2. Order / limit categories.
    category_orders = {}
    colours = {}
    if split_by:
        colours = colour_map(_domain(source, split_by, data[split_by]), t["categorical"])
        category_orders[labels[split_by]] = [v for v in colours if v in set(data[split_by])]
    if chart_type == "donut":
        colours = colour_map(_domain(source, x, data[x]), t["categorical"])
    if chart_type in ("bar", "stacked_bar", "donut") and not x_is_date:
        if sort or top_n:
            order = category_order(df, x, y[0], measures[y[0]], top_n, sort or "desc")
            data = data[data[x].isin(order)]
            category_orders[labels[x]] = order

    # 3. Plot on human labels (axis titles and legends come for free).
    data = data.rename(columns=labels)
    X, Y = labels[x], [labels[v] for v in y]
    color = labels[split_by] if split_by else None
    single = color is None and len(Y) == 1 and chart_type != "donut"
    seq = [t["single_series"]] if single else t["categorical"]
    yarg = Y[0] if len(Y) == 1 else Y
    common = dict(color=color, color_discrete_sequence=seq, category_orders=category_orders)
    if split_by:
        common["color_discrete_map"] = colours
    fmt = formats[y[0]]

    if chart_type == "line":
        fig = px.line(data, x=X, y=yarg, markers=len(data) <= 24, **common)
        fig.update_traces(line_width=2, marker_size=8)
    elif chart_type == "area":
        fig = px.area(data, x=X, y=yarg, **common)
        fig.update_traces(line_width=2)
    elif chart_type in ("bar", "stacked_bar"):
        barmode = "stack" if chart_type == "stacked_bar" else "group"
        if horizontal:
            fig = px.bar(data, y=X, x=yarg, orientation="h", barmode=barmode, **common)
            fig.update_yaxes(autorange="reversed" if (sort or top_n) else True, title_text="")
        else:
            fig = px.bar(data, x=X, y=yarg, barmode=barmode, **common)
        fig.update_layout(barcornerradius=4, bargap=0.3, bargroupgap=0.08)
        fig.update_traces(marker_line_width=0)
    elif chart_type == "scatter":
        fig = px.scatter(data, x=X, y=yarg, hover_name=labels.get(detail) if detail else None, **common)
        fig.update_traces(marker=dict(size=10, opacity=0.9))  # surface ring comes from the theme template
    elif chart_type == "donut":
        fig = px.pie(data, names=X, values=Y[0], hole=0.6, color=X, color_discrete_map=colours,
                     category_orders=category_orders)
        fig.update_traces(textinfo="percent", textposition="outside", sort=False,
                          hovertemplate=f"%{{label}}<br>%{{value:{D3_FORMATS[fmt]}}} (%{{percent}})<extra></extra>")
    else:  # unreachable: validated upstream
        raise ValueError(f"unknown chart type {chart_type}")

    # 4. Number formats from the semantic type; legend on top; recessive axes.
    if chart_type != "donut":
        value_axis = fig.update_xaxes if horizontal else fig.update_yaxes
        value_axis(tickformat=AXIS_FORMATS[fmt], hoverformat=D3_FORMATS[fmt])
        if chart_type == "scatter":
            fig.update_xaxes(tickformat=AXIS_FORMATS[formats[x]], hoverformat=D3_FORMATS[formats[x]])
        if x_is_date:
            g = time_grain or "month"
            fig.update_xaxes(tickformat=DATE_TICKS[g], hoverformat=DATE_TICKS[g])
            if g in DATE_DTICK:  # one tick per bucket, so labels never repeat ("Q1, Q1, Q2")
                fig.update_xaxes(dtick=DATE_DTICK[g], tick0=data[X].min() if len(data) else None)
        if len(Y) > 1:
            (fig.update_xaxes if horizontal else fig.update_yaxes)(title_text="")
        if chart_type in ("line", "area"):
            fig.update_layout(hovermode="x unified")
    fig.update_layout(
        showlegend=not single,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0, title_text=""),
    )
    return fig
