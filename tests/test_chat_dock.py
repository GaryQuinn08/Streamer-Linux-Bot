"""Private chat dock is separate from viewer overlays and read-only."""
import asyncio
import os
from pathlib import Path
import stat
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from aiohttp import ClientSession, WSServerHandshakeError

from slbot.chat_dock import KEY_NAME, load_key
from slbot.core.config import Config
from slbot.core.events import Event
from slbot.runtime import Runtime


class ChatDockTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.profile = Path(folder.name)
        env = patch.dict(os.environ, {"SLB_CONFIG_DIR": folder.name, "SLB_DATA_DIR": folder.name})
        env.start()
        self.addCleanup(env.stop)
        self.rt = Runtime(config=Config.load(self.profile / "custom-profile.json"), port=0)
        await self.rt.overlays.start(0)
        self.addAsyncCleanup(self.rt.overlays.stop)
        self.client = ClientSession()
        self.addAsyncCleanup(self.client.close)

    @property
    def base(self):
        return f"http://127.0.0.1:{self.rt.port}"

    async def test_private_capability_survives_restart_and_is_not_in_catalog(self):
        path = self.rt.overlays.chat_dock_path
        self.assertRegex(path, r"^/dock/chat/[A-Za-z0-9_-]{32}/$")
        key = self.profile / KEY_NAME
        self.assertEqual(stat.S_IMODE(key.stat().st_mode), 0o600)
        self.assertEqual(load_key(self.profile), path.split("/")[-2])
        for missing in ("/dock/chat/", "/dock/chat/" + "?" * 32, "/dock/chat/" + "0" * 32 + "/"):
            async with self.client.get(self.base + missing) as response:
                self.assertEqual(response.status, 404)
        for unrelated in ("/", "/api/overlays", "/sdk/overlay-sdk.js"):
            async with self.client.get(self.base + unrelated) as response:
                self.assertNotIn(path.split("/")[-2], await response.text())
        async with self.client.get(self.base + path) as response:
            self.assertEqual(response.status, 200)
            self.assertEqual(response.headers["Cache-Control"], "no-store")
            self.assertEqual(response.headers["Referrer-Policy"], "no-referrer")
            self.assertIn("frame-ancestors 'none'", response.headers["Content-Security-Policy"])
            self.assertIn("Chat privado", await response.text())
        await self.rt.overlays.stop()
        self.assertIsNone(self.rt.overlays.chat_dock_path)
        await self.rt.overlays.start(0)
        self.assertEqual(self.rt.overlays.chat_dock_path, path)

    async def test_feed_excludes_simulations_and_input_never_reaches_public_overlay(self):
        path = self.base + self.rt.overlays.chat_dock_path + "events"
        for origin in ({}, {"Origin": "https://example.invalid"}, {"Origin": "http://localhost:8080"}):
            with self.assertRaises(WSServerHandshakeError) as error:
                await self.client.ws_connect(path, headers=origin)
            self.assertEqual(error.exception.status, 403)
        async with self.client.ws_connect(path, origin=self.base) as dock, \
                self.client.ws_connect(self.base + "/ws/multi-chat", origin=self.base) as public:
            self.assertEqual(await dock.receive_json(), {"channel": "dock", "type": "hello"})
            await public.receive_json()
            await public.receive_json()  # Only viewer overlay receives chat-settings.
            await self.rt.overlays.forward_chat(Event("twitch", "chat", "Luna", {"text": "Demo", "simulated": True}))
            self.assertTrue((await public.receive_json())["simulated"])
            with self.assertRaises(TimeoutError):
                await dock.receive_json(timeout=.08)
            for platform in ("twitch", "youtube", "kick", "tiktok"):
                await self.rt.overlays.forward_chat(Event(platform, "chat", "Luna", {"text": f"Hola {platform}"}))
                item = await dock.receive_json(timeout=1)
                self.assertEqual(item["platform"], platform)
                self.assertEqual(item["text"], f"Hola {platform}")
                await public.receive_json(timeout=1)
            await dock.send_json({"channel": "chat", "platform": "twitch", "text": "No debe salir"})
            closed = await dock.receive(timeout=1)
            self.assertEqual(closed.data, 1008)
            with self.assertRaises(TimeoutError):
                await public.receive_json(timeout=.08)

    async def test_insecure_existing_key_does_not_disable_public_overlays(self):
        await self.rt.overlays.stop()
        (self.profile / KEY_NAME).chmod(0o644)
        await self.rt.overlays.start(0)
        self.assertIsNone(self.rt.overlays.chat_dock_path)
        async with self.client.get(self.base + "/overlay/multi-chat/") as response:
            self.assertEqual(response.status, 200)
