"""Controles Qt de inicio de sesión para Twitch y YouTube."""
from __future__ import annotations

import asyncio
import os
from concurrent.futures import Future
from pathlib import Path

from PySide6.QtCore import QSettings, Qt, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFileDialog, QGroupBox, QHBoxLayout, QInputDialog, QLabel, QPushButton, QVBoxLayout,
)

from ..connectors.oauth import TWITCH_REDIRECT

GUIDE = "https://github.com/GaryQuinn08/Streamer-Linux-Bot/blob/refactor/overlay-boundary/docs/CONECTORES.md#iniciar-sesión-desde-la-app"


class PlatformLoginPanel(QGroupBox):
    open_requested = Signal(str, object)

    def __init__(self, rt, settings=None):
        super().__init__("Twitch / YouTube")
        self.rt = rt
        self.settings = settings if settings is not None else QSettings("Streamer Linux Bot", "Streamer Linux Bot")
        self.controls = {}
        self.open_requested.connect(self._open_in_desktop, Qt.ConnectionType.QueuedConnection)
        layout = QVBoxLayout(self)
        details = QLabel("Autoriza en tu navegador, sin pegar tokens en la terminal. "
                         "La primera vez necesitas el registro de desarrollador de la plataforma.")
        details.setWordWrap(True)
        layout.addWidget(details)

        for key, name in (("twitch", "Twitch"), ("youtube", "YouTube")):
            row = QHBoxLayout()
            connect = QPushButton(f"Iniciar sesión en {name}")
            connect.setObjectName(f"signin-{key}")
            connect.clicked.connect(lambda checked=False, k=key: self._start(k))
            setup = QPushButton("Configurar…")
            setup.setAccessibleName(f"Configurar {name}")
            setup.clicked.connect(lambda checked=False, k=key: self._choose_setting(k))
            disconnect = QPushButton("Desconectar")
            disconnect.setAccessibleName(f"Desconectar {name}")
            disconnect.clicked.connect(lambda checked=False, k=key: self._stop(k))
            for button in (connect, setup, disconnect):
                row.addWidget(button)
            layout.addLayout(row)
            status = QLabel()
            status.setTextFormat(Qt.TextFormat.PlainText)
            status.setWordWrap(True)
            layout.addWidget(status)
            self.controls[key] = connect, setup, disconnect, status

        help_button = QPushButton("Ver guía de configuración")
        help_button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(GUIDE)))
        layout.addWidget(help_button)
        self.refresh()

    def _setting(self, platform):
        key = f"browser_login/{platform}"
        if self.settings.contains(key):
            return self.settings.value(key, "", type=str)
        return os.getenv("SLB_TWITCH_CLIENT_ID" if platform == "twitch" else "SLB_GOOGLE_CLIENT_JSON", "").strip()

    def _choose_setting(self, platform):
        if platform == "twitch":
            value, ok = QInputDialog.getText(
                self, "Configurar Twitch",
                f"Client ID de tu app pública de Twitch. Registra esta URL OAuth:\n{TWITCH_REDIRECT}",
                text=self._setting(platform),
            )
            value = value.strip() if ok else ""
        else:
            value, _ = QFileDialog.getOpenFileName(
                self, "Elige el JSON OAuth de Google (Aplicación de escritorio)",
                str(Path.home()), "Configuración de Google (*.json)")
        if value:
            self.settings.setValue(f"browser_login/{platform}", value)
        return value

    def _start(self, platform):
        connector = self.rt.connectors[platform]
        if connector.busy:
            return
        setting = self._setting(platform)
        if not setting or (platform == "youtube" and not Path(setting).is_file()):
            setting = self._choose_setting(platform)
        if not setting:
            return
        self.controls[platform][0].setEnabled(False)
        self.rt.submit(connector.start(browser=self._browser, setting=setting))

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
        for key, (connect, setup, disconnect, label) in self.controls.items():
            connector = self.rt.connectors[key]
            busy = connector.busy
            connect.setEnabled(not busy)
            setup.setEnabled(not busy)
            disconnect.setEnabled(busy)
            label.setText(connector.status)
