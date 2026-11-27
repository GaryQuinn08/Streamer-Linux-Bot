import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from slbot.connectors.oauth import SignInError, TWITCH_WRITE_SCOPE
from slbot.connectors.platforms import TwitchConnector


def response(status=200, body=None):
    context = MagicMock()
    reply = context.__aenter__.return_value
    reply.status = status
    reply.json = AsyncMock(return_value=body)
    return context


class TwitchChatTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.connector = TwitchConnector(MagicMock())
        self.session = MagicMock()
        self.headers = {"Authorization": "Bearer fixture", "Client-Id": "fixture-id"}

    async def test_desktop_sends_only_when_requested_and_granted(self):
        async def event_session(*_):
            self.connector.status = "conectado (EventSub)"
            self.assertEqual(self.connector.can_send, permitted and requested)
            if permitted and requested:
                await self.connector.send_chat(" hola ")
        self.session.post.return_value = response(body={"data": [{"is_sent": True}]})
        for permitted, requested in ((True, False), (False, True), (True, True)):
            with patch("slbot.connectors.platforms.aiohttp.ClientSession") as client, \
                 patch("slbot.connectors.platforms.twitch_session_identity", new_callable=AsyncMock) as identity, \
                 patch.object(self.connector, "_events", side_effect=event_session):
                client.return_value.__aenter__.return_value = self.session
                identity.return_value = ("123", (TWITCH_WRITE_SCOPE,) if permitted else ())
                await self.connector.receive(("fixture", "fixture-id"), twitch_write=requested)
            self.assertFalse(self.connector.can_send)
        self.session.post.assert_called_once_with(
            "https://api.twitch.tv/helix/chat/messages", headers=self.headers, allow_redirects=False,
            json={"broadcaster_id": "123", "sender_id": "123", "message": "hola"},
        )

    async def test_invalid_and_unauthorized_messages_do_not_make_a_request(self):
        for value in ("   ", "x" * 501, "dos\nlíneas", "nul\x00"):
            with self.assertRaisesRegex(SignInError, "500"):
                await self.connector.send_chat(value)
        with self.assertRaisesRegex(SignInError, "Conecta Twitch"):
            await self.connector.send_chat("hola")
        self.session.post.assert_not_called()

    async def test_honors_twitch_rejection_and_disables_on_invalid_token(self):
        self.connector.status = "conectado (EventSub)"
        self.connector._writer = self.session, self.headers, "123"
        self.session.post.return_value = response(body={
            "data": [{"is_sent": False, "drop_reason": {"code": "automod_held", "message": "<b>unsafe</b>"}}],
        })
        with self.assertRaisesRegex(SignInError, "AutoMod"):
            await self.connector.send_chat("hola")
        self.session.post.return_value = response(status=401)
        with self.assertRaisesRegex(SignInError, "vuelve a autorizar"):
            await self.connector.send_chat("hola")
        self.assertFalse(self.connector.can_send)
        self.assertEqual(self.session.post.call_count, 2)
