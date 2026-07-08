"""Run external commands safely and stream their output to the Journal.

The :class:`CommandRunner` centralises every ``subprocess`` invocation so that:

* stdout/stderr are captured and forwarded to a log callback line by line;
* the return code is always reported;
* ``sudo`` is never run silently (a guard forces explicit opt-in);
* a global dry-run mode can turn any call into a no-op that only logs;
* long-running commands can be executed on a background thread without
  blocking the Qt event loop.

The module is intentionally free of any Qt import so it can be unit tested and
reused headless.
"""

from __future__ import annotations

import logging
import os
import shlex
import subprocess
import threading
from dataclasses import dataclass, field
from typing import Callable, Sequence

LogCallback = Callable[[str, str], None]  # (level, message)

_logger = logging.getLogger("unreal_linux_manager.command")


@dataclass
class CommandResult:
    """Outcome of a command execution."""

    command: list[str]
    returncode: int
    stdout: str = ""
    stderr: str = ""
    started: bool = True  # False when blocked (e.g. sudo without confirm)
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.started and self.returncode == 0


@dataclass
class CommandRunner:
    """Execute commands and forward their output to a log sink."""

    log_callback: LogCallback | None = None
    dry_run: bool = False
    allow_sudo: bool = False
    verbose: bool = False
    _extra_sinks: list[LogCallback] = field(default_factory=list)

    # -- logging ------------------------------------------------------------ #
    def add_sink(self, callback: LogCallback) -> None:
        """Register an additional log sink (e.g. the GUI Journal panel)."""
        self._extra_sinks.append(callback)

    def _emit(self, level: str, message: str) -> None:
        _logger.log(getattr(logging, level.upper(), logging.INFO), message)
        if self.log_callback is not None:
            self.log_callback(level, message)
        for sink in self._extra_sinks:
            try:
                sink(level, message)
            except Exception:  # a broken GUI sink must never crash a command
                pass

    def log(self, level: str, message: str) -> None:
        """Public helper so other modules can push messages to the Journal."""
        self._emit(level, message)

    # -- helpers ------------------------------------------------------------ #
    @staticmethod
    def format_command(command: Sequence[str]) -> str:
        return " ".join(shlex.quote(part) for part in command)

    def _is_sudo(self, command: Sequence[str]) -> bool:
        return bool(command) and os.path.basename(command[0]) in {"sudo", "pkexec"}

    # -- execution ---------------------------------------------------------- #
    def run(
        self,
        command: Sequence[str],
        *,
        cwd: str | os.PathLike | None = None,
        env: dict[str, str] | None = None,
        timeout: float | None = None,
        input_text: str | None = None,
    ) -> CommandResult:
        """Run a command synchronously and return its :class:`CommandResult`."""
        cmd = [str(part) for part in command]
        pretty = self.format_command(cmd)

        if self._is_sudo(cmd) and not self.allow_sudo:
            msg = f"Commande privilégiée bloquée (confirmation requise) : {pretty}"
            self._emit("warning", msg)
            return CommandResult(cmd, returncode=126, started=False, error=msg)

        if self.dry_run:
            self._emit("info", f"[dry-run] {pretty}")
            return CommandResult(cmd, returncode=0, started=True)

        self._emit("info", f"$ {pretty}")

        merged_env = None
        if env:
            merged_env = {**os.environ, **env}

        try:
            proc = subprocess.Popen(
                cmd,
                cwd=str(cwd) if cwd else None,
                env=merged_env,
                stdin=subprocess.PIPE if input_text is not None else None,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
        except FileNotFoundError:
            msg = f"Commande introuvable : {cmd[0]}"
            self._emit("error", msg)
            return CommandResult(cmd, returncode=127, started=False, error=msg)
        except PermissionError as exc:
            msg = f"Permission refusée : {pretty} ({exc})"
            self._emit("error", msg)
            return CommandResult(cmd, returncode=126, started=False, error=msg)
        except OSError as exc:
            msg = f"Échec du lancement : {pretty} ({exc})"
            self._emit("error", msg)
            return CommandResult(cmd, returncode=1, started=False, error=str(exc))

        if input_text is not None and proc.stdin is not None:
            try:
                proc.stdin.write(input_text)
                proc.stdin.close()
            except (BrokenPipeError, OSError):
                pass

        collected: list[str] = []
        try:
            assert proc.stdout is not None
            for raw in proc.stdout:
                line = raw.rstrip("\n")
                collected.append(line)
                if line and (self.verbose or True):
                    self._emit("info", line)
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            msg = f"Délai dépassé : {pretty}"
            self._emit("error", msg)
            return CommandResult(
                cmd, returncode=124, stdout="\n".join(collected),
                started=True, error=msg,
            )
        except KeyboardInterrupt:  # pragma: no cover
            proc.kill()
            raise

        output = "\n".join(collected)
        rc = proc.returncode or 0
        level = "info" if rc == 0 else "error"
        self._emit(level, f"↳ code de sortie {rc}")
        return CommandResult(cmd, returncode=rc, stdout=output, started=True)

    def run_async(
        self,
        command: Sequence[str],
        *,
        on_finished: Callable[[CommandResult], None] | None = None,
        **kwargs,
    ) -> threading.Thread:
        """Run a command on a daemon thread; call ``on_finished`` when done.

        This is a lightweight fallback for headless usage. The GUI uses the
        dedicated Qt worker in :mod:`ui.workers` instead, so it can marshal
        results back onto the main thread safely.
        """

        def target() -> None:
            result = self.run(command, **kwargs)
            if on_finished is not None:
                on_finished(result)

        thread = threading.Thread(target=target, daemon=True)
        thread.start()
        return thread


def which(program: str) -> str | None:
    """Return the absolute path of ``program`` on ``PATH`` or ``None``."""
    from shutil import which as _which

    return _which(program)
