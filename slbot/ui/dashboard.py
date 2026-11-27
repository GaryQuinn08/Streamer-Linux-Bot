"""Inicio para monitorear el directo, sin iniciar sesión ni emitir por sí solo."""
from __future__ import annotations

import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from ..dashboard import PLATFORMS

COLORS = {"twitch": "#bf9aff", "tiktok": "#61e5d5", "youtube": "#ffa3a8", "kick": "#a9e77c"}
BREAKDOWN = {
    "twitch": (("chat", "mensajes"), ("follow", "seguidores"), ("sub", "subs"),
               ("bits_value", "bits"), ("points", "canjes")),
    "tiktok": (("chat", "mensajes"), ("follow", "seguidores"), ("gift_units", "regalos"),
               ("gift_value", "diamantes informados"), ("like_units", "me gusta"),
               ("share", "compartidos"), ("sub", "subs")),
    "youtube": (("chat", "mensajes"), ("sub", "miembros nuevos"), ("donation", "Super Chats / Stickers")),
    "kick": (("chat", "mensajes"), ("follow", "seguidores"), ("sub", "eventos de sub"), ("gift_value", "Kicks")),
}
STYLES = """
QFrame[dashTile="true"] { background: #1a222e; border: 1px solid #39485a; border-radius: 9px; }
QFrame#dashOverview { background: #172d30; border: 1px solid #416d65; border-radius: 10px; }
QFrame[dashTile="true"] QLabel, QFrame#dashOverview QLabel { background: transparent; border: none; }
QLabel[dashMuted="true"] { color: #b6c4d5; }
QLabel[dashKpi="true"] { color: #ecf7f3; font-size: 24px; font-weight: 700; }
QLabel[dashSection="true"] { color: #d7e1ed; font-size: 13px; font-weight: 700; }
"""


def _caption(value="", *, muted=False):
    label = QLabel(value)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(True)
    label.setProperty("dashMuted", muted)
    return label


def _clock(value):
    return time.strftime("%H:%M:%S", time.localtime(value))


def _units(value):
    return "—" if value is None else f"{value:,}"


def _duration(started):
    if started is None:
        return ""
    seconds = max(0, int(time.time() - started))
    return f"{seconds // 3600:02d}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"


def _connection(status):
    if status.startswith(("conectado", "escuchando", "autorizado; esperando", "autorizado; el directo", "canal sin directo; esperando")):
        return "#8ae7bb"
    if status == "desconectado" or status.startswith("canal sin directo"):
        return "#b6c4d5"
    if "conectando" in status or status.startswith("autoriza en"):
        return "#f4d28f"
    return "#ffa8ac"


class _PlatformCard(QFrame):
    def __init__(self, key, title, connect):
        super().__init__()
        self.setObjectName("dashboard-" + key)
        self.setProperty("dashTile", True)
        self.key = key
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 9, 12, 9)
        layout.setSpacing(4)
        top = QHBoxLayout()
        service = _caption(title)
        service.setStyleSheet(f"font-weight: 700; font-size: 16px; color: {COLORS[key]}")
        top.addWidget(service, 1)
        self.live_flag = _caption()
        top.addWidget(self.live_flag)
        layout.addLayout(top)
        self.link_status = _caption(muted=True)
        layout.addWidget(self.link_status)
        self.title = _caption()
        layout.addWidget(self.title)
        self.audience = _caption()
        layout.addWidget(self.audience)
        self.totals = _caption(muted=True)
        layout.addWidget(self.totals)
        self.detail = _caption(muted=True)
        layout.addWidget(self.detail)
        layout.addStretch(1)
        button = QPushButton("Ir al receptor" if key == "kick" else "Ir a la conexión")
        button.setObjectName("dashboard-connect-" + key)
        button.clicked.connect(lambda: connect(key))
        layout.addWidget(button, 0, Qt.AlignmentFlag.AlignLeft)

    def update_data(self, state, connector):
        status = connector.status
        color = "#8ae7bb" if state.live is True else "#b4c1d1"
        self.live_flag.setStyleSheet(f"font-weight: 700; color: {color}")
        self.live_flag.setText("EN DIRECTO" if state.live is True else "FUERA DE DIRECTO" if state.live is False
                               else "SIN CONFIRMAR")
        self.link_status.setStyleSheet(f"color: {_connection(status)}")
        self.link_status.setText("Conector: " + status[:160])
        context = " · ".join(v for v in (state.identity, state.title, _duration(state.started_at)) if v)
        self.title.setVisible(bool(context))
        self.title.setText(context)
        self.audience.setText(f"Espectadores: {_units(state.viewers)}   ·   Pico observado: {_units(state.peak)}")
        totals = dict(state.totals)
        parts = [f"{_units(totals.get(kind, 0))} {label}"
                 for kind, label in BREAKDOWN[self.key]
                 if kind != "gift_value" or kind in totals]
        self.totals.setText(" · ".join(parts) + ("\n" + " · ".join(
            f"{format(value, 'f')} {currency}" for currency, value in state.currencies) if state.currencies else ""))
        details = []
        if state.last_event:
            details.append("Última señal: " + _clock(state.last_event))
        elif status.startswith("escuchando"):
            details.append("Aún no llegó un evento firmado.")
        elif "TikFinity" in status:
            details.append("Puente abierto; esperando datos de sala.")
        elif status.startswith("conectado"):
            details.append("Todavía no llegaron interacciones.")
        if state.live_at is not None:
            details.append("Estado consultado: " + _clock(state.live_at))
        if state.note:
            details.append(state.note)
        if getattr(connector, "feed_detail", "") and status.startswith("conectado"):
            details.append(connector.feed_detail)
        self.detail.setText(" · ".join(details))
        self.detail.setVisible(bool(details))


class DashboardPage(QWidget):
    def __init__(self, runtime, jump, connect):
        super().__init__()
        self.rt = runtime
        self.setStyleSheet(STYLES)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        outer.addWidget(scroll)
        body = QWidget()
        scroll.setWidget(body)
        layout = QVBoxLayout(body)
        layout.setContentsMargins(1, 1, 8, 8)
        layout.setSpacing(10)

        hero = QFrame()
        hero.setObjectName("dashOverview")
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(14, 10, 14, 10)
        overview = QGridLayout()
        self.summary = {}
        for i, (key, label) in enumerate((
            ("live", "En directo confirmado"), ("links", "Conectores activos"), ("chat", "Mensajes recibidos"),
        )):
            value = _caption()
            value.setProperty("dashKpi", True)
            value.setObjectName("dashboard-kpi-" + key)
            self.summary[key] = value
            overview.addWidget(value, 0, i)
            overview.addWidget(_caption(label, muted=True), 1, i)
            overview.setColumnStretch(i, 1)
        hero_layout.addLayout(overview)
        self.obs_status = _caption(muted=True)
        self.obs_status.setObjectName("dashboard-obs")
        hero_layout.addWidget(self.obs_status)
        layout.addWidget(hero)

        quick = QFrame()
        quick.setProperty("dashTile", True)
        shortcuts = QGridLayout(quick)
        shortcuts.setContentsMargins(12, 8, 12, 8)
        title = _caption("Accesos rápidos")
        title.setProperty("dashSection", True)
        shortcuts.addWidget(title, 0, 0, 1, 3)
        for i, (dest, caption) in enumerate((
            ("connections", "Conexiones"), ("chat", "Chat y voz (TTS)"), ("actions", "Acciones y sonidos"),
            ("overlays", "Overlays"), ("music", "Música"), ("log", "Registro"),
        )):
            button = QPushButton(caption)
            button.setObjectName("dashboard-open-" + dest)
            button.clicked.connect(lambda _checked=False, target=dest: jump(target))
            shortcuts.addWidget(button, 1 + i // 3, i % 3)
        self.quick_state = _caption(muted=True)
        shortcuts.addWidget(self.quick_state, 3, 0, 1, 3)
        layout.addWidget(quick)

        section = _caption("Estado por plataforma")
        section.setProperty("dashSection", True)
        layout.addWidget(section)
        layout.addWidget(_caption("Los contadores solo incluyen eventos recibidos desde que abriste el bot, no tu historial "
                                  "ni las simulaciones. «—» indica un dato que no está disponible.", muted=True))
        cards = QGridLayout()
        self.cards = {}
        for i, (key, title) in enumerate(PLATFORMS.items()):
            card = _PlatformCard(key, title, connect)
            cards.addWidget(card, i // 2, i % 2)
            self.cards[key] = card
        cards.setColumnStretch(0, 1)
        cards.setColumnStretch(1, 1)
        layout.addLayout(cards)
        layout.addStretch(1)

        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.refresh)
        self.refresh()

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh()
        self.timer.start()

    def hideEvent(self, event):
        self.timer.stop()
        super().hideEvent(event)

    def refresh(self):
        states = self.rt.dashboard.snapshot()
        live = connected = messages = 0
        for key, card in self.cards.items():
            connector, state = self.rt.connectors[key], states[key]
            card.update_data(state, connector)
            live += state.live is True
            connected += connector.status.startswith(("conectado", "escuchando", "autorizado; esperando",
                                                      "autorizado; el directo", "canal sin directo; esperando"))
            messages += dict(state.totals).get("chat", 0)
        for key, value in (("live", live), ("links", f"{connected}/4"), ("chat", _units(messages))):
            self.summary[key].setText(str(value))
        state = states["obs"]
        obs = self.rt.obs.status
        if state.live is True:
            obs = f"emitiendo{(' · ' + _duration(state.started_at)) if state.started_at else ''}"
        elif state.live is False:
            obs = "conectado · sin emitir"
        if state.note:
            obs += " · " + state.note
        overlay = f"activo ({len(self.rt.overlays.clients)} fuentes abiertas)" if self.rt.port is not None else "inactivo"
        self.obs_status.setText(f"OBS: {obs}  |  Servidor de overlays: {overlay}")
        tts = "activa" if self.rt.chat_tts.settings.enabled else "apagada"
        active = [trigger for trigger in self.rt.config.triggers if trigger.enabled]
        self.quick_state.setText(f"Lectura de chat: {tts}  ·  Disparadores activos: {len(active)}  ·  "
                                 f"Audios en cola: {len(self.rt.music.pending())}")
