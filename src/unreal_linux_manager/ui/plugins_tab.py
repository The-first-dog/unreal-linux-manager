"""Onglet "Plugins / Assets" : gérer les plugins de projet et moteur."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..app_context import AppContext
from ..core.engine_manager import EngineInfo
from ..core.plugin_manager import PluginInfo
from ..core.project_manager import ProjectInfo
from . import helpers
from .workers import TaskRunner


class PluginsTab(QWidget):
    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ctx = ctx
        self._tasks = TaskRunner(self)
        self._projects: list[ProjectInfo] = []
        self._engines: list[EngineInfo] = []
        self._plugins: list[PluginInfo] = []
        self._build_ui()
        self.refresh_sources()

    # -- UI ----------------------------------------------------------------- #
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Selection row
        sel = QHBoxLayout()
        sel.addWidget(QLabel("Projet :"))
        self._project_combo = QComboBox()
        self._project_combo.setMinimumWidth(220)
        sel.addWidget(self._project_combo)
        sel.addWidget(QLabel("Moteur :"))
        self._engine_combo = QComboBox()
        self._engine_combo.setMinimumWidth(220)
        sel.addWidget(self._engine_combo)
        self._refresh_btn = QPushButton("Rafraîchir")
        sel.addWidget(self._refresh_btn)
        self._scan_btn = QPushButton("Scanner les plugins")
        sel.addWidget(self._scan_btn)
        sel.addStretch(1)
        layout.addLayout(sel)

        # Plugin table
        self._table = QTableWidget(0, 4)
        self._table.setMinimumHeight(180)
        self._table.setHorizontalHeaderLabels(
            ["Plugin", "Portée", "Version", "Chemin"]
        )
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        layout.addWidget(self._table)

        # Project plugin actions
        actions = QHBoxLayout()
        self._add_local_btn = QPushButton("Ajouter plugin local")
        self._open_plugins_btn = QPushButton("Ouvrir dossier Plugins du projet")
        self._rebuild_btn = QPushButton("Reconstruire projet / GenerateProjectFiles")
        actions.addWidget(self._add_local_btn)
        actions.addWidget(self._open_plugins_btn)
        actions.addWidget(self._rebuild_btn)
        actions.addStretch(1)
        layout.addLayout(actions)

        # Epic Asset Manager / Marketplace group
        eam = QGroupBox("Assets Epic / Marketplace (Fab)")
        eam_layout = QVBoxLayout(eam)
        note = QLabel(
            "La gestion complète du Marketplace/Fab n'est pas réimplémentée. "
            "Utilisez Epic Asset Manager (Flatpak) pour télécharger vos assets, "
            "puis ajoutez-les comme plugins locaux."
        )
        note.setWordWrap(True)
        eam_layout.addWidget(note)
        self._eam_status = QLabel("Epic Asset Manager : vérification…")
        eam_layout.addWidget(self._eam_status)
        eam_row = QHBoxLayout()
        self._eam_launch_btn = QPushButton("Lancer Epic Asset Manager")
        self._eam_copy_btn = QPushButton("Copier la commande d'installation")
        eam_row.addWidget(self._eam_launch_btn)
        eam_row.addWidget(self._eam_copy_btn)
        eam_row.addStretch(1)
        eam_layout.addLayout(eam_row)
        layout.addWidget(eam)

        # Wire up
        self._refresh_btn.clicked.connect(self.refresh_sources)
        self._scan_btn.clicked.connect(self.scan_plugins)
        self._add_local_btn.clicked.connect(self._on_add_local)
        self._open_plugins_btn.clicked.connect(self._on_open_plugins)
        self._rebuild_btn.clicked.connect(self._on_rebuild)
        self._eam_launch_btn.clicked.connect(self._on_eam_launch)
        self._eam_copy_btn.clicked.connect(self._on_eam_copy)

    # -- sources ------------------------------------------------------------ #
    def refresh_sources(self) -> None:
        """Reload the project & engine combos, then check Epic Asset Manager."""
        self._tasks.start(
            self._ctx.projects.scan, self._ctx.config.project_scan_paths(),
            on_finished=self._on_projects_loaded,
            on_failed=lambda m: self._ctx.runner.log("error", m),
        )
        self._tasks.start(
            self._ctx.engines.scan, self._ctx.config.engine_scan_paths(),
            on_finished=self._on_engines_loaded,
            on_failed=lambda m: self._ctx.runner.log("error", m),
        )
        self._tasks.start(
            self._ctx.plugins.epic_asset_manager_installed,
            on_finished=self._on_eam_checked,
            on_failed=lambda m: self._ctx.runner.log("error", m),
        )

    def _on_projects_loaded(self, projects: list[ProjectInfo]) -> None:
        self._projects = projects
        self._project_combo.clear()
        for p in projects:
            self._project_combo.addItem(p.name, p.path)

    def _on_engines_loaded(self, engines: list[EngineInfo]) -> None:
        self._engines = engines
        self._engine_combo.clear()
        for e in engines:
            self._engine_combo.addItem(e.name, e.path)

    def _on_eam_checked(self, installed: bool) -> None:
        if installed:
            self._eam_status.setText("Epic Asset Manager : installé (Flatpak)")
            self._eam_launch_btn.setEnabled(True)
        else:
            self._eam_status.setText("Epic Asset Manager : non installé")
            self._eam_launch_btn.setEnabled(False)

    # -- plugin scan -------------------------------------------------------- #
    def scan_plugins(self) -> None:
        self._plugins = []
        project_path = self._project_combo.currentData()
        engine_path = self._engine_combo.currentData()

        def collect() -> list[PluginInfo]:
            result: list[PluginInfo] = []
            if project_path:
                result.extend(self._ctx.plugins.scan_project(str(project_path)))
            if engine_path:
                result.extend(self._ctx.plugins.scan_engine(str(engine_path)))
            return result

        self._tasks.start(
            collect,
            on_finished=self._on_plugins_done,
            on_failed=lambda m: self._ctx.runner.log("error", m),
        )

    def _on_plugins_done(self, plugins: list[PluginInfo]) -> None:
        self._plugins = plugins
        self._table.setRowCount(len(plugins))
        for row, plugin in enumerate(plugins):
            label = plugin.friendly_name or plugin.name
            values = [label, plugin.scope, plugin.version or "—", plugin.path]
            for col, text in enumerate(values):
                item = QTableWidgetItem(text)
                item.setToolTip(text)
                self._table.setItem(row, col, item)
        self._ctx.runner.log("info", f"{len(plugins)} plugin(s) listé(s).")

    # -- actions ------------------------------------------------------------ #
    def _on_add_local(self) -> None:
        project_path = self._project_combo.currentData()
        if not project_path:
            helpers.warn_box(self, "Aucun projet",
                             "Sélectionnez d'abord un projet.")
            return
        folder = QFileDialog.getExistingDirectory(
            self, "Choisir le dossier du plugin (contenant un .uplugin)",
        )
        if not folder:
            return
        try:
            dest = self._ctx.plugins.copy_plugin_to_project(folder, str(project_path))
        except ValueError as exc:
            helpers.error_box(self, "Ajout impossible", str(exc))
            return
        helpers.info_box(self, "Plugin ajouté", f"Plugin copié vers :\n{dest}")
        self.scan_plugins()

    def _on_open_plugins(self) -> None:
        project_path = self._project_combo.currentData()
        if not project_path:
            helpers.warn_box(self, "Aucun projet", "Sélectionnez d'abord un projet.")
            return
        self._ctx.plugins.open_plugins_folder(str(project_path))

    def _on_rebuild(self) -> None:
        project_path = self._project_combo.currentData()
        engine_path = self._engine_combo.currentData()
        if not project_path or not engine_path:
            helpers.warn_box(self, "Sélection incomplète",
                             "Sélectionnez un projet ET un moteur.")
            return
        self._ctx.projects.generate_project_files(str(engine_path), str(project_path))

    def _on_eam_launch(self) -> None:
        self._ctx.plugins.launch_epic_asset_manager()

    def _on_eam_copy(self) -> None:
        cmd = " ".join(self._ctx.plugins.epic_asset_manager_install_command())
        helpers.copy_to_clipboard(cmd)
        helpers.info_box(
            self, "Commande copiée",
            f"Commande copiée dans le presse-papiers :\n{cmd}",
        )
