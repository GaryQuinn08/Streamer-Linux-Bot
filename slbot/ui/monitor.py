"""Vistas de sesión del chat y del historial de acciones."""
from __future__ import annotations

import time

from PySide6.QtCore import QTimer, Qt, Signal, Slot
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget

from ..connectors.oauth import SignInError
from ..connectors.simulator import sample_event
from ..core.action_queue import ACTIVE_STATES
from .chat_speech import ChatSpeechPanel
from .rule_editor import ActionWorkspace


def _clock(at):
    return time.strftime("%H:%M:%S", time.localtime(at))


class SessionPanel(QWidget):
    send_finished = Signal(str)
    queue_finished = Signal(str)

    def __init__(self, runtime, *, chat):
        super().__init__()
        self.rt, self.chat, self._last = runtime, chat, None
        layout = QVBoxLayout(self)
        controls = QHBoxLayout()
        self.platform = QComboBox()
        self.platform.setAccessibleName("Filtrar por plataforma")
        self.platform.addItem("Todas las plataformas", None)
        for label, key in (("TikTok", "tiktok"), ("Twitch", "twitch"), ("YouTube", "youtube"),
                           ("Kick", "kick"), ("Sistema", "system")):
            self.platform.addItem(label, key)
        self.platform.currentIndexChanged.connect(self.refresh)
        controls.addWidget(self.platform)
        if chat:
            sample = QPushButton("Simular mensaje")
            sample.clicked.connect(lambda: self.rt.emit(sample_event("chat")))
            controls.addWidget(sample)
        else:
            self.pause_button = QPushButton("Pausar nuevas acciones")
            self.pause_button.clicked.connect(lambda: self._queue_request(
                self.rt.pause_actions(not self.rt.action_queue.paused)))
            self.cancel_button = QPushButton("Cancelar ejecución")
            self.cancel_button.clicked.connect(self._cancel_selected)
            self.cancel_button.setEnabled(False)
            controls.addWidget(self.pause_button)
            controls.addWidget(self.cancel_button)
            self.queue_finished.connect(self._queue_done, Qt.ConnectionType.QueuedConnection)
        controls.addStretch(1)
        layout.addLayout(controls)
        headers = ("Hora", "Plataforma", "Usuario", "Mensaje") if chat else (
            "Hora", "Acción", "Origen", "Evento", "Estado", "Tiempo", "Cola")
        self.table = ActionWorkspace._table(headers, "chat-monitor" if chat else "action-history",
                                            stretch=3 if chat else 1)
        layout.addWidget(self.table)
        if not chat:
            self._runs = ()
            self.table.itemSelectionChanged.connect(self._update_cancel_button)
            self.queue_result = QLabel()
            self.queue_result.setTextFormat(Qt.TextFormat.PlainText)
            self.queue_result.setWordWrap(True)
            layout.addWidget(self.queue_result)
        self.notice = QLabel()
        self.notice.setWordWrap(True)
        layout.addWidget(self.notice)
        if chat:
            self.speech = ChatSpeechPanel(runtime)
            layout.addWidget(self.speech)
            self._sending = False
            self.send_finished.connect(self._twitch_done, Qt.ConnectionType.QueuedConnection)
            composer = QHBoxLayout()
            self.twitch_message = QLineEdit()
            self.twitch_message.setMaxLength(500)
            self.twitch_message.setPlaceholderText("Mensaje para tu canal de Twitch")
            self.twitch_message.textChanged.connect(self._refresh_twitch)
            self.twitch_message.returnPressed.connect(self._send_to_twitch)
            composer.addWidget(self.twitch_message, 1)
            self.twitch_send = QPushButton("Enviar a Twitch")
            self.twitch_send.clicked.connect(self._send_to_twitch)
            composer.addWidget(self.twitch_send)
            layout.addLayout(composer)
            self.twitch_hint = QLabel()
            self.twitch_hint.setWordWrap(True)
            layout.addWidget(self.twitch_hint)
            self.send_result = QLabel()
            self.send_result.setTextFormat(Qt.TextFormat.PlainText)
            self.send_result.setWordWrap(True)
            layout.addWidget(self.send_result)
            self._refresh_twitch()
        timer = QTimer(self)
        timer.timeout.connect(self._update_if_visible)
        timer.start(300)

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh()

    def _update_if_visible(self):
        if self.isVisible():
            self.refresh()

    def _refresh_twitch(self, *_):
        enabled = self.rt.connectors["twitch"].can_send
        self.twitch_message.setEnabled(enabled and not self._sending)
        self.twitch_send.setEnabled(enabled and not self._sending and bool(self.twitch_message.text().strip()))
        message = ("Se publica desde tu cuenta. Si activaste Chat compartido, Twitch también lo muestra en los canales enlazados."
                   if enabled else "Para enviar, en Conexiones marca «Autorizar envío manual al chat de Twitch» antes de conectar.")
        if self.twitch_hint.text() != message:
            self.twitch_hint.setText(message)

    def _send_to_twitch(self):
        if not self.twitch_send.isEnabled():
            return
        message = self.twitch_message.text()
        self._sending = True
        self.send_result.setText("Enviando a Twitch…")
        self._refresh_twitch()
        notify = self.send_finished

        def finished(future):
            if future.cancelled():
                result = "Se canceló el envío. Revisa Twitch antes de reintentar."
            else:
                error = future.exception()
                result = str(error) if isinstance(error, SignInError) else (
                    "No se pudo confirmar el envío. Revisa Twitch antes de reintentar." if error else "")
            try:
                notify.emit(result)
            except RuntimeError:  # la ventana pudo cerrarse durante el envío
                pass

        self.rt.submit(self.rt.connectors["twitch"].send_chat(message)).add_done_callback(finished)

    @Slot(str)
    def _twitch_done(self, error):
        self._sending = False
        if not error:
            self.twitch_message.clear()
        self.send_result.setText(error or "Twitch confirmó el envío.")
        self._refresh_twitch()

    def _selected_run(self):
        row = self.table.currentRow()
        if self.table.selectedItems() and 0 <= row < len(self._runs):
            return self._runs[row]
        return None

    def _update_cancel_button(self):
        run = self._selected_run()
        self.cancel_button.setEnabled(run is not None and run.state in ACTIVE_STATES)

    def _cancel_selected(self):
        run = self._selected_run()
        if run is not None and run.state in ACTIVE_STATES:
            self._queue_request(self.rt.cancel_action(run.id))

    def _queue_request(self, coro):
        notify = self.queue_finished

        def finished(future):
            error = "Operación cancelada." if future.cancelled() else str(future.exception() or "")
            try:
                notify.emit(error)
            except RuntimeError:
                pass

        self.rt.submit(coro).add_done_callback(finished)

    @Slot(str)
    def _queue_done(self, error):
        self.queue_result.setText(error)
        self.refresh()

    def refresh(self, *_):
        if self.chat:
            self._refresh_twitch()
        else:
            paused = self.rt.action_queue.paused
            self.pause_button.setText("Reanudar acciones" if paused else "Pausar nuevas acciones")
        selected = self.platform.currentData()
        items = self.rt.chat_snapshot() if self.chat else self.rt.action_snapshot()
        items = tuple(item for item in items if selected is None or item.platform == selected)
        if items == self._last:
            return
        self._last = items
        if self.chat:
            rows = [(_clock(line.at), line.platform + (" · prueba" if line.simulated else ""),
                     line.user, line.text) for line in reversed(items)]
            text = ("Los mensajes llegan de las plataformas conectadas; "
                    "las pruebas se identifican en la lista. El chat no se guarda al cerrar. "
                    "Para mostrarlo en OBS, copia la URL en Overlays → Chat multiplataforma y marca "
                    "«Actualizar el navegador cuando la escena se active» en la fuente Navegador.")
        else:
            selected_run = self._selected_run()
            self._runs = tuple(sorted(items, key=lambda run: run.id, reverse=True))
            rows = [(_clock(run.at), run.action, run.origin, f"{run.platform}/{run.event}",
                     run.state + (f" ({run.failures})" if run.failures else ""),
                     "—" if run.duration_ms is None else f"{run.duration_ms} ms", run.queue or "Paralela") for run in self._runs]
            text = ("Pausar detiene el inicio de nuevas acciones, no las que ya empezaron. "
                    "Cancelar no deshace pasos ya ejecutados. Solo se conserva el historial de esta sesión.")
        self.notice.setText(text if rows else "Todavía no hay resultados para este filtro. " + text)
        selected_row = -1
        if not self.chat and selected_run is not None:
            selected_row = next((i for i, run in enumerate(self._runs) if run.id == selected_run.id), -1)
        ActionWorkspace._fill(self.table, rows, selected_row, tooltips=False)
        if not self.chat:
            self._update_cancel_button()
