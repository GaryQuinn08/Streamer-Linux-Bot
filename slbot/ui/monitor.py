"""Vistas de sesión del chat y del historial de acciones."""
from __future__ import annotations

import time

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ..connectors.simulator import sample_event
from .rule_editor import ActionWorkspace


def _clock(at):
    return time.strftime("%H:%M:%S", time.localtime(at))


class SessionPanel(QWidget):
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
        controls.addStretch(1)
        layout.addLayout(controls)
        headers = ("Hora", "Plataforma", "Usuario", "Mensaje") if chat else (
            "Hora", "Acción", "Origen", "Evento", "Estado", "Tiempo")
        self.table = ActionWorkspace._table(headers, "chat-monitor" if chat else "action-history",
                                            stretch=3 if chat else 1)
        layout.addWidget(self.table)
        self.notice = QLabel()
        self.notice.setWordWrap(True)
        layout.addWidget(self.notice)
        timer = QTimer(self)
        timer.timeout.connect(self._update_if_visible)
        timer.start(300)

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh()

    def _update_if_visible(self):
        if self.isVisible():
            self.refresh()

    def refresh(self, *_):
        selected = self.platform.currentData()
        items = self.rt.chat_snapshot() if self.chat else self.rt.action_snapshot()
        items = tuple(item for item in items if selected is None or item.platform == selected)
        if items == self._last:
            return
        self._last = items
        if self.chat:
            rows = [(_clock(line.at), line.platform + (" · prueba" if line.simulated else ""),
                     line.user, line.text) for line in reversed(items)]
            text = ("Solo lectura. Los mensajes reales llegan de las plataformas conectadas; "
                    "las pruebas se identifican en la lista. El chat no se guarda al cerrar.")
        else:
            rows = [(_clock(run.at), run.action, run.origin, f"{run.platform}/{run.event}",
                     run.state + (f" ({run.failures})" if run.failures else ""),
                     "…" if run.duration_ms is None else f"{run.duration_ms} ms")
                    for run in sorted(items, key=lambda run: run.id, reverse=True)]
            text = "El historial se conserva durante esta sesión. Consulta Registro para ver el detalle de un error."
        self.notice.setText(text if rows else "Todavía no hay resultados para este filtro. " + text)
        ActionWorkspace._fill(self.table, rows, tooltips=False)
