import asyncio
import os
import tempfile
import unittest
from unittest.mock import patch

import aiohttp

from slbot.connectors.simulator import sample_event
from slbot.core.config import Action, Config
from slbot.core.events import Event
from slbot.runtime import Runtime


class SessionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        data = tempfile.TemporaryDirectory()
        self.addCleanup(data.cleanup)
        env = patch.dict(os.environ, {"SLB_DATA_DIR": data.name})
        env.start()
        self.addCleanup(env.stop)
        self.rt = Runtime(config=Config.defaults(), port=0)
        await self.rt._startup()
        self.addAsyncCleanup(self.rt._shutdown)

    async def test_chat_and_command_not_duplicated(self):
        await self.rt.bus.publish(Event("youtube", "chat", "u", {"text": "<test>"}))
        await self.rt.bus.publish(Event("youtube", "command", "u", {"text": "!test"}))
        await self.rt.bus.publish(sample_event("chat"))
        real, sample = self.rt.chat_snapshot()
        self.assertEqual((real.platform, real.text, real.simulated), ("youtube", "<test>", False))
        self.assertTrue(sample.simulated)

    async def test_history_reports_failure_and_runs_remaining_steps(self):
        action = Action("test", "Mi acción", [{"type": "chat_message"}, {"type": "log", "message": "siguiente"}])
        await self.rt.execute_action(action, sample_event("gift"), "Prueba manual")
        run, = self.rt.action_snapshot()
        self.assertEqual((run.state, run.failures, run.origin), ("Con errores", 1, "Prueba manual"))
        self.assertGreaterEqual(run.duration_ms, 0)
        self.assertIn("siguiente", self.rt.log_history[-1])

    async def test_history_tracks_automatic_runs_and_cancellation(self):
        await self.rt.bus.publish(sample_event("gift"))
        await asyncio.gather(*self.rt._background)
        run, = self.rt.action_snapshot()
        self.assertEqual((run.state, run.platform, run.event), ("Completada", "tiktok", "gift"))
        task = asyncio.create_task(self.rt.execute_action(
            Action("wait", "Espera", [{"type": "wait", "seconds": 30}]), sample_event("gift"), "manual"))
        await asyncio.sleep(0)
        self.assertEqual(self.rt.action_snapshot()[0].state, "En curso")
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(self.rt.action_snapshot()[-1].state, "Cancelada")

    async def test_goal_updates_and_retains_counts_on_reconnect(self):
        base = f"http://127.0.0.1:{self.rt.port}"
        async with aiohttp.ClientSession() as session:
            async with session.get(base + "/overlay/live-goal/") as page:
                self.assertEqual(page.status, 200)
                self.assertIn("Meta del LIVE", await page.text())
            async with session.ws_connect(base + "/ws/live-goal") as goal:
                await goal.receive_json(timeout=2)
                self.assertEqual((await goal.receive_json(timeout=2))["counts"], {"gift": 0, "follow": 0})
                await self.rt.bus.publish(sample_event("gift"))
                await self.rt.bus.publish(Event("twitch", "follow", "no aplica"))
                await self.rt.preview_overlay("live-goal")
                self.assertEqual((await goal.receive_json(timeout=2))["channel"], "goal-preview")
                await self.rt.bus.publish(Event("tiktok", "gift", "viewer", {"count": 4}))
                self.assertEqual((await goal.receive_json(timeout=2))["counts"], {"gift": 4, "follow": 0})
                await self.rt.bus.publish(Event("tiktok", "follow", "viewer"))
                self.assertEqual((await goal.receive_json(timeout=2))["counts"], {"gift": 4, "follow": 1})
            async with session.ws_connect(base + "/ws/live-goal") as goal:
                await goal.receive_json(timeout=2)
                self.assertEqual((await goal.receive_json(timeout=2))["counts"], {"gift": 4, "follow": 1})
