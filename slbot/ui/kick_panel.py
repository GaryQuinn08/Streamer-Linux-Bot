"""Opt-in desktop receiver for Kick's signed webhook."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRegularExpression, Qt, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices, QRegularExpressionValidator
from PySide6.QtWidgets import QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSpinBox


class KickPanel(QGroupBox):
    finished = Signal(str)

    def __init__(self, runtime):
        super().__init__("Kick · webhook firmado")
        self.rt = runtime
        self.connector = runtime.connectors["kick"]
        self.pending = False
        layout = QFormLayout(self)
        hint = QLabel("Opcional y avanzado: requiere el extra --kick y que hayas configurado tu webhook en Kick. "
                      "El receptor solo escucha en este equipo; no abre el puerto a Internet.")
        hint.setWordWrap(True)
        layout.addRow(hint)
        self.channel = QLineEdit()
        self.channel.setValidator(QRegularExpressionValidator(QRegularExpression("[0-9]{1,18}"), self))
        self.channel.setPlaceholderText("ID numérico del canal")
        layout.addRow("Canal:", self.channel)
        self.port = QSpinBox()
        self.port.setRange(1, 65535)
        self.port.setValue(8770)
        layout.addRow("Puerto local:", self.port)
        self.pem = QLineEdit()
        self.pem.setPlaceholderText("Ruta a la clave pública .pem de Kick")
        files = QHBoxLayout()
        files.addWidget(self.pem, 1)
        choose = QPushButton("Elegir archivo")
        choose.clicked.connect(self._choose)
        files.addWidget(choose)
        layout.addRow("Clave pública:", files)
        row = QHBoxLayout()
        self.connect = QPushButton("Activar receptor")
        self.connect.clicked.connect(self._start)
        self.disconnect = QPushButton("Desactivar")
        self.disconnect.clicked.connect(lambda: self._submit(self.connector.stop()))
        guide = QPushButton("Guía de Kick")
        guide.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(
            "https://github.com/GaryQuinn08/Streamer-Linux-Bot/blob/refactor/overlay-boundary/docs/CONECTORES.md#kick-webhook-firmado"
        )))
        for button in (self.connect, self.disconnect, guide):
            row.addWidget(button)
        row.addStretch(1)
        layout.addRow(row)
        self.feedback = QLabel()
        self.feedback.setTextFormat(Qt.TextFormat.PlainText)
        self.feedback.setWordWrap(True)
        layout.addRow(self.feedback)
        self.finished.connect(self._done, Qt.ConnectionType.QueuedConnection)
        self.refresh()

    def refresh(self):
        self.connect.setEnabled(not self.pending and self.connector.port is None)
        self.disconnect.setEnabled(not self.pending and self.connector.port is not None)

    def _choose(self):
        chosen, _ = QFileDialog.getOpenFileName(self, "Clave pública de Kick", "", "Clave PEM (*.pem);;Todos (*)")
        if chosen:
            self.pem.setText(chosen)

    def _start(self):
        if not self.channel.hasAcceptableInput() or int(self.channel.text()) <= 0 or not self.pem.text().strip():
            self.feedback.setText("Indica el ID del canal y el archivo PEM público.")
            return
        self._submit(self.connector.start(self.port.value(), int(self.channel.text()),
                                          Path(self.pem.text().strip()).expanduser()))

    def _submit(self, operation):
        if self.pending:
            operation.close()
            return
        self.pending = True
        self.refresh()
        self.feedback.setText("Comprobando receptor local…")
        try:
            future = self.rt.submit(operation)
        except RuntimeError:
            operation.close()
            self._done("El bot no está activo.")
            return
        signal = self.finished

        def completed(done):
            issue = None if done.cancelled() else done.exception()
            if isinstance(issue, ImportError):
                result = "Reinstala el bot con --kick para activar este receptor."
            elif isinstance(issue, OSError):
                result = "No se pudo leer la clave o abrir el puerto local. Revisa esos dos campos."
            elif issue:
                result = "No se pudo activar el receptor. Revisa que sea la clave pública PEM de Kick."
            else:
                result = "Operación cancelada." if done.cancelled() else ""
            try:
                signal.emit(result)
            except RuntimeError:
                pass

        future.add_done_callback(completed)

    @Slot(str)
    def _done(self, issue):
        self.pending = False
        self.refresh()
        port = self.connector.port
        self.feedback.setText(issue or (f"Escuchando en 127.0.0.1:{port}/webhooks/kick"
                                        if port is not None else "Receptor desactivado."))
