"""Port recovery and real overlay customization regressions."""
from __future__ import annotations

import asyncio
import os
import socket
import tempfile
import unittest
from pathlib import Path

import aiohttp

from slbot.core.config import Config
from slbot.overlay_manager import create_alert, import_overlay, list_overlays
from slbot.runtime import Runtime
from test_smoke import RuntimeCase


class PortTests(unittest.TestCase):
    def test_port_conflict_keeps_qt_usable_and_new_port_is_persisted(self):
        try:
            from PySide6.QtWidgets import QApplication
            from slbot.ui.main_window import LogBridge, MainWindow
        except ImportError as exc:
            self.skipTest(str(exc))
        with tempfile.TemporaryDirectory() as cfg_dir, socket.socket() as blocker:
            blocker.bind(("127.0.0.1", 0))
            blocker.listen()
            occupied = blocker.getsockname()[1]
            cfg = Config.defaults()
            cfg.settings["overlay_port"] = occupied
            path = Path(cfg_dir) / "config.json"
            cfg.save(path)
            old = os.environ.get("SLB_DATA_DIR")
            os.environ["SLB_DATA_DIR"] = cfg_dir
            app = QApplication.instance() or QApplication([])
            rt = Runtime(config=cfg)
            rt.start()
            window = None
            try:
                window = MainWindow(rt, LogBridge())
                home = window.connections_page
                overlays = window.overlays_page
                self.assertIsNone(rt.port)
                self.assertEqual(home.overlay_port.text(), "")
                self.assertIn(f"El puerto {occupied} está ocupado", home.server_label.text())
                self.assertFalse(overlays.copy_btn.isEnabled())
                with self.assertRaisesRegex(ValueError, "ocupado"):
                    rt.submit(rt.change_overlay_port(occupied)).result(5)
                with socket.socket() as probe:
                    probe.bind(("127.0.0.1", 0))
                    available = probe.getsockname()[1]
                home.overlay_port.setText(str(available))
                home.assign_port.click()
                from PySide6.QtTest import QTest

                for _ in range(200):
                    QTest.qWait(10)
                    if home.assign_port.isEnabled():
                        break
                self.assertEqual(rt.port, available, home.port_result.text())
                self.assertEqual(Config.load(path).settings["overlay_port"], available)
                self.assertTrue(overlays.copy_btn.isEnabled())
                self.assertIn(f":{available}/overlay/", overlays.url.text())
                with self.assertRaisesRegex(ValueError, "ocupado"):
                    rt.submit(rt.change_overlay_port(occupied)).result(5)
                self.assertEqual(rt.port, available)
            finally:
                if window is not None:
                    window.close()
                rt.stop()
                if old is None:
                    os.environ.pop("SLB_DATA_DIR", None)
                else:
                    os.environ["SLB_DATA_DIR"] = old


class OverlayBeta2Tests(RuntimeCase):
    def test_new_alert_can_be_targeted_and_appearance_is_persistent(self):
        alert = create_alert("Mi alerta de prueba")
        self.assertEqual(alert.id, "mi-alerta-de-prueba")
        self.assertNotEqual(create_alert("Mi alerta de prueba").id, alert.id)
        self.rt.submit(self.rt.save_overlay_preset(alert.id, {"color": "#32aa45", "duration": "8"})).result(5)
        self.rt.submit(self.rt.save_gift_rule(True, "", 0, "Gracias {user}", overlay_id=alert.id)).result(5)
        saved = Config.load(self.rt.config.path)
        self.assertEqual(saved.settings["overlay_presets"][alert.id]["color"], "#32aa45")

        async def flow():
            async with aiohttp.ClientSession() as session:
                async with session.get(self.base_url + "/") as response:
                    page = await response.text()
                    self.assertIn(f'/overlay/{alert.id}/', page)
                    self.assertIn("Mi alerta de prueba", page)
                async with session.get(self.base_url + "/sdk/overlay-sdk.js") as response:
                    self.assertIn(f'"{alert.id}": {{"color": "#32aa45", "duration": "8"}}', await response.text())
                async with session.ws_connect(f"{self.base_url}/ws/{alert.id}") as ws:
                    await ws.receive_json(timeout=5)
                    from slbot.connectors.simulator import sample_event

                    self.rt.emit(sample_event("gift"))
                    self.assertEqual((await ws.receive_json(timeout=5))["title"], "Gracias viewer_demo")
        asyncio.run(flow())
        self.rt.submit(self.rt.save_overlay_preset(alert.id, {})).result(5)
        self.assertNotIn(alert.id, Config.load(self.rt.config.path).settings["overlay_presets"])

    def test_import_independent_html_keeps_content(self):
        with tempfile.TemporaryDirectory() as folder:
            original = Path(folder) / "Mis alertas.html"
            original.write_text("<p>Una alerta anterior</p>", encoding="utf-8")
            info = import_overlay(original)
            self.assertEqual(info.id, "mis-alertas")
            self.assertIn(info.id, list_overlays())
            self.assertEqual((info.path / "index.html").read_text(encoding="utf-8"),
                             original.read_text(encoding="utf-8"))
