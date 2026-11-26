"""Read-only music metadata: bounded input, selected source, opt-in lifecycle."""
import asyncio
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from slbot.core.config import Config
from slbot.now_playing import (BOT_SOURCE, CONFIG_KEY, MPRIS_PREFIX, MPRIS_PLAYER,
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
            await service.apply(NowPlayingSettings.select(True, PLAYER))
            await asyncio.sleep(0.03)
            self.assertEqual(service.snapshot(), received.as_dict())
            self.assertTrue(all(call.args == (PLAYER,) for call in read.call_args_list))
            self.assertEqual(rt.overlays.broadcast_now_playing.await_count, 1)
            await service.apply(NowPlayingSettings())
            self.assertEqual(service.snapshot(), Track().as_dict())
            self.assertEqual(rt.overlays.broadcast_now_playing.await_count, 2)
            await service.close()

    async def test_runtime_profile_and_bot_music_snapshot(self):
        with tempfile.TemporaryDirectory() as folder:
            config = Config.load(Path(folder) / "profile.json")
            rt = Runtime(config=config)
            rt.now_playing._interval = 0.01
            stub = AsyncMock()
            with patch.object(rt.overlays, "broadcast_now_playing", stub, create=True):
                self.assertFalse(rt.now_playing.settings.enabled)
                rt.music.now_playing_title = "Cielo claro"
                await rt.configure_now_playing(True, BOT_SOURCE)
                await asyncio.sleep(0.02)
                self.assertEqual(rt.now_playing.snapshot(), Track("playing", "Cielo claro", "", "Bot").as_dict())
                self.assertEqual(Config.load(config.path).settings[CONFIG_KEY],
                                 {"enabled": True, "source": BOT_SOURCE})
                await rt.configure_now_playing(False, BOT_SOURCE)
                self.assertEqual(rt.now_playing.snapshot(), Track().as_dict())
                self.assertEqual(stub.await_count, 2)
                await rt.now_playing.close()

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
