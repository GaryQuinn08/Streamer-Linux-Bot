import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from slbot.core.config import Action, Config
from slbot.core.timers import Timer, TimerService, read_timers
from slbot.runtime import Runtime


def timer_data(**changes):
    return {**{"id": "t1", "name": "Pausa", "action_id": "notice", "seconds": 4, "enabled": True}, **changes}


class TimerTests(unittest.IsolatedAsyncioTestCase):
    def test_validate_and_dedupe(self):
        for interval in (0, -1, True, "1", 86401):
            with self.assertRaises(ValueError):
                Timer.parse(timer_data(seconds=interval))
        self.assertEqual(read_timers({"timers": [None, timer_data(), timer_data(seconds=5)]}),
                         [Timer.parse(timer_data())])

    async def test_runs_after_interval_without_overlap_or_backlog(self):
        config = Config(actions=[Action("notice", "Aviso", [{"type": "log", "message": "hola"}])])
        config.settings["timers"] = [timer_data()]
        unblock = asyncio.Event()
        tasks = []

        async def execute(action, event, origin):
            self.assertEqual(action.id, "notice")
            self.assertEqual(event.data["timer"], "Pausa")
            self.assertEqual(origin, "Temporizador: Pausa")
            await unblock.wait()

        def spawn(coro):
            task = asyncio.create_task(coro)
            tasks.append(task)
            return task
        rt = SimpleNamespace(config=config, spawn=spawn, execute_action=AsyncMock(side_effect=execute))
        service = TimerService(rt)
        try:
            service.tick(10)
            service.tick(13.9)
            self.assertFalse(tasks)
            service.tick(14)
            service.tick(24)
            self.assertEqual(len(tasks), 1)
            unblock.set()
            await tasks[0]
            service.tick(27.9)
            self.assertEqual(len(tasks), 1)
            service.tick(28)
            self.assertEqual(len(tasks), 2)
            config.settings["timers"] = [timer_data(enabled=False)]
            service.tick(100)
            self.assertEqual(len(tasks), 2)
        finally:
            unblock.set()
            await asyncio.gather(*tasks)

    async def test_edit_persists_and_keeps_action_references(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            config = Config(actions=[Action("notice", "Aviso", [{"type": "log", "message": "hola"}])], path=path)
            runtime = Runtime(config=config)
            await runtime.edit_timer(timer_data())
            self.assertEqual(read_timers(Config.load(path).settings), [Timer.parse(timer_data())])
            with self.assertRaisesRegex(ValueError, "Pausa"):
                await runtime.edit_rule("action", {"id": "notice"}, delete=True)
            with self.assertRaisesRegex(ValueError, "existente"):
                await runtime.edit_timer(timer_data(action_id="desconocida"))
            await runtime.edit_timer({"id": "t1"}, delete=True)
            await runtime.edit_rule("action", {"id": "notice"}, delete=True)
            self.assertEqual(Config.load(path).actions, [])
            self.assertEqual(read_timers(Config.load(path).settings), [])
