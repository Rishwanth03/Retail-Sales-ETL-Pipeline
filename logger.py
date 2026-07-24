"""
============================================================
scripts/logger.py -- Centralized Logging Utility
============================================================
Purpose:
    Provides a reusable, configured Python logger that writes
    to both the console and a rotating log file.  All pipeline
    modules import this utility instead of calling logging
    directly, ensuring consistent formatting and log rotation
    across the entire project.

Inputs:
    name     (str)  - logger name, typically __name__
    log_file (str)  - optional override for the log filename

Outputs:
    logging.Logger instance configured with:
      * StreamHandler  -> coloured console output
      * RotatingFileHandler -> logs/<date>_retail_etl.log

Usage:
    from scripts.logger import get_logger
    logger = get_logger(__name__)
    logger.info("Pipeline started")
============================================================
"""

import logging
import sys
from logging.handlers import RotatingFileHandler
from datetime import datetime
from pathlib import Path

# ── Resolve log directory relative to this file ──────────────────────────────
_PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent
_LOG_DIR: Path = _PROJECT_ROOT / "logs"
_LOG_DIR.mkdir(parents=True, exist_ok=True)

# ── Log file name includes today's date for easy archival ───────────────────
_TODAY: str = datetime.now().strftime("%Y-%m-%d")
_LOG_FILE: Path = _LOG_DIR / f"{_TODAY}_retail_etl.log"

# ── Log format ───────────────────────────────────────────────────────────────
_LOG_FORMAT: str = (
    "%(asctime)s | %(levelname)-8s | %(name)-30s | %(message)s"
)
_DATE_FORMAT: str = "%Y-%m-%d %H:%M:%S"

# ── ANSI colour codes for console output ─────────────────────────────────────
_COLOURS: dict = {
    "DEBUG":    "\033[36m",   # Cyan
    "INFO":     "\033[32m",   # Green
    "WARNING":  "\033[33m",   # Yellow
    "ERROR":    "\033[31m",   # Red
    "CRITICAL": "\033[35m",   # Magenta
    "RESET":    "\033[0m",
}


class _ColouredFormatter(logging.Formatter):
    """Custom formatter that adds ANSI colours to console log levels."""

    def format(self, record: logging.LogRecord) -> str:  # noqa: A003
        colour = _COLOURS.get(record.levelname, _COLOURS["RESET"])
        reset = _COLOURS["RESET"]
        record.levelname = f"{colour}{record.levelname}{reset}"
        return super().format(record)


def get_logger(
    name: str = "retail_etl",
    log_file: str | None = None,
    level: int | str = logging.INFO,
) -> logging.Logger:
    """
    Return a configured Logger instance.

    Parameters
    ----------
    name : str
        Logger name. Use __name__ in each module for clear attribution.
    log_file : str | None
        Custom log file path. Defaults to logs/<date>_retail_etl.log.
    level : int | str
        Logging level (e.g. logging.DEBUG or "DEBUG"). Defaults to INFO.

    Returns
    -------
    logging.Logger
        Configured logger with console + file handlers.
    """
    logger = logging.getLogger(name)

    # Avoid adding duplicate handlers when the same logger is requested twice
    if logger.handlers:
        return logger

    logger.setLevel(level)

    # ── Console handler (coloured) ───────────────────────────────────────────
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(
        _ColouredFormatter(fmt=_LOG_FORMAT, datefmt=_DATE_FORMAT)
    )

    # ── File handler (rotating, plain text) ─────────────────────────────────
    file_path = Path(log_file) if log_file else _LOG_FILE
    file_handler = RotatingFileHandler(
        filename=str(file_path),
        maxBytes=10 * 1024 * 1024,   # 10 MB per file
        backupCount=5,                # Keep last 5 rotated files
        encoding="utf-8",
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(
        logging.Formatter(fmt=_LOG_FORMAT, datefmt=_DATE_FORMAT)
    )

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    # Prevent log records from propagating to the root logger
    logger.propagate = False

    return logger
