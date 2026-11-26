import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from slbot.core.config import Config
from slbot.runtime import Runtime


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        try:
            from PySide6.QtWidgets import QApplication
        except ImportError:
            self.skipTest("Qt no instalado")
        self.app = QApplication.instance() or QApplication([])
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        data = patch.dict(os.environ, {"SLB_DATA_DIR": self.tmp.name})
        data.start()
        self.addCleanup(data.stop)
        self.path = Path(self.tmp.name) / "config.json"
        self.rt = Runtime(config=Config.load(self.path), port=0)
        self.rt.start()
        self.addCleanup(self.rt.stop)

    def _wait_for(self, predicate):
        from PySide6.QtTest import QTest
        for _ in range(200):
            if predicate():
                return
            QTest.qWait(10)
        self.fail("La operación de la interfaz no terminó.")

    def test_action_selection_and_search_keep_details_in_scope(self):
        from slbot.ui.main_window import LogBridge
        from slbot.ui.rule_editor import ActionWorkspace

        bridge = LogBridge()
        view = ActionWorkspace(self.rt, bridge.rules_changed)
        self.addCleanup(view.close)
        self.assertEqual(view.action_table.rowCount(), 3)
        self.assertEqual(view.action.id, "alert-gift")
        self.assertEqual(view.trigger_table.rowCount(), 1)
        self.assertEqual(view.trigger_table.item(0, 2).text(), "gift")
        view.action_table.selectRow(1)
        self.assertEqual(view.trigger_table.item(0, 2).text(), "follow")
        view.filter.setText("DONACIÓN")
        self.assertEqual(view.action_table.rowCount(), 1)
        self.assertEqual(view.trigger_table.item(0, 2).text(), "donation")
        view.filter.setText("no existe")
        self.assertEqual(view.trigger_table.rowCount(), 0)
        self.assertEqual(view.step_table.rowCount(), 0)
        self.assertFalse(view.trigger_tools[0].isEnabled())

    def test_reordering_and_adding_a_scoped_trigger_persist(self):
        from slbot.ui.main_window import LogBridge
        from slbot.ui.rule_editor import ActionWorkspace

        bridge = LogBridge()
        view = ActionWorkspace(self.rt, bridge.rules_changed)
        self.addCleanup(view.close)
        view.step_table.selectRow(0)
        view.step_tools[4].click()
        self._wait_for(lambda: view.isEnabled() and view.notice.text() == "Cambios guardados.")
        action = Config.load(self.path).action_by_id("alert-gift")
        self.assertEqual([step["type"] for step in action.steps], ["log", "overlay_alert"])
        self.assertEqual(view.step_table.currentRow(), 1)

        class FakeTriggerDialog:
            def __init__(self, _owner, data, actions, *, fixed_action):
                if not fixed_action or data["action_id"] != actions[0].id:
                    raise AssertionError("El nuevo disparador no quedó ligado a la acción seleccionada.")
                self.result_data = {**data, "name": "Mi prueba", "event_type": "chat", "platform": "tiktok"}

            def exec(self):
                return True

        with patch("slbot.ui.rule_editor.TriggerForm", FakeTriggerDialog):
            view.trigger_tools[0].click()
        self._wait_for(lambda: view.isEnabled() and view.trigger_table.rowCount() == 2)
        created = next(t for t in Config.load(self.path).triggers if t.name == "Mi prueba")
        self.assertEqual(created.action_id, "alert-gift")

    def test_navigation_and_tiktok_direct_are_the_defaults(self):
        from PySide6.QtWidgets import QPushButton
        from slbot.ui.main_window import LogBridge, MainWindow

        window = MainWindow(self.rt, LogBridge())
        self.addCleanup(window.close)
        self.assertIs(window.pages.currentWidget(), window.dashboard_page)
        window.findChild(QPushButton, "navigate-connections").click()
        self.assertIs(window.pages.currentWidget(), window.connections_page)
        view = window.connections_page
        self.assertEqual(view.tiktok_mode.currentData(), "directo")
        self.assertTrue(view.tiktok_channel.isEnabled())
        self.assertIn("No necesitas", view.tiktok_hint.text())
        view.tiktok_mode.setCurrentIndex(1)
        self.assertFalse(view.tiktok_channel.isEnabled())
        self.assertIn("alternativa", view.tiktok_hint.text())

    def test_chat_filter_and_history_navigation(self):
        from PySide6.QtWidgets import QPushButton
        from slbot.connectors.simulator import sample_event
        from slbot.core.events import Event
        from slbot.ui.main_window import LogBridge, MainWindow

        window = MainWindow(self.rt, LogBridge())
        self.addCleanup(window.close)
        window.findChild(QPushButton, "navigate-chat").click()
        self.assertIs(window.pages.currentWidget(), window.chat_page)
        async def send_samples():
            await self.rt.bus.publish(sample_event("chat"))
            await self.rt.bus.publish(Event("tiktok", "chat", "A", {"text": "<b>hola</b>"}))
            await self.rt.bus.publish(sample_event("gift"))
        self.rt.submit(send_samples()).result(timeout=2)
        chat = window.chat_page
        chat.refresh()
        self.assertEqual(chat.table.rowCount(), 2)
        self.assertIn("prueba", chat.table.item(1, 1).text())
        chat.platform.setCurrentIndex(chat.platform.findData("tiktok"))
        self.assertEqual(chat.table.rowCount(), 1)
        self.assertEqual(chat.table.item(0, 3).text(), "<b>hola</b>")
        self.assertEqual(chat.table.item(0, 3).toolTip(), "")
        window.findChild(QPushButton, "navigate-history").click()
        self.assertIs(window.pages.currentWidget(), window.history_page)
        window.history_page.refresh()
        self.assertEqual(window.history_page.table.rowCount(), 1)
        self.assertIn(window.history_page.table.item(0, 4).text(), ("Completada", "En curso"))

    def test_action_workspace_and_history_pause_and_cancel(self):
        from PySide6.QtWidgets import QPushButton
        from slbot.core.config import Action
        from slbot.ui.main_window import LogBridge, MainWindow
        from slbot.ui.rule_editor import ActionForm

        action = Action("hold", "En espera manual", [{"type": "wait", "seconds": 90}])
        form = ActionForm(None, action.to_dict())
        self.addCleanup(form.close)
        form.queue.setText("Alertas")
        form.accept()
        self.rt.submit(self.rt.edit_rule("action", form.result_data)).result(timeout=2)

        window = MainWindow(self.rt, LogBridge())
        self.addCleanup(window.close)
        window.show()
        window.findChild(QPushButton, "navigate-history").click()
        panel = window.history_page
        panel.pause_button.click()
        self._wait_for(lambda: panel.pause_button.text() == "Reanudar acciones")

        window.findChild(QPushButton, "navigate-actions").click()
        view = window.pages.currentWidget()
        view.filter.setText("En espera manual")
        self.assertEqual(view.action_table.item(0, 1).text(), "Alertas")
        with patch.object(view, "_confirm", return_value=True):
            view.test_button.click()
        self._wait_for(lambda: view.isEnabled() and "Prueba programada" in view.notice.text())
        window.findChild(QPushButton, "navigate-history").click()
        self._wait_for(lambda: panel.table.rowCount() == 1)
        self.assertEqual(panel.table.item(0, 4).text(), "En espera")
        self.assertEqual(panel.table.item(0, 6).text(), "Alertas")
        panel.table.selectRow(0)
        panel.cancel_button.click()
        self._wait_for(lambda: panel.table.item(0, 4).text() == "Cancelada")
        self.assertFalse(panel.cancel_button.isEnabled())
        panel.pause_button.click()
        self._wait_for(lambda: panel.pause_button.text() == "Pausar nuevas acciones")

    def test_twitch_composer_only_sends_manual_input_and_preserves_failed_draft(self):
        from unittest.mock import AsyncMock, PropertyMock
        from PySide6.QtCore import QCoreApplication, QEvent
        from slbot.connectors.oauth import SignInError
        from slbot.ui.monitor import SessionPanel

        panel = SessionPanel(self.rt, chat=True)
        def dispose():
            panel.close()
            panel.deleteLater()
            QCoreApplication.sendPostedEvents(panel, QEvent.Type.DeferredDelete)
        self.addCleanup(dispose)
        twitch = self.rt.connectors["twitch"]
        self.assertFalse(panel.twitch_send.isEnabled())
        with patch.object(type(twitch), "can_send", new_callable=PropertyMock, return_value=True), \
                patch.object(twitch, "send_chat", new_callable=AsyncMock) as send:
            self.assertFalse(panel.twitch_send.isEnabled())
            panel.twitch_message.setText("Borrador")
            send.assert_not_called()
            send.side_effect = SignInError("AutoMod retuvo el mensaje.")
            panel.twitch_send.click()
            self._wait_for(lambda: "AutoMod" in panel.send_result.text())
            self.assertEqual(panel.twitch_message.text(), "Borrador")
            send.side_effect = None
            panel.twitch_send.click()
            self._wait_for(lambda: panel.send_result.text() == "Twitch confirmó el envío.")
            self.assertEqual(panel.twitch_message.text(), "")
            self.assertEqual(send.await_count, 2)
            send.assert_awaited_with("Borrador")

    def test_multichat_shows_obs_scene_refresh_hint(self):
        from slbot.ui.main_window import LogBridge, MainWindow

        window = MainWindow(self.rt, LogBridge())
        self.addCleanup(window.close)
        label = "Actualizar el navegador cuando la escena se active"
        window.show()
        window.select_page("chat")
        self.assertIn(label, window.chat_page.notice.text())
        window.select_page("overlays")
        view = window.overlays_page
        view.refresh(select_id="multi-chat")
        self.assertIn(label, view.overlay_hint.text())
        self.assertIn("/overlay/multi-chat/", view.url.text())
        view.refresh(select_id="gift-alert")
        self.assertNotIn(label, view.overlay_hint.text())

    def test_timer_editor_uses_profile_and_exposes_pause(self):
        from PySide6.QtCore import QCoreApplication, QEvent
        from slbot.core.timers import read_timers
        from slbot.ui.main_window import LogBridge, MainWindow

        window = MainWindow(self.rt, LogBridge())
        def dispose():
            window.close()
            window.deleteLater()
            QCoreApplication.sendPostedEvents(window, QEvent.Type.DeferredDelete)
        self.addCleanup(dispose)
        window.select_page("timers")
        panel = window.timer_page
        self.assertIs(window.pages.currentWidget(), panel)

        class FixtureForm:
            def __init__(self, _parent, actions, existing):
                self.result_data = {"id": "demo", "name": "Aviso", "seconds": 30,
                                    "action_id": actions[0].id, "enabled": False}
                if existing is not None:
                    raise AssertionError("Nuevo temporizador con perfil existente")

            def exec(self):
                return True

        with patch("slbot.ui.timer_panel.TimerForm", FixtureForm):
            panel.add.click()
        self._wait_for(lambda: panel.table.rowCount() == 1)
        self.assertEqual(panel.table.item(0, 3).text(), "Inactivo")
        panel.toggle.click()
        self._wait_for(lambda: panel.table.item(0, 3).text() == "Activo")
        self.assertTrue(read_timers(Config.load(self.path).settings)[0].enabled)
        self.assertEqual(panel.toggle.text(), "Desactivar")
