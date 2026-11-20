"""Time bar: ranges, comparison windows, KPI deltas, validation rules and compiled controls."""

from datetime import date

import pandas as pd
import pytest
import vizro.models as vm
import yaml
from vizro.managers import model_manager

from rbc_bi.components.kpi import _delta, rbc_kpi
from rbc_bi.components.timebar import comparison_range, default_range, in_range, parse_range
from rbc_bi.spec.validator import load_dashboard, load_project

T = pd.Timestamp


def test_parse_range_accepts_strings_and_orders_them():
    assert parse_range(["2025-03-31", "2025-01-01"]) == (T("2025-01-01"), T("2025-03-31"))
    assert parse_range(None) is None and parse_range([None, None]) is None


def test_in_range_is_inclusive_of_end_day():
    df = pd.DataFrame({"d": pd.to_datetime(["2025-01-01", "2025-01-31 18:00", "2025-02-01"], format="mixed")})
    assert len(in_range(df, "d", (T("2025-01-01"), T("2025-01-31")))) == 2


@pytest.mark.parametrize("rng, compare, expected", [
    # month-aligned windows shift by whole months: MoM, QoQ, and a 12-month window
    (("2025-03-01", "2025-03-31"), "previous_period", ("2025-02-01", "2025-02-28")),
    (("2025-04-01", "2025-06-30"), "previous_period", ("2025-01-01", "2025-03-31")),
    (("2025-01-01", "2025-12-31"), "previous_period", ("2024-01-01", "2024-12-31")),
    # YoY
    (("2025-04-01", "2025-06-30"), "previous_year", ("2024-04-01", "2024-06-30")),
    # arbitrary days: same length immediately before
    (("2025-01-11", "2025-01-20"), "previous_period", ("2025-01-01", "2025-01-10")),
])
def test_comparison_range(rng, compare, expected):
    got = comparison_range((T(rng[0]), T(rng[1])), compare)
    assert got == (T(expected[0]), T(expected[1]))


def test_no_comparison_when_off():
    assert comparison_range((T("2025-01-01"), T("2025-01-31")), "none") is None


@pytest.mark.parametrize("name, expected", [
    ("last_12_months", [date(2025, 1, 1), date(2025, 12, 31)]),
    ("year_to_date", [date(2025, 1, 1), date(2025, 12, 31)]),
    ("last_quarter", [date(2025, 10, 1), date(2025, 12, 31)]),
    ("last_month", [date(2025, 12, 1), date(2025, 12, 31)]),
    ("all", [date(2022, 1, 1), date(2025, 12, 31)]),
])
def test_default_range_is_relative_to_latest_data(name, expected):
    assert default_range(name, date(2022, 1, 1), date(2025, 12, 31)) == expected


def test_delta_relative_and_percentage_points():
    assert _delta(120.0, 100.0, "currency", False) == ("20.0%", "good", "▲")
    assert _delta(80.0, 100.0, "currency", True) == ("20.0%", "good", "▼")  # lower is better
    assert _delta(0.12, 0.15, "percent", False)[0] == "3.0 pts"
    assert _delta(1.0, 0.0, "currency", False) is None  # no baseline


def _texts(component) -> str:
    """All text inside a Dash component tree."""
    if component is None:
        return ""
    if isinstance(component, str):
        return component
    if isinstance(component, (list, tuple)):
        return " ".join(_texts(c) for c in component)
    return _texts(getattr(component, "children", None))


def test_kpi_yoy_matches_hand_computation():
    df = pd.DataFrame({"d": pd.to_datetime(["2024-05-01", "2025-05-01", "2025-06-01"]), "sales": [100.0, 80.0, 70.0]})
    card = rbc_kpi(data_frame=df, measure="sales", agg={"agg": "sum", "ratio": None}, fmt="currency", title="Sales",
                   time_field="d", date_range=["2025-01-01", "2025-12-31"], compare="previous_year")()  # figure captures stay lazy
    text = _texts(card)
    assert "$150" in text and "50.0%" in text and "vs last year" in text


# ---- validation ------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def project():
    return load_project()


def _errs(tmp_path, project, spec):
    p = tmp_path / "t-dash.yaml"
    p.write_text(yaml.safe_dump(spec, sort_keys=False), encoding="utf-8")
    return [str(e) for e in load_dashboard(p, project.semantic, project.platform)[1]]


BASE = {"id": "t-dash", "title": "T", "description": "D.", "owner": "o", "domain": "sales",
        "layout": [{"row": [{"kpi": {"dataset": "orders", "measure": "sales", "title": "S"}}]}]}


def test_time_block_validates(tmp_path, project):
    assert _errs(tmp_path, project, {**BASE, "time": {"default_range": "year_to_date", "compare": "previous_period"}}) == []


def test_bad_time_option_lists_choices(tmp_path, project):
    errs = _errs(tmp_path, project, {**BASE, "time": {"grain": "week"}})
    assert any("time.grain" in e and "quarter" in e for e in errs)


def test_time_field_filter_conflicts_with_time_bar(tmp_path, project):
    spec = {**BASE, "time": {}, "filters": [{"field": "order_date", "type": "date_range"}]}
    assert any("controlled by the time bar" in e for e in _errs(tmp_path, project, spec))


# ---- compiled page ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def app():
    from rbc_bi.app import create_app

    return create_app(load_project())


def test_time_controls_target_every_dated_component(app):
    rng = model_manager["sales-overview__range"]
    grain = model_manager["sales-overview__grain"]
    compare = model_manager["sales-overview__compare"]
    assert isinstance(rng.selector, vm.DatePicker)
    assert "sales-overview__r0c0.date_range" in rng.targets          # KPI
    assert "sales-overview__r1c0.time_grain" in grain.targets         # trend chart follows View by
    assert all(t.endswith(".compare") for t in compare.targets) and len(compare.targets) == 4


def test_pinned_grain_is_not_switched(app):
    grain = model_manager["regional-targets__grain"]
    assert "regional-targets__r2c1.time_grain" not in grain.targets  # quarterly stacked bar pins its grain


def test_filters_live_in_top_bar_not_side_panel(app):
    page = model_manager["sales-overview"]
    assert page.controls == []
    body = model_manager["sales-overview__body"]
    assert any(isinstance(c, vm.Filter) for c in body.controls)
