"""Logging setup helpers for CLI and future background shells."""

from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger

_LOGGING_CONFIGURED = False


def configure_logging(project_root: Path) -> Path:
    """Configure console and file logging exactly once for the process."""

    global _LOGGING_CONFIGURED

    log_dir = project_root / "core" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "aradhya.log"

    if _LOGGING_CONFIGURED:
        return log_path

    logger.remove()
    logger.add(
        sys.stderr,
        level="INFO",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
    )
    # The rotating file keeps a longer audit trail for planner and voice
    # debugging without requiring the user to keep the terminal open.
    logger.add(
        log_path,
        level="DEBUG",
        rotation="1 MB",
        enqueue=False,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {name}:{function}:{line} | {message}",
    )
    _LOGGING_CONFIGURED = True
    logger.info("Logging initialized at {}", log_path)
    return log_path
