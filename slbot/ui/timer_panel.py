"""Editor de temporizadores del perfil."""
from __future__ import annotations

from uuid import uuid4

from PySide6.QtCore import Signal, Slot, Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPushButton, QSpinBox, QVBoxLayout, QWidget,
)

from ..core.timers import Timer, read_timers
from .deletion import confirm_delete, delete_shortcut
from .rule_editor import ActionWorkspace


class TimerForm(QDialog):
    def __init__(self, parent, actions, existing):
        super().__init__(parent)
        self.setWindowTitle("Temporizador")
        self.result_data = {}
        form = QFormLayout(self)
        self.name = QLineEdit(existing.name if existing else "")
        self.name.setMaxLength(100)
        self.action = QComboBox()
        for item in actions:
            self.action.addItem(item.name, item.id)
        if existing:
            self.action.setCurrentIndex(self.action.findData(existing.action_id))
        self.interval = QSpinBox()
        self.interval.setRange(1, 86400)
        self.interval.setValue(existing.seconds if existing else 60)
        self.enabled = QCheckBox("Ejecutar mientras el bot esté abierto")
        self.enabled.setChecked(bool(existing and existing.enabled))
        form.addRow("Nombre", self.name)
        form.addRow("Acción", self.action)
        form.addRow("Cada (segundos)", self.interval)
        form.addRow("Activo", self.enabled)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)
        self.ident = existing.id if existing else uuid4().hex

    def accept(self):
        raw = {"id": self.ident, "name": self.name.text(), "action_id": self.action.currentData(),
               "seconds": self.interval.value(), "enabled": self.enabled.isChecked()}
        try:
            self.result_data = Timer.parse(raw).to_dict()
        except ValueError as exc:
            QMessageBox.warning(self, "Revisa el temporizador", str(exc))
            return
        super().accept()


class TimerPanel(QWidget):
    completed = Signal(str)

    def __init__(self, rt, rules_changed):
        super().__init__()
        self.rt = rt
        self.pending = False
        self.timers = []
        self.completed.connect(self._done, Qt.ConnectionType.QueuedConnection)
        layout = QVBoxLayout(self)
        row = QHBoxLayout()
        self.add = QPushButton("Agregar")
        self.edit = QPushButton("Editar")
        self.toggle = QPushButton("Activar")
        self.delete = QPushButton("Eliminar")
        self.add.clicked.connect(lambda: self._form(None))
        self.edit.clicked.connect(lambda: self._form(self._selected()))
        self.toggle.clicked.connect(self._toggle)
        self.delete.clicked.connect(self._delete)
        for button in (self.add, self.edit, self.toggle, self.delete):
            row.addWidget(button)
        row.addStretch()
        layout.addLayout(row)
        self.table = ActionWorkspace._table(("Temporizador", "Acción", "Intervalo", "Estado"), "timers", stretch=1)
        self.table.itemSelectionChanged.connect(self._buttons)
        delete_shortcut(self.table, self._delete)
        layout.addWidget(self.table)
        self.status = QLabel("El primer ciclo se ejecuta tras el intervalo. Desactivar no interrumpe una acción en curso.")
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        rules_changed.connect(self.refresh)
        self.refresh()

    def _selected(self):
        index = self.table.currentRow()
        return self.timers[index] if self.table.selectedItems() and 0 <= index < len(self.timers) else None

    def _buttons(self):
        timer = self._selected()
        self.add.setEnabled(not self.pending and bool(self.rt.config.actions))
        for button in (self.edit, self.toggle, self.delete):
            button.setEnabled(not self.pending and timer is not None)
        self.toggle.setText("Desactivar" if timer and timer.enabled else "Activar")

    def refresh(self, _kind=None):
        previous = self._selected()
        self.timers = read_timers(self.rt.config.settings)
        names = {item.id: item.name for item in self.rt.config.actions}
        rows = [(timer.name, names.get(timer.action_id, "Acción no disponible"),
                 f"{timer.seconds} s", "Activo" if timer.enabled else "Inactivo")
                for timer in self.timers]
        idx = next((i for i, item in enumerate(self.timers) if previous and item.id == previous.id), -1)
        ActionWorkspace._fill(self.table, rows, idx if idx >= 0 else (0 if rows else -1), tooltips=False)
        self._buttons()

    def _form(self, timer):
        dialog = TimerForm(self, self.rt.config.actions, timer)
        if dialog.exec():
            self._save(dialog.result_data)

    def _toggle(self):
        timer = self._selected()
        if timer:
            self._save({**timer.to_dict(), "enabled": not timer.enabled})

    def _delete(self):
        timer = self._selected()
        if not self.pending and timer and confirm_delete(
                self, "Eliminar temporizador", f"¿Eliminar el temporizador «{timer.name}»?\n\n"
                "No volverá a dispararse. Una acción que ya está en curso puede terminar."):
            self._save({"id": timer.id}, delete=True)

    def _save(self, data, *, delete=False):
        self.pending = True
        self._buttons()
        self.status.setText("Guardando…")
        notify = self.completed

        def done(result):
            message = "Se canceló la operación." if result.cancelled() else str(result.exception() or "")
            try:
                notify.emit(message)
            except RuntimeError:
                pass

        self.rt.submit(self.rt.edit_timer(data, delete=delete)).add_done_callback(done)

    @Slot(str)
    def _done(self, error):
        self.pending = False
        success = ("Guardado. Recarga el perfil en el servidor para aplicarlo." if self.rt.editor_only else
                   "Guardado. Consulta Historial para ver las ejecuciones.")
        self.status.setText(error or success)
        self.refresh()
