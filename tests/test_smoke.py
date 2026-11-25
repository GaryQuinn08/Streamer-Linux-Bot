"""Pruebas de humo: evento -> trigger -> acción -> overlay (por WebSocket).

Ejecutar:  python -m unittest discover -s tests -v
"""
from __future__ import annotations

import asyncio
import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path

import aiohttp
from yarl import URL

from slbot.core.config import Trigger
from slbot.core.events import Event


class RuntimeCase(unittest.TestCase):
    """Arranca un Runtime real con configuración y datos temporales."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        base = Path(self._tmp.name)
        self._old_env = {k: os.environ.get(k) for k in ("SLB_CONFIG_DIR", "SLB_DATA_DIR")}
        os.environ["SLB_CONFIG_DIR"] = str(base / "config")
        os.environ["SLB_DATA_DIR"] = str(base / "data")

        from slbot.runtime import Runtime

        self.logs: list[str] = []
        self.rt = Runtime(on_log=self.logs.append, port=0)
        self.rt.start()
        self.base_url = f"http://127.0.0.1:{self.rt.port}"

    def tearDown(self) -> None:
        self.rt.stop()
        for key, value in self._old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self._tmp.cleanup()


class ServerTests(RuntimeCase):
    def test_gift_event_triggers_alert_over_websocket(self) -> None:
        async def flow() -> list[dict]:
            received: list[dict] = []
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(f"{self.base_url}/ws") as ws:
                    hello = await ws.receive_json(timeout=5)
                    self.assertEqual(hello["type"], "hello")
                    async with session.post(f"{self.base_url}/api/test", json={"sample": "gift"}) as resp:
                        self.assertEqual(resp.status, 200)
                    for _ in range(2):  # el evento y la alerta de la acción
                        received.append(await ws.receive_json(timeout=5))
            return received

        messages = asyncio.run(flow())
        channels = {m["channel"] for m in messages}
        self.assertEqual(channels, {"event", "alert"})
        alert = next(m for m in messages if m["channel"] == "alert")
        self.assertEqual(alert["overlay"], "gift-alert")
        self.assertIn("viewer_demo", alert["title"])
        self.assertIn("Rose", alert["title"])

    def test_foreign_origin_is_rejected(self) -> None:
        async def flow() -> int:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/api/test",
                    json={"sample": "gift"},
                    headers={"Origin": "https://evil.example"},
                ) as resp:
                    return resp.status

        self.assertEqual(asyncio.run(flow()), 403)

    def test_test_endpoint_requires_json_content_type(self) -> None:
        async def flow() -> int:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/api/test", data='{"sample":"gift"}', headers={"Content-Type": "text/plain"}
                ) as resp:
                    return resp.status

        self.assertEqual(asyncio.run(flow()), 415)

    def test_overlay_files_served_and_traversal_blocked(self) -> None:
        async def flow() -> tuple[int, int, int]:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.base_url}/overlay/gift-alert/") as r1:
                    ok = r1.status
                async with session.get(f"{self.base_url}/sdk/overlay-sdk.js") as r2:
                    sdk = r2.status
                evil = URL(f"{self.base_url}/overlay/gift-alert/..%2f..%2f..%2fconfig.py", encoded=True)
                async with session.get(evil) as r3:
                    traversal = r3.status
                return ok, sdk, traversal

        ok, sdk, traversal = asyncio.run(flow())
        self.assertEqual(ok, 200)
        self.assertEqual(sdk, 200)
        self.assertEqual(traversal, 404)

    def test_obs_action_without_connection_logs_error_and_continues(self) -> None:
        from slbot.core.config import Action
        from slbot.core.actions import run_action

        action = Action("t", "Prueba", [
            {"type": "obs_scene", "scene": "Juego"},
            {"type": "log", "message": "sigue"},
        ])
        asyncio.run_coroutine_threadsafe(
            run_action(self.rt, action, Event("system", "test", "x")), self.rt.loop
        ).result(5)
        joined = "\n".join(self.logs)
        self.assertIn("falló", joined)
        self.assertIn("sigue", joined)


class TriggerTests(unittest.TestCase):
    def test_matching_filters(self) -> None:
        trig = Trigger("t", "gift", "a", platform="tiktok", filters={"min_value": 5, "gift_name": "rose"})
        ok = Event("tiktok", "gift", "u", {"gift_name": "Rose", "value": 5})
        self.assertTrue(trig.matches(ok))
        self.assertFalse(trig.matches(Event("tiktok", "gift", "u", {"gift_name": "Rose", "value": 4})))
        self.assertFalse(trig.matches(Event("twitch", "gift", "u", {"gift_name": "Rose", "value": 9})))
        self.assertFalse(trig.matches(Event("tiktok", "follow", "u", {})))

    def test_cooldown_blocks_second_fire(self) -> None:
        from slbot.core.config import Action, Config
        from slbot.core.engine import Engine

        fired: list[str] = []

        class FakeRuntime:
            config = Config(
                triggers=[Trigger("t", "follow", "a", cooldown_s=60)],
                actions=[Action("a", "A", [])],
            )

            def log(self, msg: str) -> None:
                fired.append(msg)

            def spawn(self, coro) -> None:
                coro.close()

        engine = Engine(FakeRuntime())  # type: ignore[arg-type]

        async def run() -> None:
            await engine.on_event(Event("twitch", "follow", "u"))
            await engine.on_event(Event("twitch", "follow", "u"))

        asyncio.run(run())
        self.assertEqual(len([m for m in fired if "->" in m]), 1)


class OverlayImportTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self._old = os.environ.get("SLB_DATA_DIR")
        os.environ["SLB_DATA_DIR"] = str(self.base / "data")

    def tearDown(self) -> None:
        if self._old is None:
            os.environ.pop("SLB_DATA_DIR", None)
        else:
            os.environ["SLB_DATA_DIR"] = self._old
        self._tmp.cleanup()

    def _make_zip(self, name: str, files: dict[str, str]) -> Path:
        path = self.base / name
        with zipfile.ZipFile(path, "w") as zf:
            for filename, content in files.items():
                zf.writestr(filename, content)
        return path

    def test_import_valid_zip(self) -> None:
        from slbot.overlay_manager import import_overlay, list_overlays

        manifest = json.dumps({"id": "mi-overlay", "name": "Mi overlay", "params": []})
        z = self._make_zip("ok.zip", {"mi-overlay/manifest.json": manifest, "mi-overlay/index.html": "<p>hola</p>"})
        info = import_overlay(z)
        self.assertEqual(info.id, "mi-overlay")
        self.assertIn("mi-overlay", list_overlays())

    def test_zip_slip_is_rejected(self) -> None:
        from slbot.overlay_manager import import_overlay

        z = self._make_zip("evil.zip", {"../evil.txt": "x", "manifest.json": "{}", "index.html": ""})
        with self.assertRaises(ValueError):
            import_overlay(z)
        self.assertFalse((self.base / "evil.txt").exists())

    def test_invalid_manifest_is_rejected(self) -> None:
        from slbot.overlay_manager import import_overlay

        bad = json.dumps({"id": "Mal Id!", "name": "x"})
        z = self._make_zip("bad.zip", {"manifest.json": bad, "index.html": ""})
        with self.assertRaises(ValueError):
            import_overlay(z)


class UiTests(RuntimeCase):
    def test_main_window_builds_offscreen(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        try:
            from PySide6.QtWidgets import QApplication

            from slbot.ui.main_window import LogBridge, MainWindow
        except ImportError as exc:  # PySide6 no instalado
            self.skipTest(str(exc))

        app = QApplication.instance() or QApplication([])
        window = MainWindow(self.rt, LogBridge())
        self.assertEqual(window.centralWidget().count(), 5)
        window.close()
        del app


if __name__ == "__main__":
    unittest.main()
