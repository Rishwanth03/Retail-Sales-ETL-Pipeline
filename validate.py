"""
============================================================
scripts/validate.py -- Data Validation Module
============================================================
Purpose:
    Runs a comprehensive set of data-quality checks on each
    raw DataFrame BEFORE any transformations are applied.

    Checks performed:
    * Null / missing values in required columns
    * Duplicate rows (full) and duplicate primary-key values
    * Invalid email formats (customers)
    * Negative prices or costs (products)
    * Negative or zero quantities (sales)
    * Future order / registration dates
    * Orphaned foreign keys (orders.CustomerID not in customers)
    * Orphaned foreign keys (sales.OrderID / ProductID)

    Outputs a structured validation report (dict) and exports
    it as a CSV to data/processed/validation_report.csv.

Inputs:
    Dict[str, pd.DataFrame] -- raw DataFrames from extract.py

Outputs:
    Dict[str, list[dict]] -- validation report per dataset
    CSV file at data/processed/validation_report.csv

Usage:
    from scripts.validate import validate_all
    report = validate_all(data)
============================================================
"""

from __future__ import annotations

from datetime import date
from typing import Dict, List

import pandas as pd

from config.config import PROCESSED_DATA_PATH
from scripts.logger import get_logger
from scripts.helpers import is_valid_email, is_future_date, timer

logger = get_logger(__name__)

# ── Type alias ────────────────────────────────────────────────────────────────
ValidationReport = Dict[str, List[dict]]


# ── Internal check helpers ───────────────────────────────────────────────────

def _check_nulls(df: pd.DataFrame, required_cols: list[str], dataset: str) -> list[dict]:
    """Return issue records for missing values in required columns."""
    issues = []
    for col in required_cols:
        if col not in df.columns:
            issues.append({
                "dataset": dataset,
                "check": "missing_column",
                "column": col,
                "count": None,
                "details": f"Column '{col}' not found in dataset",
            })
            continue
        n_null = df[col].isnull().sum() + (df[col] == "").sum()
        if n_null:
            issues.append({
                "dataset": dataset,
                "check": "null_values",
                "column": col,
                "count": int(n_null),
                "details": f"{n_null} null/empty values in required column '{col}'",
            })
            logger.warning(f"  [{dataset}] {col}: {n_null} null/empty value(s)")
    return issues


def _check_duplicates(df: pd.DataFrame, pk_col: str, dataset: str) -> list[dict]:
    """Return issue records for duplicate primary keys."""
    issues = []
    full_dupes = df.duplicated().sum()
    if full_dupes:
        issues.append({
            "dataset": dataset,
            "check": "duplicate_rows",
            "column": "ALL",
            "count": int(full_dupes),
            "details": f"{full_dupes} fully duplicate rows",
        })
        logger.warning(f"  [{dataset}] {full_dupes} fully duplicate row(s)")

    if pk_col in df.columns:
        pk_dupes = df[pk_col].duplicated().sum()
        if pk_dupes:
            issues.append({
                "dataset": dataset,
                "check": "duplicate_primary_key",
                "column": pk_col,
                "count": int(pk_dupes),
                "details": f"{pk_dupes} duplicate {pk_col} value(s)",
            })
            logger.warning(f"  [{dataset}] {pk_dupes} duplicate {pk_col} value(s)")
    return issues


def _check_emails(df: pd.DataFrame, email_col: str = "Email") -> list[dict]:
    """Return issue records for malformed email addresses."""
    issues = []
    if email_col not in df.columns:
        return issues
    mask_invalid = ~df[email_col].apply(is_valid_email)
    n_invalid = mask_invalid.sum()
    if n_invalid:
        bad_emails = df.loc[mask_invalid, email_col].tolist()[:10]
        issues.append({
            "dataset": "customers",
            "check": "invalid_email",
            "column": email_col,
            "count": int(n_invalid),
            "details": f"Invalid emails (first 10): {bad_emails}",
        })
        logger.warning(f"  [customers] {n_invalid} invalid email(s)")
    return issues


def _check_negative_numeric(
    df: pd.DataFrame,
    col: str,
    dataset: str,
    allow_zero: bool = False,
) -> list[dict]:
    """Return issue records for negative (or zero) numeric values."""
    issues = []
    if col not in df.columns:
        return issues
    series = pd.to_numeric(df[col], errors="coerce")
    if allow_zero:
        mask = series < 0
        label = "negative"
    else:
        mask = series <= 0
        label = "negative/zero"
    n_bad = mask.sum()
    if n_bad:
        issues.append({
            "dataset": dataset,
            "check": f"{label}_values",
            "column": col,
            "count": int(n_bad),
            "details": f"{n_bad} {label} value(s) in '{col}'",
        })
        logger.warning(f"  [{dataset}] {n_bad} {label} value(s) in '{col}'")
    return issues


def _check_future_dates(df: pd.DataFrame, col: str, dataset: str) -> list[dict]:
    """Return issue records for date values in the future."""
    issues = []
    if col not in df.columns:
        return issues
    parsed = pd.to_datetime(df[col], errors="coerce")
    today = pd.Timestamp(date.today())
    n_future = (parsed > today).sum()
    if n_future:
        issues.append({
            "dataset": dataset,
            "check": "future_date",
            "column": col,
            "count": int(n_future),
            "details": f"{n_future} date(s) in '{col}' are in the future",
        })
        logger.warning(f"  [{dataset}] {n_future} future date(s) in '{col}'")
    return issues


def _check_orphan_fk(
    child_df: pd.DataFrame,
    parent_df: pd.DataFrame,
    fk_col: str,
    pk_col: str,
    child_name: str,
    parent_name: str,
) -> list[dict]:
    """Return issue records for FK values not present in the parent table."""
    issues = []
    if fk_col not in child_df.columns or pk_col not in parent_df.columns:
        return issues
    valid_ids = set(parent_df[pk_col].dropna())
    child_ids = set(child_df[fk_col].dropna())
    orphans = child_ids - valid_ids
    if orphans:
        issues.append({
            "dataset": child_name,
            "check": "orphan_foreign_key",
            "column": fk_col,
            "count": len(orphans),
            "details": (
                f"{len(orphans)} {fk_col} value(s) in '{child_name}' "
                f"not found in '{parent_name}.{pk_col}': "
                f"{list(orphans)[:5]}"
            ),
        })
        logger.warning(
            f"  [{child_name}] {len(orphans)} orphan FK value(s) in '{fk_col}'"
        )
    return issues


# ── Per-dataset validators ───────────────────────────────────────────────────

def validate_customers(df: pd.DataFrame) -> list[dict]:
    """
    Run all quality checks on the customers DataFrame.

    Checks: nulls, duplicates, email format, future registration dates.
    """
    logger.info("  Validating customers ...")
    issues: list[dict] = []
    required = ["CustomerID", "CustomerName", "Email", "Country"]
    issues += _check_nulls(df, required, "customers")
    issues += _check_duplicates(df, "CustomerID", "customers")
    issues += _check_emails(df, "Email")
    issues += _check_future_dates(df, "RegistrationDate", "customers")
    return issues


def validate_products(df: pd.DataFrame) -> list[dict]:
    """
    Run all quality checks on the products DataFrame.

    Checks: nulls, duplicates, negative price/cost.
    """
    logger.info("  Validating products ...")
    issues: list[dict] = []
    required = ["ProductID", "ProductName", "Category", "Price", "Cost"]
    issues += _check_nulls(df, required, "products")
    issues += _check_duplicates(df, "ProductID", "products")
    issues += _check_negative_numeric(df, "Price", "products", allow_zero=True)
    issues += _check_negative_numeric(df, "Cost", "products", allow_zero=True)
    return issues


def validate_orders(
    df: pd.DataFrame,
    customers_df: pd.DataFrame,
) -> list[dict]:
    """
    Run all quality checks on the orders DataFrame.

    Checks: nulls, duplicates, future order dates, orphan CustomerIDs.
    """
    logger.info("  Validating orders ...")
    issues: list[dict] = []
    required = ["OrderID", "CustomerID", "OrderDate", "PaymentMethod"]
    issues += _check_nulls(df, required, "orders")
    issues += _check_duplicates(df, "OrderID", "orders")
    issues += _check_future_dates(df, "OrderDate", "orders")
    issues += _check_orphan_fk(df, customers_df, "CustomerID", "CustomerID",
                               "orders", "customers")
    return issues


def validate_sales(
    df: pd.DataFrame,
    orders_df: pd.DataFrame,
    products_df: pd.DataFrame,
) -> list[dict]:
    """
    Run all quality checks on the sales DataFrame.

    Checks: nulls, duplicates, negative quantity, orphan OrderID/ProductID.
    """
    logger.info("  Validating sales ...")
    issues: list[dict] = []
    required = ["SaleID", "OrderID", "ProductID", "Quantity"]
    issues += _check_nulls(df, required, "sales")
    issues += _check_duplicates(df, "SaleID", "sales")
    issues += _check_negative_numeric(df, "Quantity", "sales", allow_zero=False)
    issues += _check_orphan_fk(df, orders_df, "OrderID", "OrderID",
                               "sales", "orders")
    issues += _check_orphan_fk(df, products_df, "ProductID", "ProductID",
                               "sales", "products")
    return issues


# ── Report export ────────────────────────────────────────────────────────────

def _export_report(all_issues: list[dict]) -> None:
    """Save the validation report as a CSV in data/processed/."""
    report_df = pd.DataFrame(all_issues)
    out_path = PROCESSED_DATA_PATH / "validation_report.csv"
    PROCESSED_DATA_PATH.mkdir(parents=True, exist_ok=True)
    report_df.to_csv(out_path, index=False)
    logger.info(f"  Validation report saved -> {out_path}")


# ── Main entry point ─────────────────────────────────────────────────────────

@timer
def validate_all(data: Dict[str, pd.DataFrame]) -> ValidationReport:
    """
    Run all validators against every dataset.

    Parameters
    ----------
    data : Dict[str, pd.DataFrame]
        Output from extract.extract_all().

    Returns
    -------
    ValidationReport
        Dict mapping each dataset name to its list of issue records.
        An empty list means no issues found.
    """
    logger.info("=" * 50)
    logger.info("VALIDATE PHASE -- data quality checks")
    logger.info("=" * 50)

    customers_df = data.get("customers", pd.DataFrame())
    products_df  = data.get("products",  pd.DataFrame())
    orders_df    = data.get("orders",    pd.DataFrame())
    sales_df     = data.get("sales",     pd.DataFrame())

    report: ValidationReport = {
        "customers": validate_customers(customers_df),
        "products":  validate_products(products_df),
        "orders":    validate_orders(orders_df, customers_df),
        "sales":     validate_sales(sales_df, orders_df, products_df),
    }

    all_issues = [issue for issues in report.values() for issue in issues]
    total_issues = len(all_issues)

    if total_issues == 0:
        logger.info("  [OK] All validation checks passed -- no issues found.")
    else:
        logger.warning(f"  (!)️  {total_issues} data quality issue(s) found.")
        _export_report(all_issues)

    logger.info("Validation phase complete.")
    return report
