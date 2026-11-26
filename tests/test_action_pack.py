import json
import tempfile
import unittest
from pathlib import Path

from slbot.core.action_pack import ActionPack
from slbot.core.config import Action, Config, Trigger


class PackTests(unittest.TestCase):
    def test_roundtrip_remaps_flow_and_disables_imported_triggers(self):
        with tempfile.TemporaryDirectory() as folder:
            config = Config(path=Path(folder) / "config.json",
                settings={"obs": {"password": "secret"}, "note": "private"},
                actions=[Action("main", "Principal", [{"type": "run_action", "action_id": "nested"}]),
                         Action("nested", "Interna", [{"type": "log", "message": "{user}"}]),
                         Action("outside", "No incluir", [{"type": "log", "message": "Fuera"}])],
                triggers=[Trigger("rule", "chat", "main", "Prueba")])
            raw = ActionPack.export_selected(config, "main")
            for private in (b"secret", b"private", b"Fuera"):
                self.assertNotIn(private, raw)
            pack = ActionPack.parse(raw)
            new_id = pack.install(config)
            loaded = Config.load(config.path)
            self.assertEqual(len(loaded.actions), 5)
            self.assertTrue(loaded.triggers[0].enabled)
            self.assertFalse(loaded.triggers[1].enabled)
            self.assertEqual(loaded.triggers[1].action_id, new_id)
            self.assertEqual(loaded.actions[3].steps[0]["action_id"], loaded.actions[4].id)
            self.assertTrue(loaded.actions[3].name.startswith("Principal (importada"))

    def test_export_rejects_local_files_and_import_rejects_unknown_steps_and_cycles(self):
        for step in ({"type": "play_sound", "file": "/home/private.wav"}, {"type": "shell"},
                     {"type": "run_action", "action_id": "loop"}):
            document = {"format": "streamer-linux-bot-actions", "version": 1,
                        "actions": [Action("loop", "No", [step]).to_dict()], "triggers": []}
            with self.assertRaises(ValueError):
                ActionPack.parse(json.dumps(document).encode())

    def test_import_rejects_oversized_or_foreign_data_before_changes(self):
        for value in (b"0" * 262145, b'{"actions": []}', b'{"data": Infinity}', b"[" * 10000):
            with self.assertRaises(ValueError):
                ActionPack.parse(value)
