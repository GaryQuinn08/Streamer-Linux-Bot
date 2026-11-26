import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from slbot.connectors.platforms import chat_events
from slbot.core.config import Action, Config, Trigger
from slbot.core.events import Event
from slbot.runtime import Runtime


class QueueTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.rt = Runtime(config=Config.defaults(), port=0)

    def schedule(self, name, queue="", seconds=0):
        return self.rt.spawn(self.rt.execute_action(
            Action(name, name, [{"type": "wait", "seconds": seconds}], queue),
            Event("system", "test"), "Prueba"))

    def states(self):
        return {run.action: run.state for run in self.rt.action_snapshot()}

    async def test_fifo_is_case_insensitive_and_does_not_block_other_queues(self):
        first = self.schedule("Primera", "Alertas", 120)
        second = self.schedule("Segunda", "alertas", 120)
        third = self.schedule("Tercera", "ALERTAS", 120)
        other = self.schedule("Otra", "Escenas")
        parallel = self.schedule("Paralela")
        await asyncio.gather(other, parallel)
        self.assertEqual(self.states(), {"Primera": "En curso", "Segunda": "En espera",
                         "Tercera": "En espera", "Otra": "Completada", "Paralela": "Completada"})
        ids = {run.action: run.id for run in self.rt.action_snapshot()}
        await self.rt.cancel_action(ids["Primera"])
        await asyncio.gather(first, return_exceptions=True)
        self.assertEqual(self.states()["Segunda"], "En curso")
        self.assertEqual(self.states()["Tercera"], "En espera")
        await self.rt.cancel_action(ids["Tercera"])
        await self.rt.cancel_action(ids["Segunda"])
        await asyncio.gather(second, third, return_exceptions=True)
        self.assertEqual(self.states()["Tercera"], "Cancelada")
        self.assertEqual(self.states()["Segunda"], "Cancelada")

    async def test_pause_stops_new_work_but_does_not_interrupt_running_work(self):
        running = self.schedule("Ya empezó", "", 0)
        await asyncio.sleep(0)
        await self.rt.pause_actions(True)
        pending = self.schedule("Pendiente")
        await running
        self.assertEqual(self.states(), {"Ya empezó": "Completada", "Pendiente": "En espera"})
        await self.rt.pause_actions(False)
        await pending
        self.assertEqual(self.states()["Pendiente"], "Completada")

    async def test_paused_queue_bounded_and_shutdown_cancels_pending(self):
        await self.rt.pause_actions(True)
        tasks = [self.schedule(f"acción {i}") for i in range(129)]
        await asyncio.sleep(0)
        self.assertEqual(sum(state == "En espera" for state in self.states().values()), 128)
        self.assertEqual(self.states()["acción 128"], "Descartada: cola llena")
        await self.rt._shutdown()
        self.assertTrue(all(task.done() for task in tasks))
        self.assertEqual(sum(state == "Cancelada" for state in self.states().values()), 128)

    async def test_cancel_waits_for_inflight_obs_then_skips_next_step(self):
        entered, release = asyncio.Event(), asyncio.Event()

        async def obs(_scene):
            entered.set()
            await release.wait()

        action = Action("obs", "OBS", [{"type": "obs_scene", "scene": "A"},
                                       {"type": "log", "message": "Paso siguiente"}], "Escenas")
        with patch.object(self.rt.obs, "set_scene", side_effect=obs):
            task = self.rt.spawn(self.rt.execute_action(action, Event("system", "test"), "Prueba"))
            await asyncio.wait_for(entered.wait(), 1)
            later = self.schedule("Siguiente acción", "escenas")
            await asyncio.sleep(0)
            ident = next(run.id for run in self.rt.action_snapshot() if run.action == "OBS")
            await self.rt.cancel_action(ident)
            await asyncio.sleep(0)
            self.assertEqual(self.states(), {"OBS": "En curso", "Siguiente acción": "En espera"})
            release.set()
            await asyncio.gather(task, later, return_exceptions=True)
        self.assertEqual(self.states(), {"OBS": "Cancelada", "Siguiente acción": "Completada"})
        self.assertFalse(any("Paso siguiente" in line for line in self.rt.log_history))

    async def test_aliases_share_user_cooldown_but_not_users_or_platforms(self):
        self.rt.config.triggers = [Trigger.from_dict({
            "id": "hola", "name": "Hola", "event_type": "command", "action_id": "alert-gift",
            "user_cooldown_s": 60, "filters": {"command": "hi", "command_aliases": ["hola", "saludo"]},
        })]
        self.rt.bus.subscribe(self.rt.engine.on_event)
        for platform, user, text in (
            ("twitch", "Luna", "!HOLA mundo"),
            ("twitch", "luna", "!saludo"),
            ("twitch", "Luna", "!hi"),
            ("twitch", "Sol", "!saludo"),
            ("tiktok", "Luna", "!hi"),
            ("tiktok", "Sol", "!hola2"),
        ):
            for event in chat_events(platform, user, text):
                await self.rt.bus.publish(event)
        await asyncio.gather(*self.rt._background)
        self.assertCountEqual([run.platform for run in self.rt.action_snapshot()],
                              ["twitch", "twitch", "tiktok"])


class ConfigTests(unittest.TestCase):
    def test_old_profile_retains_parallel_default_and_new_fields_roundtrip(self):
        config = Config.defaults()
        self.assertTrue(all(not item.queue and "queue" not in item.to_dict() for item in config.actions))
        config.actions[0].queue = "Regalos"
        config.triggers[0].user_cooldown_s = 20
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "config.json"
            config.save(path)
            restored = Config.load(path)
        self.assertEqual(restored.actions[0].queue, "Regalos")
        self.assertEqual(restored.triggers[0].user_cooldown_s, 20)
