"""Onglet "Compte Epic".

Shows the Epic connection state and lets the user authenticate through
Legendary (secure browser OAuth). The application never asks for or stores the
Epic password. A fully manual "no account / ZIP import" mode is always offered.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..app_context import AppContext
from . import helpers
from .workers import TaskRunner


class AccountTab(QWidget):
    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ctx = ctx
        self._tasks = TaskRunner(self)
        self._build_ui()
        self.refresh()

    # -- UI ----------------------------------------------------------------- #
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Status group
        status_group = QGroupBox("État de connexion Epic")
        status_layout = QVBoxLayout(status_group)
        self._status_label = QLabel("État : inconnu")
        self._method_label = QLabel("Méthode : —")
        self._legendary_label = QLabel("Legendary : recherche…")
        for lbl in (self._status_label, self._method_label, self._legendary_label):
            lbl.setTextInteractionFlags(lbl.textInteractionFlags())
            status_layout.addWidget(lbl)
        layout.addWidget(status_group)

        # Legendary actions
        legendary_group = QGroupBox("Legendary (connexion sécurisée par navigateur)")
        lg_layout = QVBoxLayout(legendary_group)

        note = QLabel(
            "La connexion Epic passe par Legendary, qui ouvre une page de "
            "connexion officielle dans votre navigateur. Ce programme ne voit "
            "jamais votre mot de passe et ne stocke aucun identifiant."
        )
        note.setWordWrap(True)
        lg_layout.addWidget(note)

        row1 = QHBoxLayout()
        self._install_btn = QPushButton("Installer Legendary si absent")
        self._connect_btn = QPushButton("Connexion via Legendary")
        row1.addWidget(self._install_btn)
        row1.addWidget(self._connect_btn)
        lg_layout.addLayout(row1)

        row2 = QHBoxLayout()
        self._refresh_btn = QPushButton("Vérifier l'état")
        self._logout_btn = QPushButton("Déconnexion")
        row2.addWidget(self._refresh_btn)
        row2.addWidget(self._logout_btn)
        lg_layout.addLayout(row2)

        layout.addWidget(legendary_group)

        # Manual mode
        manual_group = QGroupBox("Mode manuel (sans compte)")
        manual_layout = QVBoxLayout(manual_group)
        manual_note = QLabel(
            "Vous pouvez utiliser l'application sans compte Epic : importez un "
            "ZIP officiel d'Unreal Engine pour Linux depuis l'onglet Moteurs."
        )
        manual_note.setWordWrap(True)
        manual_layout.addWidget(manual_note)
        self._manual_btn = QPushButton("Activer le mode manuel / import ZIP")
        manual_layout.addWidget(self._manual_btn)
        layout.addWidget(manual_group)

        layout.addStretch(1)

        self._install_btn.clicked.connect(self._on_install)
        self._connect_btn.clicked.connect(self._on_connect)
        self._refresh_btn.clicked.connect(self.refresh)
        self._logout_btn.clicked.connect(self._on_logout)
        self._manual_btn.clicked.connect(self._on_manual)

    # -- actions ------------------------------------------------------------ #
    def refresh(self) -> None:
        epic = self._ctx.epic
        binary = epic.find_legendary()
        if binary:
            self._legendary_label.setText(f"Legendary : {binary}")
            self._connect_btn.setEnabled(True)
            self._logout_btn.setEnabled(True)
            self._install_btn.setEnabled(False)
        else:
            self._legendary_label.setText("Legendary : introuvable (non installé)")
            self._connect_btn.setEnabled(False)
            self._logout_btn.setEnabled(False)
            self._install_btn.setEnabled(True)

        state = epic.state
        if state.logged_in:
            who = f" ({state.username})" if state.username else ""
            self._status_label.setText(f"État : connecté{who}")
        else:
            self._status_label.setText("État : non connecté")
        self._method_label.setText(f"Méthode : {state.method}")

        # Query legendary status in the background if it is available.
        if binary:
            self._tasks.start(
                epic.refresh_status,
                on_finished=lambda _s: self._apply_state(),
                on_failed=lambda msg: self._ctx.runner.log("error", msg),
            )

    def _apply_state(self) -> None:
        state = self._ctx.epic.state
        if state.logged_in:
            who = f" ({state.username})" if state.username else ""
            self._status_label.setText(f"État : connecté{who}")
        else:
            self._status_label.setText("État : non connecté")
        self._method_label.setText(f"Méthode : {state.method}")

    def _on_install(self) -> None:
        if not helpers.confirm(
            self, "Installer Legendary",
            "Installer Legendary dans votre espace utilisateur (pipx de "
            "préférence, sinon pip --user) ? Aucune modification système ne "
            "sera effectuée.",
        ):
            return
        self._ctx.epic.install_legendary()
        helpers.info_box(
            self, "Installation lancée",
            "L'installation de Legendary a été lancée. Suivez la progression "
            "dans le Journal, puis cliquez sur « Vérifier l'état ».",
        )

    def _on_connect(self) -> None:
        self._ctx.epic.start_auth()
        helpers.info_box(
            self, "Connexion Epic",
            "Legendary va ouvrir la page de connexion Epic dans votre "
            "navigateur. Terminez la connexion, puis cliquez sur « Vérifier "
            "l'état ». Votre mot de passe n'est jamais transmis à cette "
            "application.",
        )

    def _on_logout(self) -> None:
        if not helpers.confirm(self, "Déconnexion",
                               "Supprimer la session Legendary locale ?"):
            return
        self._ctx.epic.logout()
        self.refresh()

    def _on_manual(self) -> None:
        self._ctx.epic.set_manual_mode()
        self.refresh()
        helpers.info_box(
            self, "Mode manuel",
            "Mode manuel activé. Rendez-vous dans l'onglet Moteurs pour "
            "importer un ZIP officiel d'Unreal Engine.",
        )
