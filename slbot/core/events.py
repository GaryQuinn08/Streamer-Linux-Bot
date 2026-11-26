"""Evento normalizado y bus de eventos.

Todos los conectores (Twitch, YouTube, Kick, TikTok...) traducen lo que reciben
a un `Event`. Así un trigger o un overlay reacciona igual sin importar de qué
plataforma venga el evento.

Tipos de evento previstos (`type`):
    chat, command, follow, sub, gift, donation, bits, points, raid, like, share

Campos habituales en `data`:
    text, command, gift_name, count, value, amount, currency
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

log = logging.getLogger("slb.events")


@dataclass
class Event:
    platform: str  # twitch | youtube | kick | tiktok | system
    type: str
    user: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    ts: float = field(default_factory=time.time)
    actor_id: str = ""  # interno: no se envía a overlays ni templates
    chat_role: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "platform": self.platform,
            "type": self.type,
            "user": self.user,
            "data": self.data,
            "ts": self.ts,
        }


Subscriber = Callable[[Event], Awaitable[None] | None]


class EventBus:
    def __init__(self) -> None:
        self._subscribers: list[Subscriber] = []

    def subscribe(self, fn: Subscriber) -> None:
        self._subscribers.append(fn)

    async def publish(self, event: Event) -> None:
        for fn in list(self._subscribers):
            try:
                result = fn(event)
                if asyncio.iscoroutine(result):
                    await result
            except Exception:  # un suscriptor roto no debe tumbar a los demás
                log.exception("Error en un suscriptor del bus de eventos")
