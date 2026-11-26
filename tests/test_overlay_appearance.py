import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aiohttp import ClientSession

from slbot.core.config import Action, Config
from slbot.overlay_manager import find_overlay, import_overlay, validate_overlay_values
from slbot.overlay_pack import import_pack
from slbot.runtime import Runtime


class EditableOverlaysTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        env = patch.dict(os.environ, {"SLB_DATA_DIR": str(self.root / "data"),
                                     "SLB_CONFIG_DIR": str(self.root / "config")})
        env.start()
        self.addCleanup(env.stop)
        self.runtime = Runtime(config=Config.defaults())
        await self.runtime.overlays.start(0)
        self.addAsyncCleanup(self.runtime.overlays.stop)
        self.session = ClientSession()
        self.addAsyncCleanup(self.session.close)

    def old_pack(self):
        original = self.root / "coleccion.slbpack"
        original.write_text(json.dumps({
            "format": "slb-pack", "version": 1, "name": "Archivo antiguo",
            "components": [
                {"kind": "alert", "design": {"title": "{user} antes", "duration": 15, "enter": "pop"}},
                {"kind": "starting", "design": {"title": "Bienvenidos & bienvenidas", "accent": "#cc77aa",
                    "background": "#173b47", "textColor": "#dddddd", "positionX": 80, "positionY": 40,
                    "width": 65, "opacity": 65, "padding": 22}},
            ]
        }), encoding="utf-8")
        return original, import_pack(original)

    async def get(self, overlay, status=200, index=""):
        port = self.runtime.overlays.port
        async with self.session.get(f"http://127.0.0.1:{port}/overlay/{overlay.id}/{index}") as response:
            self.assertEqual(response.status, status)
            return await response.text()

    async def test_edits_older_imported_pack_without_reimport_and_resets(self):
        _, (alert, scene) = self.old_pack()
        for old in (alert, scene):
            (old.path / "slb-appearance.json").unlink()  # Desktop beta 11 wrote no sidecar.
        scene = find_overlay(scene.id)
        defaults = {spec["key"]: spec["default"] for spec in scene.params}
        self.assertEqual(defaults["title"], "Bienvenidos & bienvenidas")
        for key, expected in {"background": "#173b47", "positionX": 80, "positionY": 40,
                              "width": 65, "opacity": 65, "padding": 22, "accent": "#cc77aa"}.items():
            self.assertEqual(defaults[key], expected, key)
        original = await self.get(scene)
        await self.runtime.save_overlay_preset(scene.id, {"title": "<nuevo> & listo", "background": "#123456",
                                                          "size": "38", "width": "70", "opacity": "90"})
        result = await self.get(scene, index="index.html")
        self.assertIn("&lt;nuevo&gt; &amp; listo", result)
        self.assertIn("--fill:#123456e6", result)
        self.assertIn("--size:38px", result)
        self.assertIn("--width:70%", result)
        self.assertEqual((scene.path / "index.html").read_text(), original)
        await self.runtime.save_overlay_preset(alert.id, {"title": "{user}: ¡Hola!", "duration": "9",
                                                         "enter": "slide-left", "enterMs": "170"})
        edited_alert = await self.get(alert)
        self.assertIn('"duration": 9', edited_alert)
        self.assertIn('"enter": "slide-left"', edited_alert)
        self.assertIn("--in-time:170ms", edited_alert)
        self.assertIn(r'{user}: \u00a1Hola!', edited_alert)
        await self.runtime.save_overlay_preset(scene.id, {})
        self.assertEqual(await self.get(scene), original)

    async def test_web_export_updates_without_replacing_custom_markup(self):
        export = self.root / "estudio.html"
        export.write_text(
            '<!doctype html><html><style>:root{--accent:#118844}.custom{font-weight:bold}</style><body>'
            '<template id="slb-template"><article class="custom">{title}</article></template>'
            '<script id="slb-design-v1" type="application/json">{"mode":"chat","title":"{user}",'
            '"name":"export","body":"{text}","duration":3}</script>'
            '<script>(function(config){ window.fixture=config; })({"title":"{user}","mode":"chat"});'
            '</script></body></html>', encoding="utf-8")
        item = import_overlay(export)
        self.assertTrue(item.appearance.editor_export)
        invalid = {"accent": "red; } body{display:none}"}
        with self.assertRaises(ValueError):
            validate_overlay_values(item, invalid)
        await self.runtime.save_overlay_preset(item.id, {"title": "</script><script>bad()", "accent": "#ffaacc"})
        altered = await self.get(item)
        self.assertIn("--accent:#ffaacc", altered)
        self.assertIn(".custom{font-weight:bold}", altered)
        self.assertIn('<article class="custom">{title}</article>', altered)
        self.assertIn(r"\u003c/script\u003e\u003cscript\u003ebad()", altered)
        self.assertNotIn("<script>bad()", altered)

    async def test_unrecognized_html_is_preserved_and_deletable_but_builtins_are_not(self):
        original = self.root / "externo.html"
        original.write_text("<h1>Externo sin parámetros</h1>", encoding="utf-8")
        item = import_overlay(original)
        self.assertIsNone(item.appearance)
        self.assertFalse(item.params)
        self.assertEqual(await self.get(item), original.read_text())
        with self.assertRaises(ValueError):
            await self.runtime.delete_user_overlay("gift-alert", 0)
        await self.runtime.delete_user_overlay(item.id, 0)
        self.assertEqual(original.read_text(), "<h1>Externo sin parámetros</h1>")
        await self.get(item, 404)

    async def test_delete_overlay_clears_only_its_presets_and_references_and_persists(self):
        original, (alert, keep) = self.old_pack()
        self.runtime.config.actions.append(Action("custom", steps=[
            {"type": "overlay_alert", "overlay": alert.id}, {"type": "log", "message": "Conservar"},
            {"type": "overlay_alert", "overlay": "gift-alert"},
        ]))
        await self.runtime.save_overlay_preset(alert.id, {"textColor": "#ff0000"})
        await self.runtime.save_overlay_preset(keep.id, {"textColor": "#ff00ff"})
        with self.assertRaisesRegex(ValueError, "Confirma de nuevo"):
            await self.runtime.delete_user_overlay(alert.id, 0)
        with patch.object(Config, "save", side_effect=OSError("Sin espacio")):
            with self.assertRaises(OSError):
                await self.runtime.delete_user_overlay(alert.id, 1)
        await self.get(alert)
        self.assertEqual(self.runtime.overlay_use_count(alert.id), 1)
        await self.runtime.delete_user_overlay(alert.id, 1)
        await self.get(alert, 404)
        await self.get(keep)
        self.assertTrue(original.is_file())
        saved = Config.load()
        self.assertEqual(saved.settings["overlay_presets"], {keep.id: {"textColor": "#ff00ff"}})
        steps = next(action.steps for action in saved.actions if action.id == "custom")
        self.assertEqual([step["type"] for step in steps], ["log", "overlay_alert"])
        self.assertEqual(steps[-1]["overlay"], "gift-alert")


class EditableOverlaysQtTest(unittest.TestCase):
    def test_old_pack_displays_native_fields_and_can_be_edited_and_deleted(self):
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QApplication, QLineEdit, QMessageBox, QSpinBox
        from slbot.ui.main_window import LogBridge, OverlaysTab

        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {
            "SLB_DATA_DIR": temp, "SLB_CONFIG_DIR": temp,
        }):
            archive = Path(temp) / "antiguo.slbpack"
            archive.write_text(json.dumps({"format": "slb-pack", "version": 1, "name": "Tema",
                "components": [{"kind": "banner", "design": {"title": "Antes", "size": 35}}]}))
            overlay = import_pack(archive)[0]
            (overlay.path / "slb-appearance.json").unlink()
            rt = Runtime(config=Config.defaults(), port=0)
            rt.start()
            self.addCleanup(rt.stop)
            bridge = LogBridge()
            tab = OverlaysTab(rt, bridge)
            self.addCleanup(tab.close)
            self.assertFalse(tab.delete_btn.isEnabled())
            tab.refresh(select_id=overlay.id)
            self.assertTrue(tab.delete_btn.isEnabled())
            self.assertFalse(tab.preview_btn.isEnabled())
            url = tab.url.text()
            field = tab.form_host.findChildren(QLineEdit)[0]
            self.assertEqual(field.text(), "Antes")
            field.setText("Ahora desde Linux")
            size = next(widget for widget in tab.form_host.findChildren(QSpinBox) if widget.value() == 35)
            size.setValue(44)
            tab.save_btn.click()

            def wait_for(predicate):
                for _ in range(200):
                    if predicate():
                        return
                    app.processEvents()
                    QTest.qWait(10)
                self.fail("La operación de la interfaz no terminó.")

            wait_for(lambda: tab.status.text().startswith("Apariencia guardada"))
            self.assertEqual(tab.url.text(), url)
            self.assertEqual(Config.load().settings["overlay_presets"][overlay.id],
                             {"title": "Ahora desde Linux", "size": "44"})

            def inspect_dialog(box):
                self.assertEqual(box.defaultButton(), box.button(QMessageBox.No))
                self.assertIn("La URL dejará de funcionar", box.informativeText())
                return QMessageBox.Yes

            with patch.object(QMessageBox, "exec", inspect_dialog):
                tab.delete_btn.click()
            wait_for(lambda: tab.status.text().startswith("Overlay eliminado"))
            self.assertIsNone(find_overlay(overlay.id))
            self.assertTrue(archive.is_file())


if __name__ == "__main__":
    unittest.main()
