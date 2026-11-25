"""Configuración persistente: ajustes, triggers y acciones (JSON)."""
from __future__ import annotations

import copy
import json
import logging
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..paths import config_dir
from .events import Event

log = logging.getLogger("slb.config")


@dataclass
class Trigger:
    """Un evento (con filtros) que dispara una acción."""

    id: str
    event_type: str
    action_id: str
    name: str = ""
    enabled: bool = True
    platform: str = "*"  # "*" = cualquier plataforma
    filters: dict[str, Any] = field(default_factory=dict)
    cooldown_s: float = 0.0

    def matches(self, ev: Event) -> bool:
        if self.platform not in ("*", ev.platform):
            return False
        if self.event_type != ev.type:
            return False
        f = self.filters
        try:
            if "min_value" in f and float(ev.data.get("value", 0) or 0) < float(f["min_value"]):
                return False
        except (TypeError, ValueError):
            return False
        if "gift_name" in f and str(ev.data.get("gift_name", "")).lower() != str(f["gift_name"]).lower():
            return False
        if "user" in f and ev.user.lower() != str(f["user"]).lower():
            return False
        if "contains" in f and str(f["contains"]).lower() not in str(ev.data.get("text", "")).lower():
            return False
        if "command" in f and str(ev.data.get("command", "")).lower() != str(f["command"]).lower():
            return False
        return True

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Trigger":
        return cls(
            id=str(d["id"]),
            event_type=str(d["event_type"]),
            action_id=str(d["action_id"]),
            name=str(d.get("name", d["id"])),
            enabled=bool(d.get("enabled", True)),
            platform=str(d.get("platform", "*")),
            filters=dict(d.get("filters", {})),
            cooldown_s=float(d.get("cooldown_s", 0)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "enabled": self.enabled,
            "platform": self.platform,
            "event_type": self.event_type,
            "filters": self.filters,
            "cooldown_s": self.cooldown_s,
            "action_id": self.action_id,
        }


@dataclass
class Action:
    """Lista ordenada de pasos (sub-acciones) que se ejecutan en secuencia."""

    id: str
    name: str = ""
    steps: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Action":
        return cls(id=str(d["id"]), name=str(d.get("name", d["id"])), steps=list(d.get("steps", [])))

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name, "steps": self.steps}


DEFAULT_SETTINGS: dict[str, Any] = {
    "overlay_port": 8765,
    "obs": {"host": "127.0.0.1", "port": 4455, "password": "", "autoconnect": False},
}

DEFAULT_ACTIONS: list[dict[str, Any]] = [
    {
        "id": "alert-gift",
        "name": "Alerta de regalo",
        "steps": [
            {"type": "overlay_alert", "overlay": "gift-alert", "title": "{user} envió {gift_name}", "text": "x{count}"},
            {"type": "log", "message": "Regalo de {user}: {gift_name} x{count}"},
        ],
    },
    {
        "id": "alert-follow",
        "name": "Alerta de seguidor",
        "steps": [
            {"type": "overlay_alert", "overlay": "gift-alert", "title": "{user}", "text": "¡Nuevo seguidor!"},
        ],
    },
    {
        "id": "alert-donation",
        "name": "Alerta de donación",
        "steps": [
            {"type": "overlay_alert", "overlay": "gift-alert", "title": "{user} donó {amount} {currency}", "text": "{text}"},
        ],
    },
]

DEFAULT_TRIGGERS: list[dict[str, Any]] = [
    {"id": "tiktok-gift", "name": "Regalo de TikTok", "platform": "tiktok", "event_type": "gift",
     "filters": {"min_value": 1}, "cooldown_s": 0, "action_id": "alert-gift"},
    {"id": "any-follow", "name": "Nuevo seguidor", "platform": "*", "event_type": "follow",
     "filters": {}, "cooldown_s": 0, "action_id": "alert-follow"},
    {"id": "any-donation", "name": "Donación", "platform": "*", "event_type": "donation",
     "filters": {}, "cooldown_s": 0, "action_id": "alert-donation"},
]


def _merge(base: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(base)
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


@dataclass
class Config:
    settings: dict[str, Any] = field(default_factory=lambda: copy.deepcopy(DEFAULT_SETTINGS))
    triggers: list[Trigger] = field(default_factory=list)
    actions: list[Action] = field(default_factory=list)
    path: Path | None = None

    def action_by_id(self, action_id: str) -> Action | None:
        return next((a for a in self.actions if a.id == action_id), None)

    @classmethod
    def defaults(cls) -> "Config":
        return cls(
            settings=copy.deepcopy(DEFAULT_SETTINGS),
            triggers=[Trigger.from_dict(t) for t in DEFAULT_TRIGGERS],
            actions=[Action.from_dict(a) for a in DEFAULT_ACTIONS],
        )

    @classmethod
    def load(cls, path: Path | None = None) -> "Config":
        path = path or (config_dir() / "config.json")
        if not path.exists():
            cfg = cls.defaults()
            cfg.path = path
            cfg.save()
            return cfg
        try:
            raw = json.loads(path.read_text("utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            backup = path.with_suffix(".json.bak")
            shutil.copy2(path, backup)
            log.error("Configuración ilegible (%s). Copia en %s; se usan valores por defecto.", exc, backup)
            cfg = cls.defaults()
            cfg.path = path
            return cfg

        cfg = cls(settings=_merge(DEFAULT_SETTINGS, raw.get("settings", {})), path=path)
        for item in raw.get("triggers", []):
            try:
                cfg.triggers.append(Trigger.from_dict(item))
            except (KeyError, TypeError, ValueError):
                log.warning("Trigger inválido omitido: %r", item)
        for item in raw.get("actions", []):
            try:
                cfg.actions.append(Action.from_dict(item))
            except (KeyError, TypeError, ValueError):
                log.warning("Acción inválida omitida: %r", item)
        return cfg

    def save(self, path: Path | None = None) -> None:
        path = path or self.path or (config_dir() / "config.json")
        data = {
            "settings": self.settings,
            "triggers": [t.to_dict() for t in self.triggers],
            "actions": [a.to_dict() for a in self.actions],
        }
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), "utf-8")
        os.chmod(tmp, 0o600)  # puede contener la contraseña de OBS
        tmp.replace(path)
        self.path = path
