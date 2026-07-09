"""Load, persist and expose user configuration.

Configuration is stored as TOML in the user's config directory. Reading uses
the standard-library ``tomllib`` (Python 3.11+). Writing uses a small,
dependency-free TOML serializer that covers exactly the structures this
application produces (tables, lists of strings, inline tables of strings,
booleans and strings).
"""

from __future__ import annotations

import copy
import shutil
from pathlib import Path
from typing import Any

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # pragma: no cover - fallback for older runtimes
    tomllib = None  # type: ignore

from . import paths

# In-memory default used when neither the user config nor the bundled default
# file can be read. Keeps the application usable in every situation.
_FALLBACK_DEFAULTS: dict[str, Any] = {
    "general": {
        "beginner_mode": True,
        "verbose_logging": False,
        "preferred_editor": "vscode",
        "custom_editor_command": "",
        "preferred_terminal": "",
    },
    "paths": {
        "engines_dir": "~/Games/Unreal/Engines",
        "projects_dir": "~/Unreal Projects",
        "vault_dir": "~/Games/Unreal/Vault",
        "extra_engine_scan_paths": ["~/UnrealEngine", "/opt/UnrealEngine"],
        "extra_project_scan_paths": ["~/Documents/Unreal Projects"],
    },
    "engine": {
        "default_engine_path": "",
    },
    "launch": {
        "env": {},
        "extra_args": [],
    },
}


def _load_toml(path: Path) -> dict[str, Any]:
    if tomllib is None:  # pragma: no cover
        raise RuntimeError("tomllib is unavailable; Python 3.11+ is required.")
    with path.open("rb") as fh:
        return tomllib.load(fh)


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge ``override`` onto a copy of ``base``."""
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def load_defaults() -> dict[str, Any]:
    """Return the default configuration, preferring the bundled TOML file."""
    source = paths.default_config_source()
    if source.is_file() and tomllib is not None:
        try:
            return _load_toml(source)
        except Exception:
            pass
    return copy.deepcopy(_FALLBACK_DEFAULTS)


# --------------------------------------------------------------------------- #
# Minimal TOML writer
# --------------------------------------------------------------------------- #
def _toml_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _format_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return f'"{_toml_escape(value)}"'
    raise TypeError(f"Unsupported scalar for TOML: {value!r}")


def _format_array(values: list[Any]) -> str:
    return "[" + ", ".join(_format_scalar(v) for v in values) + "]"


def _format_inline_table(mapping: dict[str, Any]) -> str:
    items = ", ".join(f'"{_toml_escape(k)}" = {_format_scalar(v)}' for k, v in mapping.items())
    return "{ " + items + " }" if items else "{}"


def _dump_toml(data: dict[str, Any]) -> str:
    """Serialize a shallow-nested dict (one level of tables) to TOML text."""
    lines: list[str] = []

    def emit_pairs(mapping: dict[str, Any]) -> None:
        for key, value in mapping.items():
            if isinstance(value, dict):
                continue  # handled as a table
            if isinstance(value, list):
                lines.append(f"{key} = {_format_array(value)}")
            else:
                lines.append(f"{key} = {_format_scalar(value)}")

    # Top-level scalar keys first (there are usually none).
    emit_pairs({k: v for k, v in data.items() if not isinstance(v, dict)})

    for section, value in data.items():
        if not isinstance(value, dict):
            continue
        if lines:
            lines.append("")
        lines.append(f"[{section}]")
        for key, sub in value.items():
            if isinstance(sub, dict):
                lines.append(f"{key} = {_format_inline_table(sub)}")
            elif isinstance(sub, list):
                lines.append(f"{key} = {_format_array(sub)}")
            else:
                lines.append(f"{key} = {_format_scalar(sub)}")

    return "\n".join(lines) + "\n"


class Config:
    """High-level accessor around the merged configuration dictionary."""

    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    # -- persistence -------------------------------------------------------- #
    @classmethod
    def load(cls) -> "Config":
        """Load user config merged over defaults, creating it if missing."""
        paths.ensure_runtime_dirs()
        defaults = load_defaults()
        cfg_path = paths.config_file()

        if not cfg_path.exists():
            # First run: copy the bundled default file for user editing.
            source = paths.default_config_source()
            try:
                if source.is_file():
                    shutil.copyfile(source, cfg_path)
                else:
                    cfg_path.write_text(_dump_toml(defaults), encoding="utf-8")
            except OSError:
                pass
            return cls(defaults)

        try:
            user_data = _load_toml(cfg_path)
        except Exception:
            user_data = {}
        return cls(_deep_merge(defaults, user_data))

    def save(self) -> None:
        """Persist the current configuration to disk."""
        paths.ensure_runtime_dirs()
        paths.config_file().write_text(_dump_toml(self._data), encoding="utf-8")

    def reset_to_defaults(self) -> None:
        """Replace the current configuration with the shipped defaults."""
        self._data = load_defaults()
        self.save()

    # -- generic access ----------------------------------------------------- #
    def get(self, section: str, key: str, default: Any = None) -> Any:
        return self._data.get(section, {}).get(key, default)

    def set(self, section: str, key: str, value: Any) -> None:
        self._data.setdefault(section, {})[key] = value

    def as_dict(self) -> dict[str, Any]:
        return copy.deepcopy(self._data)

    # -- typed convenience accessors --------------------------------------- #
    @property
    def beginner_mode(self) -> bool:
        return bool(self.get("general", "beginner_mode", True))

    @beginner_mode.setter
    def beginner_mode(self, value: bool) -> None:
        self.set("general", "beginner_mode", bool(value))

    @property
    def verbose_logging(self) -> bool:
        return bool(self.get("general", "verbose_logging", False))

    @property
    def preferred_editor(self) -> str:
        return str(self.get("general", "preferred_editor", "vscode"))

    @property
    def custom_editor_command(self) -> str:
        return str(self.get("general", "custom_editor_command", ""))

    @property
    def preferred_terminal(self) -> str:
        return str(self.get("general", "preferred_terminal", ""))

    @property
    def engines_dir(self) -> Path:
        return paths.expand(self.get("paths", "engines_dir", "~/Games/Unreal/Engines"))

    @property
    def projects_dir(self) -> Path:
        return paths.expand(self.get("paths", "projects_dir", "~/Unreal Projects"))

    @property
    def vault_dir(self) -> Path:
        return paths.expand(self.get("paths", "vault_dir", "~/Games/Unreal/Vault"))

    @property
    def default_engine_path(self) -> str:
        return str(self.get("engine", "default_engine_path", ""))

    @default_engine_path.setter
    def default_engine_path(self, value: str) -> None:
        self.set("engine", "default_engine_path", value)

    @property
    def launch_env(self) -> dict[str, str]:
        env = self.get("launch", "env", {}) or {}
        return {str(k): str(v) for k, v in env.items()}

    @property
    def launch_extra_args(self) -> list[str]:
        return [str(a) for a in (self.get("launch", "extra_args", []) or [])]

    # -- scan path helpers -------------------------------------------------- #
    def engine_scan_paths(self) -> list[str]:
        """All directories to scan for engines (well-known + configured)."""
        result = list(paths.DEFAULT_ENGINE_SCAN_PATHS)
        result.append(str(self.engines_dir))
        result.extend(self.get("paths", "extra_engine_scan_paths", []) or [])
        return _dedup(result)

    def project_scan_paths(self) -> list[str]:
        """All directories to scan for projects (well-known + configured)."""
        result = list(paths.DEFAULT_PROJECT_SCAN_PATHS)
        result.append(str(self.projects_dir))
        result.extend(self.get("paths", "extra_project_scan_paths", []) or [])
        return _dedup(result)

    def add_engine_scan_path(self, path: str) -> None:
        current = self.get("paths", "extra_engine_scan_paths", []) or []
        if path not in current:
            current.append(path)
            self.set("paths", "extra_engine_scan_paths", current)

    def add_project_scan_path(self, path: str) -> None:
        current = self.get("paths", "extra_project_scan_paths", []) or []
        if path not in current:
            current.append(path)
            self.set("paths", "extra_project_scan_paths", current)


def _dedup(items: list[str]) -> list[str]:
    """Return items with duplicates removed, preserving order (by expansion)."""
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = str(paths.expand(item))
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out
