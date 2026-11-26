"""Motor de triggers: evento -> trigger -> acción."""
from __future__ import annotations

import time
from collections import OrderedDict
from typing import TYPE_CHECKING

from .events import Event

if TYPE_CHECKING:
    from ..runtime import Runtime


class Engine:
    def __init__(self, rt: "Runtime") -> None:
        self.rt = rt
        self._last_fired: dict[str, float] = {}
        self._last_user_fired: OrderedDict[tuple[str, str, str], float] = OrderedDict()

    async def on_event(self, ev: Event) -> None:
        for trigger in self.rt.config.triggers:
            if not trigger.enabled or not trigger.matches(ev):
                continue

            now = time.monotonic()
            last = self._last_fired.get(trigger.id)
            if trigger.cooldown_s and last is not None and now - last < trigger.cooldown_s:
                continue
            author = ev.user.strip().casefold()[:100] if isinstance(ev.user, str) else ""
            key = (trigger.id, ev.platform, author)
            last_user = self._last_user_fired.get(key) if trigger.user_cooldown_s else None
            if last_user is not None and now - last_user < trigger.user_cooldown_s:
                continue

            action = self.rt.config.action_by_id(trigger.action_id)
            if action is None:
                self.rt.log(f"Trigger '{trigger.name}': no existe la acción '{trigger.action_id}'")
                continue

            self._last_fired[trigger.id] = now
            if trigger.user_cooldown_s:
                self._last_user_fired[key] = now
                self._last_user_fired.move_to_end(key)
                if len(self._last_user_fired) > 4096:
                    self._last_user_fired.popitem(last=False)
            self.rt.log(f"Trigger '{trigger.name}' -> acción '{action.name}'")
            self.rt.spawn(self.rt.execute_action(action, ev, trigger.name))
