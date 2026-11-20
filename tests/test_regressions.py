"""Regression tests for the bugs found in the first code review. One test (or more) per finding."""

import os
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest
import yaml

from rbc_bi import paths
from rbc_bi.components.charts import category_order, colour_map, rbc_chart
from rbc_bi.compiler.compiler import PageCompiler
from rbc_bi.modules.cache import TTL, make_cache
from rbc_bi.spec.models import DashboardSpec, DatasetSpec, FieldSpec
from rbc_bi.spec.validator import load_dashboard, load_project, looks_like_sql

SUM = {"agg": "sum", "ratio": None}
MARGIN = {"agg": "ratio", "ratio": ["profit", "sales"]}


@pytest.fixture(scope="module")
def project():
    return load_project()


def _errors(tmp_path, project, spec, name="t-dash"):
    p = tmp_path / f"{name}.yaml"
    p.write_text(yaml.safe_dump(spec, sort_keys=False), encoding="utf-8")
    return [str(e) for e in load_dashboard(p, project.semantic, project.platform)[1]]


def _spec(chart_kwargs=None, **top):
    chart = {"type": "bar", "dataset": "orders", "x": "region", "y": "sales", "title": "C"}
    chart.update(chart_kwargs or {})
    spec = {"id": "t-dash", "title": "T", "description": "D.", "owner": "o", "domain": "sales",
            "layout": [{"row": [{"chart": chart}]}]}
    spec.update(top)
    return spec


# 1. realtime must not mean "cache forever" (Flask-Caching: timeout 0 == never expire)
def test_every_refresh_ttl_expires():
    assert all(v > 0 for v in TTL.values())


def test_realtime_entry_expires(monkeypatch):
    import time

    from flask import Flask

    cache = make_cache()
    cache.init_app(Flask(__name__))
    cache.set("k", 1, timeout=TTL["realtime"])
    time.sleep(TTL["realtime"] + 0.2)
    assert cache.get("k") is None


# 2. Plain English with "select ... from" is not SQL; real SQL still is.
@pytest.mark.parametrize("text", [
    "Select a region from the filter to compare targets.",
    "Selected products from the West region",
    "select the top customers from each segment",
])
def test_english_is_not_sql(text):
    assert not looks_like_sql(text)


@pytest.mark.parametrize("text", [
    "select * from orders",
    "select sales from retail.orders",
    "SELECT region, sum(sales) FROM orders GROUP BY region",
    "select a from b where c = 1",
    "select distinct region from orders",
])
def test_real_sql_is_sql(text):
    assert looks_like_sql(text)


def test_english_description_validates(tmp_path, project):
    assert _errors(tmp_path, project, _spec(description="Select a region from the filter to compare.")) == []


# 3. Colours follow the entity, not its rank among the filtered values.
def test_colour_map_is_stable_under_filtering():
    palette = ["c1", "c2", "c3"]
    full = colour_map(["Furniture", "Office Supplies", "Technology"], palette)
    assert full == {"Furniture": "c1", "Office Supplies": "c2", "Technology": "c3"}


def test_colour_map_never_cycles():
    m = colour_map(list("abcd"), ["c1", "c2"])
    assert m["c"] == m["d"] != "c1"


def test_filtered_chart_keeps_series_colours():
    df = pd.DataFrame({"region": ["E", "W", "E", "W"], "seg": ["A", "B", "C", "C"], "sales": [1.0, 2.0, 3.0, 4.0]})
    kw = dict(chart_type="bar", x="region", y=["sales"], measures={"sales": SUM},
              labels={"region": "Region", "seg": "Segment", "sales": "Sales"},
              formats={"sales": "currency"}, split_by="seg")

    def colours(frame):
        fig = rbc_chart(data_frame=frame, **kw)  # a real DataFrame runs the captured function directly
        return {t.name: t.marker.color for t in fig.data}

    full = colours(df)
    # Filter out segment A. With the domain read from the full dataset (as `source` does in the app),
    # B and C must keep their colours.
    from rbc_bi.components import charts

    orig = charts._domain
    charts._domain = lambda source, column, fallback: df[column].unique().tolist()
    try:
        filtered = colours(df[df["seg"] != "A"])
    finally:
        charts._domain = orig
    assert filtered["B"] == full["B"] and filtered["C"] == full["C"]


# 4. top_n keeps the N largest whatever the sort direction.
def test_top_n_with_ascending_sort_keeps_largest():
    df = pd.DataFrame({"x": list("abcde"), "y": [5.0, 1.0, 4.0, 2.0, 3.0]})
    assert category_order(df, "x", "y", SUM, 2, "asc") == ["c", "a"]
    assert category_order(df, "x", "y", SUM, 2, "desc") == ["a", "c"]
    assert category_order(df, "x", "y", SUM, None, "asc") == ["b", "d", "e", "c", "a"]


# 9. Ranking uses the measure's own aggregation (ratio = sum/sum, not a sum of ratios).
def test_ratio_ranking_uses_true_ratio():
    df = pd.DataFrame({
        "x": ["a", "a", "a", "b"],
        "profit": [1.0, 1.0, 1.0, 50.0],
        "sales": [10.0, 10.0, 10.0, 100.0],
    })
    # a: 3/30 = 10%; b: 50/100 = 50%. Summing per-row ratios would make a = 30%... still lower, so add rows:
    df = pd.concat([df] * 1 + [pd.DataFrame({"x": ["a"] * 6, "profit": [1.0] * 6, "sales": [10.0] * 6})])
    # a = 9/90 = 10% (sum of row ratios = 90%), b = 50%
    assert category_order(df, "x", "margin", {**MARGIN, "column": "margin"}, 1, "desc") == ["b"]


# 5 + 10. The app never holds the warehouse open, so it can be rebuilt while running.
def test_connector_does_not_hold_file_open(tmp_path):
    import duckdb

    from rbc_bi.semantic.connectors import DuckDBConnector

    db = tmp_path / "w.duckdb"
    duckdb.connect(str(db)).execute("create table t as select 1 as a").close()
    con = DuckDBConnector("x", path=str(db))
    assert con.query("select a from t").iloc[0, 0] == 1
    replacement = tmp_path / "new.duckdb"
    duckdb.connect(str(replacement)).execute("create table t as select 2 as a").close()
    os.replace(replacement, db)  # fails on Windows if the connector kept the file open
    assert con.query("select a from t").iloc[0, 0] == 2


# 6. The project root is found from the working directory, not from where the package is installed.
def test_root_found_from_cwd(tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "platform.yaml").write_text("domains: {}\n", encoding="utf-8")
    sub = tmp_path / "dashboards"
    sub.mkdir()
    env = {k: v for k, v in os.environ.items() if k != "RBC_BI_ROOT"}
    out = subprocess.run([sys.executable, "-c", "from rbc_bi import paths; print(paths.ROOT)"],
                         cwd=sub, env=env, capture_output=True, text=True, check=True).stdout.strip()
    assert Path(out).resolve() == tmp_path.resolve()


def test_package_files_resolve_from_package():
    assert (paths.THEME_DIR / "tokens.yaml").is_file()
    assert paths.SCHEMA_PATH.parent == paths.PACKAGE_DIR / "spec"


# 7. Style/SQL errors don't hide other errors in the same spec.
def test_all_errors_reported_in_one_run(tmp_path, project):
    errs = _errors(tmp_path, project, _spec({"color": "red", "y": "proft"}))
    assert any("style key 'color'" in e for e in errs)
    assert any("Did you mean 'profit'?" in e for e in errs)


# 8. Filter labels and type checks only consider datasets on the page.
def test_filter_label_comes_from_page_dataset(project):
    sem = project.semantic.model_copy(deep=True)
    other = DatasetSpec(description="x", grain=["region"], sql="select 1",
                        fields={"region": FieldSpec(type="string", label="Sales territory")})
    sem.datasets = {"aaa_other": other, **sem.datasets}  # earlier in the file than `orders`
    spec = DashboardSpec.model_validate(_spec(filters=[{"field": "region", "type": "multi_select"}]))
    flt = PageCompiler(spec, sem).filter(spec.filters[0])
    assert flt.selector.title == "Region"


def test_filter_field_type_conflict_is_reported(tmp_path, project):
    sem = project.semantic.model_copy(deep=True)
    sem.datasets["sales_vs_target"].fields["region"] = FieldSpec(type="integer", label="Region")
    spec = _spec(filters=[{"field": "region", "type": "multi_select"}])
    spec["layout"].append({"row": [{"kpi": {"dataset": "sales_vs_target", "measure": "sales", "title": "S"}}]})
    p = tmp_path / "t-dash.yaml"
    p.write_text(yaml.safe_dump(spec, sort_keys=False), encoding="utf-8")
    errs = [str(e) for e in load_dashboard(p, sem, project.platform)[1]]
    assert any("different types in the datasets on this page" in e for e in errs)
