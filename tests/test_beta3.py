from __future__ import annotations

import asyncio
import base64
import json
import os
import socket
import signal
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import aiohttp

from slbot.audio import MusicQueue
from slbot.connectors.platforms import twitch_events, youtube_events
from slbot.core.config import Config
from slbot.core.editing import update_rules
from slbot.runtime import Runtime


class RuleTests(unittest.TestCase):
    def test_add_trigger_and_ordered_action_and_check_references(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "config.json"
            cfg = Config.load(path)
            steps = [{"type": "obs_scene", "scene": "Inicio"},
                     {"type": "obs_source_visible", "scene": "Inicio", "source": "Cámara", "visible": False}]
            update_rules(cfg, "action", {"id": "custom", "name": "En directo", "steps": steps})
            update_rules(cfg, "trigger", {"id": "custom-trigger", "name": "Comando", "event_type": "command",
                        "platform": "twitch", "filters": {"command": "escena"}, "action_id": "custom"})
            saved = Config.load(path)
            self.assertEqual(saved.action_by_id("custom").steps, steps)
            self.assertIn("custom-trigger", [item.id for item in saved.triggers])
            with self.assertRaisesRegex(ValueError, "todavía se utiliza"):
                update_rules(cfg, "action", {"id": "custom"}, delete=True)
            update_rules(cfg, "trigger", {"id": "custom-trigger"}, delete=True)
            update_rules(cfg, "action", {"id": "custom"}, delete=True)
            self.assertIsNone(Config.load(path).action_by_id("custom"))

    def test_platform_events(self):
        events = twitch_events("channel.chat.message", {"chatter_user_name": "ana", "message": {"text": "!hola 12"}})
        self.assertEqual([ev.type for ev in events], ["chat", "command"])
        self.assertEqual(events[-1].data["command"], "hola")
        events = youtube_events({"snippet": {"type": "superChatEvent",
            "superChatDetails": {"amountMicros": "23500000", "currency": "MXN"}}})
        self.assertEqual(events[0].data["amount"], "23.5")


class ServerTests(unittest.IsolatedAsyncioTestCase):
    async def test_headless_terminal_to_overlay(self):
        with tempfile.TemporaryDirectory() as root, socket.socket() as guard:
            guard.bind(("127.0.0.1", 0))
            port = guard.getsockname()[1]
            guard.close()
            env = {**os.environ, "SLB_CONFIG_DIR": root, "SLB_DATA_DIR": root}
            proc = await asyncio.create_subprocess_exec(sys.executable, "-m", "slbot", "servidor",
                "--puerto", str(port), "--simular", "gift", "--espera", "1",
                env=env, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            try:
                self.assertIn(str(port).encode(), await asyncio.wait_for(proc.stdout.readline(), 10))
                async with aiohttp.ClientSession() as session:
                    async with session.get(f"http://127.0.0.1:{port}/") as reply:
                        self.assertIn("LIVE Studio", await reply.text())
                    async with session.ws_connect(f"http://127.0.0.1:{port}/ws/gift-alert") as ws:
                        self.assertEqual((await ws.receive_json(timeout=3))["type"], "hello")
                        self.assertEqual((await ws.receive_json(timeout=5))["text"], "x3")
            finally:
                if proc.returncode is None:
                    proc.terminate()
                await asyncio.wait_for(proc.communicate(), 5)
            self.assertEqual(proc.returncode, 0)

    @unittest.skipUnless(hasattr(signal, "SIGHUP"), "requiere SIGHUP")
    async def test_server_reloads_profile_without_rebinding(self):
        with tempfile.TemporaryDirectory() as root, socket.socket() as guard:
            guard.bind(("127.0.0.1", 0))
            port = guard.getsockname()[1]
            guard.close()
            env = {**os.environ, "SLB_CONFIG_DIR": root, "SLB_DATA_DIR": root}
            proc = await asyncio.create_subprocess_exec(sys.executable, "-m", "slbot", "servidor",
                "--puerto", str(port), env=env, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            try:
                await asyncio.wait_for(proc.stdout.readline(), 10)
                config = Config.load(Path(root) / "config.json")
                config.settings["overlay_presets"] = {"gift-alert": {"color": "#c0ffee"}}
                config.settings["timers"] = [{"id": "test", "name": "Prueba SIGHUP",
                    "action_id": "alert-gift", "seconds": 1, "enabled": True}]
                config.save()
                proc.send_signal(signal.SIGHUP)
                async with aiohttp.ClientSession() as session:
                    for _ in range(100):
                        async with session.get(f"http://127.0.0.1:{port}/sdk/overlay-sdk.js") as res:
                            if "#c0ffee" in await res.text():
                                break
                        await asyncio.sleep(.02)
                    else:
                        self.fail("no se recargó el preset")
                    async with session.ws_connect(f"http://127.0.0.1:{port}/ws/gift-alert") as ws:
                        self.assertEqual((await ws.receive_json(timeout=3))["type"], "hello")
                        self.assertEqual((await ws.receive_json(timeout=4))["channel"], "alert")
            finally:
                if proc.returncode is None:
                    proc.terminate()
                await asyncio.wait_for(proc.communicate(), 5)
            self.assertEqual(proc.returncode, 0)

    async def test_kick_valid_signature_channel_age_and_duplicate(self):
        try:
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import padding, rsa
        except ImportError:
            self.skipTest("cryptography no instalado (extra --kick)")
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "key.pem"
            path.write_bytes(key.public_key().public_bytes(serialization.Encoding.PEM,
                serialization.PublicFormat.SubjectPublicKeyInfo))
            rt = Runtime(config=Config.defaults())
            seen = []

            async def remember(event):
                seen.append(event)

            rt.bus.subscribe(remember)
            kick = rt.connectors["kick"]
            await kick.start(0, 123, path)

            def packet(owner=123, time_delta=0, ident="signed001", kind="chat.message.sent", custom=None):
                body = {"broadcaster": {"user_id": owner},
                        **(custom or {"sender": {"username": "ana"}, "content": "hola"})}
                raw = json.dumps(body).encode()
                stamp = (datetime.now(timezone.utc) + timedelta(seconds=time_delta)).isoformat()
                signature = key.sign(f"{ident}.{stamp}.".encode() + raw, padding.PKCS1v15(), hashes.SHA256())
                return raw, {"Kick-Event-Message-Id": ident, "Kick-Event-Message-Timestamp": stamp,
                             "Kick-Event-Signature": base64.b64encode(signature).decode(),
                             "Kick-Event-Type": kind, "Kick-Event-Version": "1"}

            try:
                async with aiohttp.ClientSession() as session:
                    endpoint = f"http://127.0.0.1:{kick.port}/webhooks/kick"
                    raw, headers = packet()
                    for _ in range(2):
                        async with session.post(endpoint, data=raw, headers=headers) as response:
                            self.assertEqual(response.status, 204)
                    async with session.post(endpoint, data=raw + b" ", headers=headers) as response:
                        self.assertEqual(response.status, 401)
                    kind = "livestream.status.updated"
                    start = {"is_live": True, "title": "En vivo", "started_at": "2026-11-26T12:20:00Z"}
                    raw, headers = packet(ident="stream001", kind=kind, custom=start)
                    async with session.post(endpoint, data=raw, headers=headers) as response:
                        self.assertEqual(response.status, 204)
                    current = rt.dashboard.snapshot()["kick"]
                    self.assertTrue(current.live)
                    self.assertEqual(current.title, "En vivo")
                    self.assertIsNone(current.viewers)
                    raw, headers = packet(ident="stream002", kind=kind, custom={**start, "is_live": False,
                                                                                "ended_at": "2026-11-26T13:10:00Z"})
                    async with session.post(endpoint, data=raw, headers=headers) as response:
                        self.assertEqual(response.status, 204)
                    self.assertIs(rt.dashboard.snapshot()["kick"].live, False)
                    raw, headers = packet(124)
                    async with session.post(endpoint, data=raw, headers=headers) as response:
                        self.assertEqual(response.status, 403)
                    raw, headers = packet(time_delta=-600)
                    async with session.post(endpoint, data=raw, headers=headers) as response:
                        self.assertEqual(response.status, 401)
            finally:
                await kick.stop()
            self.assertEqual([(event.platform, event.user) for event in seen], [("kick", "ana")])

    async def test_music_queue_single_player_fifo(self):
        rt = Runtime(config=Config.defaults())
        queue = MusicQueue(rt)
        with tempfile.TemporaryDirectory() as root:
            files = [Path(root) / name for name in ("uno.wav", "dos.mp3")]
            for path in files:
                path.touch()
            with patch("slbot.audio.shutil.which", return_value="/usr/bin/mpv"), patch(
                    "slbot.audio.run_process", new_callable=AsyncMock, return_value=0) as play:
                for item in files:
                    queue.enqueue(str(item))
                await asyncio.wait_for(queue.items.join(), 3)
                self.assertEqual([call.args[-1] for call in play.await_args_list], [str(p) for p in files])
                await queue.clear()
