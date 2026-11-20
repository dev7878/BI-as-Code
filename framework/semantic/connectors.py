"""Connector interface: every query in the platform goes through `Connector.query`.

Swapping the data platform (DuckDB -> Databricks, Snowflake, Postgres, SQL Server) means adding a
connector here and pointing config/connectors.yaml at it. Dashboards never change.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from functools import lru_cache
from pathlib import Path

import pandas as pd

from rbc_bi import paths


class Connector(ABC):
    """Read-only access to one data platform."""

    def __init__(self, name: str, **config):
        self.name, self.config = name, config

    @abstractmethod
    def query(self, sql: str, params: dict | None = None) -> pd.DataFrame:
        """Run SQL and return a DataFrame."""

    def columns(self, sql: str) -> list[str]:
        """Column names the SQL returns, without fetching rows."""
        return list(self.query(f"select * from ({sql}) as _q limit 0").columns)


class DuckDBConnector(Connector):
    """Local DuckDB file, opened read-only for each query and closed straight after.

    Opening a local DuckDB file takes milliseconds, and results are cached upstream, so a connection per
    query costs little. In return the app never holds the file open: `rbc-bi data` can rebuild it while
    the app runs (Windows won't replace an open file), and nothing reads a stale copy.
    """

    def __init__(self, name: str, path: str, **config):
        super().__init__(name, **config)
        p = Path(path)
        self.path = p if p.is_absolute() else paths.ROOT / p

    def query(self, sql: str, params: dict | None = None) -> pd.DataFrame:
        import duckdb

        if not self.path.exists():
            raise FileNotFoundError(f"{self.path} not found. Run `rbc-bi data` to build the local warehouse.")
        with duckdb.connect(str(self.path), read_only=True) as con:
            return con.execute(sql, params or {}).df()


class _NotWiredUp(Connector):
    driver = ""

    def query(self, sql: str, params: dict | None = None) -> pd.DataFrame:
        raise NotImplementedError(
            f"{type(self).__name__} is a stub in the prototype. Implement query() with {self.driver}; "
            f"the interface is the same as DuckDBConnector."
        )


class DatabricksConnector(_NotWiredUp):
    driver = "databricks-sql-connector"


class SnowflakeConnector(_NotWiredUp):
    driver = "snowflake-connector-python"


class PostgresConnector(_NotWiredUp):
    driver = "psycopg"


class SqlServerConnector(_NotWiredUp):
    driver = "pyodbc"


CONNECTOR_TYPES: dict[str, type[Connector]] = {
    "duckdb": DuckDBConnector,
    "databricks": DatabricksConnector,
    "snowflake": SnowflakeConnector,
    "postgres": PostgresConnector,
    "sqlserver": SqlServerConnector,
}


@lru_cache(maxsize=None)
def get_connector(name: str) -> Connector:
    from rbc_bi.spec.validator import load_platform

    _, connectors, errors = load_platform(paths.ROOT)
    if connectors is None or name not in connectors.connectors:
        raise KeyError(f"Connector '{name}' is not defined in config/connectors.yaml. {errors or ''}")
    cfg = connectors.connectors[name]
    cls = CONNECTOR_TYPES.get(cfg.type)
    if cls is None:
        raise KeyError(f"Unknown connector type '{cfg.type}'. Known: {', '.join(CONNECTOR_TYPES)}")
    return cls(name, **cfg.__pydantic_extra__)
