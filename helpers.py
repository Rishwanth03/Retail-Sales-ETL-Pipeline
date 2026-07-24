"""
============================================================
scripts/helpers.py -- Shared Utility Functions
============================================================
Purpose:
    A collection of small, reusable helper functions used
    across multiple pipeline modules.  Keeping them here
    eliminates code duplication and makes the helpers easy
    to unit-test independently.

Inputs / Outputs:
    Each function is documented individually below.

Usage:
    from scripts.helpers import timer, is_valid_email, ...
============================================================
"""

import re
import time
import functools
from typing import Callable, Any
from pathlib import Path
from datetime import datetime

import pandas as pd

from scripts.logger import get_logger

logger = get_logger(__name__)


# ── Timing decorator ─────────────────────────────────────────────────────────

def timer(func: Callable) -> Callable:
    """
    Decorator that logs the execution time of any function.

    Usage:
        @timer
        def my_function(): ...
    """
    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        start = time.perf_counter()
        logger.info(f"[START] {func.__name__}()")
        result = func(*args, **kwargs)
        elapsed = time.perf_counter() - start
        logger.info(f"[END]   {func.__name__}() -- completed in {elapsed:.3f}s")
        return result
    return wrapper


# ── Email validation ─────────────────────────────────────────────────────────

_EMAIL_REGEX: re.Pattern = re.compile(
    r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$"
)


def is_valid_email(email: str) -> bool:
    """
    Return True if *email* matches a basic RFC-5321 pattern.

    Parameters
    ----------
    email : str
        Email address string to validate.

    Returns
    -------
    bool
    """
    if not isinstance(email, str):
        return False
    return bool(_EMAIL_REGEX.match(email.strip()))


# ── Path helpers ─────────────────────────────────────────────────────────────

def ensure_dir(path: str | Path) -> Path:
    """
    Create *path* (and any parents) if it doesn't exist.

    Parameters
    ----------
    path : str | Path

    Returns
    -------
    Path
        The resolved Path object.
    """
    resolved = Path(path).resolve()
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def resolve_path(base: str | Path, *parts: str) -> Path:
    """
    Build an absolute path by joining *base* with *parts*.

    Parameters
    ----------
    base : str | Path
    *parts : str

    Returns
    -------
    Path
    """
    return Path(base).resolve().joinpath(*parts)


# ── DataFrame helpers ────────────────────────────────────────────────────────

def strip_string_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Strip leading / trailing whitespace from all string columns.

    Parameters
    ----------
    df : pd.DataFrame

    Returns
    -------
    pd.DataFrame
    """
    str_cols = df.select_dtypes(include=["object", "string"]).columns
    df[str_cols] = df[str_cols].apply(lambda col: col.str.strip())
    return df


def coerce_dates(df: pd.DataFrame, date_cols: list[str]) -> pd.DataFrame:
    """
    Parse *date_cols* in *df* to datetime64, coercing errors to NaT.

    Parameters
    ----------
    df : pd.DataFrame
    date_cols : list[str]
        Column names to convert.

    Returns
    -------
    pd.DataFrame
    """
    for col in date_cols:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")
            n_invalid = df[col].isna().sum()
            if n_invalid:
                logger.warning(f"  {col}: {n_invalid} unparseable date(s) -> NaT")
    return df


def coerce_numeric(
    df: pd.DataFrame,
    cols: list[str],
    dtype: type = float,
) -> pd.DataFrame:
    """
    Cast *cols* in *df* to *dtype*, coercing errors to NaN / 0.

    Parameters
    ----------
    df : pd.DataFrame
    cols : list[str]
    dtype : type
        Target numeric type (float or int).

    Returns
    -------
    pd.DataFrame
    """
    for col in cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
            if dtype is int:
                df[col] = df[col].fillna(0).astype(int)
            else:
                df[col] = df[col].astype(float)
    return df


def drop_duplicate_rows(df: pd.DataFrame, subset: list[str] | None = None) -> pd.DataFrame:
    """
    Remove duplicate rows and log the count removed.

    Parameters
    ----------
    df : pd.DataFrame
    subset : list[str] | None
        Column names to consider. None -> all columns.

    Returns
    -------
    pd.DataFrame
    """
    before = len(df)
    df = df.drop_duplicates(subset=subset)
    removed = before - len(df)
    if removed:
        logger.info(f"  Removed {removed} duplicate row(s).")
    return df


# ── Export helpers ───────────────────────────────────────────────────────────

def export_dataframe(
    df: pd.DataFrame,
    output_dir: str | Path,
    filename: str,
    index: bool = False,
) -> Path:
    """
    Save *df* as a CSV file inside *output_dir*.

    Parameters
    ----------
    df : pd.DataFrame
    output_dir : str | Path
    filename : str
        File name without path (e.g. "top_customers.csv").
    index : bool
        Whether to write the DataFrame index.

    Returns
    -------
    Path
        Absolute path to the written file.
    """
    out_dir = ensure_dir(output_dir)
    out_path = out_dir / filename
    df.to_csv(out_path, index=index)
    logger.info(f"  Exported {len(df)} rows -> {out_path}")
    return out_path


# ── Date helpers ─────────────────────────────────────────────────────────────

def is_future_date(date_val: Any) -> bool:
    """
    Return True if *date_val* is a future datetime (> today).

    Parameters
    ----------
    date_val : Any
        Accepts datetime, pd.Timestamp, or ISO string.

    Returns
    -------
    bool
    """
    try:
        parsed = pd.Timestamp(date_val)
        return parsed > pd.Timestamp(datetime.now().date())
    except Exception:
        return False


# ── Logging summary helpers ──────────────────────────────────────────────────

def log_dataframe_info(df: pd.DataFrame, label: str) -> None:
    """
    Log shape, dtypes, and null counts for a DataFrame.

    Parameters
    ----------
    df : pd.DataFrame
    label : str
        Descriptive name logged alongside the stats.
    """
    logger.info(f"  [{label}] shape={df.shape}, columns={list(df.columns)}")
    null_counts = df.isnull().sum()
    null_summary = null_counts[null_counts > 0]
    if not null_summary.empty:
        logger.warning(f"  [{label}] nulls:\n{null_summary}")
