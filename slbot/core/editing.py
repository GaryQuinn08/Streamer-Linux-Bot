"""Validación compartida de las reglas editables."""
from __future__ import annotations

import copy
from uuid import uuid4

from .config import Action, Config, Trigger
from .timers import read_timers, without_timers

# key, label, type, default. Requests use only the action types listed here.
STEP_FIELDS = {
    "overlay_alert": ("Mostrar alerta", (
        ("overlay", "Alerta", "overlay", "gift-alert"), ("title", "Título", "text", "{user}"),
        ("text", "Mensaje", "text", ""), ("image", "URL de imagen (opcional)", "text", ""))),
    "obs_scene": ("Cambiar escena de OBS", (("scene", "Escena", "required", ""),)),
    "obs_source_visible": ("Mostrar u ocultar fuente de OBS", (
        ("scene", "Escena", "required", ""), ("source", "Fuente", "required", ""),
        ("visible", "Visible", "bool", True))),
    "play_sound": ("Reproducir sonido", (("file", "Archivo", "file", ""),)),
    "tts": ("Leer texto (TTS)", (("text", "Texto", "required", "{text}"),)),
    "music_queue_add": ("Encolar canción local", (("query", "Archivo", "file", ""),)),
    "wait": ("Esperar", (("seconds", "Segundos", "number", 1),)),
    "log": ("Escribir en Registro", (("message", "Mensaje", "text", "{platform}: {type}"),)),
}


def action_references(config: Config, action_id: str):
    return ([item for item in config.triggers if item.action_id == action_id],
            [item for item in read_timers(config.settings) if item.action_id == action_id])


def update_rules(config: Config, kind: str, data: dict, *, delete: bool = False) -> None:
    """Guarda antes de publicar el nuevo estado; la ruta y los ajustes no se cambian."""
    name = str(data.get("name", "")).strip()
    ident = data.get("id") or uuid4().hex
    if not delete and not name:
        raise ValueError("Escribe un nombre.")
    actions = copy.deepcopy(config.actions)
    triggers = copy.deepcopy(config.triggers)
    settings = config.settings
    if kind == "action":
        if delete:
            trigger_refs, timer_refs = action_references(config, ident)
            expected = {"triggers": sorted({t.id for t in trigger_refs}), "timers": sorted({t.id for t in timer_refs})}
            confirmation = data.get("confirmed_dependencies")
            if confirmation is not None and confirmation != expected:
                raise ValueError("Los disparadores o temporizadores vinculados cambiaron. Vuelve a confirmar la eliminación.")
            if (trigger_refs or timer_refs) and confirmation is None:
                raise ValueError("La acción todavía se utiliza en: " + ", ".join(t.name for t in [*trigger_refs, *timer_refs]))
            if trigger_refs:
                triggers = [t for t in triggers if t.action_id != ident]
            settings = without_timers(settings, set(expected["timers"]))
            actions = [a for a in actions if a.id != ident]
        else:
            action = Action.from_dict({**data, "id": ident, "name": name})
            if not action.steps and not any(a.id == ident for a in actions):
                raise ValueError("Agrega al menos un paso.")
            actions = _upsert(actions, action)
    elif kind == "trigger":
        if delete:
            triggers = [t for t in triggers if t.id != ident]
        else:
            trigger = Trigger.from_dict({**data, "id": ident, "name": name})
            if not trigger.event_type or not any(a.id == trigger.action_id for a in actions):
                raise ValueError("Elige un evento y una acción existente.")
            triggers = _upsert(triggers, trigger)
    else:
        raise ValueError("Tipo de regla inválido.")
    Config(settings=settings, actions=actions, triggers=triggers, path=config.path).save()
    config.actions, config.triggers, config.settings = actions, triggers, settings


def _upsert(items: list, replacement) -> list:
    for i, existing in enumerate(items):
        if existing.id == replacement.id:
            items[i] = replacement
            break
    else:
        items.append(replacement)
    return items
