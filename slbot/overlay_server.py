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
import re
from typing import TYPE_CHECKING, Any
from urllib.parse import quote, urlsplit

from aiohttp import web

from .chat_dock import ChatDock, load_key
from .core.events import Event
from .now_playing import clean_metadata
from .overlay_manager import find_overlay, list_overlays, validate_overlay_values
from .paths import SDK_DIR, config_dir

if TYPE_CHECKING:
    from .runtime import Runtime

LOCAL_HOSTS = {"127.0.0.1", "localhost"}
CHAT_PLATFORMS = ("twitch", "youtube", "kick", "tiktok")
MUSIC_REPORT_PATH = "/api/music/browser"
_EXTENSION_ORIGIN = re.compile(r"chrome-extension://[a-p]{32}\Z")
NOW_PLAYING_IDS = ("now-playing", "now-playing-spectrum")
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
        self._chat_dock = ChatDock()
        self.port: int | None = None
        self._runner: web.AppRunner | None = None

    @property
    def chat_dock_path(self) -> str | None:
        return self._chat_dock.path if self.port is not None else None

    # -- ciclo de vida -----------------------------------------------------

    async def start(self, port: int) -> None:
        app = web.Application(middlewares=[self._local_only])
        app.add_routes(
            [
                web.get("/", self._index),
                web.get("/ws/{id}", self._ws),
                web.get("/sdk/overlay-sdk.js", self._sdk),
                web.get(r"/sdk/{asset:now-playing\.(?:css|js)}", self._now_playing_asset),
                web.get("/api/overlays", self._api_overlays),
                web.post(MUSIC_REPORT_PATH, self._music_browser),
                web.get("/overlay/{id}", self._redirect_slash),
                web.get("/overlay/{id}/", self._overlay_file),
                web.get("/overlay/{id}/{path:.+}", self._overlay_file),
                *self._chat_dock.routes(),
            ]
        )
        # Dock URLs contain a private capability and must not appear in access logs.
        runner = web.AppRunner(app, shutdown_timeout=2, access_log=None)
        try:
            await runner.setup()
            await web.TCPSite(runner, "127.0.0.1", port).start()
        except BaseException:
            await runner.cleanup()
            raise
        self._runner = runner
        self.port = runner.addresses[0][1]
        try:
            path = self.rt.config.path
            self._chat_dock.token = load_key(path.parent if path else config_dir())
        except (OSError, ValueError):
            self.rt.log("No se pudo habilitar el panel privado de chat: revisa los permisos del perfil.")

    async def stop(self) -> None:
        self.port = None
        await self._chat_dock.stop()
        await asyncio.gather(*(ws.close(drain=False) for ws in list(self.clients)),
                             return_exceptions=True)
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

    def _now_playing_message(self) -> dict[str, str]:
        service = getattr(self.rt, "now_playing", None)
        snapshot = service.snapshot() if service is not None else {}
        title = clean_metadata(snapshot.get("title"), 110)
        state = snapshot.get("state")
        if state not in ("playing", "paused") or not title:
            return {"channel": "now-playing", "state": "idle", "title": "", "artist": ""}
        return {"channel": "now-playing", "state": state, "title": title,
                "artist": clean_metadata(snapshot.get("artist"), 90)}

    async def broadcast_now_playing(self) -> None:
        message = self._now_playing_message()
        await asyncio.gather(*(self.broadcast(overlay, message) for overlay in NOW_PLAYING_IDS))

    def _now_playing_settings(self, overlay_id: str) -> dict:
        info = find_overlay(overlay_id)
        raw = self.rt.config.settings.get("overlay_presets", {})
        saved = raw.get(overlay_id, {}) if isinstance(raw, dict) else {}
        values = {}
        if info is not None and isinstance(saved, dict):
            for key, value in saved.items():
                try:
                    values.update(validate_overlay_values(info, {key: value}))
                except (TypeError, ValueError):
                    continue
        return {"channel": "now-playing-settings", "values": values}

    async def broadcast_now_playing_settings(self, overlay_id: str) -> None:
        if overlay_id in NOW_PLAYING_IDS:
            await self.broadcast(overlay_id, self._now_playing_settings(overlay_id))

    async def preview_now_playing(self, overlay_id: str) -> None:
        if overlay_id in NOW_PLAYING_IDS:
            await self.broadcast(overlay_id, {"channel": "now-playing-preview", "state": "playing",
                                 "title": "Órbita de medianoche", "artist": "Luna Vector"})

    async def _now_playing_asset(self, request: web.Request) -> web.StreamResponse:
        return web.FileResponse(SDK_DIR / request.match_info["asset"], headers=NO_STORE)

    async def forward_event(self, ev: Event) -> None:
        # Los overlays integrados reciben solo campos de presentación.
        data = {
            key: ev.data[key]
            for key in FEED_FIELDS.get(ev.type, ())
            if key in ev.data and isinstance(ev.data[key], (str, int, float))
        }
        await self.broadcast("event-feed", {
            "channel": "event", "platform": ev.platform, "type": ev.type,
            "user": ev.user, "ts": ev.ts, "data": data,
        })
        await self.forward_chat(ev)

    async def forward_chat(self, ev: Event) -> None:
        text = ev.data.get("text")
        if (ev.type != "chat" or ev.platform not in CHAT_PLATFORMS
                or not isinstance(text, str) or not text.strip()):
            return
        message = {
            "channel": "chat", "platform": ev.platform,
            "user": ev.user[:100] if isinstance(ev.user, str) else "",
            "text": text[:500], "simulated": ev.data.get("simulated") is True,
        }
        await asyncio.gather(self.broadcast("multi-chat", message), self._chat_dock.broadcast(message))

    # -- middleware --------------------------------------------------------

    @web.middleware
    async def _local_only(self, request: web.Request, handler):
        origin = request.headers.get("Origin")
        if origin and urlsplit(origin).hostname not in LOCAL_HOSTS:
            if not (request.path == MUSIC_REPORT_PATH and request.method == "POST"
                    and _EXTENSION_ORIGIN.fullmatch(origin)):
                return web.Response(status=403, text="Origin no permitido")
        if request.host.split(":")[0] not in LOCAL_HOSTS:
            return web.Response(status=403, text="Host no permitido")
        return await handler(request)

    # -- rutas -------------------------------------------------------------

    async def _music_browser(self, request: web.Request) -> web.Response:
        service = self.rt.now_playing
        authorization = request.headers.get("Authorization", "")
        if not service.authorizes(authorization):
            return web.Response(status=403, headers=NO_STORE)
        if request.content_type != "application/json" or request.content_length is None:
            return web.Response(status=400, headers=NO_STORE)
        if request.content_length > 4096:
            return web.Response(status=413, headers=NO_STORE)
        try:
            async with asyncio.timeout(2):
                body = await request.json()
        except (ValueError, TimeoutError, RecursionError):
            return web.Response(status=400, headers=NO_STORE)
        if not isinstance(body, dict) or not await service.receive_browser(body, authorization):
            return web.Response(status=400, headers=NO_STORE)
        return web.Response(status=204, headers=NO_STORE)

    async def _index(self, request: web.Request) -> web.Response:
        rows = "".join(
            f'<li><a href="/overlay/{quote(o.id)}/">{html.escape(o.name)}</a> '
            f"<small>({html.escape(o.id)})</small><p>{html.escape(o.description)}</p></li>"
            for o in list_overlays().values()
        )
        body = (
            "<!doctype html><html lang='es'><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width, initial-scale=1'>"
            "<title>Streamer Linux Bot</title><style>"
            "body{font:1rem system-ui;max-width:45rem;margin:3rem auto;padding:0 1rem;"
            "background:#171b26;color:#f2f4fb}a{color:#9bd2ff}ul{padding:0;list-style:none}"
            "li{padding:1rem;background:#242b3c;border-radius:.5rem;margin:.6rem 0}"
            "li p{margin:.5rem 0 0;color:#c7cedf}</style>"
            "<h1>Overlays y alertas</h1><p>Abre una alerta para obtener la URL de OBS o LIVE Studio. "
            "Para personalizar, crear o importar, usa la pestaña Overlays de la aplicación.</p>"
            f"<ul>{rows}</ul></html>"
        )
        return web.Response(text=body, content_type="text/html", headers=NO_STORE)

    async def _sdk(self, request: web.Request) -> web.Response:
        raw = self.rt.config.settings.get("overlay_presets", {})
        presets = raw if isinstance(raw, dict) else {}
        values = {key: value for key, value in presets.items() if isinstance(value, dict)}
        sdk = (SDK_DIR / "overlay-sdk.js").read_text(encoding="utf-8")
        script = sdk.replace("/* SLB_PRESETS */ {}", json.dumps(values, ensure_ascii=True), 1)
        return web.Response(text=script, content_type="application/javascript", headers=NO_STORE)

    async def _ws(self, request: web.Request) -> web.WebSocketResponse:
        overlay_id = request.match_info["id"]
        if find_overlay(overlay_id) is None:
            raise web.HTTPNotFound()
        ws = web.WebSocketResponse(heartbeat=30, max_msg_size=64 * 1024)
        await ws.prepare(request)
        self.clients[ws] = overlay_id
        try:
            await ws.send_str(json.dumps({"channel": "system", "type": "hello"}))
            if overlay_id == "live-goal":
                await ws.send_str(json.dumps({"channel": "goal", "counts": self.rt.goal_counts}))
            elif overlay_id == "multi-chat":
                presets = self.rt.config.settings.get("overlay_presets", {})
                values = presets.get(overlay_id, {}) if isinstance(presets, dict) else {}
                await ws.send_str(json.dumps({
                    "channel": "chat-settings", "values": values if isinstance(values, dict) else {},
                }))
            elif overlay_id in NOW_PLAYING_IDS:
                await ws.send_json(self._now_playing_settings(overlay_id))
                await ws.send_json(self._now_playing_message())
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
        if rel == "index.html" and info.appearance:
            raw = self.rt.config.settings.get("overlay_presets", {})
            saved = raw.get(info.id, {}) if isinstance(raw, dict) else {}
            if isinstance(saved, dict) and saved:
                checked = {}
                for key, value in saved.items():
                    try:
                        checked.update(validate_overlay_values(info, {key: value}))
                    except (ValueError, TypeError):
                        continue
                if checked:
                    body = info.appearance.render(info.path, checked)
                    return web.Response(text=body, content_type="text/html", headers=NO_STORE)
            upgraded = info.appearance.refresh_live(info.path)
            if upgraded is not None:
                return web.Response(text=upgraded, content_type="text/html", headers=NO_STORE)
        return web.FileResponse(target, headers=NO_STORE)
