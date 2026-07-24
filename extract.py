"""
============================================================
scripts/extract.py -- Data Extraction Module
============================================================
Purpose:
    Reads all four raw CSV datasets from the data/raw/ directory
    and returns them as typed Pandas DataFrames.

    Responsibilities:
    * Validate that each CSV file exists before reading.
    * Handle missing or unreadable files gracefully (log + raise).
    * Return DataFrames with consistent column naming.
    * Log row / column counts for each file read.

Inputs:
    data/raw/customers.csv
    data/raw/products.csv
    data/raw/orders.csv
    data/raw/sales.csv

Outputs:
    Dict[str, pd.DataFrame] with keys:
        "customers", "products", "orders", "sales"

Usage:
    from scripts.extract import extract_all
    data = extract_all()
    customers_df = data["customers"]
============================================================
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict

import pandas as pd

from config.config import CUSTOMERS_CSV, PRODUCTS_CSV, ORDERS_CSV, SALES_CSV
from scripts.logger import get_logger
from scripts.helpers import timer, log_dataframe_info

logger = get_logger(__name__)

# ── File registry ─────────────────────────────────────────────────────────────
# Maps a logical name to its Path.  Extend here if new sources are added.
_CSV_REGISTRY: Dict[str, Path] = {
    "customers": CUSTOMERS_CSV,
    "products":  PRODUCTS_CSV,
    "orders":    ORDERS_CSV,
    "sales":     SALES_CSV,
}


# ── Internal helpers ─────────────────────────────────────────────────────────

def _validate_file(name: str, path: Path) -> None:
    """
    Raise FileNotFoundError if *path* does not exist or is empty.

    Parameters
    ----------
    name : str
        Logical dataset name (used in error messages).
    path : Path
        Filesystem path to validate.
    """
    if not path.exists():
        raise FileNotFoundError(
            f"[extract] Required file not found: {path}\n"
            f"  Please ensure '{name}.csv' is in the data/raw/ directory."
        )
    if path.stat().st_size == 0:
        raise ValueError(
            f"[extract] File is empty: {path}\n"
            f"  Please check that '{name}.csv' contains data."
        )


def _read_csv(name: str, path: Path) -> pd.DataFrame:
    """
    Read a CSV file from *path* and return a DataFrame.

    Parameters
    ----------
    name : str
        Logical dataset name.
    path : Path
        Path to the CSV file.

    Returns
    -------
    pd.DataFrame

    Raises
    ------
    FileNotFoundError
        If the file does not exist.
    pd.errors.ParserError
        If the CSV cannot be parsed.
    """
    _validate_file(name, path)
    logger.info(f"  Reading [{name}] from: {path}")

    try:
        df = pd.read_csv(
            path,
            dtype=str,          # read everything as string first
            keep_default_na=False,  # do not auto-convert "" to NaN
            na_values=["NA", "N/A", "NULL", "null", "None", "none", "-"],
        )
        log_dataframe_info(df, name)
        return df

    except pd.errors.ParserError as exc:
        logger.error(f"  Failed to parse '{name}' CSV: {exc}")
        raise
    except Exception as exc:
        logger.error(f"  Unexpected error reading '{name}': {exc}")
        raise


# ── Public API ────────────────────────────────────────────────────────────────

@timer
def extract_customers() -> pd.DataFrame:
    """
    Extract the customers CSV into a DataFrame.

    Returns
    -------
    pd.DataFrame
        Raw customers data.
    """
    return _read_csv("customers", CUSTOMERS_CSV)


@timer
def extract_products() -> pd.DataFrame:
    """
    Extract the products CSV into a DataFrame.

    Returns
    -------
    pd.DataFrame
        Raw products data.
    """
    return _read_csv("products", PRODUCTS_CSV)


@timer
def extract_orders() -> pd.DataFrame:
    """
    Extract the orders CSV into a DataFrame.

    Returns
    -------
    pd.DataFrame
        Raw orders data.
    """
    return _read_csv("orders", ORDERS_CSV)


@timer
def extract_sales() -> pd.DataFrame:
    """
    Extract the sales CSV into a DataFrame.

    Returns
    -------
    pd.DataFrame
        Raw sales data.
    """
    return _read_csv("sales", SALES_CSV)


@timer
def extract_all() -> Dict[str, pd.DataFrame]:
    """
    Extract all four datasets and return them in a dictionary.

    This is the main entry point for the Extract phase of the ETL.
    Missing files cause the pipeline to abort with a clear error.

    Returns
    -------
    Dict[str, pd.DataFrame]
        Keys: "customers", "products", "orders", "sales"

    Raises
    ------
    FileNotFoundError
        If any required CSV file is missing.
    """
    logger.info("=" * 50)
    logger.info("EXTRACT PHASE -- reading raw CSV files")
    logger.info("=" * 50)

    datasets: Dict[str, pd.DataFrame] = {}
    errors: list[str] = []

    for name, path in _CSV_REGISTRY.items():
        try:
            datasets[name] = _read_csv(name, path)
        except (FileNotFoundError, ValueError) as exc:
            logger.error(str(exc))
            errors.append(name)

    if errors:
        raise FileNotFoundError(
            f"Extract phase aborted -- missing/invalid files: {errors}"
        )

    total_rows = sum(len(df) for df in datasets.values())
    logger.info(f"Extract complete -- {len(datasets)} datasets, {total_rows} total rows.")
    return datasets
