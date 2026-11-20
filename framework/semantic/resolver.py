"""Dataset resolver: turns semantic-layer datasets into Vizro data sources.

Each dataset is registered with Vizro's `data_manager` as a loader function, so data loads at
request time and is cached with a TTL from the dataset's `refresh` setting (see modules/cache.py).
"""

from __future__ import annotations

import logging

import pandas as pd
from vizro.managers import data_manager

from rbc_bi.modules.cache import ttl_seconds
from rbc_bi.semantic.connectors import get_connector
from rbc_bi.spec.models import DatasetSpec, SemanticLayer

log = logging.getLogger(__name__)


def load_dataset(name: str, ds: DatasetSpec) -> pd.DataFrame:
    """Run a dataset's SQL and coerce column types from the semantic layer."""
    df = get_connector(ds.connector).query(ds.sql)
    for col, f in ds.fields.items():
        if col not in df.columns:
            continue
        if f.type == "date":
            df[col] = pd.to_datetime(df[col])
        elif f.type == "string":
            df[col] = df[col].astype("string")
        elif f.is_numeric:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    # Row-level security hook: filter `df` for the current user here when it is needed.
    log.info("loaded dataset %s (%d rows)", name, len(df))
    return df


def register_datasets(semantic: SemanticLayer, names: set[str] | None = None) -> None:
    for name, ds in semantic.datasets.items():
        if names is not None and name not in names:
            continue

        def _loader(_name=name, _ds=ds) -> pd.DataFrame:
            return load_dataset(_name, _ds)

        data_manager[name] = _loader
        data_manager[name].timeout = ttl_seconds(ds.refresh)
