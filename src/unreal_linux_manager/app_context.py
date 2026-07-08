"""Shared application context wiring the core services together.

A single :class:`AppContext` instance is created at startup and passed to every
tab, so they all share the same configuration, command runner (and therefore
the same Journal) and manager objects.
"""

from __future__ import annotations

from .core.command_runner import CommandRunner
from .core.config import Config
from .core.engine_manager import EngineManager
from .core.epic_auth import EpicAuth
from .core.plugin_manager import PluginManager
from .core.project_manager import ProjectManager
from .core.system_check import SystemCheck


class AppContext:
    """Container for the long-lived, shared services of the application."""

    def __init__(self) -> None:
        self.config = Config.load()
        self.runner = CommandRunner(verbose=self.config.verbose_logging)

        self.engines = EngineManager(self.runner)
        self.projects = ProjectManager(self.runner, self.config)
        self.plugins = PluginManager(self.runner)
        self.epic = EpicAuth(self.runner)
        self.system = SystemCheck(self.runner)

    def apply_config(self) -> None:
        """Re-apply config-derived settings after the user edits them."""
        self.runner.verbose = self.config.verbose_logging
