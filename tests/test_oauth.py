import asyncio
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from unittest.mock import AsyncMock, patch

import aiohttp

from slbot.connectors import oauth
from slbot.core.config import Config
from slbot.runtime import Runtime


class OAuthTests(unittest.IsolatedAsyncioTestCase):
    async def check_provider(self, client, host):
        posted = {}

        async def browser(url):
            posted["auth"] = url
            parsed = urlsplit(url)
            params = parse_qs(parsed.query)
            redirect, state = params["redirect_uri"][0], params["state"][0]
            async with aiohttp.ClientSession() as session:
                async with session.get(redirect, params={"state": "wrong", "code": "wrong"}) as reply:
                    self.assertEqual(reply.status, 400)
                async with session.get(redirect, params={"state": state, "code": "no"},
                                       headers={"Host": "outside.invalid"}) as reply:
                    self.assertEqual(reply.status, 403)
                async with session.get(redirect, params={"state": state, "code": "fixture-code"}) as reply:
                    self.assertEqual(reply.status, 200)
                    self.assertEqual(reply.headers.get("Cache-Control"), "no-store")
                    self.assertNotIn("fixture-code", await reply.text())
            return True

        exchange = AsyncMock(return_value="fixture-token")
        with patch.object(oauth, "_exchange", exchange):
            token = await oauth.sign_in(client, browser)
        self.assertEqual(token, "fixture-token")
        auth = urlsplit(posted["auth"])
        self.assertEqual(auth.hostname, host)
        params = parse_qs(auth.query)
        endpoint, args, _ = exchange.await_args.args
        self.assertEqual(args["code"], "fixture-code")
        self.assertEqual(params["code_challenge_method"], ["S256"])
        self.assertEqual(oauth._challenge(args["code_verifier"]), params["code_challenge"][0])
        self.assertEqual(args["redirect_uri"], params["redirect_uri"][0])
        self.assertNotIn("client_secret", params)
        self.assertEqual(args.get("client_secret", ""), client.secret)
        expected_endpoint = {"twitch": "id.twitch.tv", "youtube": "oauth2.googleapis.com",
                             "spotify": "accounts.spotify.com"}[client.platform]
        self.assertEqual(urlsplit(endpoint).hostname, expected_endpoint)

    async def test_twitch_browser_callback(self):
        with patch.object(oauth, "TWITCH_PORT", 0):
            await self.check_provider(oauth.Client("twitch", "public12345"), "id.twitch.tv")

    async def test_google_browser_callback(self):
        await self.check_provider(oauth.Client("youtube", "fixture.apps.googleusercontent.com", "client-fixture"),
                                  "accounts.google.com")

    async def test_spotify_pkce_uses_only_playback_scope(self):
        with patch.object(oauth, "SPOTIFY_PORT", 0):
            await self.check_provider(oauth.Client("spotify", "spotifyfixture124"), "accounts.spotify.com")
        self.assertEqual(oauth.SPOTIFY_SCOPE, "user-modify-playback-state")

    async def test_provisioning_resolves_private_google_config_relative_to_profile(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {}, clear=True):
            profile = Path(tmp)
            self.assertEqual(oauth.deployment_setting("twitch", profile), "")
            (profile / "oauth-clients.json").write_text(json.dumps({
               "twitch_client_id": "project123", "google_client_file": "private-gcp.json",
               "spotify_client_id": "spotify123"}))
            self.assertEqual(oauth.deployment_setting("youtube", profile), str(profile / "private-gcp.json"))
            self.assertEqual(oauth.deployment_setting("spotify", profile), "spotify123")
            with patch.dict(os.environ, {"SLB_TWITCH_CLIENT_ID": "environment123"}):
                self.assertEqual(oauth.deployment_setting("twitch", profile), "environment123")

    async def test_failed_browser_does_not_exchange(self):
        exchange = AsyncMock()
        with patch.object(oauth, "_exchange", exchange):
            with self.assertRaisesRegex(oauth.SignInError, "No se pudo abrir"):
                await oauth.sign_in(oauth.Client("youtube", "fixture"), AsyncMock(return_value=False))
        exchange.assert_not_awaited()

    async def test_cancellation_closes_loopback(self):
        shown = asyncio.get_running_loop().create_future()

        async def browser(url):
            shown.set_result(parse_qs(urlsplit(url).query)["redirect_uri"][0])
            return True

        run = asyncio.create_task(oauth.sign_in(oauth.Client("youtube", "fixture"), browser))
        redirect = await asyncio.wait_for(shown, 3)
        run.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await run
        async with aiohttp.ClientSession() as session:
            with self.assertRaises(aiohttp.ClientConnectorError):
                await session.get(redirect)

    async def test_google_configuration_trusts_no_endpoints_from_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "client.json"
            mock = {"client_id": "demo.apps.googleusercontent.com", "client_secret": "fixture",
                    "auth_uri": "https://outside.invalid", "token_uri": "https://outside.invalid"}
            path.write_text(json.dumps({"web": mock}))
            with self.assertRaises(oauth.SignInError):
                await oauth.browser_client("youtube", str(path))
            path.write_text(json.dumps({"installed": mock}))
            item = await oauth.browser_client("youtube", str(path))
            self.assertEqual(item.client_id, mock["client_id"])
            self.assertNotIn("fixture", repr(item))

    async def test_receivers_get_browser_token_and_forget_on_stop(self):
        rt = Runtime(config=Config.defaults())
        connector = rt.connectors["twitch"]
        delivered = asyncio.get_running_loop().create_future()

        async def receive(auth):
            delivered.set_result(auth)
            await asyncio.Future()

        with patch("slbot.connectors.platforms.sign_in", new=AsyncMock(return_value="fixture-token")):
            with patch.object(connector, "receive", side_effect=receive):
                await connector.start(browser=AsyncMock(), setting="twitchpublic123")
                self.assertEqual(await asyncio.wait_for(delivered, 3), ("fixture-token", "twitchpublic123"))
                self.assertTrue(connector.busy)
                await connector.stop()
                self.assertFalse(connector.busy)


class SocialUiTests(unittest.TestCase):
    def test_button_uses_system_default_browser(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtCore import QSettings, Qt
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QApplication, QPushButton
        from slbot.ui.platform_login import PlatformLoginPanel

        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "client_settings.ini")
            settings = QSettings(path, QSettings.Format.IniFormat)
            cfg = Config.defaults()
            cfg.path = Path(tmp) / "config.json"
            (cfg.path.parent / "oauth-clients.json").write_text(json.dumps(
                {"twitch_client_id": "twitchpublic123"}))
            rt = Runtime(config=cfg, port=0)
            rt.start()
            panel = PlatformLoginPanel(rt, settings)
            panel.show()
            try:
                with patch.object(oauth, "TWITCH_PORT", 0):
                    with patch("slbot.ui.platform_login.QDesktopServices.openUrl", return_value=True) as launch:
                        button = panel.findChild(QPushButton, "signin-twitch")
                        self.assertFalse(panel.findChild(QPushButton, "signin-youtube").isEnabled())
                        self.assertTrue(button.isEnabled())
                        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
                        deadline = time.monotonic() + 3
                        while not launch.called and time.monotonic() < deadline:
                            app.processEvents()
                            time.sleep(.015)
                        self.assertEqual(launch.call_count, 1)
                        self.assertEqual(launch.call_args.args[0].host(), "id.twitch.tv")
                rt.submit(rt.connectors["twitch"].stop()).result(4)
            finally:
                panel.close()
                rt.stop()
