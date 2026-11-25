"""Ventana principal (PySide6)."""
from __future__ import annotations

import functools
import json
from pathlib import Path
from urllib.parse import urlencode

from PySide6.QtCore import QObject, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QGuiApplication, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..connectors.simulator import SAMPLE_KINDS, sample_event
from ..overlay_manager import OverlayInfo, import_overlay, list_overlays
from ..runtime import Runtime

SAMPLE_LABELS = {
    "gift": "Regalo (TikTok)",
    "follow": "Seguidor (Twitch)",
    "donation": "Donación",
    "chat": "Mensaje de chat",
}


class LogBridge(QObject):
    """Puente seguro entre hilos: el runtime emite, la interfaz recibe."""

    message = Signal(str)


# --------------------------------------------------------------------------
# Pestaña Inicio
# --------------------------------------------------------------------------

class HomeTab(QWidget):
    def __init__(self, runtime: Runtime) -> None:
        super().__init__()
        self.rt = runtime
        layout = QVBoxLayout(self)

        self.server_label = QLabel()
        self.server_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.server_label)

        layout.addWidget(QLabel("<b>Conexiones</b>"))
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Conexión", "Estado"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table)

        obs_row = QHBoxLayout()
        connect_obs = QPushButton("Conectar OBS")
        connect_obs.clicked.connect(lambda: self.rt.submit(self.rt.obs.start()))
        disconnect_obs = QPushButton("Desconectar OBS")
        disconnect_obs.clicked.connect(lambda: self.rt.submit(self.rt.obs.stop()))
        obs_row.addWidget(connect_obs)
        obs_row.addWidget(disconnect_obs)
        obs_row.addStretch(1)
        layout.addLayout(obs_row)

        layout.addWidget(QLabel("<b>Enviar un evento de prueba</b> (pasa por los triggers y los overlays)"))
        tests = QHBoxLayout()
        for kind in SAMPLE_KINDS:
            button = QPushButton(SAMPLE_LABELS[kind])
            button.clicked.connect(functools.partial(self._send_sample, kind))
            tests.addWidget(button)
        tests.addStretch(1)
        layout.addLayout(tests)
        layout.addStretch(1)

        self.refresh()
        timer = QTimer(self)
        timer.timeout.connect(self.refresh)
        timer.start(1000)

    def _send_sample(self, kind: str) -> None:
        self.rt.emit(sample_event(kind))

    def refresh(self) -> None:
        self.server_label.setText(f"Servidor de overlays: http://127.0.0.1:{self.rt.port}/")
        connectors = list(self.rt.connectors.values())
        if self.table.rowCount() != len(connectors):
            self.table.setRowCount(len(connectors))
        for row, connector in enumerate(connectors):
            self.table.setItem(row, 0, QTableWidgetItem(connector.name))
            self.table.setItem(row, 1, QTableWidgetItem(connector.status))


# --------------------------------------------------------------------------
# Pestañas Triggers y Acciones (solo lectura por ahora)
# --------------------------------------------------------------------------

class TriggersTab(QWidget):
    def __init__(self, runtime: Runtime) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Triggers configurados (el editor visual llegará en una fase posterior; "
                                "por ahora se editan en config.json)."))
        table = QTableWidget(0, 7)
        table.setHorizontalHeaderLabels(["Nombre", "Plataforma", "Evento", "Filtros", "Cooldown (s)", "Acción", "Activo"])
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.verticalHeader().setVisible(False)
        triggers = runtime.config.triggers
        table.setRowCount(len(triggers))
        for row, t in enumerate(triggers):
            values = [t.name, t.platform, t.event_type, json.dumps(t.filters, ensure_ascii=False),
                      str(t.cooldown_s), t.action_id, "sí" if t.enabled else "no"]
            for col, value in enumerate(values):
                table.setItem(row, col, QTableWidgetItem(value))
        layout.addWidget(table)


class ActionsTab(QWidget):
    def __init__(self, runtime: Runtime) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Acciones configuradas y sus pasos."))
        tree = QTreeWidget()
        tree.setHeaderLabels(["Acción / paso", "Detalle"])
        tree.header().setSectionResizeMode(QHeaderView.ResizeToContents)
        for action in runtime.config.actions:
            parent = QTreeWidgetItem([f"{action.name}  ({action.id})", ""])
            tree.addTopLevelItem(parent)
            for i, step in enumerate(action.steps, start=1):
                detail = ", ".join(f"{k}={v}" for k, v in step.items() if k != "type")
                parent.addChild(QTreeWidgetItem([f"{i}. {step.get('type', '?')}", detail]))
            parent.setExpanded(True)
        layout.addWidget(tree)


# --------------------------------------------------------------------------
# Pestaña Overlays
# --------------------------------------------------------------------------

class _ColorButton(QPushButton):
    changed = Signal(str)

    def __init__(self, value: str) -> None:
        super().__init__()
        self._value = value
        self._paint()
        self.clicked.connect(self._pick)

    def _paint(self) -> None:
        self.setText(self._value)
        self.setStyleSheet(f"background-color: {self._value}; padding: 4px 12px;")

    def _pick(self) -> None:
        color = QColorDialog.getColor(QColor(self._value), self)
        if color.isValid():
            self._value = color.name()
            self._paint()
            self.changed.emit(self._value)


class OverlaysTab(QWidget):
    def __init__(self, runtime: Runtime) -> None:
        super().__init__()
        self.rt = runtime
        self._info: OverlayInfo | None = None
        self._values: dict[str, str] = {}
        self._defaults: dict[str, str] = {}

        root = QHBoxLayout(self)
        left = QVBoxLayout()
        self.list = QListWidget()
        self.list.setMaximumWidth(260)
        self.list.currentItemChanged.connect(self._on_select)
        left.addWidget(self.list)
        import_zip = QPushButton("Importar .zip…")
        import_zip.clicked.connect(self._import_zip)
        import_dir = QPushButton("Importar carpeta…")
        import_dir.clicked.connect(self._import_dir)
        left.addWidget(import_zip)
        left.addWidget(import_dir)
        root.addLayout(left)

        right = QVBoxLayout()
        self.title = QLabel()
        self.title.setStyleSheet("font-size: 16px; font-weight: bold;")
        self.desc = QLabel()
        self.desc.setWordWrap(True)
        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumHeight(120)
        self.form_host = QWidget()
        self.form = QFormLayout(self.form_host)
        self.url = QLineEdit()
        self.url.setReadOnly(True)
        buttons = QHBoxLayout()
        copy_btn = QPushButton("Copiar URL para OBS")
        copy_btn.clicked.connect(self._copy_url)
        open_btn = QPushButton("Abrir en el navegador")
        open_btn.clicked.connect(self._open_url)
        buttons.addWidget(copy_btn)
        buttons.addWidget(open_btn)
        buttons.addStretch(1)
        hint = QLabel("En OBS: Fuentes → + → Navegador → pega la URL. "
                      "Usa los botones de prueba de la pestaña Inicio para verlo funcionar.")
        hint.setWordWrap(True)

        right.addWidget(self.title)
        right.addWidget(self.desc)
        right.addWidget(self.preview)
        right.addWidget(self.form_host)
        right.addWidget(QLabel("URL del overlay:"))
        right.addWidget(self.url)
        right.addLayout(buttons)
        right.addWidget(hint)
        right.addStretch(1)
        root.addLayout(right, 1)

        self.refresh()

    # -- lista -------------------------------------------------------------

    def refresh(self, select_id: str | None = None) -> None:
        overlays = list_overlays()
        self.list.blockSignals(True)
        self.list.clear()
        for info in overlays.values():
            tag = "" if info.source == "builtin" else "  [propio]"
            item = QListWidgetItem(info.name + tag)
            item.setData(Qt.UserRole, info.id)
            self.list.addItem(item)
        self.list.blockSignals(False)
        if self.list.count():
            row = 0
            if select_id:
                for i in range(self.list.count()):
                    if self.list.item(i).data(Qt.UserRole) == select_id:
                        row = i
            self.list.setCurrentRow(row)
            self._show(overlays[self.list.item(row).data(Qt.UserRole)])

    def _on_select(self, current: QListWidgetItem | None, _previous) -> None:
        if current is None:
            return
        info = list_overlays().get(current.data(Qt.UserRole))
        if info:
            self._show(info)

    # -- detalle y formulario ------------------------------------------------

    def _show(self, info: OverlayInfo) -> None:
        self._info = info
        self.title.setText(info.name)
        self.desc.setText(info.description)
        preview = info.preview_path
        if preview:
            self.preview.setPixmap(QPixmap(str(preview)).scaledToHeight(160, Qt.SmoothTransformation))
        else:
            self.preview.setPixmap(QPixmap())
            self.preview.setText("(sin vista previa)")
        self._build_form(info)
        self._update_url()

    def _build_form(self, info: OverlayInfo) -> None:
        while self.form.rowCount():
            self.form.removeRow(0)
        self._values.clear()
        self._defaults.clear()
        for p in info.params:
            key = p["key"]
            default = p.get("default", "")
            self._defaults[key] = self._to_text(default)
            self._values[key] = self._defaults[key]
            widget = self._make_widget(p, default)
            self.form.addRow(p.get("label", key), widget)

    @staticmethod
    def _to_text(value) -> str:
        if isinstance(value, bool):
            return "true" if value else "false"
        return str(value)

    def _set_value(self, key: str, value) -> None:
        self._values[key] = self._to_text(value)
        self._update_url()

    def _make_widget(self, p: dict, default) -> QWidget:
        key, kind = p["key"], p["type"]
        setter = functools.partial(self._set_value, key)
        if kind == "number":
            lo, hi = p.get("min", 0), p.get("max", 9999)
            if isinstance(default, int) and isinstance(lo, int) and isinstance(hi, int):
                w = QSpinBox()
                w.setRange(lo, hi)
                w.setValue(default)
            else:
                w = QDoubleSpinBox()
                w.setRange(float(lo), float(hi))
                w.setValue(float(default or 0))
            w.valueChanged.connect(setter)
            return w
        if kind == "bool":
            w = QCheckBox()
            w.setChecked(bool(default))
            w.toggled.connect(setter)
            return w
        if kind == "color":
            w = _ColorButton(str(default) or "#ffffff")
            w.changed.connect(setter)
            return w
        if kind == "select":
            w = QComboBox()
            w.addItems([str(o) for o in p.get("options", [])])
            w.setCurrentText(str(default))
            w.currentTextChanged.connect(setter)
            return w
        w = QLineEdit(str(default))
        w.textChanged.connect(setter)
        return w

    def _update_url(self) -> None:
        if self._info is None:
            return
        changed = {k: v for k, v in self._values.items() if v != self._defaults.get(k)}
        url = f"http://127.0.0.1:{self.rt.port}/overlay/{self._info.id}/"
        if changed:
            url += "?" + urlencode(changed)
        self.url.setText(url)

    def _copy_url(self) -> None:
        QGuiApplication.clipboard().setText(self.url.text())

    def _open_url(self) -> None:
        QDesktopServices.openUrl(QUrl(self.url.text()))

    # -- importar ------------------------------------------------------------

    def _import_zip(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Importar overlay", "", "Overlay (*.zip)")
        if path:
            self._do_import(Path(path))

    def _import_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Importar overlay (carpeta)")
        if path:
            self._do_import(Path(path))

    def _do_import(self, source: Path) -> None:
        warning = QMessageBox.question(
            self,
            "Importar overlay",
            "Un overlay contiene JavaScript que se ejecuta dentro de OBS en tu equipo.\n"
            "Importa solo overlays de gente en la que confíes.\n\n¿Continuar?",
        )
        if warning != QMessageBox.Yes:
            return
        try:
            info = import_overlay(source)
        except FileExistsError:
            if QMessageBox.question(self, "Importar overlay", "Ya existe un overlay con ese id. ¿Reemplazarlo?") != QMessageBox.Yes:
                return
            try:
                info = import_overlay(source, overwrite=True)
            except (ValueError, OSError) as exc:
                QMessageBox.critical(self, "Importar overlay", str(exc))
                return
        except (ValueError, OSError) as exc:
            QMessageBox.critical(self, "Importar overlay", str(exc))
            return
        self.rt.log(f"Overlay importado: {info.name} ({info.id})")
        self.refresh(select_id=info.id)


# --------------------------------------------------------------------------
# Ventana principal
# --------------------------------------------------------------------------

class MainWindow(QMainWindow):
    def __init__(self, runtime: Runtime, bridge: LogBridge) -> None:
        super().__init__()
        self.rt = runtime
        self.setWindowTitle("Streamer Linux Bot")
        self.resize(960, 640)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(2000)
        for line in runtime.log_history:
            self.log_view.appendPlainText(line)
        bridge.message.connect(self.log_view.appendPlainText)

        tabs = QTabWidget()
        tabs.addTab(HomeTab(runtime), "Inicio")
        tabs.addTab(TriggersTab(runtime), "Triggers")
        tabs.addTab(ActionsTab(runtime), "Acciones")
        tabs.addTab(OverlaysTab(runtime), "Overlays")
        tabs.addTab(self.log_view, "Registro")
        self.setCentralWidget(tabs)
