"""Intercambio nativo y validado de acciones; sin perfil, credenciales ni código."""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, replace
from pathlib import Path
from uuid import uuid4

from .config import Action, Config, Trigger
from .editing import STEP_FIELDS
from .flow import REF_FIELDS, references, validate_links, validate_steps

FORMAT = "streamer-linux-bot-actions"
MAX_BYTES = 256 * 1024
_FILES = {"play_sound", "music_queue_add"}
_FILTERS = {"min_value", "gift_name", "user", "contains", "command", "command_aliases"}


def _text(value, max_length=160):
    return isinstance(value, str) and 0 < len(value.strip()) <= max_length and value.isprintable()


@dataclass(frozen=True)
class ActionPack:
    actions: tuple[Action, ...]
    triggers: tuple[Trigger, ...]

    @classmethod
    def read(cls, source: Path):
        with source.open("rb") as file:
            raw = file.read(MAX_BYTES + 1)
        return cls.parse(raw)

    @classmethod
    def parse(cls, raw: bytes):
        if len(raw) > MAX_BYTES:
            raise ValueError("El paquete de acciones supera 256 KiB.")
        try:
            data = json.loads(raw.decode("utf-8"), parse_constant=lambda _token: _reject())
        except (ValueError, RecursionError):
            raise ValueError("El paquete no contiene JSON válido.") from None
        if not isinstance(data, dict) or data.get("format") != FORMAT or type(data.get("version")) is not int or data["version"] != 1:
            raise ValueError("Selecciona un paquete nativo .slbactions, versión 1.")
        raw_actions, raw_triggers = data.get("actions"), data.get("triggers")
        if not isinstance(raw_actions, list) or not 1 <= len(raw_actions) <= 50 or (
            not isinstance(raw_triggers, list) or len(raw_triggers) > 100
        ):
            raise ValueError("El paquete admite de 1 a 50 acciones y hasta 100 disparadores.")
        actions = []
        ids = set()
        for item in raw_actions:
            if not isinstance(item, dict) or not _text(item.get("name"), 120) or not _text(item.get("id"), 100):
                raise ValueError("El paquete contiene una acción inválida.")
            action = Action.from_dict(item)
            if action.id in ids or len(action.steps) > 100:
                raise ValueError("El paquete repite un ID o una acción supera 100 subacciones.")
            ids.add(action.id)
            for step in action.steps:
                kind = step.get("type")
                if not isinstance(kind, str) or kind not in STEP_FIELDS or kind in _FILES:
                    raise ValueError("El paquete incluye un paso no compatible o que requiere un archivo local.")
                expected = {key: (mode, default) for key, _label, mode, default in STEP_FIELDS[kind][1]}
                if any(key not in {"type", "id", *expected} for key in step):
                    raise ValueError("El paquete utiliza campos de subacción desconocidos.")
                for key, (mode, default) in expected.items():
                    value = step.get(key, default)
                    if mode == "bool":
                        valid = type(value) is bool
                    elif mode in {"number", "db"}:
                        low, high = (-100, 0) if mode == "db" else (0, 3600)
                        valid = type(value) in {int, float} and low <= value <= high
                    else:
                        valid = isinstance(value, str) and len(value) <= 4096
                        if mode in {"required", "action", "overlay"}:
                            valid = valid and bool(value.strip())
                    if not valid:
                        raise ValueError("El paquete contiene un valor de subacción inválido.")
                    step[key] = value
                step.pop("id", None)
            validate_steps(action.steps)
            actions.append(action)
        for action in actions:
            validate_links(action, actions)
        triggers = []
        for item in raw_triggers:
            if not isinstance(item, dict) or not all(_text(item.get(key), limit) for key, limit in
                    (("id", 100), ("event_type", 100), ("name", 120), ("action_id", 100))):
                raise ValueError("El paquete contiene un disparador inválido.")
            filters = item.get("filters", {})
            if not isinstance(filters, dict) or not filters.keys() <= _FILTERS or any(
                not ((isinstance(value, str) and len(value) <= 4096) or
                     (type(value) in {int, float} and -1e100 <= value <= 1e100))
                for key, value in filters.items() if key != "command_aliases"
            ):
                raise ValueError("El paquete utiliza filtros no compatibles.")
            if "min_value" in filters:
                try:
                    if not math.isfinite(float(filters["min_value"])) or float(filters["min_value"]) < 0:
                        raise ValueError()
                except (ValueError, OverflowError):
                    raise ValueError("El valor mínimo de un disparador no es válido.") from None
            try:
                trigger = Trigger.from_dict(item)
            except (KeyError, ValueError, TypeError, OverflowError):
                raise ValueError("El paquete contiene un disparador inválido.") from None
            if trigger.action_id not in ids:
                raise ValueError("Un disparador apunta a una acción no incluida.")
            triggers.append(trigger)
        return cls(tuple(actions), tuple(triggers))

    @classmethod
    def export_selected(cls, config: Config, selected: str) -> bytes:
        known = {item.id: item for item in config.actions}
        found = {}
        pending = [selected]
        while pending:
            ident = pending.pop()
            if ident in found:
                continue
            if ident not in known:
                raise ValueError("Una acción referenciada no existe.")
            action = known[ident]
            found[ident] = action.to_dict()
            if len(found) > 50:
                raise ValueError("El paquete supera 50 acciones vinculadas.")
            pending.extend(reversed(list(references(action.steps))))
        data = {"format": FORMAT, "version": 1, "actions": list(found.values()),
                "triggers": [t.to_dict() for t in config.triggers if t.action_id in found]}
        raw = json.dumps(data, indent=2, ensure_ascii=False).encode() + b"\n"
        cls.parse(raw)
        return raw

    def install(self, config: Config) -> str:
        mapping = {action.id: uuid4().hex for action in self.actions}
        names = {item.name.casefold() for item in config.actions}
        appended = []
        for action in self.actions:
            name = action.name
            suffix = 1
            while name.casefold() in names:
                ending = f" (importada {suffix})"
                name = action.name[:120 - len(ending)] + ending
                suffix += 1
            names.add(name.casefold())
            steps = []
            for step in action.steps:
                patched = dict(step)
                for key in REF_FIELDS.get(step["type"], ()):
                    if patched.get(key):
                        patched[key] = mapping[patched[key]]
                steps.append(patched)
            appended.append(replace(action, id=mapping[action.id], name=name, steps=steps))
        triggers = [replace(trigger, id=uuid4().hex, action_id=mapping[trigger.action_id], enabled=False)
                    for trigger in self.triggers]
        new_actions, new_triggers = [*config.actions, *appended], [*config.triggers, *triggers]
        Config(settings=config.settings, actions=new_actions, triggers=new_triggers, path=config.path).save()
        config.actions, config.triggers = new_actions, new_triggers
        return appended[0].id


def _reject():
    raise ValueError("Solo se admiten números finitos en JSON.")
