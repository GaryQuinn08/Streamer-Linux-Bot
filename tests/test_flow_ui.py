"""Editor real y ejecución manual para el flujo de beta 20."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from slbot.core.config import Action, Config
from slbot.runtime import Runtime


class FlowUiTests(unittest.TestCase):
    def test_edit_numeric_condition_selects_stable_action_and_runs(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        try:
            from PySide6.QtTest import QTest
            from PySide6.QtWidgets import QApplication
        except ImportError:
            self.skipTest("Qt no instalado")
        from slbot.ui.main_window import LogBridge
        from slbot.ui.rule_editor import ActionWorkspace, StepForm

        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"SLB_DATA_DIR": directory}):
            config = Config(path=Path(directory) / "config.json")
            child = Action("child", "Saludo del regalo", [
                {"type": "set_variable", "key": "saludo", "value": "Gracias, {user}"},
            ], "Alertas")
            parent = Action("parent", "Regalo grande", [{"type": "log", "message": "{local_saludo}"}], "Alertas")
            config.actions = [parent, child]
            rt = Runtime(config=config, port=0)
            rt.start()
            try:
                form = StepForm(None, {"type": "condition"}, config.actions, current_id="parent")
                branch = form.fields["then_id"][1]
                self.assertEqual(branch.findData("parent"), -1)
                branch.setCurrentIndex(branch.findText("Saludo del regalo"))
                form.accept()
                self.assertEqual(form.result_data["then_id"], "child")
                rt.submit(rt.edit_rule("action", {**parent.to_dict(),
                           "steps": [form.result_data, *parent.steps]})).result(timeout=2)
                form.close()
                bridge = LogBridge()
                view = ActionWorkspace(rt, bridge.rules_changed)
                self.assertIn("Saludo del regalo", view.step_table.item(0, 1).text())
                with patch.object(view, "_confirm", return_value=True):
                    view.test_button.click()
                for _ in range(150):
                    if any("Gracias, viewer_demo" in line for line in rt.log_history):
                        break
                    QTest.qWait(10)
                self.assertIn("Gracias, viewer_demo", "\n".join(rt.log_history))
                self.assertEqual([run.action for run in rt.action_snapshot()], ["Regalo grande"])
                view.close()
                app.processEvents()
            finally:
                rt.stop()
