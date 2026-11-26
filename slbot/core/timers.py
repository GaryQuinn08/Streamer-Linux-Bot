"""Temporizadores repetibles que solo corren mientras el bot está abierto."""
from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING

from .events import Event

if TYPE_CHECKING:
    from ..runtime import Runtime


@dataclass(frozen=True)
class Timer:
    id: str
    name: str
    action_id: str
    seconds: int
    enabled: bool = False

    @classmethod
    def parse(cls, raw):
        if not isinstance(raw, dict):
            raise ValueError("Temporizador inválido.")
        ident, name, action = (raw.get(key) for key in ("id", "name", "action_id"))
        if not all(isinstance(value, str) and 0 < len(value.strip()) <= 100
                   for value in (ident, name, action)):
            raise ValueError("Escribe un nombre y elige una acción.")
        seconds = raw.get("seconds")
        if type(seconds) is not int or not 1 <= seconds <= 86400:
            raise ValueError("El intervalo debe ser de 1 a 86 400 segundos.")
        enabled = raw.get("enabled", False)
        if type(enabled) is not bool:
            raise ValueError("Estado del temporizador inválido.")
        return cls(ident.strip(), name.strip(), action.strip(), seconds, enabled)

    def to_dict(self):
        return asdict(self)


def read_timers(settings: dict) -> list[Timer]:
    raw = settings.get("timers")
    result = {}
    for entry in raw[:100] if isinstance(raw, list) else []:
        try:
            timer = Timer.parse(entry)
        except ValueError:
            continue
        result.setdefault(timer.id, timer)
    return list(result.values())


def without_timers(settings: dict, ids: set[str]) -> dict:
    """Remove only confirmed timer IDs, retaining other configuration entries."""
    source = settings.get("timers")
    if not ids or not isinstance(source, list):
        return settings
    return {**settings, "timers": [
        item for item in source
        if not (isinstance(item, dict) and isinstance(item.get("id"), str) and item["id"].strip() in ids)
    ]}


class TimerService:
    def __init__(self, rt: Runtime):
        self.rt = rt
        self._selected: dict[str, tuple[Timer, float]] = {}
        self._running: dict[str, asyncio.Task] = {}

    async def run(self):
        loop = asyncio.get_running_loop()
        while True:
            self.tick(loop.time())
            await asyncio.sleep(.25)

    def tick(self, now: float) -> None:
        self._running = {key: task for key, task in self._running.items() if not task.done()}
        selected = {}
        for timer in read_timers(self.rt.config.settings):
            if not timer.enabled:
                continue
            action = self.rt.config.action_by_id(timer.action_id)
            if action is None:
                continue
            previous = self._selected.get(timer.id)
            deadline = previous[1] if previous and previous[0] == timer else now + timer.seconds
            if deadline <= now:
                # No acumular ejecuciones tras suspensión o una acción larga.
                deadline = now + timer.seconds
                if timer.id not in self._running:
                    event = Event("system", "timer", data={
                        "timer": timer.name, "timer_id": timer.id, "interval": timer.seconds,
                    })
                    self._running[timer.id] = self.rt.spawn(self.rt.execute_action(
                        action, event, f"Temporizador: {timer.name}",
                    ))
            selected[timer.id] = timer, deadline
        self._selected = selected
