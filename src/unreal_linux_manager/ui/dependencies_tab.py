"""Onglet "Dépendances" : vérifier et installer les prérequis Linux d'Unreal.

L'installation n'est jamais lancée sans que l'utilisateur ait vu les commandes,
et les commandes privilégiées (sudo / rpm-ostree) exigent une confirmation
explicite. Une simulation (dry-run) est toujours possible.
"""

from __future__ import annotations

from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtCore import QUrl
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
from ..core import constants
from ..core import dependency_manager as dm
from . import helpers
from .workers import TaskRunner

_STATUS_COLOR = {
    dm.STATUS_OK: QColor(30, 120, 40),
    dm.STATUS_MISSING: QColor(170, 30, 30),
    dm.STATUS_PROBLEM: QColor(170, 30, 30),
    dm.STATUS_OPTIONAL: QColor(160, 110, 0),
    dm.STATUS_NA: QColor(90, 90, 90),
}


class DependenciesTab(QWidget):
    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ctx = ctx
        self._tasks = TaskRunner(self)
        self._results: list[dm.DependencyResult] = []
        self._plan: dm.InstallPlan | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        intro = QLabel(
            "Vérifiez si votre PC Linux est prêt pour Unreal Engine, puis "
            "installez ce qui manque avec votre accord. Sur Bazzite / Fedora "
            "Atomic, l'application privilégie Flatpak, Homebrew et Distrobox et "
            "n'utilise rpm-ostree qu'en dernier recours, avec avertissement.")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self._os_label = QLabel("Système : —")
        layout.addWidget(self._os_label)

        top = QHBoxLayout()
        self._check_btn = QPushButton("Vérifier les dépendances")
        self._install_btn = QPushButton("Installer les dépendances manquantes")
        self._copy_btn = QPushButton("Copier les commandes")
        self._bazzite_btn = QPushButton("Ouvrir aide Bazzite")
        for b in (self._check_btn, self._install_btn, self._copy_btn, self._bazzite_btn):
            top.addWidget(b)
        top.addStretch(1)
        layout.addLayout(top)

        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(
            ["Dépendance", "État", "Catégorie", "Détail / Rôle"])
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self._table.setWordWrap(True)
        layout.addWidget(self._table)

        self._install_btn.setEnabled(False)
        self._copy_btn.setEnabled(False)

        self._check_btn.clicked.connect(self.check)
        self._install_btn.clicked.connect(self._on_install)
        self._copy_btn.clicked.connect(self._on_copy)
        self._bazzite_btn.clicked.connect(self._on_bazzite_help)

    # -- check -------------------------------------------------------------- #
    def check(self) -> None:
        self._check_btn.setEnabled(False)
        self._ctx.dependencies.os_info(refresh=True)
        self._tasks.start(
            self._ctx.dependencies.check_dependencies,
            on_finished=self._on_check_done,
            on_failed=self._on_failed,
        )

    def _on_check_done(self, results: list[dm.DependencyResult]) -> None:
        self._results = results
        self._check_btn.setEnabled(True)
        info = self._ctx.dependencies.os_info()
        self._os_label.setText(
            f"Système : {info.label} — Flatpak : {'oui' if info.has_flatpak else 'non'}, "
            f"Distrobox : {'oui' if info.has_distrobox else 'non'}, "
            f"Homebrew : {'oui' if info.has_brew else 'non'}, "
            f"rpm-ostree : {'oui' if info.has_rpm_ostree else 'non'}")

        self._table.setRowCount(len(results))
        for row, res in enumerate(results):
            name_item = QTableWidgetItem(res.dependency.display)
            status_item = QTableWidgetItem(res.status_label)
            color = _STATUS_COLOR.get(res.status)
            if color:
                status_item.setForeground(color)
            cat_item = QTableWidgetItem(res.dependency.category)
            detail = res.detail
            if res.hint:
                detail = f"{detail}\n→ {res.hint}" if detail else f"→ {res.hint}"
            detail_item = QTableWidgetItem(detail)
            detail_item.setToolTip(detail)
            for col, item in enumerate((name_item, status_item, cat_item, detail_item)):
                self._table.setItem(row, col, item)
        self._table.resizeRowsToContents()

        # Build the install plan for the missing (non-optional) dependencies.
        missing = self._ctx.dependencies.missing_installable(results)
        if missing:
            self._plan = self._ctx.dependencies.build_install_plan(missing)
            self._install_btn.setEnabled(True)
            self._copy_btn.setEnabled(True)
        else:
            self._plan = None
            self._install_btn.setEnabled(False)
            self._copy_btn.setEnabled(False)
            self._ctx.runner.log(
                "info", "Toutes les dépendances nécessaires sont présentes.")

    # -- install ------------------------------------------------------------ #
    def _on_install(self) -> None:
        if self._plan is None or self._plan.is_empty:
            helpers.info_box(self, "Rien à installer",
                             "Aucune dépendance manquante à installer.")
            return

        commands = self._ctx.dependencies.copy_install_commands(self._plan)
        dangerous = any(s.dangerous for s in self._plan.steps)
        needs_confirm = self._ctx.dependencies.confirm_before_system_install(self._plan)

        message = (
            "Voici les commandes qui seront exécutées :\n\n"
            f"{commands}\n\n"
        )
        if dangerous:
            message += (
                "ATTENTION : ce plan contient une commande rpm-ostree qui "
                "modifie l'image système et demandera probablement un "
                "redémarrage. Choisissez « Simuler » si vous préférez d'abord "
                "voir sans rien modifier.\n\n")
        elif needs_confirm:
            message += ("Ce plan contient des commandes privilégiées (sudo).\n\n")

        # Offer three choices: real install, dry-run, cancel.
        choice = helpers.three_way(
            self, "Installer les dépendances", message,
            yes_text="Installer", alt_text="Simuler (dry-run)", no_text="Annuler")
        if choice == "no":
            return
        dry_run = choice == "alt"

        self._install_btn.setEnabled(False)
        self._tasks.start(
            self._ctx.dependencies.install_dependencies, self._plan,
            dry_run=dry_run,
            on_finished=lambda ok: self._on_install_done(ok, dry_run),
            on_failed=self._on_failed,
        )

    def _on_install_done(self, ok: bool, dry_run: bool) -> None:
        self._install_btn.setEnabled(True)
        if dry_run:
            helpers.info_box(self, "Simulation terminée",
                             "Les commandes ont été affichées dans le Journal, "
                             "rien n'a été installé.")
            return
        if ok:
            helpers.info_box(self, "Installation terminée",
                             "Installation terminée. Relancez « Vérifier les "
                             "dépendances » pour confirmer.")
            self.check()
        else:
            helpers.warn_box(self, "Installation incomplète",
                             "Une ou plusieurs commandes ont échoué. Consultez "
                             "le Journal pour le détail.")

    def _on_copy(self) -> None:
        if self._plan is None:
            helpers.info_box(self, "Rien à copier",
                             "Lancez d'abord « Vérifier les dépendances ».")
            return
        helpers.copy_to_clipboard(self._ctx.dependencies.copy_install_commands(self._plan))
        helpers.info_box(self, "Commandes copiées",
                         "Les commandes d'installation ont été copiées.")

    def _on_bazzite_help(self) -> None:
        url = constants.BAZZITE_HELP_URL
        if not QDesktopServices.openUrl(QUrl(url)):
            self._ctx.runner.run_async(["xdg-open", url])

    def _on_failed(self, message: str) -> None:
        self._check_btn.setEnabled(True)
        self._install_btn.setEnabled(True)
        self._ctx.runner.log("error", message)
        helpers.error_box(self, "Erreur", message)
