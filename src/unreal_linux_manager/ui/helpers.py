"""Small reusable UI helpers kept free of business logic."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication, QMessageBox, QPushButton, QWidget


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


def three_way(
    parent: QWidget,
    title: str,
    text: str,
    *,
    yes_text: str,
    alt_text: str,
    no_text: str,
) -> str:
    """A three-button dialog. Returns "yes", "alt" or "no"."""
    box = QMessageBox(parent)
    box.setWindowTitle(title)
    box.setText(text)
    box.setIcon(QMessageBox.Question)
    yes_btn = box.addButton(yes_text, QMessageBox.AcceptRole)
    alt_btn = box.addButton(alt_text, QMessageBox.ActionRole)
    no_btn = box.addButton(no_text, QMessageBox.RejectRole)
    box.setDefaultButton(alt_btn)
    box.exec()
    clicked = box.clickedButton()
    if clicked is yes_btn:
        return "yes"
    if clicked is alt_btn:
        return "alt"
    return "no"
