from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from .config import ConfigStore
from .gui import MainWindow
from .linker import elevated_apply
from .logging_setup import configure_logging


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--elevated-apply", type=Path, default=None, help=argparse.SUPPRESS)
    return parser.parse_args()


def main() -> int:
    args = _args()
    logger = configure_logging()

    def exception_hook(exc_type, exc_value, traceback) -> None:
        logger.critical(
            "Unhandled application exception",
            exc_info=(exc_type, exc_value, traceback),
        )
        sys.__excepthook__(exc_type, exc_value, traceback)

    sys.excepthook = exception_hook

    # Elevated helper mode must not create a GUI, but it still writes to log.txt.
    if args.elevated_apply is not None:
        logger.info("Elevated Windows link helper started with plan: %s", args.elevated_apply)
        result = elevated_apply(args.elevated_apply)
        logger.info("Elevated Windows link helper finished with exit code %s", result)
        return result

    app = QApplication(sys.argv)
    app.setApplicationName("Remote Play Enabler")
    app.setOrganizationName("Remote Play Enabler")

    store = ConfigStore()
    logger.debug("Configuration file: %s", store.path)

    window = MainWindow(store, logger)
    window.show()
    result = app.exec()
    logger.info("Session ended with exit code %s", result)
    return result
