"""Confirmations and focused Delete shortcuts for editable records."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QMessageBox


def confirm_delete(parent, title: str, message: str) -> bool:
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Question)
    box.setWindowTitle(title)
    box.setTextFormat(Qt.TextFormat.PlainText)
    box.setText(message)
    box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
    box.button(QMessageBox.StandardButton.Yes).setText("Eliminar")
    box.button(QMessageBox.StandardButton.No).setText("Cancelar")
    box.setDefaultButton(QMessageBox.StandardButton.No)
    box.setEscapeButton(QMessageBox.StandardButton.No)
    return box.exec() == QMessageBox.StandardButton.Yes


def delete_shortcut(widget, callback) -> QShortcut:
    shortcut = QShortcut(QKeySequence(Qt.Key.Key_Delete), widget)
    shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
    shortcut.setAutoRepeat(False)
    shortcut.activated.connect(callback)
    return shortcut
