"""Compile validated specs into ONE Vizro Dashboard.

Each spec becomes a Vizro Page, grouped in navigation by domain. A page is one body Container whose
controls render as a **top filter bar**:

    [ Date range ][ View by: Month | Quarter | Year ][ Compare to: Previous period | Last year ][ filters... ]
    [ KPI ][ KPI ][ KPI ]
    [ chart              ][ chart ]

The time controls are Vizro Parameters that set `date_range`, `time_grain` and `compare` on every
component whose dataset declares a `time_field`; dropdown filters are Vizro Filters. Nothing here is
dashboard-specific: if a spec can't express something, extend the spec + this compiler.
"""

from __future__ import annotations

from functools import lru_cache

import pandas as pd
import vizro.models as vm
from vizro.actions import export_data

from rbc_bi.components.charts import rbc_chart
from rbc_bi.components.kpi import rbc_kpi
from rbc_bi.components.table import rbc_table
from rbc_bi.components.timebar import default_range
from rbc_bi.semantic.connectors import get_connector
from rbc_bi.spec.models import DashboardSpec, DatasetSpec, Filter, SemanticLayer
from rbc_bi.spec.validator import Project

GRID_COLUMNS = 12
ROW_UNIT_PX = 64  # one grid row
ROW_GAP_PX = 16
ROW_UNITS = {"kpi": 2, "chart": 6}  # KPI row 144px, chart row 464px

GRAIN_OPTIONS = [{"label": "Month", "value": "month"}, {"label": "Quarter", "value": "quarter"},
                 {"label": "Year", "value": "year"}]
COMPARE_OPTIONS = [{"label": "Previous period", "value": "previous_period"},
                   {"label": "Last year", "value": "previous_year"}, {"label": "Off", "value": "none"}]


def _measure(ds: DatasetSpec, name: str, agg_override: str | None = None) -> dict:
    f = ds.fields[name]
    agg = agg_override or f.default_agg()
    return {"column": name, "agg": agg, "ratio": list(f.ratio) if agg == "ratio" else None}


def _table_units(page_size: int, exportable: bool) -> int:
    px = 56 + 64 + page_size * 42 + 48 + (52 if exportable else 0)  # title, header, rows, pager, buttons
    return max(3, -(-px // (ROW_UNIT_PX + ROW_GAP_PX)))


@lru_cache(maxsize=None)
def _time_bounds(connector: str, sql: str, field: str):
    """(min, max) of a dataset's time field, for the date picker's limits and default range."""
    row = get_connector(connector).query(f"select min({field}) as lo, max({field}) as hi from ({sql}) as _q")
    return row["lo"].iloc[0].date(), row["hi"].iloc[0].date()


class PageCompiler:
    def __init__(self, spec: DashboardSpec, semantic: SemanticLayer):
        self.spec, self.semantic = spec, semantic
        self.time = spec.time
        # Targets for the time-bar parameters, filled while components are built.
        self.range_targets: list[str] = []
        self.grain_targets: list[str] = []
        self.compare_targets: list[str] = []
        self._range_value = None
        if self.time:
            bounds = [_time_bounds(d.connector, d.sql, d.time_field)
                      for d in {c.body.dataset: self.semantic.datasets[c.body.dataset]
                                for _, c in spec.components()}.values() if d.time_field]
            # Picker spans whole months, so default ranges are month-aligned and "previous period" is a
            # clean MoM / QoQ / YoY comparison.
            lo, hi = pd.Timestamp(min(b[0] for b in bounds)), pd.Timestamp(max(b[1] for b in bounds))
            self.lo = lo.to_period("M").start_time.date()
            self.hi = hi.to_period("M").end_time.normalize().date()
            self._range_value = default_range(self.time.default_range, self.lo, self.hi)

    def cid(self, r: int, c: int, suffix: str = "") -> str:
        return f"{self.spec.id}__r{r}c{c}{suffix}"

    def _time_args(self, cid: str, ds: DatasetSpec) -> dict:
        """date_range/time_field args for a component, registering it as a date-range target."""
        if not (self.time and ds.time_field):
            return {}
        self.range_targets.append(f"{cid}.date_range")
        return {"time_field": ds.time_field, "date_range": self._range_value}

    # ---- components -------------------------------------------------------------------------

    def kpi(self, r, c, k):
        ds = self.semantic.datasets[k.dataset]
        f = ds.fields[k.measure]
        counting = k.agg in ("count", "count_distinct")
        fmt = k.format or ("integer" if counting else f.default_format())
        cid = self.cid(r, c)
        extra = self._time_args(cid, ds)
        if extra:
            extra |= {"compare": self.time.compare, "time_grain": self.time.grain}
            self.compare_targets.append(f"{cid}.compare")
            self.grain_targets.append(f"{cid}.time_grain")
        return vm.Figure(
            id=cid,
            figure=rbc_kpi(
                data_frame=k.dataset,
                measure=k.measure,
                agg=_measure(ds, k.measure, k.agg),
                fmt=fmt,
                title=k.title,
                reference=k.reference,
                reference_agg=_measure(ds, k.reference) if k.reference else None,
                lower_is_better=k.lower_is_better,
                **extra,
            ),
        )

    def chart(self, r, c, ch):
        ds = self.semantic.datasets[ch.dataset]
        ys = [ch.y] if isinstance(ch.y, str) else list(ch.y)
        used = [ch.x, *ys, *(v for v in (ch.split_by, ch.detail) if v)]
        measures = {m: _measure(ds, m, ch.agg) for m in ys}
        if ch.type == "scatter":
            measures[ch.x] = _measure(ds, ch.x)
        counting = ch.agg in ("count", "count_distinct")
        formats = {m: ("integer" if counting and m in ys else ds.fields[m].default_format()) for m in measures}
        cid = self.cid(r, c)
        x_is_date = ds.fields[ch.x].type == "date"
        grain = ch.time_grain
        if self.time and x_is_date and not ch.time_grain:
            # Trend charts follow the "View by" switch unless the spec pins a grain.
            grain = self.time.grain
            self.grain_targets.append(f"{cid}.time_grain")
        return vm.Graph(
            id=cid,
            title=ch.title,
            description=vm.Tooltip(text=ch.description, icon="info") if ch.description else None,
            figure=rbc_chart(
                data_frame=ch.dataset,
                chart_type=ch.type,
                x=ch.x,
                y=ys,
                measures=measures,
                labels={f: ds.fields[f].label + (" (count)" if counting and f in ys else "") for f in used},
                formats=formats,
                split_by=ch.split_by,
                detail=ch.detail,
                time_grain=grain,
                x_is_date=x_is_date,
                sort=ch.sort,
                top_n=ch.top_n,
                horizontal=ch.horizontal,
                source=ch.dataset,  # full domain for stable series colours
                **self._time_args(cid, ds),
            ),
        )

    def table(self, r, c, t):
        ds = self.semantic.datasets[t.dataset]
        group = t.group_by or []
        cid = self.cid(r, c)
        table = vm.Table(
            id=cid,
            title=t.title or "",
            figure=rbc_table(
                data_frame=t.dataset,
                columns=t.columns,
                labels={col: ds.fields[col].label for col in t.columns},
                types={col: ds.fields[col].type for col in t.columns},
                measures={col: _measure(ds, col) for col in t.columns if col not in group},
                group_by=t.group_by,
                sort_by=t.sort_by,
                sort=t.sort,
                top_n=t.top_n,
                page_size=t.page_size,
                **self._time_args(cid, ds),
            ),
        )
        if not t.exportable:
            return table
        # Exports module: CSV + Excel of the *filtered* rows behind the table.
        buttons = vm.Container(
            layout=vm.Flex(direction="row", gap="8px"),
            components=[
                vm.Button(text="CSV", icon="download", variant="outlined",
                          actions=export_data(targets=[table.id], file_format="csv")),
                vm.Button(text="Excel", icon="download", variant="outlined",
                          actions=export_data(targets=[table.id], file_format="xlsx")),
            ],
        )
        return vm.Container(layout=vm.Flex(direction="column", gap="8px"), components=[table, buttons])

    def filter(self, f: Filter):
        # Label from a dataset used on THIS page (the validator guarantees one has the field).
        on_page = dict.fromkeys(comp.body.dataset for _, comp in self.spec.components())
        ds = next(self.semantic.datasets[n] for n in on_page if f.field in self.semantic.datasets[n].fields)
        title = f.title or ds.fields[f.field].label
        selector = {
            "multi_select": lambda: vm.Dropdown(multi=True, title=title),
            "single_select": lambda: vm.Dropdown(multi=False, title=title),
            "checklist": lambda: vm.Checklist(title=title),
            "date_range": lambda: vm.DatePicker(range=True, title=title),
            "range": lambda: vm.Slider(range=True, title=title),
        }[f.type]()
        return vm.Filter(column=f.field, selector=selector)

    def time_controls(self) -> list[vm.Parameter]:
        if not self.time or not self.range_targets:
            return []
        sid = self.spec.id
        controls = [vm.Parameter(
            id=f"{sid}__range",
            targets=self.range_targets,
            selector=vm.DatePicker(range=True, min=self.lo, max=self.hi, value=self._range_value, title="Date range"),
        )]
        if self.grain_targets:
            controls.append(vm.Parameter(
                id=f"{sid}__grain",
                targets=self.grain_targets,
                selector=vm.RadioItems(options=GRAIN_OPTIONS, value=self.time.grain, title="View by"),
            ))
        if self.compare_targets:
            controls.append(vm.Parameter(
                id=f"{sid}__compare",
                targets=self.compare_targets,
                selector=vm.RadioItems(options=COMPARE_OPTIONS, value=self.time.compare, title="Compare to"),
            ))
        return controls

    # ---- page -------------------------------------------------------------------------------

    def page(self) -> vm.Page:
        components, grid = [], []
        for r, row in enumerate(self.spec.layout):
            width = GRID_COLUMNS // len(row.row)
            units = 1
            idxs = []
            for c, comp in enumerate(row.row):
                components.append(getattr(self, comp.kind)(r, c, comp.body))
                idxs.append(len(components) - 1)
                if comp.kind == "table":
                    units = max(units, _table_units(comp.table.page_size, comp.table.exportable))
                else:
                    units = max(units, ROW_UNITS[comp.kind])
            line = [i for i in idxs for _ in range(width)]
            line += [-1] * (GRID_COLUMNS - len(line))
            grid += [line] * units
        s = self.spec
        controls = [*self.time_controls(), *(self.filter(f) for f in s.filters)]
        body = vm.Container(
            id=f"{s.id}__body",
            components=components,
            controls=controls,
            layout=vm.Grid(grid=grid, row_min_height=f"{ROW_UNIT_PX}px", row_gap=f"{ROW_GAP_PX}px",
                           col_gap=f"{ROW_GAP_PX}px"),
        )
        return vm.Page(
            id=s.id,
            path=s.id,
            title=s.title,
            description=vm.Tooltip(text=f"{s.description}\n\nOwner: {s.owner}", icon="info"),
            components=[body],
        )


def _catalog_page(project: Project) -> vm.Page:
    domains = project.platform.domains
    intro = vm.Text(
        text=(
            f"{len(project.dashboards)} dashboards, each one a YAML file in `dashboards/`. Specs are written by "
            "an AI agent, validated in CI and rendered by the framework, so they all look and behave the same. "
            "No AI runs inside this app."
        )
    )
    cards = []
    for s in sorted(project.dashboards, key=lambda s: (s.domain, s.title)):
        datasets = sorted({comp.body.dataset for _, comp in s.components()})
        cards.append(
            vm.Card(
                header=f"{domains.get(s.domain, s.domain).upper()}",
                text=f"#### {s.title}\n{s.description}",
                footer=f"`{s.id}.yaml` · {', '.join(datasets)}",
                href=f"/{s.id}",
            )
        )
    n_cols, card_rows = 3, 3  # intro takes one grid row, each card three (Vizro grid rows are equal height)
    grid = [[0] * n_cols]
    for i in range(0, len(cards), n_cols):
        grid += [[i + j + 1 if i + j < len(cards) else -1 for j in range(n_cols)]] * card_rows
    return vm.Page(
        id="catalog", path="/", title="Dashboard catalog", components=[intro, *cards],
        layout=vm.Grid(grid=grid, row_min_height="64px", row_gap="16px", col_gap="16px"),
    )


def _errors_page(project: Project) -> vm.Page:
    lines = "\n".join(f"- `{e.file}` `{e.path or '(file)'}`: {e.message}" for e in project.errors)
    skipped = ", ".join(f"`{f}`" for f in project.invalid_dashboard_files) or "none"
    return vm.Page(
        id="spec-errors",
        path="spec-errors",
        title=f"Spec errors ({len(project.errors)})",
        components=[vm.Text(text=(
            "### Some specs failed validation\n"
            f"These dashboards are not shown until they are fixed: {skipped}.\n\n"
            "Run `rbc-bi validate` to see the same messages in the terminal.\n\n" + lines
        ))],
    )


def build_dashboard(project: Project) -> vm.Dashboard:
    semantic = project.semantic
    pages = [_catalog_page(project)]
    nav: dict[str, list[str]] = {"Home": ["catalog"]}
    if project.errors:
        pages.append(_errors_page(project))
        nav["Home"].append("spec-errors")
    for domain, label in project.platform.domains.items():
        specs = sorted((s for s in project.dashboards if s.domain == domain), key=lambda s: s.title)
        for s in specs:
            pages.append(PageCompiler(s, semantic).page())
            nav.setdefault(label, []).append(s.id)
    return vm.Dashboard(
        title=project.platform.title,
        theme="vizro_light",
        pages=pages,
        navigation=vm.Navigation(pages=nav),
    )
