"""Discover and install Unreal plugins for projects and engines."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from . import paths
from .command_runner import CommandRunner, which


@dataclass
class PluginInfo:
    """Metadata describing a discovered plugin."""

    name: str
    path: str            # path to the .uplugin file
    directory: str       # plugin root directory
    friendly_name: str = ""
    version: str = ""
    description: str = ""
    scope: str = "project"   # "project" or "engine"
    project: str = ""        # owning project name when scope == "project"


def read_uplugin(path: str | Path) -> dict:
    """Parse a ``.uplugin`` descriptor and return its JSON content."""
    p = paths.expand(path)
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def validate_plugin_folder(path: str | Path) -> bool:
    """True if the directory contains exactly-one top-level ``.uplugin``."""
    directory = paths.expand(path)
    if not directory.is_dir():
        return False
    return any(directory.glob("*.uplugin"))


def _find_uplugin(directory: Path) -> Path | None:
    for entry in directory.glob("*.uplugin"):
        return entry
    return None


def _build_plugin_info(uplugin: Path, *, scope: str, project: str = "") -> PluginInfo:
    data = read_uplugin(uplugin)
    return PluginInfo(
        name=uplugin.stem,
        path=str(uplugin),
        directory=str(uplugin.parent),
        friendly_name=str(data.get("FriendlyName", "")),
        version=str(data.get("VersionName", data.get("Version", ""))),
        description=str(data.get("Description", "")),
        scope=scope,
        project=project,
    )


def scan_project_plugins(project_path: str | Path) -> list[PluginInfo]:
    """List plugins in a project's ``Plugins/`` directory."""
    project = paths.expand(project_path)
    project_dir = project.parent if project.is_file() else project
    project_name = project.stem if project.is_file() else project_dir.name
    plugins_dir = project_dir / "Plugins"
    result: list[PluginInfo] = []
    if not plugins_dir.is_dir():
        return result
    for uplugin in sorted(plugins_dir.rglob("*.uplugin")):
        result.append(_build_plugin_info(uplugin, scope="project", project=project_name))
    return result


def scan_engine_marketplace_plugins(engine_path: str | Path) -> list[PluginInfo]:
    """List plugins under ``Engine/Plugins/Marketplace`` for an engine."""
    engine = paths.expand(engine_path)
    marketplace = engine / "Engine/Plugins/Marketplace"
    result: list[PluginInfo] = []
    if not marketplace.is_dir():
        return result
    for uplugin in sorted(marketplace.rglob("*.uplugin")):
        result.append(_build_plugin_info(uplugin, scope="engine"))
    return result


class PluginManager:
    """Facade used by the GUI for plugin operations."""

    EPIC_ASSET_MANAGER_FLATPAK = "io.github.achetagames.epic_asset_manager"

    def __init__(self, runner: CommandRunner) -> None:
        self._runner = runner

    def scan_project(self, project_path: str | Path) -> list[PluginInfo]:
        return scan_project_plugins(project_path)

    def scan_engine(self, engine_path: str | Path) -> list[PluginInfo]:
        return scan_engine_marketplace_plugins(engine_path)

    def copy_plugin_to_project(
        self, plugin_folder: str | Path, project_path: str | Path
    ) -> Path:
        """Copy a plugin directory into a project's ``Plugins/`` folder.

        Returns the destination path. Raises ``ValueError`` on invalid input.
        """
        src = paths.expand(plugin_folder)
        if not validate_plugin_folder(src):
            raise ValueError(
                f"Le dossier ne contient pas de fichier .uplugin : {src}"
            )
        project = paths.expand(project_path)
        project_dir = project.parent if project.is_file() else project
        plugins_dir = project_dir / "Plugins"
        plugins_dir.mkdir(parents=True, exist_ok=True)

        uplugin = _find_uplugin(src)
        plugin_name = uplugin.stem if uplugin else src.name
        dest = plugins_dir / plugin_name

        if dest.exists():
            raise ValueError(f"Le plugin existe déjà : {dest}")

        self._runner.log("info", f"Copie du plugin {plugin_name} vers {dest} …")
        shutil.copytree(src, dest)
        self._runner.log("info", f"Plugin copié : {dest}")
        return dest

    def open_plugins_folder(self, project_path: str | Path):
        project = paths.expand(project_path)
        project_dir = project.parent if project.is_file() else project
        plugins_dir = project_dir / "Plugins"
        plugins_dir.mkdir(parents=True, exist_ok=True)
        return self._runner.run_async(["xdg-open", str(plugins_dir)])

    # -- Epic Asset Manager integration ------------------------------------ #
    def epic_asset_manager_installed(self) -> bool:
        """True if Epic Asset Manager is installed as a Flatpak."""
        if which("flatpak") is None:
            return False
        result = self._runner.run(
            ["flatpak", "info", self.EPIC_ASSET_MANAGER_FLATPAK], timeout=15
        )
        return result.ok

    def launch_epic_asset_manager(self):
        if which("flatpak") is None:
            self._runner.log("warning", "Flatpak n'est pas installé.")
            return None
        return self._runner.run_async(
            ["flatpak", "run", self.EPIC_ASSET_MANAGER_FLATPAK]
        )

    def epic_asset_manager_install_command(self) -> list[str]:
        return ["flatpak", "install", "flathub", self.EPIC_ASSET_MANAGER_FLATPAK]
