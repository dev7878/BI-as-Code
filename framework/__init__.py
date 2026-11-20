"""rbc_bi: a thin, opinionated BI-as-Code layer on top of Vizro.

Dashboards are YAML specs (dashboards/*.yaml) that reference datasets in the semantic layer
(semantic/datasets.yaml). The framework validates specs, compiles them to Vizro models and
applies one theme everywhere. No AI runs inside the app.
"""

__version__ = "0.1.0"
