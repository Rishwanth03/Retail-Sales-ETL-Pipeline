"""
============================================================
scripts/transform.py -- Data Transformation Module
============================================================
Purpose:
    Cleans and enriches the four raw DataFrames, then merges
    them into a denormalised analytical fact table.

    Steps performed:
    1. Strip whitespace from all string columns.
    2. Remove fully duplicate rows.
    3. Convert date columns to datetime64.
    4. Convert Price, Cost -> float; Quantity -> int.
    5. Standardise column names to snake_case.
    6. Fill safe defaults for non-critical nulls.
    7. Merge datasets: customers <- orders <- sales -> products.
    8. Calculate business metrics:
         TotalAmount        = Quantity × Price
         Profit             = TotalAmount − (Quantity × Cost)
         ProfitPercentage   = Profit / TotalAmount × 100
    9. Derive time dimensions:
         order_year, order_month, order_quarter, order_weekday

Inputs:
    Dict[str, pd.DataFrame] -- raw DataFrames from extract.py

Outputs:
    Dict[str, pd.DataFrame] containing:
        "customers", "products", "orders", "sales",
        "sales_fact"  (the merged analytical table)

Usage:
    from scripts.transform import transform_all
    clean_data = transform_all(raw_data)
============================================================
"""

from __future__ import annotations

from typing import Dict

import pandas as pd
import numpy as np

from config.config import CLEANED_DATA_PATH
from scripts.logger import get_logger
from scripts.helpers import (
    timer,
    strip_string_columns,
    coerce_dates,
    coerce_numeric,
    drop_duplicate_rows,
    log_dataframe_info,
    export_dataframe,
)

logger = get_logger(__name__)


# ── Column name mapper ────────────────────────────────────────────────────────

# Maps raw column names to their canonical snake_case equivalents
_COLUMN_RENAMES: dict[str, str] = {
    "customername":    "customer_name",
    "productname":     "product_name",
    "registrationdate": "registration_date",
    "orderdate":       "order_date",
    "orderid":         "order_id",
    "customerid":      "customer_id",
    "paymentmethod":   "payment_method",
    "subcategory":     "sub_category",
    "saleid":          "sale_id",
    "productid":       "product_id",
}


def _to_snake_case(df: pd.DataFrame) -> pd.DataFrame:
    """Rename all columns to lowercase snake_case."""
    df.columns = (
        df.columns
        .str.strip()
        .str.lower()
        .str.replace(r"[\s\-]+", "_", regex=True)
        .str.replace(r"[^\w]", "", regex=True)
    )
    # Apply explicit renames for compound words
    df.rename(columns=_COLUMN_RENAMES, inplace=True)
    return df


# ── Individual cleaners ───────────────────────────────────────────────────────

@timer
def clean_customers(df: pd.DataFrame) -> pd.DataFrame:
    """
    Clean the raw customers DataFrame.

    Operations:
    * Strip whitespace from all string columns.
    * Drop full duplicates.
    * Rename columns to snake_case.
    * Parse RegistrationDate -> datetime.
    * Fill missing Phone / City / State with 'Unknown'.
    * Drop rows with null CustomerID or Email.

    Parameters
    ----------
    df : pd.DataFrame

    Returns
    -------
    pd.DataFrame
        Cleaned customers data.
    """
    logger.info("  Cleaning customers ...")
    df = strip_string_columns(df.copy())
    df = drop_duplicate_rows(df)
    df = coerce_dates(df, ["RegistrationDate"])
    df = _to_snake_case(df)  # CustomerID -> customer_id, RegistrationDate -> registration_date

    # Fill non-critical missing values
    for col in ("phone", "city", "state"):
        if col in df.columns:
            df[col] = df[col].replace("", np.nan).fillna("Unknown")

    # Drop rows with no ID or email (cannot load to DB)
    before = len(df)
    df = df.dropna(subset=["customer_id", "email"])  # use post-rename column names
    after = len(df)
    if before != after:
        logger.warning(f"  Dropped {before - after} row(s) with null CustomerID or Email.")

    log_dataframe_info(df, "customers (cleaned)")
    return df


@timer
def clean_products(df: pd.DataFrame) -> pd.DataFrame:
    """
    Clean the raw products DataFrame.

    Operations:
    * Strip whitespace.
    * Drop full duplicates.
    * Rename to snake_case.
    * Cast Price and Cost to float.
    * Fill missing SubCategory with Category.
    * Fill missing Supplier with 'Unknown'.

    Parameters
    ----------
    df : pd.DataFrame

    Returns
    -------
    pd.DataFrame
        Cleaned products data.
    """
    logger.info("  Cleaning products ...")
    df = strip_string_columns(df.copy())
    df = drop_duplicate_rows(df)
    df = _to_snake_case(df)

    # Cast numeric columns
    df = coerce_numeric(df, ["price", "cost"], dtype=float)

    # Clamp negatives to 0
    for col in ("price", "cost"):
        if col in df.columns:
            n_neg = (df[col] < 0).sum()
            if n_neg:
                logger.warning(f"  Clamping {n_neg} negative {col} value(s) to 0.")
            df[col] = df[col].clip(lower=0.0)

    # Fill non-critical nulls
    if "sub_category" in df.columns:
        df["sub_category"] = df["sub_category"].fillna(df.get("category", "Unknown"))
    if "supplier" in df.columns:
        df["supplier"] = df["supplier"].replace("", np.nan).fillna("Unknown")

    log_dataframe_info(df, "products (cleaned)")
    return df


@timer
def clean_orders(df: pd.DataFrame) -> pd.DataFrame:
    """
    Clean the raw orders DataFrame.

    Operations:
    * Strip whitespace.
    * Drop full duplicates.
    * Rename to snake_case.
    * Parse OrderDate -> datetime.
    * Fill missing PaymentMethod with 'Unknown'.

    Parameters
    ----------
    df : pd.DataFrame

    Returns
    -------
    pd.DataFrame
        Cleaned orders data.
    """
    logger.info("  Cleaning orders ...")
    df = strip_string_columns(df.copy())
    df = drop_duplicate_rows(df)
    df = coerce_dates(df, ["OrderDate"])
    df = _to_snake_case(df)

    if "payment_method" in df.columns:
        df["payment_method"] = df["payment_method"].replace("", np.nan).fillna("Unknown")

    log_dataframe_info(df, "orders (cleaned)")
    return df


@timer
def clean_sales(df: pd.DataFrame) -> pd.DataFrame:
    """
    Clean the raw sales DataFrame.

    Operations:
    * Strip whitespace.
    * Drop full duplicates.
    * Rename to snake_case.
    * Cast Quantity to int.
    * Remove rows with Quantity ≤ 0.

    Parameters
    ----------
    df : pd.DataFrame

    Returns
    -------
    pd.DataFrame
        Cleaned sales data.
    """
    logger.info("  Cleaning sales ...")
    df = strip_string_columns(df.copy())
    df = drop_duplicate_rows(df)
    df = _to_snake_case(df)

    df = coerce_numeric(df, ["quantity"], dtype=int)

    # Remove non-positive quantities
    before = len(df)
    df = df[df["quantity"] > 0]
    removed = before - len(df)
    if removed:
        logger.warning(f"  Removed {removed} row(s) with non-positive quantity.")

    log_dataframe_info(df, "sales (cleaned)")
    return df


# ── Business metric calculations ─────────────────────────────────────────────

def _add_business_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add TotalAmount, Profit, and ProfitPercentage columns.

    Parameters
    ----------
    df : pd.DataFrame
        Must contain: quantity (int), price (float), cost (float).

    Returns
    -------
    pd.DataFrame
    """
    df["total_amount"] = (df["quantity"] * df["price"]).round(2)
    df["profit"] = (df["total_amount"] - df["quantity"] * df["cost"]).round(2)
    df["profit_percentage"] = np.where(
        df["total_amount"] > 0,
        (df["profit"] / df["total_amount"] * 100).round(4),
        0.0,
    )
    return df


def _add_time_dimensions(df: pd.DataFrame) -> pd.DataFrame:
    """
    Derive order_year, order_month, order_quarter, order_weekday.

    Parameters
    ----------
    df : pd.DataFrame
        Must contain: order_date (datetime64).

    Returns
    -------
    pd.DataFrame
    """
    if "order_date" not in df.columns:
        return df
    dt = pd.to_datetime(df["order_date"], errors="coerce")
    df["order_year"]    = dt.dt.year.astype("Int16")
    df["order_month"]   = dt.dt.month.astype("Int8")
    df["order_quarter"] = dt.dt.quarter.astype("Int8")
    df["order_weekday"] = dt.dt.day_name()
    return df


# ── Merge / build fact table ─────────────────────────────────────────────────

@timer
def build_sales_fact(
    customers: pd.DataFrame,
    products: pd.DataFrame,
    orders: pd.DataFrame,
    sales: pd.DataFrame,
) -> pd.DataFrame:
    """
    Join all four clean tables into a denormalised fact table.

    Join order:
        sales -> orders -> customers
        sales -> products

    Then add business metrics and time dimensions.

    Parameters
    ----------
    customers : pd.DataFrame   (cleaned)
    products  : pd.DataFrame   (cleaned)
    orders    : pd.DataFrame   (cleaned)
    sales     : pd.DataFrame   (cleaned)

    Returns
    -------
    pd.DataFrame
        The fully enriched analytical fact table.
    """
    logger.info("  Building sales_fact table ...")

    # sales <- orders
    fact = sales.merge(orders, on="order_id", how="left")

    # <- customers (bring in customer-level dimensions)
    fact = fact.merge(
        customers[["customer_id", "customer_name", "city", "state", "country"]],
        on="customer_id",
        how="left",
    )

    # <- products (bring in product-level dimensions + price/cost)
    fact = fact.merge(
        products[["product_id", "product_name", "category", "sub_category",
                  "price", "cost"]],
        on="product_id",
        how="left",
    )

    # Add business metrics
    fact = _add_business_metrics(fact)

    # Add time dimensions
    fact = _add_time_dimensions(fact)

    log_dataframe_info(fact, "sales_fact")
    logger.info(f"  sales_fact: {len(fact)} rows, {len(fact.columns)} columns.")
    return fact


# ── Main entry point ─────────────────────────────────────────────────────────

@timer
def transform_all(raw_data: Dict[str, pd.DataFrame]) -> Dict[str, pd.DataFrame]:
    """
    Run the full transformation pipeline.

    Parameters
    ----------
    raw_data : Dict[str, pd.DataFrame]
        Output from extract.extract_all().

    Returns
    -------
    Dict[str, pd.DataFrame]
        Keys: "customers", "products", "orders", "sales", "sales_fact"
    """
    logger.info("=" * 50)
    logger.info("TRANSFORM PHASE -- clean and enrich data")
    logger.info("=" * 50)

    # Clean individual datasets
    customers = clean_customers(raw_data["customers"])
    products  = clean_products(raw_data["products"])
    orders    = clean_orders(raw_data["orders"])
    sales     = clean_sales(raw_data["sales"])

    # Build fact table
    sales_fact = build_sales_fact(customers, products, orders, sales)

    # Export cleaned datasets to data/cleaned/
    export_dataframe(customers, CLEANED_DATA_PATH, "customers_cleaned.csv")
    export_dataframe(products,  CLEANED_DATA_PATH, "products_cleaned.csv")
    export_dataframe(orders,    CLEANED_DATA_PATH, "orders_cleaned.csv")
    export_dataframe(sales,     CLEANED_DATA_PATH, "sales_cleaned.csv")
    export_dataframe(sales_fact, CLEANED_DATA_PATH, "sales_fact.csv")

    logger.info("Transform phase complete -- cleaned files saved to data/cleaned/.")

    return {
        "customers": customers,
        "products":  products,
        "orders":    orders,
        "sales":     sales,
        "sales_fact": sales_fact,
    }
