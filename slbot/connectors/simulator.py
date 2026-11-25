"""Eventos de prueba para probar triggers y overlays sin estar en directo."""
from __future__ import annotations

from ..core.events import Event


def sample_event(kind: str) -> Event:
    kind = kind.lower()
    if kind == "gift":
        return Event("tiktok", "gift", "viewer_demo", {"gift_name": "Rose", "count": 3, "value": 3})
    if kind == "follow":
        return Event("twitch", "follow", "viewer_demo", {})
    if kind == "donation":
        return Event(
            "twitch", "donation", "viewer_demo",
            {"amount": 5.0, "currency": "USD", "value": 5.0, "text": "¡Buen stream!"},
        )
    if kind == "chat":
        return Event("twitch", "chat", "viewer_demo", {"text": "Hola a todos"})
    raise ValueError(f"Evento de prueba desconocido: {kind}")


SAMPLE_KINDS = ("gift", "follow", "donation", "chat")
