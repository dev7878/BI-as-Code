"""Pydantic models for every spec format: dashboards, the semantic layer and platform config.

These models are the contract between the agent and the framework. Keep them small and
opinionated: fewer options mean more consistent agent output. Every field has a description,
which flows into the exported JSON Schema (IDE autocomplete and agent context).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

# --------------------------------------------------------------------------------------------
# Shared vocabularies
# --------------------------------------------------------------------------------------------

FieldType = Literal["date", "string", "integer", "number", "currency", "percent"]
NUMERIC_TYPES = {"integer", "number", "currency", "percent"}
DIMENSION_TYPES = {"date", "string"}

Agg = Literal["sum", "mean", "median", "min", "max", "count", "count_distinct", "ratio"]
Format = Literal["currency", "percent", "number", "integer"]
ChartType = Literal["line", "bar", "stacked_bar", "area", "scatter", "donut"]
FilterType = Literal["multi_select", "single_select", "checklist", "date_range", "range"]
TimeGrain = Literal["day", "week", "month", "quarter", "year"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --------------------------------------------------------------------------------------------
# Semantic layer (semantic/datasets.yaml)
# --------------------------------------------------------------------------------------------


class FieldSpec(Strict):
    type: FieldType = Field(description="Data type. Numeric types are measures; date and string are dimensions.")
    label: str = Field(description="Human label used in axes, legends, table headers and filters.")
    description: str | None = Field(None, description="What the field means. Agents read this.")
    agg: Literal["sum", "mean", "median", "min", "max", "count", "count_distinct"] | None = Field(
        None, description="Default aggregation when rolled up. Defaults to sum (mean for percent)."
    )
    ratio: tuple[str, str] | None = Field(
        None, description="[numerator, denominator]: aggregate as sum(numerator) / sum(denominator)."
    )

    @property
    def is_numeric(self) -> bool:
        return self.type in NUMERIC_TYPES

    def default_agg(self) -> str:
        if self.ratio:
            return "ratio"
        if self.agg:
            return self.agg
        if self.type == "percent":
            return "mean"
        return "sum" if self.is_numeric else "count"

    def default_format(self) -> str:
        return {"currency": "currency", "percent": "percent", "integer": "integer"}.get(self.type, "number")


class DatasetSpec(Strict):
    description: str = Field(description="What one row is and what the dataset is for.")
    connector: str = Field("warehouse", description="Connector name from config/connectors.yaml.")
    refresh: Literal["realtime", "hourly", "daily"] = Field("daily", description="Cache TTL for query results.")
    grain: list[str] = Field(description="Fields that uniquely identify a row.")
    sql: str = Field(description="SQL against the connector. Must return every field listed in `fields`.")
    fields: dict[str, FieldSpec]


class SemanticLayer(Strict):
    datasets: dict[str, DatasetSpec]


# --------------------------------------------------------------------------------------------
# Platform + connectors config (config/*.yaml)
# --------------------------------------------------------------------------------------------


class PlatformConfig(Strict):
    title: str = "Insights"
    domains: dict[str, str] = Field(description="domain id -> navigation label")
    export_row_cap: int = 1_000_000


class ConnectorConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    type: str


class ConnectorsConfig(Strict):
    connectors: dict[str, ConnectorConfig]


# --------------------------------------------------------------------------------------------
# Dashboard spec (dashboards/<id>.yaml)
# --------------------------------------------------------------------------------------------


class Kpi(Strict):
    """A single headline number."""

    dataset: str = Field(description="Dataset name from semantic/datasets.yaml.")
    measure: str = Field(description="Field to aggregate. Numeric, unless agg is count or count_distinct.")
    agg: Agg | None = Field(None, description="Aggregation. Defaults to the field's default aggregation.")
    format: Format | None = Field(None, description="Number format. Defaults from the field type.")
    title: str = Field(description="Card title, e.g. 'Total sales'.")
    reference: str | None = Field(
        None, description="Optional measure to compare against (e.g. a target). Shows the delta in a footer."
    )
    lower_is_better: bool = Field(False, description="Flip the good/bad signal of the delta (e.g. costs).")


class Chart(Strict):
    """A chart from the approved set. Data is aggregated by the framework: give fields, not numbers."""

    type: ChartType = Field(description="line | bar | stacked_bar | area | scatter | donut")
    dataset: str = Field(description="Dataset name from semantic/datasets.yaml.")
    x: str = Field(description="Category or date field (for scatter: a measure). For donut: the slice names.")
    y: str | list[str] = Field(description="Measure(s) to plot. Several measures only without split_by.")
    split_by: str | None = Field(None, description="Dimension that splits the data into series (legend).")
    detail: str | None = Field(None, description="Scatter only: one point per value of this dimension.")
    agg: Agg | None = Field(None, description="Override the measure's default aggregation.")
    time_grain: TimeGrain | None = Field(None, description="Bucket a date x axis. Defaults to month for dates.")
    sort: Literal["asc", "desc"] | None = Field(None, description="Sort bars by value.")
    top_n: int | None = Field(None, ge=1, le=100, description="Keep only the top N categories by value.")
    horizontal: bool = Field(False, description="Bars only: draw horizontal bars (good for long labels).")
    title: str = Field(description="Chart title. Required: it is also the accessible name.")
    description: str | None = Field(None, description="One sentence on how to read the chart (tooltip + a11y).")


class Table(Strict):
    """A detail or summary table (AG Grid). With group_by it aggregates; without it shows rows."""

    dataset: str = Field(description="Dataset name from semantic/datasets.yaml.")
    columns: list[str] = Field(min_length=1, description="Fields to show, in order.")
    group_by: list[str] | None = Field(
        None, description="Aggregate to this grain. Numeric columns are rolled up with their default agg."
    )
    sort_by: str | None = Field(None, description="Column to sort by.")
    sort: Literal["asc", "desc"] = "desc"
    top_n: int | None = Field(None, ge=1, le=10000, description="Keep only the first N rows after sorting.")
    title: str | None = None
    exportable: bool = Field(False, description="Add CSV and Excel download buttons (exports filtered data).")
    page_size: int = Field(20, ge=5, le=200)


class Component(Strict):
    """Exactly one of kpi, chart or table."""

    kpi: Kpi | None = None
    chart: Chart | None = None
    table: Table | None = None

    @model_validator(mode="after")
    def _exactly_one(self) -> "Component":
        set_ = [k for k in ("kpi", "chart", "table") if getattr(self, k) is not None]
        if len(set_) != 1:
            raise ValueError(f"each layout item must have exactly one of kpi, chart or table (found {set_ or 'none'})")
        return self

    @property
    def kind(self) -> str:
        return next(k for k in ("kpi", "chart", "table") if getattr(self, k) is not None)

    @property
    def body(self) -> Kpi | Chart | Table:
        return getattr(self, self.kind)


class Row(Strict):
    row: list[Component] = Field(min_length=1, max_length=4, description="1 to 4 components, equal width.")


class Filter(Strict):
    field: str = Field(description="Field to filter on. Applies to every component whose dataset has it.")
    type: FilterType = Field(description="multi_select | single_select | checklist (strings), date_range (dates), range (numbers)")
    title: str | None = Field(None, description="Label. Defaults to the field label.")


class AccessGroups(Strict):
    groups: list[str] = Field(min_length=1)


class DashboardSpec(Strict):
    id: str = Field(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$", description="kebab-case, unique, matches the filename.")
    title: str
    description: str = Field(description="Who it is for and what question it answers.")
    owner: str = Field(description="Owning team or distribution list.")
    domain: str = Field(description="Navigation group; one of the domains in config/platform.yaml.")
    access: Literal["public"] | AccessGroups = Field(
        "public", description="Recorded for governance. Not enforced in the prototype."
    )
    tags: list[str] = []
    filters: list[Filter] = Field([], description="Page-level filters, applied to every component.")
    layout: list[Row] = Field(min_length=1, description="Rows of components; the framework sizes and spaces them.")

    def components(self):
        """Yield (yaml_path, Component) for every component."""
        for r, row in enumerate(self.layout):
            for c, comp in enumerate(row.row):
                yield f"layout[{r}].row[{c}].{comp.kind}", comp
