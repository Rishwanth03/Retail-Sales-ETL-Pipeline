"""
============================================================
scripts/database.py -- Database Connection Utility
============================================================
Purpose:
    Provides a reusable SQLAlchemy engine and a context-managed
    connection helper.  All pipeline modules that touch the
    database import from here -- never creating their own engines.

Inputs:
    DATABASE_URL from config/config.py (read from .env)

Outputs:
    SQLAlchemy Engine, Connection, and Session objects.

Usage:
    from scripts.database import get_engine, get_connection
    engine = get_engine()
    with get_connection(engine) as conn:
        result = conn.execute(text("SELECT 1"))
============================================================
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Generator

import sqlalchemy
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, Connection
from sqlalchemy.exc import OperationalError, SQLAlchemyError

from config.config import (
    DATABASE_URL,
    POSTGRES_DEFAULT_URL,
    DB_NAME,
    DB_POOL_SIZE,
    DB_MAX_OVERFLOW,
    DB_POOL_TIMEOUT,
)
from scripts.logger import get_logger

logger = get_logger(__name__)

# Module-level singleton engine (lazy-initialised)
_engine: Engine | None = None


# ── Engine factory ───────────────────────────────────────────────────────────

def get_engine(database_url: str | None = None) -> Engine:
    """
    Return (or create) the singleton SQLAlchemy engine.

    The engine is created once and reused for the lifetime of the process.
    Connection-pool settings come from config/config.py.

    Parameters
    ----------
    database_url : str | None
        Override the default URL (useful in tests or DB-creation scripts).

    Returns
    -------
    sqlalchemy.engine.Engine
    """
    global _engine

    if _engine is not None and database_url is None:
        return _engine

    url = database_url or DATABASE_URL
    logger.info(
        f"Creating SQLAlchemy engine -> "
        f"{url.split('@')[-1]}"   # log host/db only, never credentials
    )

    try:
        engine = create_engine(
            url,
            pool_size=DB_POOL_SIZE,
            max_overflow=DB_MAX_OVERFLOW,
            pool_timeout=DB_POOL_TIMEOUT,
            pool_pre_ping=True,          # validate connections before use
            echo=False,                  # set True for SQL debug output
        )
        # Quick connectivity check
        with engine.connect() as test_conn:
            test_conn.execute(text("SELECT 1"))

        logger.info("Database engine created and connection verified.")
        if database_url is None:
            _engine = engine
        return engine

    except OperationalError as exc:
        logger.error(f"Cannot connect to database: {exc}")
        raise
    except SQLAlchemyError as exc:
        logger.error(f"SQLAlchemy error during engine creation: {exc}")
        raise


# ── Context-managed connection ───────────────────────────────────────────────

@contextmanager
def get_connection(engine: Engine | None = None) -> Generator[Connection, None, None]:
    """
    Context manager that yields a database Connection and handles rollback.

    Commits on successful exit; rolls back and re-raises on exception.

    Parameters
    ----------
    engine : Engine | None
        Engine to use. Defaults to the singleton engine.

    Yields
    ------
    sqlalchemy.engine.Connection
    """
    _eng = engine or get_engine()
    conn = _eng.connect()
    try:
        yield conn
        conn.commit()
    except SQLAlchemyError as exc:
        conn.rollback()
        logger.error(f"Database error -- rolling back transaction: {exc}")
        raise
    finally:
        conn.close()


# ── Database existence check & creation ─────────────────────────────────────

def database_exists() -> bool:
    """
    Return True if the target RetailSalesDB database exists in PostgreSQL.

    Connects to the 'postgres' system database to query pg_database.

    Returns
    -------
    bool
    """
    try:
        # Must use isolation_level AUTOCOMMIT for DDL against pg_database
        admin_engine = create_engine(
            POSTGRES_DEFAULT_URL,
            isolation_level="AUTOCOMMIT",
        )
        with admin_engine.connect() as conn:
            result = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": DB_NAME},
            )
            return result.fetchone() is not None
    except OperationalError as exc:
        logger.error(f"Cannot check database existence: {exc}")
        raise
    finally:
        admin_engine.dispose()


def create_database_if_not_exists() -> None:
    """
    Create the RetailSalesDB PostgreSQL database if it doesn't already exist.

    Uses AUTOCOMMIT isolation level because CREATE DATABASE cannot run
    inside a transaction block in PostgreSQL.
    """
    if database_exists():
        logger.info(f"Database '{DB_NAME}' already exists -- skipping creation.")
        return

    logger.info(f"Creating database '{DB_NAME}' ...")
    try:
        admin_engine = create_engine(
            POSTGRES_DEFAULT_URL,
            isolation_level="AUTOCOMMIT",
        )
        with admin_engine.connect() as conn:
            conn.execute(text(f'CREATE DATABASE "{DB_NAME}"'))
        logger.info(f"Database '{DB_NAME}' created successfully.")
    except SQLAlchemyError as exc:
        logger.error(f"Failed to create database '{DB_NAME}': {exc}")
        raise
    finally:
        admin_engine.dispose()


# ── Engine disposal ──────────────────────────────────────────────────────────

def dispose_engine() -> None:
    """
    Dispose the singleton engine and release all pool connections.

    Call this at the end of the pipeline to cleanly shut down.
    """
    global _engine
    if _engine is not None:
        _engine.dispose()
        _engine = None
        logger.info("Database engine disposed -- all connections released.")
