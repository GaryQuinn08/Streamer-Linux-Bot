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
        async def flow() -> None:
            async with aiohttp.ClientSession() as session:
                async with (
                    session.ws_connect(f"{self.base_url}/ws/gift-alert") as gift,
                    session.ws_connect(f"{self.base_url}/ws/event-feed") as feed,
                ):
                    for ws in (gift, feed):
                        self.assertEqual((await ws.receive_json(timeout=5))["type"], "hello")
                    # Es la misma entrada que usa el botón de Inicio en Qt.
                    from slbot.connectors.simulator import sample_event

                    ev = sample_event("gift")
                    ev.data["connector_metadata"] = {"private": "not for overlays"}
                    self.rt.emit(ev)
                    alert = await gift.receive_json(timeout=5)
                    event = await feed.receive_json(timeout=5)
                    self.assertEqual(alert["channel"], "alert")
                    self.assertEqual(alert["overlay"], "gift-alert")
                    self.assertEqual(alert["title"], "viewer_demo envió Rose")
                    self.assertEqual(alert["text"], "x3")
                    self.assertEqual(event["channel"], "event")
                    self.assertEqual(event["data"], {"gift_name": "Rose", "count": 3})
                    for ws in (gift, feed):
                        with self.assertRaises(asyncio.TimeoutError):
                            await ws.receive_json(timeout=0.1)

        asyncio.run(flow())

    def test_foreign_origin_is_rejected(self) -> None:
        async def flow() -> None:
            async with aiohttp.ClientSession() as session:
                with self.assertRaises(aiohttp.WSServerHandshakeError) as error:
                    await session.ws_connect(
                        f"{self.base_url}/ws/gift-alert", origin="https://foreign.example",
                    )
                self.assertEqual(error.exception.status, 403)

        asyncio.run(flow())

    def test_simulation_is_not_exposed_over_http(self) -> None:
        async def flow() -> None:
            async with aiohttp.ClientSession() as session:
                async with session.post(f"{self.base_url}/api/test") as response:
                    self.assertEqual(response.status, 404)

        asyncio.run(flow())

    def test_legacy_global_socket_and_unknown_overlay_are_unavailable(self) -> None:
        async def flow() -> None:
            async with aiohttp.ClientSession() as session:
                for route in ("/ws", "/ws/not-an-overlay"):
                    with self.assertRaises(aiohttp.WSServerHandshakeError) as error:
                        await session.ws_connect(self.base_url + route)
                    self.assertEqual(error.exception.status, 404)

        asyncio.run(flow())

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

    def test_import_cannot_replace_builtin_overlay(self) -> None:
        from slbot.overlay_manager import import_overlay, list_overlays

        manifest = json.dumps({"id": "event-feed", "name": "Otro feed"})
        z = self._make_zip("reserved.zip", {"manifest.json": manifest, "index.html": "<p>otro</p>"})
        with self.assertRaises(ValueError):
            import_overlay(z, overwrite=True)
        self.assertEqual(list_overlays()["event-feed"].source, "builtin")

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
        self.assertEqual(window.centralWidget().count(), 7)
        window.close()
        del app


if __name__ == "__main__":
    unittest.main()
