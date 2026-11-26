"""Endpoint de Kick separado del catálogo. Solo escucha en loopback."""
from __future__ import annotations

import base64
import binascii
import json
import math
import re
from datetime import datetime, timezone
from collections import OrderedDict
from pathlib import Path
import time

from aiohttp import web

from .base import Connector
from .platforms import chat_events
from ..core.events import Event
from ..dashboard import timestamp as parse_stamp


def kick_events(kind: str, body: dict) -> list[Event]:
    def username(field):
        person = body.get(field)
        return str(person.get("username", ""))[:100] if isinstance(person, dict) else ""
    if kind == "chat.message.sent" and isinstance(body.get("content"), str) and username("sender"):
        return chat_events("kick", username("sender"), body["content"])
    if kind == "channel.followed" and username("follower"):
        return [Event("kick", "follow", username("follower"))]
    if kind in {"channel.subscription.new", "channel.subscription.renewal"} and username("subscriber"):
        return [Event("kick", "sub", username("subscriber"))]
    if kind == "kicks.gifted" and username("sender") and isinstance(body.get("gift"), dict):
        gift = body["gift"]
        if type(gift.get("amount")) is int and gift["amount"] > 0:
            return [Event("kick", "gift", username("sender"), {
                "gift_name": str(gift.get("name", "Kicks"))[:100], "count": 1, "value": gift["amount"],
                "text": str(gift.get("message", ""))[:500]})]
    return []


class KickConnector(Connector):
    name = "kick"

    def __init__(self, rt):
        super().__init__(rt)
        self.runner = None
        self.port = None
        self.seen = OrderedDict()

    async def start(self, port: int, broadcaster: int, pem: Path) -> None:
        from cryptography.hazmat.primitives.serialization import load_pem_public_key
        from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
        if self.runner is not None:
            raise ValueError("Kick ya está en ejecución.")
        if broadcaster <= 0:
            raise ValueError("Indica el ID numérico del canal Kick.")
        key = load_pem_public_key(pem.read_bytes())
        if not isinstance(key, RSAPublicKey) or key.key_size < 2048:
            raise ValueError("La clave de Kick no es una clave pública RSA válida.")
        self.key, self.broadcaster = key, broadcaster
        app = web.Application(client_max_size=128 * 1024)
        app.router.add_post("/webhooks/kick", self.handle)
        runner = web.AppRunner(app, access_log=None, shutdown_timeout=3)
        try:
            await runner.setup()
            await web.TCPSite(runner, "127.0.0.1", port).start()
        except BaseException:
            await runner.cleanup()
            raise
        self.seen.clear()
        self.rt.dashboard.reset_connection("kick")
        self.runner = runner
        self.port = runner.addresses[0][1]
        self.status = "escuchando (webhook firmado)"
        self.rt.log(f"Kick: escuchando en 127.0.0.1:{self.port}/webhooks/kick")

    async def stop(self):
        if self.runner is not None:
            await self.runner.cleanup()
            self.runner = None
        self.port = None
        self.status = "desconectado"
        self.rt.dashboard.invalidate("kick")

    async def handle(self, request):
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding
        h = request.headers
        ident = h.get("Kick-Event-Message-Id", "")
        timestamp = h.get("Kick-Event-Message-Timestamp", "")
        signature = h.get("Kick-Event-Signature", "")
        if (not re.fullmatch(r"[A-Za-z0-9_-]{8,128}", ident) or len(timestamp) > 80
                or not 16 <= len(signature) <= 1024):
            raise web.HTTPUnauthorized()
        try:
            sent = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            age = abs((datetime.now(timezone.utc) - sent).total_seconds())
            if not math.isfinite(age) or age > 300:
                raise ValueError()
            decoded = base64.b64decode(signature, validate=True)
            raw = await request.read()
            self.key.verify(decoded, f"{ident}.{timestamp}.".encode("ascii") + raw,
                            padding.PKCS1v15(), hashes.SHA256())
        except (ValueError, TypeError, UnicodeError, binascii.Error, InvalidSignature):
            raise web.HTTPUnauthorized() from None
        try:
            body = json.loads(raw)
            broadcaster = body["broadcaster"]["user_id"]
        except (ValueError, TypeError, KeyError, RecursionError):
            raise web.HTTPBadRequest() from None
        if type(broadcaster) is not int or broadcaster != self.broadcaster:
            raise web.HTTPForbidden()
        if h.get("Kick-Event-Version") != "1":
            return web.Response(status=204)
        kind = h.get("Kick-Event-Type", "")
        events = kick_events(kind, body)
        live = body.get("is_live") if kind == "livestream.status.updated" else None
        start = parse_stamp(body.get("started_at"))
        has_status = type(live) is bool and start is not None and (
            live or parse_stamp(body.get("ended_at")) is not None)
        now = time.monotonic()
        while self.seen and next(iter(self.seen.values())) < now - 600:
            self.seen.popitem(last=False)
        if ident not in self.seen and (events or has_status):
            if len(self.seen) >= 100_000:
                raise web.HTTPServiceUnavailable()
            self.seen[ident] = now
            if has_status:
                self.rt.dashboard.activity("kick")
                self.rt.dashboard.signal(
                    "kick", live, title=body.get("title", ""), started_at=start, session_id=body.get("started_at"),
                    identity=body["broadcaster"].get("channel_slug"), order=sent.timestamp(), ttl=300,
                    note="Último aviso oficial: " + ("inicio del directo." if live else "fin del directo.") +
                         " Kick no envía espectadores por este webhook.")
            for event in events:
                await self.rt.bus.publish(event)
        return web.Response(status=204)
