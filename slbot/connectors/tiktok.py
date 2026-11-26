"""Entradas de TikTok LIVE, desactivadas hasta que el usuario las conecte."""
from __future__ import annotations

import asyncio
import json
import re
import sys
from collections import OrderedDict

import aiohttp

from ..core.events import Event
from ..paths import data_dir
from .base import Connector
from .platforms import chat_events

SUPPORTED = {"chat", "follow", "share", "like", "gift", "subscribe"}


def _positive(value, fallback: int = 1) -> int:
    try:
        return max(1, int(value))
    except (ValueError, TypeError, OverflowError):
        return fallback


def _flag(value) -> bool:
    return value is True or value == 1 or value in ("1", "true")


def normalize_tikfinity(packet: dict) -> Event | None:
    kind, data = packet.get("event"), packet.get("data")
    if not isinstance(kind, str) or kind not in SUPPORTED or not isinstance(data, dict):
        return None
    user = str(data.get("nickname") or data.get("uniqueId") or "")[:100]
    if kind == "chat":
        return Event("tiktok", "chat", user, {"text": str(data.get("comment", ""))[:500]})
    if kind == "gift":
        gift = data.get("gift")
        gift = gift if isinstance(gift, dict) else {}
        is_streak = str(data.get("giftType", gift.get("gift_type", ""))) == "1"
        if is_streak and not _flag(data.get("repeatEnd")):
            return None
        name = data.get("giftName") or gift.get("name")
        if not name:
            return None
        count = _positive(data.get("repeatCount"))
        value = count * _positive(data.get("diamondCount"), fallback=1)
        return Event("tiktok", "gift", user, {"gift_name": str(name)[:100], "count": count, "value": value})
    return Event("tiktok", "sub" if kind == "subscribe" else kind, user)


def normalize_live_gift(event) -> Event | None:
    gift = getattr(event, "gift", None)
    if gift is None or getattr(event, "streaking", False):
        return None
    name = getattr(gift, "name", None) or getattr(gift, "gift_name", None)
    if not name:
        return None
    user = getattr(event, "user", None)
    count = _positive(getattr(event, "repeat_count", 1))
    diamonds = _positive(getattr(gift, "diamond_count", 1))
    return Event("tiktok", "gift", _display_name(user), {
        "gift_name": str(name)[:100], "count": count, "value": count * diamonds,
    })


def _display_name(user) -> str:
    return str(getattr(user, "nickname", None) or getattr(user, "unique_id", ""))[:100]


class TiktokConnector(Connector):
    name = "tiktok"

    def __init__(self, rt) -> None:
        super().__init__(rt)
        self._task: asyncio.Task | None = None
        self._seen: OrderedDict[str, None] = OrderedDict()

    async def start(self, mode: str = "tikfinity", channel: str = "") -> None:
        if self._task is not None and not self._task.done():
            return
        channel = channel.strip().removeprefix("@")
        if mode not in {"tikfinity", "directo"} or (
            mode == "directo" and not re.fullmatch(r"[A-Za-z0-9_.]{1,32}", channel)
        ):
            self.rt.log("TikTok: escribe un @usuario válido para la conexión directa.")
            return
        self._seen.clear()
        self.status = "conectando…"
        self._task = asyncio.create_task(self._run(mode, channel))

    async def _run(self, mode: str, channel: str) -> None:
        try:
            if mode == "tikfinity":
                await self._tikfinity()
            else:
                await self._direct(channel)
            self.status = "desconectado"
            self.rt.log("TikTok: terminó la conexión. Pulsa Conectar para volver a intentarlo.")
        except asyncio.CancelledError:
            raise
        except ImportError as exc:
            self.status = "faltan dependencias"
            self.rt.log("TikTok directo: revisa las dependencias del conector; reinstala con --tiktok.")
        except Exception as exc:
            self.status = "error"
            self.rt.log(f"TikTok ({mode}): conexión no disponible ({type(exc).__name__}). "
                        "Revisa que el directo o TikFinity estén activos.")

    async def _publish(self, event: Event | None, message_id=None) -> None:
        if event is None:
            return
        if message_id:
            key = f"{event.type}:{message_id}"
            if key in self._seen:
                return
            self._seen[key] = None
            if len(self._seen) > 2048:
                self._seen.popitem(last=False)
        if event.type == "chat":
            for message in chat_events("tiktok", event.user, event.data["text"]):
                await self.rt.bus.publish(message)
        else:
            await self.rt.bus.publish(event)

    async def _tikfinity(self, url: str = "ws://127.0.0.1:21213/") -> None:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as session:
            async with session.ws_connect(url, heartbeat=25,
                                          max_msg_size=256 * 1024) as ws:
                self.status = "conectado (TikFinity)"
                self.rt.log("TikFinity conectado mediante su Event API local.")
                async for message in ws:
                    if message.type != aiohttp.WSMsgType.TEXT:
                        continue
                    try:
                        packet = json.loads(message.data)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(packet, dict):
                        data = packet.get("data")
                        message_id = data.get("msgId") if isinstance(data, dict) else None
                        if not isinstance(message_id, (str, int)):
                            message_id = None
                        await self._publish(normalize_tikfinity(packet), message_id)

    async def _direct(self, channel: str) -> None:
        extra = data_dir() / "tiktok-deps"
        if extra.is_dir() and str(extra) not in sys.path:
            sys.path.append(str(extra))
        from TikTokLive import TikTokLiveClient
        from TikTokLive.events import CommentEvent, ConnectEvent, FollowEvent, GiftEvent

        client = TikTokLiveClient(unique_id=channel)

        @client.on(ConnectEvent)
        async def connected(_event):
            self.status = "conectado (experimental)"
            self.rt.log("TikTok LIVE conectado mediante el conector experimental.")

        @client.on(CommentEvent)
        async def chat(event):
            await self._publish(Event("tiktok", "chat", _display_name(event.user),
                                      {"text": str(event.comment)[:500]}))

        @client.on(FollowEvent)
        async def follow(event):
            await self._publish(Event("tiktok", "follow", _display_name(event.user)))

        @client.on(GiftEvent)
        async def gift(event):
            common = getattr(event, "common", None)
            await self._publish(normalize_live_gift(event), getattr(common, "msg_id", None))

        try:
            async with asyncio.timeout(30):
                task = await client.start()
            await task
        finally:
            try:
                async with asyncio.timeout(3):
                    if client.connected:
                        await client.disconnect()
            finally:
                await client.close()

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None
        self.status = "desconectado"
