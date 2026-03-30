"""Dual-handler logging setup: Rich console (INFO) + file (DEBUG)."""

from __future__ import annotations

import logging
from pathlib import Path

from rich.logging import RichHandler

__all__ = ["get_logger", "setup_logging"]

_LOGGER_NAME = "creative_pipeline"
_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d | %(message)s"
_initialized = False


def setup_logging(
    log_level: str = "INFO",
    log_file: str | Path | None = None,
) -> logging.Logger:
    """Configure dual-handler logging for the pipeline.

    Args:
        log_level: Console handler log level (e.g., 'INFO', 'DEBUG').
        log_file: Optional path to log file. If provided, a file handler
            capturing DEBUG-level messages is added.

    Returns:
        Configured root logger for the pipeline.
    """
    global _initialized

    logger = logging.getLogger(_LOGGER_NAME)

    if _initialized:
        return logger

    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    # Console handler via Rich — user-friendly, colorized
    console_handler = RichHandler(
        rich_tracebacks=True,
        show_time=True,
        show_path=False,
        markup=True,
    )
    console_level = getattr(logging, log_level.upper(), logging.INFO)
    console_handler.setLevel(console_level)
    console_handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(console_handler)

    # File handler — full debug detail for troubleshooting
    if log_file is not None:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(str(log_path), mode="w", encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter(_LOG_FORMAT))
        logger.addHandler(file_handler)

    _initialized = True
    return logger


def get_logger(name: str | None = None) -> logging.Logger:
    """Get a child logger under the pipeline namespace.

    Args:
        name: Optional child logger name. If None, returns the root pipeline logger.

    Returns:
        Logger instance.
    """
    if name is None:
        return logging.getLogger(_LOGGER_NAME)
    return logging.getLogger(f"{_LOGGER_NAME}.{name}")


def reset_logging() -> None:
    """Reset logging state. Used in tests to allow re-initialization."""
    global _initialized
    logger = logging.getLogger(_LOGGER_NAME)
    logger.handlers.clear()
    _initialized = False
