"""Conector de OBS Studio por obs-websocket (incluido en OBS 28 o superior).

Activa el servidor en OBS: Herramientas -> Ajustes del servidor WebSocket.
NOTA: esta parte no se ha podido probar contra un OBS real en el desarrollo
inicial; si algún método falla, el error aparece en el Registro.
"""
from __future__ import annotations

import asyncio
from typing import Any

from .base import Connector


class ObsConnector(Connector):
    name = "obs"
    kind = "broadcaster"

    def __init__(self, rt) -> None:
        super().__init__(rt)
        self._client: Any = None

    async def start(self) -> None:
        cfg = self.rt.config.settings["obs"]
        self.status = "conectando..."

        def _connect() -> Any:
            import obsws_python as obs

            return obs.ReqClient(
                host=str(cfg["host"]),
                port=int(cfg["port"]),
                password=str(cfg.get("password", "")),
                timeout=5,
            )

        try:
            self._client = await asyncio.to_thread(_connect)
            self.status = "conectado"
            self.rt.log(f"OBS conectado en {cfg['host']}:{cfg['port']}")
        except Exception as exc:
            self._client = None
            self.status = "error"
            self.rt.log(f"OBS: no se pudo conectar ({exc})")

    async def stop(self) -> None:
        client, self._client = self._client, None
        if client is not None:
            try:
                await asyncio.to_thread(client.disconnect)
            except Exception:
                pass
        self.status = "desconectado"

    def _require(self) -> Any:
        if self._client is None:
            raise RuntimeError("OBS no está conectado")
        return self._client

    async def set_scene(self, scene: str) -> None:
        client = self._require()
        await asyncio.to_thread(client.set_current_program_scene, scene)

    async def set_source_visible(self, scene: str, source: str, visible: bool) -> None:
        client = self._require()

        def _apply() -> None:
            item = client.get_scene_item_id(scene, source)
            client.set_scene_item_enabled(scene, item.scene_item_id, visible)

        await asyncio.to_thread(_apply)
