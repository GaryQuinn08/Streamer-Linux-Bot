"""Editable settings for current packs and recognizable older SLB exports."""
from __future__ import annotations

import hashlib
import html
import json
import re
from dataclasses import dataclass
from pathlib import Path

_META = "slb-appearance.json"
_LIMIT = 250_000
_FIELDS = {
    "title": ("Título", "text", 220), "body": ("Texto secundario", "text", 380),
    "accent": ("Acento y borde", "color"), "textColor": ("Color del texto", "color"),
    "background": ("Fondo", "color"), "opacity": ("Opacidad del fondo (%)", "number"),
    "size": ("Tamaño del texto", "number"), "align": ("Alineación", "select", ["left", "center", "right"]),
    "positionX": ("Posición horizontal (%)", "number"), "positionY": ("Posición vertical (%)", "number"),
    "width": ("Ancho (%)", "number"), "padding": ("Espaciado", "number"), "border": ("Grosor del borde", "number"),
    "radius": ("Esquinas redondeadas", "number"), "duration": ("Duración (s; 0 no oculta)", "number"),
    "max": ("Máximo de mensajes", "number"), "showPlatform": ("Mostrar plataforma", "bool"),
    "enter": ("Animación de entrada", "select"), "enterMs": ("Entrada (ms)", "number"),
    "exit": ("Animación de salida", "select"), "exitMs": ("Salida (ms)", "number"),
}
_EFFECTS = ["none", "fade", "slide-up", "slide-left", "zoom", "pop"]
_EDITOR_CALL = re.compile(r'\}\)\((\{[^\n]*\})\);(?=</script>\s*</body>\s*</html>\s*$)')
# The exact built-in dynamic script shipped before entrance duration was honored.
_OLD_PACK_SCRIPT_HASH = "337b82ac7923acd036d2a642032de58db321e668981d4df7bdb0ddb9afc1cecc"
_OLD_WEB_TIMER = "      if (timed && duration > 0) timers.set(row, setTimeout(() => dismiss(row), duration * 1000));"
_WEB_TIMER = (
    '      const entrance = row.classList.contains("slb-enter")\n'
    '        && !doc.defaultView?.matchMedia("(prefers-reduced-motion: reduce)").matches ? config.enterMs : 0;\n'
    "      if (timed && duration > 0) timers.set(row, setTimeout(() => dismiss(row), entrance + duration * 1000));"
)


@dataclass(frozen=True)
class Appearance:
    kind: str
    defaults: dict
    editor_export: bool = False

    def specs(self) -> list[dict]:
        from .overlay_pack import DYNAMIC, RANGES

        fields = set(_FIELDS)
        if self.kind not in DYNAMIC:
            fields -= {"duration", "max", "showPlatform", "enter", "exit", "enterMs", "exitMs"}
        if self.kind == "alert":
            fields.discard("max")
        if self.kind == "camera":
            fields -= {"positionX", "positionY", "width", "align"}
        specs = []
        for key, (label, kind, *extra) in _FIELDS.items():
            if key not in fields:
                continue
            spec = {"key": key, "label": label, "type": kind, "default": self.defaults[key]}
            if kind == "select":
                spec["options"] = extra[0] if extra else _EFFECTS
            elif kind == "number":
                spec["min"], spec["max"], _ = RANGES[key]
            elif kind == "text":
                spec["maxLength"] = extra[0]
            specs.append(spec)
        return specs

    def render(self, folder: Path, settings: dict[str, str]) -> str:
        from .overlay_pack import _component, render_piece

        values = self.defaults.copy()
        for spec in self.specs():
            key = spec["key"]
            if key not in settings:
                continue
            value = settings[key]
            values[key] = int(float(value)) if spec["type"] == "number" else (
                value == "true" if spec["type"] == "bool" else value)
        values = _component(self.kind, values)
        # Keep the exported editor's actual HTML template, custom CSS and runtime.
        # No user string becomes CSS, markup or a script instruction.
        if self.editor_export:
            source = _read(folder / "index.html")
            if source:
                patched = _patch_editor(source, values, settings)
                if patched is not None:
                    return patched
        return render_piece(self.kind, values)

    def refresh_live(self, folder: Path) -> str | None:
        """Upgrade only known older generated runtimes, without touching the imported file."""
        from .overlay_pack import DYNAMIC, RUNTIME, STYLE, pack_motion_style

        if self.kind not in DYNAMIC:
            return None
        source = _read(folder / "index.html")
        if not source:
            return None
        if self.editor_export:
            upgraded = _refresh_web_timer(source)
            return upgraded if upgraded != source else None
        head, marker, tail = source.rpartition("<script>")
        script, end, rest = tail.partition("</script>")
        if marker and end and hashlib.sha256(script.encode()).hexdigest() == _OLD_PACK_SCRIPT_HASH:
            head = head.replace(STYLE + "</style>", STYLE + pack_motion_style(self.defaults) + "</style>", 1)
            return head + marker + RUNTIME + end + rest
        return None


def _refresh_web_timer(source: str) -> str:
    # Patch the known renderer block, never matching an unrelated string in a user's template.
    marker = "<script>function renderEngine("
    start = source.rfind(marker)
    if start == -1 or not _EDITOR_CALL.search(source, start):
        return source
    return source[:start] + source[start:].replace(_OLD_WEB_TIMER, _WEB_TIMER, 1)


def _read(path: Path) -> str | None:
    try:
        if path.is_symlink() or not path.is_file():
            return None
        with path.open("rb") as stream:
            raw = stream.read(_LIMIT + 1)
        return raw.decode("utf-8-sig") if len(raw) <= _LIMIT else None
    except (OSError, UnicodeError):
        return None


def _json(source: str | None):
    try:
        return json.loads(source) if source else None
    except (ValueError, RecursionError):
        return None


def _json_tag(source: str, marker: str):
    match = re.search(
        r'<script\b(?=[^>]*\bid="' + marker + r'")(?=[^>]*\btype="application/json")[^>]*>(.*?)</script>',
        source, re.S,
    )
    return _json(match.group(1)) if match else None


def _legacy_static(source: str, name: str) -> tuple[str, dict] | None:
    from .overlay_pack import LABELS, STYLE

    # Older desktop packs did not record static metadata; accept only this exact renderer.
    if STYLE not in source:
        return None
    root = re.search(r"<style>:root\{([^}]+)\}", source)
    if not root:
        return None
    if '<main class="frame">' in source:
        kind = "camera"
    elif '<main class="banner">' in source:
        kind = "banner"
    elif '<main class="scene">' in source:
        kind = next((k for k in ("starting", "brb", "ending") if name.endswith(" · " + LABELS[k])), "starting")
    else:
        return None
    props = dict(item[2:].split(":", 1) for item in root[1].split(";") if item.startswith("--") and ":" in item)
    copy = re.search(r"<h1>([^<]*)</h1><p>([^<]*)</p>", source)
    values = {"name": name, "title": html.unescape(copy[1]) if copy else "",
              "body": html.unescape(copy[2]) if copy else "", "accent": props.get("accent"),
              "textColor": props.get("ink"), "align": props.get("align")}
    fill = props.get("fill", "")
    if re.fullmatch(r"#[0-9a-fA-F]{8}", fill):
        values.update(background=fill[:7], opacity=round(int(fill[7:], 16) * 100 / 255))
    for dst, css, suffix in (("width", "width", "%"), ("positionY", "y", "%"), ("offset", "offset", "%"),
                             ("size", "size", "px"), ("padding", "padding", "px"), ("border", "line", "px"),
                             ("radius", "radius", "px")):
        raw = props.get(css, "")
        if re.fullmatch(r"[0-9.]{1,8}" + suffix, raw):
            try:
                values[dst] = float(raw.removesuffix(suffix))
            except ValueError:
                pass
    if values.get("width", 100) < 100 and "offset" in values:
        values["positionX"] = values["offset"] * 100 / (100 - values["width"])
    return kind, values


def load_appearance(folder: Path, name: str) -> Appearance | None:
    from .overlay_pack import DYNAMIC, LABELS, _component

    stored = _json(_read(folder / _META))
    if isinstance(stored, dict) and isinstance(stored.get("kind"), str) and stored["kind"] in LABELS:
        raw = stored.get("design")
        if isinstance(raw, dict):
            return Appearance(stored["kind"], _component(stored["kind"], raw))
    source = _read(folder / "index.html")
    if not source:
        return None
    static = _json_tag(source, "slb-pack-component-v1")
    if isinstance(static, dict) and isinstance(static.get("kind"), str) and static["kind"] in LABELS:
        raw = static.get("design")
        if isinstance(raw, dict):
            return Appearance(static["kind"], _component(static["kind"], raw))
    pack = _json_tag(source, "slb-pack-data")
    if isinstance(pack, dict) and isinstance(pack.get("mode"), str) and pack["mode"] in DYNAMIC:
        return Appearance(pack["mode"], _component(pack["mode"], pack))
    editor = _json_tag(source, "slb-design-v1")
    if (isinstance(editor, dict) and isinstance(editor.get("mode"), str) and editor["mode"] in DYNAMIC
            and _EDITOR_CALL.search(source) and "</style>" in source and 'id="slb-template"' in source):
        return Appearance(editor["mode"], _component(editor["mode"], editor), editor_export=True)
    old = _legacy_static(source, name)
    return Appearance(old[0], _component(*old)) if old else None


def _patch_editor(source: str, c: dict, overrides: dict) -> str | None:
    from .overlay_pack import motion_keyframes

    source = _refresh_web_timer(source)
    match = _EDITOR_CALL.search(source)
    if not match or "</style>" not in source:
        return None
    runtime = _json(match.group(1))
    if not isinstance(runtime, dict):
        return None
    for prop in ("title", "body", "max", "duration", "enter", "exit", "enterMs", "exitMs"):
        if prop in overrides:
            runtime[prop] = c[prop]
    payload = (json.dumps(runtime, ensure_ascii=True).replace("<", r"\u003c")
               .replace(">", r"\u003e").replace("&", r"\u0026"))
    source = source[:match.start(1)] + payload + source[match.end(1):]
    color = c["background"] + f"{round(c['opacity'] * 255 / 100):02x}"
    props = {
        "accent": ("--accent", c["accent"]), "textColor": ("--ink", c["textColor"]), "size": ("font-size", f"{c['size']}px"),
        "background": ("--card", color), "opacity": ("--card", color), "align": ("--slb-align", c["align"]),
        "width": ("--slb-width", f"{c['width']}%"), "padding": ("--slb-padding", f"{c['padding']}px"),
        "radius": ("--slb-radius", f"{c['radius']}px"), "border": ("--slb-border", f"{c['border']}px"),
        "showPlatform": ("--slb-platform", "block" if c["showPlatform"] else "none"),
    }
    css = ":root{" + ";".join(":".join(props[key]) for key in props if key in overrides) + "}"
    if "positionX" in overrides or "width" in overrides:
        css += f":root{{--slb-x:{(100-c['width'])*c['positionX']/100:g}%}}"
    if "positionY" in overrides:
        css += f":root{{--slb-y:{c['positionY']}%;--slb-shift-y:-{c['positionY']}%}}"
    for i, (event, token, timing) in enumerate((("enter", "in", "cubic-bezier(.2,.75,.35,1)"), ("exit", "out", "ease-in"))):
        if event not in overrides and event + "Ms" not in overrides:
            continue
        duration, effect = c[event + "Ms"], c[event]
        selector = f".slb-row.slb-{event}"
        if not duration or effect == "none":
            css += selector + "{animation:none}"
            continue
        css += f"@keyframes slb-custom-{token}{{{motion_keyframes(effect, leaving=bool(i))}}}"
        css += selector + f"{{animation:slb-custom-{token} {duration}ms {timing} both}}"
        css += f"@media(prefers-reduced-motion:reduce){{{selector}{{animation:none!important}}}}"
    return source.replace("</style>", "\n" + css + "</style>", 1)
