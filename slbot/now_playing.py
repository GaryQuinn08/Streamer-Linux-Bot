"""Read-only music metadata from one explicitly selected local player."""
from __future__ import annotations

import asyncio
import json
import re
import shutil
import sys
import unicodedata
from dataclasses import dataclass

CONFIG_KEY = "now_playing"
BOT_SOURCE = "bot"
MPRIS_PREFIX = "org.mpris.MediaPlayer2."
MPRIS_PATH = "/org/mpris/MediaPlayer2"
MPRIS_PLAYER = MPRIS_PREFIX + "Player"
_PLAYER = re.compile(r"(?:[A-Za-z_][A-Za-z0-9_-]*)(?:\.[A-Za-z0-9_-]+){0,5}\Z")
_PRIVATE = re.compile(
    r"https?:|www\.|file:|spotify:|data:|ftp:|blob:|[A-Z][A-Z0-9+.-]*://|"
    r"\\|(?:^|\s|[(\[{])(?:~?/|\.{1,2}/|[A-Z]:/)|"
    r"\b[\w.-]+/(?:[\w.-]+/|[\w.-]+\.[a-z]{2,8}(?:$|\s))|\b[\w.-]+\.[a-z]{2,8}/|"
    r"(?:^|\s)\S+\.(?:wav|mp3|ogg|opus|flac|m4a|aac|mkv|mp4|webm)(?:$|\s)|"
    r"\b(?:access[_ -]?token|authorization|bearer|api[_ -]?key|secret|token|pass(?:word|wd)|signature|sig|key)\s*[:=]|"
    r"\bbearer\s+\S+|\b[0-9a-f]{32,}\b|\beyJ[A-Za-z0-9_-]{12,}|[A-Za-z0-9_+-]{36,}",
    re.IGNORECASE,
)


def _player_name(value) -> bool:
    return isinstance(value, str) and len(value) <= 100 and _PLAYER.fullmatch(value) is not None


def clean_metadata(value, limit: int) -> str:
    if not isinstance(value, str) or len(value) > 500:
        return ""
    value = unicodedata.normalize("NFKC", value)
    value = "".join(" " if c.isspace() else c for c in value if not unicodedata.category(c).startswith("C") or c.isspace())
    value = " ".join(value.split())
    if _PRIVATE.search(value):
        return ""
    return value[:limit].strip()


@dataclass(frozen=True)
class NowPlayingSettings:
    enabled: bool = False
    source: str = ""

    @classmethod
    def from_config(cls, settings) -> NowPlayingSettings:
        saved = settings.get(CONFIG_KEY, {})
        if isinstance(saved, dict) and saved.get("enabled") is True:
            try:
                return cls.select(True, saved.get("source"))
            except ValueError:
                pass
        return cls()

    @classmethod
    def select(cls, enabled: bool, source) -> NowPlayingSettings:
        if enabled is not True:
            return cls()
        if source == BOT_SOURCE or (isinstance(source, str) and source.startswith(MPRIS_PREFIX)
                                    and _player_name(source[len(MPRIS_PREFIX):])):
            return cls(True, source)
        raise ValueError("Elige un reproductor específico antes de activar Ahora suena.")

    def to_dict(self) -> dict:
        return {"enabled": self.enabled, "source": self.source}


@dataclass(frozen=True)
class Track:
    state: str = "idle"
    title: str = ""
    artist: str = ""
    source: str = ""

    def as_dict(self) -> dict[str, str]:
        return {"state": self.state, "title": self.title, "artist": self.artist, "source": self.source}


async def _bus(*argv: str):
    if not sys.platform.startswith("linux"):
        return None
    executable = shutil.which("busctl")
    if executable is None:
        return None
    spawn = asyncio.create_task(asyncio.create_subprocess_exec(
        executable, "--user", "--json=short", "--auto-start=no", "--allow-interactive-authorization=no",
        "--timeout=1s", *argv,
        stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
    ))
    process = None
    try:
        try:
            process = await asyncio.shield(spawn)
        except asyncio.CancelledError:
            try:
                process = await spawn
            except OSError:
                pass
            raise
        # Bound subprocess output as well as duration. Never record output in logs.
        async with asyncio.timeout(1.5):
            raw = await process.stdout.readexactly(65537)
        return None  # oversize
    except asyncio.IncompleteReadError as exc:
        try:
            code = await asyncio.wait_for(process.wait(), 0.5)
            return json.loads(exc.partial) if code == 0 else None
        except (TimeoutError, ValueError, UnicodeError, RecursionError):
            return None
    except (OSError, TimeoutError):
        return None
    finally:
        if process is not None and process.returncode is None:
            try:
                process.kill()
            except ProcessLookupError:
                pass
            # Drain the pipe so waiting for the transport cannot stall on a full buffer.
            await process.communicate()


async def available_players() -> tuple[str, ...]:
    # Ask D-Bus for owned names, not for playback/metadata. No fallback to an
    # arbitrary active player, and no application can be activated by this.
    reply = await _bus("call", "org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus", "ListNames")
    data = _typed(reply, "as")
    names = data[0] if isinstance(data, list) and len(data) == 1 and isinstance(data[0], list) else ()
    return tuple(sorted({name for name in names if isinstance(name, str) and name.startswith(MPRIS_PREFIX)
                         and _player_name(name[len(MPRIS_PREFIX):])}))[:100]


def _typed(variant, signature: str):
    return variant.get("data") if isinstance(variant, dict) and variant.get("type") == signature else None


async def _property(source: str, name: str):
    # Invoke Get explicitly so busctl enforces no autostart/authorization and
    # the configured call timeout even on older systemd (e.g. Mint 22).
    reply = await _bus("call", source, MPRIS_PATH, "org.freedesktop.DBus.Properties",
                       "Get", "ss", MPRIS_PLAYER, name)
    variants = _typed(reply, "v")
    return variants[0] if isinstance(variants, list) and len(variants) == 1 else None


async def mpris_track(source: str) -> Track:
    # The full well-known D-Bus name is the exact destination: no prefix match,
    # no playerctld "current player", and no switching between browser instances.
    if not source.startswith(MPRIS_PREFIX) or not _player_name(source[len(MPRIS_PREFIX):]):
        return Track()
    status = _typed(await _property(source, "PlaybackStatus"), "s")
    if status not in ("Playing", "Paused"):
        return Track()
    metadata = _typed(await _property(source, "Metadata"), "a{sv}")
    if not isinstance(metadata, dict):
        return Track()
    title = clean_metadata(_typed(metadata.get("xesam:title"), "s"), 110)
    if not title:
        return Track()
    raw_artists = _typed(metadata.get("xesam:artist"), "as")
    artists = (clean_metadata(raw, 90) for raw in raw_artists[:4]) if isinstance(raw_artists, list) else ()
    return Track(status.lower(), title, ", ".join(filter(None, artists))[:90], source[len(MPRIS_PREFIX):])


class NowPlaying:
    def __init__(self, runtime, settings: NowPlayingSettings, interval: float = 2) -> None:
        self.rt = runtime
        self.settings = settings
        self._interval = interval
        self._track = Track()
        self._task: asyncio.Task | None = None
        self._lock = asyncio.Lock()

    def snapshot(self) -> dict[str, str]:
        return self._track.as_dict()

    async def apply(self, settings: NowPlayingSettings) -> None:
        async with self._lock:
            await self._stop()
            self.settings = settings
            await self._publish(Track())
            if settings.enabled and not self.rt.editor_only:
                self._task = asyncio.create_task(self._watch(settings.source))

    async def close(self) -> None:
        async with self._lock:
            await self._stop()
            await self._publish(Track())

    async def _stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None

    async def _publish(self, track: Track) -> None:
        if track != self._track:
            self._track = track
            await self.rt.overlays.broadcast_now_playing()

    async def _watch(self, source: str) -> None:
        while True:
            if source == BOT_SOURCE:
                title = clean_metadata(self.rt.music.now_playing_title, 110)
                track = Track("playing", title, "", "Bot") if title else Track()
            else:
                track = await mpris_track(source)
            await self._publish(track)
            await asyncio.sleep(self._interval)
