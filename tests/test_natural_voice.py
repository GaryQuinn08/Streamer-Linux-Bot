from __future__ import annotations

import hashlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from slbot import natural_voice


class VoiceInstallTests(unittest.TestCase):
    def test_verifies_downloads_and_leaves_no_partial_model(self):
        expected = b"pinned model fixture"
        manifest = {"voice.onnx": (len(expected), hashlib.sha256(expected).hexdigest())}
        with tempfile.TemporaryDirectory() as folder, patch.dict(natural_voice._FILES, manifest, clear=True), patch(
            "slbot.natural_voice.voice_folder", return_value=Path(folder),
        ), patch("urllib.request.build_opener") as opener:
            service = opener.return_value
            service.open = Mock(return_value=io.BytesIO(b"bad"))
            with self.assertRaisesRegex(ValueError, "integridad"):
                natural_voice.install_model()
            self.assertEqual(list(Path(folder).iterdir()), [])
            service.open.return_value = io.BytesIO(expected)
            natural_voice.install_model()
            self.assertEqual((Path(folder) / "voice.onnx").read_bytes(), expected)
            service.open.reset_mock()
            natural_voice.install_model()
            service.open.assert_not_called()
