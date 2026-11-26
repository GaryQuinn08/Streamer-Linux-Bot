"""Reproducción local y síntesis, con procesos gestionados por el runtime."""
from __future__ import annotations

import asyncio
import os
import shutil
import tempfile
from pathlib import Path

AUDIO_TYPES = {".wav", ".mp3", ".ogg", ".opus", ".flac", ".m4a", ".aac"}


async def run_process(*argv: str, text: str | None = None, timeout: float = 7200) -> int:
    process = await asyncio.create_subprocess_exec(
        *argv, stdin=(asyncio.subprocess.PIPE if text is not None else asyncio.subprocess.DEVNULL),
        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        if text is not None:
            await asyncio.wait_for(process.communicate(text.encode("utf-8")), timeout)
        else:
            await asyncio.wait_for(process.wait(), timeout)
        return process.returncode
    finally:
        if process.returncode is None:
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
        self.items: asyncio.Queue[Path] = asyncio.Queue(maxsize=50)
        self.worker: asyncio.Task | None = None
        self.current = ""

    def enqueue(self, raw: str) -> None:
        path = Path(raw).expanduser().resolve()
        if path.suffix.lower() not in AUDIO_TYPES or not path.is_file():
            raise ValueError("Elige un archivo local de audio existente; no se aceptan URLs ni listas.")
        mpv = shutil.which("mpv")
        if not mpv:
            raise RuntimeError("Instala mpv para usar la cola.")
        if self.items.full():
            raise ValueError("La cola ya tiene 50 canciones pendientes.")
        self.items.put_nowait(path)
        self.rt.log(f"Música: en cola «{path.name}».")
        if self.worker is None or self.worker.done():
            self.worker = self.rt.spawn(self._play(mpv))

    async def _play(self, mpv):
        while not self.items.empty():
            path = self.items.get_nowait()
            self.current = path.name
            try:
                self.rt.log(f"Música: reproduciendo «{path.name}».")
                if await run_process(mpv, "--no-config", "--no-video", "--no-ytdl", "--", str(path)):
                    self.rt.log(f"Música: no se pudo reproducir «{path.name}».")
            except (OSError, TimeoutError):
                self.rt.log(f"Música: falló la reproducción de «{path.name}».")
            finally:
                self.current = ""
                self.items.task_done()

    async def clear(self) -> None:
        while not self.items.empty():
            self.items.get_nowait()
            self.items.task_done()
        if self.worker is not None:
            self.worker.cancel()
            await asyncio.gather(self.worker, return_exceptions=True)
            self.worker = None


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
    text = value.strip()[:300]
    if not text:
        return
    model = os.environ.get("SLB_PIPER_MODEL", "")
    if model:
        voice = Path(model).expanduser().resolve()
        piper = os.environ.get("SLB_PIPER") or shutil.which("piper")
        if piper and voice.is_file() and voice.with_suffix(".onnx.json").is_file():
            with tempfile.TemporaryDirectory() as folder:
                wav = Path(folder) / "voz.wav"
                code = await run_process(piper, "-m", str(voice), "-f", str(wav),
                                         text=text + "\n", timeout=30)
                if code == 0 and wav.is_file():
                    await play_sound(wav)
                    return
        rt.log("Piper no pudo generar la voz. Se intentará con espeak-ng.")
    fallback = shutil.which("espeak-ng")
    if fallback and await run_process(fallback, "-v", "es", "--stdin", text=text, timeout=30) == 0:
        return
    raise RuntimeError("No se encontró una voz funcional. Configura Piper o instala espeak-ng.")
