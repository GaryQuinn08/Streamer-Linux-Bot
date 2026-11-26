"""Motor de triggers: evento -> trigger -> acción."""
from __future__ import annotations

import time
from typing import TYPE_CHECKING

from .events import Event

if TYPE_CHECKING:
    from ..runtime import Runtime


class Engine:
    def __init__(self, rt: "Runtime") -> None:
        self.rt = rt
        self._last_fired: dict[str, float] = {}

    async def on_event(self, ev: Event) -> None:
        for trigger in self.rt.config.triggers:
            if not trigger.enabled or not trigger.matches(ev):
                continue

            now = time.monotonic()
            last = self._last_fired.get(trigger.id)
            if trigger.cooldown_s and last is not None and now - last < trigger.cooldown_s:
                continue
            self._last_fired[trigger.id] = now

            action = self.rt.config.action_by_id(trigger.action_id)
            if action is None:
                self.rt.log(f"Trigger '{trigger.name}': no existe la acción '{trigger.action_id}'")
                continue

            self.rt.log(f"Trigger '{trigger.name}' -> acción '{action.name}'")
            self.rt.spawn(self.rt.execute_action(action, ev, trigger.name))
