"""Every example dashboard compiles, and every component renders against real data."""

import pytest
import vizro.models as vm
from plotly.io.json import to_json_plotly
from vizro.managers import model_manager

from rbc_bi.app import create_app
from rbc_bi.spec.validator import load_project


@pytest.fixture(scope="module")
def app():
    return create_app(load_project())


def test_all_example_dashboards_are_pages(app):
    page_ids = {p.id for p in model_manager._get_models(vm.Page)}
    for spec in load_project().dashboards:
        assert spec.id in page_ids


@pytest.mark.parametrize("model_type", [vm.Figure, vm.Graph, vm.Table])
def test_every_component_renders(app, model_type):
    models = list(model_manager._get_models(model_type))
    assert models
    for m in models:
        # Loads the dataset through the connector, runs the component, and checks Dash can send it.
        to_json_plotly(m())


def test_catalog_is_home(app):
    assert model_manager["catalog"].path == "/"
