"""
============================================================
scripts/load.py -- Data Load Module
============================================================
Purpose:
    Loads the cleaned DataFrames produced by transform.py into
    the PostgreSQL database using SQLAlchemy.

    Strategy:
    * Uses pandas .to_sql() with if_exists='append'.
    * Each table load runs inside a transaction; failures roll back.
    * Duplicate primary keys are handled by ON CONFLICT DO NOTHING
      via a pre-load UPSERT helper for the fact table.
    * Tables are loaded in dependency order:
        1. customers  (no FKs)
        2. products   (no FKs)
        3. orders     (FK -> customers)
        4. sales      (FK -> orders, products)
        5. sales_fact (standalone analytical table)

Inputs:
    Dict[str, pd.DataFrame] -- cleaned DataFrames from transform.py
    SQLAlchemy Engine from database.py

Outputs:
    Rows inserted into PostgreSQL tables.

Usage:
    from scripts.load import load_all
    load_all(clean_data, engine)
============================================================
"""

from __future__ import annotations

from typing import Dict

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from config.config import (
    TABLE_CUSTOMERS,
    TABLE_PRODUCTS,
    TABLE_ORDERS,
    TABLE_SALES,
    TABLE_SALES_FACT,
)
from scripts.logger import get_logger
from scripts.helpers import timer

logger = get_logger(__name__)

# ── Column mapping: DataFrame column -> DB column name ────────────────────────
_CUSTOMERS_COLS: dict[str, str] = {
    "customer_id":        "customer_id",
    "customer_name":      "customer_name",
    "email":              "email",
    "phone":              "phone",
    "city":               "city",
    "state":              "state",
    "country":            "country",
    "registration_date":  "registration_date",
}

_PRODUCTS_COLS: dict[str, str] = {
    "product_id":   "product_id",
    "product_name": "product_name",
    "category":     "category",
    "sub_category": "sub_category",
    "price":        "price",
    "cost":         "cost",
    "supplier":     "supplier",
}

_ORDERS_COLS: dict[str, str] = {
    "order_id":       "order_id",
    "customer_id":    "customer_id",
    "order_date":     "order_date",
    "payment_method": "payment_method",
}

_SALES_COLS: dict[str, str] = {
    "sale_id":    "sale_id",
    "order_id":   "order_id",
    "product_id": "product_id",
    "quantity":   "quantity",
}

_SALES_FACT_COLS: list[str] = [
    "sale_id", "order_id", "customer_id", "customer_name",
    "city", "state", "country",
    "product_id", "product_name", "category", "sub_category",
    "order_date", "payment_method", "quantity",
    "price", "cost", "total_amount", "profit", "profit_percentage",
    "order_year", "order_month", "order_quarter", "order_weekday",
]


# ── Internal helpers ─────────────────────────────────────────────────────────

def _prepare_df(df: pd.DataFrame, col_map: dict[str, str]) -> pd.DataFrame:
    """
    Select and rename DataFrame columns to match DB schema.

    Parameters
    ----------
    df : pd.DataFrame
    col_map : dict[str, str]
        Mapping of DataFrame column names -> DB column names.

    Returns
    -------
    pd.DataFrame
    """
    # Keep only columns that exist in the DataFrame
    available = {k: v for k, v in col_map.items() if k in df.columns}
    return df[list(available.keys())].rename(columns=available)


def _upsert_table(
    df: pd.DataFrame,
    table_name: str,
    pk_col: str,
    engine: Engine,
) -> int:
    """
    Insert rows, skipping those whose primary key already exists.

    Uses a temp table + INSERT ... SELECT ... WHERE NOT EXISTS strategy.

    Parameters
    ----------
    df : pd.DataFrame
    table_name : str
    pk_col : str
    engine : Engine

    Returns
    -------
    int
        Number of rows actually inserted.
    """
    tmp_table = f"_tmp_{table_name}"
    rows_inserted = 0

    with engine.begin() as conn:
        # Load into temp table
        df.to_sql(tmp_table, con=conn, if_exists="replace", index=False)

        # Insert only non-duplicate rows
        result = conn.execute(text(f"""
            INSERT INTO {table_name}
            SELECT t.*
            FROM   {tmp_table} t
            WHERE  t.{pk_col} NOT IN (SELECT {pk_col} FROM {table_name})
        """))
        rows_inserted = result.rowcount

        # Drop temp table
        conn.execute(text(f"DROP TABLE IF EXISTS {tmp_table}"))

    return rows_inserted


def _load_table(
    df: pd.DataFrame,
    table_name: str,
    col_map: dict[str, str] | None,
    pk_col: str,
    engine: Engine,
    fact_cols: list[str] | None = None,
) -> None:
    """
    Prepare and load a DataFrame into a PostgreSQL table.

    Parameters
    ----------
    df : pd.DataFrame
    table_name : str
    col_map : dict | None
        Column mapping. Pass None for the fact table (uses fact_cols directly).
    pk_col : str
        Primary key column name in the DB.
    engine : Engine
    fact_cols : list[str] | None
        Explicit column list (for sales_fact).
    """
    try:
        if fact_cols:
            cols_to_use = [c for c in fact_cols if c in df.columns]
            prepared = df[cols_to_use].copy()
        else:
            prepared = _prepare_df(df, col_map or {})

        if prepared.empty:
            logger.warning(f"  [{table_name}] DataFrame is empty -- skipping load.")
            return

        logger.info(f"  Loading {len(prepared)} rows -> [{table_name}] ...")
        rows_inserted = _upsert_table(prepared, table_name, pk_col, engine)
        logger.info(
            f"  [{table_name}] Inserted {rows_inserted} new row(s) "
            f"({len(prepared) - rows_inserted} skipped as duplicates)."
        )

    except SQLAlchemyError as exc:
        logger.error(f"  [{table_name}] Load FAILED -- rolling back: {exc}")
        raise


# ── Public API ────────────────────────────────────────────────────────────────

@timer
def load_customers(df: pd.DataFrame, engine: Engine) -> None:
    """Load cleaned customers DataFrame into the 'customers' table."""
    _load_table(df, TABLE_CUSTOMERS, _CUSTOMERS_COLS, "customer_id", engine)


@timer
def load_products(df: pd.DataFrame, engine: Engine) -> None:
    """Load cleaned products DataFrame into the 'products' table."""
    _load_table(df, TABLE_PRODUCTS, _PRODUCTS_COLS, "product_id", engine)


@timer
def load_orders(df: pd.DataFrame, engine: Engine) -> None:
    """Load cleaned orders DataFrame into the 'orders' table."""
    _load_table(df, TABLE_ORDERS, _ORDERS_COLS, "order_id", engine)


@timer
def load_sales(df: pd.DataFrame, engine: Engine) -> None:
    """Load cleaned sales DataFrame into the 'sales' table."""
    _load_table(df, TABLE_SALES, _SALES_COLS, "sale_id", engine)


@timer
def load_sales_fact(df: pd.DataFrame, engine: Engine) -> None:
    """Load the enriched sales_fact DataFrame into the 'sales_fact' table."""
    _load_table(df, TABLE_SALES_FACT, None, "sale_id", engine,
                fact_cols=_SALES_FACT_COLS)


@timer
def load_all(clean_data: Dict[str, pd.DataFrame], engine: Engine) -> None:
    """
    Load all cleaned datasets into PostgreSQL in dependency order.

    Parameters
    ----------
    clean_data : Dict[str, pd.DataFrame]
        Output from transform.transform_all().
    engine : Engine
        Active SQLAlchemy engine.
    """
    logger.info("=" * 50)
    logger.info("LOAD PHASE -- inserting data into PostgreSQL")
    logger.info("=" * 50)

    # Dependency order: customers -> products -> orders -> sales -> sales_fact
    load_customers(clean_data["customers"], engine)
    load_products(clean_data["products"],   engine)
    load_orders(clean_data["orders"],       engine)
    load_sales(clean_data["sales"],         engine)
    load_sales_fact(clean_data["sales_fact"], engine)

    logger.info("Load phase complete -- all tables populated.")
