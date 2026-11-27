"""Entradas de TikTok LIVE, desactivadas hasta que el usuario las conecte."""
from __future__ import annotations

import asyncio
import json
import re
import sys
from collections import OrderedDict

import aiohttp

from ..core.events import Event
from ..dashboard import number
from ..paths import data_dir
from .base import Connector
from .platforms import chat_events

SUPPORTED = {"chat", "follow", "share", "like", "gift", "subscribe"}
_OFFLINE_RECHECK = 90
_WAITING = "canal sin directo; esperando"


def _positive(value, fallback: int = 1) -> int:
    try:
        return max(1, int(value))
    except (ValueError, TypeError, OverflowError):
        return fallback


def _flag(value) -> bool:
    return value is True or value == 1 or value in ("1", "true")


def normalize_tikfinity(packet: dict) -> Event | None:
    kind, data = packet.get("event"), packet.get("data")
    if (not isinstance(kind, str) or kind not in SUPPORTED or not isinstance(data, dict)
            or data.get("simulated") or packet.get("simulated")):
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
        diamond = number(data.get("diamondCount"))
        return Event("tiktok", "gift", user, {"gift_name": str(name)[:100], "count": count,
                                              "value": count * _positive(data.get("diamondCount")),
                                              "diamonds": None if diamond is None else count * diamond})
    if kind == "like":
        return Event("tiktok", "like", user, {"count": number(data.get("likeCount")) or 1})
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
    raw_diamonds = number(getattr(gift, "diamond_count", None))
    diamonds = _positive(raw_diamonds)
    return Event("tiktok", "gift", _display_name(user), {
        "gift_name": str(name)[:100], "count": count, "value": count * diamonds,
        "diamonds": None if raw_diamonds is None else count * raw_diamonds,
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
        self.rt.dashboard.reset_connection("tiktok")
        self.status = "conectando…"
        self._task = asyncio.create_task(self._run(mode, channel))

    async def _run(self, mode: str, channel: str) -> None:
        try:
            if mode == "tikfinity":
                await self._tikfinity()
            else:
                await self._watch_direct(channel)
            self.status = "desconectado"
            self.rt.log("TikTok: terminó la conexión. Pulsa Conectar para volver a intentarlo.")
        except asyncio.CancelledError:
            raise
        except ImportError as exc:
            self.status = "faltan dependencias"
            self.rt.log("TikTok directo: revisa las dependencias del conector; reinstala con --tiktok.")
        except Exception as exc:
            self.rt.dashboard.invalidate("tiktok")
            self.status = "error"
            self.rt.log(f"TikTok ({mode}): conexión no disponible ({type(exc).__name__}). "
                        "Revisa que el directo o TikFinity estén activos.")
        finally:
            self.rt.dashboard.invalidate("tiktok", keep_offline=True)

    async def _watch_direct(self, channel: str) -> None:
        # Only retry a documented offline verdict or an explicit LIVE end.
        # Network/signing failures surface as errors instead of a retry storm.
        while True:
            await self._direct(channel)
            if self.status != _WAITING:
                return
            await asyncio.sleep(_OFFLINE_RECHECK)

    async def _publish(self, event: Event | None, message_id=None, *, metrics_only=False) -> None:
        if event is None:
            return
        if message_id:
            key = f"{event.type}:{message_id}"
            if key in self._seen:
                return
            self._seen[key] = None
            if len(self._seen) > 2048:
                self._seen.popitem(last=False)
        if metrics_only:
            self.rt.dashboard.event(event)
        elif event.type == "chat":
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
                        if isinstance(data, dict) and not (data.get("simulated") or packet.get("simulated")):
                            if packet.get("event") == "roomUser" and (viewers := number(data.get("viewerCount"))) is not None:
                                room = data.get("roomId")
                                self.rt.dashboard.signal("tiktok", True, viewers=viewers,
                                                         session_id=room if isinstance(room, (str, int)) else None,
                                                         ttl=120, note="Datos de sala recibidos del puente TikFinity.")
                                self.rt.dashboard.activity("tiktok")
                            elif packet.get("event") == "streamEnd":
                                self.rt.dashboard.signal("tiktok", False, ttl=180)
                                self.rt.dashboard.activity("tiktok")
                        message_id = data.get("msgId") if isinstance(data, dict) else None
                        if not isinstance(message_id, (str, int)):
                            message_id = None
                        await self._publish(normalize_tikfinity(packet), message_id)

    async def _direct(self, channel: str) -> None:
        extra = data_dir() / "tiktok-deps"
        if extra.is_dir() and str(extra) not in sys.path:
            sys.path.append(str(extra))
        from TikTokLive import TikTokLiveClient
        from TikTokLive.client.errors import UserOfflineError
        from TikTokLive.events import (CommentEvent, ConnectEvent, FollowEvent, GiftEvent,
                                       LikeEvent, LiveEndEvent, RoomUserSeqEvent, ShareEvent)

        client = TikTokLiveClient(unique_id=channel)

        @client.on(ConnectEvent)
        async def connected(_event):
            self.status = "conectado (experimental)"
            self.rt.dashboard.signal("tiktok", True, identity="@" + channel,
                                     session_id=client.room_id, ttl=None)
            self.rt.log("TikTok LIVE conectado mediante el conector experimental.")

        @client.on(RoomUserSeqEvent)
        async def viewer_count(event):
            viewers = number(event.total)
            if viewers is not None and self.status == "conectado (experimental)":
                self.rt.dashboard.signal("tiktok", True, viewers=viewers, session_id=client.room_id, ttl=None)
                self.rt.dashboard.activity("tiktok")

        @client.on(LiveEndEvent)
        async def ended(_event):
            self.status = _WAITING
            self.rt.dashboard.signal("tiktok", False, identity="@" + channel, ttl=180)

        @client.on(LikeEvent)
        async def like(event):
            await self._publish(Event("tiktok", "like", _display_name(event.user), {"count": number(event.count) or 1}),
                                getattr(getattr(event, "common", None), "msg_id", None), metrics_only=True)

        @client.on(ShareEvent)
        async def share(event):
            await self._publish(Event("tiktok", "share", _display_name(event.user)),
                                getattr(getattr(event, "common", None), "msg_id", None), metrics_only=True)

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
        except UserOfflineError:
            self.status = _WAITING
            self.rt.dashboard.signal("tiktok", False, identity="@" + channel, ttl=180)
        finally:
            try:
                async with asyncio.timeout(3):
                    if client.connected:
                        await client.disconnect()
            finally:
                # TikTokLive 6.6 close() intenta relanzar el loop existente.
                # El WebSocket ya se cerró arriba; aquí solo se cierra su HTTP.
                await client.web.close()

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None
        self.status = "desconectado"
        self.rt.dashboard.invalidate("tiktok")
