from __future__ import annotations

import asyncio
import tempfile
import os
import unittest
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from slbot.connectors.platforms import TwitchConnector, YoutubeConnector
from slbot.connectors.simulator import sample_event
from slbot.connectors.tiktok import TiktokConnector, _WAITING
from slbot.core.config import Config
from slbot.core.events import Event
from slbot.dashboard import LiveDashboard
from slbot.runtime import Runtime


class DashboardCounts(unittest.TestCase):
    def test_observed_units_and_currencies_never_mix_with_sandbox_events(self):
        panel = LiveDashboard()
        samples = [
            sample_event("gift"), sample_event("follow"), sample_event("chat"),
            Event("twitch", "chat", data={"text": "!hello"}),
            Event("twitch", "command", data={"command": "hello"}),
            Event("twitch", "bits", data={"value": 100}),
            Event("tiktok", "gift", data={"count": 7, "value": 7}),  # Default overlay value isn't diamonds.
            Event("tiktok", "gift", data={"count": 5, "diamonds": 30}),
            Event("tiktok", "like", data={"count": 10}),
            Event("youtube", "donation", data={"amount": "1.23", "currency": "USD"}),
            Event("youtube", "donation", data={"amount": "100", "currency": "MXN"}),
            Event("youtube", "donation", data={"amount": "NaN", "currency": "GBP"}),
        ]
        for sample in samples:
            panel.event(sample)
        rows = panel.snapshot()
        self.assertEqual(dict(rows["twitch"].totals), {"chat": 1, "bits": 1, "bits_value": 100})
        self.assertEqual(dict(rows["tiktok"].totals), {"gift": 2, "gift_units": 12, "gift_value": 30,
                                                      "like": 1, "like_units": 10})
        self.assertEqual(dict(rows["youtube"].currencies), {"MXN": Decimal("100"), "USD": Decimal("1.23")})
        self.assertIsNotNone(rows["twitch"].last_event)
        self.assertIsNone(rows["twitch"].live)  # An ordinary chat can arrive while offline.

    def test_zero_differs_from_unavailable_and_old_status_cannot_reappear(self):
        panel = LiveDashboard()
        with patch("slbot.dashboard.time.time", return_value=1000):
            panel.signal("twitch", True, viewers=0, session_id="one")
            self.assertEqual(panel.snapshot()["twitch"].viewers, 0)
            panel.signal("twitch", True, viewers=25, session_id="one")
            panel.signal("twitch", True, viewers=10, session_id="one")
            panel.signal("kick", False, order=20)
            panel.signal("kick", True, order=10)
            self.assertIs(panel.snapshot()["kick"].live, False)
        with patch("slbot.dashboard.time.time", return_value=1190):
            old = panel.snapshot()["twitch"]
            self.assertEqual((old.live, old.viewers, old.peak), (None, None, 25))
            panel.signal("twitch", True, session_id="two")
            fresh = panel.snapshot()["twitch"]
            self.assertEqual((fresh.live, fresh.viewers, fresh.peak), (True, None, None))
            panel.invalidate("twitch")
            self.assertIsNone(panel.snapshot()["twitch"].live)


class Reply:
    def __init__(self, data, status=200):
        self.data, self.status = data, status

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    async def json(self):
        return self.data

    def raise_for_status(self):
        if self.status >= 400:
            raise ValueError(self.status)


class Session:
    def __init__(self, *replies):
        self.replies = iter(replies)
        self.requests = []

    def get(self, url, **args):
        self.requests.append((url, args))
        return next(self.replies)


class PlatformMetrics(unittest.IsolatedAsyncioTestCase):
    async def test_twitch_helix_checks_only_selected_broadcaster_and_expires_failures(self):
        board = LiveDashboard()
        connection = TwitchConnector(SimpleNamespace(dashboard=board))
        sessions = Session(Reply({"data": [{"id": "stream-A", "title": "Título", "viewer_count": 32}]}),
                           Reply({}, status=503), Reply({"data": []}))
        observations = []

        async def next_sample(_):
            observations.append(board.snapshot()["twitch"])
            if len(observations) == 3:
                raise asyncio.CancelledError

        with patch("slbot.connectors.platforms.asyncio.sleep", side_effect=next_sample):
            with self.assertRaises(asyncio.CancelledError):
                await connection._poll_dashboard(sessions, {"Authorization": "fixture"}, "123")
        self.assertEqual([(x.live, x.viewers) for x in observations], [(True, 32), (True, 32), (False, None)])
        self.assertIn("no respondió", observations[1].note)
        self.assertEqual(sessions.requests[0][1]["params"], {"user_id": "123"})

    async def test_direct_tiktok_waits_after_confirmed_offline_and_flags_next_live(self):
        board = LiveDashboard()
        connection = TiktokConnector(SimpleNamespace(dashboard=board))
        samples = iter((False, True))

        async def connect(channel):
            live = next(samples)
            board.signal("tiktok", live, identity="@" + channel)
            connection.status = "conectado (experimental)" if live else _WAITING

        with patch.object(connection, "_direct", side_effect=connect), patch(
            "slbot.connectors.tiktok.asyncio.sleep", new_callable=AsyncMock,
        ) as pause:
            await connection._watch_direct("canal")
        pause.assert_awaited_once_with(90)
        self.assertIs(board.snapshot()["tiktok"].live, True)

    async def test_youtube_honors_hidden_viewers_and_end_without_fabricating_counts(self):
        board = LiveDashboard()
        connection = YoutubeConnector(SimpleNamespace(dashboard=board, log=lambda _: None))
        sessions = Session(Reply({"items": [{"liveStreamingDetails": {"actualStartTime": "2026-11-26T14:00:00Z",
                                                                     "concurrentViewers": "0"}}]}),
                           Reply({"items": [{"liveStreamingDetails": {}}]}),
                           Reply({"items": [], "offlineAt": "2026-11-26T15:55:00Z"}))
        await connection._video_metrics(sessions, {}, "video", "", "Título")
        self.assertEqual(board.snapshot()["youtube"].viewers, 0)
        await connection._video_metrics(sessions, {}, "video", "", "Título")
        current = board.snapshot()["youtube"]
        self.assertEqual((current.live, current.viewers, current.peak), (True, None, 0))
        await connection._read_chat(sessions, {}, "chat", video="video")
        self.assertIs(board.snapshot()["youtube"].live, False)
        self.assertIn("esperando directo", connection.status)


class DesktopDashboard(unittest.TestCase):
    def test_home_updates_cards_and_shortcuts_from_runtime(self):
        try:
            from PySide6.QtWidgets import QApplication, QPushButton
            from slbot.ui.main_window import MainWindow, LogBridge
        except ImportError:
            self.skipTest("Qt not installed")
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ):
            os.environ["SLB_DATA_DIR"] = folder
            runtime = Runtime(config=Config.load(Path(folder) / "config.json"), port=0)
            runtime.start()
            try:
                win = MainWindow(runtime, LogBridge())
                win.show()
                app.processEvents()
                view = win.dashboard_page
                self.assertIs(win.pages.currentWidget(), view)
                runtime.connectors["twitch"].status = "conectado (EventSub)"
                runtime.dashboard.signal("twitch", True, viewers=7, title="<a href='https://example.org'>texto</a>")
                runtime.submit(runtime.bus.publish(Event("twitch", "chat", "ana", {"text": "hola"}))).result(5)
                runtime.submit(runtime.bus.publish(sample_event("chat"))).result(5)
                view.refresh()
                self.assertEqual(view.summary["live"].text(), "1")
                self.assertEqual(view.summary["chat"].text(), "1")
                self.assertIn("Espectadores: 7", view.cards["twitch"].audience.text())
                self.assertIn("SIN CONFIRMAR", view.cards["kick"].live_flag.text())
                win.findChild(QPushButton, "dashboard-open-chat").click()
                self.assertIs(win.pages.currentWidget(), win.chat_page)
                self.assertFalse(view.timer.isActive())
                win.select_page("dashboard")
                win.findChild(QPushButton, "dashboard-connect-kick").click()
                self.assertIs(win.pages.currentWidget(), win.connections_page)
                win.close()
            finally:
                runtime.stop()
