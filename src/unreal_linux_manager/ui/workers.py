"""Generic QThread worker so the GUI never blocks on slow operations.

Any callable (scan, ZIP extraction, diagnostics, a subprocess wrapper) can be
pushed onto a :class:`Worker`. Results and log lines are delivered back to the
main thread through Qt signals, which is the only thread-safe way to touch
widgets.
"""

from __future__ import annotations

import traceback
from typing import Any, Callable

from PySide6.QtCore import QObject, QThread, Signal


class Worker(QObject):
    """Runs a single callable on a background thread."""

    finished = Signal(object)          # result value
    failed = Signal(str)               # error message
    progress = Signal(int, int)        # (done, total)
    log = Signal(str, str)             # (level, message)

    def __init__(self, func: Callable[..., Any], *args, **kwargs) -> None:
        super().__init__()
        self._func = func
        self._args = args
        self._kwargs = kwargs

    def run(self) -> None:
        try:
            # Expose a progress emitter to the callable if it accepts one.
            if "progress" in self._func.__code__.co_varnames:  # type: ignore[attr-defined]
                self._kwargs.setdefault("progress", self.progress.emit)
        except Exception:
            pass
        try:
            result = self._func(*self._args, **self._kwargs)
            self.finished.emit(result)
        except Exception as exc:  # noqa: BLE001 - report every failure to the UI
            details = "".join(traceback.format_exception_only(type(exc), exc)).strip()
            self.failed.emit(details)


class TaskRunner:
    """Owns a QThread + Worker pair and keeps them alive until completion.

    Usage::

        runner = TaskRunner(self)  # parent keeps a reference
        runner.start(func, args...,
                     on_finished=cb, on_failed=cb, on_progress=cb, on_log=cb)
    """

    def __init__(self, parent: QObject) -> None:
        self._parent = parent
        self._threads: list[QThread] = []

    def start(
        self,
        func: Callable[..., Any],
        *args,
        on_finished: Callable[[Any], None] | None = None,
        on_failed: Callable[[str], None] | None = None,
        on_progress: Callable[[int, int], None] | None = None,
        on_log: Callable[[str, str], None] | None = None,
        **kwargs,
    ) -> None:
        thread = QThread(self._parent)
        worker = Worker(func, *args, **kwargs)
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        if on_finished is not None:
            worker.finished.connect(on_finished)
        if on_failed is not None:
            worker.failed.connect(on_failed)
        if on_progress is not None:
            worker.progress.connect(on_progress)
        if on_log is not None:
            worker.log.connect(on_log)

        # Tear down the thread when the worker is done (success or failure).
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(lambda: self._cleanup(thread))

        self._threads.append(thread)
        thread.start()

    def _cleanup(self, thread: QThread) -> None:
        if thread in self._threads:
            self._threads.remove(thread)
        thread.deleteLater()

    def wait_all(self, timeout_ms: int = 3000) -> None:
        """Ask running threads to finish; used on application shutdown."""
        for thread in list(self._threads):
            thread.quit()
            thread.wait(timeout_ms)
