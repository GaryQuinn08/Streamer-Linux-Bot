from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from slbot import audio
from slbot.chat_tts import ChatTtsSettings
from slbot.core.config import Action, Config
from slbot.core.events import Event
from slbot.runtime import Runtime


def chat(source, who, text, *, simulated=False):
    return Event(source, "chat", who, {"text": text, "simulated": simulated})


class ChatTtsRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.profile = Path(self.folder.name) / "config.json"
        self.rt = Runtime(config=Config.load(self.profile), port=0)
        await self.rt._startup()

    async def asyncTearDown(self):
        await self.rt._shutdown()

    async def drain(self):
        if self.rt.chat_tts._worker:
            await asyncio.wait_for(asyncio.shield(self.rt.chat_tts._worker), 2)

    async def test_explicit_per_network_opt_in_without_altering_chat(self):
        voice = AsyncMock()
        with patch("slbot.audio._say", voice):
            self.assertEqual(self.rt.chat_tts.settings, ChatTtsSettings())
            await self.rt.bus.publish(chat("twitch", "silent", "Sigue siendo visible"))
            await self.drain()
            voice.assert_not_awaited()
            settings = await self.rt.configure_chat_tts(True, ["kick", "twitch", "youtube", "tiktok"])
            self.assertEqual(settings.platforms, {"kick", "twitch", "youtube", "tiktok"})
            self.assertEqual(Config.load(self.profile).settings["chat_tts"]["platforms"],
                             ["twitch", "tiktok", "youtube", "kick"])
            for source in ("kick", "twitch", "youtube", "tiktok"):
                await self.rt.bus.publish(chat(source, "Viewer", f"Saludos desde {source}"))
            await self.drain()
            self.assertEqual([args.args[1] for args in voice.await_args_list],
                             [f"Viewer dice: Saludos desde {key}" for key in ("kick", "twitch", "youtube", "tiktok")])
            await self.rt.configure_chat_tts(True, ["youtube"])
            await self.rt.bus.publish(chat("kick", "Kick", "Esto ya no se oye"))
            await self.rt.bus.publish(chat("youtube", "YouTube", "Uno solo puede hablar"))
            await self.drain()
            self.assertEqual(voice.await_count, 5)
            self.assertEqual([line.text for line in self.rt.chat_snapshot()][-2:],
                             ["Esto ya no se oye", "Uno solo puede hablar"])

    async def test_simulated_commands_links_spam_and_duplicates_are_silent(self):
        voice = AsyncMock()
        with patch("slbot.audio._say", voice):
            await self.rt.configure_chat_tts(True, ["youtube", "tiktok"])
            data = [
                chat("tiktok", "demo", "Muestra visible", simulated=True),
                chat("tiktok", "unaltered", "！play mi canción"),
                chat("tiktok", "slash", "/vote 2"),
                chat("tiktok", "url", "Vete a h​ttps://example.org ahora"),
                chat("tiktok", "site", "Mira mi página kick.com/u"),
                chat("tiktok", "ip", "Vete a 192.0.2.10"),
                chat("tiktok", "spam", "jajajaaaaaaaaaa"),
                chat("tiktok", "tag", "literal <em>hola</em>"),
                Event("tiktok", "command", "twice", {"text": "No se repite"}),
                chat("tiktok", "ok", "¡Buen directo!"),
                chat("tiktok", "OK", "Siguiente mensaje del mismo usuario"),
                chat("youtube", "other", "¡BUEN DIRECTO!"),
                chat("youtube", "other", "Qué buen día"),
            ]
            for event in data:
                await self.rt.bus.publish(event)
            await self.drain()
            self.assertEqual([args.args[1] for args in voice.await_args_list], ["ok dice: ¡Buen directo!", "other dice: Qué buen día"])
            self.assertEqual(len(self.rt.chat_snapshot()), len(data) - 1)
            self.assertTrue(self.rt.chat_snapshot()[0].simulated)

    async def test_speaks_display_name_safely_and_falls_back_without_dropping_messages(self):
        voice = AsyncMock()
        with patch("slbot.audio._say", voice):
            await self.rt.configure_chat_tts(True, ["tiktok", "youtube"])
            long_author = "abcdefghijklmnopqrstuvxyz0123456789 " * 3
            inputs = [
                ("tiktok", "@María.José_08 ✨", "¿Ya empezó el directo?"),
                ("youtube", "", "Saludos sin nombre"),
                ("youtube", "https://example.org/<em>", "Mensaje con autor no utilizable"),
                ("youtube", "✨ ⁠", "Sin letras en el nombre"),
                ("youtube", long_author, "Texto " * 43),
            ]
            for platform, name, text in inputs:
                await self.rt.bus.publish(chat(platform, name, text))
            await self.drain()
        said = [args.args[1] for args in voice.await_args_list]
        self.assertEqual(said[:4], [
            "María José 08 dice: ¿Ya empezó el directo?",
            "Alguien dice: Saludos sin nombre",
            "Alguien dice: Mensaje con autor no utilizable",
            "Alguien dice: Sin letras en el nombre",
        ])
        author, separator, message = said[4].partition(" dice: ")
        self.assertEqual(separator, " dice: ")
        self.assertLessEqual(len(author), 40)
        self.assertLessEqual(len(message), 160)
        self.assertTrue(message.endswith("…"))
        self.assertEqual([line.user for line in self.rt.chat_snapshot()], [name for _, name, _ in inputs])

    async def test_fifo_is_bounded_and_clear_cancels_current_without_disabling(self):
        speaks, started, release = [], asyncio.Event(), asyncio.Event()

        async def voice(_runtime, value):
            speaks.append(value)
            started.set()
            await release.wait()

        with patch("slbot.audio._say", side_effect=voice):
            await self.rt.configure_chat_tts(True, ["twitch"])
            await self.rt.bus.publish(chat("twitch", "first", "Primera frase"))
            await asyncio.wait_for(started.wait(), 2)
            for i in range(16):
                await self.rt.bus.publish(chat("twitch", f"viewer-{i}", f"Frase número {i}"))
            self.assertEqual(speaks, ["first dice: Primera frase"])
            self.assertEqual(len(self.rt.chat_tts._pending), 8)
            release.set()
            await self.drain()
            self.assertEqual(speaks, ["first dice: Primera frase"] + [f"viewer {i} dice: Frase número {i}" for i in range(8)])
            release.clear()
            started.clear()
            preview = asyncio.create_task(self.rt.preview_chat_tts())
            await asyncio.wait_for(started.wait(), 2)
            await self.rt.bus.publish(chat("twitch", "waiting", "Descarta lo que esté esperando"))
            await self.rt.clear_chat_tts()
            with self.assertRaisesRegex(RuntimeError, "Se detuvo"):
                await preview
            self.assertFalse(self.rt.chat_tts._pending)
            self.assertEqual(self.rt.chat_tts.settings.platforms, {"twitch"})
            self.assertTrue(self.rt.chat_tts.settings.enabled)
            release.set()
            await self.rt.bus.publish(chat("twitch", "fresh", "La lectura vuelve con un mensaje nuevo"))
            await self.drain()
            self.assertEqual(speaks[-1], "fresh dice: La lectura vuelve con un mensaje nuevo")

    async def test_manual_preview_runs_while_automatic_off_and_reports_errors(self):
        with patch("slbot.audio._say", new_callable=AsyncMock) as voice:
            await self.rt.preview_chat_tts()
            voice.assert_awaited_once_with(self.rt, "Luna dice: ¡Hola! Así sonarán los mensajes de tu chat.")
            self.assertFalse(self.rt.chat_tts.settings.enabled)
            voice.side_effect = RuntimeError("do not reveal private message or process details")
            with self.assertRaisesRegex(RuntimeError, "no terminó"):
                await self.rt.preview_chat_tts()
            self.assertNotIn("do not reveal", " ".join(self.rt.log_history))

    async def test_chat_and_action_share_voice_without_overlapping(self):
        spoken, action_started, release = [], asyncio.Event(), asyncio.Event()

        async def speak(_runtime, value):
            spoken.append(value)
            if value == "Voz desde una acción":
                action_started.set()
                await release.wait()

        with patch("slbot.audio._say", side_effect=speak):
            await self.rt.configure_chat_tts(True, ["tiktok"])
            action = Action("called", "Manual", [{"type": "tts", "text": "Voz desde una acción"}])
            active = asyncio.create_task(self.rt.execute_action(action, Event("system", "test"), "prueba"))
            await asyncio.wait_for(action_started.wait(), 2)
            await self.rt.bus.publish(chat("tiktok", "waiting", "Voz desde chat"))
            await asyncio.sleep(0)
            self.assertEqual(spoken, ["Voz desde una acción"])
            release.set()
            await asyncio.wait_for(active, 2)
            await self.drain()
            self.assertEqual(spoken, ["Voz desde una acción", "waiting dice: Voz desde chat"])

    async def test_shutdown_cancels_speech_and_drops_pending(self):
        started, stopped = asyncio.Event(), asyncio.Event()

        async def speak(*_):
            started.set()
            try:
                await asyncio.Future()
            finally:
                stopped.set()

        with patch("slbot.audio._say", side_effect=speak):
            await self.rt.configure_chat_tts(True, ["kick"])
            await self.rt.bus.publish(chat("kick", "first", "Sonando"))
            await asyncio.wait_for(started.wait(), 2)
            await self.rt.bus.publish(chat("kick", "next", "Nunca se escuchará"))
            await self.rt.chat_tts.close()
        self.assertTrue(stopped.is_set())
        self.assertFalse(self.rt.chat_tts._pending)


class LocalVoiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_espeak_uses_spanish_and_pipes_input(self):
        rt = SimpleNamespace(voice_lock=asyncio.Lock())
        async def run(*args, **kwargs):
            Path(args[4]).write_bytes(b"x" * 100)
            return 0

        with patch.dict(os.environ, {"SLB_PIPER_MODEL": ""}), patch(
            "slbot.audio.shutil.which", return_value="/usr/bin/espeak-ng",
        ), patch("slbot.audio.run_process", side_effect=run) as process, patch(
            "slbot.audio._play_voice", new_callable=AsyncMock,
        ) as play:
            await audio.say(rt, "¡Un mismo texto!")
        (exe, voice_arg, language, output_arg, wav, stdin), kwargs = process.await_args
        self.assertEqual((exe, voice_arg, language, output_arg, stdin),
                         ("/usr/bin/espeak-ng", "-v", "es", "-w", "--stdin"))
        self.assertEqual(kwargs, {"text": "¡Un mismo texto!", "timeout": 10})
        play.assert_awaited_once_with(Path(wav))
        self.assertFalse(Path(wav).exists())

    async def test_missing_engine_is_distinct_from_synthesis_failure(self):
        rt = SimpleNamespace()
        with patch.dict(os.environ, {"SLB_PIPER_MODEL": ""}), patch(
            "slbot.audio.shutil.which", return_value=None,
        ):
            with self.assertRaisesRegex(audio.VoiceError, "Falta la voz local"):
                await audio.say(rt, "Hola")
        with patch.dict(os.environ, {"SLB_PIPER_MODEL": ""}), patch(
            "slbot.audio.shutil.which", return_value="/usr/bin/espeak-ng",
        ), patch("slbot.audio.run_process", new_callable=AsyncMock, side_effect=OSError("private path")):
            with self.assertRaisesRegex(audio.VoiceError, "no pudo generar la voz"):
                await audio.say(rt, "Hola")

    async def test_playback_distinguishes_missing_tools_from_audio_session_failure(self):
        with patch("slbot.audio.shutil.which", return_value=None):
            with self.assertRaisesRegex(audio.VoiceError, "falta un reproductor"):
                await audio._play_voice(Path("/tmp/voice.wav"))
        tools = {"paplay": "/bin/paplay", "pw-play": "/bin/pw-play"}
        with patch("slbot.audio.shutil.which", side_effect=tools.get), patch(
            "slbot.audio.run_process", new_callable=AsyncMock, side_effect=[1, 0, 1, 1],
        ) as run:
            await audio._play_voice(Path("/tmp/voice.wav"))
            self.assertEqual([call.args[0] for call in run.await_args_list], list(tools.values()))
            with self.assertRaisesRegex(audio.VoiceError, "salida de audio"):
                await audio._play_voice(Path("/tmp/voice.wav"))

    async def test_piper_process_failure_falls_back_to_espeak(self):
        with tempfile.TemporaryDirectory() as folder:
            model = Path(folder) / "voice.onnx"
            model.touch()
            model.with_suffix(".onnx.json").touch()
            rt = SimpleNamespace(log=lambda _: None)
            async def run(*args, **kwargs):
                if args[0] == "piper-fixture":
                    return 1
                Path(args[4]).write_bytes(b"x" * 100)
                return 0

            with patch.dict(os.environ, {"SLB_PIPER_MODEL": str(model), "SLB_PIPER": "piper-fixture"}), patch(
                "slbot.audio.shutil.which", return_value="/usr/bin/espeak-ng",
            ), patch("slbot.audio.run_process", side_effect=run) as process, patch(
                "slbot.audio._play_voice", new_callable=AsyncMock,
            ) as play:
                await audio.say(rt, "Hola")
            self.assertEqual([call.args[0] for call in process.await_args_list], ["piper-fixture", "/usr/bin/espeak-ng"])
            play.assert_awaited_once()

    async def test_installed_natural_voice_uses_shared_player_and_never_falls_back_silently(self):
        async def run(*args, **kwargs):
            Path(args[-1]).write_bytes(b"x" * 100)
            return True

        with patch.dict(os.environ, {"SLB_PIPER_MODEL": ""}), patch(
            "slbot.natural_voice.enabled", return_value=True,
        ), patch("slbot.audio._voice_command", side_effect=run) as command, patch(
            "slbot.audio._play_voice", new_callable=AsyncMock,
        ) as play, patch("slbot.audio.shutil.which") as resolve:
            await audio.say(SimpleNamespace(), "Hola, chat")
            self.assertEqual(command.await_args.args[:-1],
                             (sys.executable, "-m", "slbot.natural_voice", "--generar"))
            self.assertEqual(command.await_args.kwargs["text"], "Hola, chat")
            play.assert_awaited_once()
            command.side_effect = None
            command.return_value = False
            with self.assertRaisesRegex(audio.VoiceError, "No se usó la voz básica"):
                await audio.say(SimpleNamespace(), "Hola de nuevo")
            resolve.assert_not_called()

    async def test_cancelling_during_process_creation_recovers_and_stops_child(self):
        spawned, ready = asyncio.Event(), asyncio.Event()
        terminated = []

        class Process:
            returncode = None

            def terminate(self):
                terminated.append("terminate")
                self.returncode = 0

            async def wait(self):
                return self.returncode

        async def create(*args, **kwargs):
            spawned.set()
            await ready.wait()
            return Process()

        with patch("slbot.audio.asyncio.create_subprocess_exec", side_effect=create):
            task = asyncio.create_task(audio.run_process("/usr/bin/example"))
            await asyncio.wait_for(spawned.wait(), 2)
            task.cancel()
            ready.set()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertEqual(terminated, ["terminate"])

    @unittest.skipUnless(os.name == "posix", "requiere señales POSIX")
    async def test_real_process_is_reaped_on_cancel(self):
        with tempfile.TemporaryDirectory() as folder:
            pidfile = Path(folder) / "pid"
            script = (
                "import os, pathlib, sys, time;"
                "pathlib.Path(sys.argv[1]).write_text(str(os.getpid()));"
                "time.sleep(60)"
            )
            task = asyncio.create_task(audio.run_process(sys.executable, "-c", script, str(pidfile)))
            try:
                for _ in range(150):
                    if pidfile.is_file() and pidfile.stat().st_size:
                        break
                    await asyncio.sleep(.02)
                else:
                    self.fail("el subproceso local no inició")
                pid = int(pidfile.read_text())
            finally:
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await asyncio.wait_for(task, 4)
            with self.assertRaises(ProcessLookupError):
                os.kill(pid, 0)
