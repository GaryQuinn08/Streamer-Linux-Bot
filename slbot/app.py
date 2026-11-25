"""Punto de entrada de la aplicación de escritorio."""
from __future__ import annotations

import logging
import sys

from PySide6.QtWidgets import QApplication, QMessageBox

from .runtime import Runtime
from .ui.main_window import LogBridge, MainWindow


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    app = QApplication(sys.argv if argv is None else argv)
    app.setApplicationName("Streamer Linux Bot")
    app.setDesktopFileName("streamer-linux-bot")

    bridge = LogBridge()
    runtime = Runtime(on_log=bridge.message.emit)
    try:
        runtime.start()
    except Exception as exc:
        QMessageBox.critical(
            None,
            "Streamer Linux Bot",
            f"No se pudo iniciar el servidor local de overlays:\n{exc}\n\n"
            "¿Ya hay otra copia de la app abierta usando el mismo puerto?",
        )
        return 1

    window = MainWindow(runtime, bridge)
    window.show()
    code = app.exec()
    runtime.stop()
    return code
