"""Onglet "Compte Epic".

Connexion Epic guidée en plusieurs étapes, entièrement via Legendary et le
navigateur externe de l'utilisateur (jamais de WebView interne). L'application
ne demande ni ne stocke jamais le mot de passe ou un token Epic : c'est
Legendary qui gère sa propre session.
"""

from __future__ import annotations

from PySide6.QtGui import QDesktopServices
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..app_context import AppContext
from ..core.command_runner import CommandRunner
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

        # État
        status_group = QGroupBox("État de connexion Epic")
        status_layout = QVBoxLayout(status_group)
        self._status_label = QLabel("État : inconnu")
        self._method_label = QLabel("Méthode : —")
        self._legendary_label = QLabel("Legendary : recherche…")
        for lbl in (self._status_label, self._method_label, self._legendary_label):
            status_layout.addWidget(lbl)
        layout.addWidget(status_group)

        note = QLabel(
            "La connexion Epic passe par Legendary et votre navigateur. "
            "Cette application ne voit jamais votre mot de passe et ne stocke "
            "aucun identifiant ni token."
        )
        note.setWordWrap(True)
        layout.addWidget(note)

        # Étape 1 : Legendary
        step1 = QGroupBox("1. Legendary (l'outil de connexion)")
        s1 = QHBoxLayout(step1)
        self._check_btn = QPushButton("Vérifier Legendary")
        self._install_btn = QPushButton("Installer Legendary")
        s1.addWidget(self._check_btn)
        s1.addWidget(self._install_btn)
        s1.addStretch(1)
        layout.addWidget(step1)

        # Étape 2 : connexion automatique
        step2 = QGroupBox("2. Connexion automatique")
        s2 = QVBoxLayout(step2)
        s2.addWidget(QLabel(
            "Ouvre la connexion Epic dans votre navigateur via Legendary. "
            "Terminez la connexion, puis revenez ici et testez la connexion."))
        s2row = QHBoxLayout()
        self._auto_btn = QPushButton("Connexion automatique Legendary")
        s2row.addWidget(self._auto_btn)
        s2row.addStretch(1)
        s2.addLayout(s2row)
        layout.addWidget(step2)

        # Étape 3 : connexion manuelle avec code
        step3 = QGroupBox("3. Connexion manuelle avec code (si l'automatique échoue)")
        s3 = QVBoxLayout(step3)
        s3.addWidget(QLabel(
            "Ouvrez la page de connexion, connectez-vous, puis Epic affiche une "
            "page JSON. Copiez la valeur « authorizationCode » et collez-la "
            "ci-dessous. Vous pouvez aussi coller tout le JSON."))
        s3row1 = QHBoxLayout()
        self._open_login_btn = QPushButton(
            "Ouvrir la page de connexion Legendary/Epic dans mon navigateur")
        s3row1.addWidget(self._open_login_btn)
        s3row1.addStretch(1)
        s3.addLayout(s3row1)

        s3row2 = QHBoxLayout()
        self._code_edit = QLineEdit()
        self._code_edit.setPlaceholderText("Coller authorizationCode ici")
        self._validate_btn = QPushButton("Valider le code")
        s3row2.addWidget(self._code_edit)
        s3row2.addWidget(self._validate_btn)
        s3.addLayout(s3row2)
        layout.addWidget(step3)

        # Étape 4 : tester / déconnexion
        step4 = QGroupBox("4. Vérifier / gérer la session")
        s4 = QHBoxLayout(step4)
        self._test_btn = QPushButton("Tester la connexion")
        self._logout_btn = QPushButton("Déconnexion")
        self._open_cfg_btn = QPushButton("Ouvrir le dossier Legendary")
        s4.addWidget(self._test_btn)
        s4.addWidget(self._logout_btn)
        s4.addWidget(self._open_cfg_btn)
        s4.addStretch(1)
        layout.addWidget(step4)

        # Mode manuel
        manual_group = QGroupBox("Sans compte Epic")
        m = QVBoxLayout(manual_group)
        m.addWidget(QLabel(
            "Vous pouvez utiliser l'application sans compte : importez un ZIP "
            "officiel d'Unreal Engine pour Linux depuis l'onglet Moteurs."))
        self._manual_btn = QPushButton("Activer le mode manuel / import ZIP")
        m.addWidget(self._manual_btn)
        layout.addWidget(manual_group)

        layout.addStretch(1)

        # Wire up
        self._check_btn.clicked.connect(self._on_check)
        self._install_btn.clicked.connect(self._on_install)
        self._auto_btn.clicked.connect(self._on_auto)
        self._open_login_btn.clicked.connect(self._on_open_login)
        self._validate_btn.clicked.connect(self._on_validate_code)
        self._test_btn.clicked.connect(self._on_test)
        self._logout_btn.clicked.connect(self._on_logout)
        self._open_cfg_btn.clicked.connect(self._on_open_config)
        self._manual_btn.clicked.connect(self._on_manual)

    # -- state display ------------------------------------------------------ #
    def refresh(self) -> None:
        epic = self._ctx.epic
        binary = epic.find_legendary()
        installed = binary is not None
        if installed:
            self._legendary_label.setText(f"Legendary : {binary}")
        else:
            self._legendary_label.setText("Legendary : introuvable (non installé)")
        for b in (self._auto_btn, self._open_login_btn, self._validate_btn,
                  self._test_btn, self._logout_btn):
            b.setEnabled(installed)
        self._install_btn.setEnabled(not installed)
        self._apply_state()

    def _apply_state(self) -> None:
        state = self._ctx.epic.state
        if state.logged_in:
            who = f" ({state.username})" if state.username else ""
            self._status_label.setText(f"État : connecté{who}")
        else:
            self._status_label.setText("État : non connecté")
        self._method_label.setText(f"Méthode : {state.method}")

    # -- actions ------------------------------------------------------------ #
    def _on_check(self) -> None:
        epic = self._ctx.epic
        binary = epic.find_legendary()
        if not binary:
            helpers.info_box(
                self, "Legendary",
                "Legendary n'est pas installé. Cliquez sur « Installer "
                "Legendary » pour l'ajouter dans votre espace utilisateur.")
            self.refresh()
            return

        def work() -> str | None:
            return epic.legendary_version()

        self._check_btn.setEnabled(False)
        self._tasks.start(
            work,
            on_finished=self._on_check_done,
            on_failed=self._on_failed,
        )

    def _on_check_done(self, version) -> None:
        self._check_btn.setEnabled(True)
        binary = self._ctx.epic.find_legendary()
        helpers.info_box(
            self, "Legendary détecté",
            f"Chemin : {binary}\nVersion : {version or 'inconnue'}")
        self.refresh()

    def _on_install(self) -> None:
        epic = self._ctx.epic
        commands = epic.install_commands_preview()
        pretty = "\n".join("  " + CommandRunner.format_command(c) for c in commands)
        if not helpers.confirm(
            self, "Installer Legendary",
            "Les commandes suivantes vont être exécutées dans votre espace "
            "utilisateur (aucune modification système, pas de sudo) :\n\n"
            f"{pretty}\n\nContinuer ?",
        ):
            return
        self._install_btn.setEnabled(False)
        self._tasks.start(
            epic.install_legendary,
            on_finished=self._on_install_done,
            on_failed=self._on_failed,
        )

    def _on_install_done(self, ok: bool) -> None:
        self.refresh()
        if ok:
            helpers.info_box(self, "Legendary installé",
                             "Legendary est prêt. Passez à l'étape 2 ou 3.")
        else:
            helpers.warn_box(
                self, "Installation incomplète",
                "L'installation de Legendary a échoué ou le binaire reste "
                "introuvable. Consultez le Journal pour le détail.")

    def _on_auto(self) -> None:
        self._ctx.epic.start_auth()
        helpers.info_box(
            self, "Connexion automatique",
            "Legendary tente d'ouvrir la connexion Epic dans votre navigateur. "
            "Terminez la connexion, puis cliquez sur « Tester la connexion ». "
            "Si rien ne s'ouvre, utilisez la « Connexion manuelle avec code ».")

    def _on_open_login(self) -> None:
        url = self._ctx.epic.auth_url()
        # Prefer the external browser explicitly (xdg-open), never a WebView.
        if not QDesktopServices.openUrl(QUrl(url)):
            self._ctx.runner.run_async(["xdg-open", url])
        self._ctx.runner.log("info", f"Ouverture de la page de connexion Epic : {url}")
        helpers.info_box(
            self, "Page de connexion ouverte",
            "Après connexion, Epic peut afficher une page JSON. Copiez la "
            "valeur « authorizationCode », collez-la dans le champ, puis "
            "cliquez sur « Valider le code ».")

    def _on_validate_code(self) -> None:
        raw = self._code_edit.text().strip()
        if not raw:
            helpers.warn_box(self, "Code manquant",
                             "Collez d'abord l'authorizationCode (ou le JSON).")
            return
        self._validate_btn.setEnabled(False)
        self._tasks.start(
            self._ctx.epic.authenticate_with_code, raw,
            on_finished=self._on_validate_done,
            on_failed=self._on_failed,
        )

    def _on_validate_done(self, ok: bool) -> None:
        self._validate_btn.setEnabled(True)
        self.refresh()
        if ok:
            self._code_edit.clear()
            helpers.info_box(self, "Connecté", "Connexion Epic réussie via Legendary.")
        else:
            helpers.warn_box(
                self, "Échec de la connexion",
                "Legendary n'a pas réussi à valider le code. Le code expire "
                "vite : régénérez-en un via « Ouvrir la page de connexion », "
                "puis réessayez.")

    def _on_test(self) -> None:
        self._test_btn.setEnabled(False)
        self._tasks.start(
            self._ctx.epic.test_connection,
            on_finished=self._on_test_done,
            on_failed=self._on_failed,
        )

    def _on_test_done(self, result) -> None:
        self._test_btn.setEnabled(True)
        self.refresh()
        ok, account = result
        if ok:
            who = f"\nCompte : {account}" if account else ""
            helpers.info_box(self, "Connecté", f"Connexion Epic active.{who}")
        else:
            helpers.warn_box(
                self, "Non connecté",
                "Aucune session Epic active. Utilisez la connexion automatique "
                "ou la connexion manuelle avec code.")

    def _on_logout(self) -> None:
        if not helpers.confirm(self, "Déconnexion",
                               "Supprimer la session Legendary locale ?"):
            return
        self._tasks.start(
            self._ctx.epic.logout,
            on_finished=lambda _ok: self.refresh(),
            on_failed=self._on_failed,
        )

    def _on_open_config(self) -> None:
        self._ctx.epic.open_config_folder()

    def _on_manual(self) -> None:
        self._ctx.epic.set_manual_mode()
        self.refresh()
        helpers.info_box(
            self, "Mode manuel",
            "Mode manuel activé. Rendez-vous dans l'onglet Moteurs pour "
            "importer un ZIP officiel d'Unreal Engine.")

    def _on_failed(self, message: str) -> None:
        for b in (self._check_btn, self._install_btn, self._validate_btn,
                  self._test_btn):
            b.setEnabled(True)
        self._ctx.runner.log("error", message)
        helpers.error_box(self, "Erreur", message)
