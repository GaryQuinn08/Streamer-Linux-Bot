"""Conectores de plataforma (por implementar).

Cada uno debe leer los eventos de su plataforma y publicarlos con:

    await self.rt.bus.publish(Event("twitch", "follow", user, {...}))

Plan por plataforma:
  - Twitch:  EventSub por WebSocket + inicio de sesión OAuth del propio usuario.
  - YouTube: API de YouTube Live Chat + OAuth de Google.
  - Kick:    API pública de Kick (aún cambia con frecuencia).
"""
from __future__ import annotations

from .base import Connector


class _PendingConnector(Connector):
    kind = "platform"

    def __init__(self, rt) -> None:
        super().__init__(rt)
        self.status = "pendiente de implementar"

    async def start(self) -> None:
        self.status = "pendiente de implementar"
        self.rt.log(f"{self.name}: conector aún no implementado")


class TwitchConnector(_PendingConnector):
    name = "twitch"


class YoutubeConnector(_PendingConnector):
    name = "youtube"


class KickConnector(_PendingConnector):
    name = "kick"
