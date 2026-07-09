"""Onglet "Paramètres" : dossiers, éditeur, options de lancement."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..app_context import AppContext
from . import helpers


class _PathRow(QWidget):
    """A line edit with a "Parcourir" button that picks a directory."""

    def __init__(self, initial: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.edit = QLineEdit(initial)
        self.browse = QPushButton("Parcourir…")
        layout.addWidget(self.edit)
        layout.addWidget(self.browse)
        self.browse.clicked.connect(self._pick)

    def _pick(self) -> None:
        directory = QFileDialog.getExistingDirectory(
            self, "Choisir un dossier", self.edit.text() or ""
        )
        if directory:
            self.edit.setText(directory)

    def text(self) -> str:
        return self.edit.text().strip()


class SettingsTab(QWidget):
    # Notifies the window that config changed so other tabs can refresh.
    def __init__(self, ctx: AppContext, on_saved=None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ctx = ctx
        self._on_saved = on_saved
        self._build_ui()
        self._load_from_config()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Mode (beginner / advanced)
        mode_group = QGroupBox("Mode d'utilisation")
        mode_layout = QVBoxLayout(mode_group)
        self._beginner = QCheckBox("Mode débutant (masquer les fonctions avancées)")
        mode_layout.addWidget(self._beginner)
        mode_hint = QLabel(
            "En mode débutant, les fonctions risquées (compilation depuis les "
            "sources, toolchain, variables d'environnement, rpm-ostree direct) "
            "sont masquées et davantage d'explications sont affichées.")
        mode_hint.setWordWrap(True)
        mode_layout.addWidget(mode_hint)
        layout.addWidget(mode_group)

        # Directories
        dirs = QGroupBox("Dossiers par défaut")
        dirs_form = QFormLayout(dirs)
        self._engines_dir = _PathRow("")
        self._projects_dir = _PathRow("")
        self._vault_dir = _PathRow("")
        dirs_form.addRow("Moteurs :", self._engines_dir)
        dirs_form.addRow("Projets :", self._projects_dir)
        dirs_form.addRow("Vault / assets :", self._vault_dir)
        layout.addWidget(dirs)

        # Editor & terminal
        tools = QGroupBox("Outils")
        tools_form = QFormLayout(tools)
        self._editor_combo = QComboBox()
        self._editor_combo.addItem("VS Code", "vscode")
        self._editor_combo.addItem("Rider", "rider")
        self._editor_combo.addItem("Personnalisé", "custom")
        self._custom_editor = QLineEdit()
        self._custom_editor.setPlaceholderText("Commande, ex : /usr/bin/mon-editeur")
        self._terminal = QLineEdit()
        self._terminal.setPlaceholderText("Commande, ex : konsole, gnome-terminal")
        tools_form.addRow("Éditeur de code :", self._editor_combo)
        tools_form.addRow("Commande éditeur personnalisé :", self._custom_editor)
        tools_form.addRow("Terminal préféré :", self._terminal)
        layout.addWidget(tools)

        # Launch options (default engine is always visible)
        launch = QGroupBox("Lancement d'Unreal")
        launch_form = QFormLayout(launch)
        self._default_engine = QComboBox()
        launch_form.addRow("Moteur par défaut :", self._default_engine)
        layout.addWidget(launch)

        # Advanced launch options (hidden in beginner mode)
        self._advanced_launch = QGroupBox("Options avancées de lancement")
        adv_form = QFormLayout(self._advanced_launch)
        self._extra_args = QLineEdit()
        self._extra_args.setPlaceholderText("ex : -vulkan -windowed")
        self._env_vars = QLineEdit()
        self._env_vars.setPlaceholderText("ex : DXVK_HUD=fps;__GL_SHADER_DISK_CACHE=1")
        adv_form.addRow("Arguments supplémentaires :", self._extra_args)
        adv_form.addRow("Variables d'environnement (k=v;k=v) :", self._env_vars)
        layout.addWidget(self._advanced_launch)

        # Logging
        logging_group = QGroupBox("Journalisation")
        logging_layout = QVBoxLayout(logging_group)
        self._verbose = QCheckBox("Activer les logs détaillés")
        logging_layout.addWidget(self._verbose)
        layout.addWidget(logging_group)

        # Scan paths
        scan_group = QGroupBox("Chemins de scan supplémentaires")
        scan_layout = QVBoxLayout(scan_group)
        scan_layout.addWidget(QLabel("Moteurs :"))
        self._engine_paths = QListWidget()
        scan_layout.addWidget(self._engine_paths)
        eng_btns = QHBoxLayout()
        self._add_engine_path = QPushButton("Ajouter")
        self._del_engine_path = QPushButton("Retirer")
        eng_btns.addWidget(self._add_engine_path)
        eng_btns.addWidget(self._del_engine_path)
        eng_btns.addStretch(1)
        scan_layout.addLayout(eng_btns)

        scan_layout.addWidget(QLabel("Projets :"))
        self._project_paths = QListWidget()
        scan_layout.addWidget(self._project_paths)
        proj_btns = QHBoxLayout()
        self._add_project_path = QPushButton("Ajouter")
        self._del_project_path = QPushButton("Retirer")
        proj_btns.addWidget(self._add_project_path)
        proj_btns.addWidget(self._del_project_path)
        proj_btns.addStretch(1)
        scan_layout.addLayout(proj_btns)
        layout.addWidget(scan_group)

        # Save / reset
        bottom = QHBoxLayout()
        self._save_btn = QPushButton("Enregistrer")
        self._reset_btn = QPushButton("Réinitialiser la configuration")
        bottom.addWidget(self._save_btn)
        bottom.addStretch(1)
        bottom.addWidget(self._reset_btn)
        layout.addLayout(bottom)
        layout.addStretch(1)

        # Wire up
        self._beginner.toggled.connect(lambda _c: self.apply_mode())
        self._save_btn.clicked.connect(self._save)
        self._reset_btn.clicked.connect(self._reset)
        self._add_engine_path.clicked.connect(
            lambda: self._add_path(self._engine_paths))
        self._del_engine_path.clicked.connect(
            lambda: self._remove_selected(self._engine_paths))
        self._add_project_path.clicked.connect(
            lambda: self._add_path(self._project_paths))
        self._del_project_path.clicked.connect(
            lambda: self._remove_selected(self._project_paths))

    # -- config <-> widgets ------------------------------------------------- #
    def apply_mode(self) -> None:
        """Hide advanced settings widgets in beginner mode."""
        advanced = not self._beginner.isChecked()
        self._advanced_launch.setVisible(advanced)

    def _load_from_config(self) -> None:
        cfg = self._ctx.config
        self._beginner.setChecked(cfg.beginner_mode)
        self.apply_mode()
        self._engines_dir.edit.setText(cfg.get("paths", "engines_dir", ""))
        self._projects_dir.edit.setText(cfg.get("paths", "projects_dir", ""))
        self._vault_dir.edit.setText(cfg.get("paths", "vault_dir", ""))

        idx = self._editor_combo.findData(cfg.preferred_editor)
        self._editor_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._custom_editor.setText(cfg.custom_editor_command)
        self._terminal.setText(cfg.preferred_terminal)

        self._extra_args.setText(" ".join(cfg.launch_extra_args))
        self._env_vars.setText(
            ";".join(f"{k}={v}" for k, v in cfg.launch_env.items())
        )
        self._verbose.setChecked(cfg.verbose_logging)

        self._engine_paths.clear()
        self._engine_paths.addItems(cfg.get("paths", "extra_engine_scan_paths", []) or [])
        self._project_paths.clear()
        self._project_paths.addItems(cfg.get("paths", "extra_project_scan_paths", []) or [])

        self._reload_default_engines()

    def _reload_default_engines(self) -> None:
        """Populate the default-engine combo from a quick engine scan."""
        cfg = self._ctx.config
        engines = self._ctx.engines.scan(cfg.engine_scan_paths())
        self._default_engine.clear()
        self._default_engine.addItem("(demander à chaque fois)", "")
        selected = 0
        for i, engine in enumerate(engines, start=1):
            self._default_engine.addItem(engine.name, engine.path)
            if engine.path == cfg.default_engine_path:
                selected = i
        self._default_engine.setCurrentIndex(selected)

    def _add_path(self, widget: QListWidget) -> None:
        directory = QFileDialog.getExistingDirectory(self, "Choisir un dossier")
        if directory:
            widget.addItem(directory)

    def _remove_selected(self, widget: QListWidget) -> None:
        for item in widget.selectedItems():
            widget.takeItem(widget.row(item))

    # -- persistence -------------------------------------------------------- #
    def _parse_env(self) -> dict[str, str]:
        env: dict[str, str] = {}
        for pair in self._env_vars.text().split(";"):
            pair = pair.strip()
            if not pair or "=" not in pair:
                continue
            key, _, value = pair.partition("=")
            key = key.strip()
            if key:
                env[key] = value.strip()
        return env

    def _save(self) -> None:
        cfg = self._ctx.config
        cfg.set("paths", "engines_dir", self._engines_dir.text())
        cfg.set("paths", "projects_dir", self._projects_dir.text())
        cfg.set("paths", "vault_dir", self._vault_dir.text())

        cfg.set("general", "beginner_mode", self._beginner.isChecked())
        cfg.set("general", "preferred_editor", self._editor_combo.currentData())
        cfg.set("general", "custom_editor_command", self._custom_editor.text().strip())
        cfg.set("general", "preferred_terminal", self._terminal.text().strip())
        cfg.set("general", "verbose_logging", self._verbose.isChecked())

        cfg.default_engine_path = str(self._default_engine.currentData() or "")
        args = self._extra_args.text().split()
        cfg.set("launch", "extra_args", args)
        cfg.set("launch", "env", self._parse_env())

        cfg.set("paths", "extra_engine_scan_paths",
                [self._engine_paths.item(i).text() for i in range(self._engine_paths.count())])
        cfg.set("paths", "extra_project_scan_paths",
                [self._project_paths.item(i).text() for i in range(self._project_paths.count())])

        cfg.save()
        self._ctx.apply_config()
        helpers.info_box(self, "Enregistré", "Configuration enregistrée.")
        if self._on_saved:
            self._on_saved()

    def _reset(self) -> None:
        if not helpers.confirm(
            self, "Réinitialiser",
            "Réinitialiser toute la configuration aux valeurs par défaut ?",
        ):
            return
        self._ctx.config.reset_to_defaults()
        self._ctx.apply_config()
        self._load_from_config()
        helpers.info_box(self, "Réinitialisé",
                         "Configuration réinitialisée aux valeurs par défaut.")
        if self._on_saved:
            self._on_saved()
