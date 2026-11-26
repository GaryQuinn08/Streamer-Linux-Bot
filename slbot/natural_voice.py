"""Install a pinned Piper voice; synthesize local PCM without sending text off-device."""
from __future__ import annotations

import argparse
import hashlib
import os
import sys
import tempfile
import urllib.request
import wave
from pathlib import Path

VOICE_ID = "es_MX-claude-high"
VOICE_LABEL = "Claude (español de México)"
_COMMIT = "c10ece1aade47bb51c153c893d14e5bf8e5b7117"
_BASE = f"https://huggingface.co/rhasspy/piper-voices/resolve/{_COMMIT}/es/es_MX/claude/high/"
_FILES = {
    VOICE_ID + ".onnx": (63122309, "3ef40a71ea63852cd8ab7e6fa7d2ecdcfa67a0b47c9c48e3f10e02ee02083ea0"),
    VOICE_ID + ".onnx.json": (4963, "1afc81f703c0e4cb3b4d7c0dca096b8b54a98806807f0170cf5eb5557723c12d"),
}


def voice_folder() -> Path:
    root = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return root / "streamer-linux-bot" / "voices" / VOICE_ID


def enabled() -> bool:
    return (Path(sys.prefix) / ".slb-natural-voice").is_file()


class _HttpsOnly(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not newurl.startswith("https://"):
            raise OSError("La descarga de voz intentó salir de HTTPS.")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _verified(path: Path, length: int, digest: str) -> bool:
    if not path.is_file() or path.stat().st_size != length:
        return False
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest() == digest


def install_model() -> None:
    folder = voice_folder()
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    opener = urllib.request.build_opener(_HttpsOnly())
    for name, (length, digest) in _FILES.items():
        path = folder / name
        if _verified(path, length, digest):
            continue
        with tempfile.NamedTemporaryFile(dir=folder, delete=False) as tmp:
            staged = Path(tmp.name)
            try:
                size = 0
                hasher = hashlib.sha256()
                with opener.open(_BASE + name + "?download=true", timeout=45) as response:
                    while chunk := response.read(1024 * 1024):
                        size += len(chunk)
                        if size > length:
                            raise ValueError("La descarga de la voz es más grande de lo esperado.")
                        hasher.update(chunk)
                        tmp.write(chunk)
                if size != length or hasher.hexdigest() != digest:
                    raise ValueError("No pasó la verificación de integridad de la voz.")
                tmp.close()
                staged.replace(path)
            finally:
                staged.unlink(missing_ok=True)


def render(path: Path) -> None:
    # Imports are optional and only run inside the isolated synthesis process.
    import onnxruntime
    from piper import PiperVoice

    onnxruntime.disable_telemetry_events()
    voice = PiperVoice.load(voice_folder() / (VOICE_ID + ".onnx"), use_cuda=False)
    with wave.open(str(path), "wb") as wav:
        voice.synthesize_wav(sys.stdin.read(320).strip(), wav)
    if path.stat().st_size <= 44:
        raise ValueError("Piper no generó una muestra de voz.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    work = parser.add_mutually_exclusive_group(required=True)
    work.add_argument("--descargar", action="store_true")
    work.add_argument("--generar", type=Path, metavar="WAV")
    args = parser.parse_args()
    try:
        if args.descargar:
            install_model()
        else:
            render(args.generar)
    except (OSError, ValueError, RuntimeError, ImportError) as exc:
        raise SystemExit(f"No se pudo preparar la voz natural: {exc}") from None


if __name__ == "__main__":
    main()
