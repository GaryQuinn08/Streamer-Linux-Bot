import asyncio
import tempfile
import unittest
from pathlib import Path

from slbot.core.actions import overlay_variables
from slbot.core.config import Action, Config
from slbot.core.editing import update_rules
from slbot.core.events import Event
from slbot.runtime import Runtime


def put(name, value):
    return {"type": "set_variable", "key": name, "value": value}


def call(ident):
    return {"type": "run_action", "action_id": ident}


def write(text):
    return {"type": "log", "message": text}


class FlowTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.rt = Runtime(config=Config.defaults())

    async def test_numeric_branch_shares_variables_and_never_requeues_child(self):
        child = Action("child", "Actualiza", [put("resultado", "{local_resultado}-{user}")], "Alertas")
        alternative = Action("else", "Alternativa", [put("resultado", "no")])
        parent = Action("parent", "Principal", [put("resultado", "sí"), {
            "type": "condition", "key": "count", "operator": "gte", "value": "9",
            "then_id": "child", "else_id": "else",
        }, write("Resultado: {local_resultado}")], "Alertas")
        self.rt.config.actions = [parent, child, alternative]
        for user, count in [("Luna", 10), ("Sol", 2), ("Otra", "NaN")]:
            ev = Event("tiktok", "gift", user, {"count": count, "local_resultado": "no filtrado"})
            run = await asyncio.wait_for(self.rt.execute_action(parent, ev, "Prueba"), 1)
            self.assertEqual(run.state, "Completada")
            self.assertNotIn("local_resultado", overlay_variables(ev))
        lines = "\n".join(self.rt.log_history)
        self.assertIn("Resultado: sí-Luna", lines)
        self.assertEqual(lines.count("Resultado: no"), 2)
        self.assertEqual([run.action for run in self.rt.action_snapshot()], ["Principal"] * 3)

    async def test_recursive_or_missing_link_fails_and_remaining_steps_continue(self):
        a = Action("a", "A", [call("b"), call("nada"), write("siguiente")])
        b = Action("b", "B", [call("a")])
        self.rt.config.actions = [a, b]
        run = await self.rt.execute_action(a, Event("system", "test"), "Prueba")
        self.assertEqual((run.state, run.failures), ("Con errores", 2))
        self.assertIn("circular", "\n".join(self.rt.log_history))
        self.assertIn("siguiente", self.rt.log_history[-1])

    async def test_parallel_runs_isolate_local_values_and_cancellation_releases_queue(self):
        child = Action("child", "Child", [put("actor", "{user}"), {"type": "wait", "seconds": .01}])
        parent = Action("parent", "Parent", [call("child"), write("guarda: {local_actor}")])
        self.rt.config.actions = [child, parent]
        await asyncio.gather(*(self.rt.execute_action(parent, Event("system", "test", user), "Prueba")
                               for user in ["Uno", "Dos"]))
        self.assertIn("guarda: Uno", "\n".join(self.rt.log_history))
        self.assertIn("guarda: Dos", "\n".join(self.rt.log_history))
        child.steps = [{"type": "wait", "seconds": 120}]
        parent.queue = "Serial"
        task = self.rt.spawn(self.rt.execute_action(parent, Event("system", "test"), "Prueba"))
        await asyncio.sleep(0)
        run = next(run for run in self.rt.action_snapshot() if run.state == "En curso")
        await self.rt.cancel_action(run.id)
        await asyncio.gather(task, return_exceptions=True)
        third = await asyncio.wait_for(self.rt.execute_action(
            Action("other", "Otro", [], "Serial"), Event("system", "test"), "Prueba"), 1)
        self.assertEqual(third.state, "Completada")

    async def test_missing_values_are_not_literal_matches(self):
        yes = Action("yes", "Sí", [write("rama sí")])
        no = Action("no", "No", [write("rama no")])
        self.rt.config.actions = [yes, no]
        for op, key, value, desired in (
            ("neq", "absent", "x", "no"), ("missing", "absent", "", "sí"),
            ("eq", "text", "{desconocida}", "no"), ("exists", "text", "", "sí"),
        ):
            parent = Action("a", "A", [{"type": "condition", "key": key, "operator": op, "value": value,
                                        "then_id": "yes", "else_id": "no"}])
            await self.rt.execute_action(parent, Event("system", "test", data={"text": "{desconocida}"}), "Prueba")
            self.assertIn(f"rama {desired}", self.rt.log_history[-1])


class FlowEditingTests(unittest.TestCase):
    def test_validation_and_delete_do_not_leave_dangling_actions(self):
        with tempfile.TemporaryDirectory() as d:
            config = Config(path=Path(d) / "config.json")
            update_rules(config, "action", Action("a", "A", [write("a")]).to_dict())
            update_rules(config, "action", Action("b", "B", [call("a")]).to_dict())
            with self.assertRaisesRegex(ValueError, "ciclo"):
                update_rules(config, "action", Action("a", "A", [call("b")]).to_dict())
            with self.assertRaisesRegex(ValueError, "referencias"):
                update_rules(config, "action", {"id": "a"}, delete=True)
            with self.assertRaisesRegex(ValueError, "no existe"):
                update_rules(config, "action", Action("c", "C", [call("ausente")]).to_dict())
            self.assertEqual(Config.load(config.path).action_by_id("b").steps, [call("a")])
