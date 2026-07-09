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
import sys
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
    def legendary_venv_dir() -> Path:
        """Directory of the app-managed Legendary virtual environment."""
        return paths.data_dir() / "legendary-venv"

    @classmethod
    def legendary_venv_binary(cls) -> Path:
        return cls.legendary_venv_dir() / "bin" / "legendary"

    @classmethod
    def find_legendary(cls) -> str | None:
        """Return the path to the ``legendary`` binary, or ``None``."""
        # Standard PATH lookup first.
        found = which("legendary")
        if found:
            return found
        # pipx, user-local, and app-managed venv installs.
        for candidate in (
            cls.legendary_venv_binary(),
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
    def in_virtualenv() -> bool:
        """True when the current interpreter runs inside a virtual environment."""
        return sys.prefix != getattr(sys, "base_prefix", sys.prefix)

    def install_commands_preview(self) -> list[list[str]]:
        """Return the exact commands that :meth:`install_legendary` will run.

        Used by the UI to show the user what will happen before anything runs.
        Priority: pipx (isolated, user-space) → a dedicated venv managed by the
        app. ``pip install --user`` is never used because it fails inside a
        virtualenv and pollutes the user site otherwise.
        """
        if which("pipx"):
            return [["pipx", "install", "legendary-gl"]]

        venv = self.legendary_venv_dir()
        py = str(venv / "bin" / "python")
        return [
            [sys.executable, "-m", "venv", str(venv)],
            [py, "-m", "pip", "install", "--upgrade", "pip"],
            [py, "-m", "pip", "install", "legendary-gl"],
        ]

    def install_legendary(self, *, dry_run: bool = False) -> bool:
        """Install Legendary in user space (pipx preferred, else app venv).

        Synchronous: run it from a background worker. Returns True on success.
        """
        commands = self.install_commands_preview()
        method = "pipx" if which("pipx") else "environnement virtuel dédié"
        self._runner.log("info", f"Installation de Legendary via {method} …")
        if not which("pipx"):
            self.legendary_venv_dir().parent.mkdir(parents=True, exist_ok=True)

        previous = self._runner.dry_run
        self._runner.dry_run = dry_run
        ok = True
        try:
            for cmd in commands:
                result = self._runner.run(cmd)
                if not result.ok and not dry_run:
                    ok = False
                    break
        finally:
            self._runner.dry_run = previous

        if ok and not dry_run:
            found = self.find_legendary()
            if found:
                self._runner.log("info", f"Legendary installé : {found}")
            else:
                self._runner.log(
                    "warning",
                    "Installation terminée mais 'legendary' est introuvable. "
                    "Vérifiez le Journal pour d'éventuelles erreurs.",
                )
                ok = False
        return ok

    # -- auth flow ---------------------------------------------------------- #
    @staticmethod
    def auth_url() -> str:
        """Epic login helper URL used for the manual authorizationCode flow."""
        from . import constants

        return constants.LEGENDARY_AUTH_URL

    def start_auth(self):
        """Launch ``legendary auth`` (opens the secure browser OAuth flow).

        Fire-and-forget: Legendary opens the user's real browser. We never use
        an internal WebView and never see the Epic password.
        """
        binary = self.find_legendary()
        if not binary:
            self._runner.log("error", "Legendary introuvable. Installez-le d'abord.")
            return None
        self._runner.log(
            "info",
            "Lancement de 'legendary auth'. Une page de connexion Epic va "
            "s'ouvrir dans votre navigateur. Ce programme ne voit jamais votre "
            "mot de passe. Si le navigateur ne s'ouvre pas, utilisez la "
            "« Connexion manuelle avec code ».",
        )
        return self._runner.run_async([binary, "auth"])

    @staticmethod
    def extract_authorization_code(raw: str) -> str:
        """Extract an authorizationCode from raw user input.

        Accepts the bare code, the full JSON Epic returns
        (``{"authorizationCode": "…"}``), or a redirect URL containing
        ``?code=`` / ``&code=``.
        """
        text = (raw or "").strip()
        if not text:
            return ""
        if text.startswith("{"):
            try:
                data = json.loads(text)
                for key in ("authorizationCode", "code"):
                    if data.get(key):
                        return str(data[key]).strip()
            except json.JSONDecodeError:
                pass
        if "code=" in text and ("http://" in text or "https://" in text or "?" in text):
            import urllib.parse

            try:
                query = urllib.parse.urlparse(text).query
                params = urllib.parse.parse_qs(query)
                if params.get("code"):
                    return params["code"][0].strip()
            except ValueError:
                pass
        return text

    def authenticate_with_code(self, raw_code: str) -> bool:
        """Authenticate using a pasted authorizationCode (manual flow).

        Tries ``legendary auth --code <CODE>`` first; if that Legendary build
        does not support ``--code``, falls back to feeding the code to
        ``legendary auth`` on stdin. Synchronous; returns True on success.
        """
        binary = self.find_legendary()
        if not binary:
            self._runner.log("error", "Legendary introuvable. Installez-le d'abord.")
            return False

        code = self.extract_authorization_code(raw_code)
        if not code:
            self._runner.log("error", "Aucun authorizationCode valide fourni.")
            return False

        self._runner.log("info", "Validation du code d'autorisation via Legendary …")
        result = self._runner.run([binary, "auth", "--code", code], timeout=120)

        if not result.ok and _looks_like_unknown_arg(result.stdout):
            self._runner.log(
                "info",
                "Cette version de Legendary ne connaît pas '--code' ; nouvelle "
                "tentative en mode interactif (code envoyé sur l'entrée standard).",
            )
            result = self._runner.run(
                [binary, "auth"], input_text=code + "\n", timeout=120
            )

        if result.ok:
            self.refresh_status()
            if self.state.logged_in:
                self._runner.log("info", "Connexion Epic réussie.")
            return True
        self._runner.log(
            "error",
            "La validation du code a échoué. Vérifiez que le code n'a pas "
            "expiré (il est valable peu de temps) et régénérez-en un si besoin.",
        )
        return False

    def test_connection(self) -> tuple[bool, str]:
        """Test the Epic session with ``legendary list``. Returns (ok, account)."""
        binary = self.find_legendary()
        if not binary:
            self._runner.log("error", "Legendary introuvable.")
            return False, ""
        self._runner.log("info", "Test de la connexion (legendary list) …")
        result = self._runner.run([binary, "list"], timeout=60)
        state = self.refresh_status()
        if result.ok:
            who = state.username or ""
            self._runner.log(
                "info", f"Connecté{f' en tant que {who}' if who else ''}.")
            return True, who
        self._runner.log(
            "warning",
            "Non connecté. Essayez la « Connexion manuelle avec code » : "
            "ouvrez la page Epic, copiez la valeur 'authorizationCode', puis "
            "collez-la dans l'application.",
        )
        return False, state.username

    def open_config_folder(self):
        """Open Legendary's config folder (~/.config/legendary) for the user."""
        config = Path.home() / ".config" / "legendary"
        if not config.exists():
            self._runner.log(
                "warning",
                f"Dossier de configuration Legendary introuvable : {config}",
            )
            return None
        return self._runner.run_async(["xdg-open", str(config)])

    def logout(self) -> bool:
        """Delete the local Legendary session. Synchronous; returns True on success."""
        binary = self.find_legendary()
        if not binary:
            self.state = AccountState(method="manual")
            self.state.save()
            return True
        result = self._runner.run([binary, "auth", "--delete"], timeout=60)
        self.state = AccountState(logged_in=False, username="", method="legendary")
        self.state.save()
        if not result.ok:
            self._runner.log(
                "warning",
                "La suppression automatique a échoué. Vous pouvez supprimer la "
                "session manuellement dans ~/.config/legendary.",
            )
        return result.ok

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


def _looks_like_unknown_arg(output: str) -> bool:
    """Heuristic: did Legendary reject the ``--code`` argument?"""
    text = (output or "").lower()
    return any(
        marker in text
        for marker in (
            "unrecognized arguments",
            "invalid choice",
            "unrecognized argument",
            "error: argument",
            "no such option",
        )
    )
