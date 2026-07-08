"""Epic Games account handling via the Legendary CLI.

Security notes
--------------
This module NEVER asks for, receives or stores an Epic Games password.
Authentication is delegated entirely to Legendary, which performs a secure
browser-based OAuth flow. We only:

* detect whether the ``legendary`` binary is available;
* trigger ``legendary auth`` (which opens the browser flow);
* query ``legendary status`` to know whether a session exists;
* cache a *non-secret* boolean/username locally so the UI can show state.

A fully manual "no account / import ZIP" mode is always available and does not
require Legendary at all.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path

from . import paths
from .command_runner import CommandRunner, which


@dataclass
class AccountState:
    """Non-secret, cached representation of the Epic connection state."""

    logged_in: bool = False
    username: str = ""
    method: str = "manual"   # "legendary" or "manual"

    def save(self) -> None:
        try:
            paths.account_state_file().parent.mkdir(parents=True, exist_ok=True)
            paths.account_state_file().write_text(
                json.dumps(asdict(self), indent=2), encoding="utf-8"
            )
        except OSError:
            pass

    @classmethod
    def load(cls) -> "AccountState":
        path = paths.account_state_file()
        if not path.is_file():
            return cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return cls(
                logged_in=bool(data.get("logged_in", False)),
                username=str(data.get("username", "")),
                method=str(data.get("method", "manual")),
            )
        except (OSError, json.JSONDecodeError):
            return cls()


class EpicAuth:
    """Thin, defensive wrapper around the Legendary CLI."""

    def __init__(self, runner: CommandRunner) -> None:
        self._runner = runner
        self.state = AccountState.load()

    # -- detection ---------------------------------------------------------- #
    @staticmethod
    def find_legendary() -> str | None:
        """Return the path to the ``legendary`` binary, or ``None``."""
        # Standard PATH lookup first.
        found = which("legendary")
        if found:
            return found
        # pipx and user-local installs.
        for candidate in (
            Path.home() / ".local/bin/legendary",
            Path.home() / ".local/share/pipx/venvs/legendary/bin/legendary",
        ):
            if candidate.is_file():
                return str(candidate)
        return None

    def legendary_available(self) -> bool:
        return self.find_legendary() is not None

    def legendary_version(self) -> str | None:
        binary = self.find_legendary()
        if not binary:
            return None
        result = self._runner.run([binary, "--version"], timeout=20)
        if result.ok:
            return result.stdout.strip().splitlines()[0] if result.stdout else "installé"
        return None

    # -- install ------------------------------------------------------------ #
    @staticmethod
    def install_command() -> list[str]:
        """Recommended user-space install command for Legendary."""
        return ["pipx", "install", "legendary-gl"]

    @staticmethod
    def install_command_fallback() -> list[str]:
        """Fallback install using pip --user when pipx is unavailable."""
        return ["python3", "-m", "pip", "install", "--user", "legendary-gl"]

    def install_legendary(self):
        """Install Legendary in user space (pipx preferred, pip --user fallback)."""
        if which("pipx"):
            self._runner.log("info", "Installation de Legendary via pipx …")
            return self._runner.run_async(self.install_command())
        self._runner.log(
            "warning",
            "pipx est absent. Installation via 'pip install --user'. "
            "Pour une meilleure isolation, installez pipx.",
        )
        return self._runner.run_async(self.install_command_fallback())

    # -- auth flow ---------------------------------------------------------- #
    def start_auth(self):
        """Launch ``legendary auth`` (opens a secure browser OAuth flow)."""
        binary = self.find_legendary()
        if not binary:
            self._runner.log("error", "Legendary introuvable. Installez-le d'abord.")
            return None
        self._runner.log(
            "info",
            "Lancement de 'legendary auth'. Une page de connexion Epic va "
            "s'ouvrir dans votre navigateur. Ce programme ne voit jamais votre "
            "mot de passe.",
        )
        return self._runner.run_async([binary, "auth"])

    def logout(self):
        """Delete the local Legendary session (``legendary auth --delete``)."""
        binary = self.find_legendary()
        if not binary:
            # Nothing to do beyond clearing our own cached state.
            self.state = AccountState(method="manual")
            self.state.save()
            return None
        thread = self._runner.run_async(
            [binary, "auth", "--delete"],
            on_finished=lambda _r: self._on_logout(),
        )
        return thread

    def _on_logout(self) -> None:
        self.state = AccountState(logged_in=False, username="", method="legendary")
        self.state.save()

    def refresh_status(self) -> AccountState:
        """Query ``legendary status`` and update the cached state."""
        binary = self.find_legendary()
        if not binary:
            self.state = AccountState(logged_in=False, username="", method="manual")
            self.state.save()
            return self.state

        result = self._runner.run([binary, "status", "--json"], timeout=30)
        logged_in = False
        username = ""
        if result.ok and result.stdout.strip():
            try:
                data = json.loads(result.stdout)
                account = data.get("account", "")
                if account and account.lower() not in {"<not logged in>", "not logged in"}:
                    logged_in = True
                    username = account
            except json.JSONDecodeError:
                # Fall back to plain-text parsing.
                text = result.stdout.lower()
                logged_in = "logged in" in text and "not logged in" not in text
        self.state = AccountState(
            logged_in=logged_in, username=username, method="legendary"
        )
        self.state.save()
        return self.state

    def set_manual_mode(self) -> AccountState:
        """Switch to the offline / manual ZIP-import mode."""
        self.state = AccountState(logged_in=False, username="", method="manual")
        self.state.save()
        self._runner.log(
            "info",
            "Mode manuel activé : import de ZIP officiels sans compte Epic.",
        )
        return self.state
