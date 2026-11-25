"""Sub-acciones: los pasos que puede ejecutar una acción.

Para añadir un paso nuevo basta con registrar una función:

    @subaction("mi_paso")
    async def _mi_paso(rt, params, ev):
        ...

`params` son los valores del paso con las plantillas ya resueltas
(por ejemplo "{user}" se sustituye por el nombre del usuario del evento).
"""
from __future__ import annotations

import asyncio
import logging
import re
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Any, Awaitable, Callable

from .config import Action
from .events import Event

if TYPE_CHECKING:  # evita importaciones circulares
    from ..runtime import Runtime

log = logging.getLogger("slb.actions")

Handler = Callable[["Runtime", dict[str, Any], Event], Awaitable[None]]
_HANDLERS: dict[str, Handler] = {}

_TEMPLATE = re.compile(r"\{(\w+)\}")


def subaction(name: str) -> Callable[[Handler], Handler]:
    def decorator(fn: Handler) -> Handler:
        _HANDLERS[name] = fn
        return fn

    return decorator


def available_subactions() -> list[str]:
    return sorted(_HANDLERS)


def build_context(ev: Event) -> dict[str, str]:
    ctx = {"user": ev.user, "platform": ev.platform, "type": ev.type}
    ctx.update({str(k): str(v) for k, v in ev.data.items()})
    return ctx


def render(value: Any, ctx: dict[str, str]) -> Any:
    """Sustituye {variables} en cadenas. Las variables desconocidas se dejan tal cual."""
    if not isinstance(value, str):
        return value
    return _TEMPLATE.sub(lambda m: ctx.get(m.group(1), m.group(0)), value)


async def run_action(rt: "Runtime", action: Action, ev: Event) -> None:
    ctx = build_context(ev)
    for index, step in enumerate(action.steps, start=1):
        step_type = step.get("type")
        handler = _HANDLERS.get(str(step_type))
        if handler is None:
            rt.log(f"[{action.name}] paso {index}: tipo desconocido '{step_type}'")
            continue
        params = {k: render(v, ctx) for k, v in step.items() if k != "type"}
        try:
            await handler(rt, params, ev)
        except Exception as exc:  # un paso que falla no cancela los siguientes
            rt.log(f"[{action.name}] paso {index} ({step_type}) falló: {exc}")


# --------------------------------------------------------------------------
# Sub-acciones incluidas
# --------------------------------------------------------------------------

@subaction("log")
async def _log(rt: "Runtime", p: dict[str, Any], ev: Event) -> None:
    rt.log(str(p.get("message", "")))


@subaction("wait")
async def _wait(rt: "Runtime", p: dict[str, Any], ev: Event) -> None:
    await asyncio.sleep(max(0.0, min(float(p.get("seconds", 1)), 3600.0)))


@subaction("overlay_alert")
async def _overlay_alert(rt: "Runtime", p: dict[str, Any], ev: Event) -> None:
    overlay_id = str(p.get("overlay", "gift-alert"))
    await rt.overlays.broadcast(
        overlay_id,
        {
            "channel": "alert",
            "overlay": overlay_id,
            "title": str(p.get("title", "")),
            "text": str(p.get("text", "")),
            "image": str(p.get("image", "")),
        }
    )


@subaction("obs_scene")
async def _obs_scene(rt: "Runtime", p: dict[str, Any], ev: Event) -> None:
    await rt.obs.set_scene(str(p["scene"]))


@subaction("obs_source_visible")
async def _obs_source_visible(rt: "Runtime", p: dict[str, Any], ev: Event) -> None:
    visible = p.get("visible", True)
    if isinstance(visible, str):
        visible = visible.strip().lower() in ("1", "true", "si", "sí", "yes")
    await rt.obs.set_source_visible(str(p["scene"]), str(p["source"]), bool(visible))


async def _spawn_process(rt: "Runtime", *argv: str) -> None:
    proc = await asyncio.create_subprocess_exec(
        *argv, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL
    )
    rt.spawn(proc.wait())  # recoger el proceso sin bloquear los pasos siguientes


@subaction("play_sound")
async def _play_sound(rt: "Runtime", p: dict[str, Any], ev: Event) -> None:
    path = Path(str(p.get("file", "")))
    if not path.is_file():
        rt.log(f"play_sound: no existe el archivo {path}")
        return
    players: tuple[tuple[str, list[str]], ...] = (
        ("paplay", []),
        ("pw-play", []),
        ("mpv", ["--no-video", "--really-quiet"]),
        ("ffplay", ["-nodisp", "-autoexit", "-loglevel", "quiet"]),
        ("aplay", []),
    )
    for name, extra in players:
        exe = shutil.which(name)
        if exe:
            await _spawn_process(rt, exe, *extra, str(path))
            return
    rt.log("play_sound: no se encontró ningún reproductor (paplay, pw-play, mpv, ffplay, aplay)")


@subaction("tts")
async def _tts(rt: "Runtime", p: dict[str, Any], ev: Event) -> None:
    # TODO: sustituir por Piper cuando se integre el TTS definitivo.
    text = str(p.get("text", ""))[:300]
    if not text:
        return
    for name in ("espeak-ng", "spd-say"):
        exe = shutil.which(name)
        if exe:
            await _spawn_process(rt, exe, text)
            return
    rt.log("tts: instala espeak-ng (o configura Piper cuando esté integrado)")


@subaction("music_queue_add")
async def _music_queue_add(rt: "Runtime", p: dict[str, Any], ev: Event) -> None:
    # TODO: pendiente de decidir qué reproductor controlará la app.
    rt.log(f"music_queue_add (pendiente de implementar): {p.get('query', '')}")


@subaction("chat_message")
async def _chat_message(rt: "Runtime", p: dict[str, Any], ev: Event) -> None:
    # TODO: se enviará a través del conector de la plataforma indicada.
    rt.log(f"chat_message (pendiente de implementar) -> {p.get('platform', ev.platform)}: {p.get('text', '')}")
