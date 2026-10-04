from __future__ import annotations

import logging
import platform
import sys
from pathlib import Path

from . import __version__
from .config import app_data_dir


def log_file_path() -> Path:
    """Persistent plain-text log shared by all app sessions."""
    return app_data_dir() / "log.txt"


def configure_logging() -> logging.Logger:
    logger = logging.getLogger("remote_play_enabler")
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    # Avoid duplicate handlers if configure_logging() is called twice in one process.
    if not any(getattr(h, "_rpe_file_handler", False) for h in logger.handlers):
        handler = logging.FileHandler(log_file_path(), mode="a", encoding="utf-8")
        handler._rpe_file_handler = True  # type: ignore[attr-defined]
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(
            logging.Formatter("[%(asctime)s] %(levelname)-8s %(name)s: %(message)s")
        )
        logger.addHandler(handler)

    logger.info("")
    logger.info("=" * 78)
    logger.info("Remote Play Enabler v%s - session started", __version__)
    logger.info("Platform: %s | Python: %s", platform.platform(), sys.version.replace("\n", " "))
    logger.info("Executable: %s", sys.executable)
    logger.info("Log file: %s", log_file_path())
    return logger
