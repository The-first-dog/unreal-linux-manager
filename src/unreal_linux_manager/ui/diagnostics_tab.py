"""Onglet "Diagnostics" : vérifier que Linux est prêt pour Unreal."""

from __future__ import annotations

from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
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
from ..core.system_check import CheckResult
from . import helpers
from .workers import TaskRunner

# Sober status colours applied only to the small status cell, no gradients or
# effects. Chosen to remain readable on both light and dark system themes.
_STATUS_STYLE = {
    "ok": ("OK", QColor(30, 120, 40)),
    "warn": ("Attention", QColor(160, 110, 0)),
    "error": ("Problème", QColor(170, 30, 30)),
    "info": ("Info", QColor(60, 60, 60)),
}


class DiagnosticsTab(QWidget):
    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ctx = ctx
        self._tasks = TaskRunner(self)
        self._results: list[CheckResult] = []
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        intro = QLabel(
            "Diagnostic de compatibilité Unreal Engine sous Linux. "
            "Les résultats sont indicatifs et n'exécutent aucune commande "
            "privilégiée."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        top = QHBoxLayout()
        self._run_btn = QPushButton("Diagnostic")
        self._copy_btn = QPushButton("Copier le rapport")
        top.addWidget(self._run_btn)
        top.addWidget(self._copy_btn)
        top.addStretch(1)
        layout.addLayout(top)

        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(["Test", "État", "Détail / Conseil"])
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self._table.setWordWrap(True)
        layout.addWidget(self._table)

        self._run_btn.clicked.connect(self.run)
        self._copy_btn.clicked.connect(self._copy_report)

    def run(self) -> None:
        self._run_btn.setEnabled(False)
        engine_paths = self._ctx.config.engine_scan_paths()
        disk_dirs = [
            str(self._ctx.config.engines_dir),
            str(self._ctx.config.projects_dir),
        ]

        def do_checks() -> list[CheckResult]:
            return self._ctx.system.run_all(
                engine_scan_paths=engine_paths, disk_dirs=disk_dirs
            )

        self._tasks.start(
            do_checks,
            on_finished=self._on_done,
            on_failed=self._on_failed,
        )

    def _on_done(self, results: list[CheckResult]) -> None:
        self._results = results
        self._run_btn.setEnabled(True)
        self._table.setRowCount(len(results))
        for row, res in enumerate(results):
            label, color = _STATUS_STYLE.get(res.status, _STATUS_STYLE["info"])

            name_item = QTableWidgetItem(res.name)
            status_item = QTableWidgetItem(label)
            status_item.setForeground(color)

            detail = res.detail
            if res.hint:
                detail = f"{detail}\n→ {res.hint}" if detail else f"→ {res.hint}"
            detail_item = QTableWidgetItem(detail)
            detail_item.setToolTip(detail)

            self._table.setItem(row, 0, name_item)
            self._table.setItem(row, 1, status_item)
            self._table.setItem(row, 2, detail_item)
        self._table.resizeRowsToContents()

    def _on_failed(self, message: str) -> None:
        self._run_btn.setEnabled(True)
        helpers.error_box(self, "Diagnostic échoué", message)

    def _copy_report(self) -> None:
        if not self._results:
            helpers.info_box(self, "Rapport vide",
                             "Lancez d'abord un diagnostic.")
            return
        lines = ["Rapport de diagnostic Unreal Linux Manager", "=" * 44]
        for res in self._results:
            label = _STATUS_STYLE.get(res.status, _STATUS_STYLE["info"])[0]
            lines.append(f"[{label}] {res.name}: {res.detail}")
            if res.hint:
                lines.append(f"    → {res.hint}")
        helpers.copy_to_clipboard("\n".join(lines))
        helpers.info_box(self, "Rapport copié",
                         "Le rapport de diagnostic a été copié.")
