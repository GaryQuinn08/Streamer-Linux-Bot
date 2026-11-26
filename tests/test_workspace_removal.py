"""Deletion via the desktop workbench and on-disk profile integrity."""
import asyncio
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from slbot.audio import MusicQueue
from slbot.core.config import Config
from slbot.core.editing import update_rules
from slbot.core.timers import read_timers
from slbot.runtime import Runtime


def timer(ident, action_id="alert-gift"):
    return {"id": ident, "name": ident, "action_id": action_id, "seconds": 60, "enabled": True}


class RemovalTests(unittest.IsolatedAsyncioTestCase):
    async def test_cascade_requires_exact_dependencies_and_atomic_save(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "config.json"
            cfg = Config.load(path)
            cfg.settings["timers"] = [timer("gift-clock"), timer("follow-clock", "alert-follow"), {"other": "kept"}]
            cfg.save()
            unsafe = {"id": "alert-gift", "confirmed_dependencies": {"triggers": ["tiktok-gift"], "timers": []}}
            with self.assertRaisesRegex(ValueError, "cambiaron"):
                update_rules(cfg, "action", unsafe, delete=True)
            self.assertIsNotNone(Config.load(path).action_by_id("alert-gift"))
            approved = {**unsafe, "confirmed_dependencies": {"triggers": ["tiktok-gift"], "timers": ["gift-clock"]}}
            with patch.object(Config, "save", side_effect=OSError("disk error")), self.assertRaises(OSError):
                update_rules(cfg, "action", approved, delete=True)
            self.assertIsNotNone(cfg.action_by_id("alert-gift"))
            self.assertEqual([t.id for t in read_timers(cfg.settings)], ["gift-clock", "follow-clock"])
            update_rules(cfg, "action", approved, delete=True)
            reopened = Config.load(path)
            self.assertIsNone(reopened.action_by_id("alert-gift"))
            self.assertEqual([t.id for t in reopened.triggers], ["any-follow", "any-donation"])
            self.assertEqual(reopened.settings["timers"], [timer("follow-clock", "alert-follow"), {"other": "kept"}])

    async def test_pending_queue_removes_only_selected_copy_preserving_active_and_other_tracks(self):
        started, release = asyncio.Event(), asyncio.Event()
        played = []

        async def player(*args):
            played.append(Path(args[-1]).name)
            started.set()
            await release.wait()
            return 0

        with tempfile.TemporaryDirectory() as folder, patch("slbot.audio.shutil.which", return_value="mpv"), \
                patch("slbot.audio.run_process", side_effect=player):
            track = Path(folder) / "same.wav"
            track.touch()
            queue = MusicQueue(SimpleNamespace(log=lambda _msg: None, spawn=asyncio.create_task))
            for _ in range(3):
                queue.enqueue(str(track))
            active, removed, kept = [ident for ident, _ in queue.pending()]
            await asyncio.wait_for(started.wait(), 2)
            with self.assertRaisesRegex(ValueError, "ya no está pendiente"):
                await queue.remove(active)
            await queue.remove(removed)
            self.assertEqual(queue.pending(), ((kept, "same.wav"),))
            self.assertEqual(queue.current, "same.wav")
            release.set()
            await asyncio.wait_for(queue.items.join(), 2)
            self.assertEqual(played, ["same.wav", "same.wav"])
            self.assertTrue(track.exists())


class WorkbenchRemovalTests(unittest.TestCase):
    def setUp(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        try:
            from PySide6.QtCore import QCoreApplication, QEvent
            from PySide6.QtWidgets import QApplication
            from slbot.ui.main_window import LogBridge, MainWindow
        except ImportError:
            self.skipTest("Qt no instalado")
        self.app = QApplication.instance() or QApplication([])
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        env = patch.dict(os.environ, {"SLB_DATA_DIR": folder.name})
        env.start()
        self.addCleanup(env.stop)
        self.path = Path(folder.name) / "config.json"
        self.rt = Runtime(config=Config.load(self.path), port=0)
        self.rt.start()
        self.addCleanup(self.rt.stop)
        self.win = MainWindow(self.rt, LogBridge())
        self.win.show()
        def dispose():
            self.win.close()
            self.win.deleteLater()
            QCoreApplication.sendPostedEvents(self.win, QEvent.Type.DeferredDelete)
        self.addCleanup(dispose)

    def wait_for(self, predicate):
        from PySide6.QtTest import QTest
        for _ in range(200):
            if predicate():
                return
            QTest.qWait(10)
        self.fail("La operación de la interfaz no terminó.")

    def test_action_cancellation_and_last_step_removal_are_persistent(self):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        self.win.select_page("actions")
        workbench = self.win.action_page
        workbench.action_table.selectRow(1)
        self.assertEqual(workbench.action.id, "alert-follow")
        with patch("slbot.ui.rule_editor.confirm_delete", return_value=False) as confirmation:
            workbench.action_tools[2].click()
            self.assertIn("Nuevo seguidor", confirmation.call_args.args[2])
        self.assertIsNotNone(Config.load(self.path).action_by_id("alert-follow"))

        self.win.activateWindow()
        workbench.step_table.setFocus()
        QTest.qWait(30)
        workbench.step_table.selectRow(0)
        with patch("slbot.ui.rule_editor.confirm_delete", return_value=True) as confirmation:
            QTest.keyClick(workbench.step_table, Qt.Key.Key_Delete)
            self.wait_for(lambda: workbench.step_table.rowCount() == 0)
            self.assertIn("quedará vacía", confirmation.call_args.args[2])
        self.assertEqual(Config.load(self.path).action_by_id("alert-follow").steps, [])

    def test_delete_action_with_trigger_and_timer_refreshes_all_pages(self):
        self.rt.submit(self.rt.edit_timer(timer("Reloj"))).result(timeout=2)
        self.win.timer_page.refresh()
        table = self.win.action_page
        self.assertEqual(table.action.id, "alert-gift")
        with patch("slbot.ui.rule_editor.confirm_delete", return_value=True) as confirmation:
            table.action_tools[2].click()
            self.wait_for(lambda: table.action_table.rowCount() == 2)
            self.assertIn("Regalo de TikTok", confirmation.call_args.args[2])
            self.assertIn("Reloj", confirmation.call_args.args[2])
        self.assertEqual(self.win.timer_page.table.rowCount(), 0)
        self.assertNotIn("tiktok-gift", [t.id for t in Config.load(self.path).triggers])
        self.assertEqual(self.win.quick_page.save_button.text(), "Crear regla de regalos")

    def test_individual_quick_trigger_and_timer_delete(self):
        self.rt.submit(self.rt.edit_timer(timer("Borrar reloj"))).result(timeout=2)
        self.win.select_page("timers")
        page = self.win.timer_page
        page.refresh()
        with patch("slbot.ui.timer_panel.confirm_delete", return_value=True):
            page.delete.click()
            self.wait_for(lambda: page.table.rowCount() == 0)
        self.assertFalse(read_timers(Config.load(self.path).settings))

        self.win.select_page("gifts")
        quick = self.win.quick_page
        quick.table.selectRow(0)
        with patch("slbot.ui.deletion.confirm_delete", return_value=True):
            quick.delete_button.click()
            self.wait_for(lambda: quick.table.rowCount() == 2)
        cfg = Config.load(self.path)
        self.assertNotIn("tiktok-gift", [t.id for t in cfg.triggers])
        self.assertIsNotNone(cfg.action_by_id("alert-gift"))

    def test_music_removal_sends_only_the_selected_item(self):
        self.win.select_page("music")
        page = self.win.music_page
        with patch.object(self.rt.music, "pending", return_value=((11, "Pista"), (12, "Pista"))), \
                patch.object(self.rt.music, "remove", new_callable=AsyncMock) as remove, \
                patch("slbot.ui.music_panel.confirm_delete", return_value=True):
            page.refresh()
            page.pending_list.setCurrentRow(1)
            page.remove_button.click()
            self.wait_for(lambda: page.result.text() == "Audio quitado de la cola.")
            remove.assert_awaited_once_with(12)

    def test_confirmation_defaults_to_no_and_treats_titles_as_text(self):
        from PySide6.QtCore import Qt, QTimer
        from PySide6.QtWidgets import QApplication, QMessageBox
        from slbot.ui.deletion import confirm_delete
        observed = []
        def close():
            box = QApplication.activeModalWidget()
            if isinstance(box, QMessageBox):
                observed.append((box.defaultButton() == box.button(QMessageBox.StandardButton.No), box.textFormat(), box.text()))
                box.button(QMessageBox.StandardButton.No).click()
        QTimer.singleShot(0, close)
        self.assertFalse(confirm_delete(self.win, "Eliminar", "<b>texto literal</b>"))
        self.assertEqual(observed[0][1:], (Qt.TextFormat.PlainText, "<b>texto literal</b>"))
        self.assertTrue(observed[0][0])
