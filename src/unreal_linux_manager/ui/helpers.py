"""Small reusable UI helpers kept free of business logic."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication, QMessageBox, QWidget


def info_box(parent: QWidget, title: str, text: str) -> None:
    QMessageBox.information(parent, title, text)


def warn_box(parent: QWidget, title: str, text: str) -> None:
    QMessageBox.warning(parent, title, text)


def error_box(parent: QWidget, title: str, text: str) -> None:
    QMessageBox.critical(parent, title, text)


def confirm(parent: QWidget, title: str, text: str) -> bool:
    reply = QMessageBox.question(
        parent, title, text,
        QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
    )
    return reply == QMessageBox.Yes


def copy_to_clipboard(text: str) -> None:
    QApplication.clipboard().setText(text)
