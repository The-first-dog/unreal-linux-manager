"""Discover, import and launch Unreal Engine installations.

A valid engine is any directory containing
``Engine/Binaries/Linux/UnrealEditor``. The manager never downloads or
redistributes the engine itself; it only operates on ZIP archives supplied by
the user (the official Linux Unreal Engine build) and on already-present local
installations.
"""

from __future__ import annotations

import os
import stat
import zipfile
from dataclasses import dataclass
from pathlib import Path

from . import paths, unreal_detector
from .command_runner import CommandRunner


@dataclass
class EngineInfo:
    """Metadata describing a detected engine installation."""

    path: str
    name: str
    version: str
    editor_path: str
    size_bytes: int = -1  # -1 means "not computed yet"

    @property
    def exists(self) -> bool:
        return Path(self.editor_path).is_file()

    @property
    def size_human(self) -> str:
        return human_size(self.size_bytes) if self.size_bytes >= 0 else "…"


def human_size(num_bytes: int) -> str:
    """Format a byte count as a human-readable string."""
    if num_bytes < 0:
        return "inconnue"
    value = float(num_bytes)
    for unit in ("o", "Kio", "Mio", "Gio", "Tio"):
        if value < 1024.0:
            return f"{value:.1f} {unit}" if unit != "o" else f"{int(value)} {unit}"
        value /= 1024.0
    return f"{value:.1f} Pio"


def get_unreal_editor_path(engine_path: str | Path) -> Path:
    """Return the expected UnrealEditor path for an engine directory."""
    return unreal_detector.unreal_editor_path(engine_path)


def is_valid_engine(engine_path: str | Path) -> bool:
    return unreal_detector.is_valid_engine(engine_path)


def estimate_folder_size(path: str | Path) -> int:
    """Return the total size of a directory tree in bytes (best effort)."""
    total = 0
    root = paths.expand(path)
    if not root.exists():
        return 0
    for dirpath, _dirnames, filenames in os.walk(root, onerror=lambda _e: None):
        for name in filenames:
            fp = Path(dirpath) / name
            try:
                if not fp.is_symlink():
                    total += fp.stat().st_size
            except OSError:
                continue
    return total


def make_unreal_editor_executable(engine_path: str | Path) -> bool:
    """Ensure the UnrealEditor binary carries the executable bit.

    Returns True if the binary exists (and is now executable), False otherwise.
    """
    editor = get_unreal_editor_path(engine_path)
    if not editor.is_file():
        return False
    try:
        current = editor.stat().st_mode
        editor.chmod(current | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    except OSError:
        return False

    # A number of helper shell scripts under Engine/Build/BatchFiles/Linux also
    # need to be executable for the editor to start; fix them opportunistically.
    batch = paths.expand(engine_path) / "Engine/Build/BatchFiles/Linux"
    if batch.is_dir():
        for script in batch.glob("*.sh"):
            try:
                mode = script.stat().st_mode
                script.chmod(mode | stat.S_IXUSR)
            except OSError:
                continue
    return True


def build_engine_info(engine_path: str | Path, *, with_size: bool = False) -> EngineInfo:
    """Create an :class:`EngineInfo` for a directory (size optional)."""
    path = paths.expand(engine_path)
    return EngineInfo(
        path=str(path),
        name=unreal_detector.engine_display_name(path),
        version=unreal_detector.detect_engine_version(path),
        editor_path=str(get_unreal_editor_path(path)),
        size_bytes=estimate_folder_size(path) if with_size else -1,
    )


def scan_engines(scan_paths: list[str], *, with_size: bool = False) -> list[EngineInfo]:
    """Scan directories for valid engine installations.

    Each entry in ``scan_paths`` may itself be an engine root, or a parent
    directory containing several engine sub-folders. Both are handled.
    """
    found: dict[str, EngineInfo] = {}

    def consider(candidate: Path) -> None:
        if is_valid_engine(candidate):
            key = str(candidate.resolve())
            if key not in found:
                found[key] = build_engine_info(candidate, with_size=with_size)

    for raw in scan_paths:
        base = paths.expand(raw)
        if not base.exists():
            continue
        # The path itself could be an engine.
        consider(base)
        # Or its immediate children could be engines.
        if base.is_dir():
            try:
                for child in sorted(base.iterdir()):
                    if child.is_dir():
                        consider(child)
            except OSError:
                continue

    return list(found.values())


class EngineManager:
    """Stateful facade used by the GUI to work with engines."""

    def __init__(self, runner: CommandRunner) -> None:
        self._runner = runner

    # -- discovery ---------------------------------------------------------- #
    def scan(self, scan_paths: list[str], *, with_size: bool = False) -> list[EngineInfo]:
        self._runner.log("info", f"Scan des moteurs dans : {', '.join(scan_paths)}")
        engines = scan_engines(scan_paths, with_size=with_size)
        self._runner.log("info", f"{len(engines)} moteur(s) détecté(s).")
        return engines

    # -- launching ---------------------------------------------------------- #
    def launch_engine(
        self,
        engine_path: str | Path,
        *,
        env: dict[str, str] | None = None,
        extra_args: list[str] | None = None,
    ):
        editor = get_unreal_editor_path(engine_path)
        if not editor.is_file():
            self._runner.log("error", f"UnrealEditor introuvable : {editor}")
            return None
        make_unreal_editor_executable(engine_path)
        command = [str(editor), *(extra_args or [])]
        return self._runner.run_async(command, env=env)

    def launch_project(
        self,
        engine_path: str | Path,
        uproject_path: str | Path,
        *,
        env: dict[str, str] | None = None,
        extra_args: list[str] | None = None,
    ):
        editor = get_unreal_editor_path(engine_path)
        uproject = paths.expand(uproject_path)
        if not editor.is_file():
            self._runner.log("error", f"UnrealEditor introuvable : {editor}")
            return None
        if not uproject.is_file():
            self._runner.log("error", f"Projet introuvable : {uproject}")
            return None
        make_unreal_editor_executable(engine_path)
        command = [str(editor), str(uproject), *(extra_args or [])]
        return self._runner.run_async(command, env=env)

    # -- import ------------------------------------------------------------- #
    def import_engine_zip(
        self,
        zip_path: str | Path,
        destination: str | Path,
        *,
        progress: "callable | None" = None,
    ) -> EngineInfo:
        """Extract an official Unreal Linux ZIP into ``destination``.

        Raises ``ValueError`` if the archive does not contain a valid engine.
        ``progress`` is an optional callback ``(done, total)`` for the GUI.
        """
        zip_file = paths.expand(zip_path)
        dest = paths.expand(destination)

        if not zipfile.is_zipfile(zip_file):
            raise ValueError(f"Le fichier n'est pas une archive ZIP valide : {zip_file}")

        dest.mkdir(parents=True, exist_ok=True)
        self._runner.log("info", f"Extraction de {zip_file.name} vers {dest} …")

        with zipfile.ZipFile(zip_file) as archive:
            members = archive.infolist()
            total = len(members)
            for index, member in enumerate(members, start=1):
                # Guard against path traversal (Zip Slip).
                target = (dest / member.filename).resolve()
                if not str(target).startswith(str(dest.resolve())):
                    raise ValueError(f"Entrée d'archive suspecte ignorée : {member.filename}")
                archive.extract(member, dest)
                if progress is not None and (index % 200 == 0 or index == total):
                    progress(index, total)

        # The archive may contain a single top-level engine directory.
        engine_root = self._locate_engine_root(dest)
        if engine_root is None:
            raise ValueError(
                "Extraction terminée mais aucun binaire "
                f"'{paths.UNREAL_EDITOR_RELATIVE}' n'a été trouvé."
            )

        make_unreal_editor_executable(engine_root)
        self._runner.log("info", f"Moteur importé : {engine_root}")
        return build_engine_info(engine_root, with_size=False)

    @staticmethod
    def _locate_engine_root(base: Path) -> Path | None:
        """Find the engine root within an extracted tree, if any."""
        if is_valid_engine(base):
            return base
        try:
            for child in base.iterdir():
                if child.is_dir() and is_valid_engine(child):
                    return child
        except OSError:
            return None
        return None

    # -- toolchain ---------------------------------------------------------- #
    def setup_toolchain(self, engine_path: str | Path):
        """Run the engine's Linux SetupToolchain.sh script if present."""
        script = paths.expand(engine_path) / "Engine/Build/BatchFiles/Linux/SetupToolchain.sh"
        if not script.is_file():
            self._runner.log(
                "warning",
                f"Script de toolchain absent : {script}. "
                "Certaines versions n'en fournissent pas.",
            )
            return None
        try:
            mode = script.stat().st_mode
            script.chmod(mode | stat.S_IXUSR)
        except OSError:
            pass
        return self._runner.run_async([str(script)])
