"""Read-only music metadata: bounded input, selected source, opt-in lifecycle."""
import asyncio
from pathlib import Path

import aiohttp
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from slbot.core.config import Config
from slbot.now_playing import (SPOTIFY_DESKTOP, CONFIG_KEY, MPRIS_PREFIX, MPRIS_PLAYER,
                               NowPlaying, NowPlayingSettings, Track, _bus, available_players,
                               clean_metadata, mpris_track)
from slbot.runtime import Runtime

PLAYER = MPRIS_PREFIX + "chromium.instance1234"
VARIANT = lambda kind, value: {"type": kind, "data": value}
PROPERTY = lambda kind, value: VARIANT("v", [VARIANT(kind, value)])


class NowPlayingTests(unittest.IsolatedAsyncioTestCase):
    async def test_player_discovery_only_gets_exact_mpris_names(self):
        with patch("slbot.now_playing._bus", new_callable=AsyncMock) as command:
            command.return_value = VARIANT("as", [[PLAYER, "org.freedesktop.secrets", PLAYER, MPRIS_PREFIX + "%any"]])
            self.assertEqual(await available_players(), (PLAYER,))
            self.assertEqual(command.await_count, 1)
            self.assertEqual(command.await_args.args[-1], "ListNames")

    async def test_read_exact_mpris_instance_and_publish_safe_fields_only(self):
        with patch("slbot.now_playing._bus", new_callable=AsyncMock) as command:
            command.side_effect = [
                PROPERTY("s", "Paused"),
                PROPERTY("a{sv}", {
                    "xesam:title": VARIANT("s", "Canción\n de\u202e prueba"),
                    "xesam:artist": VARIANT("as", ["Luna", "Río", "https://provider.invalid/secret"]),
                    "mpris:artUrl": VARIANT("s", "file:///home/gary/private.jpg"),
                    "xesam:url": VARIANT("s", "https://provider.invalid?token=private"),
                }),
            ]
            self.assertEqual(await mpris_track(PLAYER), Track("paused", "Canción de prueba", "Luna, Río", "chromium.instance1234"))
            self.assertEqual([args.args[-1] for args in command.await_args_list], ["PlaybackStatus", "Metadata"])
            self.assertTrue(all(args.args[1] == PLAYER and args.args[-2] == MPRIS_PLAYER
                                for args in command.await_args_list))

    async def test_stopped_player_no_metadata_request_and_invalid_never_passed_to_bus(self):
        with patch("slbot.now_playing._bus", new_callable=AsyncMock) as command:
            command.return_value = PROPERTY("s", "Stopped")
            self.assertEqual(await mpris_track(PLAYER), Track())
            self.assertEqual(await mpris_track("--version"), Track())
            command.assert_awaited_once()

    async def test_user_opt_in_tracks_single_source_and_disable_clears(self):
        rt = SimpleNamespace(
            editor_only=False, music=SimpleNamespace(now_playing_title=""), overlays=SimpleNamespace(
                broadcast_now_playing=AsyncMock()))
        service = NowPlaying(rt, NowPlayingSettings(), interval=0.01)
        received = Track("playing", "Garabato", "Tinta", "chromium.instance1234")
        with patch("slbot.now_playing.mpris_track", return_value=received) as read:
            await service.apply(service.settings)
            await asyncio.sleep(0.02)
            read.assert_not_called()
            await service.apply(NowPlayingSettings.select(True, SPOTIFY_DESKTOP))
            await asyncio.sleep(0.03)
            self.assertEqual(service.snapshot(), received.as_dict())
            self.assertTrue(all(call.args == (SPOTIFY_DESKTOP,) for call in read.call_args_list))
            self.assertEqual(rt.overlays.broadcast_now_playing.await_count, 1)
            await service.apply(NowPlayingSettings())
            self.assertEqual(service.snapshot(), Track().as_dict())
            self.assertEqual(rt.overlays.broadcast_now_playing.await_count, 2)
            await service.close()

    async def test_revision_migrates_old_local_selection_and_rejects_unaffiliated_apps(self):
        for source in ("bot", PLAYER, "web:imitation"):
            self.assertEqual(NowPlayingSettings.from_config({CONFIG_KEY: {"enabled": True, "source": source}}),
                             NowPlayingSettings())
            with self.assertRaises(ValueError):
                NowPlayingSettings.select(True, source)

    async def test_extension_post_updates_both_overlays_only_with_correct_code_and_provider(self):
        with tempfile.TemporaryDirectory() as folder:
            config = Config.load(Path(folder) / "profile.json")
            rt = Runtime(config=config, port=0)
            await rt._startup()
            try:
                self.assertEqual(rt.now_playing.pairing_code(rt.port), "")
                await rt.configure_now_playing(True, "web:youtube")
                code = rt.now_playing.pairing_code(rt.port)
                port, token = code.split(".")
                self.assertEqual(int(port), rt.port)
                self.assertNotIn(token, config.path.read_text())
                self.assertEqual(Config.load(config.path).settings[CONFIG_KEY],
                                 {"enabled": True, "source": "web:youtube"})
                base = f"http://127.0.0.1:{rt.port}"
                headers = {"Authorization": "Bearer " + token, "Origin": "chrome-extension://" + "a" * 32}
                body = {"state": "playing", "title": "Cielo claro", "artist": "Luna", "provider": "youtube"}
                async with aiohttp.ClientSession() as session:
                    async with session.ws_connect(base + "/ws/now-playing") as vinyl, session.ws_connect(
                        base + "/ws/now-playing-spectrum") as neon:
                        for socket in (vinyl, neon):
                            await socket.receive_json(timeout=1)
                            self.assertEqual((await socket.receive_json(timeout=1))["channel"], "now-playing-settings")
                            self.assertEqual((await socket.receive_json(timeout=1))["state"], "idle")
                        for status, request_headers, payload in (
                            (403, {**headers, "Origin": "https://music.youtube.com"}, body),
                            (403, {**headers, "Authorization": "Bearer wrong"}, body),
                            (400, headers, {**body, "provider": "amazon"}),
                            (400, headers, {**body, "url": "https://music.youtube.com"}),
                            (204, headers, body),
                        ):
                            async with session.post(base + "/api/music/browser", json=payload, headers=request_headers) as response:
                                self.assertEqual(response.status, status)
                        for socket in (vinyl, neon):
                            self.assertEqual(await socket.receive_json(timeout=1), {
                                "channel": "now-playing", "state": "playing", "title": "Cielo claro", "artist": "Luna",
                            })
                        await rt.configure_now_playing(True, "web:amazon")
                        self.assertNotEqual(rt.now_playing.pairing_code(rt.port), code)
                        self.assertEqual((await vinyl.receive_json(timeout=1))["state"], "idle")
                        async with session.post(base + "/api/music/browser", json=body, headers=headers) as response:
                            self.assertEqual(response.status, 403)
            finally:
                await rt._shutdown()

    async def test_bus_subprocess_bounds_and_malformed_output(self):
        with tempfile.TemporaryDirectory() as folder:
            fake = Path(folder) / "busctl"
            fake.write_text("#!/bin/sh\nprintf '%s' '{\"type\":\"s\",\"data\":\"ok\"}'\n")
            fake.chmod(0o755)
            with patch("slbot.now_playing.shutil.which", return_value=str(fake)):
                self.assertEqual(await _bus("test"), VARIANT("s", "ok"))
                fake.write_text("#!/bin/sh\nprintf '%065538d' 0\n")
                self.assertIsNone(await asyncio.wait_for(_bus("test"), 3))
                fake.write_text("#!/bin/sh\nprintf '%s' 'not json'\n")
                self.assertIsNone(await _bus("test"))

    def test_rejects_urls_paths_and_credential_patterns_without_publishing_partial(self):
        for unsafe in ("See https://site.invalid/x", "www.site.invalid", "pista file:///tmp/secret.wav",
                       "Cuarto /home/private/secret", "C:\\Users\\private\\music", "../folder/private",
                       "relative/private.txt", "visit example.org/private.txt", "token=secret",
                       "secret 120cfc06425bf24d9ab77098cea924e3", "Bearer abc", "pista.mp3"):
            with self.subTest(unsafe=unsafe):
                self.assertEqual(clean_metadata(unsafe, 110), "")
        self.assertEqual(clean_metadata("AC/DC y José", 90), "AC/DC y José")

    def test_config_never_infers_opt_in_from_presence_of_player(self):
        for enabled in (False, "yes", 1, None):
            state = NowPlayingSettings.from_config({CONFIG_KEY: {"enabled": enabled, "source": PLAYER}})
            self.assertEqual(state, NowPlayingSettings())


if __name__ == "__main__":
    unittest.main()
