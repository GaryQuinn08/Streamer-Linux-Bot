"""Now-playing browser protocol and native rehearsal (no live music provider)."""
import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aiohttp import ClientSession

from slbot.core.config import Config
from slbot.now_playing import Track
from slbot.overlay_manager import find_overlay
from slbot.overlay_server import NOW_PLAYING_IDS
from slbot.runtime import Runtime


class NowPlayingProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def test_sanitized_track_only_goes_to_both_music_sources(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {
            "SLB_DATA_DIR": folder, "SLB_CONFIG_DIR": folder,
        }):
            rt = Runtime(config=Config.load())
            await rt.overlays.start(0)
            try:
                base = f"http://127.0.0.1:{rt.port}"
                async with ClientSession() as session:
                    for endpoint in ["/overlay/" + ident + "/" for ident in NOW_PLAYING_IDS] + [
                            "/sdk/now-playing.css", "/sdk/now-playing.js"]:
                        async with session.get(base + endpoint) as response:
                            self.assertEqual(response.status, 200)
                    await rt.now_playing._publish(Track("playing", "Una canción", "Artista", "PrivateProvider"))
                    async with session.ws_connect(base + "/ws/now-playing") as vinyl, \
                            session.ws_connect(base + "/ws/now-playing-spectrum") as neon, \
                            session.ws_connect(base + "/ws/multi-chat") as chat:
                        for ws in (vinyl, neon):
                            await ws.receive_json(timeout=1)  # hello
                            self.assertEqual((await ws.receive_json(timeout=1))["channel"], "now-playing-settings")
                            self.assertEqual(await ws.receive_json(timeout=1), {
                                "channel": "now-playing", "state": "playing", "title": "Una canción",
                                "artist": "Artista",
                            })
                        await chat.receive_json(timeout=1)
                        await chat.receive_json(timeout=1)
                        await rt.overlays.preview_now_playing("now-playing-spectrum")
                        self.assertEqual((await neon.receive_json(timeout=1))["channel"], "now-playing-preview")
                        with self.assertRaises(TimeoutError):
                            await vinyl.receive_json(timeout=.06)
                        await rt.now_playing._publish(Track("paused", "Otra", "https://private.invalid/token", "A"))
                        for ws in (vinyl, neon):
                            data = await ws.receive_json(timeout=1)
                            self.assertEqual(data, {"channel": "now-playing", "state": "paused",
                                                    "title": "Otra", "artist": ""})
                        with self.assertRaises(TimeoutError):
                            await chat.receive_json(timeout=.06)
                        await rt.now_playing._publish(Track("playing", "/home/private/song.ogg", "A", "A"))
                        self.assertEqual((await vinyl.receive_json(timeout=1))["state"], "idle")
                        self.assertEqual(rt.chat_snapshot(), ())
                        self.assertFalse(rt.action_snapshot())
            finally:
                await rt.overlays.stop()


class NowPlayingQtTests(unittest.TestCase):
    def test_preview_both_styles_is_offline_and_editable(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QApplication
        from slbot.ui.main_window import LogBridge, OverlaysTab

        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {
            "SLB_DATA_DIR": folder, "SLB_CONFIG_DIR": folder,
        }):
            rt = Runtime(config=Config(path=Path(folder) / "config.json"))
            tab = OverlaysTab(rt, LogBridge())
            self.addCleanup(tab.close)
            tab.resize(1050, 820)
            tab.show()
            captures = []
            for ident in NOW_PLAYING_IDS:
                tab.refresh(select_id=ident)
                app.processEvents()
                view = tab.preview
                self.assertIsNotNone(view.model)
                self.assertTrue(view.can_play)
                self.assertFalse(tab.preview_btn.isEnabled())
                captures.append(view.grab().toImage())
                tab._set_value("position", "Arriba a la derecha")
                tab._set_value("accent", "#ff4000")
                tab._set_value("showArtist", False)
                self.assertEqual(view.model.settings["position"], "Arriba a la derecha")
                self.assertNotEqual(view.grab().toImage(), captures[-1])
                with patch.object(rt, "submit") as outbound:
                    tab.play_preview.click()
                    self.assertEqual(view.phase, "enter")
                    QTest.qWait(120)
                    outbound.assert_not_called()
                tab._set_value("motion", False)
                self.assertFalse(view.can_exit)
                self.assertEqual(find_overlay(ident).source, "builtin")
            self.assertNotEqual(*captures)
