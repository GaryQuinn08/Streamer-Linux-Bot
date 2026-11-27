"""Configuración persistente: ajustes, triggers y acciones (JSON)."""
from __future__ import annotations

import copy
import json
import logging
import math
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..paths import config_dir
from .events import Event
from .trigger_catalog import CHAT_PERMISSIONS

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
    user_cooldown_s: float = 0.0
    chat_permission: str = "everyone"

    def matches(self, ev: Event) -> bool:
        if self.platform not in ("*", ev.platform):
            return False
        if self.event_type != ev.type:
            return False
        if self.chat_permission != "everyone":
            roles = {"staff": ("owner", "moderator"), "owner": ("owner",)}.get(self.chat_permission, ())
            if (ev.platform not in {"twitch", "youtube"} or ev.type not in {"chat", "command"}
                    or ev.data.get("simulated") or not ev.actor_id or ev.chat_role not in roles):
                return False
        f = self.filters
        try:
            if "min_value" in f:
                value = float(ev.data.get("value", 0) or 0)
                minimum = float(f["min_value"])
                if not (math.isfinite(value) and math.isfinite(minimum) and value >= minimum):
                    return False
        except (TypeError, ValueError, OverflowError):
            return False
        if "gift_name" in f and str(ev.data.get("gift_name", "")).lower() != str(f["gift_name"]).lower():
            return False
        if "user" in f and ev.user.lower() != str(f["user"]).lower():
            return False
        if "contains" in f and str(f["contains"]).lower() not in str(ev.data.get("text", "")).lower():
            return False
        if "command" in f or "command_aliases" in f:
            command = str(ev.data.get("command", "")).casefold()
            exact = f.get("command")
            aliases = f.get("command_aliases", [])
            if not command or not (
                isinstance(exact, str) and command == exact.casefold()
                or isinstance(aliases, list)
                and any(isinstance(alias, str) and command == alias.casefold() for alias in aliases)
            ):
                return False
        return True

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Trigger":
        if not isinstance(d, dict):
            raise ValueError("Un trigger debe ser un objeto.")
        cooldown = float(d.get("cooldown_s", 0))
        user_cooldown = float(d.get("user_cooldown_s", 0))
        if not math.isfinite(cooldown) or cooldown < 0:
            raise ValueError("Cooldown inválido")
        if not math.isfinite(user_cooldown) or not 0 <= user_cooldown <= 86400:
            raise ValueError("La espera por usuario debe ser de 0 a 86 400 segundos.")
        permission = d.get("chat_permission", "everyone")
        if not isinstance(permission, str) or permission not in CHAT_PERMISSIONS:
            raise ValueError("Permiso de chat inválido.")
        if permission != "everyone" and (d.get("event_type") not in {"chat", "command"}
                                         or d.get("platform", "*") not in {"twitch", "youtube", "*"}):
            raise ValueError("Los roles solo se verifican en el chat de Twitch y YouTube.")
        filters = dict(d.get("filters", {}))
        if "command_aliases" in filters:
            aliases = filters["command_aliases"]
            if not isinstance(aliases, list) or not 1 <= len(aliases) <= 20 or any(
                not isinstance(a, str) or not 1 <= len(a) <= 40 or a.startswith("!")
                or not a.isprintable() or any(c.isspace() for c in a) for a in aliases
            ):
                raise ValueError("Escribe hasta 20 alias de una palabra de 40 caracteres, sin !.")
        return cls(
            id=str(d["id"]),
            event_type=str(d["event_type"]),
            action_id=str(d["action_id"]),
            name=str(d.get("name", d["id"])),
            enabled=bool(d.get("enabled", True)),
            platform=str(d.get("platform", "*")),
            filters=filters,
            cooldown_s=cooldown,
            user_cooldown_s=user_cooldown,
            chat_permission=permission,
        )

    def to_dict(self) -> dict[str, Any]:
        data = {
            "id": self.id,
            "name": self.name,
            "enabled": self.enabled,
            "platform": self.platform,
            "event_type": self.event_type,
            "filters": self.filters,
            "cooldown_s": self.cooldown_s,
            "action_id": self.action_id,
        }
        if self.user_cooldown_s:
            data["user_cooldown_s"] = self.user_cooldown_s
        if self.chat_permission != "everyone":
            data["chat_permission"] = self.chat_permission
        return data


@dataclass
class Action:
    """Lista ordenada de pasos (sub-acciones) que se ejecutan en secuencia."""

    id: str
    name: str = ""
    steps: list[dict[str, Any]] = field(default_factory=list)
    queue: str = ""  # vacío conserva el modo paralelo

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Action":
        if not isinstance(d, dict):
            raise ValueError("Una acción debe ser un objeto.")
        steps = d.get("steps", [])
        if not isinstance(steps, list) or any(not isinstance(step, dict) for step in steps):
            raise ValueError("Cada paso de una acción debe ser un objeto")
        queue = d.get("queue", "")
        if not isinstance(queue, str) or len(queue.strip()) > 40 or (
            queue.strip() and not queue.strip().isprintable()
        ):
            raise ValueError("La cola debe tener un nombre de hasta 40 caracteres en una sola línea.")
        return cls(id=str(d["id"]), name=str(d.get("name", d["id"])), steps=steps, queue=queue.strip())

    def to_dict(self) -> dict[str, Any]:
        data = {"id": self.id, "name": self.name, "steps": self.steps}
        if self.queue:
            data["queue"] = self.queue
        return data


DEFAULT_SETTINGS: dict[str, Any] = {
    "overlay_port": 8765,
    "obs": {"host": "127.0.0.1", "port": 4455, "autoconnect": False},
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
    def load(cls, path: Path | None = None, *, recover: bool = True) -> "Config":
        path = path or (config_dir() / "config.json")
        if not path.exists():
            if not recover:
                raise FileNotFoundError(path)
            cfg = cls.defaults()
            cfg.path = path
            cfg.save()
            return cfg
        try:
            raw = json.loads(path.read_text("utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            if not recover:
                raise
            backup = path.with_suffix(".json.bak")
            shutil.copy2(path, backup)
            log.error("Configuración ilegible (%s). Copia en %s; se usan valores por defecto.", exc, backup)
            cfg = cls.defaults()
            cfg.path = path
            return cfg

        if not isinstance(raw, dict):
            if not recover:
                raise ValueError("El perfil no es un objeto JSON.")
            log.error("La configuración no es un objeto JSON. Se usan los ajustes predeterminados.")
            cfg = cls.defaults()
            cfg.path = path
            return cfg
        if not recover and (not isinstance(raw.get("triggers"), list)
                            or not isinstance(raw.get("actions"), list)):
            raise ValueError("El perfil necesita sus listas de triggers y acciones.")
        settings = raw.get("settings")
        cfg = cls(settings=_merge(DEFAULT_SETTINGS, settings if isinstance(settings, dict) else {}), path=path)
        if not isinstance(cfg.settings["obs"], dict):
            cfg.settings["obs"] = copy.deepcopy(DEFAULT_SETTINGS["obs"])
        legacy_obs = cfg.settings["obs"]
        if "password" in legacy_obs:
            legacy_obs.pop("password")
            legacy_obs["autoconnect"] = False
            # Nunca persiste secretos de una configuración antigua.
            try:
                cfg._remove_legacy_obs_password(raw)
            except OSError as exc:
                log.warning("No se pudo retirar del archivo la contraseña antigua de OBS: %s", exc)
        for item in raw["triggers"] if isinstance(raw.get("triggers"), list) else []:
            try:
                cfg.triggers.append(Trigger.from_dict(item))
            except (KeyError, TypeError, ValueError) as exc:
                if not recover:
                    raise ValueError("El perfil contiene un trigger inválido.") from exc
                log.warning("Trigger inválido omitido: %r", item)
        for item in raw["actions"] if isinstance(raw.get("actions"), list) else []:
            try:
                cfg.actions.append(Action.from_dict(item))
            except (KeyError, TypeError, ValueError) as exc:
                if not recover:
                    raise ValueError("El perfil contiene una acción inválida.") from exc
                log.warning("Acción inválida omitida: %r", item)
        return cfg

    def _remove_legacy_obs_password(self, raw: dict[str, Any]) -> None:
        """Migra el secreto sin reinterpretar ni perder otros campos del archivo."""
        old = raw["settings"]["obs"]
        old.pop("password", None)
        old["autoconnect"] = False
        self._write(self.path, raw)

    @staticmethod
    def _write(path: Path, data: dict[str, Any]) -> None:
        import tempfile

        descriptor, name = tempfile.mkstemp(prefix=".config-", suffix=".tmp", dir=path.parent)
        temporary = Path(name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as file:
                json.dump(data, file, indent=2, ensure_ascii=False)
                file.write("\n")
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)

    def save(self, path: Path | None = None) -> None:
        path = path or self.path or (config_dir() / "config.json")
        settings = copy.deepcopy(self.settings)
        if isinstance(settings.get("obs"), dict) and "password" in settings["obs"]:
            settings["obs"].pop("password")
            settings["obs"]["autoconnect"] = False
        self._write(path, {
            "settings": settings,
            "triggers": [t.to_dict() for t in self.triggers],
            "actions": [a.to_dict() for a in self.actions],
        })
        self.path = path
