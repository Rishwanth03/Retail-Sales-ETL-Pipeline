"""
============================================================
scripts/analysis.py -- SQL Analysis Module
============================================================
Purpose:
    Executes analytical SQL queries against the PostgreSQL
    sales_fact table and returns results as DataFrames.

    Queries provided:
    01. total_revenue          -- overall revenue KPI
    02. total_orders           -- count of distinct orders
    03. total_customers        -- count of unique customers
    04. avg_order_value        -- mean revenue per order
    05. top_customers          -- top 10 by total spend
    06. top_products           -- top 10 products by revenue
    07. monthly_revenue        -- revenue trend by year-month
    08. revenue_by_category    -- revenue breakdown by category
    09. revenue_by_state       -- revenue breakdown by state
    10. best_selling_products  -- products by quantity sold
    11. lowest_selling_products -- bottom 10 by units sold
    12. highest_profit_products -- top 10 by total profit
    13. repeat_customers        -- customers with > 1 order

    Each function:
    * Executes its query.
    * Logs row count returned.
    * Returns a pd.DataFrame.
    * Exports the result to data/processed/analysis/<name>.csv.

Inputs:
    SQLAlchemy Engine from database.py

Outputs:
    Dict[str, pd.DataFrame]
    CSV files in data/processed/analysis/

Usage:
    from scripts.analysis import run_all_analysis
    results = run_all_analysis(engine)
============================================================
"""

from __future__ import annotations

from typing import Dict

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from config.config import ANALYSIS_OUTPUT_PATH
from scripts.logger import get_logger
from scripts.helpers import timer, export_dataframe

logger = get_logger(__name__)


# ── Internal query runner ─────────────────────────────────────────────────────

def _run_query(sql: str, engine: Engine, label: str) -> pd.DataFrame:
    """
    Execute a SQL SELECT query and return the result as a DataFrame.

    Parameters
    ----------
    sql : str
        SQL query string.
    engine : Engine
        Active SQLAlchemy engine.
    label : str
        Human-readable name for logging.

    Returns
    -------
    pd.DataFrame
    """
    try:
        with engine.connect() as conn:
            df = pd.read_sql(text(sql), conn)
        logger.info(f"  [{label}] -> {len(df)} row(s)")
        return df
    except SQLAlchemyError as exc:
        logger.error(f"  [{label}] Query FAILED: {exc}")
        return pd.DataFrame()


# ── SQL query definitions ─────────────────────────────────────────────────────

_SQL = {

    "total_revenue": """
        SELECT
            ROUND(SUM(total_amount)::numeric, 2)  AS total_revenue,
            ROUND(SUM(profit)::numeric, 2)         AS total_profit,
            ROUND(AVG(profit_percentage)::numeric, 2) AS avg_profit_pct
        FROM sales_fact;
    """,

    "total_orders": """
        SELECT COUNT(DISTINCT order_id) AS total_orders
        FROM sales_fact;
    """,

    "total_customers": """
        SELECT COUNT(DISTINCT customer_id) AS total_customers
        FROM sales_fact;
    """,

    "avg_order_value": """
        SELECT
            ROUND(SUM(total_amount) / COUNT(DISTINCT order_id), 2)
            AS avg_order_value
        FROM sales_fact;
    """,

    "top_customers": """
        SELECT
            customer_id,
            customer_name,
            city,
            state,
            COUNT(DISTINCT order_id)              AS total_orders,
            SUM(quantity)                          AS total_units,
            ROUND(SUM(total_amount)::numeric, 2)  AS total_spent
        FROM sales_fact
        GROUP BY customer_id, customer_name, city, state
        ORDER BY total_spent DESC
        LIMIT 10;
    """,

    "top_products": """
        SELECT
            product_id,
            product_name,
            category,
            sub_category,
            SUM(quantity)                          AS units_sold,
            ROUND(SUM(total_amount)::numeric, 2)  AS revenue,
            ROUND(SUM(profit)::numeric, 2)         AS profit
        FROM sales_fact
        GROUP BY product_id, product_name, category, sub_category
        ORDER BY revenue DESC
        LIMIT 10;
    """,

    "monthly_revenue": """
        SELECT
            order_year,
            order_month,
            TO_CHAR(TO_DATE(order_month::text, 'MM'), 'Month') AS month_name,
            COUNT(DISTINCT order_id)              AS orders,
            ROUND(SUM(total_amount)::numeric, 2)  AS revenue,
            ROUND(SUM(profit)::numeric, 2)         AS profit
        FROM sales_fact
        GROUP BY order_year, order_month
        ORDER BY order_year, order_month;
    """,

    "revenue_by_category": """
        SELECT
            category,
            COUNT(DISTINCT product_id)             AS products,
            SUM(quantity)                           AS units_sold,
            ROUND(SUM(total_amount)::numeric, 2)   AS revenue,
            ROUND(SUM(profit)::numeric, 2)          AS profit,
            ROUND(AVG(profit_percentage)::numeric, 2) AS avg_profit_pct
        FROM sales_fact
        GROUP BY category
        ORDER BY revenue DESC;
    """,

    "revenue_by_state": """
        SELECT
            state,
            COUNT(DISTINCT customer_id)            AS customers,
            COUNT(DISTINCT order_id)               AS orders,
            ROUND(SUM(total_amount)::numeric, 2)   AS revenue,
            ROUND(SUM(profit)::numeric, 2)          AS profit
        FROM sales_fact
        GROUP BY state
        ORDER BY revenue DESC;
    """,

    "best_selling_products": """
        SELECT
            product_id,
            product_name,
            category,
            SUM(quantity)                           AS units_sold,
            ROUND(SUM(total_amount)::numeric, 2)    AS revenue
        FROM sales_fact
        GROUP BY product_id, product_name, category
        ORDER BY units_sold DESC
        LIMIT 10;
    """,

    "lowest_selling_products": """
        SELECT
            product_id,
            product_name,
            category,
            SUM(quantity)                           AS units_sold,
            ROUND(SUM(total_amount)::numeric, 2)    AS revenue
        FROM sales_fact
        GROUP BY product_id, product_name, category
        ORDER BY units_sold ASC
        LIMIT 10;
    """,

    "highest_profit_products": """
        SELECT
            product_id,
            product_name,
            category,
            ROUND(SUM(profit)::numeric, 2)            AS total_profit,
            ROUND(AVG(profit_percentage)::numeric, 2) AS avg_profit_pct,
            SUM(quantity)                              AS units_sold
        FROM sales_fact
        GROUP BY product_id, product_name, category
        ORDER BY total_profit DESC
        LIMIT 10;
    """,

    "repeat_customers": """
        SELECT
            customer_id,
            customer_name,
            state,
            COUNT(DISTINCT order_id)               AS order_count,
            ROUND(SUM(total_amount)::numeric, 2)   AS lifetime_value
        FROM sales_fact
        GROUP BY customer_id, customer_name, state
        HAVING COUNT(DISTINCT order_id) > 1
        ORDER BY order_count DESC, lifetime_value DESC;
    """,

    "quarterly_revenue": """
        SELECT
            order_year,
            order_quarter,
            ROUND(SUM(total_amount)::numeric, 2)  AS revenue,
            ROUND(SUM(profit)::numeric, 2)         AS profit,
            COUNT(DISTINCT order_id)               AS orders
        FROM sales_fact
        GROUP BY order_year, order_quarter
        ORDER BY order_year, order_quarter;
    """,

    "payment_method_analysis": """
        SELECT
            payment_method,
            COUNT(DISTINCT order_id)              AS orders,
            ROUND(SUM(total_amount)::numeric, 2)  AS revenue
        FROM sales_fact
        GROUP BY payment_method
        ORDER BY revenue DESC;
    """,
}


# ── Individual query functions ────────────────────────────────────────────────

def get_total_revenue(engine: Engine) -> pd.DataFrame:
    """Return total revenue, profit, and average profit % KPIs."""
    return _run_query(_SQL["total_revenue"], engine, "total_revenue")


def get_total_orders(engine: Engine) -> pd.DataFrame:
    """Return count of distinct orders."""
    return _run_query(_SQL["total_orders"], engine, "total_orders")


def get_total_customers(engine: Engine) -> pd.DataFrame:
    """Return count of unique customers."""
    return _run_query(_SQL["total_customers"], engine, "total_customers")


def get_avg_order_value(engine: Engine) -> pd.DataFrame:
    """Return average order value across all orders."""
    return _run_query(_SQL["avg_order_value"], engine, "avg_order_value")


def get_top_customers(engine: Engine) -> pd.DataFrame:
    """Return top 10 customers by total spend."""
    return _run_query(_SQL["top_customers"], engine, "top_customers")


def get_top_products(engine: Engine) -> pd.DataFrame:
    """Return top 10 products by revenue."""
    return _run_query(_SQL["top_products"], engine, "top_products")


def get_monthly_revenue(engine: Engine) -> pd.DataFrame:
    """Return revenue and profit aggregated by year-month."""
    return _run_query(_SQL["monthly_revenue"], engine, "monthly_revenue")


def get_revenue_by_category(engine: Engine) -> pd.DataFrame:
    """Return revenue, profit, and unit counts by product category."""
    return _run_query(_SQL["revenue_by_category"], engine, "revenue_by_category")


def get_revenue_by_state(engine: Engine) -> pd.DataFrame:
    """Return revenue and order counts by customer state."""
    return _run_query(_SQL["revenue_by_state"], engine, "revenue_by_state")


def get_best_selling_products(engine: Engine) -> pd.DataFrame:
    """Return top 10 products by units sold."""
    return _run_query(_SQL["best_selling_products"], engine, "best_selling_products")


def get_lowest_selling_products(engine: Engine) -> pd.DataFrame:
    """Return bottom 10 products by units sold."""
    return _run_query(_SQL["lowest_selling_products"], engine, "lowest_selling_products")


def get_highest_profit_products(engine: Engine) -> pd.DataFrame:
    """Return top 10 products by total profit generated."""
    return _run_query(_SQL["highest_profit_products"], engine, "highest_profit_products")


def get_repeat_customers(engine: Engine) -> pd.DataFrame:
    """Return customers who have placed more than one order."""
    return _run_query(_SQL["repeat_customers"], engine, "repeat_customers")


def get_quarterly_revenue(engine: Engine) -> pd.DataFrame:
    """Return revenue and profit by quarter."""
    return _run_query(_SQL["quarterly_revenue"], engine, "quarterly_revenue")


def get_payment_method_analysis(engine: Engine) -> pd.DataFrame:
    """Return order counts and revenue broken down by payment method."""
    return _run_query(_SQL["payment_method_analysis"], engine, "payment_method_analysis")


# ── Main entry point ─────────────────────────────────────────────────────────

@timer
def run_all_analysis(engine: Engine) -> Dict[str, pd.DataFrame]:
    """
    Execute all analytical queries and export results to CSV.

    Parameters
    ----------
    engine : Engine
        Active SQLAlchemy engine connected to RetailSalesDB.

    Returns
    -------
    Dict[str, pd.DataFrame]
        Analysis results keyed by query name.
    """
    logger.info("=" * 50)
    logger.info("ANALYSIS PHASE -- executing SQL queries")
    logger.info("=" * 50)

    # Build a registry of all query functions
    query_registry = {
        "01_total_revenue":           get_total_revenue,
        "02_total_orders":            get_total_orders,
        "03_total_customers":         get_total_customers,
        "04_avg_order_value":         get_avg_order_value,
        "05_top_customers":           get_top_customers,
        "06_top_products":            get_top_products,
        "07_monthly_revenue":         get_monthly_revenue,
        "08_revenue_by_category":     get_revenue_by_category,
        "09_revenue_by_state":        get_revenue_by_state,
        "10_best_selling_products":   get_best_selling_products,
        "11_lowest_selling_products": get_lowest_selling_products,
        "12_highest_profit_products": get_highest_profit_products,
        "13_repeat_customers":        get_repeat_customers,
        "14_quarterly_revenue":       get_quarterly_revenue,
        "15_payment_method_analysis": get_payment_method_analysis,
    }

    results: Dict[str, pd.DataFrame] = {}

    for name, query_fn in query_registry.items():
        try:
            df = query_fn(engine)
            results[name] = df
            if not df.empty:
                export_dataframe(df, ANALYSIS_OUTPUT_PATH, f"{name}.csv")
        except Exception as exc:
            logger.error(f"  [{name}] analysis failed: {exc}")
            results[name] = pd.DataFrame()

    success_count = sum(1 for df in results.values() if not df.empty)
    logger.info(
        f"Analysis phase complete -- "
        f"{success_count}/{len(query_registry)} queries succeeded."
    )
    return results
