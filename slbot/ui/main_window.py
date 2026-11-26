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
    QFrame,
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
    QStackedWidget,
    QScrollArea,
    QGroupBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..connectors.simulator import SAMPLE_KINDS, sample_event
from ..overlay_pack import import_pack
from ..overlay_manager import OverlayInfo, create_alert, import_overlay, list_overlays, validate_overlay_values
from ..runtime import Runtime
from .rule_editor import ActionWorkspace, RulesPanel
from .platform_login import PlatformLoginPanel

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
    overlay_deleted = Signal(str, str)
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
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Conexión", "Estado"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
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
        tiktok_group = QGroupBox("TikTok LIVE · experimental")
        tiktok_form = QFormLayout(tiktok_group)
        self.tiktok_mode = QComboBox()
        self.tiktok_mode.addItem("TikTok directo · sin TikFinity", "directo")
        self.tiktok_mode.addItem("TikFinity · puente opcional", "tikfinity")
        self.tiktok_channel = QLineEdit()
        self.tiktok_channel.setPlaceholderText("@usuario en directo")
        self.tiktok_mode.currentIndexChanged.connect(self._update_tiktok_mode)
        tiktok_form.addRow("Conector:", self.tiktok_mode)
        tiktok_form.addRow("Canal:", self.tiktok_channel)
        self.tiktok_hint = QLabel()
        self.tiktok_hint.setObjectName("tiktok-mode-hint")
        self.tiktok_hint.setWordWrap(True)
        tiktok_form.addRow(self.tiktok_hint)
        self._update_tiktok_mode()
        tiktok_row = QHBoxLayout()
        connect_tiktok = QPushButton("Conectar TikTok")
        connect_tiktok.clicked.connect(self._connect_tiktok)
        disconnect_tiktok = QPushButton("Desconectar TikTok")
        disconnect_tiktok.clicked.connect(lambda: self.rt.submit(self.rt.connectors["tiktok"].stop()))
        tiktok_row.addWidget(connect_tiktok)
        tiktok_row.addWidget(disconnect_tiktok)
        tiktok_row.addStretch(1)
        tiktok_form.addRow(tiktok_row)
        self.platform_login = PlatformLoginPanel(runtime)
        layout.addWidget(self.platform_login)
        layout.addWidget(tiktok_group)

        sample_group = QGroupBox("Eventos de prueba")
        sample_layout = QVBoxLayout(sample_group)
        sample_caption = QLabel("Los eventos simulados pasan por los disparadores y overlays. No necesitan cuenta.")
        sample_caption.setProperty("muted", True)
        sample_caption.setWordWrap(True)
        sample_layout.addWidget(sample_caption)
        tests = QHBoxLayout()
        for kind in SAMPLE_KINDS:
            button = QPushButton(SAMPLE_LABELS[kind])
            button.clicked.connect(functools.partial(self._send_sample, kind))
            tests.addWidget(button)
        tests.addStretch(1)
        sample_layout.addLayout(tests)
        layout.addWidget(sample_group)
        layout.addWidget(obs_group)
        layout.addWidget(overlay_group)

        connection_status = QGroupBox("Estado de los conectores")
        status_layout = QVBoxLayout(connection_status)
        status_layout.setContentsMargins(3, 3, 3, 3)
        self.table.verticalHeader().setDefaultSectionSize(26)
        self.table.setMinimumHeight(166)
        status_layout.addWidget(self.table)
        layout.addWidget(connection_status)
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

    def _update_tiktok_mode(self, _index=None) -> None:
        direct = self.tiktok_mode.currentData() == "directo"
        self.tiktok_channel.setEnabled(direct)
        self.tiktok_hint.setText(
            "Solo escribe tu @usuario cuando estés en vivo. No necesitas iniciar sesión ni instalar "
            "TikFinity. Usa la biblioteca no oficial TikTokLive (instalación: --tiktok)."
            if direct else
            "Usa este modo solo si ya tienes TikFinity enviando eventos a su API local. "
            "Es una alternativa; no se necesita para usar TikTok directo."
        )

    def _send_sample(self, kind: str) -> None:
        self.rt.emit(sample_event(kind))

    def refresh(self) -> None:
        port = self.rt.port
        self.server_label.setText(f"Servidor de overlays: http://127.0.0.1:{port}/" if port is not None
                                  else self.rt.overlay_port_message or "Asigna un puerto para activar los overlays.")
        self.open_catalog.setEnabled(port is not None)
        self.platform_login.refresh()
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
    delete_done = Signal(str)

    def __init__(self, runtime: Runtime, bridge: LogBridge) -> None:
        super().__init__()
        self.rt = runtime
        self.bridge = bridge
        self._editing = False
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
        self.result = QLabel("El botón de Conexiones simula Rose ×3. Usa «Rose» o deja el filtro vacío para probar.")
        self.result.setWordWrap(True)
        form.addRow(self.result)
        layout.addWidget(editor)
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["Nombre", "Plataforma", "Evento", "Filtros", "Cooldown (s)", "Acción", "Activo"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table)
        from .deletion import delete_shortcut
        self.delete_button = QPushButton("Eliminar disparador seleccionado")
        self.delete_button.setEnabled(False)
        self.delete_button.clicked.connect(self._delete_trigger)
        self.table.itemSelectionChanged.connect(self._update_delete_button)
        delete_shortcut(self.table, self._delete_trigger)
        layout.addWidget(self.delete_button, alignment=Qt.AlignmentFlag.AlignLeft)
        self.delete_done.connect(self._deleted)
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
        self.table.clearSelection()
        self.save_button.setText("Guardar regla" if any(t.id == "tiktok-gift" for t in triggers)
                                 else "Crear regla de regalos")
        self.table.setRowCount(len(triggers))
        for row, t in enumerate(triggers):
            values = [t.name, t.platform, t.event_type, json.dumps(t.filters, ensure_ascii=False),
                      str(t.cooldown_s), t.action_id, "sí" if t.enabled else "no"]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole, t.id)
                self.table.setItem(row, col, item)

    def _delete_trigger(self) -> None:
        from .deletion import confirm_delete
        if not self.delete_button.isEnabled():
            return
        item = self.table.item(self.table.currentRow(), 0)
        if item is None:
            return
        ident = item.data(Qt.ItemDataRole.UserRole)
        if not confirm_delete(self, "Eliminar disparador", f"¿Eliminar el disparador «{item.text()}»?"):
            return
        self._editing = True
        self.table.setEnabled(False)
        self._update_delete_button()
        self.save_button.setEnabled(False)
        future = self.rt.submit(self.rt.edit_rule("trigger", {"id": ident}, delete=True))

        def done(completed) -> None:
            message = "Se canceló la operación." if completed.cancelled() else str(completed.exception() or "")
            self.delete_done.emit(message)

        future.add_done_callback(done)

    def _deleted(self, error: str) -> None:
        self._editing = False
        self.table.setEnabled(True)
        self.save_button.setEnabled(True)
        if not error:
            self.bridge.rules_changed.emit("trigger")
        self._update_delete_button()
        self.result.setText(f"No se pudo eliminar: {error}" if error else "Disparador eliminado.")

    def _update_delete_button(self) -> None:
        self.delete_button.setEnabled(not self._editing and bool(self.table.selectedItems()))

    def _refresh_targets(self, selected: str | None = None) -> None:
        selected = selected or self.destination.currentData()
        self.destination.clear()
        for item in sorted(list_overlays().values(), key=lambda item: item.id != "gift-alert"):
            if item.id not in {"event-feed", "live-goal", "multi-chat"}:
                self.destination.addItem(item.name, item.id)
        index = self.destination.findData(selected)
        self.destination.setCurrentIndex(max(index, 0))

    def _pick_sound(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Elegir sonido", "", "Audio (*.wav *.ogg *.mp3 *.flac);;Todos (*)")
        if path:
            self.sound.setText(path)

    def _save_rule(self) -> None:
        if self._editing:
            return
        title, sound = self.title.text().strip(), self.sound.text().strip()
        if not title or (sound and not Path(sound).expanduser().is_file()):
            self.result.setText("Escribe un título y elige un archivo de sonido que exista (u omítelo).")
            return
        self._editing = True
        self._update_delete_button()
        self.save_button.setEnabled(False)
        future = self.rt.submit(self.rt.save_gift_rule(
            self.enabled_rule.isChecked(), self.gift_name.text().strip(),
            self.cooldown.value(), title, str(Path(sound).expanduser().resolve()) if sound else "",
            self.destination.currentData(),
        ))
        bridge = self.bridge

        def done(completed) -> None:
            if completed.cancelled():
                bridge.gift_save_done.emit("Se canceló la operación.")
                return
            error = completed.exception()
            bridge.gift_save_done.emit(str(error) if error else "")

        future.add_done_callback(done)

    def _saved(self, error: str) -> None:
        self._editing = False
        self.save_button.setEnabled(True)
        self.result.setText(f"No se pudo guardar: {error}" if error else "Regla guardada. Prueba el regalo desde Conexiones.")
        if not error:
            self._refresh()
        self._update_delete_button()


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
        self._deleting: str | None = None

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
        import_theme = QPushButton("Importar tema (.slbpack)…")
        import_theme.clicked.connect(self._import_theme)
        left.addWidget(import_theme)
        self.delete_btn = QPushButton("Eliminar overlay…")
        self.delete_btn.clicked.connect(self._delete_overlay)
        self.delete_btn.setEnabled(False)
        left.addWidget(self.delete_btn)
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
        self.overlay_hint = QLabel()
        self.overlay_hint.setWordWrap(True)

        right.addWidget(self.title)
        right.addWidget(self.desc)
        right.addWidget(self.preview)
        right.addLayout(edits)
        right.addWidget(self.status)
        right.addWidget(QLabel("URL del overlay:"))
        right.addWidget(self.url)
        right.addWidget(self.overlay_hint)
        right.addLayout(buttons)
        right.addWidget(self.form_host)
        right.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        detail = QWidget()
        right.setContentsMargins(4, 0, 6, 0)
        detail.setLayout(right)
        scroll.setWidget(detail)
        root.addWidget(scroll, 1)

        self.bridge.overlay_saved.connect(self._preset_saved)
        self.bridge.overlay_deleted.connect(self._overlay_deleted)
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
        if info.id == "multi-chat":
            self.overlay_hint.setText(
                "OBS: al pegar esta URL en las propiedades de la fuente Navegador, marca "
                "«Actualizar el navegador cuando la escena se active». "
                "Al recargarse, la fuente empieza sin los mensajes anteriores. "
                "Abre la fuente antes de pulsar «Probar alerta»."
            )
        else:
            self.overlay_hint.setText(
                "Abre la URL en el navegador o como fuente de OBS antes de probar. "
                "Después de guardar la apariencia, actualiza la fuente para verla."
            )
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
        self.delete_btn.setEnabled(info.source == "user" and self._deleting is None)
        self.delete_btn.setToolTip("Los overlays incluidos no se eliminan." if info.source == "builtin" else "")
        kind = info.appearance.kind if info.appearance else None
        self.preview_btn.setText({"chat": "Probar chat", "events": "Probar actividad"}.get(kind, "Probar alerta"))
        if info.appearance:
            self.desc.setText(info.description + "\nPersonaliza el diseño y guarda. Los cambios mantienen tu URL.")
        elif not info.params and info.source == "user":
            self.desc.setText(info.description + "\nEste HTML no incluye ajustes editables; se conserva sin modificar.")
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
            appearance_options = {
                "left": "Izquierda", "center": "Centro", "right": "Derecha", "none": "Ninguna",
                "fade": "Desvanecer", "slide-up": "Deslizar arriba", "slide-left": "Deslizar a la izquierda",
                "zoom": "Zoom", "pop": "Rebote",
            } if self._info and self._info.appearance else {}
            for option in map(str, p.get("options", [])):
                w.addItem(appearance_options.get(option, option), option)
            w.setCurrentIndex(w.findData(str(default)))
            w.currentIndexChanged.connect(lambda _: setter(w.currentData()))
            return w
        w = QLineEdit(str(default))
        if "maxLength" in p and self._info and self._info.appearance:
            w.setMaxLength(p["maxLength"])
        w.textChanged.connect(setter)
        return w

    def _update_url(self) -> None:
        port = self.rt.port
        ready = port is not None and self._info is not None
        self.url.setText(f"http://127.0.0.1:{port}/overlay/{self._info.id}/" if ready else "")
        self.url.setPlaceholderText("Asigna un puerto desde Inicio para generar la URL.")
        for button in (self.copy_btn, self.open_btn):
            button.setEnabled(ready)
        kind = self._info.appearance.kind if self._info and self._info.appearance else None
        self.preview_btn.setEnabled(ready and (kind is None or kind in {"alert", "chat", "events"}))

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
        if error:
            self.status.setText(f"No se guardó: {error}")
        elif overlay_id == "multi-chat":
            self.status.setText("Apariencia guardada. La fuente abierta se actualiza sin cambiar la URL.")
        else:
            self.status.setText("Apariencia guardada. Actualiza la fuente de OBS; la URL no cambia.")

    def _delete_overlay(self) -> None:
        info = self._info
        if info is None or info.source != "user" or self._deleting:
            return
        uses = self.rt.overlay_use_count(info.id)
        detail = f"Se quitarán {uses} paso(s) de acción que usan ese overlay. " if uses else ""
        confirm = QMessageBox(self)
        confirm.setIcon(QMessageBox.Warning)
        confirm.setWindowTitle("Eliminar overlay")
        confirm.setTextFormat(Qt.PlainText)
        confirm.setText(f"¿Eliminar «{info.name}» del bot?")
        confirm.setInformativeText(detail + "La URL dejará de funcionar. No se eliminarán fuentes ni escenas de OBS.")
        confirm.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        confirm.setDefaultButton(QMessageBox.No)
        if confirm.exec() != QMessageBox.Yes:
            return
        self._deleting = info.id
        self.delete_btn.setEnabled(False)
        future = self.rt.submit(self.rt.delete_user_overlay(info.id, uses))
        signal = self.bridge.overlay_deleted

        def done(completed) -> None:
            error = completed.exception() if not completed.cancelled() else RuntimeError("Operación cancelada.")
            signal.emit(info.id, str(error) if error else "")

        future.add_done_callback(done)

    def _overlay_deleted(self, overlay_id: str, error: str) -> None:
        self._deleting = None
        current = self._info.id if self._info else None
        if error:
            self.delete_btn.setEnabled(self._info is not None and self._info.source == "user")
            QMessageBox.warning(self, "Eliminar overlay", error)
            return
        self.refresh(select_id=current if current != overlay_id else None)
        self.bridge.overlays_catalog_changed.emit()
        self.bridge.rules_changed.emit("action")
        self.status.setText("Overlay eliminado. Sus archivos externos y las fuentes de OBS no cambiaron.")

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

    def _import_theme(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Importar tema completo", "", "Tema (*.slbpack)")
        if not path:
            return
        try:
            pieces = import_pack(Path(path))
        except (ValueError, OSError) as exc:
            QMessageBox.warning(self, "Importar tema", str(exc))
            return
        self.refresh(select_id=pieces[0].id)
        self.bridge.overlays_catalog_changed.emit()
        self.rt.log(f"Tema importado: {len(pieces)} pieza(s)")
        self.status.setText(f"Tema importado: {len(pieces)} pieza(s). Copia sus URLs a fuentes Navegador de OBS.")

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

# Top-level workbench palette: a dark native desktop with a restrained mint accent.
WORKBENCH_STYLE = """
QMainWindow, QWidget#desktop-workbench { background: #12161d; color: #edf0f5; }
QWidget { color: #e0e5ed; }
QLabel[muted="true"] { color: #aab6c5; }
QFrame#workbench-sidebar { background: #191e27; border-right: 1px solid #2b3441; }
QLabel#workbench-brand { color: #edf3fa; font-size: 16px; font-weight: 700; }
QLabel#workbench-mark {
    background: #163f39; color: #88f0cb; border: 1px solid #317861;
    border-radius: 7px; font-size: 12px; font-weight: 700;
}
QLabel[navSection="true"] { color: #9caabc; font-size: 10px; font-weight: 700; padding: 8px 8px 3px; }
QPushButton[nav="true"] {
    text-align: left; border: 1px solid transparent; background: transparent; color: #c0ccda;
    padding: 8px 10px; border-radius: 5px;
}
QPushButton[nav="true"]:hover { background: #262f3d; color: #f1f8ff; }
QPushButton[nav="true"]:checked { background: #24423e; border-color: #3a7a67; color: #a3f2d4; font-weight: 700; }
QLabel#workbench-heading { font-size: 24px; font-weight: 700; color: #f2f6fc; }
QLabel#workbench-description { color: #a4b0c0; padding-bottom: 2px; }
QLabel#workbench-mode { border: 1px solid #3d4858; color: #b3c2d0; border-radius: 5px; padding: 4px 7px; }
QFrame#workbench-pane { background: #191f29; border: 1px solid #303b4a; border-radius: 8px; }
QLabel#workbench-pane-title { color: #edf3fa; font-size: 13px; font-weight: 700; }
QLabel#workbench-count { color: #acebcf; background: #233e3a; padding: 3px 7px; border-radius: 5px; }
QLabel#workbench-notice { color: #adb9c8; padding: 3px 0; }
QLabel#tiktok-mode-hint { color: #b3c4cf; }
QWidget#desktop-workbench QStackedWidget, QScrollArea { border: 0; }
QScrollArea > QWidget > QWidget { background: #12161d; }
QScrollBar:vertical { background: #18212b; width: 9px; margin: 0; border-radius: 4px; }
QScrollBar:horizontal { background: #18212b; height: 9px; margin: 0; border-radius: 4px; }
QScrollBar::handle { background: #526377; border: 1px solid #18212b; border-radius: 4px; }
QScrollBar::handle:vertical { min-height: 24px; }
QScrollBar::handle:horizontal { min-width: 24px; }
QScrollBar::handle:hover { background: #687e94; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: none; }
QGroupBox { border: 1px solid #364353; border-radius: 7px; margin-top: 10px; padding: 10px 8px 7px; font-weight: 700; }
QGroupBox::title { subcontrol-origin: margin; left: 9px; padding: 0 5px; color: #e0e8f1; }
QPushButton { padding: 5px 8px; background: #283241; border: 1px solid #435269; border-radius: 5px; }
QPushButton:hover { background: #34465a; border-color: #61788e; }
QPushButton:focus, QLineEdit:focus, QComboBox:focus { border-color: #6ebca2; }
QPushButton[role="primary"] { color: #b3f5df; background: #275046; border-color: #42866f; font-weight: 600; }
QPushButton[role="primary"]:hover { background: #32685a; }
QPushButton:disabled { color: #8190a2; background: #242b35; border-color: #333c46; }
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPlainTextEdit, QListWidget, QTableWidget {
    background: #141922; border: 1px solid #394657; border-radius: 5px;
    selection-background-color: #2e6157; selection-color: #ffffff;
}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPlainTextEdit { padding: 4px 6px; }
QListWidget::item { padding: 5px; }
QTableWidget { alternate-background-color: #19212b; gridline-color: #2e3948; }
QTableWidget::item { padding-left: 6px; }
QHeaderView::section { background: #263140; color: #cbd5e2; border: 0; padding: 5px 6px; }
QStatusBar { background: #191e27; color: #c1cddb; border-top: 1px solid #303b4a; }
QStatusBar::item { border: none; }
QMenu, QDialog, QMessageBox { background: #1d2530; color: #edf2f8; }
QMenu::item:selected { background: #2e6157; color: #fff; }
QToolTip { background: #202b39; color: #f2f6fc; border: 1px solid #456073; padding: 4px; }
"""


class MainWindow(QMainWindow):
    def __init__(self, runtime: Runtime, bridge: LogBridge) -> None:
        super().__init__()
        self.rt = runtime
        self.setWindowTitle("Streamer Linux Bot · Editor de perfil" if runtime.editor_only else "Streamer Linux Bot")
        self.resize(1100, 720)
        self.setMinimumSize(760, 535)
        self.setStyleSheet(WORKBENCH_STYLE)

        shell = QWidget()
        shell.setObjectName("desktop-workbench")
        outer = QHBoxLayout(shell)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        sidebar = QFrame()
        sidebar.setObjectName("workbench-sidebar")
        sidebar.setFixedWidth(172)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(11, 15, 11, 12)
        side.setSpacing(4)
        brand = QHBoxLayout()
        brand.setSpacing(8)
        mark = QLabel("SL")
        mark.setObjectName("workbench-mark")
        mark.setFixedSize(29, 29)
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        brand.addWidget(mark)
        title = QLabel("Streamer\nLinux Bot")
        title.setObjectName("workbench-brand")
        brand.addWidget(title)
        brand.addStretch(1)
        side.addLayout(brand)
        side.addSpacing(9)
        outer.addWidget(sidebar)

        center = QVBoxLayout()
        center.setContentsMargins(17, 14, 17, 10)
        center.setSpacing(10)
        header = QHBoxLayout()
        words = QVBoxLayout()
        words.setSpacing(2)
        self.heading = QLabel()
        self.heading.setObjectName("workbench-heading")
        self.description = QLabel()
        self.description.setObjectName("workbench-description")
        self.description.setWordWrap(True)
        words.addWidget(self.heading)
        words.addWidget(self.description)
        header.addLayout(words, 1)
        mode = QLabel("EDITOR DE PERFIL" if runtime.editor_only else "MODO LOCAL")
        mode.setObjectName("workbench-mode")
        header.addWidget(mode, 0, Qt.AlignmentFlag.AlignTop)
        center.addLayout(header)
        self.pages = QStackedWidget()
        self.pages.setObjectName("workbench-pages")
        center.addWidget(self.pages, 1)
        outer.addLayout(center, 1)
        self.setCentralWidget(shell)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(2000)
        self.log_view.setPlaceholderText("No hay actividad todavía.")
        for line in runtime.log_history:
            self.log_view.appendPlainText(line)
        bridge.message.connect(self.log_view.appendPlainText)
        self.action_page = ActionWorkspace(runtime, bridge.rules_changed)
        self.trigger_page = RulesPanel(runtime, "trigger", bridge.rules_changed)
        from .timer_panel import TimerPanel
        self.timer_page = TimerPanel(runtime, bridge.rules_changed)
        self.quick_page = TriggersTab(runtime, bridge)
        self.overlays_page = OverlaysTab(runtime, bridge)
        bridge.gift_save_done.connect(lambda error: bridge.rules_changed.emit("quick") if not error else None)

        if runtime.editor_only:
            self.connections_page = QLabel("Editor de perfil: no abre puertos ni transmite. "
                                           "Guarda los cambios y recarga el servidor desde terminal para aplicarlos.")
            self.connections_page.setWordWrap(True)
            self.connections_page.setAlignment(Qt.AlignmentFlag.AlignTop)
            self.connections_page.setMargin(12)
        else:
            from .monitor import SessionPanel
            from .music_panel import MusicPanel

            self.connections_page = HomeTab(runtime, bridge)
            self.music_page = MusicPanel(runtime)
            self.chat_page = SessionPanel(runtime, chat=True)
            self.history_page = SessionPanel(runtime, chat=False)

        self.navigation = {}

        def add_group(name):
            label = QLabel(name)
            label.setProperty("navSection", True)
            side.addWidget(label)

        def add_page(key, title_text, help_text, page):
            idx = self.pages.addWidget(page)
            button = QPushButton(title_text)
            button.setCheckable(True)
            button.setProperty("nav", True)
            button.setObjectName(f"navigate-{key}")
            button.clicked.connect(lambda _checked=False: self.select_page(key))
            side.addWidget(button)
            self.navigation[key] = (idx, title_text, help_text, button)

        add_group("AUTOMATIZACIÓN")
        add_page("actions", "Acciones", "Edita los disparadores y los pasos de una acción desde un solo lugar.", self.action_page)
        add_page("triggers", "Disparadores", "Consulta todos los eventos que activan tus acciones.", self.trigger_page)
        add_page("timers", "Temporizadores", "Ejecuta acciones a intervalos sin depender del chat.", self.timer_page)
        add_page("gifts", "Regla de regalos", "Configura rápidamente la alerta predeterminada de TikTok.", self.quick_page)
        add_group("TRANSMISIÓN")
        add_page("connections", "Conexiones", "Conecta tus cuentas, prepara OBS o prueba un evento simulado.", self.connections_page)
        add_page("overlays", "Overlays", "Personaliza tus alertas y copia el enlace para OBS o TikTok LIVE Studio.", self.overlays_page)
        if not runtime.editor_only:
            add_page("music", "Música", "Gestiona fuentes de audio y su cola de reproducción.", self.music_page)
        add_group("MONITOR")
        if not runtime.editor_only:
            add_page("chat", "Chat", "Lee los mensajes de todas las plataformas en un solo lugar.", self.chat_page)
            add_page("history", "Historial", "Consulta qué disparó cada acción, su resultado y su duración.", self.history_page)
        add_page("log", "Registro", "Revisa eventos, conexiones y errores de esta sesión.", self.log_view)
        guide = QLabel(
            "<h2>Tu primera alerta</h2>"
            "<ol><li>En <b>Overlays</b>, selecciona <b>Alerta de regalos</b> y copia su URL.</li>"
            "<li>En OBS añade una <b>Fuente de navegador</b>, pega la URL y deja la fuente visible. "
            "En TikTok LIVE Studio, usa una fuente <b>Enlace</b> si la opción está disponible.</li>"
            "<li>En <b>Conexiones</b>, pulsa <b>Regalo (TikTok)</b> para simular una Rosa ×3.</li>"
            "<li>Desde <b>Acciones</b> puedes editar qué eventos disparan la alerta y en qué orden se ejecutan sus pasos.</li></ol>"
            "<p>Para TikTok en vivo, usa <b>TikTok directo</b> con tu @usuario y el conector no oficial "
            "TikTokLive. TikFinity es un puente alternativo, no un requisito.</p>"
            "<p>Los eventos simulados no necesitan cuenta. El control de OBS por WebSocket se usa "
            "para escenas y fuentes; no hace falta para mostrar una alerta en el navegador.</p>"
        )
        guide.setWordWrap(True)
        guide.setMargin(15)
        guide.setAlignment(Qt.AlignmentFlag.AlignTop)
        add_page("guide", "Guía rápida", "Configura y prueba tu primera alerta.", guide)
        side.addStretch(1)
        self.select_page("actions")

        self.footer = QLabel()
        self.footer.setObjectName("workbench-status")
        self.statusBar().addWidget(self.footer, 1)
        self.statusBar().setSizeGripEnabled(True)
        bridge.overlay_port_done.connect(lambda _error: self._update_status())
        self._update_status()

    def _update_status(self):
        if self.rt.editor_only:
            state = "Editor de perfil · Sin servidor local"
        elif self.rt.port is None:
            state = "Overlays sin conectar · Revisa el puerto en Conexiones"
        else:
            state = f"Overlays activos · 127.0.0.1:{self.rt.port}"
        self.footer.setText(state)

    def select_page(self, key):
        index, title, help_text, _button = self.navigation[key]
        self.pages.setCurrentIndex(index)
        for other, (_index, _title, _text, button) in self.navigation.items():
            button.setChecked(key == other)
        self.heading.setText(title)
        self.description.setText(help_text)
