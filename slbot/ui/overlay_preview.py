"""Native overlay rehearsal. No imported HTML or JavaScript runs inside Qt."""
from __future__ import annotations

import re
from dataclasses import dataclass
from math import sin
from PySide6.QtCore import QEasingCurve, QElapsedTimer, QPointF, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QLinearGradient, QPainter, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import QWidget

from ..overlay_manager import OverlayInfo, validate_overlay_values
from ..overlay_pack import DYNAMIC, _component

_MUSIC = {"music-vinyl", "music-spectrum"}
_ACTIVE = {"alert", "chat", "events", "goal"} | _MUSIC
_BUILTIN = {"gift-alert": "alert", "multi-chat": "chat", "event-feed": "events", "live-goal": "goal",
            "now-playing": "music-vinyl", "now-playing-spectrum": "music-spectrum"}
_TOKEN = re.compile(r"\{([a-z][a-z0-9_]{0,40})\}", re.I)
_W, _H = 960, 540
_SAMPLES = {
    "alert": [("Luna", "TikTok", "¡Gracias por el apoyo!", "gift", "envió un regalo")],
    "chat": [("Luna", "Twitch", "¡Hola a todos!", "chat", "escribió en el chat"),
             ("Mar", "YouTube", "Saludos desde México", "chat", "escribió en el chat"),
             ("Alex", "Kick", "¡Qué buen directo!", "chat", "escribió en el chat"),
             ("Nora", "TikTok", "Ya llegó la banda", "chat", "escribió en el chat")],
    "events": [("Luna", "TikTok", "", "gift", "envió un regalo"),
               ("Mar", "Twitch", "", "follow", "ahora te sigue"),
               ("Alex", "YouTube", "", "sub", "se suscribió")],
}


@dataclass
class Rehearsal:
    kind: str
    settings: dict
    builtin: bool = False


def make_rehearsal(info: OverlayInfo, draft: dict[str, str]) -> Rehearsal | None:
    checked = {}
    for key, value in draft.items():
        try:
            checked.update(validate_overlay_values(info, {key: value}))
        except (TypeError, ValueError):
            continue
    if info.appearance:
        original = info.appearance
        settings = original.defaults.copy()
        for spec in original.specs():
            key = spec["key"]
            if key not in checked:
                continue
            val = checked[key]
            settings[key] = int(float(val)) if spec["type"] == "number" else (
                val == "true" if spec["type"] == "bool" else val)
        return Rehearsal(original.kind, _component(original.kind, settings))
    kind = _BUILTIN.get(info.id)
    # Copies made through Nueva alerta retain the same asset and declared controls.
    if kind is None and info.source == "user" and info.description == "Alerta propia. Puedes enviarla desde Triggers.":
        kind = "alert"
    if kind is None:
        return None
    settings = {spec["key"]: spec.get("default") for spec in info.params}
    for spec in info.params:
        if spec["key"] in checked:
            val = checked[spec["key"]]
            settings[spec["key"]] = int(float(val)) if spec["type"] == "number" else (
                val == "true" if spec["type"] == "bool" else val)
    if kind in _MUSIC:
        enabled = settings.get("motion", True)
        effect = "slide-up" if kind == "music-vinyl" else "slide-left"
        settings.update(enter=effect if enabled else "none", exit=effect if enabled else "none",
                        enterMs=480, exitMs=300, duration=3)
        return Rehearsal(kind, settings, True)
    settings.update({
        "alert": {"enter": "pop", "exit": "pop", "enterMs": 350, "exitMs": 350},
        "chat": {"enter": "slide-up", "exit": "fade", "enterMs": 180, "exitMs": 320},
        "events": {"enter": "slide-up", "exit": "none", "enterMs": 250, "exitMs": 0},
        "goal": {"enter": "fade", "exit": "none", "enterMs": 550, "exitMs": 0},
    }[kind])
    return Rehearsal(kind, settings, True)


def _bezier(x1: float, y1: float, x2: float, y2: float) -> QEasingCurve:
    curve = QEasingCurve(QEasingCurve.BezierSpline)
    curve.addCubicBezierSegment(QPointF(x1, y1), QPointF(x2, y2), QPointF(1, 1))
    return curve


_ENTER = _bezier(.2, .75, .35, 1)
_EXIT = _bezier(.42, 0, 1, 1)


def motion(effect: str, progress: float, leaving: bool) -> tuple[float, float, float, float]:
    """Interpolate the browser's supported opacity, translate and scale keyframes."""
    p = max(0., min(1., progress))
    if effect == "none":
        return 1., 0., 0., 1.
    curve = _EXIT if leaving else _ENTER
    if effect == "pop":
        start_opacity, start_scale = (1., 1.) if leaving else (0., .84)
        end_opacity, end_scale = (0., .88) if leaving else (1., 1.)
        middle_scale = 1.05 if leaving else 1.06
        if p <= .68:
            x = curve.valueForProgress(p / .68)
            return start_opacity + (1. - start_opacity) * x, 0., 0., start_scale + (middle_scale - start_scale) * x
        x = curve.valueForProgress((p - .68) / .32)
        return 1. + (end_opacity - 1.) * x, 0., 0., middle_scale + (end_scale - middle_scale) * x
    amount = curve.valueForProgress(p)
    amount = amount if leaving else 1. - amount
    direction = -1 if leaving else 1
    dx = 24 * amount * direction if effect == "slide-left" else 0.
    dy = 24 * amount * direction if effect == "slide-up" else 0.
    return 1. - amount, dx, dy, 1. - .12 * amount if effect == "zoom" else 1.


def _sample_text(s: dict, row: tuple[str, str, str, str, str]) -> tuple[str, str, str]:
    name, source, message, event, label = row
    values = {"user": name, "platform": source.lower(), "text": message, "user_name": name,
              "type": event, "event_type": event, "event_label": label, "gift_name": "Rosa",
              "count": "3", "amount": "25", "currency": "MXN", "time": "21:15",
              "alert_title": f"{name} {label}", "alert_text": "Rosa ×3", "event_text": message,
              "title": f"{name} {label}"}
    expand = lambda text: _TOKEN.sub(lambda m: values.get(m[1].lower(), ""), text)
    return expand(s["title"]), expand(s["body"]), source if s["showPlatform"] else ""


class OverlayPreview(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("overlayPreviewCanvas")
        self.setAccessibleName("Vista previa de overlay con datos ficticios")
        self.setMinimumHeight(220)
        self.model: Rehearsal | None = None
        self.image = QPixmap()
        self._clock = QElapsedTimer()
        self._timer = QTimer(self, interval=16)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._tick)
        self.phase = "idle"

    def sizeHint(self):
        return QSize(580, 255)

    @property
    def can_play(self) -> bool:
        return self.model is not None and self.model.kind in _ACTIVE

    @property
    def can_exit(self) -> bool:
        return self.can_play and self.model.settings.get("exit") != "none" and self.model.settings.get("exitMs", 0) > 0

    def set_overlay(self, info: OverlayInfo, draft: dict[str, str]):
        self._timer.stop()
        self.phase = "idle"
        self.model = make_rehearsal(info, draft)
        self.image = QPixmap()
        if self.model is None and info.preview_path:
            self.image = QPixmap(str(info.preview_path))
        self.update()

    def play(self):
        if self.can_play:
            self._begin("enter")

    def play_exit(self):
        if self.can_exit:
            self._begin("exit")

    def _begin(self, phase: str):
        self.phase = phase
        self._clock.restart() if self._clock.isValid() else self._clock.start()
        self._tick()

    def _tick(self):
        if not self.can_play:
            self._timer.stop()
            return
        s = self.model.settings
        elapsed = self._clock.elapsed()
        if self.phase == "enter":
            length = s.get("enterMs", 0) if s.get("enter") != "none" else 0
            if elapsed >= length:
                self._begin("hold")
                return
        elif self.phase == "hold":
            length = 1000 * s.get("duration", 0)
            if not length:
                self._timer.stop()
                self.update()
                return
            if elapsed >= length:
                if self.can_exit:
                    self._begin("exit")
                    return
                self.phase = "hidden"
        elif self.phase == "exit" and elapsed >= s.get("exitMs", 0):
            self.phase = "hidden"
        if self.phase not in {"idle", "hidden"}:
            animated_music = self.model.kind in _MUSIC and s.get("motion", True)
            self._timer.start(max(1, length - elapsed) if self.phase == "hold" and not animated_music else 16)
        else:
            self._timer.stop()
        self.update()

    def hideEvent(self, event):
        self._timer.stop()
        self.phase = "idle"
        super().hideEvent(event)

    @staticmethod
    def _font(size, bold=False):
        font = QFont()
        font.setPixelSize(max(int(size), 1))
        font.setBold(bold)
        return font

    def _text(self, p: QPainter, rect: QRectF, text: str, px, color, align="left", bold=False):
        if not text:
            return 0.0
        font = self._font(px, bold)
        p.setFont(font)
        p.setPen(QColor(color))
        flags = {"left": Qt.AlignLeft, "right": Qt.AlignRight, "center": Qt.AlignHCenter}[align]
        flags = int(flags | Qt.AlignTop) | int(Qt.TextWrapAnywhere)
        height = QFontMetricsF(font).boundingRect(QRectF(0, 0, rect.width(), _H * 2), flags, text).height()
        p.drawText(rect, flags, text)
        return height

    def _card(self, p, rect, s, text, subtitle="", platform="", *, top=False, camera=False):
        radius, padding = s["radius"], s["padding"]
        fill = QColor(s["background"])
        fill.setAlphaF(s["opacity"] / 100)
        p.setPen(Qt.NoPen)
        p.setBrush(fill)
        p.drawRoundedRect(rect, radius, radius)
        border = min(s["border"], rect.width(), rect.height())
        if border:
            p.setBrush(QColor(s.get("stripeColor", s["accent"])))
            if top:
                band = QRectF(rect.x(), rect.y(), rect.width(), border)
            else:
                band = QRectF(rect.x(), rect.y(), border, rect.height())
            p.drawRoundedRect(band, min(radius, border / 2), min(radius, border / 2))
        text_rect = rect.adjusted(padding + (border if not top else 0), padding + (border if top else 0), -padding, 0)
        if text_rect.width() <= 0:
            return
        size = s["size"]
        align = "left" if camera else s["align"]
        if platform:
            shift = self._text(p, text_rect, platform.upper(), size * .56, s.get("stripeColor", s["accent"]), align, True)
            text_rect.adjust(0, shift + size * .15, 0, 0)
        shift = self._text(p, text_rect, text, size, s.get("nameColor", s["textColor"]), align, True)
        text_rect.adjust(0, shift + size * .13, 0, 0)
        self._text(p, text_rect, subtitle, size * .73, s["textColor"], align)

    @staticmethod
    def _height(s, data, width):
        title, body, platform = data
        title_size = s["size"]
        safe_width = max(1, width - 2 * s["padding"] - s["border"])
        height = 2 * s["padding"] + 3
        for text, scale in ((title, 1.), (body, .73), (platform, .56)):
            if text:
                font = OverlayPreview._font(title_size * scale, True)
                height += QFontMetricsF(font).boundingRect(
                    QRectF(0, 0, safe_width, 2 * _H), int(Qt.TextWrapAnywhere), text).height() + title_size * .14
        return min(max(height, 18.), _H)

    @staticmethod
    def _position(s, width, height):
        return QRectF((_W - width) * s["positionX"] / 100,
                      (_H - height) * s["positionY"] / 100, width, height)

    def _appearance(self, p, model):
        kind, s = model.kind, model.settings
        if model.builtin:
            self._builtin(p, kind, s)
            return
        if kind in DYNAMIC:
            rows = [_sample_text(s, row) for row in _SAMPLES[kind][:s["max"]]]
            self._stack(p, s, rows)
            return
        data = (s["title"], s["body"], "")
        if kind == "camera":
            inset = max(1, s["border"] / 2)
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(QColor(s["accent"]), s["border"] or 0.01))
            p.drawRoundedRect(QRectF(inset, inset, _W - 2 * inset, _H - 2 * inset), s["radius"], s["radius"])
            if s["title"] or s["body"]:
                width = min(670, max(215, s["size"] * (len(s["title"]) + 3) * .55 + 2 * s["padding"]))
                height = self._height(s, data, width)
                self._card(p, QRectF(0, _H - height, width, height), s, *data, camera=True)
            return
        if kind != "banner":
            base = QColor(s["background"])
            base.setAlphaF(s["opacity"] / 100)
            p.fillRect(QRectF(0, 0, _W, _H), base)
            gradient = QLinearGradient(QPointF(_W, 0), QPointF(_W * .42, _H * .65))
            glow = QColor(s["accent"])
            glow.setAlpha(105)
            gradient.setColorAt(0., glow)
            glow.setAlpha(0)
            gradient.setColorAt(1., glow)
            p.fillRect(QRectF(0, 0, _W, _H), gradient)
            tracer = QColor(s["accent"])
            tracer.setAlpha(28)
            p.setPen(QPen(tracer, 1.7))
            for x in range(-_H, _W, 33):
                p.drawLine(QPointF(x, _H), QPointF(x + _H, 0))
        width = _W * s["width"] / 100
        height = self._height(s, data, width)
        self._card(p, self._position(s, width, height), s, *data, top=True)

    def _stack(self, p, s, rows):
        width = _W * s["width"] / 100
        heights = [self._height(s, data, width) for data in rows]
        gap = max(6, s["size"] * .19)
        area = self._position(s, width, sum(heights) + max(0, len(rows) - 1) * gap)
        y = area.y()
        for data, height in zip(rows, heights):
            self._card(p, QRectF(area.x(), y, width, height), s, *data)
            y += height + gap

    def _builtin(self, p, kind, opts):
        s = {"accent": opts.get("color", "#37dfa8"), "textColor": "#f4f6ff", "background": "#171a29",
             "padding": 13, "border": 4, "width": 85, "positionX": 50, "positionY": 91,
             "size": opts.get("size", 24), "radius": 10, "align": "left", "opacity": opts.get("opacity", 90)}
        if kind == "alert":
            s.update(positionY=50, width=66, padding=24, radius=19, align="center")
            self._stack(p, s, [("Luna envió Rosa", "×3", "")])
        elif kind == "chat":
            rows = [(name, source, message) for name, source, message, _, _ in _SAMPLES["chat"]
                    if opts.get(source.lower(), True)][:opts.get("max", 8)]
            width = _W * s["width"] / 100
            cards = []
            for name, source, message in rows:
                palette = opts.get(source.lower() + "Color", s["accent"])
                show_names = opts.get("names", True)
                data = (name if show_names else "", message, source if opts.get("badges", True) else "")
                color = palette if opts.get("nameByPlatform", False) else s["accent"]
                card_settings = {**s, "border": 3 if opts.get("platformStripe", True) else 0,
                                 "stripeColor": palette, "nameColor": color}
                cards.append((card_settings, data, self._height(card_settings, data, width)))
            gap = max(6, s["size"] * .19)
            area = self._position(s, width, sum(height for _, _, height in cards) + max(0, len(cards) - 1) * gap)
            y = area.y()
            for card_settings, data, height in cards:
                self._card(p, QRectF(area.x(), y, width, height), card_settings, *data)
                y += height + gap
        elif kind == "events":
            s.update(positionY=8, width=90)
            rows = [(name + " " + verb, "", source) for name, source, _, _, verb in _SAMPLES["events"]]
            self._stack(p, s, rows[:opts.get("max", 6)])
        elif kind in _MUSIC:
            self._music(p, kind == "music-spectrum", opts)
        else:
            target = max(1, opts.get("target", 25))
            viewers = 1 if opts.get("metric") == "Seguidores" else 3
            title = opts.get("title") or "Meta de " + opts.get("metric", "Regalos").lower()
            rect = QRectF(120, 185, 720, 137)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#1a2131"))
            p.drawRoundedRect(rect, 16, 16)
            self._text(p, rect.adjusted(25, 19, -25, 0), title, 26, "#f4f6ff", bold=True)
            self._text(p, rect.adjusted(25, 19, -25, 0), f"{viewers} / {target}", 26, s["accent"], align="right")
            bar = QRectF(rect.x() + 25, rect.y() + 75, rect.width() - 50, 18)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#3b4659"))
            p.drawRoundedRect(bar, 8, 8)
            bar.setWidth(bar.width() * min(viewers / target, 1))
            p.setBrush(QColor(s["accent"]))
            p.drawRoundedRect(bar, 8, 8)

    def _music(self, p, spectrum: bool, opts: dict):
        width = max(200, opts["width"] * _W / 100)
        height = 78
        placement = opts["position"]
        x = _W - width - 25 if placement.endswith("derecha") else 25
        y = 25 if placement.startswith("Arriba") else _H - height - 25
        rect = QRectF(x, y, width, height)
        accent, second, fill = (QColor(opts[key]) for key in ("accent", "secondary", "background"))
        fill.setAlpha(round(opts["opacity"] * 255 / 100))
        p.setBrush(fill)
        p.setPen(QPen(accent, 1))
        tick = self._clock.elapsed() if self.phase == "hold" and opts.get("motion") else 0
        if spectrum:
            edge = 10
            p.drawPolygon(QPolygonF([QPointF(x, y), QPointF(rect.right() - edge, y),
                                     QPointF(rect.right(), y + edge), rect.bottomRight(),
                                     QPointF(x + edge, rect.bottom()), QPointF(x, rect.bottom() - edge)]))
            p.setPen(Qt.NoPen)
            p.setBrush(second)
            p.drawRect(QRectF(x + 1, y + 2, 3, height - 13))
            meter = QRectF(x + 12, y + 13, 62, height - 26)
            p.setBrush(QColor("#141a26"))
            p.drawRoundedRect(meter, 2, 2)
            gradient = QLinearGradient(meter.topLeft(), meter.bottomLeft())
            gradient.setColorAt(0, second)
            gradient.setColorAt(1, accent)
            p.setBrush(gradient)
            for i in range(9):
                bar = 16 + 28 * abs(sin(1.57 + i * .83 + tick / 220))
                p.drawRoundedRect(QRectF(meter.x() + 6 + i * 5.7, meter.center().y() - bar / 2, 3.7, bar), 1, 1)
        else:
            p.drawRoundedRect(rect, 14, 14)
            center = QPointF(x + 42, y + height / 2)
            p.setBrush(QColor("#111521"))
            p.drawEllipse(center, 30, 30)
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(QColor("#3b354f"), 1))
            for r in (17, 21, 25, 28):
                p.drawEllipse(center, r, r)
            p.setPen(QPen(accent, 2))
            p.drawArc(QRectF(center.x()-25, center.y()-25, 50, 50), round((-35 + tick * .06) * 16), 56 * 16)
            p.setPen(Qt.NoPen)
            p.setBrush(accent)
            p.drawEllipse(center, 12, 12)
            p.setBrush(second)
            p.drawEllipse(center, 6, 6)
            p.setBrush(QColor("#111521"))
            p.drawEllipse(center, 2.4, 2.4)
        copy = rect.adjusted(88, 9, -11, 0)
        self._text(p, copy, "AHORA SUENA  ·  PRUEBA", 11, second, bold=True)
        title = QFontMetricsF(self._font(23, True)).elidedText(
            "Órbita de medianoche", Qt.TextElideMode.ElideRight, copy.width())
        self._text(p, copy.adjusted(0, 17, 0, 0), title, 23, "#f9fafe", bold=True)
        if opts.get("showArtist"):
            self._text(p, copy.adjusted(0, 43, 0, 0), "Luna Vector", 14, "#dedff1")

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor("#111820"))
        scale = min(self.width() / _W, self.height() / _H)
        if scale <= 0:
            return
        frame = QRectF((self.width() - _W * scale) / 2, (self.height() - _H * scale) / 2, _W * scale, _H * scale)
        p.setClipRect(frame)
        p.fillRect(frame, QColor("#222d3b"))
        for y in range(0, int(frame.height()) + 1, 12):
            for x in range((y // 12 % 2) * 12, int(frame.width()) + 1, 24):
                p.fillRect(QRectF(frame.x() + x, frame.y() + y, 12, 12), QColor("#293646"))
        if not self.model:
            if not self.image.isNull():
                image = self.image.scaled(int(frame.width()), int(frame.height()), Qt.KeepAspectRatio, Qt.SmoothTransformation)
                p.drawPixmap(QPointF(frame.center().x() - image.width()/2, frame.center().y() - image.height()/2), image)
            else:
                p.setPen(QColor("#d9e6ef"))
                p.drawText(frame.adjusted(12, 12, -12, -12),
                           int(Qt.AlignCenter | Qt.TextWordWrap), "HTML externo. Ábrelo en el navegador para ver su diseño y animaciones.")
            return
        if self.phase == "hidden":
            return
        p.translate(frame.x(), frame.y())
        p.scale(scale, scale)
        if self.phase in {"enter", "exit"}:
            s = self.model.settings
            opacity, x, y, size = motion(s[self.phase], self._clock.elapsed() / max(1, s[self.phase + "Ms"]), self.phase == "exit")
            p.setOpacity(opacity)
            p.translate(_W / 2 + x, _H / 2 + y)
            p.scale(size, size)
            p.translate(-_W / 2, -_H / 2)
        self._appearance(p, self.model)
