"""Música: Spotify privado y fuentes que el operador está autorizado a transmitir."""
from __future__ import annotations

import asyncio
from concurrent.futures import Future
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox, QFileDialog, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QVBoxLayout, QWidget,
)

from ..connectors.oauth import deployment_setting


class MusicPanel(QWidget):
    open_requested = Signal(str, object)
    operation_done = Signal(str)

    def __init__(self, rt) -> None:
        super().__init__()
        self.rt = rt
        self.spotify = rt.connectors["spotify"]
        self._pending = False
        self.open_requested.connect(self._open_in_desktop, Qt.ConnectionType.QueuedConnection)
        self.operation_done.connect(self._complete)
        outer = QVBoxLayout(self)

        spotify = QGroupBox("Spotify · escucha privada")
        block = QVBoxLayout(spotify)
        notice = QLabel("Controla la cola de tu Spotify Premium. La música se reproduce en tu dispositivo Spotify, "
                        "no en el bot. No captures ni retransmitas ese audio en tu directo.")
        notice.setWordWrap(True)
        block.addWidget(notice)
        self.private = QCheckBox("No enviaré el audio de Spotify al directo")
        self.private.toggled.connect(self._private_changed)
        block.addWidget(self.private)
        connect_row = QHBoxLayout()
        self.connect = QPushButton("Conectar Spotify")
        self.connect.setObjectName("connect-spotify")
        self.connect.clicked.connect(self._connect)
        self.stop = QPushButton("Desconectar Spotify")
        self.stop.clicked.connect(lambda: self.rt.submit(self.spotify.stop()))
        connect_row.addWidget(self.connect)
        connect_row.addWidget(self.stop)
        block.addLayout(connect_row)
        self.spotify_status = QLabel()
        self.spotify_status.setTextFormat(Qt.TextFormat.PlainText)
        self.spotify_status.setWordWrap(True)
        block.addWidget(self.spotify_status)
        row = QHBoxLayout()
        self.spotify_url = QLineEdit()
        self.spotify_url.setMaxLength(2048)
        self.spotify_url.setAccessibleName("Enlace de canción de Spotify")
        self.spotify_url.setPlaceholderText("Pega el enlace de una canción de Spotify")
        self.spotify_url.returnPressed.connect(self._add_spotify)
        self.add_spotify = QPushButton("Agregar a Spotify")
        self.add_spotify.clicked.connect(self._add_spotify)
        row.addWidget(self.spotify_url)
        row.addWidget(self.add_spotify)
        block.addLayout(row)
        outer.addWidget(spotify)

        licensed = QGroupBox("Audio autorizado para el directo")
        block = QVBoxLayout(licensed)
        notice = QLabel("Usa una URL HTTPS directa al archivo de tu proveedor (MP3, WAV, FLAC u Ogg) o un archivo local. "
                        "Verifica que la licencia cubra tu directo y la repetición si guardas el video.")
        notice.setWordWrap(True)
        block.addWidget(notice)
        self.licensed = QCheckBox("Tengo permiso para transmitir este audio")
        self.licensed.toggled.connect(lambda _checked: self.refresh())
        block.addWidget(self.licensed)
        row = QHBoxLayout()
        self.licensed_url = QLineEdit()
        self.licensed_url.setMaxLength(2048)
        self.licensed_url.setAccessibleName("Enlace directo al archivo de audio autorizado")
        self.licensed_url.setPlaceholderText("https://… enlace directo al archivo de audio")
        self.licensed_url.returnPressed.connect(self._add_url)
        self.url_button = QPushButton("Agregar enlace")
        self.url_button.clicked.connect(self._add_url)
        row.addWidget(self.licensed_url)
        row.addWidget(self.url_button)
        block.addLayout(row)
        row = QHBoxLayout()
        self.local_button = QPushButton("Agregar archivo local…")
        self.local_button.clicked.connect(self._add_file)
        self.clear_button = QPushButton("Detener y vaciar esta cola")
        self.clear_button.clicked.connect(lambda: self._operate(self.rt.music.clear(), "Cola de audio vacía."))
        row.addWidget(self.local_button)
        row.addWidget(self.clear_button)
        block.addLayout(row)
        self.local_status = QLabel()
        self.local_status.setTextFormat(Qt.TextFormat.PlainText)
        self.local_status.setWordWrap(True)
        block.addWidget(self.local_status)
        outer.addWidget(licensed)

        self.result = QLabel()
        self.result.setTextFormat(Qt.TextFormat.PlainText)
        self.result.setWordWrap(True)
        outer.addWidget(self.result)
        outer.addStretch(1)
        timer = QTimer(self)
        timer.timeout.connect(self.refresh)
        timer.start(300)
        self.refresh()

    def refresh(self):
        permitted = self.private.isChecked()
        self.connect.setEnabled(permitted and not self.spotify.busy and not self.spotify.connected)
        self.stop.setEnabled(self.spotify.busy or self.spotify.connected)
        self.add_spotify.setEnabled(permitted and self.spotify.connected and not self._pending)
        self.spotify_url.setEnabled(permitted and self.spotify.connected)
        self.url_button.setEnabled(self.licensed.isChecked() and not self._pending)
        self.local_button.setEnabled(self.licensed.isChecked() and not self._pending)
        self.clear_button.setEnabled(not self._pending)
        self.spotify_status.setText(self.spotify.status)
        current = self.rt.music.current or "Sin reproducción activa"
        pending = self.rt.music.items.qsize()
        error = self.rt.music.last_error
        self.local_status.setText(f"{current} · {pending} en cola" + (f" · {error}" if error else ""))

    def _private_changed(self, checked):
        if not checked:
            self.rt.submit(self.spotify.stop())
        self.refresh()

    def _connect(self):
        if not self.private.isChecked():
            return
        setting = deployment_setting("spotify", self.rt.config.path.parent if self.rt.config.path else None)
        if not setting:
            self.result.setText("Spotify aún no está habilitado por el proyecto en esta instalación.")
            return
        self.result.clear()
        self.rt.submit(self.spotify.start(browser=self._browser, setting=setting))

    def _add_spotify(self):
        if self.add_spotify.isEnabled() and self.spotify_url.text().strip():
            self._operate(self.spotify.enqueue(self.spotify_url.text()), "Canción agregada en Spotify.")

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

    def _add_file(self):
        if not self.local_button.isEnabled():
            return
        name, _ = QFileDialog.getOpenFileName(
            self, "Elige audio autorizado", str(Path.home()), "Audio (*.wav *.mp3 *.ogg *.opus *.flac *.m4a *.aac)")
        if name:
            self._operate(self._local(name, online=False), "Archivo agregado.")

    def _add_url(self):
        if self.url_button.isEnabled() and self.licensed_url.text().strip():
            self._operate(self._local(self.licensed_url.text(), online=True), "Enlace agregado a la cola del bot.")

    async def _local(self, name, *, online):
        if online:
            self.rt.music.enqueue_url(name)
        else:
            self.rt.music.enqueue(name)

    def _operate(self, operation, success):
        self._pending = True
        self.result.clear()
        self.refresh()

        async def run():
            try:
                await operation
            except (ValueError, RuntimeError) as exc:
                self.operation_done.emit(str(exc))
            except Exception:
                self.operation_done.emit("No se pudo completar la operación.")
            else:
                self.operation_done.emit(success)

        self.rt.submit(run())

    def _complete(self, text):
        self._pending = False
        self.result.setText(text)
        self.refresh()
