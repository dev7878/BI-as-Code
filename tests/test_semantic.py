"""Semantic layer: aggregation maths and connector behaviour."""

import pandas as pd
import pytest

from rbc_bi.components.aggregate import aggregate, aggregate_scalar
from rbc_bi.semantic.connectors import DatabricksConnector, get_connector
from rbc_bi.semantic.resolver import load_dataset
from rbc_bi.spec.validator import load_project


def test_ratio_is_sum_over_sum_not_mean_of_ratios():
    df = pd.DataFrame({"g": ["a", "a"], "profit": [10.0, 0.0], "sales": [10.0, 90.0]})
    m = {"agg": "ratio", "ratio": ["profit", "sales"], "column": "margin"}
    assert aggregate_scalar(df, m) == pytest.approx(0.10)  # mean of row ratios would be 0.5
    out = aggregate(df, ["g"], {"margin": m})
    assert out.loc[0, "margin"] == pytest.approx(0.10)


def test_count_distinct():
    df = pd.DataFrame({"order_id": ["x", "x", "y"]})
    assert aggregate_scalar(df, {"agg": "count_distinct", "ratio": None}, "order_id") == 2


def test_dataset_loads_with_semantic_types():
    proj = load_project()
    df = load_dataset("orders", proj.semantic.datasets["orders"])
    assert len(df) == 9994
    assert pd.api.types.is_datetime64_any_dtype(df["order_date"])
    assert df["sales"].sum() == pytest.approx(2297200.86, rel=1e-6)


def test_connector_is_read_only():
    with pytest.raises(Exception):
        get_connector("warehouse").query("create table x as select 1")


def test_stub_connector_explains_itself():
    with pytest.raises(NotImplementedError, match="databricks-sql-connector"):
        DatabricksConnector("lake").query("select 1")
