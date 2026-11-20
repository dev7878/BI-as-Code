"""Build the local DuckDB warehouse from the Kaggle "Superstore" dataset.

Source: https://www.kaggle.com/datasets/vivek468/superstore-dataset-final  (Sample - Superstore.csv)
Download (no Kaggle login needed for this public dataset):

    curl -L -o data/raw/superstore.zip https://www.kaggle.com/api/v1/datasets/download/vivek468/superstore-dataset-final
    (then unzip into data/raw/)

Tables created (schema `retail`):
  retail.orders          one row per order line (cleaned, snake_case columns)
  retail.sales_targets   monthly sales target per region (synthetic, deterministic: see below)

Order and ship dates are shifted forward by DATE_SHIFT_YEARS so the demo shows recent months.
Everything here is the *physical* layer. Dashboards never see these names; they go through
semantic/datasets.yaml.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "Sample - Superstore.csv"
DB_PATH = ROOT / "data" / "warehouse.duckdb"
DATE_SHIFT_YEARS = 8  # 2014-2017 -> 2022-2025
SEED = 42


def load_orders() -> pd.DataFrame:
    if not RAW.exists():
        sys.exit(f"Missing {RAW}. Download it first (see the docstring at the top of {Path(__file__).name}).")
    try:
        df = pd.read_csv(RAW, encoding="utf-8")
    except UnicodeDecodeError:
        df = pd.read_csv(RAW, encoding="latin-1")

    df.columns = [c.strip().lower().replace(" ", "_").replace("-", "_") for c in df.columns]
    shift = pd.DateOffset(years=DATE_SHIFT_YEARS)
    df["order_date"] = pd.to_datetime(df["order_date"], format="%m/%d/%Y") + shift
    df["ship_date"] = pd.to_datetime(df["ship_date"], format="%m/%d/%Y") + shift
    df["postal_code"] = df["postal_code"].astype("string")
    return df.drop(columns=["row_id"])


def build_targets(orders: pd.DataFrame) -> pd.DataFrame:
    """Monthly target per region = same month last year x 1.10 growth (first year: actual +/- 10% noise)."""
    rng = np.random.default_rng(SEED)
    monthly = (
        orders.assign(month=orders["order_date"].dt.to_period("M").dt.to_timestamp())
        .groupby(["region", "month"], as_index=False)["sales"]
        .sum()
    )
    prior = monthly.assign(month=monthly["month"] + pd.DateOffset(years=1)).rename(columns={"sales": "prior"})
    t = monthly.merge(prior, on=["region", "month"], how="left")
    noise = rng.uniform(0.9, 1.1, len(t))
    t["sales_target"] = np.where(t["prior"].notna(), t["prior"] * 1.10, t["sales"] * noise).round(2)
    return t[["month", "region", "sales_target"]]


def main() -> None:
    orders = load_orders()
    targets = build_targets(orders)
    # Build into a temp file, then swap it in, so a running app never sees a half-built warehouse.
    tmp = DB_PATH.with_suffix(".building.duckdb")
    tmp.unlink(missing_ok=True)
    con = duckdb.connect(str(tmp))
    con.execute("create schema retail")
    con.register("orders_df", orders)
    con.register("targets_df", targets)
    con.execute("create table retail.orders as select * from orders_df")
    con.execute("create table retail.sales_targets as select * from targets_df")
    n_orders = con.execute("select count(*) from retail.orders").fetchone()[0]
    lo, hi = con.execute("select min(order_date), max(order_date) from retail.orders").fetchone()
    con.close()
    for attempt in range(10):  # a query in flight holds the file for a few ms; retry briefly
        try:
            os.replace(tmp, DB_PATH)
            break
        except PermissionError:
            if attempt == 9:
                tmp.unlink(missing_ok=True)
                sys.exit(f"Could not replace {DB_PATH.name}: another process has it open "
                         f"(e.g. a DuckDB CLI or notebook). Close it and re-run.")
            time.sleep(0.3)
    print(f"Built {DB_PATH.relative_to(ROOT)}: retail.orders={n_orders:,} rows ({lo:%Y-%m-%d} to {hi:%Y-%m-%d}), "
          f"retail.sales_targets={len(targets):,} rows")


if __name__ == "__main__":
    main()
