"""Editor de reglas y acciones sin editar JSON."""
from __future__ import annotations

from functools import partial
import math
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
    QFileDialog, QFormLayout, QFrame, QHeaderView, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QMenu, QMessageBox, QPushButton, QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ..connectors.simulator import sample_event
from ..core.config import Action
from ..core.action_pack import ActionPack
from ..core.editing import STEP_FIELDS, action_callers, action_references
from ..core.flow import OPERATORS, VALUELESS_OPERATORS, validate_steps
from ..core.trigger_catalog import CHAT_PERMISSIONS, EVENTS, PLATFORMS, event_hint, event_label
from ..overlay_manager import list_overlays
from ..overlay_server import NOW_PLAYING_IDS
from .deletion import confirm_delete, delete_shortcut


def confirm_action_deletion(parent, config, item):
    callers = action_callers(config, item.id)
    if callers:
        names = ", ".join(action.name[:80] for action in callers[:5])
        QMessageBox.information(parent, "Acción en uso",
                               "Quita primero las referencias en estas acciones: " + names)
        return None
    triggers, timers = action_references(config, item.id)
    message = f"¿Eliminar la acción «{item.name}»?"
    for label, refs in (("Disparadores", triggers), ("Temporizadores", timers)):
        if refs:
            names = ", ".join(t.name[:70] for t in refs[:4])
            if len(refs) > 4:
                names += f" y {len(refs) - 4} más"
            message += f"\n\n{label} vinculados que también se eliminarán ({len(refs)}): {names}."
    if not confirm_delete(parent, "Eliminar acción", message):
        return None
    return {"id": item.id, "confirmed_dependencies": {
        "triggers": sorted({t.id for t in triggers}), "timers": sorted({t.id for t in timers}),
    }}


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
    def __init__(self, parent, data, actions, *, fixed_action=False):
        super().__init__(parent, "Configurar disparador")
        self.original = data
        self.name = QLineEdit(data.get("name", ""))
        self.enabled = QCheckBox()
        self.enabled.setChecked(data.get("enabled", True))
        self.platform = combo([(label, key) for key, label in PLATFORMS.items()], data.get("platform", "*"))
        choices = [(label, key) for key, (label, _) in EVENTS.items()]
        self.event = combo(choices, data.get("event_type", "gift"))
        self.advanced_event = QLineEdit()
        self.advanced_event.setPlaceholderText("Código del evento")
        self.event.addItem("Evento avanzado…", "")
        self.permission = combo([(label, key) for key, label in CHAT_PERMISSIONS.items()],
                                data.get("chat_permission", "everyone"))
        self.action = combo([(a.name, a.id) for a in actions], data.get("action_id"))
        self.action.setEnabled(not fixed_action)
        self.cooldown = QDoubleSpinBox()
        self.cooldown.setRange(0, 86400)
        self.cooldown.setValue(data.get("cooldown_s", 0))
        self.cooldown.setSuffix(" s")
        self.user_cooldown = QDoubleSpinBox()
        self.user_cooldown.setRange(0, 86400)
        self.user_cooldown.setValue(data.get("user_cooldown_s", 0))
        self.user_cooldown.setSuffix(" s")
        guide = QLabel("Cuando ocurra este evento y se cumplan los filtros, el bot ejecutará la acción elegida.")
        guide.setWordWrap(True)
        self.form.addRow(guide)
        for label, widget in (("Nombre de la regla", self.name), ("Activo", self.enabled),
                              ("Plataforma", self.platform), ("Evento", self.event),
                              ("Código personalizado", self.advanced_event)):
            self.form.addRow(label, widget)
        self.event_help = QLabel()
        self.event_help.setWordWrap(True)
        self.form.addRow(self.event_help)
        for label, widget in (("Acción a ejecutar", self.action), ("Espera global", self.cooldown),
                              ("Espera por usuario", self.user_cooldown), ("Quién puede activarlo", self.permission)):
            self.form.addRow(label, widget)
        self.filters = {}
        for key, label in (("gift_name", "Regalo exacto"), ("user", "Usuario exacto"), ("contains", "Texto contiene"),
                           ("command", "Comando exacto"), ("min_value", "Valor mínimo")):
            value = data.get("filters", {}).get(key, "")
            self.filters[key] = QLineEdit(str(value))
            self.form.addRow(label, self.filters[key])
        self.aliases = QLineEdit(", ".join(data.get("filters", {}).get("command_aliases", [])))
        self.aliases.setMaxLength(850)
        self.aliases.setPlaceholderText("Ej. hola, saludo, buenas")
        self.form.addRow("Alias del comando", self.aliases)
        self.event.currentIndexChanged.connect(self._refresh_fields)
        self.platform.currentIndexChanged.connect(self._refresh_fields)
        self.permission.currentIndexChanged.connect(self._refresh_fields)
        self._refresh_fields()
        self.finish()

    def _refresh_fields(self, *_):
        key = self.event.currentData()
        platform = self.platform.currentData()
        self.form.setRowVisible(self.advanced_event, key == "")
        hint = event_hint(key, platform)
        self.permissions_available = key in {"command", "chat"} and platform in {"*", "twitch", "youtube"}
        restricted = self.permission.currentData() != "everyone"
        self.form.setRowVisible(self.permission, self.permissions_available or restricted)
        if self.permissions_available:
            hint += " Los roles se comprueban solo en Twitch y YouTube."
        elif restricted:
            hint += " El permiso actual no se puede comprobar en este evento. Cámbialo explícitamente o elige otro evento."
        self.event_help.setText(hint)
        self.form.setRowVisible(self.aliases, key == "command" or bool(self.aliases.text()))
        relevant = {
            "gift_name": key == "gift", "user": True,
            "contains": key in {"chat", "command", "donation", "bits", "points"},
            "command": key == "command", "min_value": key in {"gift", "donation", "bits"},
        }
        for field, widget in self.filters.items():
            self.form.setRowVisible(widget, relevant[field] or bool(widget.text()))

    def accept(self):
        filters = dict(self.original.get("filters", {}))
        for key, field in self.filters.items():
            value = field.text().strip()
            filters.pop(key, None)
            if value:
                filters[key] = value
        aliases = list(dict.fromkeys(
            value.strip().removeprefix("!").casefold() for value in self.aliases.text().split(",") if value.strip()
        ))
        event_type = self.event.currentData() or self.advanced_event.text().strip()
        if not event_type:
            QMessageBox.warning(self, "Evento", "Elige un evento o escribe su código.")
            return
        permission = self.permission.currentData()
        if permission != "everyone" and not self.permissions_available:
            QMessageBox.warning(self, "Permiso del chat",
                                "Conserva un evento de Twitch o YouTube o elige explícitamente «Cualquier persona».")
            return
        filters.pop("command_aliases", None)
        if aliases:
            if event_type != "command" or len(aliases) > 20 or any(
                not a or len(a) > 40 or a.startswith("!") or not a.isprintable() or any(c.isspace() for c in a)
                for a in aliases
            ):
                QMessageBox.warning(self, "Alias", "Elige el evento command y escribe hasta 20 alias de una palabra.")
                return
            filters["command_aliases"] = aliases
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
                            "platform": self.platform.currentData(), "event_type": event_type,
                            "action_id": self.action.currentData(), "cooldown_s": self.cooldown.value(),
                            "user_cooldown_s": self.user_cooldown.value(), "filters": filters,
                            "chat_permission": permission}
        super().accept()


class StepForm(Form):
    def __init__(self, parent, data, actions=(), current_id=None):
        super().__init__(parent, "Editar paso")
        self.original = data
        self.action_choices = [(a.name, a.id) for a in actions if a.id != current_id]
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
                widget = combo([(o.name, o.id) for o in list_overlays().values()
                                if o.id not in {"event-feed", "live-goal", "multi-chat", *NOW_PLAYING_IDS}], value)
                row = widget
            elif mode in {"action", "optional_action"}:
                options = [("Elige una acción" if mode == "action" else "No hacer nada", "")]
                widget = combo(options + self.action_choices, value)
                row = widget
            elif mode == "operator":
                widget = combo([(title, code) for code, title in OPERATORS.items()], value)
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
        hints = {
            "set_variable": "Este ejemplo se usa como {local_saludo}. Cada ejecución tiene sus propios valores.",
            "run_action": "Sus pasos se ejecutan aquí y comparten las variables locales; no se agrega otra ejecución a la cola.",
            "condition": "Por ejemplo, count mayor o igual a 3. Puedes comparar con otra variable usando {local_nombre}.",
        }
        if kind in hints:
            hint = QLabel(hints[kind])
            hint.setWordWrap(True)
            self.dynamic.addRow(hint)
        if kind == "condition":
            operator = self.fields["operator"][1]
            value_field = self.fields["value"][1]
            def sync_compare():
                value_field.setEnabled(operator.currentData() not in VALUELESS_OPERATORS)
            operator.currentIndexChanged.connect(sync_compare)
            sync_compare()

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
            value = field.isChecked() if mode == "bool" else (
                field.currentData() if mode in {"overlay", "action", "optional_action", "operator"} else field.text().strip()
            )
            if mode in {"required", "file", "number", "db", "overlay", "action"} and not value:
                QMessageBox.warning(self, "Paso incompleto", f"Completa el campo «{key}».")
                return
            if mode in {"number", "db"}:
                low, high, unit = (-100, 0, "dB") if mode == "db" else (0, 3600, "segundos")
                try:
                    value = float(value)
                    if not low <= value <= high:
                        raise ValueError()
                except (TypeError, ValueError):
                    QMessageBox.warning(self, "Valor", f"Escribe de {low} a {high} {unit}.")
                    return
            data[key] = value
        try:
            validate_steps([data])
        except ValueError as error:
            QMessageBox.warning(self, "Configuración", str(error))
            return
        self.result_data = data
        super().accept()


class ActionForm(Form):
    def __init__(self, parent, data, actions=()):
        super().__init__(parent, "Editar acción")
        self.original = data
        self.actions = actions
        self.name = QLineEdit(data.get("name", ""))
        self.form.addRow("Nombre", self.name)
        self.queue = QLineEdit(data.get("queue", ""))
        self.queue.setMaxLength(40)
        self.queue.setPlaceholderText("Vacía: en paralelo")
        self.form.addRow("Cola", self.queue)
        hint = QLabel("Las acciones con el mismo nombre de cola se ejecutan una por una, en orden.")
        hint.setWordWrap(True)
        self.form.addRow(hint)
        self.steps = [dict(s) for s in data.get("steps", [])]
        self.list = QListWidget()
        self.outer.addWidget(self.list)
        self.list.itemDoubleClicked.connect(lambda _item: self.edit())
        buttons(self.outer, [("Agregar paso", lambda: self.edit(True)), ("Editar", lambda: self.edit()), ("Quitar", self.remove)])
        delete_shortcut(self.list, self.remove)
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
        form = StepForm(self, self.steps[i] if i >= 0 else {}, self.actions, self.original.get("id"))
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
        self.result_data = {**self.original, "name": self.name.text(), "steps": self.steps,
                            "queue": self.queue.text()}
        super().accept()


class RulesPanel(QWidget):
    completed = Signal(str)

    def __init__(self, rt, kind, changed):
        super().__init__()
        self.rt, self.kind, self.changed = rt, kind, changed
        layout = QVBoxLayout(self)
        hint = QLabel(
            "Un disparador define cuándo ejecutar una acción. Aquí ves todos; desde Acciones ves solo los de la acción seleccionada."
            if kind == "trigger" else "Los pasos se ejecutan en orden. Puedes usar variables como {user}, {text} y {gift_name}.")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Buscar por nombre, plataforma, evento o acción")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.refresh)
        layout.addWidget(self.search)
        self.list = QListWidget()
        layout.addWidget(self.list)
        self.list.itemDoubleClicked.connect(lambda _item: self.edit())
        delete_shortcut(self.list, self.delete)
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

    def refresh(self, *_):
        previous = self.selected() if hasattr(self, "items") else None
        candidates = self.rt.config.triggers if self.kind == "trigger" else self.rt.config.actions
        names = {item.id: item.name for item in self.rt.config.actions}
        query = self.search.text().strip().casefold()
        labels = []
        self.items = []
        for item in candidates:
            if self.kind == "trigger":
                title = (f"{item.name} · {PLATFORMS.get(item.platform, item.platform)} / "
                         f"{event_label(item.event_type)} → {names.get(item.action_id, 'Acción no encontrada')}")
                if not item.enabled:
                    title += " · Desactivado"
                searchable = title + " " + item.event_type
            else:
                searchable = title = f"{item.name} · {len(item.steps)} paso(s)"
            if query in searchable.casefold():
                self.items.append(item)
                labels.append(title)
        self.list.clear()
        self.list.addItems(labels)
        selected = next((i for i, item in enumerate(self.items) if previous and item.id == previous.id), 0)
        self.list.setCurrentRow(selected if self.items else -1)

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
        form = TriggerForm(self, data, self.rt.config.actions) if self.kind == "trigger" else ActionForm(self, data, self.rt.config.actions)
        if form.exec():
            self.send(self.rt.edit_rule(self.kind, form.result_data))

    def delete(self):
        item = self.selected()
        if not item:
            return
        data = (confirm_action_deletion(self, self.rt.config, item) if self.kind == "action" else
                {"id": item.id} if confirm_delete(self, "Eliminar disparador", f"¿Eliminar «{item.name}»?") else None)
        if data:
            self.send(self.rt.edit_rule(self.kind, data, delete=True))

    def test_action(self):
        action = self.selected()
        if action and QMessageBox.question(self, "Ejecutar acción",
                "Se ejecutarán sus pasos reales, incluidos cambios de OBS o audio. ¿Continuar?") == QMessageBox.Yes:
            self.send(self.rt.schedule_action_test(Action.from_dict(action.to_dict()), sample_event("gift")))


class ActionWorkspace(QWidget):
    """One action on the left; its triggers and ordered steps on the right."""

    completed = Signal(str, str)

    def __init__(self, rt, changed):
        super().__init__()
        self.rt, self.changed = rt, changed
        self.actions = []
        self.triggers = []
        self.action = None
        self._selected_id = None
        self._trigger_selection = 0
        self._step_selection = 0
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)

        panes = QSplitter(Qt.Orientation.Horizontal)
        panes.setChildrenCollapsible(False)
        panes.setObjectName("workspace-split")
        outer.addWidget(panes, 1)

        action_panel, action_layout, self.action_count = self._panel("Acciones")
        self.filter = QLineEdit()
        self.filter.setObjectName("action-search")
        self.filter.setPlaceholderText("Buscar acciones")
        self.filter.setClearButtonEnabled(True)
        self.filter.textChanged.connect(lambda _text: self.refresh())
        action_layout.addWidget(self.filter)
        self.action_table = self._table(("Nombre", "Cola"), "workbench-actions")
        self.action_table.itemSelectionChanged.connect(self._action_changed)
        self.action_table.cellDoubleClicked.connect(lambda *_: self.edit_action())
        action_layout.addWidget(self.action_table, 1)
        action_toolbar = [("+ Acción", lambda: self.edit_action(True)),
                          ("Editar", self.edit_action), ("Eliminar", self.delete_action)]
        self.action_tools = self._toolbar(action_layout, self.action_table, action_toolbar)
        self.import_button = QPushButton("Importar…")
        self.export_button = QPushButton("Exportar…")
        io_row = QHBoxLayout()
        io_row.addWidget(self.import_button)
        io_row.addWidget(self.export_button)
        action_layout.addLayout(io_row)
        self.import_button.clicked.connect(self._import_actions)
        self.export_button.clicked.connect(self._export_action)
        delete_shortcut(self.action_table, self.delete_action)
        if not rt.editor_only:
            self.test_button = QPushButton("Ejecutar con regalo de prueba")
            self.test_button.clicked.connect(self.test_action)
            action_layout.addWidget(self.test_button)
        panes.addWidget(action_panel)

        right = QSplitter(Qt.Orientation.Vertical)
        right.setChildrenCollapsible(False)
        panes.addWidget(right)
        trigger_panel, trigger_layout, self.trigger_count = self._panel("Disparadores")
        self.trigger_table = self._table(("Nombre", "Plataforma", "Evento", "Estado"), "workbench-triggers")
        self.trigger_table.cellDoubleClicked.connect(lambda *_: self.edit_trigger())
        self.trigger_table.itemSelectionChanged.connect(self._update_tools)
        trigger_layout.addWidget(self.trigger_table, 1)
        self.trigger_tools = self._toolbar(trigger_layout, self.trigger_table,
            [("+ Disparador", lambda: self.edit_trigger(True)),
             ("Editar", self.edit_trigger), ("Eliminar", self.delete_trigger)])
        delete_shortcut(self.trigger_table, self.delete_trigger)
        right.addWidget(trigger_panel)

        step_panel, step_layout, self.step_count = self._panel("Subacciones")
        self.step_table = self._table(("Tipo", "Configuración"), "workbench-steps", stretch=1)
        self.step_table.cellDoubleClicked.connect(lambda *_: self.edit_step())
        self.step_table.itemSelectionChanged.connect(self._update_tools)
        step_layout.addWidget(self.step_table, 1)
        self.step_tools = self._toolbar(step_layout, self.step_table,
            [("+ Subacción", lambda: self.edit_step(True)), ("Editar", self.edit_step),
             ("Eliminar", self.delete_step), ("Subir", lambda: self.move_step(-1)),
             ("Bajar", lambda: self.move_step(1))])
        delete_shortcut(self.step_table, self.delete_step)
        for button, arrow in zip(self.step_tools[-2:], ("↑", "↓")):
            label = button.text()
            button.setAccessibleName(label)
            button.setToolTip(label + " un lugar")
            button.setText(arrow)
            button.setFixedWidth(30)
        right.addWidget(step_panel)
        right.setSizes([280, 340])
        panes.setSizes([280, 620])
        panes.setStretchFactor(0, 0)
        panes.setStretchFactor(1, 1)

        self.notice = QLabel()
        self.notice.setTextFormat(Qt.TextFormat.PlainText)
        self.notice.setWordWrap(True)
        self.notice.setObjectName("workbench-notice")
        self.notice.setText("Selecciona una acción para ver cuándo se activa y qué pasos ejecuta.")
        outer.addWidget(self.notice)
        self.completed.connect(self._complete)
        self.changed.connect(self.refresh)
        self.refresh()

    @staticmethod
    def _panel(title):
        panel = QFrame()
        panel.setObjectName("workbench-pane")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)
        header = QHBoxLayout()
        heading = QLabel(title)
        heading.setObjectName("workbench-pane-title")
        count = QLabel("0")
        count.setObjectName("workbench-count")
        header.addWidget(heading)
        header.addStretch(1)
        header.addWidget(count)
        layout.addLayout(header)
        return panel, layout, count

    @staticmethod
    def _table(headers, name, stretch=0):
        table = QTableWidget(0, len(headers))
        table.setObjectName(name)
        table.setHorizontalHeaderLabels(headers)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setAlternatingRowColors(True)
        table.setShowGrid(False)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(29)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(stretch, QHeaderView.ResizeMode.Stretch)
        return table

    @staticmethod
    def _toolbar(layout, table, commands):
        row = QHBoxLayout()
        row.setSpacing(5)
        tools = []
        for label, callback in commands:
            button = QPushButton(label)
            button.clicked.connect(lambda _checked=False, fn=callback: fn())
            if not tools:
                button.setProperty("role", "primary")
            tools.append(button)
            row.addWidget(button)
        row.addStretch(1)
        layout.addLayout(row)
        table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

        def menu_at(point):
            if table.itemAt(point) is not None:
                table.selectRow(table.itemAt(point).row())
            menu = QMenu(table)
            for button, (text, handler) in zip(tools, commands):
                action = menu.addAction(text)
                action.setEnabled(button.isEnabled())
                action.triggered.connect(lambda _checked=False, fn=handler: fn())
            menu.exec(table.viewport().mapToGlobal(point))

        table.customContextMenuRequested.connect(menu_at)
        return tools

    @staticmethod
    def _fill(table, rows, selected=-1, *, tooltips=True):
        table.blockSignals(True)
        table.clearContents()
        table.setRowCount(len(rows))
        for r, values in enumerate(rows):
            for c, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if tooltips:
                    item.setToolTip(str(value))
                table.setItem(r, c, item)
        if rows and 0 <= selected < len(rows):
            table.selectRow(selected)
        else:
            table.clearSelection()
        table.blockSignals(False)

    def refresh(self, _kind=None):
        selected = self._selected_id
        values = self.rt.config.actions
        query = self.filter.text().strip().casefold()
        self.actions = [a for a in values if not query or query in a.name.casefold()]
        found = next((i for i, a in enumerate(self.actions) if a.id == selected), None)
        row = found if found is not None else (0 if self.actions else -1)
        self._fill(self.action_table, [(a.name, a.queue or "Paralela") for a in self.actions], row)
        self.action_count.setText(f"{len(self.actions)} / {len(values)}" if query else str(len(values)))
        self._action_changed()

    def _action_changed(self):
        index = self.action_table.currentRow() if self.action_table.selectedItems() else -1
        self.action = self.actions[index] if 0 <= index < len(self.actions) else None
        action_id = self.action.id if self.action else None
        if action_id and action_id != self._selected_id:
            self._trigger_selection = self._step_selection = 0
        if action_id:
            self._selected_id = action_id
        self.triggers = [t for t in self.rt.config.triggers if t.action_id == action_id] if self.action else []
        steps = self.action.steps if self.action else []
        self._fill(self.trigger_table, [(t.name, PLATFORMS.get(t.platform, t.platform),
                                         event_label(t.event_type), "Activo" if t.enabled else "Inactivo")
                                        for t in self.triggers], min(self._trigger_selection, len(self.triggers) - 1))
        names = {item.id: item.name for item in self.rt.config.actions}
        def detail(step):
            return " · ".join(
                names.get(str(value), "Acción no encontrada") if key in {"action_id", "then_id", "else_id"}
                else OPERATORS.get(str(value), str(value)) if key == "operator" else str(value)
                for key, value in step.items() if key not in {"type", "id"} and value != ""
            )
        self._fill(self.step_table, [(STEP_FIELDS.get(str(s.get("type")), (s.get("type", "Desconocida"),))[0],
                                     detail(s)) for s in steps], min(self._step_selection, len(steps) - 1))
        self.trigger_count.setText(str(len(self.triggers)))
        self.step_count.setText(str(len(steps)))
        self._update_tools()

    def _update_tools(self):
        has_action = self.action is not None
        has_trigger = bool(self.trigger_table.selectedItems())
        row = self.step_table.currentRow() if self.step_table.selectedItems() else -1
        for button, state in zip(self.action_tools, (True, has_action, has_action)):
            button.setEnabled(state)
        for button, state in zip(self.trigger_tools, (has_action, has_trigger, has_trigger)):
            button.setEnabled(state)
        for button, state in zip(self.step_tools, (has_action, row >= 0, row >= 0, row > 0,
                                                   0 <= row < self.step_table.rowCount() - 1)):
            button.setEnabled(state)
        self.export_button.setEnabled(has_action)
        if hasattr(self, "test_button"):
            self.test_button.setEnabled(has_action)

    def _export_action(self):
        if not self.action:
            return
        try:
            content = ActionPack.export_selected(self.rt.config, self.action.id)
            path, _ = QFileDialog.getSaveFileName(self, "Exportar acción y referencias", "acciones.slbactions",
                                                      "Paquete de acciones (*.slbactions)")
            if not path:
                return
            Path(path).write_bytes(content)
        except (ValueError, OSError) as exc:
            self.notice.setText(str(exc))
        else:
            self.notice.setText("Paquete guardado. Revisa los textos y nombres antes de compartirlo.")

    def _import_actions(self):
        path, _ = QFileDialog.getOpenFileName(self, "Importar paquete de acciones", "",
                                             "Paquete de acciones (*.slbactions)")
        if not path:
            return
        try:
            pack = ActionPack.read(Path(path))
        except (ValueError, OSError) as exc:
            self.notice.setText(str(exc))
            return
        names = ", ".join(action.name for action in pack.actions[:5])
        if len(pack.actions) > 5:
            names += f" y {len(pack.actions) - 5} más"
        dialog = QMessageBox(self)
        dialog.setWindowTitle("Revisar paquete de acciones")
        dialog.setTextFormat(Qt.TextFormat.PlainText)
        dialog.setText(f"Acciones ({len(pack.actions)}): {names}\nDisparadores ({len(pack.triggers)}): "
                       "se importan desactivados.\nNo se reemplaza ni ejecuta nada. Revísalos antes de activarlos.")
        dialog.setStandardButtons(QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel)
        dialog.setDefaultButton(QMessageBox.StandardButton.Cancel)
        if dialog.exec() != QMessageBox.StandardButton.Ok:
            return
        self.filter.clear()

        async def import_to_profile():
            pack.install(self.rt.config)

        self._send(import_to_profile(), "action")

    def _send(self, coro, kind):
        self.setEnabled(False)
        self.notice.setText("Guardando cambios…" if kind else "Programando la prueba…")
        signal = self.completed

        def on_done(result):
            error = "Se canceló la operación." if result.cancelled() else str(result.exception() or "")
            signal.emit(kind, error)

        self.rt.submit(coro).add_done_callback(on_done)

    def _complete(self, kind, error):
        self.setEnabled(True)
        self.notice.setText(error or ("Cambios guardados." if kind else "Prueba programada. Abre Historial para ver su estado o cancelarla."))
        if not error and kind:
            self.changed.emit(kind)

    def edit_action(self, new=False):
        if not new and not self.action:
            return
        data = {"id": uuid4().hex} if new else self.action.to_dict()
        dialog = ActionForm(self, data, self.rt.config.actions)
        if not dialog.exec():
            return
        if new:
            self.filter.clear()
        self._selected_id = data["id"]
        self._send(self.rt.edit_rule("action", dialog.result_data), "action")

    def delete_action(self):
        if self.action:
            data = confirm_action_deletion(self, self.rt.config, self.action)
            if data:
                self._send(self.rt.edit_rule("action", data, delete=True), "action")

    def edit_trigger(self, new=False):
        if not self.action:
            return
        row = self.trigger_table.currentRow()
        if not new and (not self.trigger_table.selectedItems() or row >= len(self.triggers)):
            return
        data = {"action_id": self.action.id} if new else self.triggers[row].to_dict()
        dialog = TriggerForm(self, data, [self.action], fixed_action=True)
        if dialog.exec():
            self._trigger_selection = len(self.triggers) if new else row
            self._send(self.rt.edit_rule("trigger", dialog.result_data), "trigger")

    def delete_trigger(self):
        row = self.trigger_table.currentRow()
        if self.trigger_table.selectedItems() and 0 <= row < len(self.triggers):
            item = self.triggers[row]
            if confirm_delete(self, "Eliminar disparador", f"¿Eliminar el disparador «{item.name}»?"):
                self._trigger_selection = row
                self._send(self.rt.edit_rule("trigger", {"id": item.id}, delete=True), "trigger")

    def edit_step(self, new=False):
        if not self.action:
            return
        steps = list(self.action.steps)
        row = len(steps) if new else self.step_table.currentRow()
        if not new and (not self.step_table.selectedItems() or row >= len(steps)):
            return
        dialog = StepForm(self, {} if new else steps[row], self.rt.config.actions, self.action.id)
        if dialog.exec():
            if new:
                steps.append(dialog.result_data)
            else:
                steps[row] = dialog.result_data
            self._save_steps(steps, row)

    def delete_step(self):
        row = self.step_table.currentRow()
        if self.action and self.step_table.selectedItems() and 0 <= row < len(self.action.steps):
            message = "¿Eliminar esta subacción?"
            if len(self.action.steps) == 1:
                message += "\n\nLa acción quedará vacía y no ejecutará nada hasta que agregues otra subacción."
            if confirm_delete(self, "Eliminar subacción", message):
                steps = list(self.action.steps)
                steps.pop(row)
                self._save_steps(steps, row)

    def move_step(self, delta):
        row = self.step_table.currentRow()
        if self.action and self.step_table.selectedItems() and 0 <= row + delta < len(self.action.steps):
            steps = list(self.action.steps)
            steps[row], steps[row + delta] = steps[row + delta], steps[row]
            self._save_steps(steps, row + delta)

    def _save_steps(self, steps, row):
        self._step_selection = row
        self._send(self.rt.edit_rule("action", {**self.action.to_dict(), "steps": steps}), "action")

    def _confirm(self, message):
        return QMessageBox.question(self, "Confirmar", message) == QMessageBox.StandardButton.Yes

    def test_action(self):
        if self.action and self._confirm("Esto ejecutará los pasos reales de la acción con un regalo simulado, "
                                         "incluidos cambios de OBS o audio. ¿Continuar?"):
            self._send(self.rt.schedule_action_test(Action.from_dict(self.action.to_dict()), sample_event("gift")), "")
