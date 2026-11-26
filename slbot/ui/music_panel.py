"""Música: Spotify privado y fuentes que el operador está autorizado a transmitir."""
from __future__ import annotations

import asyncio
from concurrent.futures import Future
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from ..connectors.oauth import deployment_setting
from ..now_playing import BOT_SOURCE, MPRIS_PREFIX, available_players
from .deletion import confirm_delete, delete_shortcut


class MusicPanel(QWidget):
    open_requested = Signal(str, object)
    operation_done = Signal(str)
    players_found = Signal(object)

    def __init__(self, rt) -> None:
        super().__init__()
        self.rt = rt
        self.spotify = rt.connectors["spotify"]
        self._pending = False
        self._queue_rows = ()
        self.open_requested.connect(self._open_in_desktop, Qt.ConnectionType.QueuedConnection)
        self.operation_done.connect(self._complete)
        frame = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        scroll.setWidget(content)
        frame.addWidget(scroll)
        outer = QVBoxLayout(content)

        now = QGroupBox("Ahora suena · información para overlays")
        block = QVBoxLayout(now)
        notice = QLabel(
            "Comparte solo título, artista y estado; no conecta cuentas ni transmite el audio. "
            "Si eliges un navegador, puede mostrar los títulos de videos o pestañas privadas. "
            "Usa un reproductor dedicado para evitar mostrarlos."
        )
        notice.setWordWrap(True)
        block.addWidget(notice)
        self.share_now = QCheckBox("Mostrar el tema del reproductor elegido en mis overlays")
        self.share_now.setChecked(rt.now_playing.settings.enabled)
        self.share_now.toggled.connect(lambda _checked: self.refresh())
        block.addWidget(self.share_now)
        row = QHBoxLayout()
        self.player = QComboBox()
        self.player.setAccessibleName("Reproductor que se mostrará en los overlays")
        self.player.currentIndexChanged.connect(lambda _index: self.refresh())
        row.addWidget(self.player, stretch=1)
        self.find_players = QPushButton("Buscar reproductores")
        self.find_players.clicked.connect(self._search_players)
        row.addWidget(self.find_players)
        self.save_player = QPushButton("Guardar Ahora suena")
        self.save_player.clicked.connect(self._save_player)
        row.addWidget(self.save_player)
        block.addLayout(row)
        self.now_status = QLabel()
        self.now_status.setTextFormat(Qt.TextFormat.PlainText)
        self.now_status.setWordWrap(True)
        block.addWidget(self.now_status)
        self.player_status = QLabel()
        self.player_status.setWordWrap(True)
        block.addWidget(self.player_status)
        outer.addWidget(now)
        self.players_found.connect(self._populate_players)

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
        self.clear_button.clicked.connect(self._clear)
        row.addWidget(self.local_button)
        row.addWidget(self.clear_button)
        block.addLayout(row)
        self.pending_list = QListWidget()
        self.pending_list.setAccessibleName("Audio pendiente en la cola del bot")
        self.pending_list.setMaximumHeight(100)
        self.pending_list.itemSelectionChanged.connect(self._queue_buttons)
        delete_shortcut(self.pending_list, self._remove_pending)
        block.addWidget(self.pending_list)
        self.remove_button = QPushButton("Quitar seleccionado de la cola")
        self.remove_button.clicked.connect(self._remove_pending)
        block.addWidget(self.remove_button, alignment=Qt.AlignmentFlag.AlignLeft)
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
        self._populate_players(None)
        self.refresh()

    def refresh(self):
        if self.player.count():
            self.save_player.setEnabled(not self._pending and
                                        (not self.share_now.isChecked() or bool(self.player.currentData())))
        selection = self.rt.now_playing.settings
        snapshot = self.rt.now_playing.snapshot()
        if not selection.enabled:
            self.now_status.setText("No se comparte información.")
        elif not snapshot["title"]:
            self.now_status.setText("Activado · esperando una pista del reproductor seleccionado.")
        else:
            label = "En pausa" if snapshot["state"] == "paused" else "Reproduciendo"
            artist = f' · {snapshot["artist"]}' if snapshot["artist"] else ""
            self.now_status.setText(f'{label}: {snapshot["title"]}{artist}')
        permitted = self.private.isChecked()
        self.connect.setEnabled(permitted and not self.spotify.busy and not self.spotify.connected)
        self.stop.setEnabled(self.spotify.busy or self.spotify.connected)
        self.add_spotify.setEnabled(permitted and self.spotify.connected and not self._pending)
        self.spotify_url.setEnabled(permitted and self.spotify.connected)
        self.url_button.setEnabled(self.licensed.isChecked() and not self._pending)
        self.local_button.setEnabled(self.licensed.isChecked() and not self._pending)
        self.spotify_status.setText(self.spotify.status)
        current = self.rt.music.current or "Sin reproducción activa"
        rows = self.rt.music.pending()
        if rows != self._queue_rows:
            selected = self.pending_list.currentItem()
            selected_id = selected.data(Qt.ItemDataRole.UserRole) if selected else None
            self.pending_list.clear()
            for ident, name in rows:
                item = QListWidgetItem(name)
                item.setData(Qt.ItemDataRole.UserRole, ident)
                self.pending_list.addItem(item)
                if ident == selected_id:
                    self.pending_list.setCurrentItem(item)
            self._queue_rows = rows
        self._queue_buttons()
        error = self.rt.music.last_error
        self.local_status.setText(f"{current} · {len(rows)} en cola" + (f" · {error}" if error else ""))

    def _populate_players(self, players):
        selected = self.player.currentData() or self.rt.now_playing.settings.source
        names = set(players or ())
        if selected and selected.startswith(MPRIS_PREFIX):
            names.add(selected)
        self.player.blockSignals(True)
        self.player.clear()
        self.player.addItem("Elige un reproductor…", "")
        self.player.addItem("Cola de audio de Streamer Linux Bot (mpv)", BOT_SOURCE)
        for name in sorted(names):
            label = name.removeprefix(MPRIS_PREFIX)
            if players is not None and name not in players:
                label += " (no detectado)"
            self.player.addItem(label, name)
        index = self.player.findData(selected)
        self.player.setCurrentIndex(max(index, 0))
        self.player.blockSignals(False)
        if players is not None:
            self.player_status.setText(
                "" if players else "No se detectaron reproductores externos. Reproduce algo en la misma sesión de Linux y vuelve a buscar."
            )
        self.find_players.setEnabled(True)
        self.refresh()

    def _search_players(self):
        self.find_players.setEnabled(False)
        self.player_status.setText("Buscando reproductores en esta sesión de Linux…")

        async def search():
            self.players_found.emit(await available_players())

        self.rt.submit(search())

    def _save_player(self):
        if self.save_player.isEnabled():
            self._operate(
                self.rt.configure_now_playing(self.share_now.isChecked(), self.player.currentData() or ""),
                "Preferencia de Ahora suena guardada.",
            )

    def _queue_buttons(self):
        self.remove_button.setEnabled(not self._pending and self.pending_list.currentItem() is not None
                                      and bool(self.pending_list.selectedItems()))
        self.clear_button.setEnabled(not self._pending and bool(self._queue_rows or self.rt.music.current))

    def _remove_pending(self):
        item = self.pending_list.currentItem()
        if not item or not self.remove_button.isEnabled():
            return
        ident = item.data(Qt.ItemDataRole.UserRole)
        if confirm_delete(self, "Quitar audio de la cola", f"¿Quitar «{item.text()}» de la cola? No se borrará el archivo."):
            self._operate(self.rt.music.remove(ident), "Audio quitado de la cola.")

    def _clear(self):
        if self.clear_button.isEnabled() and confirm_delete(
                self, "Detener y vaciar la cola",
                "¿Detener la reproducción y quitar todos los audios pendientes? No se borrarán archivos."):
            self._operate(self.rt.music.clear(), "Cola de audio vacía.")

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
