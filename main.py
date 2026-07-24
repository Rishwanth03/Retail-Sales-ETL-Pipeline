"""
============================================================
scripts/main.py -- Retail Sales ETL Pipeline Orchestrator
============================================================
Purpose:
    Single entry point that runs the complete ETL pipeline:

    1. Connect to Database
    2. Extract      -- read raw CSV files
    3. Validate     -- data quality checks
    4. Transform    -- clean, enrich, build fact table
    5. Load         -- insert into PostgreSQL
    6. Analysis     -- run SQL business queries
    7. Export       -- results written to data/processed/analysis/
    8. Finish       -- log summary and dispose engine

Usage:
    python scripts/main.py

    Or from the project root:
    python -m scripts.main

Airflow:
    Wrap each phase in its own PythonOperator for DAG scheduling.
    See notebooks/ for a sample DAG template.
============================================================
"""

import sys
import time
from pathlib import Path
from typing import Dict

import pandas as pd

# ── Ensure project root is on sys.path ───────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.logger import get_logger
from scripts.database import get_engine, create_database_if_not_exists, dispose_engine
from scripts.extract import extract_all
from scripts.validate import validate_all
from scripts.transform import transform_all
from scripts.load import load_all
from scripts.analysis import run_all_analysis

# Import apply_schema from the database package
import importlib.util as _ilu
import pathlib as _pl
_db_init_path = _pl.Path(__file__).resolve().parent.parent / "database" / "create_database.py"
_spec = _ilu.spec_from_file_location("create_database", _db_init_path)
_db_mod = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_db_mod)
apply_schema = _db_mod.apply_schema

logger = get_logger("main")

PIPELINE_BANNER = """
╔══════════════════════════════════════════════════════╗
║      RETAIL SALES ETL PIPELINE  v1.0.0               ║
║      Author : Your Name                               ║
║      Stack  : Python · Pandas · SQLAlchemy · PostgreSQL║
╚══════════════════════════════════════════════════════╝
"""


def _log_validation_summary(report: Dict[str, list]) -> None:
    """Log a summary of validation findings."""
    total_issues = sum(len(issues) for issues in report.values())
    if total_issues == 0:
        logger.info("  [OK] Validation: PASSED -- no data quality issues found.")
    else:
        logger.warning(f"  (!)️  Validation: {total_issues} issue(s) found.")
        for dataset, issues in report.items():
            if issues:
                logger.warning(f"    * [{dataset}] {len(issues)} issue(s)")


def _log_analysis_summary(results: Dict[str, pd.DataFrame]) -> None:
    """Log a brief summary of the analysis results."""
    logger.info("  Analysis Results Summary:")
    for name, df in results.items():
        if not df.empty:
            logger.info(f"    [OK] {name}: {len(df)} row(s)")
        else:
            logger.warning(f"    (!)️  {name}: empty / failed")


def run_pipeline() -> bool:
    """
    Execute the complete ETL pipeline.

    Returns
    -------
    bool
        True if pipeline completed successfully, False otherwise.
    """
    pipeline_start = time.perf_counter()
    logger.info(PIPELINE_BANNER)
    logger.info("Pipeline started.")

    try:
        # ── STEP 1: Database Setup ───────────────────────────────────────────
        logger.info("─" * 55)
        logger.info("STEP 1 -- Database Setup")
        logger.info("─" * 55)
        create_database_if_not_exists()
        engine = get_engine()
        apply_schema(engine)
        logger.info("  Database ready.")

        # ── STEP 2: Extract ──────────────────────────────────────────────────
        logger.info("─" * 55)
        logger.info("STEP 2 -- Extract (read CSV files)")
        logger.info("─" * 55)
        raw_data = extract_all()

        # ── STEP 3: Validate ─────────────────────────────────────────────────
        logger.info("─" * 55)
        logger.info("STEP 3 -- Validate (data quality checks)")
        logger.info("─" * 55)
        validation_report = validate_all(raw_data)
        _log_validation_summary(validation_report)

        # ── STEP 4: Transform ────────────────────────────────────────────────
        logger.info("─" * 55)
        logger.info("STEP 4 -- Transform (clean & enrich)")
        logger.info("─" * 55)
        clean_data = transform_all(raw_data)

        # ── STEP 5: Load ─────────────────────────────────────────────────────
        logger.info("─" * 55)
        logger.info("STEP 5 -- Load (insert into PostgreSQL)")
        logger.info("─" * 55)
        load_all(clean_data, engine)

        # ── STEP 6: Analysis ─────────────────────────────────────────────────
        logger.info("─" * 55)
        logger.info("STEP 6 -- Analysis (SQL business queries)")
        logger.info("─" * 55)
        analysis_results = run_all_analysis(engine)
        _log_analysis_summary(analysis_results)

        # ── STEP 7: Finish ───────────────────────────────────────────────────
        elapsed = time.perf_counter() - pipeline_start
        logger.info("─" * 55)
        logger.info(f"[OK] Pipeline completed successfully in {elapsed:.2f}s.")
        logger.info(
            "  -> Cleaned files: data/cleaned/\n"
            "  -> Analysis CSVs: data/processed/analysis/\n"
            "  -> Logs:          logs/"
        )
        logger.info("─" * 55)
        return True

    except FileNotFoundError as exc:
        logger.critical(f"Pipeline aborted -- missing file: {exc}")
        return False
    except Exception as exc:
        logger.critical(f"Pipeline aborted -- unexpected error: {exc}", exc_info=True)
        return False
    finally:
        dispose_engine()


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    success = run_pipeline()
    sys.exit(0 if success else 1)
