"""Local, opt-in speech for incoming chat; it does not alter the event bus or chat."""
from __future__ import annotations

import asyncio
import re
import unicodedata
from collections import OrderedDict, deque
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .audio import VoiceError, say

if TYPE_CHECKING:
    from .core.events import Event
    from .runtime import Runtime

CONFIG_KEY = "chat_tts"
TTS_PLATFORMS = ("twitch", "tiktok", "youtube", "kick")
_ALLOWED = frozenset(TTS_PLATFORMS)
_MAX_PENDING = 8
_MAX_TEXT = 160
_MAX_AGE = 25
_MAX_RECENT = 300
_USER_COOLDOWN = 5
_REPEAT_COOLDOWN = 20
_VOICE_TIMEOUT = 45
_ERROR_INTERVAL = 30
_SAMPLE = "Hola. Esta es la voz que leerá los mensajes de tu chat."
# No links, including common bare domains, and no leading slash/bang commands.
_LINK = re.compile(
    r"(?:\b[a-z][a-z0-9+.-]{1,22}://|\bmailto:|\bwww\.|(?<!\w)[\w-]+(?:\.[\w-]+)*\.[a-z]{2,63}\b"
    r"|(?<!\w)(?:\d{1,3}\.){3}\d{1,3}(?!\w))",
    re.IGNORECASE,
)
_COMMAND = re.compile(r"^[!/]+\s*[\w!?/]", re.UNICODE)
_SPAM = re.compile(r"(\w)\1{7,}", re.IGNORECASE)
_MARKUP = re.compile(r"</?[A-Za-z][^>]{0,140}>")
_STOPPED = "Se detuvo la prueba de voz."


@dataclass(frozen=True)
class ChatTtsSettings:
    enabled: bool = False
    platforms: frozenset[str] = frozenset()

    @classmethod
    def from_config(cls, settings: Mapping) -> ChatTtsSettings:
        raw = settings.get(CONFIG_KEY)
        if not isinstance(raw, dict) or type(raw.get("enabled")) is not bool:
            return cls()
        platforms = raw.get("platforms")
        if not isinstance(platforms, list):
            return cls()
        allowed = frozenset(p for p in platforms if isinstance(p, str) and p in _ALLOWED)
        return cls(raw["enabled"], allowed)

    @classmethod
    def from_selection(cls, enabled: bool, platforms: Iterable[str]) -> ChatTtsSettings:
        if type(enabled) is not bool or isinstance(platforms, (str, bytes, Mapping)):
            raise ValueError("Elige las plataformas para la lectura del chat.")
        try:
            selected = frozenset(platforms)
        except TypeError:
            raise ValueError("Elige las plataformas para la lectura del chat.") from None
        if not selected.issubset(_ALLOWED):
            raise ValueError("La lectura admite Twitch, TikTok, YouTube y Kick.")
        return cls(enabled, selected)

    def to_dict(self) -> dict:
        return {"enabled": self.enabled, "platforms": [p for p in TTS_PLATFORMS if p in self.platforms]}


def _normalize(raw: str) -> str:
    return " ".join("".join(
        " " if char.isspace() else char for char in unicodedata.normalize("NFKC", raw)
        if char.isspace() or unicodedata.category(char)[0] != "C"
    ).split())


def _speech_text(raw: object) -> str | None:
    # Connectors currently cap messages, but never do unbounded normalizing in an event callback.
    if not isinstance(raw, str) or not raw or len(raw) > 1000:
        return None
    value = _normalize(raw)
    if (not value or not any(char.isalnum() for char in value) or _COMMAND.match(value)
            or _LINK.search(value) or _MARKUP.search(value) or _SPAM.search(value)):
        return None
    if len(value) > _MAX_TEXT:
        limit = _MAX_TEXT - 1
        split = value.rfind(" ", 0, limit + 1)
        value = value[:split if split >= limit // 2 else limit].rstrip() + "…"
    return value


@dataclass(frozen=True)
class _Speech:
    message: str
    done: asyncio.Future[None] | None = None
    queued_at: float | None = None


class ChatTts:
    """Asynchronous FIFO on the runtime loop; never waits in the chat callback."""

    def __init__(self, rt: Runtime, settings: ChatTtsSettings) -> None:
        self.rt = rt
        self._settings = settings
        self._pending: deque[_Speech] = deque()
        self._worker: asyncio.Task | None = None
        self._recent_users: OrderedDict[tuple[str, str], float] = OrderedDict()
        self._recent_text: OrderedDict[str, float] = OrderedDict()
        self._controls = asyncio.Lock()
        self._clearing = self._closed = False
        self._next_error = 0.0

    @property
    def settings(self) -> ChatTtsSettings:
        # Immutable snapshot: safe to read from the Qt thread.
        return self._settings

    def on_event(self, event: Event) -> None:
        selected = self._settings
        if (self._closed or self._clearing or not selected.enabled or event.type != "chat"
                or event.platform not in selected.platforms or event.data.get("simulated")
                or event.data.get("command") or len(self._pending) >= _MAX_PENDING):
            return
        value = _speech_text(event.data.get("text"))
        if value is None:
            return
        now = asyncio.get_running_loop().time()
        actor = _normalize(event.user[:120]).casefold() if isinstance(event.user, str) else ""
        author = (event.platform, actor)
        duplicate = value.casefold().rstrip("!?.,… ")
        if ((actor and self._recent_users.get(author, -float("inf")) + _USER_COOLDOWN > now)
                or self._recent_text.get(duplicate, -float("inf")) + _REPEAT_COOLDOWN > now):
            return
        if actor:
            self._remember(self._recent_users, author, now)
        self._remember(self._recent_text, duplicate, now)
        self._enqueue(_Speech(value, queued_at=now))

    @staticmethod
    def _remember(cache: OrderedDict, key, now: float) -> None:
        cache[key] = now
        cache.move_to_end(key)
        if len(cache) > _MAX_RECENT:
            cache.popitem(last=False)

    def _enqueue(self, item: _Speech) -> None:
        self._pending.append(item)
        if self._worker is None or self._worker.done():
            self._worker = asyncio.create_task(self._run(), name="slb-chat-tts")

    async def preview(self) -> None:
        """Only explicit user input plays this sample, even when automatic speech is off."""
        if self._closed:
            raise RuntimeError(_STOPPED)
        loop = asyncio.get_running_loop()
        async with self._controls:
            if self._closed:
                raise RuntimeError(_STOPPED)
            if len(self._pending) >= _MAX_PENDING:
                raise ValueError("La cola de voz está llena. Espera o usa «Detener y vaciar cola».")
            done = loop.create_future()
            self._enqueue(_Speech(_SAMPLE, done))
        await done

    async def _run(self) -> None:
        loop = asyncio.get_running_loop()
        while self._pending:
            item = self._pending.popleft()
            result = item.done
            if result is not None and result.done():
                continue
            if item.queued_at is not None and loop.time() - item.queued_at > _MAX_AGE:
                continue
            try:
                async with asyncio.timeout(_VOICE_TIMEOUT):
                    await say(self.rt, item.message)
            except asyncio.CancelledError:
                if result is not None and not result.done():
                    result.set_exception(RuntimeError(_STOPPED))
                raise
            except Exception as exc:
                # Only the fixed diagnostics from the local speech path are safe to show.
                message = (str(exc) if isinstance(exc, VoiceError) else
                           "La prueba de voz no terminó. Revisa la salida de audio y vuelve a intentar.")
                now = loop.time()
                if now >= self._next_error:
                    self._next_error = now + _ERROR_INTERVAL
                    self.rt.log("Lectura de chat: " + message)
                if result is not None and not result.done():
                    result.set_exception(RuntimeError(message))
            else:
                if result is not None and not result.done():
                    result.set_result(None)

    async def apply(self, settings: ChatTtsSettings) -> None:
        if settings != self._settings:
            self._settings = settings
            await self.clear()

    async def clear(self) -> None:
        async with self._controls:
            self._clearing = True
            try:
                while self._pending:
                    result = self._pending.popleft().done
                    if result is not None and not result.done():
                        result.set_exception(RuntimeError(_STOPPED))
                self._recent_users.clear()
                self._recent_text.clear()
                worker, self._worker = self._worker, None
                if worker is not None and not worker.done():
                    worker.cancel()
                    await asyncio.gather(worker, return_exceptions=True)
            finally:
                self._clearing = False

    async def close(self) -> None:
        self._closed = True
        await self.clear()
