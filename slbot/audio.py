"""Reproducción local y síntesis, con procesos gestionados por el runtime."""
from __future__ import annotations

import asyncio
import ipaddress
import os
import re
import socket
import shutil
import tempfile
from dataclasses import dataclass
from itertools import count
from pathlib import Path

import aiohttp
from yarl import URL

AUDIO_TYPES = {".wav", ".mp3", ".ogg", ".opus", ".flac", ".m4a", ".aac"}
_REMOTE_LIMIT = 48 * 1024 * 1024
_PUBLIC_DNS_NAME = re.compile(
    r"(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,63}\Z"
)
_REMOTE_FORMATS = {
    "audio/mpeg": ("mp3", ".mp3"),
    "audio/mp3": ("mp3", ".mp3"),
    "audio/wav": ("wav", ".wav"),
    "audio/x-wav": ("wav", ".wav"),
    "audio/flac": ("flac", ".flac"),
    "audio/x-flac": ("flac", ".flac"),
    "audio/ogg": ("ogg", ".ogg"),
    "application/ogg": ("ogg", ".ogg"),
}


class VoiceError(RuntimeError):
    """A fixed, user-facing diagnostic without chat text or subprocess output."""


class HostedAudioError(ValueError):
    """Error de validación apto para mostrar sin exponer la URL."""


@dataclass(frozen=True)
class HostedAudio:
    url: URL

    @property
    def name(self) -> str:
        # Never show paths or query parameters, which can contain signed URLs.
        return f"Audio de {self.url.raw_host}"


def licensed_audio(raw: str) -> HostedAudio:
    raw = raw.strip()
    if len(raw) > 2048 or any(c.isspace() for c in raw):
        raise ValueError("Pega una URL HTTPS directa al archivo de audio.")
    try:
        url = URL(raw)
        allowed = (
            url.scheme == "https" and url.port == 443 and url.user is None
            and not url.fragment and url.raw_host
            and _PUBLIC_DNS_NAME.fullmatch(url.raw_host)
        )
    except (UnicodeError, ValueError):
        allowed = False
    if not allowed:
        raise ValueError("Usa una URL HTTPS directa de un dominio público, sin credenciales ni puertos especiales.")
    return HostedAudio(url)


class PublicAudioResolver(aiohttp.abc.AbstractResolver):
    """Filtra el resultado que usará el conector, sin resolverlo por segunda vez."""

    def __init__(self):
        self._resolver = aiohttp.resolver.DefaultResolver()

    async def resolve(self, host, port=0, family=socket.AF_UNSPEC):
        answers = await self._resolver.resolve(host, port, family)
        public = []
        for answer in answers:
            ip = ipaddress.ip_address(answer["host"])
            mapped = ip.ipv4_mapped if isinstance(ip, ipaddress.IPv6Address) else None
            ip = mapped or ip
            if ip.is_global and not (ip.is_multicast or ip.is_reserved or ip.is_loopback or ip.is_link_local):
                public.append(answer)
        if not public:
            raise OSError("El enlace no apunta a una dirección pública.")
        return public

    async def close(self):
        await self._resolver.close()


def _matches_audio(format_name: str, data: bytes) -> bool:
    if format_name == "mp3":
        return data.startswith(b"ID3") or (len(data) > 3 and data[0] == 255 and data[1] & 224 == 224)
    if format_name == "wav":
        return data[:4] in (b"RIFF", b"RF64") and data[8:12] == b"WAVE"
    if format_name == "flac":
        return data.startswith(b"fLaC")
    return data.startswith(b"OggS") and (b"OpusHead" in data[:256] or b"\x01vorbis" in data[:256])


async def _download_audio(item: HostedAudio, folder: Path) -> tuple[Path, str]:
    resolver = PublicAudioResolver()
    try:
        # Do not use a proxy from the environment and do not follow redirects.
        connector = aiohttp.TCPConnector(resolver=resolver, use_dns_cache=False)
        timeout = aiohttp.ClientTimeout(total=60, sock_connect=10, sock_read=12)
        async with aiohttp.ClientSession(
            connector=connector, timeout=timeout, trust_env=False, auto_decompress=False,
        ) as session:
            async with session.get(item.url, allow_redirects=False, headers={"Accept-Encoding": "identity"}) as response:
                metadata = _REMOTE_FORMATS.get(response.content_type)
                if response.status != 200 or not metadata:
                    raise HostedAudioError("El proveedor no sirvió un archivo directo compatible (MP3, WAV, FLAC u Ogg).")
                if response.headers.get("Content-Encoding", "identity").lower() != "identity":
                    raise HostedAudioError("El proveedor no entregó el archivo en un formato directo.")
                if response.content_length is not None and response.content_length > _REMOTE_LIMIT:
                    raise HostedAudioError("El archivo supera el límite de 48 MiB por pista.")
                format_name, suffix = metadata
                first = await response.content.readexactly(256)
                if not _matches_audio(format_name, first):
                    raise HostedAudioError("El contenido no coincide con un formato de audio permitido.")
                target = folder / f"pista{suffix}"
                total = len(first)
                with target.open("xb") as file:
                    file.write(first)
                    async for chunk in response.content.iter_chunked(65536):
                        total += len(chunk)
                        if total > _REMOTE_LIMIT:
                            raise HostedAudioError("El archivo supera el límite de 48 MiB por pista.")
                        file.write(chunk)
                return target, format_name
    except asyncio.IncompleteReadError:
        raise HostedAudioError("El proveedor devolvió un archivo vacío o incompleto.") from None
    finally:
        await resolver.close()



async def run_process(*argv: str, text: str | None = None, timeout: float = 7200) -> int:
    process = None
    spawn = asyncio.create_task(asyncio.create_subprocess_exec(
        *argv, stdin=(asyncio.subprocess.PIPE if text is not None else asyncio.subprocess.DEVNULL),
        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
    ))
    try:
        try:
            process = await asyncio.shield(spawn)
        except asyncio.CancelledError:
            # Creation may already have started the child before it returns its transport.
            # Recover the process handle so stopping voice still terminates it.
            try:
                process = await spawn
            except Exception:
                pass
            raise
        if text is not None:
            await asyncio.wait_for(process.communicate(text.encode("utf-8")), timeout)
        else:
            await asyncio.wait_for(process.wait(), timeout)
        return process.returncode
    finally:
        if process is not None and process.returncode is None:
            try:
                process.terminate()
            except ProcessLookupError:
                pass
            try:
                await asyncio.wait_for(process.wait(), 2)
            except TimeoutError:
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
                await process.wait()


class MusicQueue:
    def __init__(self, rt):
        self.rt = rt
        self.items: asyncio.Queue[tuple[int, Path | HostedAudio]] = asyncio.Queue(maxsize=50)
        self._ids = count()
        self._pending: tuple[tuple[int, str], ...] = ()
        self.worker: asyncio.Task | None = None
        self.current = ""
        self.last_error = ""

    def enqueue(self, raw: str) -> None:
        path = Path(raw).expanduser().resolve()
        if path.suffix.lower() not in AUDIO_TYPES or not path.is_file():
            raise ValueError("Elige un archivo local de audio existente; usa Agregar enlace para audio en línea.")
        self._enqueue(path)

    def enqueue_url(self, raw: str) -> None:
        # Only the manual music panel calls this. Never route chat or triggers here.
        self._enqueue(licensed_audio(raw))

    def _enqueue(self, track: Path | HostedAudio) -> None:
        mpv = shutil.which("mpv")
        if not mpv:
            raise RuntimeError("Instala mpv para usar la cola.")
        if self.items.full():
            raise ValueError("La cola ya tiene 50 canciones pendientes.")
        ident = next(self._ids)
        self.items.put_nowait((ident, track))
        self._pending += ((ident, track.name),)
        self.rt.log(f"Música: en cola «{track.name}».")
        if self.worker is None or self.worker.done():
            self.worker = self.rt.spawn(self._play(mpv))

    async def _play(self, mpv):
        while not self.items.empty():
            ident, track = self.items.get_nowait()
            self._pending = tuple(item for item in self._pending if item[0] != ident)
            self.current = track.name
            self.last_error = ""
            error = ""
            try:
                if isinstance(track, HostedAudio):
                    with tempfile.TemporaryDirectory(prefix="slb-audio-") as folder:
                        path, format_name = await _download_audio(track, Path(folder))
                        self.rt.log(f"Música: reproduciendo «{track.name}».")
                        code = await run_process(
                            mpv, "--no-config", "--no-video", "--no-ytdl", "--load-unsafe-playlists=no",
                            "--demuxer=lavf", f"--demuxer-lavf-format={format_name}",
                            "--demuxer-lavf-o=protocol_whitelist=file", "--", str(path),
                        )
                else:
                    self.rt.log(f"Música: reproduciendo «{track.name}».")
                    code = await run_process(mpv, "--no-config", "--no-video", "--no-ytdl", "--", str(track))
                if code:
                    error = f"No se pudo reproducir «{track.name}»."
            except HostedAudioError as exc:
                error = str(exc)
            except (OSError, TimeoutError, aiohttp.ClientError, ValueError):
                error = f"Falló la reproducción de «{track.name}»."
            finally:
                if error:
                    self.rt.log(f"Música: {error}")
                if self.worker is asyncio.current_task():
                    self.last_error = error
                    self.current = ""
                self.items.task_done()

    def pending(self) -> tuple[tuple[int, str], ...]:
        return self._pending

    async def remove(self, ident: int) -> None:
        if not any(item[0] == ident for item in self._pending):
            raise ValueError("El audio ya no está pendiente. Para detener la reproducción, usa Detener y vaciar.")
        items = [self.items.get_nowait() for _ in range(self.items.qsize())]
        for item in items:
            if item[0] != ident:
                self.items.put_nowait(item)
        for _ in items:
            self.items.task_done()
        self._pending = tuple(item for item in self._pending if item[0] != ident)

    async def clear(self) -> None:
        while not self.items.empty():
            self.items.get_nowait()
            self.items.task_done()
        self._pending = ()
        worker, self.worker = self.worker, None
        self.last_error = ""
        self.current = ""
        if worker is not None:
            worker.cancel()
            await asyncio.gather(worker, return_exceptions=True)


async def play_sound(path: Path) -> None:
    path = path.expanduser().resolve()
    if not path.is_file() or path.suffix.lower() not in AUDIO_TYPES:
        raise ValueError("No existe el archivo de audio o su formato no está admitido.")
    commands = (
        ("mpv", "--no-config", "--no-video", "--no-ytdl", "--", str(path)),
        ("ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", str(path)),
        ("paplay", str(path)), ("pw-play", str(path)), ("aplay", str(path)),
    )
    for name, *args in commands:
        exe = shutil.which(name)
        if exe and await run_process(exe, *args) == 0:
            return
    raise RuntimeError("No se pudo reproducir el audio; instala mpv y revisa la salida de audio.")


async def say(rt, value: str) -> None:
    # Automatic chat shares the same synthesizer with manually configured TTS steps.
    # Keep the registration API and the same local voice for both paths.
    lock = getattr(rt, "voice_lock", None)
    if lock is None:
        await _say(rt, value)
    else:
        async with lock:
            await _say(rt, value)


async def _voice_command(*argv: str, text: str | None = None, timeout: float = 10) -> bool:
    try:
        return await run_process(*argv, text=text, timeout=timeout) == 0
    except (OSError, TimeoutError):
        return False


async def _play_voice(wav: Path) -> None:
    commands = (
        ("paplay", str(wav)), ("pw-play", str(wav)),
        ("mpv", "--no-config", "--no-video", "--no-ytdl", "--", str(wav)),
        ("ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", str(wav)),
        ("aplay", str(wav)),
    )
    available = False
    for name, *args in commands:
        if exe := shutil.which(name):
            available = True
            if await _voice_command(exe, *args, timeout=35):
                return
    if not available:
        raise VoiceError("La voz se generó, pero falta un reproductor de audio. En Mint, Ubuntu o Debian, "
                         "vuelve a ejecutar el instalador con --voz.")
    raise VoiceError("La voz se generó, pero no se pudo enviar a una salida de audio. "
                     "Revisa la salida seleccionada en Sonido del sistema y pulsa «Probar voz» de nuevo.")


def _has_voice_wav(path: Path) -> bool:
    try:
        return path.is_file() and path.stat().st_size > 44
    except OSError:
        return False


async def _say(rt, value: str) -> None:
    text = value.strip()[:300]
    if not text:
        return
    with tempfile.TemporaryDirectory() as folder:
        wav = Path(folder) / "voz.wav"
        model = os.environ.get("SLB_PIPER_MODEL", "")
        if model:
            voice = Path(model).expanduser().resolve()
            piper = os.environ.get("SLB_PIPER") or shutil.which("piper")
            if (piper and voice.is_file() and voice.with_suffix(".onnx.json").is_file()
                    and await _voice_command(piper, "-m", str(voice), "-f", str(wav),
                                             text=text + "\n", timeout=15) and _has_voice_wav(wav)):
                await _play_voice(wav)
                return
            wav.unlink(missing_ok=True)
            rt.log("Piper no pudo generar la voz. Se intentará con eSpeak NG.")
        fallback = shutil.which("espeak-ng")
        if not fallback:
            raise VoiceError("Falta la voz local eSpeak NG. En Mint, Ubuntu o Debian, "
                             "vuelve a ejecutar el instalador con --voz.")
        if (not await _voice_command(fallback, "-v", "es", "-w", str(wav), "--stdin", text=text)
                or not _has_voice_wav(wav)):
            raise VoiceError("eSpeak NG está instalado, pero no pudo generar la voz en español. "
                             "Revisa la instalación de espeak-ng y sus datos de voz.")
        await _play_voice(wav)
