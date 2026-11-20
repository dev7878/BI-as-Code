"""One test per validation rule. Messages must name the file, the YAML path and a fix."""

from pathlib import Path

import pytest
import yaml

from rbc_bi.spec.validator import load_dashboard, load_project

GOOD = {
    "id": "t-dash",
    "title": "Test",
    "description": "Test dashboard.",
    "owner": "me@example.com",
    "domain": "sales",
    "filters": [{"field": "region", "type": "multi_select"}],
    "layout": [
        {"row": [{"kpi": {"dataset": "orders", "measure": "sales", "title": "Sales"}}]},
        {"row": [{"chart": {"type": "bar", "dataset": "orders", "x": "region", "y": "sales", "title": "By region"}}]},
    ],
}


@pytest.fixture(scope="module")
def project():
    return load_project()


def errors_for(tmp_path: Path, project, spec: dict, name: str = "t-dash") -> list[str]:
    p = tmp_path / f"{name}.yaml"
    p.write_text(yaml.safe_dump(spec, sort_keys=False), encoding="utf-8")
    _, errs = load_dashboard(p, project.semantic, project.platform)
    return [str(e) for e in errs]


def mutate(**changes):
    import copy

    spec = copy.deepcopy(GOOD)
    spec.update(changes)
    return spec


def chart(**kw):
    base = {"type": "bar", "dataset": "orders", "x": "region", "y": "sales", "title": "C"}
    base.update(kw)
    return mutate(layout=[{"row": [{"chart": base}]}])


def test_examples_are_valid(project):
    assert project.errors == [], "\n".join(map(str, project.errors))
    assert len(project.dashboards) >= 4


def test_good_spec_passes(tmp_path, project):
    assert errors_for(tmp_path, project, GOOD) == []


def test_typo_in_field_suggests_fix(tmp_path, project):
    errs = errors_for(tmp_path, project, chart(y=["sales", "proft"]))
    assert len(errs) == 1
    assert "t-dash.yaml: layout[0].row[0].chart.y[1] 'proft' is not a field of dataset 'orders'" in errs[0]
    assert "Did you mean 'profit'?" in errs[0]


def test_unknown_dataset_suggests_fix(tmp_path, project):
    errs = errors_for(tmp_path, project, chart(dataset="order"))
    assert "'order' is not a dataset" in errs[0] and "Did you mean 'orders'?" in errs[0]


def test_physical_table_name_is_called_out(tmp_path, project):
    errs = errors_for(tmp_path, project, chart(dataset="retail.orders"))
    assert "looks like a physical table" in errs[0]


@pytest.mark.parametrize("key", ["color", "font", "css", "style", "template"])
def test_style_keys_rejected(tmp_path, project, key):
    errs = errors_for(tmp_path, project, chart(**{key: "red"}))
    assert any(f"style key '{key}' is not allowed" in e for e in errs)


def test_sql_rejected(tmp_path, project):
    errs = errors_for(tmp_path, project, mutate(description="select * from retail.orders"))
    assert any("looks like SQL" in e for e in errs)
    errs = errors_for(tmp_path, project, chart(sql="x"))
    assert any("dashboards never contain SQL" in e for e in errs)


def test_unknown_key_suggests_allowed(tmp_path, project):
    errs = errors_for(tmp_path, project, chart(titel="x"))
    assert any("unknown key 'titel'" in e and "Did you mean 'title'?" in e for e in errs)


def test_component_synonym(tmp_path, project):
    spec = mutate(layout=[{"row": [{"graph": {"type": "bar"}}]}])
    errs = errors_for(tmp_path, project, spec)
    assert any("unknown key 'graph'" in e and "Use 'chart' instead" in e for e in errs)


def test_bad_chart_type_lists_options(tmp_path, project):
    errs = errors_for(tmp_path, project, chart(type="pie"))
    assert any("'pie' is not allowed" in e and "donut" in e for e in errs)


def test_measure_must_be_numeric(tmp_path, project):
    errs = errors_for(tmp_path, project, chart(y="region"))
    assert any("a measure (numeric field) is needed" in e for e in errs)


def test_split_by_must_be_dimension(tmp_path, project):
    errs = errors_for(tmp_path, project, chart(split_by="sales"))
    assert any("a dimension (string or date field) is needed" in e for e in errs)


def test_split_by_and_multiple_y_conflict(tmp_path, project):
    errs = errors_for(tmp_path, project, chart(y=["sales", "profit"], split_by="segment"))
    assert any("either several y measures or split_by" in e for e in errs)


def test_stacked_bar_needs_something_to_stack(tmp_path, project):
    errs = errors_for(tmp_path, project, chart(type="stacked_bar"))
    assert any("stacked_bar needs split_by" in e for e in errs)


def test_filter_type_must_fit_field(tmp_path, project):
    errs = errors_for(tmp_path, project, mutate(filters=[{"field": "order_date", "type": "multi_select"}]))
    assert any("Use 'date_range'" in e for e in errs)


def test_filter_field_must_exist_on_page(tmp_path, project):
    errs = errors_for(tmp_path, project, mutate(filters=[{"field": "regoin", "type": "multi_select"}]))
    assert any("Did you mean 'region'?" in e for e in errs)


def test_id_must_match_filename(tmp_path, project):
    errs = errors_for(tmp_path, project, GOOD, name="other-name")
    assert any("must match the filename" in e for e in errs)


def test_domain_must_be_configured(tmp_path, project):
    errs = errors_for(tmp_path, project, mutate(domain="finanse"))
    assert any("not a domain" in e for e in errs)


def test_kpi_format_must_match_type(tmp_path, project):
    spec = mutate(layout=[{"row": [{"kpi": {"dataset": "orders", "measure": "sales", "format": "percent", "title": "S"}}]}])
    errs = errors_for(tmp_path, project, spec)
    assert any("format 'percent' does not match currency field" in e for e in errs)


def test_ratio_agg_needs_ratio_field(tmp_path, project):
    spec = mutate(layout=[{"row": [{"kpi": {"dataset": "orders", "measure": "sales", "agg": "ratio", "title": "S"}}]}])
    errs = errors_for(tmp_path, project, spec)
    assert any("agg 'ratio' needs a ratio field" in e for e in errs)


def test_table_dimension_must_be_grouped(tmp_path, project):
    spec = mutate(layout=[{"row": [{"table": {"dataset": "orders", "columns": ["region", "segment", "sales"],
                                              "group_by": ["region"]}}]}])
    errs = errors_for(tmp_path, project, spec)
    assert any("'segment' is a dimension but not in group_by" in e for e in errs)


def test_row_max_four_components(tmp_path, project):
    kpi = {"kpi": {"dataset": "orders", "measure": "sales", "title": "S"}}
    errs = errors_for(tmp_path, project, mutate(layout=[{"row": [kpi] * 5}]))
    assert any("layout[0].row" in e for e in errs)


def test_invalid_yaml_reports_line(tmp_path, project):
    p = tmp_path / "t-dash.yaml"
    p.write_text("id: t-dash\ntitle: [unclosed\n", encoding="utf-8")
    _, errs = load_dashboard(p, project.semantic, project.platform)
    assert "invalid YAML (line" in str(errs[0])


def test_semantic_sql_matches_declared_fields():
    proj = load_project(check_sql=True)
    assert proj.errors == []
