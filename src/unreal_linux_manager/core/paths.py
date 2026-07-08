"""Central place for all filesystem paths used by the application.

Follows the XDG Base Directory specification so the application behaves
correctly on immutable / atomic distributions where writing outside the
user's home directory must be avoided.

    Config : ~/.config/unreal-linux-manager/config.toml
    Data   : ~/.local/share/unreal-linux-manager/
    Logs   : ~/.local/state/unreal-linux-manager/logs/
"""

from __future__ import annotations

import os
from pathlib import Path

from .. import __app_id__

APP_ID = __app_id__


def _xdg_dir(env_var: str, default_relative: str) -> Path:
    """Return an XDG base directory, honouring the environment override."""
    override = os.environ.get(env_var)
    if override:
        return Path(override).expanduser()
    return Path.home() / default_relative


def config_dir() -> Path:
    """Directory holding the user configuration file."""
    return _xdg_dir("XDG_CONFIG_HOME", ".config") / APP_ID


def config_file() -> Path:
    """Full path to config.toml."""
    return config_dir() / "config.toml"


def data_dir() -> Path:
    """Directory for persistent application data (engine/project registry)."""
    return _xdg_dir("XDG_DATA_HOME", ".local/share") / APP_ID


def state_dir() -> Path:
    """Directory for state such as logs and last-known status."""
    return _xdg_dir("XDG_STATE_HOME", ".local/state") / APP_ID


def logs_dir() -> Path:
    """Directory where rotating log files are written."""
    return state_dir() / "logs"


def account_state_file() -> Path:
    """File where the (non-secret) Epic connection status is cached."""
    return data_dir() / "account_state.json"


def default_config_source() -> Path:
    """Path to the bundled default_config.toml shipped with the app."""
    # data/default_config.toml lives at the repository root, i.e. three
    # levels above this file: core/ -> unreal_linux_manager/ -> src/ -> root.
    here = Path(__file__).resolve()
    repo_root = here.parents[3]
    return repo_root / "data" / "default_config.toml"


def ensure_runtime_dirs() -> None:
    """Create all user directories the application needs to run."""
    for directory in (config_dir(), data_dir(), state_dir(), logs_dir()):
        directory.mkdir(parents=True, exist_ok=True)


# Well-known locations searched for engines even without configuration.
DEFAULT_ENGINE_SCAN_PATHS = [
    "~/Games/Unreal/Engines",
    "~/UnrealEngine",
    "/opt/UnrealEngine",
]

# Well-known locations searched for projects even without configuration.
DEFAULT_PROJECT_SCAN_PATHS = [
    "~/Unreal Projects",
    "~/Documents/Unreal Projects",
]

# Relative path of the editor binary inside an engine tree.
UNREAL_EDITOR_RELATIVE = "Engine/Binaries/Linux/UnrealEditor"


def expand(path: str | os.PathLike) -> Path:
    """Expand ``~`` and environment variables in a path string."""
    return Path(os.path.expandvars(os.path.expanduser(str(path))))
