"""The bottom "Journal" log panel shared by the whole window."""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Signal
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

# Simple textual prefixes rather than colours/effects, matching the sober,
# "system settings" aesthetic requested.
_LEVEL_PREFIX = {
    "info": "[i]",
    "warning": "[!]",
    "error": "[X]",
    "debug": "[.]",
}


class JournalPanel(QGroupBox):
    """A read-only log view with copy/clear controls.

    The :meth:`append` slot is thread-affine: it is always invoked on the GUI
    thread via a queued signal so background workers can log safely.
    """

    _append_requested = Signal(str, str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Journal", parent)
        self._verbose = False

        layout = QVBoxLayout(self)

        self._view = QPlainTextEdit()
        self._view.setReadOnly(True)
        self._view.setMaximumBlockCount(5000)
        self._view.setLineWrapMode(QPlainTextEdit.NoWrap)
        layout.addWidget(self._view)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self._copy_btn = QPushButton("Copier le journal")
        self._clear_btn = QPushButton("Effacer")
        buttons.addWidget(self._copy_btn)
        buttons.addWidget(self._clear_btn)
        layout.addLayout(buttons)

        self._copy_btn.clicked.connect(self._copy)
        self._clear_btn.clicked.connect(self._view.clear)

        # Queued connection guarantees GUI-thread execution.
        self._append_requested.connect(self._do_append)

    def set_verbose(self, verbose: bool) -> None:
        self._verbose = verbose

    # -- logging sink ------------------------------------------------------- #
    def log(self, level: str, message: str) -> None:
        """Thread-safe entry point used as a CommandRunner sink."""
        if level == "debug" and not self._verbose:
            return
        self._append_requested.emit(level, message)

    def _do_append(self, level: str, message: str) -> None:
        prefix = _LEVEL_PREFIX.get(level, "[i]")
        timestamp = datetime.now().strftime("%H:%M:%S")
        for line in message.splitlines() or [""]:
            self._view.appendPlainText(f"{timestamp} {prefix} {line}")
        self._view.moveCursor(QTextCursor.End)

    def _copy(self) -> None:
        from PySide6.QtWidgets import QApplication

        QApplication.clipboard().setText(self._view.toPlainText())
