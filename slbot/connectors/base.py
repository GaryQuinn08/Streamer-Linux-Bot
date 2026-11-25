"""Interfaz común de los conectores.

Hay dos tipos:
  - "platform":    reciben eventos (Twitch, YouTube, Kick, TikTok) y los publican
                   en el bus como `Event`.
  - "broadcaster": programas que la app controla (OBS, y más adelante Streamlabs,
                   Meld Studio, PolyPop).
"""
from __future__ import annotations

import abc
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..runtime import Runtime


class Connector(abc.ABC):
    name: str = ""
    kind: str = "platform"  # "platform" | "broadcaster"

    def __init__(self, rt: "Runtime") -> None:
        self.rt = rt
        self.status = "desconectado"

    @abc.abstractmethod
    async def start(self) -> None:
        """Conecta y empieza a trabajar. Debe actualizar `self.status`."""

    async def stop(self) -> None:
        """Desconecta y libera recursos."""
        self.status = "desconectado"
