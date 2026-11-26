"""Editor de reglas y acciones sin editar JSON."""
from __future__ import annotations

from functools import partial
import math
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFileDialog,
    QFormLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget, QMessageBox,
    QPushButton, QVBoxLayout, QWidget,
)

from ..connectors.simulator import sample_event
from ..core.actions import run_action
from ..core.config import Action
from ..core.editing import STEP_FIELDS
from ..overlay_manager import list_overlays


def buttons(layout, pairs):
    row = QHBoxLayout()
    for label, handler in pairs:
        button = QPushButton(label)
        button.clicked.connect(handler)
        row.addWidget(button)
    row.addStretch()
    layout.addLayout(row)


def combo(items, current="", *, editable=False):
    box = QComboBox()
    box.setEditable(editable)
    for label, value in items:
        box.addItem(label, value)
    index = box.findData(current)
    if index >= 0:
        box.setCurrentIndex(index)
    elif current:
        if editable:
            box.setEditText(current)
        else:
            box.addItem(str(current), current)
            box.setCurrentIndex(box.count() - 1)
    return box


class Form(QDialog):
    def __init__(self, parent, title):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(540, 280)
        self.outer = QVBoxLayout(self)
        self.form = QFormLayout()
        self.outer.addLayout(self.form)

    def finish(self):
        box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        self.outer.addWidget(box)


class TriggerForm(Form):
    def __init__(self, parent, data, actions):
        super().__init__(parent, "Editar trigger")
        self.original = data
        self.name = QLineEdit(data.get("name", ""))
        self.enabled = QCheckBox()
        self.enabled.setChecked(data.get("enabled", True))
        choices = [("*", "*")] + [(p, p) for p in ("tiktok", "twitch", "youtube", "kick", "manual")]
        self.platform = combo(choices, data.get("platform", "*"))
        names = ("gift", "follow", "chat", "command", "donation", "bits", "points", "like", "share", "sub")
        self.event = combo([(n, n) for n in names], data.get("event_type", "gift"), editable=True)
        self.action = combo([(a.name, a.id) for a in actions], data.get("action_id"))
        self.cooldown = QDoubleSpinBox()
        self.cooldown.setRange(0, 86400)
        self.cooldown.setValue(data.get("cooldown_s", 0))
        self.cooldown.setSuffix(" s")
        for label, widget in (("Nombre", self.name), ("Activo", self.enabled), ("Plataforma (* = todas)", self.platform),
                              ("Evento", self.event), ("Acción", self.action), ("Espera entre ejecuciones", self.cooldown)):
            self.form.addRow(label, widget)
        self.filters = {}
        for key, label in (("gift_name", "Regalo exacto"), ("user", "Usuario exacto"), ("contains", "Texto contiene"),
                           ("command", "Comando exacto"), ("min_value", "Valor mínimo")):
            value = data.get("filters", {}).get(key, "")
            self.filters[key] = QLineEdit(str(value))
            self.form.addRow(label, self.filters[key])
        self.finish()

    def accept(self):
        filters = dict(self.original.get("filters", {}))
        for key, field in self.filters.items():
            value = field.text().strip()
            filters.pop(key, None)
            if value:
                filters[key] = value
        if "min_value" in filters:
            try:
                value = float(filters["min_value"])
                if not math.isfinite(value) or value < 0:
                    raise ValueError()
                filters["min_value"] = value
            except ValueError:
                QMessageBox.warning(self, "Filtro", "Escribe un valor mínimo numérico y no negativo.")
                return
        self.result_data = {**self.original, "name": self.name.text(), "enabled": self.enabled.isChecked(),
                            "platform": self.platform.currentData(), "event_type": self.event.currentText().strip(),
                            "action_id": self.action.currentData(), "cooldown_s": self.cooldown.value(), "filters": filters}
        super().accept()


class StepForm(Form):
    def __init__(self, parent, data):
        super().__init__(parent, "Editar paso")
        self.original = data
        self.kind = combo([(label, key) for key, (label, _) in STEP_FIELDS.items()], data.get("type"))
        self.form.addRow("Tipo", self.kind)
        self.dynamic = QFormLayout()
        self.outer.addLayout(self.dynamic)
        self.kind.currentIndexChanged.connect(self.rebuild)
        self.rebuild()
        self.finish()

    def rebuild(self):
        while self.dynamic.rowCount():
            self.dynamic.removeRow(0)
        self.fields = {}
        kind = self.kind.currentData()
        for key, label, mode, default in STEP_FIELDS.get(kind, ("", ()))[1]:
            value = self.original.get(key, default) if kind == self.original.get("type") else default
            if mode == "bool":
                widget = QCheckBox()
                widget.setChecked(value is True or str(value).lower() in ("true", "1", "sí", "si", "yes"))
                row = widget
            elif mode == "overlay":
                widget = combo([(o.name, o.id) for o in list_overlays().values()], value)
                row = widget
            elif mode == "file":
                widget = QLineEdit(str(value))
                row = QHBoxLayout()
                row.addWidget(widget)
                browse = QPushButton("Buscar…")
                browse.clicked.connect(partial(self.pick, widget))
                row.addWidget(browse)
            else:
                widget = QLineEdit(str(value))
                row = widget
            self.fields[key] = (mode, widget)
            self.dynamic.addRow(label, row)

    def pick(self, widget):
        name, _ = QFileDialog.getOpenFileName(self, "Selecciona audio", str(Path.home()))
        if name:
            widget.setText(name)

    def accept(self):
        kind = self.kind.currentData()
        if kind not in STEP_FIELDS:
            QMessageBox.warning(self, "Paso", "Elige un tipo compatible o cancela para conservar el original.")
            return
        data = dict(self.original) if kind == self.original.get("type") else {}
        data["type"] = kind
        for key, (mode, field) in self.fields.items():
            value = field.isChecked() if mode == "bool" else field.currentData() if mode == "overlay" else field.text().strip()
            if mode in {"required", "file", "number", "overlay"} and not value:
                QMessageBox.warning(self, "Paso incompleto", f"Completa el campo «{key}».")
                return
            if mode == "number":
                try:
                    value = float(value)
                    if not math.isfinite(value) or not 0 <= value <= 3600:
                        raise ValueError()
                except (TypeError, ValueError):
                    QMessageBox.warning(self, "Duración", "Escribe de 0 a 3600 segundos.")
                    return
            data[key] = value
        self.result_data = data
        super().accept()


class ActionForm(Form):
    def __init__(self, parent, data):
        super().__init__(parent, "Editar acción")
        self.original = data
        self.name = QLineEdit(data.get("name", ""))
        self.form.addRow("Nombre", self.name)
        self.steps = [dict(s) for s in data.get("steps", [])]
        self.list = QListWidget()
        self.outer.addWidget(self.list)
        self.list.itemDoubleClicked.connect(lambda _item: self.edit())
        buttons(self.outer, [("Agregar paso", lambda: self.edit(True)), ("Editar", self.edit), ("Quitar", self.remove)])
        buttons(self.outer, [("Subir", lambda: self.move(-1)), ("Bajar", lambda: self.move(1))])
        self.refresh()
        self.finish()

    def refresh(self, index=0):
        self.list.clear()
        for step in self.steps:
            kind = step.get("type", "?")
            title = STEP_FIELDS.get(kind, (kind, ()))[0]
            detail = " · ".join(str(v) for k, v in step.items() if k not in {"type", "id"} and v != "")
            self.list.addItem(f"{title}: {detail}")
        self.list.setCurrentRow(min(index, len(self.steps) - 1))

    def edit(self, new=False):
        i = -1 if new else self.list.currentRow()
        if not new and i < 0:
            return
        form = StepForm(self, self.steps[i] if i >= 0 else {})
        if form.exec():
            if i < 0:
                i = len(self.steps)
                self.steps.append(form.result_data)
            else:
                self.steps[i] = form.result_data
            self.refresh(i)

    def remove(self):
        i = self.list.currentRow()
        if i >= 0:
            self.steps.pop(i)
            self.refresh(i)

    def move(self, delta):
        i = self.list.currentRow()
        if i >= 0 and 0 <= i + delta < len(self.steps):
            self.steps[i], self.steps[i + delta] = self.steps[i + delta], self.steps[i]
            self.refresh(i + delta)

    def accept(self):
        self.result_data = {**self.original, "name": self.name.text(), "steps": self.steps}
        super().accept()


class RulesPanel(QWidget):
    completed = Signal(str)

    def __init__(self, rt, kind, changed):
        super().__init__()
        self.rt, self.kind, self.changed = rt, kind, changed
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            "Vincula eventos con acciones. Los filtros vacíos no limitan el evento." if kind == "trigger"
            else "Los pasos se ejecutan en orden. Puedes usar variables como {user}, {text} y {gift_name}."))
        self.list = QListWidget()
        layout.addWidget(self.list)
        self.list.itemDoubleClicked.connect(lambda _item: self.edit())
        pairs = [("Nuevo", lambda: self.edit(True)), ("Editar", lambda: self.edit()), ("Eliminar", self.delete)]
        if kind == "action" and not rt.editor_only:
            pairs.append(("Ejecutar con regalo de prueba", self.test_action))
        buttons(layout, pairs)
        self.result = QLabel()
        self.result.setWordWrap(True)
        layout.addWidget(self.result)
        self.completed.connect(self.on_complete)
        self.changed.connect(self.refresh)
        self.refresh()

    def refresh(self):
        self.items = self.rt.config.triggers if self.kind == "trigger" else self.rt.config.actions
        current = self.list.currentRow()
        self.list.clear()
        for item in self.items:
            suffix = f" · {item.platform}/{item.event_type}" + ("" if item.enabled else " · desactivado") if self.kind == "trigger" else f" · {len(item.steps)} paso(s)"
            self.list.addItem(item.name + suffix)
        self.list.setCurrentRow(min(max(0, current), len(self.items) - 1))

    def selected(self):
        i = self.list.currentRow()
        return self.items[i] if 0 <= i < len(self.items) else None

    def send(self, coro):
        self.setEnabled(False)
        signal = self.completed
        def done(future):
            if not future.cancelled():
                signal.emit(str(future.exception() or ""))
        self.rt.submit(coro).add_done_callback(done)

    def on_complete(self, error):
        self.setEnabled(True)
        self.result.setText(error or "Listo. Consulta Registro para ver el resultado de las pruebas.")
        if not error:
            self.changed.emit(self.kind)

    def edit(self, new=False):
        item = None if new else self.selected()
        if not new and item is None:
            return
        data = item.to_dict() if item else {}
        form = TriggerForm(self, data, self.rt.config.actions) if self.kind == "trigger" else ActionForm(self, data)
        if form.exec():
            self.send(self.rt.edit_rule(self.kind, form.result_data))

    def delete(self):
        item = self.selected()
        if item and QMessageBox.question(self, "Eliminar", f"¿Eliminar «{item.name}»?") == QMessageBox.Yes:
            self.send(self.rt.edit_rule(self.kind, {"id": item.id}, delete=True))

    def test_action(self):
        action = self.selected()
        if action and QMessageBox.question(self, "Ejecutar acción",
                "Se ejecutarán sus pasos reales, incluidos cambios de OBS o audio. ¿Continuar?") == QMessageBox.Yes:
            self.send(run_action(self.rt, Action.from_dict(action.to_dict()), sample_event("gift")))
