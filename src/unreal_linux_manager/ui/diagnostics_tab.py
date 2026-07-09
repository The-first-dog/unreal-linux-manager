"""Onglet "Diagnostics" : un vrai rapport lisible sur l'état du système."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ..app_context import AppContext
from ..core import diagnostic_report, paths
from . import helpers
from .workers import TaskRunner


@dataclass
class _Gathered:
    """All data collected by a single diagnostic run."""

    report_text: str


class DiagnosticsTab(QWidget):
    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ctx = ctx
        self._tasks = TaskRunner(self)
        self._report_text = ""
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        intro = QLabel(
            "Rapport de compatibilité Unreal Engine sous Linux. Aucune commande "
            "privilégiée n'est exécutée. Le rapport ne contient aucun token Epic.")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        top = QHBoxLayout()
        self._run_btn = QPushButton("Diagnostic")
        self._copy_btn = QPushButton("Copier le rapport")
        self._export_btn = QPushButton("Exporter diagnostic")
        top.addWidget(self._run_btn)
        top.addWidget(self._copy_btn)
        top.addWidget(self._export_btn)
        top.addStretch(1)
        layout.addLayout(top)

        self._view = QTextBrowser()
        mono = QFont("monospace")
        mono.setStyleHint(QFont.Monospace)
        self._view.setFont(mono)
        self._view.setPlainText(
            "Cliquez sur « Diagnostic » pour générer le rapport.")
        layout.addWidget(self._view)

        self._copy_btn.setEnabled(False)
        self._export_btn.setEnabled(False)

        self._run_btn.clicked.connect(self.run)
        self._copy_btn.clicked.connect(self._on_copy)
        self._export_btn.clicked.connect(self._on_export)

    # -- run ---------------------------------------------------------------- #
    def run(self) -> None:
        self._run_btn.setEnabled(False)
        self._view.setPlainText("Diagnostic en cours…")
        ctx = self._ctx

        def gather() -> _Gathered:
            os_info = ctx.dependencies.os_info(refresh=True)
            engine_paths = ctx.config.engine_scan_paths()
            disk_dirs = [
                str(ctx.config.engines_dir),
                str(ctx.config.projects_dir),
                str(ctx.config.vault_dir),
            ]
            sys_results = ctx.system.run_all(
                engine_scan_paths=engine_paths, disk_dirs=disk_dirs)
            dep_results = ctx.dependencies.check_dependencies()
            engines = ctx.engines.scan(engine_paths)
            projects = ctx.projects.scan(ctx.config.project_scan_paths())
            epic_state = ctx.epic.refresh_status()
            text = diagnostic_report.build_report(
                os_info=os_info,
                sys_results=sys_results,
                dep_results=dep_results,
                engines=engines,
                projects=projects,
                epic_state=epic_state,
                config=ctx.config,
            )
            return _Gathered(report_text=text)

        self._tasks.start(
            gather,
            on_finished=self._on_done,
            on_failed=self._on_failed,
        )

    def _on_done(self, data: _Gathered) -> None:
        self._run_btn.setEnabled(True)
        self._report_text = data.report_text
        self._view.setPlainText(data.report_text)
        self._copy_btn.setEnabled(True)
        self._export_btn.setEnabled(True)

    def _on_failed(self, message: str) -> None:
        self._run_btn.setEnabled(True)
        self._view.setPlainText(f"Le diagnostic a échoué :\n{message}")
        helpers.error_box(self, "Diagnostic échoué", message)

    # -- export / copy ------------------------------------------------------ #
    def _on_copy(self) -> None:
        if not self._report_text:
            return
        helpers.copy_to_clipboard(self._report_text)
        helpers.info_box(self, "Rapport copié", "Le rapport a été copié.")

    def _on_export(self) -> None:
        if not self._report_text:
            return
        paths.ensure_runtime_dirs()
        target = paths.state_dir() / "diagnostic_report.txt"
        try:
            target.write_text(self._report_text, encoding="utf-8")
        except OSError as exc:
            helpers.error_box(self, "Export impossible",
                              f"Impossible d'écrire le rapport :\n{exc}")
            return
        self._ctx.runner.log("info", f"Rapport de diagnostic exporté : {target}")
        helpers.info_box(self, "Rapport exporté",
                         f"Rapport enregistré dans :\n{target}")
