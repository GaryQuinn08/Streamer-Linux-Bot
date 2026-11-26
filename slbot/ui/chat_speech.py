"""Desktop controls for the shared, opt-in chat narrator."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import QCheckBox, QGroupBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

PLATFORMS = (("twitch", "Twitch"), ("tiktok", "TikTok"), ("youtube", "YouTube"), ("kick", "Kick"))


class ChatSpeechPanel(QGroupBox):
    completed = Signal(int, str, str)

    def __init__(self, runtime):
        super().__init__("Leer chat en voz alta (TTS)")
        self.setObjectName("chatSpeech")
        self.rt = runtime
        self._pending = ""
        self._revision = 0
        self._baseline = None
        layout = QVBoxLayout(self)
        self.enabled = QCheckBox("Leer automáticamente los mensajes nuevos")
        self.enabled.setObjectName("enableChatTts")
        layout.addWidget(self.enabled)

        choices = QHBoxLayout()
        self.platforms = {}
        for key, label in PLATFORMS:
            option = QCheckBox(label)
            option.setObjectName("chatTts-" + key)
            option.setAccessibleName("Leer chat de " + label)
            option.toggled.connect(self._edited)
            self.platforms[key] = option
            choices.addWidget(option)
        choices.addStretch(1)
        layout.addLayout(choices)

        buttons = QHBoxLayout()
        self.save = QPushButton("Guardar lectura")
        self.save.setObjectName("saveChatTts")
        self.save.clicked.connect(self._save)
        self.preview = QPushButton("Probar voz")
        self.preview.setObjectName("testChatTts")
        self.preview.clicked.connect(self._preview)
        self.clear = QPushButton("Detener y vaciar cola")
        self.clear.setObjectName("clearChatTts")
        self.clear.setToolTip("Detiene la voz actual y descarta lo pendiente. No desactiva los próximos mensajes.")
        self.clear.clicked.connect(self._clear)
        for button in (self.save, self.preview, self.clear):
            buttons.addWidget(button)
        buttons.addStretch(1)
        layout.addLayout(buttons)

        hint = QLabel("La voz es la misma en todas las plataformas. "
                      "Este ajuste no cambia el multichat ni el overlay. "
                      "Si OBS captura el audio del bot, la voz saldrá en la emisión.")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.status = QLabel()
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.completed.connect(self._done, Qt.ConnectionType.QueuedConnection)
        self.enabled.toggled.connect(self._edited)
        self._read_settings()
        self._report_saved_settings()

    def _read_settings(self):
        config = self.rt.chat_tts.settings
        self.enabled.blockSignals(True)
        self.enabled.setChecked(config.enabled)
        self.enabled.blockSignals(False)
        for key, option in self.platforms.items():
            option.blockSignals(True)
            option.setChecked(key in config.platforms)
            option.blockSignals(False)
        self._baseline = self._draft()
        self._update_buttons()

    def _draft(self):
        return self.enabled.isChecked(), frozenset(key for key, box in self.platforms.items() if box.isChecked())

    def _update_buttons(self):
        enabled, platforms = self._draft()
        idle = not self._pending
        self.save.setEnabled(idle and (enabled, platforms) != self._baseline and (not enabled or bool(platforms)))
        self.enabled.setEnabled(idle)
        for box in self.platforms.values():
            box.setEnabled(idle)
        self.preview.setEnabled(idle)
        self.clear.setEnabled(idle or self._pending == "preview")

    def _report_saved_settings(self):
        settings = self.rt.chat_tts.settings
        labels = ", ".join(label for key, label in PLATFORMS if key in settings.platforms)
        self.status.setText("Leyendo el chat de: " + labels + "." if settings.enabled and labels else
                            "Lectura automática desactivada. Puedes probar la voz sin activarla.")

    def _edited(self, *_):
        self._update_buttons()
        enabled, platforms = self._draft()
        if enabled and not platforms:
            self.status.setText("Selecciona al menos una plataforma para activar la lectura.")
        elif self._draft() != self._baseline:
            self.status.setText("Cambios sin guardar.")
        else:
            self._report_saved_settings()

    def _submit(self, kind, factory, label):
        if self._pending and not (kind == "clear" and self._pending == "preview"):
            return
        self._pending = kind
        self._revision += 1
        revision = self._revision
        self._update_buttons()
        self.status.setText(label)
        operation = factory()
        try:
            future = self.rt.submit(operation)
        except RuntimeError:
            operation.close()
            self._done(revision, kind, "El bot no está activo. Vuelve a abrir la aplicación.")
            return

        notify = self.completed

        def complete(task):
            if task.cancelled():
                error = "La operación se canceló."
            else:
                issue = task.exception()
                error = ""
                if issue:
                    error = str(issue) if isinstance(issue, (RuntimeError, ValueError)) else (
                        "No se pudo guardar la lectura. Revisa los permisos de la configuración." if kind == "save"
                        else "No se pudo completar la prueba. Revisa el registro y la salida de audio.")
            try:
                notify.emit(revision, kind, error)
            except RuntimeError:
                pass  # the window may already be gone

        future.add_done_callback(complete)

    def _save(self):
        if self.save.isEnabled():
            enabled, platforms = self._draft()
            self._submit("save", lambda: self.rt.configure_chat_tts(enabled, platforms), "Guardando lectura…")

    def _preview(self):
        self._submit("preview", self.rt.preview_chat_tts, "Preparando una muestra de voz…")

    def _clear(self):
        self._submit("clear", self.rt.clear_chat_tts, "Deteniendo la voz…")

    @Slot(int, str, str)
    def _done(self, revision, kind, error):
        if revision != self._revision:
            return
        self._pending = ""
        if error:
            self.status.setText(error)
        elif kind == "save":
            self._read_settings()
            self._report_saved_settings()
        elif kind == "preview":
            self.status.setText("Muestra de voz reproducida.")
        else:
            self.status.setText("Voz detenida. Si la lectura sigue activada, se leerán los mensajes nuevos.")
        self._update_buttons()
