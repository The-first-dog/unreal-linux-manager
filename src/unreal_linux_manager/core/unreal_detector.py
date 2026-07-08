"""Detection helpers shared by the engine and project managers.

Kept separate so the "what is a valid engine / project" rules live in one
place and can be reused by diagnostics and the UI without importing the
heavier manager modules.
"""

from __future__ import annotations

import re
from pathlib import Path

from . import paths

UNREAL_EDITOR_RELATIVE = paths.UNREAL_EDITOR_RELATIVE

# Common version markers found in an engine tree, tried in order.
_VERSION_FILE_CANDIDATES = [
    "Engine/Build/Build.version",
    "Engine/Source/Runtime/Launch/Resources/Version.h",
]

_VERSION_DIR_RE = re.compile(r"(UE_?|UnrealEngine[-_]?)?(\d+\.\d+(?:\.\d+)?)", re.IGNORECASE)


def unreal_editor_path(engine_path: str | Path) -> Path:
    """Return the expected path of the UnrealEditor binary for an engine."""
    return paths.expand(engine_path) / UNREAL_EDITOR_RELATIVE


def is_valid_engine(engine_path: str | Path) -> bool:
    """True when the given directory looks like a usable Unreal Engine build."""
    editor = unreal_editor_path(engine_path)
    return editor.is_file()


def _read_version_from_files(engine_path: Path) -> str | None:
    # Prefer the JSON Build.version file when present.
    build_version = engine_path / "Engine/Build/Build.version"
    if build_version.is_file():
        try:
            import json

            data = json.loads(build_version.read_text(encoding="utf-8"))
            major = data.get("MajorVersion")
            minor = data.get("MinorVersion")
            patch = data.get("PatchVersion")
            if major is not None and minor is not None:
                version = f"{major}.{minor}"
                if patch:
                    version += f".{patch}"
                return version
        except Exception:
            pass

    # Fall back to parsing the C++ header.
    header = engine_path / "Engine/Source/Runtime/Launch/Resources/Version.h"
    if header.is_file():
        try:
            text = header.read_text(encoding="utf-8", errors="ignore")
            major = re.search(r"#define\s+ENGINE_MAJOR_VERSION\s+(\d+)", text)
            minor = re.search(r"#define\s+ENGINE_MINOR_VERSION\s+(\d+)", text)
            patch = re.search(r"#define\s+ENGINE_PATCH_VERSION\s+(\d+)", text)
            if major and minor:
                version = f"{major.group(1)}.{minor.group(1)}"
                if patch:
                    version += f".{patch.group(1)}"
                return version
        except Exception:
            pass
    return None


def detect_engine_version(engine_path: str | Path) -> str:
    """Best-effort human-readable version string for an engine directory."""
    path = paths.expand(engine_path)
    version = _read_version_from_files(path)
    if version:
        return version

    # Guess from the directory name (e.g. "UE_5.3", "UnrealEngine-5.2").
    match = _VERSION_DIR_RE.search(path.name)
    if match:
        return match.group(2)
    return "inconnue"


def engine_display_name(engine_path: str | Path) -> str:
    """A friendly label combining the folder name and detected version."""
    path = paths.expand(engine_path)
    version = detect_engine_version(path)
    if version != "inconnue" and version not in path.name:
        return f"{path.name} (UE {version})"
    return path.name


def is_uproject(path: str | Path) -> bool:
    """True if the path is an existing ``.uproject`` file."""
    p = Path(path)
    return p.is_file() and p.suffix.lower() == ".uproject"
