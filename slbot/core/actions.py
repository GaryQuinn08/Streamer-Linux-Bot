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
import math
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any, Awaitable, Callable

from ..audio import play_sound, say
from .config import Action
from .events import Event
from .flow import MAX_DEPTH, MAX_STEPS, VALUE_LIMIT, evaluate, validate_steps

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
    return sorted(set(_HANDLERS) | {"set_variable", "run_action", "condition"})


def build_context(ev: Event) -> dict[str, str]:
    ctx = {"user": ev.user, "platform": ev.platform, "type": ev.type}
    ctx.update({str(k): str(v) for k, v in ev.data.items()})
    return ctx


_OVERLAY_EVENT_FIELDS = ("gift_name", "count", "value", "amount", "currency", "text", "command",
                         "bits", "tier", "reward", "timer", "timer_id", "interval", "simulated")


def overlay_variables(ev: Event) -> dict[str, str | int | float | bool]:
    """El overlay elegido recibe solo campos públicos conocidos del evento."""
    values = {"user": ev.user[:100], "platform": ev.platform[:40], "type": ev.type[:80]}
    for key in _OVERLAY_EVENT_FIELDS:
        value = ev.data.get(key)
        if isinstance(value, str):
            values[key] = value[:500]
        elif type(value) in (int, bool) or (type(value) is float and math.isfinite(value)):
            values[key] = value
    return values


def render(value: Any, ctx: dict[str, str]) -> Any:
    """Sustituye {variables} en cadenas. Las variables desconocidas se dejan tal cual."""
    if not isinstance(value, str):
        return value
    return _TEMPLATE.sub(lambda m: ctx.get(m.group(1), m.group(0)), value)


class _StepLimit(ValueError):
    pass


async def run_action(rt: "Runtime", action: Action, ev: Event) -> int:
    ctx = {key: value for key, value in build_context(ev).items() if not key.startswith("local_")}
    actions = None
    remaining = MAX_STEPS
    failures = 0
    # El hijo comparte esta ejecución: no vuelve a entrar en el planificador de colas.
    async def execute(current: Action, path: tuple[str, ...]) -> None:
        nonlocal actions, remaining, failures
        for index, step in enumerate(current.steps, start=1):
            if not remaining:
                raise _StepLimit("Se alcanzó el límite de pasos de una ejecución.")
            remaining -= 1
            step_type = step.get("type")
            try:
                if step_type in ("set_variable", "run_action", "condition"):
                    validate_steps([step])
                    if step_type == "set_variable":
                        key = "local_" + step["key"]
                        ctx[key] = render(step.get("value", ""), ctx)[:VALUE_LIMIT]
                        continue
                    if step_type == "run_action":
                        target = step["action_id"]
                    else:
                        template = step.get("value", "")
                        known = all(m.group(1) in ctx for m in _TEMPLATE.finditer(template))
                        condition = evaluate(step["key"], step["operator"], render(template, ctx), ctx,
                                             expected_known=known)
                        target = step.get("then_id" if condition else "else_id")
                    if not target:
                        continue
                    if target in path:
                        raise ValueError("Se detuvo una llamada circular.")
                    if len(path) >= MAX_DEPTH:
                        raise ValueError("Se alcanzó el límite de 12 acciones anidadas.")
                    if actions is None:
                        actions = {item.id: item for item in rt.config.actions}
                    child = actions.get(target)
                    if child is None:
                        raise ValueError("La acción seleccionada no existe.")
                    await execute(child, (*path, target))
                    continue
                handler = _HANDLERS.get(str(step_type))
                if handler is None:
                    raise ValueError(f"tipo desconocido '{step_type}'")
                literal = {"play_sound": {"file"}, "music_queue_add": {"query"}}.get(str(step_type), set())
                params = {k: (v if k in literal else render(v, ctx)) for k, v in step.items() if k != "type"}
                if step_type in ("obs_scene", "obs_source_visible"):
                    # No liberar el bloqueo de OBS antes de concluir la solicitud en curso.
                    request = asyncio.create_task(handler(rt, params, ev))
                    try:
                        await asyncio.shield(request)
                    except asyncio.CancelledError:
                        await asyncio.gather(request, return_exceptions=True)
                        raise
                else:
                    await handler(rt, params, ev)
            except _StepLimit:
                raise
            except Exception as exc:  # un paso que falla no cancela los siguientes
                failures += 1
                rt.log(f"[{current.name}] paso {index} ({step_type}) falló: {exc}")

    try:
        await execute(action, (action.id,))
    except _StepLimit as exc:
        rt.log(f"[{action.name}] {exc}")
        failures += 1
    return failures


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
            "variables": overlay_variables(ev),
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


@subaction("play_sound")
async def _play_sound(rt: "Runtime", p: dict[str, Any], ev: Event) -> None:
    await play_sound(Path(str(p.get("file", ""))))


@subaction("tts")
async def _tts(rt: "Runtime", p: dict[str, Any], ev: Event) -> None:
    await say(rt, str(p.get("text", "")))


@subaction("music_queue_add")
async def _music_queue_add(rt: "Runtime", p: dict[str, Any], ev: Event) -> None:
    rt.music.enqueue(str(p.get("query", "")))


@subaction("chat_message")
async def _chat_message(rt: "Runtime", p: dict[str, Any], ev: Event) -> None:
    raise ValueError("El envío a chat no está habilitado en esta beta.")
