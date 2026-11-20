"""Load and validate every spec in the repo.

Errors are written for an agent to fix without human help: each names the file, the YAML path,
what is wrong and (where possible) a concrete fix, e.g.

    dashboards/sales-overview.yaml: layout[1].row[0].chart.y[1] 'proft' is not a field of
    dataset 'orders'. Did you mean 'profit'?
"""

from __future__ import annotations

import difflib
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, get_args

import yaml
from pydantic import BaseModel, ValidationError

from rbc_bi import paths
from rbc_bi.spec.models import (
    NUMERIC_TYPES,
    ConnectorsConfig,
    DashboardSpec,
    DatasetSpec,
    PlatformConfig,
    SemanticLayer,
)

# Keys that would let a spec restyle itself. All styling comes from framework/theme/.
STYLE_KEYS = {
    "color", "colour", "colors", "colours", "color_discrete_map", "color_discrete_sequence",
    "font", "fonts", "font_size", "css", "style", "styles", "class", "classname", "class_name",
    "theme", "template", "background", "background_color", "palette", "height", "width",
}
# Keys that would smuggle SQL or physical tables into a dashboard.
SQL_KEYS = {"sql", "query", "table_name", "from", "where", "join", "connector", "schema"}
SQL_SELECT_FROM = re.compile(r"\bselect\b[\s\S]+\bfrom\b", re.IGNORECASE)
# "Select a region from the filter" is English. It's SQL only with a structural signal as well:
# `select *`, `select distinct`, `from schema.table`, a trailing `;`, or a clause keyword after FROM.
SQL_SIGNALS = re.compile(
    r"\bselect\s+(\*|distinct\b)"
    r"|\bfrom\s+[\"\w]+\.[\"\w]+"
    r"|;\s*$"
    r"|\bfrom\b[\s\S]+\b(where|group\s+by|order\s+by|join|limit|having|union)\b",
    re.IGNORECASE,
)


def looks_like_sql(text: str) -> bool:
    return bool(SQL_SELECT_FROM.search(text) and SQL_SIGNALS.search(text))

# Common words agents reach for, mapped to the component they meant.
COMPONENT_SYNONYMS = {
    "graph": "chart", "plot": "chart", "figure": "chart", "visual": "chart",
    "metric": "kpi", "card": "kpi", "number": "kpi", "stat": "kpi", "kpi_card": "kpi",
    "grid": "table", "aggrid": "table", "ag_grid": "table", "datatable": "table",
}


@dataclass
class SpecError:
    file: str
    path: str
    message: str

    def __str__(self) -> str:
        return f"{self.file}: {self.path + ' ' if self.path else ''}{self.message}"


@dataclass
class Project:
    """Everything the compiler needs, plus every error found while loading it."""

    platform: PlatformConfig | None = None
    connectors: ConnectorsConfig | None = None
    semantic: SemanticLayer | None = None
    dashboards: list[DashboardSpec] = field(default_factory=list)
    errors: list[SpecError] = field(default_factory=list)
    invalid_dashboard_files: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


# --------------------------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------------------------


def _suggest(word: str, options) -> str | None:
    options = list(options)
    lowered = {o.lower(): o for o in options}
    if word.lower() in lowered:
        return lowered[word.lower()]
    match = difflib.get_close_matches(word, options, n=1, cutoff=0.6)
    return match[0] if match else None


def _hint(word: str, options, noun: str = "Available") -> str:
    s = _suggest(word, options)
    if s:
        return f" Did you mean '{s}'?"
    return f" {noun}: {', '.join(sorted(options))}."


def _fmt_loc(loc) -> str:
    out = ""
    for part in loc:
        if isinstance(part, int):
            out += f"[{part}]"
        else:
            out += f".{part}" if out else str(part)
    return out


def _clean_loc(loc) -> tuple:
    """Drop pydantic's union-branch tags (e.g. 'str', "literal['public']", 'AccessGroups')."""
    kept = []
    for p in loc:
        if isinstance(p, int):
            kept.append(p)
        elif p in {"str", "int", "float", "bool"} or "[" in p or p in _UNION_TAGS:
            continue
        else:
            kept.append(p)
    return tuple(kept)


_UNION_TAGS = {"AccessGroups", "function-after[_exactly_one(), Component]"}


def _first_model(annotation) -> type[BaseModel] | None:
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return annotation
    for arg in get_args(annotation):
        m = _first_model(arg)
        if m:
            return m
    return None


def _model_at(root: type[BaseModel], loc: tuple) -> type[BaseModel] | None:
    cur = root
    for part in loc:
        if isinstance(part, int):
            continue
        f = cur.model_fields.get(part)
        if f is None:
            return None
        cur = _first_model(f.annotation)
        if cur is None:
            return None
    return cur


def _pydantic_errors(file: str, exc: ValidationError, model: type[BaseModel]) -> list[SpecError]:
    errors, seen = [], set()
    for e in exc.errors():
        loc = _clean_loc(e["loc"])
        typ = e["type"]
        if typ == "extra_forbidden":
            key = loc[-1]
            parent = _model_at(model, loc[:-1])
            allowed = list(parent.model_fields) if parent else []
            if key in COMPONENT_SYNONYMS and "chart" in allowed:
                hint = f" Use '{COMPONENT_SYNONYMS[key]}' instead."
            else:
                hint = _hint(str(key), allowed, "Allowed keys") if allowed else ""
            msg = f"unknown key '{key}'.{hint}"
            path = _fmt_loc(loc)
        elif typ == "missing":
            msg = f"is required but missing."
            path = _fmt_loc(loc)
        elif typ == "literal_error":
            options = re.findall(r"'([^']*)'", e.get("ctx", {}).get("expected", ""))
            got = e.get("input")
            sug = _suggest(str(got), options) if options else None
            msg = f"{got!r} is not allowed. Use one of: {', '.join(options)}." + (f" Did you mean '{sug}'?" if sug else "")
            path = _fmt_loc(loc)
        else:
            msg = e["msg"].rstrip(".") + "."
            if msg.startswith("Value error, "):
                msg = msg[len("Value error, "):]
            path = _fmt_loc(loc)
        if path in seen:
            continue
        seen.add(path)
        errors.append(SpecError(file, path, msg))
    return errors


def _load_yaml(path: Path) -> tuple[Any, list[SpecError]]:
    file = paths.rel(path)
    try:
        with open(path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        where = f"line {mark.line + 1}, column {mark.column + 1}: " if mark else ""
        return None, [SpecError(file, "", f"invalid YAML ({where}{getattr(exc, 'problem', exc)}).")]
    if not isinstance(data, dict):
        return None, [SpecError(file, "", "must be a YAML mapping (key: value pairs) at the top level.")]
    return data, []


def _walk(obj, path=()):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield path + (k,), k, v
            yield from _walk(v, path + (k,))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield path + (i,), None, v
            yield from _walk(v, path + (i,))


def _expand_env(value: Any) -> Any:
    """Expand ${VAR} and ${VAR:-default} in config strings."""
    if not isinstance(value, str):
        return value
    return re.sub(
        r"\$\{(\w+)(?::-([^}]*))?\}", lambda m: os.environ.get(m.group(1), m.group(2) or ""), value
    )


# --------------------------------------------------------------------------------------------
# Config + semantic layer
# --------------------------------------------------------------------------------------------


def load_platform(root: Path) -> tuple[PlatformConfig | None, ConnectorsConfig | None, list[SpecError]]:
    errors: list[SpecError] = []
    platform = connectors = None
    data, errs = _load_yaml(root / "config" / "platform.yaml")
    errors += errs
    if data is not None:
        try:
            platform = PlatformConfig.model_validate(data)
        except ValidationError as exc:
            errors += _pydantic_errors("config/platform.yaml", exc, PlatformConfig)
    data, errs = _load_yaml(root / "config" / "connectors.yaml")
    errors += errs
    if data is not None:
        try:
            connectors = ConnectorsConfig.model_validate(data)
            for c in connectors.connectors.values():
                for k, v in list(c.__pydantic_extra__.items()):
                    c.__pydantic_extra__[k] = _expand_env(v)
        except ValidationError as exc:
            errors += _pydantic_errors("config/connectors.yaml", exc, ConnectorsConfig)
    return platform, connectors, errors


def check_semantic(semantic: SemanticLayer, connectors: ConnectorsConfig | None, file: str) -> list[SpecError]:
    errors = []
    for name, ds in semantic.datasets.items():
        base = f"datasets.{name}"
        if not re.fullmatch(r"[a-z][a-z0-9_]*", name):
            errors.append(SpecError(file, base, "dataset names must be snake_case (lowercase letters, digits, _)."))
        if connectors and ds.connector not in connectors.connectors:
            errors.append(SpecError(file, f"{base}.connector",
                                    f"'{ds.connector}' is not defined in config/connectors.yaml." + _hint(ds.connector, connectors.connectors)))
        if ds.time_field:
            tf = ds.fields.get(ds.time_field)
            if tf is None:
                errors.append(SpecError(file, f"{base}.time_field", f"'{ds.time_field}' is not a field of this dataset."
                                        + _hint(ds.time_field, ds.fields)))
            elif tf.type != "date":
                errors.append(SpecError(file, f"{base}.time_field", f"'{ds.time_field}' must be a date field (it is {tf.type})."))
        for g in ds.grain:
            if g not in ds.fields:
                errors.append(SpecError(file, f"{base}.grain", f"'{g}' is not a field of this dataset." + _hint(g, ds.fields)))
        for fname, f in ds.fields.items():
            if f.ratio:
                if f.type not in NUMERIC_TYPES:
                    errors.append(SpecError(file, f"{base}.fields.{fname}.ratio", "only numeric fields can be ratios."))
                for part in f.ratio:
                    if part not in ds.fields:
                        errors.append(SpecError(file, f"{base}.fields.{fname}.ratio",
                                                f"'{part}' is not a field of this dataset." + _hint(part, ds.fields)))
                    elif not ds.fields[part].is_numeric:
                        errors.append(SpecError(file, f"{base}.fields.{fname}.ratio", f"'{part}' must be numeric."))
            if f.agg and not f.is_numeric and f.agg not in ("count", "count_distinct", "min", "max"):
                errors.append(SpecError(file, f"{base}.fields.{fname}.agg",
                                        f"'{f.agg}' needs a numeric field; '{fname}' is {f.type}."))
    return errors


def check_semantic_sql(semantic: SemanticLayer, file: str) -> list[SpecError]:
    """Run each dataset's SQL with LIMIT 0 and check it returns exactly the declared fields."""
    from rbc_bi.semantic.connectors import get_connector

    errors = []
    for name, ds in semantic.datasets.items():
        try:
            cols = get_connector(ds.connector).columns(ds.sql)
        except Exception as exc:  # noqa: BLE001 - surface any driver error verbatim
            errors.append(SpecError(file, f"datasets.{name}.sql", f"query failed: {str(exc).splitlines()[0]}"))
            continue
        missing = [f for f in ds.fields if f not in cols]
        extra = [c for c in cols if c not in ds.fields]
        if missing:
            errors.append(SpecError(file, f"datasets.{name}.sql",
                                    f"query does not return declared field(s) {missing}. It returns {cols}."))
        if extra:
            errors.append(SpecError(file, f"datasets.{name}.fields",
                                    f"query returns column(s) {extra} that are not declared under fields. "
                                    f"Declare them (with type and label) or drop them from the SQL."))
    return errors


def load_semantic(root: Path, connectors: ConnectorsConfig | None) -> tuple[SemanticLayer | None, list[SpecError]]:
    path = root / "semantic" / "datasets.yaml"
    file = paths.rel(path)
    data, errors = _load_yaml(path)
    if data is None:
        return None, errors
    try:
        semantic = SemanticLayer.model_validate(data)
    except ValidationError as exc:
        return None, _pydantic_errors(file, exc, SemanticLayer)
    return semantic, check_semantic(semantic, connectors, file)


# --------------------------------------------------------------------------------------------
# Dashboards
# --------------------------------------------------------------------------------------------


def _governance_checks(raw: dict, file: str) -> tuple[list[SpecError], list[tuple]]:
    """Return (errors, locations of banned keys) so callers can strip them and keep validating."""
    errors, banned = [], []
    for loc, key, value in _walk(raw):
        if isinstance(key, str) and key.lower() in STYLE_KEYS:
            errors.append(SpecError(file, _fmt_loc(loc),
                                    f"style key '{key}' is not allowed in a dashboard spec. All styling comes from "
                                    f"framework/theme/. Remove it (use `split_by` to colour series by a field)."))
            banned.append(loc)
        elif isinstance(key, str) and key.lower() in SQL_KEYS:
            errors.append(SpecError(file, _fmt_loc(loc),
                                    f"'{key}' is not allowed: dashboards never contain SQL, connectors or physical "
                                    f"tables. Reference a dataset from semantic/datasets.yaml (add one with the "
                                    f"add-dataset skill)."))
            banned.append(loc)
        elif isinstance(value, str) and looks_like_sql(value):
            errors.append(SpecError(file, _fmt_loc(loc),
                                    "looks like SQL. Dashboards never contain SQL; put it in a dataset in "
                                    "semantic/datasets.yaml and reference the dataset by name."))
    return errors, banned


def _without(raw: dict, locs: list[tuple]) -> dict:
    """Deep copy of raw with the given key paths removed."""
    import copy

    out = copy.deepcopy(raw)
    for loc in sorted(locs, key=len, reverse=True):
        node = out
        try:
            for part in loc[:-1]:
                node = node[part]
            node.pop(loc[-1], None)
        except (KeyError, IndexError, TypeError, AttributeError):
            pass
    return out


class _Ctx:
    def __init__(self, file: str, semantic: SemanticLayer):
        self.file, self.semantic, self.errors = file, semantic, []

    def err(self, path: str, msg: str):
        self.errors.append(SpecError(self.file, path, msg))

    def dataset(self, path: str, name: str) -> DatasetSpec | None:
        ds = self.semantic.datasets.get(name)
        if ds is None:
            extra = " That looks like a physical table; dashboards use dataset names." if "." in name else ""
            self.err(f"{path}.dataset", f"'{name}' is not a dataset in semantic/datasets.yaml.{extra}"
                     + _hint(name, self.semantic.datasets, "Available datasets"))
        return ds

    def field(self, path: str, ds_name: str, ds: DatasetSpec, name: str, *, kind: str | None = None):
        f = ds.fields.get(name)
        if f is None:
            self.err(path, f"'{name}' is not a field of dataset '{ds_name}'." + _hint(name, ds.fields, "Available fields"))
            return None
        if kind == "measure" and not f.is_numeric:
            measures = [k for k, v in ds.fields.items() if v.is_numeric]
            self.err(path, f"'{name}' is a {f.type} field, but a measure (numeric field) is needed here. "
                           f"Measures in '{ds_name}': {', '.join(measures)}. (To count rows use agg: count_distinct.)")
            return None
        if kind == "dimension" and f.is_numeric:
            dims = [k for k, v in ds.fields.items() if not v.is_numeric]
            self.err(path, f"'{name}' is a measure, but a dimension (string or date field) is needed here. "
                           f"Dimensions in '{ds_name}': {', '.join(dims)}.")
            return None
        return f


FORMATS_BY_TYPE = {
    "currency": {"currency", "number"},
    "percent": {"percent"},
    "integer": {"integer", "number"},
    "number": {"number", "integer"},
}


def check_dashboard(spec: DashboardSpec, file: str, semantic: SemanticLayer, platform: PlatformConfig | None,
                    stem: str) -> list[SpecError]:
    c = _Ctx(file, semantic)
    if spec.id != stem:
        c.err("id", f"'{spec.id}' must match the filename '{stem}.yaml'. Rename the file or change the id.")
    if platform and spec.domain not in platform.domains:
        c.err("domain", f"'{spec.domain}' is not a domain in config/platform.yaml." + _hint(spec.domain, platform.domains, "Domains"))

    used: dict[str, DatasetSpec] = {}
    for path, comp in spec.components():
        body = comp.body
        ds = c.dataset(path, body.dataset)
        if ds is None:
            continue
        used[body.dataset] = ds
        dn = body.dataset

        if comp.kind == "kpi":
            counting = body.agg in ("count", "count_distinct")
            f = c.field(f"{path}.measure", dn, ds, body.measure, kind=None if counting else "measure")
            if f is not None:
                agg = body.agg or f.default_agg()
                if agg == "ratio" and not f.ratio:
                    c.err(f"{path}.agg", f"agg 'ratio' needs a ratio field; '{body.measure}' has no `ratio` in the semantic layer.")
                fmt_type = "integer" if counting else f.type
                if body.format and body.format not in FORMATS_BY_TYPE.get(fmt_type, {body.format}):
                    c.err(f"{path}.format", f"format '{body.format}' does not match {fmt_type} field '{body.measure}'. "
                                            f"Use one of: {', '.join(sorted(FORMATS_BY_TYPE[fmt_type]))} (or omit it).")
            if body.reference:
                c.field(f"{path}.reference", dn, ds, body.reference, kind="measure")

        elif comp.kind == "chart":
            ys = [body.y] if isinstance(body.y, str) else body.y
            counting = body.agg in ("count", "count_distinct")
            for i, y in enumerate(ys):
                yp = f"{path}.y" if isinstance(body.y, str) else f"{path}.y[{i}]"
                c.field(yp, dn, ds, y, kind=None if counting else "measure")
            if body.type == "scatter":
                c.field(f"{path}.x", dn, ds, body.x, kind="measure")
                if body.detail:
                    c.field(f"{path}.detail", dn, ds, body.detail, kind="dimension")
            else:
                xf = c.field(f"{path}.x", dn, ds, body.x, kind="dimension")
                if body.detail:
                    c.err(f"{path}.detail", "`detail` is only for scatter charts. Remove it.")
                if xf is not None and body.time_grain and xf.type != "date":
                    c.err(f"{path}.time_grain", f"time_grain needs a date x field; '{body.x}' is {xf.type}.")
            if body.split_by:
                c.field(f"{path}.split_by", dn, ds, body.split_by, kind="dimension")
                if len(ys) > 1:
                    c.err(f"{path}.split_by", "use either several y measures or split_by, not both. "
                                              "Make two charts, or keep one y.")
            if body.type == "donut" and (len(ys) > 1 or body.split_by):
                c.err(f"{path}", "a donut takes one y measure and no split_by.")
            if body.type == "stacked_bar" and not body.split_by and len(ys) < 2:
                c.err(f"{path}.split_by", "stacked_bar needs split_by (or 2+ y measures) to have something to stack. "
                                          "Use type: bar for a single series.")
            if body.type in ("line", "area") and (body.sort or body.top_n):
                c.err(f"{path}", "sort and top_n are for bar/donut charts; line and area charts are ordered by x.")
            if body.horizontal and body.type not in ("bar", "stacked_bar"):
                c.err(f"{path}.horizontal", "horizontal is only for bar and stacked_bar charts.")
            if body.agg == "ratio":
                for y in ys:
                    if y in ds.fields and not ds.fields[y].ratio:
                        c.err(f"{path}.agg", f"agg 'ratio' needs a ratio field; '{y}' has no `ratio` in the semantic layer.")

        elif comp.kind == "table":
            for i, col in enumerate(body.columns):
                c.field(f"{path}.columns[{i}]", dn, ds, col)
            if body.group_by:
                for i, g in enumerate(body.group_by):
                    c.field(f"{path}.group_by[{i}]", dn, ds, g, kind="dimension")
                for i, col in enumerate(body.columns):
                    f = ds.fields.get(col)
                    if f is not None and not f.is_numeric and col not in body.group_by:
                        c.err(f"{path}.columns[{i}]", f"'{col}' is a dimension but not in group_by. "
                                                      f"Add it to group_by or remove it from columns.")
            if body.sort_by and body.sort_by not in body.columns:
                c.err(f"{path}.sort_by", f"'{body.sort_by}' must be one of the table's columns." + _hint(body.sort_by, body.columns, "Columns"))

    if spec.time:
        timed = [n for n, d in used.items() if d.time_field]
        if not timed:
            c.err("time", "no dataset on this page has a `time_field`, so the time bar would do nothing. "
                          "Remove `time`, or set time_field on the dataset in semantic/datasets.yaml.")
    time_fields = {d.time_field for d in used.values() if d.time_field}
    for i, flt in enumerate(spec.filters):
        p = f"filters[{i}]"
        if spec.time and flt.field in time_fields:
            c.err(f"{p}.field", f"'{flt.field}' is controlled by the time bar (`time:`). Remove this filter and set "
                                f"`time.default_range` instead.")
            continue
        owners = {n: d for n, d in used.items() if flt.field in d.fields}
        if not owners:
            all_fields = {f for d in used.values() for f in d.fields}
            c.err(f"{p}.field", f"'{flt.field}' is not a field of any dataset used on this page ({', '.join(used) or 'none'})."
                  + _hint(flt.field, all_fields, "Available fields"))
            continue
        ftypes = {d.fields[flt.field].type for d in owners.values()}
        if len(ftypes) > 1:
            kinds = ", ".join(f"{n}: {d.fields[flt.field].type}" for n, d in owners.items())
            c.err(f"{p}.field", f"'{flt.field}' has different types in the datasets on this page ({kinds}). "
                                f"Make the types match in semantic/datasets.yaml.")
            continue
        ftype = ftypes.pop()
        need = {"date_range": {"date"}, "range": NUMERIC_TYPES}.get(flt.type, {"string"})
        if ftype not in need:
            fix = "date_range" if ftype == "date" else "range" if ftype in NUMERIC_TYPES else "multi_select"
            c.err(f"{p}.type", f"filter type '{flt.type}' does not fit {ftype} field '{flt.field}'. Use '{fix}'.")
    return c.errors


def load_dashboard(path: Path, semantic: SemanticLayer | None, platform: PlatformConfig | None
                   ) -> tuple[DashboardSpec | None, list[SpecError]]:
    file = paths.rel(path)
    raw, errors = _load_yaml(path)
    if raw is None:
        return None, errors
    # Report every problem in one run: governance errors first, then structure, then references.
    errors, banned = _governance_checks(raw, file)
    try:
        spec = DashboardSpec.model_validate(_without(raw, banned))
    except ValidationError as exc:
        return None, errors + _pydantic_errors(file, exc, DashboardSpec)
    if semantic is not None:
        errors += check_dashboard(spec, file, semantic, platform, path.stem)
    return (spec if not errors else None), errors


def load_project(root: Path | None = None, *, check_sql: bool = False, only: list[Path] | None = None) -> Project:
    """Load config, semantic layer and dashboards. Never raises on spec errors; collects them."""
    root = Path(root or paths.ROOT)
    proj = Project()
    proj.platform, proj.connectors, errs = load_platform(root)
    proj.errors += errs
    proj.semantic, errs = load_semantic(root, proj.connectors)
    proj.errors += errs
    if proj.semantic and check_sql and not errs:
        proj.errors += check_semantic_sql(proj.semantic, "semantic/datasets.yaml")

    files = sorted(only) if only else sorted((root / "dashboards").glob("*.y*ml"))
    ids: dict[str, str] = {}
    for f in files:
        spec, errs = load_dashboard(Path(f), proj.semantic, proj.platform)
        if errs:
            proj.errors += errs
            proj.invalid_dashboard_files.append(paths.rel(f))
            continue
        if spec.id in ids:
            proj.errors.append(SpecError(paths.rel(f), "id", f"'{spec.id}' is already used by {ids[spec.id]}."))
            proj.invalid_dashboard_files.append(paths.rel(f))
            continue
        ids[spec.id] = paths.rel(f)
        proj.dashboards.append(spec)
    return proj
