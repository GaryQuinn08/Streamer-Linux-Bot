"""Ventana principal (PySide6)."""
from __future__ import annotations

import functools
import json
import re
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QGuiApplication, QIntValidator, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
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
    QScrollArea,
    QGroupBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..connectors.simulator import SAMPLE_KINDS, sample_event
from ..overlay_manager import OverlayInfo, create_alert, import_overlay, list_overlays, validate_overlay_values
from ..runtime import Runtime
from .rule_editor import RulesPanel

SAMPLE_LABELS = {
    "gift": "Regalo (TikTok)",
    "follow": "Seguidor (Twitch)",
    "donation": "Donación",
    "chat": "Mensaje de chat",
}


class LogBridge(QObject):
    """Puente seguro entre hilos: el runtime emite, la interfaz recibe."""

    message = Signal(str)
    gift_save_done = Signal(str)
    overlay_port_done = Signal(str)
    overlay_saved = Signal(str, str)
    overlays_catalog_changed = Signal()
    rules_changed = Signal(str)


# --------------------------------------------------------------------------
# Pestaña Inicio
# --------------------------------------------------------------------------

class HomeTab(QWidget):
    def __init__(self, runtime: Runtime, bridge: LogBridge) -> None:
        super().__init__()
        self.rt = runtime
        self.bridge = bridge
        outer = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        layout = QVBoxLayout(body)
        scroll.setWidget(body)
        outer.addWidget(scroll)

        overlay_group = QGroupBox("Servidor local de overlays")
        overlay_form = QFormLayout(overlay_group)
        self.server_label = QLabel()
        self.server_label.setWordWrap(True)
        self.server_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        overlay_form.addRow(self.server_label)
        port_row = QHBoxLayout()
        self.overlay_port = QLineEdit(str(runtime.port) if runtime.port is not None else "")
        self.overlay_port.setObjectName("overlayPort")
        self.overlay_port.setValidator(QIntValidator(1, 65535, self))
        self.overlay_port.setPlaceholderText("Ejemplo: 8766")
        self.assign_port = QPushButton("Asignar puerto")
        self.assign_port.clicked.connect(self._assign_overlay_port)
        self.overlay_port.returnPressed.connect(self._assign_overlay_port)
        self.open_catalog = QPushButton("Abrir catálogo de alertas")
        self.open_catalog.clicked.connect(self._open_overlay_catalog)
        port_row.addWidget(self.overlay_port)
        port_row.addWidget(self.assign_port)
        port_row.addWidget(self.open_catalog)
        overlay_form.addRow("Puerto de overlays:", port_row)
        self.port_result = QLabel()
        self.port_result.setWordWrap(True)
        overlay_form.addRow(self.port_result)
        self.bridge.overlay_port_done.connect(self._overlay_port_done)
        layout.addWidget(overlay_group)

        layout.addWidget(QLabel("<b>Conexiones</b>"))
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Conexión", "Estado"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table)

        obs_group = QGroupBox("OBS Studio")
        obs_form = QFormLayout(obs_group)
        obs_cfg = runtime.config.settings["obs"]
        self.obs_host = QLineEdit(str(obs_cfg["host"]))
        self.obs_host.setObjectName("obsHost")
        self.obs_port = QSpinBox()
        self.obs_port.setRange(1, 65535)
        try:
            self.obs_port.setValue(int(obs_cfg["port"]))
        except (TypeError, ValueError):
            self.obs_port.setValue(4455)
        self.obs_password = QLineEdit()
        self.obs_password.setObjectName("obsPassword")
        self.obs_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.obs_password.setPlaceholderText("Solo para esta sesión; no se guarda")
        obs_form.addRow("Dirección:", self.obs_host)
        obs_form.addRow("Puerto:", self.obs_port)
        obs_form.addRow("Contraseña:", self.obs_password)

        row = QHBoxLayout()
        self.connect_obs = QPushButton("Conectar OBS")
        self.connect_obs.clicked.connect(self._connect_obs)
        self.disconnect_obs = QPushButton("Desconectar OBS")
        self.disconnect_obs.clicked.connect(lambda: self.rt.submit(self.rt.obs.stop()))
        row.addWidget(self.connect_obs)
        row.addWidget(self.disconnect_obs)
        row.addStretch(1)
        obs_form.addRow(row)
        obs_hint = QLabel("En OBS: Herramientas → Ajustes del servidor WebSocket → Activar. "
                          "Una fuente de navegador no necesita esta conexión; "
                          "solo las acciones que controlan escenas o fuentes.")
        obs_hint.setWordWrap(True)
        obs_form.addRow(obs_hint)
        layout.addWidget(obs_group)

        tiktok_group = QGroupBox("TikTok LIVE · experimental")
        tiktok_form = QFormLayout(tiktok_group)
        self.tiktok_mode = QComboBox()
        self.tiktok_mode.addItem("TikTok directo (conector opcional)", "directo")
        self.tiktok_mode.addItem("TikFinity (Event API local)", "tikfinity")
        self.tiktok_channel = QLineEdit()
        self.tiktok_channel.setPlaceholderText("@usuario en directo")
        self.tiktok_mode.currentIndexChanged.connect(
            lambda: self.tiktok_channel.setEnabled(self.tiktok_mode.currentData() == "directo")
        )
        tiktok_form.addRow("Conector:", self.tiktok_mode)
        tiktok_form.addRow("Usuario:", self.tiktok_channel)
        tiktok_row = QHBoxLayout()
        connect_tiktok = QPushButton("Conectar TikTok")
        connect_tiktok.clicked.connect(self._connect_tiktok)
        disconnect_tiktok = QPushButton("Desconectar TikTok")
        disconnect_tiktok.clicked.connect(lambda: self.rt.submit(self.rt.connectors["tiktok"].stop()))
        tiktok_row.addWidget(connect_tiktok)
        tiktok_row.addWidget(disconnect_tiktok)
        tiktok_row.addStretch(1)
        tiktok_form.addRow(tiktok_row)
        layout.addWidget(tiktok_group)

        receiving = QGroupBox("Twitch / YouTube · experimental")
        receiving_layout = QVBoxLayout(receiving)
        details = QLabel("Configura las credenciales de tu cuenta en la terminal antes de abrir el bot. "
                         "Consulta el README. El bot no guarda tokens ni envía mensajes de chat.")
        details.setWordWrap(True)
        receiving_layout.addWidget(details)
        for platform in ("twitch", "youtube"):
            row = QHBoxLayout()
            connector = self.rt.connectors[platform]
            connect = QPushButton(f"Conectar {platform.title()}")
            disconnect = QPushButton(f"Desconectar {platform.title()}")
            connect.clicked.connect(lambda _checked, c=connector: self.rt.submit(c.start()))
            disconnect.clicked.connect(lambda _checked, c=connector: self.rt.submit(c.stop()))
            row.addWidget(connect)
            row.addWidget(disconnect)
            receiving_layout.addLayout(row)
        layout.addWidget(receiving)

        layout.addWidget(QLabel("<b>Enviar un evento de prueba</b> (pasa por los triggers y los overlays)"))
        tests = QHBoxLayout()
        for kind in SAMPLE_KINDS:
            button = QPushButton(SAMPLE_LABELS[kind])
            button.clicked.connect(functools.partial(self._send_sample, kind))
            tests.addWidget(button)
        tests.addStretch(1)
        layout.addLayout(tests)
        audio = QGroupBox("Música local (mpv)")
        audio_form = QFormLayout(audio)
        self.music_label = QLabel()
        self.music_label.setTextFormat(Qt.PlainText)
        audio_form.addRow(self.music_label)
        music_row = QHBoxLayout()
        add_track = QPushButton("Encolar archivo…")
        add_track.clicked.connect(self._enqueue_track)
        clear_tracks = QPushButton("Detener y vaciar")
        clear_tracks.clicked.connect(lambda: self.rt.submit(self.rt.music.clear()))
        music_row.addWidget(add_track)
        music_row.addWidget(clear_tracks)
        audio_form.addRow(music_row)
        layout.addWidget(audio)
        layout.addStretch(1)

        self.refresh()
        timer = QTimer(self)
        timer.timeout.connect(self.refresh)
        timer.start(1000)

    def _assign_overlay_port(self) -> None:
        if not self.assign_port.isEnabled():
            return
        if not self.overlay_port.hasAcceptableInput():
            self.port_result.setText("Escribe un puerto entre 1 y 65535.")
            return
        self.assign_port.setEnabled(False)
        self.port_result.setText("Comprobando el puerto…")
        future = self.rt.submit(self.rt.change_overlay_port(int(self.overlay_port.text())))
        signal = self.bridge.overlay_port_done

        def done(completed) -> None:
            if not completed.cancelled():
                error = completed.exception()
                signal.emit(str(error) if error else "")

        future.add_done_callback(done)

    def _overlay_port_done(self, error: str) -> None:
        self.assign_port.setEnabled(True)
        if error:
            self.port_result.setText(error)
        else:
            self.port_result.setText("Puerto guardado. Si cambió, vuelve a copiar la URL en el programa de transmisión.")
        self.refresh()

    def _open_overlay_catalog(self) -> None:
        if self.rt.port is not None:
            QDesktopServices.openUrl(QUrl(f"http://127.0.0.1:{self.rt.port}/"))

    def _connect_obs(self) -> None:
        host = self.obs_host.text().strip()
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.-]{0,252}", host):
            QMessageBox.warning(self, "Dirección de OBS", "Escribe una IP IPv4 o un nombre de equipo.")
            return
        password = self.obs_password.text()
        self.obs_password.clear()
        self.connect_obs.setEnabled(False)
        self.rt.submit(self.rt.obs.start(host, self.obs_port.value(), password))

    def _connect_tiktok(self) -> None:
        self.rt.submit(self.rt.connectors["tiktok"].start(
            self.tiktok_mode.currentData(), self.tiktok_channel.text()
        ))

    def _enqueue_track(self) -> None:
        name, _ = QFileDialog.getOpenFileName(self, "Elige música local", str(Path.home()),
            "Audio (*.wav *.mp3 *.ogg *.opus *.flac *.m4a *.aac)")
        if not name:
            return

        async def enqueue():
            try:
                self.rt.music.enqueue(name)
            except (ValueError, RuntimeError) as exc:
                self.rt.log(f"Música: {exc}")

        self.rt.submit(enqueue())

    def _send_sample(self, kind: str) -> None:
        self.rt.emit(sample_event(kind))

    def refresh(self) -> None:
        port = self.rt.port
        self.server_label.setText(f"Servidor de overlays: http://127.0.0.1:{port}/" if port is not None
                                  else self.rt.overlay_port_message or "Asigna un puerto para activar los overlays.")
        self.open_catalog.setEnabled(port is not None)
        self.music_label.setText("En reproducción: " + self.rt.music.current
                                 if self.rt.music.current else "Sin reproducción activa.")
        self.connect_obs.setEnabled(self.rt.obs.status != "conectando…")
        connectors = list(self.rt.connectors.values())
        if self.table.rowCount() != len(connectors):
            self.table.setRowCount(len(connectors))
        for row, connector in enumerate(connectors):
            self.table.setItem(row, 0, QTableWidgetItem(connector.name))
            self.table.setItem(row, 1, QTableWidgetItem(connector.status))


# --------------------------------------------------------------------------
# Regla rápida de regalos
# --------------------------------------------------------------------------

class TriggersTab(QWidget):
    def __init__(self, runtime: Runtime, bridge: LogBridge) -> None:
        super().__init__()
        self.rt = runtime
        self.bridge = bridge
        layout = QVBoxLayout(self)
        editor = QGroupBox("Regla rápida: regalos de TikTok")
        form = QFormLayout(editor)
        trigger = next((t for t in runtime.config.triggers if t.id == "tiktok-gift"), None)
        action = runtime.config.action_by_id(trigger.action_id if trigger else "alert-gift")
        step = next((s for s in action.steps if s.get("type") == "overlay_alert"), {}) if action else {}
        self.enabled_rule = QCheckBox()
        self.enabled_rule.setChecked(trigger.enabled if trigger else True)
        self.gift_name = QLineEdit(str(trigger.filters.get("gift_name", "")) if trigger else "")
        self.gift_name.setPlaceholderText("En blanco: cualquier regalo. Ejemplo: Rose")
        self.cooldown = QSpinBox()
        self.cooldown.setRange(0, 3600)
        self.cooldown.setValue(int(trigger.cooldown_s) if trigger else 0)
        self.title = QLineEdit(str(step.get("title", "{user} envió {gift_name}")))
        self.destination = QComboBox()
        self._refresh_targets(str(step.get("overlay", "gift-alert")))
        bridge.overlays_catalog_changed.connect(self._refresh_targets)
        sound = next((s.get("file", "") for s in action.steps
                      if s.get("id") == "quick-gift-sound"), "") if action else ""
        self.sound = QLineEdit(str(sound))
        self.sound.setPlaceholderText("Opcional. Vacío: sin sonido")
        sound_row = QHBoxLayout()
        sound_row.addWidget(self.sound)
        pick = QPushButton("Elegir…")
        pick.clicked.connect(self._pick_sound)
        sound_row.addWidget(pick)
        form.addRow("Activar:", self.enabled_rule)
        form.addRow("Nombre del regalo:", self.gift_name)
        form.addRow("Espera mínima (s):", self.cooldown)
        form.addRow("Mostrar en:", self.destination)
        form.addRow("Título del overlay:", self.title)
        form.addRow("Archivo de sonido:", sound_row)
        self.save_button = QPushButton("Guardar regla")
        self.save_button.clicked.connect(self._save_rule)
        form.addRow(self.save_button)
        self.result = QLabel("El botón de Inicio simula Rose ×3. Usa «Rose» o deja el filtro vacío para probar.")
        self.result.setWordWrap(True)
        form.addRow(self.result)
        layout.addWidget(editor)
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["Nombre", "Plataforma", "Evento", "Filtros", "Cooldown (s)", "Acción", "Activo"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table)
        self.bridge.gift_save_done.connect(self._saved)
        self.bridge.rules_changed.connect(self._reload_quick_rule)
        self._refresh()

    def _reload_quick_rule(self, kind: str) -> None:
        if kind == "quick":
            self._refresh()
            return
        trigger = next((t for t in self.rt.config.triggers if t.id == "tiktok-gift"), None)
        action = self.rt.config.action_by_id(trigger.action_id) if trigger else None
        step = next((s for s in action.steps if s.get("type") == "overlay_alert"), {}) if action else {}
        sound = next((s.get("file", "") for s in action.steps if s.get("id") == "quick-gift-sound"), "") if action else ""
        self.enabled_rule.setChecked(trigger.enabled if trigger else True)
        self.gift_name.setText(str(trigger.filters.get("gift_name", "")) if trigger else "")
        self.cooldown.setValue(int(trigger.cooldown_s) if trigger else 0)
        self.title.setText(str(step.get("title", "{user} envió {gift_name}")))
        self.sound.setText(str(sound))
        self._refresh_targets(str(step.get("overlay", "gift-alert")))
        self._refresh()


    def _refresh(self) -> None:
        triggers = self.rt.config.triggers
        self.table.setRowCount(len(triggers))
        for row, t in enumerate(triggers):
            values = [t.name, t.platform, t.event_type, json.dumps(t.filters, ensure_ascii=False),
                      str(t.cooldown_s), t.action_id, "sí" if t.enabled else "no"]
            for col, value in enumerate(values):
                self.table.setItem(row, col, QTableWidgetItem(value))

    def _refresh_targets(self, selected: str | None = None) -> None:
        selected = selected or self.destination.currentData()
        self.destination.clear()
        for item in sorted(list_overlays().values(), key=lambda item: item.id != "gift-alert"):
            if item.id != "event-feed":
                self.destination.addItem(item.name, item.id)
        index = self.destination.findData(selected)
        self.destination.setCurrentIndex(max(index, 0))

    def _pick_sound(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Elegir sonido", "", "Audio (*.wav *.ogg *.mp3 *.flac);;Todos (*)")
        if path:
            self.sound.setText(path)

    def _save_rule(self) -> None:
        title, sound = self.title.text().strip(), self.sound.text().strip()
        if not title or (sound and not Path(sound).expanduser().is_file()):
            self.result.setText("Escribe un título y elige un archivo de sonido que exista (u omítelo).")
            return
        self.save_button.setEnabled(False)
        future = self.rt.submit(self.rt.save_gift_rule(
            self.enabled_rule.isChecked(), self.gift_name.text().strip(),
            self.cooldown.value(), title, str(Path(sound).expanduser().resolve()) if sound else "",
            self.destination.currentData(),
        ))
        bridge = self.bridge

        def done(completed) -> None:
            if completed.cancelled():
                return
            error = completed.exception()
            bridge.gift_save_done.emit(str(error) if error else "")

        future.add_done_callback(done)

    def _saved(self, error: str) -> None:
        self.save_button.setEnabled(True)
        self.result.setText(f"No se pudo guardar: {error}" if error else "Regla guardada. Prueba el regalo desde Inicio.")
        if not error:
            self._refresh()


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
    def __init__(self, runtime: Runtime, bridge: LogBridge) -> None:
        super().__init__()
        self.rt = runtime
        self.bridge = bridge
        self._info: OverlayInfo | None = None
        self._values: dict[str, str] = {}
        self._defaults: dict[str, str] = {}

        root = QHBoxLayout(self)
        left = QVBoxLayout()
        self.list = QListWidget()
        self.list.setMaximumWidth(260)
        self.list.currentItemChanged.connect(self._on_select)
        left.addWidget(self.list)
        new_alert = QPushButton("Nueva alerta…")
        new_alert.clicked.connect(self._create_alert)
        left.addWidget(new_alert)
        import_zip = QPushButton("Importar .zip…")
        import_zip.clicked.connect(self._import_zip)
        import_dir = QPushButton("Importar carpeta…")
        import_dir.clicked.connect(self._import_dir)
        left.addWidget(import_zip)
        left.addWidget(import_dir)
        import_html = QPushButton("Importar HTML…")
        import_html.clicked.connect(self._import_html)
        left.addWidget(import_html)
        root.addLayout(left)

        right = QVBoxLayout()
        self.title = QLabel()
        self.title.setTextFormat(Qt.PlainText)
        self.title.setStyleSheet("font-size: 16px; font-weight: bold;")
        self.desc = QLabel()
        self.desc.setTextFormat(Qt.PlainText)
        self.desc.setWordWrap(True)
        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumHeight(120)
        self.form_host = QWidget()
        self.form = QFormLayout(self.form_host)
        self.url = QLineEdit()
        self.url.setReadOnly(True)
        buttons = QHBoxLayout()
        self.copy_btn = QPushButton("Copiar URL para OBS / LIVE Studio")
        self.copy_btn.clicked.connect(self._copy_url)
        self.open_btn = QPushButton("Abrir en el navegador")
        self.open_btn.clicked.connect(self._open_url)
        self.preview_btn = QPushButton("Probar alerta")
        self.preview_btn.clicked.connect(self._preview)
        buttons.addWidget(self.copy_btn)
        buttons.addWidget(self.open_btn)
        buttons.addWidget(self.preview_btn)
        buttons.addStretch(1)

        edits = QHBoxLayout()
        self.save_btn = QPushButton("Guardar apariencia")
        self.save_btn.clicked.connect(self._save_preset)
        self.reset_btn = QPushButton("Restablecer apariencia")
        self.reset_btn.clicked.connect(self._reset_preset)
        edits.addWidget(self.save_btn)
        edits.addWidget(self.reset_btn)
        edits.addStretch(1)
        self.status = QLabel()
        self.status.setWordWrap(True)
        hint = QLabel("Abre la URL en el navegador o como fuente de OBS antes de probar. "
                      "Después de guardar la apariencia, actualiza la fuente para verla.")
        hint.setWordWrap(True)

        right.addWidget(self.title)
        right.addWidget(self.desc)
        right.addWidget(self.preview)
        right.addWidget(self.form_host)
        right.addLayout(edits)
        right.addWidget(self.status)
        right.addWidget(QLabel("URL del overlay:"))
        right.addWidget(self.url)
        right.addLayout(buttons)
        right.addWidget(hint)
        right.addStretch(1)
        root.addLayout(right, 1)

        self.bridge.overlay_saved.connect(self._preset_saved)
        self.bridge.overlay_port_done.connect(lambda _error: self._update_url())
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
        pixmap = QPixmap(str(preview)) if preview else QPixmap()
        if not pixmap.isNull():
            self.preview.setPixmap(pixmap.scaledToHeight(160, Qt.SmoothTransformation))
        else:
            self.preview.setPixmap(QPixmap())
            self.preview.setText("(sin vista previa)")
        self._build_form(info)
        self.status.clear()
        self.save_btn.setEnabled(bool(info.params))
        self.reset_btn.setEnabled(bool(info.params))
        self._update_url()

    def _build_form(self, info: OverlayInfo) -> None:
        while self.form.rowCount():
            self.form.removeRow(0)
        self._values.clear()
        self._defaults.clear()
        presets = self.rt.config.settings.get("overlay_presets", {})
        saved = presets.get(info.id, {}) if isinstance(presets, dict) else {}
        if not isinstance(saved, dict):
            saved = {}
        for p in info.params:
            key = p["key"]
            default = p.get("default", p.get("min", 0) if p["type"] == "number" else "")
            self._defaults[key] = self._to_text(default)
            value = default
            if key in saved:
                try:
                    value = validate_overlay_values(info, {key: saved[key]})[key]
                    if p["type"] == "bool":
                        value = value == "true"
                    elif p["type"] == "number" and isinstance(default, int):
                        value = int(float(value))
                except (TypeError, ValueError):
                    value = default
            self._values[key] = self._to_text(value)
            label = QLabel(str(p.get("label", key)))
            label.setTextFormat(Qt.PlainText)
            self.form.addRow(label, self._make_widget(p, value))

    @staticmethod
    def _to_text(value) -> str:
        if isinstance(value, bool):
            return "true" if value else "false"
        return str(value)

    def _set_value(self, key: str, value) -> None:
        self._values[key] = self._to_text(value)
        self.status.setText("Cambios sin guardar.")

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
            w.setChecked(default is True or str(default).lower() in {"true", "1", "yes"})
            w.toggled.connect(setter)
            return w
        if kind == "color":
            color = str(default)
            w = _ColorButton(color if re.fullmatch(r"#[0-9a-fA-F]{6}", color) else "#ffffff")
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
        port = self.rt.port
        ready = port is not None and self._info is not None
        self.url.setText(f"http://127.0.0.1:{port}/overlay/{self._info.id}/" if ready else "")
        self.url.setPlaceholderText("Asigna un puerto desde Inicio para generar la URL.")
        for button in (self.copy_btn, self.open_btn, self.preview_btn):
            button.setEnabled(ready)

    def _copy_url(self) -> None:
        if self.url.text():
            QGuiApplication.clipboard().setText(self.url.text())

    def _open_url(self) -> None:
        if self.url.text():
            QDesktopServices.openUrl(QUrl(self.url.text()))

    def _preview(self) -> None:
        if self._info and self.rt.port is not None:
            self.rt.submit(self.rt.preview_overlay(self._info.id))
            self.status.setText("Vista de prueba enviada. La página debe estar abierta para verla.")

    def _save_preset(self) -> None:
        changes = {key: value for key, value in self._values.items() if value != self._defaults[key]}
        self._write_preset(changes)

    def _reset_preset(self) -> None:
        self._write_preset({})

    def _write_preset(self, changes: dict[str, str]) -> None:
        if self._info is None:
            return
        overlay_id = self._info.id
        self.save_btn.setEnabled(False)
        self.reset_btn.setEnabled(False)
        future = self.rt.submit(self.rt.save_overlay_preset(overlay_id, changes))
        signal = self.bridge.overlay_saved

        def done(completed) -> None:
            if not completed.cancelled():
                error = completed.exception()
                signal.emit(overlay_id, str(error) if error else "")

        future.add_done_callback(done)

    def _preset_saved(self, overlay_id: str, error: str) -> None:
        if self._info is None or self._info.id != overlay_id:
            return
        self.save_btn.setEnabled(bool(self._info.params))
        self.reset_btn.setEnabled(bool(self._info.params))
        if not error:
            self._build_form(self._info)
        self.status.setText(f"No se guardó: {error}" if error else
                            "Apariencia guardada. Actualiza la fuente de OBS; la URL no cambia.")

    def _create_alert(self) -> None:
        name, accepted = QInputDialog.getText(self, "Nueva alerta", "Nombre de la alerta:")
        if not accepted:
            return
        try:
            info = create_alert(name)
        except (ValueError, OSError) as exc:
            QMessageBox.warning(self, "Nueva alerta", str(exc))
            return
        self.refresh(select_id=info.id)
        self.bridge.overlays_catalog_changed.emit()
        self.status.setText("Alerta creada. Personalízala aquí o elígela en Triggers → Mostrar en.")

    def _import_html(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Importar HTML independiente", "", "HTML (*.html *.htm)")
        if path:
            self._do_import(Path(path))

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
        self.bridge.overlays_catalog_changed.emit()
        self.status.setText("Overlay importado. Ya aparece en el catálogo.")


# --------------------------------------------------------------------------
# Ventana principal
# --------------------------------------------------------------------------

class MainWindow(QMainWindow):
    def __init__(self, runtime: Runtime, bridge: LogBridge) -> None:
        super().__init__()
        self.rt = runtime
        self.setWindowTitle("Streamer Linux Bot · Editor de perfil" if runtime.editor_only else "Streamer Linux Bot")
        self.resize(960, 640)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(2000)
        for line in runtime.log_history:
            self.log_view.appendPlainText(line)
        bridge.message.connect(self.log_view.appendPlainText)

        tabs = QTabWidget()
        if runtime.editor_only:
            help_editor = QLabel("Editor de perfil: no abre puertos ni transmite. "
                                 "Guarda los cambios y recarga el servidor desde terminal para aplicarlos.")
            help_editor.setWordWrap(True)
            help_editor.setMargin(18)
            tabs.addTab(help_editor, "Inicio")
        else:
            tabs.addTab(HomeTab(runtime, bridge), "Inicio")
        tabs.addTab(TriggersTab(runtime, bridge), "Triggers")
        tabs.addTab(RulesPanel(runtime, "action", bridge.rules_changed), "Acciones")
        bridge.gift_save_done.connect(lambda error: bridge.rules_changed.emit("quick") if not error else None)
        tabs.addTab(OverlaysTab(runtime, bridge), "Overlays")
        tabs.addTab(self.log_view, "Registro")
        guide = QLabel(
            "<h2>Tu primera alerta</h2>"
            "<ol><li>En <b>Overlays</b>, selecciona <b>Alerta de regalos</b> y copia su URL.</li>"
            "<li>En OBS, añade una <b>Fuente de navegador</b>, pega la URL y deja la fuente visible.</li>"
            "<li>En TikTok LIVE Studio, si está disponible, usa <b>Añadir fuente → Enlace</b>. "
            "Si el bot está en otro equipo, sigue la guía del repositorio para crear un túnel privado.</li>"
            "<li>Vuelve a <b>Inicio</b> y pulsa <b>Regalo (TikTok)</b> para simular una Rosa ×3.</li>"
            "<li>En <b>Triggers</b> puedes cambiar el título, el filtro y el sonido de la alerta.</li></ol>"
            "<p>Si no aparece, revisa que el navegador de OBS tenga la URL correcta y vuelve a pulsar "
            "el botón con la fuente visible. El resultado también se registra en <b>Registro</b>.</p>"
            "<p>Los eventos simulados no necesitan una cuenta. La conexión de OBS por WebSocket "
            "es independiente de la fuente de navegador.</p>"
        )
        guide.setWordWrap(True)
        guide.setMargin(18)
        guide.setAlignment(Qt.AlignTop)
        tabs.addTab(guide, "Primeros pasos")
        tabs.addTab(RulesPanel(runtime, "trigger", bridge.rules_changed), "Todos los triggers")
        self.setCentralWidget(tabs)
