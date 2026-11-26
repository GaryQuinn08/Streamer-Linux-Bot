import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from slbot.core.config import Config
from slbot.overlay_manager import import_overlay
from slbot.overlay_pack import LABELS, import_pack
from slbot.runtime import Runtime


class NativePreviewTests(unittest.TestCase):
    def setUp(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        from slbot.ui.main_window import LogBridge, OverlaysTab

        self.app = QApplication.instance() or QApplication([])
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        env = patch.dict(os.environ, {"SLB_CONFIG_DIR": tmp.name, "SLB_DATA_DIR": tmp.name})
        env.start()
        self.addCleanup(env.stop)
        source = self.root / "tema.slbpack"
        source.write_text(json.dumps({"format": "slb-pack", "version": 1, "name": "Vista local",
            "components": [{"kind": kind, "design": {"name": kind,
                "accent": "#ee55cc", "duration": 1, "enter": "slide-left", "exit": "fade",
                "enterMs": 350, "exitMs": 300}} for kind in LABELS]}))
        self.pieces = dict(zip(LABELS, import_pack(source)))
        self.runtime = Runtime(config=Config.defaults())
        self.bridge = LogBridge()
        self.tab = OverlaysTab(self.runtime, self.bridge)
        self.tab.resize(1050, 820)
        self.tab.show()
        self.addCleanup(self.tab.close)
        self.app.processEvents()

    def choose(self, kind):
        self.tab.refresh(select_id=self.pieces[kind].id)
        self.app.processEvents()
        return self.tab.preview

    def test_every_piece_paints_even_with_port_disabled(self):
        self.assertIsNone(self.runtime.port)
        snapshots = []
        for kind in LABELS:
            view = self.choose(kind)
            self.assertEqual(view.model.kind, kind)
            self.assertFalse(view.grab().isNull())
            self.assertEqual(self.tab.play_preview.isVisible(), kind in {"alert", "events", "chat"})
            self.assertFalse(self.tab.preview_btn.isEnabled())
            snapshots.append(view.grab().toImage())
        self.assertNotEqual(snapshots[0], snapshots[1])
        self.assertNotEqual(snapshots[4], snapshots[5])  # transparent camera vs full scene

    def test_dirty_settings_repaint_and_playback_is_only_local(self):
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QLineEdit

        view = self.choose("alert")
        original = view.grab().toImage()
        self.tab.form_host.findChildren(QLineEdit)[0].setText("Vista sin guardar")
        self.assertEqual(view.model.settings["title"], "Vista sin guardar")
        self.assertNotEqual(view.grab().toImage(), original)
        self.assertNotIn("overlay_presets", self.runtime.config.settings)
        with patch.object(self.runtime, "submit") as submit:
            self.tab.play_preview.click()
            self.assertEqual(view.phase, "enter")
            first_frame = view.grab().toImage()
            QTest.qWait(120)
            self.assertNotEqual(view.grab().toImage(), first_frame)
            self.assertTrue(self.tab.play_exit.isVisible())
            self.tab.play_exit.click()
            self.assertEqual(view.phase, "exit")
            for _ in range(80):
                if view.phase == "hidden":
                    break
                QTest.qWait(10)
            self.assertEqual(view.phase, "hidden")
            submit.assert_not_called()
        self.choose("banner")
        self.assertEqual(view.phase, "idle")
        self.assertFalse(self.tab.play_preview.isVisible())

    def test_pop_matches_browser_scale_milestones_and_long_form_scrolls(self):
        from PySide6.QtWidgets import QLineEdit, QScrollArea
        from slbot.ui.overlay_preview import motion
        self.choose("alert")
        scroll = self.tab.findChild(QScrollArea)
        self.assertGreater(scroll.verticalScrollBar().maximum(), 0)
        field = self.tab.form_host.findChildren(QLineEdit)[0]
        self.assertGreaterEqual(field.height(), field.minimumSizeHint().height())
        self.assertAlmostEqual(motion("pop", 0, False)[3], .84)
        self.assertAlmostEqual(motion("pop", .68, False)[3], 1.06)
        self.assertAlmostEqual(motion("pop", .68, True)[3], 1.05)
        self.assertAlmostEqual(motion("pop", 1, True)[3], .88)
        self.assertLess(motion("slide-left", 1, True)[1], 0)

    def test_html_without_metadata_remains_external(self):
        source = self.root / "libre.html"
        source.write_text("<script>throw Error('do not run')</script>", encoding="utf-8")
        item = import_overlay(source)
        self.tab.refresh(select_id=item.id)
        self.assertIsNone(self.tab.preview.model)
        self.assertIn("diseño externo", self.tab.preview_hint.text())
        self.assertFalse(self.tab.play_preview.isVisible())


if __name__ == "__main__":
    unittest.main()
