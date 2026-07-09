"""Onglet "Projets" : lister et lancer les projets .uproject."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
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
from ..core.project_manager import ProjectInfo
from . import helpers
from .workers import TaskRunner


class ProjectsTab(QWidget):
    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ctx = ctx
        self._tasks = TaskRunner(self)
        self._projects: list[ProjectInfo] = []
        self._engines: list[EngineInfo] = []
        self._build_ui()
        self.scan()

    # -- UI ----------------------------------------------------------------- #
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        top = QHBoxLayout()
        self._scan_btn = QPushButton("Scanner")
        top.addWidget(self._scan_btn)
        top.addWidget(QLabel("Moteur à utiliser :"))
        self._engine_combo = QComboBox()
        self._engine_combo.setMinimumWidth(280)
        top.addWidget(self._engine_combo)
        self._set_default_btn = QPushButton("Définir par défaut")
        top.addWidget(self._set_default_btn)
        self._launch_editor_btn = QPushButton("Lancer l'éditeur (sans projet)")
        top.addWidget(self._launch_editor_btn)
        top.addStretch(1)
        layout.addLayout(top)

        self._table = QTableWidget(0, 4)
        self._table.setMinimumHeight(180)
        self._table.setHorizontalHeaderLabels(
            ["Projet", "Chemin", "Moteur associé", "Modifié le"]
        )
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self._table.itemSelectionChanged.connect(self._update_buttons)
        layout.addWidget(self._table)

        row = QHBoxLayout()
        self._launch_btn = QPushButton("Lancer avec le moteur sélectionné")
        self._open_btn = QPushButton("Ouvrir dossier")
        self._code_btn = QPushButton("Ouvrir dans VS Code")
        self._genfiles_btn = QPushButton("Générer fichiers projet")
        for b in (self._launch_btn, self._open_btn, self._code_btn, self._genfiles_btn):
            row.addWidget(b)
        row.addStretch(1)
        layout.addLayout(row)

        self._scan_btn.clicked.connect(self.scan)
        self._launch_btn.clicked.connect(self._on_launch)
        self._open_btn.clicked.connect(self._on_open_folder)
        self._code_btn.clicked.connect(self._on_open_code)
        self._genfiles_btn.clicked.connect(self._on_generate_files)
        self._launch_editor_btn.clicked.connect(self._on_launch_editor_only)
        self._set_default_btn.clicked.connect(self._on_set_default_engine)

        self._update_buttons()

    # -- data --------------------------------------------------------------- #
    def scan(self) -> None:
        self._scan_btn.setEnabled(False)
        # Refresh engine list (fast, no size computation) then projects.
        self._tasks.start(
            self._ctx.engines.scan, self._ctx.config.engine_scan_paths(),
            on_finished=self._on_engines_done,
            on_failed=self._on_failed,
        )

    def _on_engines_done(self, engines: list[EngineInfo]) -> None:
        self._engines = engines
        self._refresh_engine_combo()
        self._tasks.start(
            self._ctx.projects.scan, self._ctx.config.project_scan_paths(),
            on_finished=self._on_projects_done,
            on_failed=self._on_failed,
        )

    def _on_projects_done(self, projects: list[ProjectInfo]) -> None:
        self._projects = projects
        self._scan_btn.setEnabled(True)
        self._populate()

    def _on_failed(self, message: str) -> None:
        self._scan_btn.setEnabled(True)
        self._ctx.runner.log("error", message)
        helpers.error_box(self, "Erreur", message)

    def _refresh_engine_combo(self) -> None:
        current = self._current_engine_path()
        self._engine_combo.clear()
        default_path = self._ctx.config.default_engine_path
        selected_index = 0
        for i, engine in enumerate(self._engines):
            self._engine_combo.addItem(engine.name, engine.path)
            if engine.path in (current, default_path):
                selected_index = i
        if self._engines:
            self._engine_combo.setCurrentIndex(selected_index)

    def _current_engine_path(self) -> str | None:
        data = self._engine_combo.currentData()
        return str(data) if data else None

    def _populate(self) -> None:
        self._table.setRowCount(len(self._projects))
        for row, project in enumerate(self._projects):
            engine_assoc = project.engine_association or "—"
            values = [project.name, project.path, engine_assoc, project.modified_human]
            for col, text in enumerate(values):
                item = QTableWidgetItem(text)
                item.setToolTip(text)
                self._table.setItem(row, col, item)
        self._update_buttons()

    def _selected_project(self) -> ProjectInfo | None:
        rows = self._table.selectionModel().selectedRows()
        if not rows:
            return None
        index = rows[0].row()
        if 0 <= index < len(self._projects):
            return self._projects[index]
        return None

    def _update_buttons(self) -> None:
        has = self._selected_project() is not None
        for b in (self._launch_btn, self._open_btn, self._code_btn, self._genfiles_btn):
            b.setEnabled(has)

    # -- actions ------------------------------------------------------------ #
    def _on_set_default_engine(self) -> None:
        path = self._current_engine_path()
        if not path:
            helpers.warn_box(self, "Aucun moteur", "Aucun moteur sélectionné.")
            return
        self._ctx.config.default_engine_path = path
        self._ctx.config.save()
        helpers.info_box(self, "Moteur par défaut",
                         f"Moteur par défaut défini :\n{path}")

    def _on_launch(self) -> None:
        project = self._selected_project()
        engine_path = self._current_engine_path()
        if not project:
            return
        if not engine_path:
            helpers.warn_box(self, "Aucun moteur",
                             "Sélectionnez un moteur dans la liste déroulante.")
            return
        self._ctx.engines.launch_project(
            engine_path, project.path,
            env=self._ctx.config.launch_env,
            extra_args=self._ctx.config.launch_extra_args,
        )
        self._ctx.runner.log("info", f"Lancement de {project.name} avec {engine_path}")

    def _on_launch_editor_only(self) -> None:
        engine_path = self._current_engine_path()
        if not engine_path:
            helpers.warn_box(self, "Aucun moteur",
                             "Aucun moteur disponible. Importez-en un d'abord.")
            return
        self._ctx.engines.launch_engine(
            engine_path,
            env=self._ctx.config.launch_env,
            extra_args=self._ctx.config.launch_extra_args,
        )

    def _on_open_folder(self) -> None:
        project = self._selected_project()
        if project:
            self._ctx.projects.open_project_folder(project.path)

    def _on_open_code(self) -> None:
        project = self._selected_project()
        if project:
            self._ctx.projects.open_in_editor(project.path)

    def _on_generate_files(self) -> None:
        project = self._selected_project()
        engine_path = self._current_engine_path()
        if not project:
            return
        if not engine_path:
            helpers.warn_box(self, "Aucun moteur",
                             "Sélectionnez un moteur pour générer les fichiers.")
            return
        self._ctx.projects.generate_project_files(engine_path, project.path)
