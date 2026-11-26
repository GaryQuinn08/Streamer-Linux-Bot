"""Recepción de Twitch EventSub y chat de YouTube con credenciales del usuario."""
from __future__ import annotations

import asyncio
import os
from collections import OrderedDict
from contextlib import AsyncExitStack
from decimal import Decimal, InvalidOperation

import aiohttp
from yarl import URL

from .base import Connector
from .oauth import (
    TWITCH_WRITE_SCOPE, SignInError, browser_client, sign_in, twitch_session_identity, youtube_live_chat,
)
from ..core.events import Event


def chat_events(platform: str, user: str, text: str) -> list[Event]:
    text = text[:500]
    events = [Event(platform, "chat", user, {"text": text})]
    if text.startswith("!") and text.split()[0][1:]:
        events.append(Event(platform, "command", user, {"text": text, "command": text.split()[0][1:]}))
    return events


def youtube_events(item: dict) -> list[Event]:
    snippet = item.get("snippet") or {}
    user = str((item.get("authorDetails") or {}).get("displayName", ""))[:100]
    kind = snippet.get("type")
    if kind == "textMessageEvent":
        return chat_events("youtube", user, str((snippet.get("textMessageDetails") or {}).get("messageText", "")))
    if kind in {"superChatEvent", "superStickerEvent"}:
        details = snippet.get("superChatDetails") or snippet.get("superStickerDetails") or {}
        try:
            amount = str(Decimal(details["amountMicros"]) / 1_000_000)
        except (InvalidOperation, TypeError, KeyError):
            return []
        return [Event("youtube", "donation", user, {
            "amount": amount, "value": amount, "currency": str(details.get("currency", ""))[:10],
            "text": str(details.get("userComment", ""))[:500]})]
    if kind == "newSponsorEvent":
        return [Event("youtube", "sub", user)]
    return []


def twitch_events(kind: str, data: dict) -> list[Event]:
    user = str(data.get("chatter_user_name") or data.get("user_name") or "")[:100]
    if kind == "channel.chat.message":
        return chat_events("twitch", user, str((data.get("message") or {}).get("text", "")))
    if kind == "channel.follow":
        return [Event("twitch", "follow", user)]
    if kind == "channel.subscribe":
        return [Event("twitch", "sub", user, {"tier": str(data.get("tier", ""))})]
    if kind == "channel.cheer" and type(data.get("bits")) is int:
        return [Event("twitch", "bits", user or "anónimo", {
            "value": data["bits"], "bits": data["bits"], "text": str(data.get("message", ""))[:500]})]
    if kind == "channel.channel_points_custom_reward_redemption.add":
        return [Event("twitch", "points", user, {"reward": str((data.get("reward") or {}).get("title", ""))[:100],
                                               "text": str(data.get("user_input", ""))[:500]})]
    return []


class _Receiver(Connector):
    def __init__(self, rt):
        super().__init__(rt)
        self._task = None
        self._seen = OrderedDict()

    async def start(self, *, browser=None, setting: str = "", twitch_write: bool = False):
        if self._task is None or self._task.done():
            self.status = "autoriza en el navegador…" if browser else "conectando…"
            self._task = asyncio.create_task(self._run(browser, setting, twitch_write and self.name == "twitch"))

    @property
    def busy(self):
        return self._task is not None and not self._task.done()

    async def _run(self, browser, setting, twitch_write):
        try:
            if browser:
                client = await browser_client(self.name, setting)
                options = {"twitch_write": True} if twitch_write else {}
                token = await sign_in(client, browser, **options)
                self.status = "autorizado; conectando…"
                await self.receive((token, client.client_id), **options)
            else:
                await self.receive()
            self.status = "desconectado"
        except SignInError as exc:
            self.status = str(exc)
            self.rt.log(f"{self.name}: {exc}")
        except ValueError:
            self.status = "revisa la configuración y el directo"
            self.rt.log(f"{self.name}: la conexión no es válida o faltan permisos.")
        except aiohttp.ClientResponseError as exc:
            self.status = ("la sesión expiró; vuelve a iniciar sesión" if exc.status == 401
                           else f"error HTTP {exc.status}")
            self.rt.log(f"{self.name}: HTTP {exc.status}. Revisa las credenciales, los permisos y el directo.")
        except (aiohttp.ClientError, TimeoutError, TypeError, KeyError):
            self.status = "conexión interrumpida"
            self.rt.log(f"{self.name}: se interrumpió la conexión. Vuelve a conectar.")
        except Exception as exc:
            self.status = "error"
            self.rt.log(f"{self.name}: {type(exc).__name__}")

    async def stop(self):
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None
        self.status = "desconectado"

    async def publish(self, ident, events):
        if isinstance(ident, str) and ident:
            if ident in self._seen:
                return
            self._seen[ident] = None
            if len(self._seen) > 2048:
                self._seen.popitem(last=False)
        for event in events:
            await self.rt.bus.publish(event)


class TwitchConnector(_Receiver):
    name = "twitch"

    def __init__(self, rt):
        super().__init__(rt)
        self._writer = None
        self._send_lock = asyncio.Lock()

    @property
    def can_send(self):
        return self.status == "conectado (EventSub)" and self._writer is not None

    async def send_chat(self, text: str) -> None:
        text = text.strip()
        if not 1 <= len(text) <= 500 or any(c in text for c in "\r\n\x00"):
            raise SignInError("Escribe un mensaje de una línea, de 1 a 500 caracteres.")
        if self._send_lock.locked():
            raise SignInError("Espera a que termine el envío anterior.")
        async with self._send_lock:
            writer = self._writer
            if writer is None or not self.can_send:
                raise SignInError("Conecta Twitch con permiso para enviar mensajes.")
            session, headers, owner = writer
            try:
                async with session.post(
                    "https://api.twitch.tv/helix/chat/messages", headers=headers, allow_redirects=False,
                    json={"broadcaster_id": owner, "sender_id": owner, "message": text},
                ) as response:
                    if response.status == 401:
                        if self._writer is writer:
                            self._writer = None
                        raise SignInError("Twitch rechazó el permiso de envío. Desconecta y vuelve a autorizar.")
                    if response.status == 429:
                        raise SignInError("Twitch limitó los envíos. Espera antes de intentar de nuevo.")
                    if response.status != 200:
                        raise SignInError(f"Twitch no confirmó el envío (HTTP {response.status}).")
                    body = await response.json()
            except SignInError:
                raise
            except (aiohttp.ClientError, TimeoutError, ValueError):
                raise SignInError("No se pudo confirmar el envío. Revisa el chat de Twitch antes de reintentar.") from None
            messages = body.get("data") if isinstance(body, dict) else None
            item = messages[0] if isinstance(messages, list) and messages and isinstance(messages[0], dict) else {}
            if item.get("is_sent") is not True:
                drop = item.get("drop_reason")
                code = drop.get("code") if isinstance(drop, dict) else None
                detail = {
                    "automod_held": "AutoMod retuvo el mensaje para revisión.",
                    "msg_duplicate": "Twitch descartó un mensaje duplicado.",
                    "slow_mode": "El chat está en modo lento. Espera antes de volver a enviar.",
                }.get(code) if isinstance(code, str) else None
                raise SignInError(detail or "Twitch no confirmó el envío. Revisa el chat antes de reintentar.")

    async def receive(self, authorization=None, *, twitch_write: bool = False):
        if authorization:
            token, client = authorization
            owner = ""
        else:
            token, client, owner = (os.environ.get(name, "") for name in
                                   ("SLB_TWITCH_TOKEN", "SLB_TWITCH_CLIENT_ID", "SLB_TWITCH_BROADCASTER_ID"))
            if not (token and client and owner.isdigit()):
                raise SignInError("Configura SLB_TWITCH_TOKEN, SLB_TWITCH_CLIENT_ID y SLB_TWITCH_BROADCASTER_ID.")
        headers = {"Authorization": f"Bearer {token}", "Client-Id": client}
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=9)) as session:
            logged_in, scopes = await twitch_session_identity(session, token, client)
            if authorization and twitch_write:
                if TWITCH_WRITE_SCOPE in scopes:
                    self._writer = session, headers, logged_in
                else:
                    self.rt.log("Twitch: la cuenta no concedió permiso para enviar mensajes.")
            try:
                await self._events(session, token, client, owner or logged_in, headers)
            finally:
                self._writer = None

    async def _events(self, session, token, client, owner, headers):
        specs = (
            ("channel.chat.message", "1", {"user_id": owner}),
            ("channel.follow", "2", {"moderator_user_id": owner}),
            ("channel.subscribe", "1", {}),
            ("channel.cheer", "1", {}),
            ("channel.channel_points_custom_reward_redemption.add", "1", {}),
        )
        async with AsyncExitStack() as sockets:
            async def open_socket(url):
                socket = await sockets.enter_async_context(
                    session.ws_connect(url, max_msg_size=1024 * 1024))
                hello = await socket.receive_json(timeout=12)
                if hello["metadata"]["message_type"] != "session_welcome":
                    raise ValueError("EventSub no envió una bienvenida.")
                return socket, hello["payload"]["session"]

            ws, info = await open_socket(URL("wss://eventsub.wss.twitch.tv/ws"))

            async def subscribe(kind, version, extra):
                async with session.post("https://api.twitch.tv/helix/eventsub/subscriptions",
                            headers=headers, allow_redirects=False, json={
                                "type": kind, "version": version,
                                "condition": {"broadcaster_user_id": owner, **extra},
                                "transport": {"method": "websocket", "session_id": info["id"]},
                            }) as response:
                    if response.status != 202:
                        self.rt.log(f"Twitch: {kind} no autorizado o no disponible ({response.status}).")
                    return response.status == 202

            if not any(await asyncio.gather(*(subscribe(*spec) for spec in specs))):
                raise ValueError("no se pudo suscribir a ningún evento; revisa los permisos del token.")
            self.status = "conectado (EventSub)"
            loop = asyncio.get_running_loop()
            validate_at = loop.time() + 3500
            while True:
                if loop.time() >= validate_at:
                    _, scopes = await twitch_session_identity(session, token, client)
                    if TWITCH_WRITE_SCOPE not in scopes:
                        self._writer = None
                    validate_at = loop.time() + 3500
                packet = await ws.receive_json(timeout=(info.get("keepalive_timeout_seconds") or 30) + 5)
                metadata, payload = packet["metadata"], packet.get("payload", {})
                kind = metadata["message_type"]
                if kind == "notification":
                    await self.publish(metadata.get("message_id"), twitch_events(
                        metadata.get("subscription_type", ""), payload.get("event", {})))
                elif kind == "revocation":
                    self.rt.log("Twitch revocó una suscripción; revisa los permisos en tu cuenta.")
                elif kind == "session_reconnect":
                    candidate = URL(payload["session"]["reconnect_url"])
                    if (candidate.scheme != "wss" or candidate.host != "eventsub.wss.twitch.tv"
                            or candidate.port != 443 or candidate.user is not None):
                        raise ValueError("EventSub envió una dirección de reconexión no válida.")
                    old = ws
                    ws, info = await open_socket(candidate)
                    await old.close()


class YoutubeConnector(_Receiver):
    name = "youtube"

    async def receive(self, authorization=None):
        if authorization:
            token, _client = authorization
            chat = ""
        else:
            token, chat = (os.environ.get(k, "") for k in ("SLB_YOUTUBE_TOKEN", "SLB_YOUTUBE_LIVE_CHAT_ID"))
            if not (token and chat):
                raise SignInError("Configura SLB_YOUTUBE_TOKEN y SLB_YOUTUBE_LIVE_CHAT_ID.")
        headers = {"Authorization": f"Bearer {token}"}
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=12)) as session:
            chat = chat or await youtube_live_chat(session, headers)
            params = {"part": "snippet,authorDetails", "liveChatId": chat, "maxResults": "200"}
            initial = True
            while True:
                async with session.get("https://www.googleapis.com/youtube/v3/liveChat/messages",
                                       headers=headers, params=params, allow_redirects=False) as response:
                    response.raise_for_status()
                    body = await response.json()
                self.status = "conectado (chat en vivo)"
                for item in body.get("items", ()):
                    await self.publish(item.get("id"), [] if initial else youtube_events(item))
                initial = False
                if body.get("offlineAt") or not body.get("nextPageToken"):
                    self.rt.log("YouTube: terminó el chat del directo.")
                    return
                params["pageToken"] = body["nextPageToken"]
                await asyncio.sleep(max(1.0, int(body.get("pollingIntervalMillis", 5000)) / 1000))
