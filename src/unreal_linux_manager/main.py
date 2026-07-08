"""Application entry point for Unreal Linux Manager.

Sets up logging, builds the shared :class:`AppContext`, creates the Qt
application and shows the main window.
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler

from . import __app_name__
from .core import paths


def _setup_logging(verbose: bool = False) -> None:
    """Configure root logging to a rotating file in the state directory."""
    paths.ensure_runtime_dirs()
    log_file = paths.logs_dir() / "unreal-linux-manager.log"

    root = logging.getLogger("unreal_linux_manager")
    root.setLevel(logging.DEBUG if verbose else logging.INFO)
    root.handlers.clear()

    try:
        handler = RotatingFileHandler(
            log_file, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
        )
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        )
        root.addHandler(handler)
    except OSError:
        # If the log file cannot be created, fall back to stderr only.
        stream = logging.StreamHandler()
        root.addHandler(stream)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)

    # Import Qt lazily so ``--help`` / import errors give a clean message.
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError as exc:  # pragma: no cover
        sys.stderr.write(
            "Erreur : PySide6 est introuvable.\n"
            "Installez les dépendances avec ./install_local.sh ou "
            "'pip install -r requirements.txt'.\n"
            f"Détail : {exc}\n"
        )
        return 1

    from .app_context import AppContext
    from .ui.main_window import MainWindow

    # Build context (loads config) before configuring verbose logging.
    ctx = AppContext()
    _setup_logging(ctx.config.verbose_logging)
    logging.getLogger("unreal_linux_manager").info("%s démarrage.", __app_name__)

    app = QApplication(argv)
    app.setApplicationName(__app_name__)
    # Use the platform's native style; no forced dark theme or custom CSS.

    window = MainWindow(ctx)
    window.show()
    return app.exec()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
