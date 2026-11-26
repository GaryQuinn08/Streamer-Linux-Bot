import asyncio
import os
import unittest
from concurrent.futures import Future
from types import SimpleNamespace


class FakeSpeechRuntime:
    def __init__(self):
        self.chat_tts = SimpleNamespace(settings=SimpleNamespace(enabled=False, platforms=frozenset()))
        self.requests = []
        self.preview_count = 0
        self.clear_count = 0

    def submit(self, coro):
        request = Future()
        self.requests.append((request, coro))
        return request

    def finish(self, index=-1, error=None):
        request, coro = self.requests[index]
        if error:
            coro.close()
            request.set_exception(error)
        else:
            request.set_result(asyncio.run(coro))

    async def configure_chat_tts(self, enabled, platforms):
        self.chat_tts.settings = SimpleNamespace(enabled=enabled, platforms=platforms)

    async def preview_chat_tts(self):
        self.preview_count += 1

    async def clear_chat_tts(self):
        self.clear_count += 1


class ChatSpeechPanelTest(unittest.TestCase):
    def setUp(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        try:
            from PySide6.QtWidgets import QApplication
        except ImportError:
            self.skipTest("Qt no instalado")
        from slbot.ui.chat_speech import ChatSpeechPanel

        self.app = QApplication.instance() or QApplication([])
        self.runtime = FakeSpeechRuntime()
        self.panel = ChatSpeechPanel(self.runtime)
        self.addCleanup(self.panel.close)

    def test_selectively_enables_and_saves_one_platform_at_a_time(self):
        p = self.panel
        self.assertFalse(p.enabled.isChecked())
        self.assertEqual(set(p.platforms), {"twitch", "tiktok", "youtube", "kick"})
        self.assertFalse(p.save.isEnabled())
        p.enabled.click()
        self.assertFalse(p.save.isEnabled())
        p.platforms["twitch"].click()
        p.platforms["kick"].click()
        self.assertTrue(p.save.isEnabled())
        p.save.click()
        self.assertFalse(p.platforms["tiktok"].isEnabled())
        self.runtime.finish()
        self.app.processEvents()
        self.assertEqual(self.runtime.chat_tts.settings.platforms, {"twitch", "kick"})
        self.assertEqual(p.status.text(), "Leyendo el chat de: Twitch, Kick.")
        p.enabled.click()
        p.save.click()
        self.runtime.finish()
        self.app.processEvents()
        self.assertFalse(self.runtime.chat_tts.settings.enabled)
        self.assertTrue(p.platforms["twitch"].isChecked())

    def test_preview_without_enabling_and_stop_while_busy(self):
        p = self.panel
        p.preview.click()
        self.runtime.finish()
        self.app.processEvents()
        self.assertEqual(self.runtime.preview_count, 1)
        self.assertEqual(p.status.text(), "Muestra de voz reproducida.")
        self.assertFalse(self.runtime.chat_tts.settings.enabled)

        p.preview.click()
        self.assertTrue(p.clear.isEnabled())
        p.clear.click()
        self.runtime.finish(-1)
        self.app.processEvents()
        stopped = p.status.text()
        self.assertIn("Voz detenida", stopped)
        self.runtime.finish(-2, RuntimeError("muestra cancelada"))
        self.app.processEvents()
        self.assertEqual(p.status.text(), stopped)
        self.assertEqual(self.runtime.clear_count, 1)
        self.assertFalse(self.runtime.chat_tts.settings.enabled)

    def test_shows_missing_voice_error(self):
        self.panel.preview.click()
        self.runtime.finish(error=RuntimeError("Instala espeak-ng."))
        self.app.processEvents()
        self.assertEqual(self.panel.status.text(), "Instala espeak-ng.")
        self.assertTrue(self.panel.preview.isEnabled())


if __name__ == "__main__":
    unittest.main()
