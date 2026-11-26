"""Loopback-only, separately scoped OBS chat dock."""
from __future__ import annotations

import asyncio
import hmac
import json
import os
import re
import secrets
import stat
import tempfile
from pathlib import Path

from aiohttp import WSMsgType, WSCloseCode, web

from .paths import PACKAGE_DIR

ASSETS = PACKAGE_DIR / "overlays" / "dock"
KEY_NAME = "chat-dock.key"
TOKEN = re.compile(r"[A-Za-z0-9_-]{32}", re.ASCII)
HEADERS = {
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": (
        "default-src 'none'; script-src 'self'; style-src 'self'; "
        "connect-src 'self' ws://127.0.0.1:* ws://localhost:*; "
        "frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
    ),
}


def load_key(directory: Path) -> str:
    """Read/create a persistent private profile capability, never replace an existing key."""
    keyfile = directory / KEY_NAME
    if not keyfile.exists():
        key = secrets.token_urlsafe(24)
        with tempfile.NamedTemporaryFile(prefix=".chat-dock-", dir=directory) as temporary:
            temporary.write(key.encode("ascii"))
            temporary.flush()
            try:
                os.link(temporary.name, keyfile)
            except FileExistsError:
                pass
    descriptor = os.open(keyfile, os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0))
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077:
            raise ValueError("La clave del panel de chat no es privada.")
        token = os.read(descriptor, 64).decode("ascii")
        if not TOKEN.fullmatch(token):
            raise ValueError("La clave del panel de chat no es válida.")
        return token
    finally:
        os.close(descriptor)


class ChatDock:
    def __init__(self):
        self.token: str | None = None
        self.clients: set[web.WebSocketResponse] = set()

    @property
    def path(self) -> str | None:
        return f"/dock/chat/{self.token}/" if self.token else None

    def routes(self) -> list:
        return [
            web.get("/dock/chat/chat.css", self.css),
            web.get("/dock/chat/chat.js", self.script),
            web.get(r"/dock/chat/{token:[A-Za-z0-9_-]{32}}/", self.page),
            web.get(r"/dock/chat/{token:[A-Za-z0-9_-]{32}}/events", self.websocket, allow_head=False),
        ]

    def authorize(self, request: web.Request) -> None:
        token = request.match_info["token"]
        if not self.token or not hmac.compare_digest(token, self.token):
            raise web.HTTPNotFound()

    async def page(self, request: web.Request) -> web.StreamResponse:
        self.authorize(request)
        return web.FileResponse(ASSETS / "index.html", headers=HEADERS)

    async def css(self, request: web.Request) -> web.StreamResponse:
        return web.FileResponse(ASSETS / "chat.css", headers=HEADERS)

    async def script(self, request: web.Request) -> web.StreamResponse:
        return web.FileResponse(ASSETS / "chat.js", headers=HEADERS)

    async def websocket(self, request: web.Request) -> web.StreamResponse:
        self.authorize(request)
        if request.headers.get("Origin") != f"http://{request.host}":
            raise web.HTTPForbidden(text="Origin del panel no permitido")
        if len(self.clients) >= 12:
            raise web.HTTPServiceUnavailable(text="Demasiados paneles de chat abiertos")
        ws = web.WebSocketResponse(heartbeat=25, max_msg_size=4096)
        await ws.prepare(request)
        self.clients.add(ws)
        try:
            await ws.send_json({"channel": "dock", "type": "hello"})
            async for item in ws:
                if item.type in (WSMsgType.TEXT, WSMsgType.BINARY):
                    await ws.close(code=WSCloseCode.POLICY_VIOLATION, message=b"Read-only dock")
                    break
        finally:
            self.clients.discard(ws)
        return ws

    async def broadcast(self, message: dict) -> None:
        if message.get("simulated") is True or not self.clients:
            return
        clients = tuple(self.clients)
        payload = json.dumps(message, ensure_ascii=True)
        results = await asyncio.gather(*(ws.send_str(payload) for ws in clients), return_exceptions=True)
        for ws, result in zip(clients, results):
            if isinstance(result, Exception):
                self.clients.discard(ws)

    async def stop(self) -> None:
        self.token = None
        await asyncio.gather(*(ws.close(drain=False) for ws in tuple(self.clients)), return_exceptions=True)
