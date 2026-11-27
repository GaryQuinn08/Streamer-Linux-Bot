import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from slbot.overlay_pack import import_pack, read_pack
from slbot.overlay_manager import list_overlays


class OverlayPackTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.data = Path(self.folder.name)
        self.settings = patch.dict(os.environ, {"SLB_DATA_DIR": str(self.data / "data")})
        self.settings.start()
        self.addCleanup(self.settings.stop)
        self.sample = self.data / "tema.slbpack"
        self.source = {
            "format": "slb-pack", "version": 1, "name": "Estrellas", "description": "Tema de prueba.",
            "components": [
                {"kind": "alert", "design": {"name": "Alerta", "title": "{alert_title}", "enter": "zoom",
                                             "accent": "#ffaa44", "body": "</script><img src=1>","css": "never_here"}},
                {"kind": "camera", "design": {"name": "Marco", "title": "<iframe>"}},
            ],
        }

    def write(self, data):
        self.sample.write_text(json.dumps(data), encoding="utf-8")
        return self.sample

    def test_import_packages_a_dynamic_and_a_static_piece(self):
        overlays = import_pack(self.write(self.source))
        self.assertEqual(len(overlays), 2)
        self.assertTrue(all(info.id in list_overlays() for info in overlays))
        alert, camera = ((o.path / "index.html").read_text() for o in overlays)
        self.assertIn("new WebSocket", alert)
        self.assertIn('"enter": "zoom"', alert)
        self.assertIn(r"\u003c/script\u003e", alert)
        self.assertNotIn("<img src=", alert)
        self.assertNotIn("never_here", alert)
        self.assertNotIn("<script", camera)
        self.assertIn("&lt;iframe&gt;", camera)
        reimport = import_pack(self.sample)
        self.assertEqual(len({o.id for o in overlays + reimport}), 4)

    def test_rejects_bad_format_before_writing_any_component(self):
        self.source["components"].append(self.source["components"][0])
        with self.assertRaisesRegex(ValueError, "duplicada"):
            import_pack(self.write(self.source))
        self.assertFalse(any(info.source == "user" for info in list_overlays().values()))
        self.sample.write_bytes(b" " * 65537)
        with self.assertRaisesRegex(ValueError, "64 KiB"):
            read_pack(self.sample)

    def test_rejects_non_object_design(self):
        self.source["components"][1]["design"] = []
        with self.assertRaisesRegex(ValueError, "ajustes"):
            read_pack(self.write(self.source))
