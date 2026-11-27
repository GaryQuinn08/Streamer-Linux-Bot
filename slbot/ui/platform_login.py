"""Controles Qt de inicio de sesión para Twitch y YouTube."""
from __future__ import annotations

import asyncio
from concurrent.futures import Future
from pathlib import Path

from PySide6.QtCore import QSettings, Qt, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox, QGroupBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout,
)

from ..connectors.oauth import deployment_setting

GUIDE = "https://github.com/GaryQuinn08/Streamer-Linux-Bot/blob/refactor/overlay-boundary/docs/CONECTORES.md#iniciar-sesión-desde-la-app"


class PlatformLoginPanel(QGroupBox):
    open_requested = Signal(str, object)

    def __init__(self, rt, settings=None):
        super().__init__("Twitch / YouTube")
        self.rt = rt
        self.settings = settings if settings is not None else QSettings("Streamer Linux Bot", "Streamer Linux Bot")
        self.controls = {}
        self.configured = {key: self._available(key) for key in ("twitch", "youtube")}
        self.open_requested.connect(self._open_in_desktop, Qt.ConnectionType.QueuedConnection)
        layout = QVBoxLayout(self)
        details = QLabel("Cuando la conexión esté disponible, pulsa Conectar y autoriza en el sitio oficial. El bot no te pedirá credenciales "
                         "de desarrollador, contraseñas ni tokens.")
        details.setWordWrap(True)
        layout.addWidget(details)

        for key, name in (("twitch", "Twitch"), ("youtube", "YouTube")):
            row = QHBoxLayout()
            connect = QPushButton(f"Conectar {name}")
            connect.setObjectName(f"signin-{key}")
            connect.clicked.connect(lambda checked=False, k=key: self._start(k))
            disconnect = QPushButton("Desconectar")
            disconnect.setAccessibleName(f"Desconectar {name}")
            disconnect.clicked.connect(lambda checked=False, k=key: self._stop(k))
            for button in (connect, disconnect):
                row.addWidget(button)
            layout.addLayout(row)
            status = QLabel()
            status.setTextFormat(Qt.TextFormat.PlainText)
            status.setWordWrap(True)
            layout.addWidget(status)
            self.controls[key] = connect, disconnect, status
            if key == "twitch":
                self.twitch_write = QCheckBox("Autorizar envío manual al chat de Twitch")
                self.twitch_write.setObjectName("twitch-write-permission")
                self.twitch_write.setToolTip("Actívalo antes de conectar. Si ya estás conectado, desconecta primero.")
                layout.addWidget(self.twitch_write)

        help_button = QPushButton("Ayuda con las conexiones")
        help_button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(GUIDE)))
        layout.addWidget(help_button)
        self.refresh()

    def _setting(self, platform):
        profile = self.rt.config.path.parent if self.rt.config.path else None
        managed = deployment_setting(platform, profile)
        if managed:
            return managed
        # No vuelve a pedir credenciales, pero conserva una configuración anterior.
        return self.settings.value(f"browser_login/{platform}", "", type=str).strip()

    def _available(self, platform):
        setting = self._setting(platform)
        if setting and (platform != "youtube" or Path(setting).is_file()):
            return setting
        return ""

    def _start(self, platform):
        connector = self.rt.connectors[platform]
        if connector.busy:
            return
        setting = self.configured[platform]
        if not setting:
            return
        self.controls[platform][0].setEnabled(False)
        options = {"twitch_write": True} if platform == "twitch" and self.twitch_write.isChecked() else {}
        self.rt.submit(connector.start(browser=self._browser, setting=setting, **options))

    def _stop(self, platform):
        self.rt.submit(self.rt.connectors[platform].stop())

    async def _browser(self, url):
        opened = Future()
        self.open_requested.emit(url, opened)
        return await asyncio.wrap_future(opened)

    @Slot(str, object)
    def _open_in_desktop(self, url, result):
        if result.set_running_or_notify_cancel():
            try:
                opened = QDesktopServices.openUrl(QUrl(url))
            except Exception:
                opened = False
            result.set_result(opened)

    def refresh(self):
        for key, (connect, disconnect, label) in self.controls.items():
            connector = self.rt.connectors[key]
            busy = connector.busy
            available = bool(self.configured[key])
            connect.setEnabled(not busy and available)
            if not available and not busy:
                label.setText("No disponible en esta beta: la distribución aún no incluye el acceso de Streamer Linux Bot. No tienes que registrarte como desarrollador.")
            else:
                label.setText(connector.status)
            disconnect.setEnabled(busy)
            if key == "twitch":
                self.twitch_write.setEnabled(available and not busy)
