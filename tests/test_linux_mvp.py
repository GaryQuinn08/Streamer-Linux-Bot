"""Protect the installed beta's main work flows."""
from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from aiohttp import web

from slbot.connectors.tiktok import TiktokConnector, normalize_live_gift, normalize_tikfinity
from slbot.core.config import Config
from slbot.core.events import Event
from test_smoke import RuntimeCase


class ConfigTests(unittest.TestCase):
    def test_migrates_obs_password_without_removing_other_data(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "config.json"
            path.write_text(json.dumps({
                "settings": {"obs": {"host": "localhost", "port": 4456, "password": "old-test",
                                     "autoconnect": True}},
                "extension": {"id": 42},
            }), encoding="utf-8")
            conf = Config.load(path)
            self.assertFalse(conf.settings["obs"]["autoconnect"])
            self.assertNotIn("password", conf.settings["obs"])
            persisted = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(persisted["extension"], {"id": 42})
            self.assertNotIn("password", persisted["settings"]["obs"])


class GiftEditorTests(RuntimeCase):
    def test_saved_rule_reapplies_and_updates_alert(self):
        import aiohttp

        self.rt.submit(self.rt.save_gift_rule(True, "Rose", 0, "Hola, {user}")).result(5)

        async def flow():
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(f"{self.base_url}/ws/gift-alert") as ws:
                    await ws.receive_json(timeout=5)
                    self.rt.emit(Event("tiktok", "gift", "demo", {"gift_name": "Star", "value": 5}))
                    self.rt.emit(Event("tiktok", "gift", "demo", {"gift_name": "Rose", "value": 5}))
                    self.assertEqual((await ws.receive_json(timeout=5))["title"], "Hola, demo")
                    with self.assertRaises(asyncio.TimeoutError):
                        await ws.receive_json(timeout=0.1)

        asyncio.run(flow())
        config = Config.load(self.rt.config.path)
        self.assertEqual(config.triggers[0].filters["gift_name"], "Rose")
        self.assertEqual(config.action_by_id("alert-gift").steps[0]["title"], "Hola, {user}")


class TiktokTests(unittest.IsolatedAsyncioTestCase):
    async def test_local_event_api_maps_final_streak_and_does_not_replay_duplicates(self):
        delivered = []

        async def publish(event):
            delivered.append(event)

        packet = {"event": "gift", "data": {
            "nickname": "demo", "giftName": "Rose", "giftType": 1,
            "repeatCount": 3, "diamondCount": 1, "repeatEnd": True, "msgId": "test-gift-1",
        }}

        async def producer(request):
            ws = web.WebSocketResponse()
            await ws.prepare(request)
            await ws.send_json({"event": "gift", "data": {**packet["data"], "repeatEnd": False}})
            await ws.send_json(packet)
            await ws.send_json(packet)
            await ws.close()
            return ws

        app = web.Application()
        app.router.add_get("/", producer)
        runner = web.AppRunner(app)
        await runner.setup()
        try:
            site = web.TCPSite(runner, "127.0.0.1", 0)
            await site.start()
            connector = TiktokConnector(SimpleNamespace(bus=SimpleNamespace(publish=publish), log=lambda _: None))
            await connector._tikfinity(f"ws://127.0.0.1:{runner.addresses[0][1]}/")
        finally:
            await runner.cleanup()
        self.assertEqual(len(delivered), 1)
        self.assertEqual(delivered[0].data, {"gift_name": "Rose", "count": 3, "value": 3})

    async def test_direct_gift_normalizer_and_invalid_event(self):
        user = SimpleNamespace(nickname="demo")
        gift = SimpleNamespace(name="Rose", diamond_count=2)
        self.assertIsNone(normalize_live_gift(SimpleNamespace(user=user, gift=gift, streaking=True)))
        result = normalize_live_gift(SimpleNamespace(user=user, gift=gift, streaking=False, repeat_count=4))
        self.assertEqual(result.data["value"], 8)
        self.assertIsNone(normalize_tikfinity({"event": [], "data": {}}))


class DebianObsTests(unittest.IsolatedAsyncioTestCase):
    async def test_obs_v5_requests(self):
        """Use the packaged client with a local OBS-protocol fixture."""
        from slbot.connectors.obs import _DebianObsClient

        requests = []

        async def server(request):
            ws = web.WebSocketResponse()
            await ws.prepare(request)
            from base64 import b64encode
            from hashlib import sha256

            await ws.send_json({"op": 0, "d": {
                "obsWebSocketVersion": "5.6.0", "rpcVersion": 1,
                "authentication": {"salt": "test-salt", "challenge": "test-challenge"},
            }})
            identify = await ws.receive_json(timeout=2)
            self.assertEqual(identify["op"], 1)
            secret = b64encode(sha256(b"fixture-passwordtest-salt").digest())
            expected = b64encode(sha256(secret + b"test-challenge").digest()).decode()
            self.assertEqual(identify["d"]["authentication"], expected)
            await ws.send_json({"op": 2, "d": {"negotiatedRpcVersion": 1}})
            async for message in ws:
                payload = message.json()
                self.assertEqual(payload["op"], 6)
                data = payload["d"]
                name = data["requestType"]
                requests.append((name, data.get("requestData")))
                response = {
                    "GetVersion": {"obsVersion": "31.0.3"},
                    "GetSceneItemId": {"sceneItemId": 7},
                }.get(name)
                reply = {"requestType": name, "requestId": data["requestId"],
                         "requestStatus": {"result": True, "code": 100}}
                if response:
                    reply["responseData"] = response
                await ws.send_json({"op": 7, "d": reply})
            return ws

        app = web.Application()
        app.router.add_get("/", server)
        runner = web.AppRunner(app)
        await runner.setup()
        try:
            site = web.TCPSite(runner, "127.0.0.1", 0)
            await site.start()
            client = _DebianObsClient("127.0.0.1", runner.addresses[0][1], "fixture-password")
            try:
                self.assertEqual(await client.connect(), "31.0.3")
                from slbot.connectors.obs import ObsConnector

                connector = ObsConnector(SimpleNamespace())
                connector._client = client
                await connector.set_scene("Demo")
                await connector.set_source_visible("Demo", "Overlay", True)
            finally:
                await client.disconnect()
            self.assertEqual(requests, [
                ("GetVersion", None),
                ("SetCurrentProgramScene", {"sceneName": "Demo"}),
                ("GetSceneItemId", {"sceneName": "Demo", "sourceName": "Overlay"}),
                ("SetSceneItemEnabled", {"sceneName": "Demo", "sceneItemId": 7, "sceneItemEnabled": True}),
            ])
        finally:
            await runner.cleanup()
