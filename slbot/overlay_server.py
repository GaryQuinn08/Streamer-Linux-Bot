"""Servidor local (aiohttp) para los overlays y el WebSocket de eventos.

OBS carga cada overlay como "Fuente de navegador" apuntando a:
    http://127.0.0.1:PUERTO/overlay/<id>/?parametro=valor

Seguridad: solo escucha en 127.0.0.1 y rechaza peticiones cuyo Origin o Host
no sean locales. La simulación existe solo en los controles nativos.
"""
from __future__ import annotations

import asyncio
import html
import json
from typing import TYPE_CHECKING, Any
from urllib.parse import quote, urlsplit

from aiohttp import web

from .core.events import Event
from .overlay_manager import find_overlay, list_overlays
from .paths import SDK_DIR

if TYPE_CHECKING:
    from .runtime import Runtime

LOCAL_HOSTS = {"127.0.0.1", "localhost"}
FEED_FIELDS = {
    "chat": ("text",),
    "gift": ("gift_name", "count"),
    "donation": ("amount", "currency"),
}
NO_STORE = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}


class OverlayServer:
    def __init__(self, rt: "Runtime") -> None:
        self.rt = rt
        self.clients: dict[web.WebSocketResponse, str] = {}
        self.port: int | None = None
        self._runner: web.AppRunner | None = None

    # -- ciclo de vida -----------------------------------------------------

    async def start(self, port: int) -> None:
        app = web.Application(middlewares=[self._local_only])
        app.add_routes(
            [
                web.get("/", self._index),
                web.get("/ws/{id}", self._ws),
                web.get("/sdk/overlay-sdk.js", self._sdk),
                web.get("/api/overlays", self._api_overlays),
                web.get("/overlay/{id}", self._redirect_slash),
                web.get("/overlay/{id}/", self._overlay_file),
                web.get("/overlay/{id}/{path:.+}", self._overlay_file),
            ]
        )
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, "127.0.0.1", port)
        await site.start()
        self.port = self._runner.addresses[0][1]

    async def stop(self) -> None:
        for ws in list(self.clients):
            await ws.close()
        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None

    # -- difusión a overlays ----------------------------------------------

    async def broadcast(self, overlay_id: str, message: dict[str, Any]) -> None:
        clients = [ws for ws, subscribed in self.clients.items() if subscribed == overlay_id]
        payload = json.dumps(message, ensure_ascii=False)
        results = await asyncio.gather(
            *(ws.send_str(payload) for ws in clients), return_exceptions=True
        )
        for ws, result in zip(clients, results):
            if isinstance(result, Exception):
                self.clients.pop(ws, None)

    async def forward_event(self, ev: Event) -> None:
        # Solo el feed integrado usa actividad de plataforma. Proyecta los
        # campos de presentación, no el payload completo del conector.
        data = {
            key: ev.data[key]
            for key in FEED_FIELDS.get(ev.type, ())
            if key in ev.data and isinstance(ev.data[key], (str, int, float))
        }
        await self.broadcast("event-feed", {
            "channel": "event", "platform": ev.platform, "type": ev.type,
            "user": ev.user, "ts": ev.ts, "data": data,
        })

    # -- middleware --------------------------------------------------------

    @web.middleware
    async def _local_only(self, request: web.Request, handler):
        origin = request.headers.get("Origin")
        if origin and urlsplit(origin).hostname not in LOCAL_HOSTS:
            return web.Response(status=403, text="Origin no permitido")
        if request.host.split(":")[0] not in LOCAL_HOSTS:
            return web.Response(status=403, text="Host no permitido")
        return await handler(request)

    # -- rutas -------------------------------------------------------------

    async def _index(self, request: web.Request) -> web.Response:
        rows = "".join(
            f'<li><a href="/overlay/{quote(o.id)}/">{html.escape(o.name)}</a> '
            f"<small>({html.escape(o.id)})</small></li>"
            for o in list_overlays().values()
        )
        body = f"<!doctype html><meta charset='utf-8'><title>Streamer Linux Bot</title><h1>Overlays</h1><ul>{rows}</ul>"
        return web.Response(text=body, content_type="text/html", headers=NO_STORE)

    async def _sdk(self, request: web.Request) -> web.FileResponse:
        return web.FileResponse(SDK_DIR / "overlay-sdk.js", headers=NO_STORE)

    async def _ws(self, request: web.Request) -> web.WebSocketResponse:
        overlay_id = request.match_info["id"]
        if find_overlay(overlay_id) is None:
            raise web.HTTPNotFound()
        ws = web.WebSocketResponse(heartbeat=30, max_msg_size=64 * 1024)
        await ws.prepare(request)
        self.clients[ws] = overlay_id
        try:
            await ws.send_str(json.dumps({"channel": "system", "type": "hello"}))
            async for _ in ws:  # los overlays solo escuchan; se ignora lo que envíen
                pass
        finally:
            self.clients.pop(ws, None)
        return ws

    async def _api_overlays(self, request: web.Request) -> web.Response:
        return web.json_response([o.to_dict() for o in list_overlays().values()], headers=NO_STORE)

    async def _redirect_slash(self, request: web.Request) -> web.Response:
        target = f"/overlay/{quote(request.match_info['id'])}/"
        if request.query_string:
            target += "?" + request.query_string
        raise web.HTTPFound(target)

    async def _overlay_file(self, request: web.Request) -> web.StreamResponse:
        info = find_overlay(request.match_info["id"])
        if info is None:
            raise web.HTTPNotFound()
        rel = request.match_info.get("path") or "index.html"
        target = (info.path / rel).resolve()
        if not target.is_relative_to(info.path) or not target.is_file():
            raise web.HTTPNotFound()
        return web.FileResponse(target, headers=NO_STORE)
