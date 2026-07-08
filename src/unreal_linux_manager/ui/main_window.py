"""Main application window: tab bar + shared Journal panel."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QMainWindow,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .. import __app_name__, __version__
from ..app_context import AppContext
from .account_tab import AccountTab
from .diagnostics_tab import DiagnosticsTab
from .engines_tab import EnginesTab
from .journal import JournalPanel
from .plugins_tab import PluginsTab
from .projects_tab import ProjectsTab
from .settings_tab import SettingsTab


class MainWindow(QMainWindow):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self._ctx = ctx
        self.setWindowTitle(f"{__app_name__} {__version__}")
        self.resize(980, 720)

        # Journal panel first so the runner can log during tab construction.
        self._journal = JournalPanel()
        self._journal.set_verbose(ctx.config.verbose_logging)
        ctx.runner.add_sink(self._journal.log)

        # Tabs
        self._tabs = QTabWidget()
        self._account_tab = AccountTab(ctx)
        self._engines_tab = EnginesTab(ctx)
        self._projects_tab = ProjectsTab(ctx)
        self._plugins_tab = PluginsTab(ctx)
        self._diagnostics_tab = DiagnosticsTab(ctx)
        self._settings_tab = SettingsTab(ctx, on_saved=self._on_settings_saved)

        self._tabs.addTab(self._account_tab, "Compte Epic")
        self._tabs.addTab(self._engines_tab, "Moteurs")
        self._tabs.addTab(self._projects_tab, "Projets")
        self._tabs.addTab(self._plugins_tab, "Plugins / Assets")
        self._tabs.addTab(self._diagnostics_tab, "Diagnostics")
        self._tabs.addTab(self._settings_tab, "Paramètres")

        # Vertical splitter: tabs on top, Journal at the bottom.
        splitter = QSplitter(Qt.Vertical)
        top = QWidget()
        top_layout = QVBoxLayout(top)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.addWidget(self._tabs)
        splitter.addWidget(top)
        splitter.addWidget(self._journal)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([500, 200])

        self.setCentralWidget(splitter)

        status = QStatusBar()
        status.showMessage("Prêt.")
        self.setStatusBar(status)

        ctx.runner.log("info", f"{__app_name__} {__version__} démarré.")
        if ctx.system.is_atomic():
            ctx.runner.log(
                "warning",
                "Système immuable détecté. Utilisez Flatpak / AppImage / "
                "Distrobox / dossiers utilisateur ; évitez les modifications "
                "système.",
            )

    def _on_settings_saved(self) -> None:
        """Refresh dependent tabs when settings change."""
        self._journal.set_verbose(self._ctx.config.verbose_logging)
        self._engines_tab.scan()
        self._projects_tab.scan()
        self._plugins_tab.refresh_sources()

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt override)
        """Wait for background scan/diagnostic threads before quitting."""
        for tab in (
            self._account_tab, self._engines_tab, self._projects_tab,
            self._plugins_tab, self._diagnostics_tab,
        ):
            runner = getattr(tab, "_tasks", None)
            if runner is not None:
                runner.wait_all()
        super().closeEvent(event)
