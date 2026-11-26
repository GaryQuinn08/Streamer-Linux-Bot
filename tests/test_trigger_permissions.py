import unittest

from slbot.connectors.platforms import twitch_events, youtube_events
from slbot.core.config import Trigger
from slbot.core.events import Event


def twitch_cmd(actor, owner="123", badges=None, source=None, text="!demo", label="Admin"):
    _, event = twitch_events("channel.chat.message", {
        "chatter_user_id": actor, "chatter_user_name": label, "broadcaster_user_id": owner,
        "source_broadcaster_user_id": source, "badges": badges or [], "message": {"text": text},
    })
    return event


def youtube_cmd(*, owner=False, moderator=False, channel="U1", snippet_channel="U1"):
    _, event = youtube_events({
        "snippet": {"type": "textMessageEvent", "authorChannelId": snippet_channel,
                    "textMessageDetails": {"messageText": "!demo"}},
        "authorDetails": {"displayName": "Admin", "channelId": channel,
                          "isChatOwner": owner, "isChatModerator": moderator},
    })
    return event


class TriggerPermissionTests(unittest.TestCase):
    def setUp(self):
        self.staff = Trigger.from_dict({"id": "test", "action_id": "a", "event_type": "command",
                                       "chat_permission": "staff"})
        self.owner = Trigger.from_dict({**self.staff.to_dict(), "chat_permission": "owner"})

    def test_twitch_role_only_from_local_channel(self):
        self.assertTrue(self.owner.matches(twitch_cmd("123")))
        moderator = twitch_cmd("456", badges=[{"set_id": "moderator"}])
        self.assertTrue(self.staff.matches(moderator))
        self.assertFalse(self.owner.matches(moderator))
        self.assertFalse(self.staff.matches(twitch_cmd("456", badges=[{"set_id": "moderator"}], source="654")))
        self.assertFalse(self.staff.matches(twitch_cmd("456", label="Moderator")))
        self.assertNotIn("actor_id", moderator.to_dict())
        self.assertNotIn("chat_role", moderator.to_dict())

    def test_youtube_validated_role_and_no_role_on_simulations_or_unknown_sources(self):
        self.assertTrue(self.owner.matches(youtube_cmd(owner=True)))
        self.assertTrue(self.staff.matches(youtube_cmd(moderator=True)))
        self.assertFalse(self.staff.matches(youtube_cmd(moderator="true")))
        self.assertFalse(self.staff.matches(youtube_cmd(owner=True, snippet_channel="U2")))
        event = youtube_cmd(owner=True)
        event.data["simulated"] = True
        self.assertFalse(self.staff.matches(event))
        self.assertFalse(self.staff.matches(Event("kick", "command", actor_id="x", chat_role="owner")))
        self.assertFalse(self.staff.matches(Event("twitch", "command", data={"chat_role": "owner"})))

    def test_legacy_default_and_rejects_bad_configuration_and_nonfinite_gifts(self):
        legacy = Trigger.from_dict({"id": "test", "action_id": "a", "event_type": "command"})
        self.assertTrue(legacy.matches(twitch_cmd("456")))
        self.assertNotIn("chat_permission", legacy.to_dict())
        with self.assertRaises(ValueError):
            Trigger.from_dict({**self.staff.to_dict(), "platform": "kick"})
        gift = Trigger.from_dict({"id": "test", "action_id": "a", "event_type": "gift",
                                  "filters": {"min_value": 10}})
        self.assertFalse(gift.matches(Event("tiktok", "gift", data={"value": "NaN"})))
        self.assertFalse(gift.matches(Event("tiktok", "gift", data={"value": "Infinity"})))
