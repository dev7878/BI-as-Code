"""Table: AG Grid with semantic labels and number formats. Optional group_by aggregation."""

from __future__ import annotations

import pandas as pd
from vizro.models.types import capture
from vizro.tables import dash_ag_grid

from rbc_bi.components.aggregate import aggregate

# AG Grid cell data types defined by Vizro's dash_ag_grid defaults.
CELL_TYPES = {"currency": "dollar", "percent": "percent", "number": "numeric", "integer": "number"}


@capture("ag_grid")
def rbc_table(
    data_frame: pd.DataFrame,
    columns: list[str],
    labels: dict,
    types: dict,
    measures: dict,
    group_by: list[str] | None = None,
    sort_by: str | None = None,
    sort: str = "desc",
    top_n: int | None = None,
    page_size: int = 20,
):
    df = data_frame
    if group_by:
        df = aggregate(df, group_by, {c: measures[c] for c in columns if c not in group_by})
    df = df[columns]
    if sort_by:
        df = df.sort_values(sort_by, ascending=(sort == "asc"))
    if top_n:
        df = df.head(top_n)
    df = df.copy()
    for c in columns:
        if types[c] == "date":
            df[c] = pd.to_datetime(df[c]).dt.strftime("%Y-%m-%d")
        if types[c] == "integer":
            df[c] = df[c].round(0)

    column_defs = []
    for c in columns:
        d = {"field": c, "headerName": labels[c]}
        if types[c] in CELL_TYPES:
            d["cellDataType"] = CELL_TYPES[types[c]]
        column_defs.append(d)
    # dash_ag_grid is itself a captured callable: build it, then call it to get the component.
    return dash_ag_grid(
        data_frame=df,
        columnDefs=column_defs,
        dashGridOptions={"pagination": True, "paginationPageSize": page_size},
    )()
