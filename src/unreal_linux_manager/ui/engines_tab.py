"""Onglet "Moteurs" : détecter, importer et lancer les moteurs Unreal."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..app_context import AppContext
from ..core.engine_manager import EngineInfo
from . import helpers
from .workers import TaskRunner


class EnginesTab(QWidget):
    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ctx = ctx
        self._tasks = TaskRunner(self)
        self._engines: list[EngineInfo] = []
        self._build_ui()
        self.scan()

    # -- UI ----------------------------------------------------------------- #
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Action buttons
        actions = QHBoxLayout()
        self._scan_btn = QPushButton("Scanner")
        self._import_btn = QPushButton("Importer ZIP officiel Unreal Linux")
        self._add_btn = QPushButton("Ajouter moteur existant")
        actions.addWidget(self._scan_btn)
        actions.addWidget(self._import_btn)
        actions.addWidget(self._add_btn)
        actions.addStretch(1)
        layout.addLayout(actions)

        # Engine table
        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["Nom / Version", "Chemin", "Taille", "Valide"])
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self._table.itemSelectionChanged.connect(self._update_buttons)
        layout.addWidget(self._table)

        # Per-engine action buttons
        row = QHBoxLayout()
        self._launch_btn = QPushButton("Lancer")
        self._open_btn = QPushButton("Ouvrir dossier")
        self._size_btn = QPushButton("Calculer la taille")
        self._toolchain_btn = QPushButton("Setup toolchain C++")
        self._remove_btn = QPushButton("Retirer de la liste")
        for b in (self._launch_btn, self._open_btn, self._size_btn,
                  self._toolchain_btn, self._remove_btn):
            row.addWidget(b)
        row.addStretch(1)
        layout.addLayout(row)

        # Progress bar (for ZIP import)
        self._progress = QProgressBar()
        self._progress.setVisible(False)
        layout.addWidget(self._progress)

        # Advanced: build from source
        adv = QGroupBox("Avancé : installer depuis les sources GitHub")
        adv_layout = QVBoxLayout(adv)
        adv_note = QLabel(
            "La compilation depuis les sources nécessite un compte GitHub lié à "
            "votre compte Epic (accès au dépôt privé EpicGames/UnrealEngine) et "
            "peut consommer plus de 100 Gio d'espace disque. Rien n'est compilé "
            "automatiquement : les commandes ci-dessous sont fournies à titre "
            "indicatif, à exécuter manuellement (idéalement dans un Distrobox "
            "sur système immuable)."
        )
        adv_note.setWordWrap(True)
        adv_layout.addWidget(adv_note)
        self._copy_source_btn = QPushButton("Copier les commandes de build")
        adv_layout.addWidget(self._copy_source_btn)
        layout.addWidget(adv)

        # Wire up
        self._scan_btn.clicked.connect(self.scan)
        self._import_btn.clicked.connect(self._on_import_zip)
        self._add_btn.clicked.connect(self._on_add_existing)
        self._launch_btn.clicked.connect(self._on_launch)
        self._open_btn.clicked.connect(self._on_open_folder)
        self._size_btn.clicked.connect(self._on_compute_size)
        self._toolchain_btn.clicked.connect(self._on_toolchain)
        self._remove_btn.clicked.connect(self._on_remove)
        self._copy_source_btn.clicked.connect(self._on_copy_source)

        self._update_buttons()

    # -- helpers ------------------------------------------------------------ #
    def _selected_engine(self) -> EngineInfo | None:
        rows = self._table.selectionModel().selectedRows()
        if not rows:
            return None
        index = rows[0].row()
        if 0 <= index < len(self._engines):
            return self._engines[index]
        return None

    def _update_buttons(self) -> None:
        has = self._selected_engine() is not None
        for b in (self._launch_btn, self._open_btn, self._size_btn,
                  self._toolchain_btn, self._remove_btn):
            b.setEnabled(has)

    def _populate(self) -> None:
        self._table.setRowCount(len(self._engines))
        for row, engine in enumerate(self._engines):
            valid = "Oui" if engine.exists else "NON"
            values = [engine.name, engine.path, engine.size_human, valid]
            for col, text in enumerate(values):
                item = QTableWidgetItem(text)
                item.setToolTip(text)
                self._table.setItem(row, col, item)
        self._update_buttons()

    # -- scan --------------------------------------------------------------- #
    def scan(self) -> None:
        scan_paths = self._ctx.config.engine_scan_paths()
        self._scan_btn.setEnabled(False)
        self._tasks.start(
            self._ctx.engines.scan, scan_paths,
            on_finished=self._on_scan_done,
            on_failed=self._on_task_failed,
        )

    def _on_scan_done(self, engines: list[EngineInfo]) -> None:
        self._engines = engines
        self._scan_btn.setEnabled(True)
        self._populate()

    def _on_task_failed(self, message: str) -> None:
        self._scan_btn.setEnabled(True)
        self._progress.setVisible(False)
        self._ctx.runner.log("error", message)
        helpers.error_box(self, "Erreur", message)

    # -- import ZIP --------------------------------------------------------- #
    def _on_import_zip(self) -> None:
        zip_path, _ = QFileDialog.getOpenFileName(
            self, "Choisir le ZIP officiel Unreal Engine (Linux)",
            str(Path.home()), "Archives ZIP (*.zip)",
        )
        if not zip_path:
            return
        default_dest = self._ctx.config.engines_dir
        default_dest.mkdir(parents=True, exist_ok=True)
        suggested = str(default_dest / Path(zip_path).stem)
        dest = QFileDialog.getExistingDirectory(
            self, "Dossier de destination du moteur", str(default_dest),
        )
        if not dest:
            return
        # Extract into a sub-folder named after the archive to stay tidy.
        target = Path(dest)
        if target == default_dest:
            target = default_dest / Path(zip_path).stem

        self._progress.setVisible(True)
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._import_btn.setEnabled(False)

        self._tasks.start(
            self._ctx.engines.import_engine_zip, zip_path, str(target),
            on_finished=self._on_import_done,
            on_failed=self._on_import_failed,
            on_progress=self._on_progress,
        )

    def _on_progress(self, done: int, total: int) -> None:
        if total > 0:
            self._progress.setValue(int(done * 100 / total))

    def _on_import_done(self, engine: EngineInfo) -> None:
        self._progress.setVisible(False)
        self._import_btn.setEnabled(True)
        helpers.info_box(
            self, "Import terminé",
            f"Moteur importé :\n{engine.name}\n{engine.path}",
        )
        self.scan()

    def _on_import_failed(self, message: str) -> None:
        self._progress.setVisible(False)
        self._import_btn.setEnabled(True)
        self._ctx.runner.log("error", message)
        helpers.error_box(self, "Import échoué", message)

    # -- add existing ------------------------------------------------------- #
    def _on_add_existing(self) -> None:
        directory = QFileDialog.getExistingDirectory(
            self, "Choisir le dossier racine d'un moteur Unreal existant",
            str(self._ctx.config.engines_dir),
        )
        if not directory:
            return
        from ..core import engine_manager

        if not engine_manager.is_valid_engine(directory):
            helpers.warn_box(
                self, "Moteur invalide",
                "Ce dossier ne contient pas "
                "'Engine/Binaries/Linux/UnrealEditor'.",
            )
            return
        # Persist as an extra scan path so it survives restarts.
        self._ctx.config.add_engine_scan_path(directory)
        self._ctx.config.save()
        self.scan()

    # -- per engine actions ------------------------------------------------- #
    def _on_launch(self) -> None:
        engine = self._selected_engine()
        if not engine:
            return
        if not engine.exists:
            helpers.error_box(self, "Lancement impossible",
                              "Le binaire UnrealEditor est introuvable.")
            return
        self._ctx.engines.launch_engine(
            engine.path,
            env=self._ctx.config.launch_env,
            extra_args=self._ctx.config.launch_extra_args,
        )
        self._ctx.runner.log("info", f"Lancement du moteur : {engine.name}")

    def _on_open_folder(self) -> None:
        engine = self._selected_engine()
        if engine:
            self._ctx.runner.run_async(["xdg-open", engine.path])

    def _on_compute_size(self) -> None:
        engine = self._selected_engine()
        if not engine:
            return
        from ..core.engine_manager import estimate_folder_size

        self._size_btn.setEnabled(False)
        self._tasks.start(
            estimate_folder_size, engine.path,
            on_finished=lambda size: self._on_size_done(engine, size),
            on_failed=self._on_task_failed,
        )

    def _on_size_done(self, engine: EngineInfo, size: int) -> None:
        engine.size_bytes = size
        self._size_btn.setEnabled(True)
        self._populate()

    def _on_toolchain(self) -> None:
        engine = self._selected_engine()
        if not engine:
            return
        if not helpers.confirm(
            self, "Setup toolchain",
            "Lancer le script SetupToolchain.sh du moteur ? "
            "Cela peut télécharger des composants de compilation.",
        ):
            return
        self._ctx.engines.setup_toolchain(engine.path)

    def _on_remove(self) -> None:
        engine = self._selected_engine()
        if not engine:
            return
        if not helpers.confirm(
            self, "Retirer de la liste",
            "Retirer ce moteur de la liste ? Les fichiers sur le disque ne "
            "seront PAS supprimés ; seul le chemin de scan personnalisé est "
            "retiré s'il en existe un.",
        ):
            return
        extra = self._ctx.config.get("paths", "extra_engine_scan_paths", []) or []
        new_extra = [p for p in extra if str(Path(p).expanduser()) != engine.path
                     and p != engine.path]
        self._ctx.config.set("paths", "extra_engine_scan_paths", new_extra)
        self._ctx.config.save()
        self.scan()

    def _on_copy_source(self) -> None:
        commands = (
            "# Prérequis : compte GitHub lié à Epic (accès au dépôt privé).\n"
            "# Idéalement dans un conteneur Distrobox sur système immuable.\n"
            "git clone https://github.com/EpicGames/UnrealEngine.git\n"
            "cd UnrealEngine\n"
            "./Setup.sh\n"
            "./GenerateProjectFiles.sh\n"
            "make\n"
        )
        helpers.copy_to_clipboard(commands)
        helpers.info_box(
            self, "Commandes copiées",
            "Les commandes de compilation ont été copiées dans le "
            "presse-papiers. Exécutez-les manuellement après avoir vérifié "
            "l'espace disque disponible.",
        )
