"""Discover, inspect and launch Unreal ``.uproject`` projects."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from . import paths, unreal_detector
from .command_runner import CommandRunner, which

# Directories we never descend into when searching for projects, to keep the
# recursive scan fast and avoid walking into engine/build output trees.
_SKIP_DIRS = {
    "Binaries", "Intermediate", "Saved", "DerivedDataCache",
    "Engine", ".git", "node_modules", "__pycache__",
}


@dataclass
class ProjectInfo:
    """Metadata describing a discovered Unreal project."""

    path: str            # full path to the .uproject file
    name: str            # project name (file stem)
    directory: str       # containing directory
    engine_association: str = ""   # value of the EngineAssociation field
    modified: float = 0.0          # mtime as epoch seconds
    plugins: list[str] = field(default_factory=list)

    @property
    def modified_human(self) -> str:
        if not self.modified:
            return "—"
        return datetime.fromtimestamp(self.modified).strftime("%Y-%m-%d %H:%M")


def read_uproject_json(path: str | Path) -> dict:
    """Parse a ``.uproject`` file and return its JSON content (or ``{}``)."""
    p = paths.expand(path)
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def detect_project_plugins(project_path: str | Path) -> list[str]:
    """Return the names of plugins declared or present in a project."""
    project = paths.expand(project_path)
    project_dir = project.parent if project.is_file() else project

    names: set[str] = set()

    # Plugins enabled inside the .uproject descriptor.
    if project.is_file():
        data = read_uproject_json(project)
        for plugin in data.get("Plugins", []):
            name = plugin.get("Name")
            if name:
                names.add(name)

    # Plugins physically present in the project's Plugins/ folder.
    plugins_dir = project_dir / "Plugins"
    if plugins_dir.is_dir():
        for entry in plugins_dir.rglob("*.uplugin"):
            names.add(entry.stem)

    return sorted(names)


def build_project_info(uproject_path: str | Path) -> ProjectInfo:
    project = paths.expand(uproject_path)
    data = read_uproject_json(project)
    try:
        mtime = project.stat().st_mtime
    except OSError:
        mtime = 0.0
    return ProjectInfo(
        path=str(project),
        name=project.stem,
        directory=str(project.parent),
        engine_association=str(data.get("EngineAssociation", "")),
        modified=mtime,
        plugins=detect_project_plugins(project),
    )


def scan_projects(scan_paths: list[str], *, max_depth: int = 6) -> list[ProjectInfo]:
    """Recursively find ``.uproject`` files under the given directories."""
    found: dict[str, ProjectInfo] = {}

    for raw in scan_paths:
        base = paths.expand(raw)
        if not base.exists():
            continue
        base_depth = len(base.parts)
        for dirpath, dirnames, filenames in os.walk(base, onerror=lambda _e: None):
            current = Path(dirpath)
            # Depth limit relative to the scan root.
            if len(current.parts) - base_depth > max_depth:
                dirnames[:] = []
                continue
            # Prune noisy / irrelevant directories.
            dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
            for name in filenames:
                if name.lower().endswith(".uproject"):
                    full = current / name
                    key = str(full.resolve())
                    if key not in found:
                        found[key] = build_project_info(full)
    return sorted(found.values(), key=lambda p: p.name.lower())


class ProjectManager:
    """Facade used by the GUI to interact with projects."""

    def __init__(self, runner: CommandRunner, config) -> None:
        self._runner = runner
        self._config = config

    def scan(self, scan_paths: list[str]) -> list[ProjectInfo]:
        self._runner.log("info", f"Scan des projets dans : {', '.join(scan_paths)}")
        projects = scan_projects(scan_paths)
        self._runner.log("info", f"{len(projects)} projet(s) détecté(s).")
        return projects

    # -- generate project files -------------------------------------------- #
    def generate_project_files(self, engine_path: str | Path, uproject_path: str | Path):
        """Invoke the engine's GenerateProjectFiles helper for a project."""
        engine = paths.expand(engine_path)
        uproject = paths.expand(uproject_path)
        script = engine / "Engine/Build/BatchFiles/Linux/GenerateProjectFiles.sh"
        if not script.is_file():
            self._runner.log("error", f"Script introuvable : {script}")
            return None
        return self._runner.run_async(
            ["bash", str(script), "-project=" + str(uproject), "-game"],
            cwd=str(engine),
        )

    # -- open helpers ------------------------------------------------------- #
    def open_project_folder(self, path: str | Path):
        directory = paths.expand(path)
        if directory.is_file():
            directory = directory.parent
        if not directory.exists():
            self._runner.log("error", f"Dossier introuvable : {directory}")
            return None
        return self._runner.run_async(["xdg-open", str(directory)])

    def open_in_editor(self, path: str | Path):
        """Open a project directory in the user's preferred code editor."""
        target = paths.expand(path)
        if target.is_file():
            target = target.parent

        editor = self._config.preferred_editor
        command: list[str] | None = None
        if editor == "vscode":
            binary = which("code") or which("code-insiders")
            if binary:
                command = [binary, str(target)]
        elif editor == "rider":
            binary = which("rider") or which("rider.sh")
            if binary:
                command = [binary, str(target)]
        elif editor == "custom":
            custom = self._config.custom_editor_command.strip()
            if custom:
                import shlex

                command = [*shlex.split(custom), str(target)]

        if command is None:
            self._runner.log(
                "warning",
                "Éditeur de code introuvable. Configurez-le dans l'onglet "
                "Paramètres (VS Code, Rider ou commande personnalisée).",
            )
            return None
        return self._runner.run_async(command)
