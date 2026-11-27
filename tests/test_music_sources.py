from __future__ import annotations

import asyncio
import os
import socket
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from slbot.audio import MusicQueue, PublicAudioResolver, _matches_audio, licensed_audio
from slbot.connectors.spotify import SpotifyConnector, spotify_track_uri

TRACK = "4iV5W9uYEdYUVa79Axb7Rh"
GOAL = "spotify:track:" + TRACK


class MusicSourceTests(unittest.TestCase):
    def test_spotify_uses_only_canonical_song_uri(self):
        self.assertEqual(spotify_track_uri(GOAL), GOAL)
        self.assertEqual(spotify_track_uri(f"https://open.spotify.com/intl-es/track/{TRACK}?si=private"), GOAL)
        for url in (f"https://example.com/track/{TRACK}", f"https://open.spotify.com@evil.test/track/{TRACK}",
                    f"http://open.spotify.com/track/{TRACK}", f"https://open.spotify.com/playlist/{TRACK}",
                    f"https://open.spotify.com/track/{TRACK}/extra", "spotify:episode:" + TRACK):
            with self.subTest(url=url), self.assertRaises(ValueError):
                spotify_track_uri(url)

    def test_external_audio_requires_https_dns_and_never_shows_query(self):
        item = licensed_audio("https://music.example.org/path/pista.mp3?token=private")
        self.assertIn("music.example.org", item.name)
        self.assertNotIn("private", item.name)
        for url in ("https://8.8.8.8/foo.mp3", "https://127.0.0.1/file.wav",
                    "https://[::ffff:127.0.0.1]/file.wav", "https://localhost/file.wav",
                    "http://music.example.org/file.wav", "https://u:pw@music.example.org/file.wav",
                    "https://music.example.org:444/file.wav", "file:///etc/passwd"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                licensed_audio(url)
        self.assertTrue(_matches_audio("mp3", b"ID3" + b"x" * 100))
        self.assertFalse(_matches_audio("mp3", b"<!doctype html>"))
        self.assertFalse(_matches_audio("ogg", b"OggS" + b"encoded-video"))


class NetworkFixtureTests(unittest.IsolatedAsyncioTestCase):
    async def test_dns_resolver_filters_local_results_at_connection(self):
        resolver = PublicAudioResolver()
        fixture = AsyncMock()
        fixture.resolve.return_value = [{"host": "127.0.0.1"}, {"host": "::ffff:10.1.10.1"},
                                        {"host": "224.0.0.1"}, {"host": "8.8.8.8"}]
        try:
            with patch.object(resolver, "_resolver", fixture):
                self.assertEqual(await resolver.resolve("demo.example.org", 443, socket.AF_INET),
                                 [{"host": "8.8.8.8"}])
                fixture.resolve.return_value = [{"host": "169.254.169.254"}]
                with self.assertRaises(OSError):
                    await resolver.resolve("demo.example.org", 443)
        finally:
            await resolver.close()

    async def test_spotify_post_passes_only_queue_uri_and_fixed_api(self):
        connector = SpotifyConnector(SimpleNamespace())
        with patch("slbot.connectors.spotify.browser_client", new_callable=AsyncMock) as client, patch(
            "slbot.connectors.spotify.sign_in", new_callable=AsyncMock
        ) as sign_in:
            client.return_value = "development client placeholder"
            sign_in.return_value = "fake token"
            await connector.start(browser=AsyncMock(), setting="publicid123")
            await connector._task
        self.assertTrue(connector.connected)
        response = SimpleNamespace(status=204)
        session = MagicMock()
        session.__aenter__.return_value = session
        session.post.return_value.__aenter__.return_value = response

        with patch("slbot.connectors.spotify.aiohttp.ClientSession", return_value=session):
            await connector.enqueue(f"https://open.spotify.com/track/{TRACK}")
            self.assertEqual(session.post.call_args.args, ("https://api.spotify.com/v1/me/player/queue",))
            self.assertEqual(session.post.call_args.kwargs["params"], {"uri": GOAL})
            self.assertFalse(session.post.call_args.kwargs["allow_redirects"])
            response.status = 401
            with self.assertRaisesRegex(ValueError, "expiró"):
                await connector.enqueue(GOAL)
        self.assertFalse(connector.connected)
        await connector.stop()

    async def test_online_audio_passes_temporary_file_not_url_to_player(self):
        state = {}
        rt = SimpleNamespace(spawn=asyncio.create_task, log=MagicMock())
        queue = MusicQueue(rt)

        async def download(item, directory):
            self.assertEqual(item.url.raw_host, "music.example.org")
            path = directory / "test.wav"
            path.write_bytes(b"stand-in")
            return path, "wav"

        async def run(*arguments):
            self.assertIn("--demuxer-lavf-format=wav", arguments)
            self.assertIn("--demuxer-lavf-o=protocol_whitelist=file", arguments)
            state["path"] = Path(arguments[-1])
            self.assertEqual(state["path"].read_bytes(), b"stand-in")
            return 0

        with patch("slbot.audio.shutil.which", return_value="/usr/bin/mpv"), patch(
            "slbot.audio._download_audio", side_effect=download
        ), patch("slbot.audio.run_process", side_effect=run):
            queue.enqueue_url("https://music.example.org/test.wav?token=private")
            await asyncio.wait_for(queue.items.join(), 3)
        self.assertFalse(state["path"].exists())
        self.assertNotIn("token=private", str(rt.log.mock_calls))


class MusicPanelTests(unittest.TestCase):
    def test_private_approval_and_browser_handoff_in_gui(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QApplication
        from slbot.core.config import Config
        from slbot.runtime import Runtime
        from slbot.ui.music_panel import MusicPanel

        app = QApplication.instance() or QApplication([])
        rt = Runtime(config=Config.defaults(), port=0)
        rt.connectors["spotify"] = SpotifyConnector(rt)
        rt.start()
        panel = MusicPanel(rt)
        panel.show()

        async def fake_authorize(_client, open_browser):
            await open_browser("https://accounts.spotify.com/authorize")
            return "mock token"

        try:
            with patch("slbot.ui.music_panel.deployment_setting", return_value="examplepublic123"), patch(
                "slbot.connectors.spotify.sign_in", side_effect=fake_authorize
            ), patch("slbot.ui.music_panel.QDesktopServices.openUrl", return_value=True) as browser:
                self.assertFalse(panel.connect.isEnabled())
                self.assertFalse(panel.url_button.isEnabled())
                panel.private.setChecked(True)
                QTest.mouseClick(panel.connect, Qt.MouseButton.LeftButton)
                deadline = time.monotonic() + 3
                while not browser.called and time.monotonic() < deadline:
                    app.processEvents()
                    time.sleep(.015)
                self.assertTrue(browser.called)
                self.assertEqual(browser.call_args.args[0].host(), "accounts.spotify.com")
                panel.private.setChecked(False)
                self.assertFalse(panel.add_spotify.isEnabled())
        finally:
            panel.close()
            rt.stop()
