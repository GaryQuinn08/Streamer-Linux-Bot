import asyncio
import os
import tempfile
import unittest
from unittest.mock import patch

import aiohttp

from slbot.connectors.simulator import sample_event
from slbot.core.config import Config
from slbot.core.events import Event
from slbot.overlay_manager import find_overlay, validate_overlay_values
from slbot.runtime import Runtime


class MultiChatTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        env = patch.dict(os.environ, {"SLB_DATA_DIR": tmp.name, "SLB_CONFIG_DIR": tmp.name})
        env.start()
        self.addCleanup(env.stop)
        self.rt = Runtime(config=Config.defaults(), port=0)
        await self.rt._startup()
        self.addAsyncCleanup(self.rt._shutdown)
        self.base = f"http://127.0.0.1:{self.rt.port}"

    async def test_catalog_serves_builtin_with_bounded_preferences(self):
        card = find_overlay("multi-chat")
        self.assertEqual(card.source, "builtin")
        self.assertEqual(validate_overlay_values(card, {"twitch": "false", "max": "12"}),
                         {"twitch": "false", "max": "12"})
        with self.assertRaises(ValueError):
            validate_overlay_values(card, {"max": "25"})
        async with aiohttp.ClientSession() as session:
            async with session.get(self.base + "/") as catalog:
                self.assertIn("/overlay/multi-chat/", await catalog.text())
            async with session.get(self.base + "/overlay/multi-chat/") as source:
                self.assertEqual(source.status, 200)
                body = await source.text()
                self.assertIn("Chat multiplataforma", body)
                self.assertIn("Content-Security-Policy", body)
            async with session.get(self.base + "/overlay/multi-chat/script.js") as script:
                source = await script.text()
                self.assertIn(".textContent =", source)
                self.assertNotIn(".innerHTML", source)

    async def test_chat_only_from_supported_platforms_and_no_connector_data_leaks(self):
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(self.base + "/ws/multi-chat") as chat:
                self.assertEqual((await chat.receive_json(timeout=2))["type"], "hello")
                await self.rt.bus.publish(Event("twitch", "command", "viewer", {"text": "!demo"}))
                await self.rt.bus.publish(Event("youtube", "follow", "viewer"))
                await self.rt.bus.publish(Event("manual", "chat", "viewer", {"text": "ignored"}))
                await self.rt.bus.publish(Event("kick", "chat", "viewer", {"text": "  "}))
                await self.rt.bus.publish(Event("tiktok", "chat", "x" * 150, {
                    "text": "<x>" * 180, "profile": "ignored", "token": "ignored",
                }))
                observed = await chat.receive_json(timeout=2)
                self.assertEqual(observed, {
                    "channel": "chat", "platform": "tiktok", "user": "x" * 100,
                    "text": ("<x>" * 180)[:500], "simulated": False,
                })
                for platform in ("twitch", "youtube", "kick"):
                    await self.rt.bus.publish(Event(platform, "chat", platform, {"text": "hola"}))
                    self.assertEqual((await chat.receive_json(timeout=2))["platform"], platform)

    async def test_preview_and_simulation_are_marked_and_not_replayed(self):
        # An ordinary overlay client cannot send an event to the browser source.
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(self.base + "/ws/multi-chat") as chat:
                await chat.receive_json(timeout=2)
                await chat.send_json({"channel": "chat", "platform": "twitch", "text": "unauthorized"})
                await self.rt.preview_overlay("multi-chat")
                previews = [await chat.receive_json(timeout=2) for _ in range(4)]
                self.assertEqual({item["platform"] for item in previews}, {"twitch", "youtube", "kick", "tiktok"})
                self.assertTrue(all(item["simulated"] is True for item in previews))
                self.assertEqual(self.rt.chat_snapshot(), ())
                await self.rt.bus.publish(sample_event("chat"))
                self.assertTrue((await chat.receive_json(timeout=2))["simulated"])
            async with session.ws_connect(self.base + "/ws/multi-chat") as reopened:
                self.assertEqual((await reopened.receive_json(timeout=2))["type"], "hello")
                with self.assertRaises(asyncio.TimeoutError):
                    await reopened.receive_json(timeout=.05)
