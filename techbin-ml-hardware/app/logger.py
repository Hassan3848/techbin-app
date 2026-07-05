"""
TechBin runtime logger.

This module provides one consistent logging setup for the whole Raspberry Pi
device runtime. All modules should use get_logger(__name__) instead of print().
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Final

from app.config import ensure_runtime_directories, settings


LOGGER_NAME: Final[str] = "techbin"
_LOG_FORMAT: Final[str] = (
    "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
)
_DATE_FORMAT: Final[str] = "%Y-%m-%d %H:%M:%S"

_MAX_LOG_FILE_BYTES: Final[int] = 2_000_000
_BACKUP_LOG_FILES: Final[int] = 5


def _parse_log_level(level_name: str) -> int:
    """
    Convert a text log level into a logging module level.

    If an invalid value is provided, INFO is used as the safe default.
    """

    normalized = level_name.strip().upper()

    return {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL,
    }.get(normalized, logging.INFO)


def _build_console_handler(level: int) -> logging.Handler:
    """
    Build a console handler for terminal output.
    """

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT))
    return handler


def _build_file_handler(log_file_path: Path, level: int) -> logging.Handler:
    """
    Build a rotating file handler.

    Rotation prevents the Pi from filling storage with one huge log file.
    """

    handler = RotatingFileHandler(
        filename=log_file_path,
        maxBytes=_MAX_LOG_FILE_BYTES,
        backupCount=_BACKUP_LOG_FILES,
        encoding="utf-8",
    )
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT))
    return handler


def configure_logging() -> logging.Logger:
    """
    Configure and return the base TechBin logger.

    This function is safe to call multiple times. It will not attach duplicate
    handlers if logging was already configured.
    """

    ensure_runtime_directories()

    level = _parse_log_level(settings.logging.log_level)
    log_file_path = settings.logs_dir / settings.logging.log_file_name

    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(level)
    logger.propagate = False

    if logger.handlers:
        return logger

    logger.addHandler(_build_console_handler(level))
    logger.addHandler(_build_file_handler(log_file_path, level))

    logger.info("TechBin logger initialized")
    logger.info("Log file: %s", log_file_path)

    return logger


def get_logger(module_name: str | None = None) -> logging.Logger:
    """
    Return a module-specific logger.

    Example:
        logger = get_logger(__name__)
    """

    configure_logging()

    if module_name is None or module_name.strip() == "":
        return logging.getLogger(LOGGER_NAME)

    clean_name = module_name.strip()

    if clean_name == LOGGER_NAME or clean_name.startswith(f"{LOGGER_NAME}."):
        return logging.getLogger(clean_name)

    return logging.getLogger(f"{LOGGER_NAME}.{clean_name}")


__all__ = [
    "configure_logging",
    "get_logger",
]
