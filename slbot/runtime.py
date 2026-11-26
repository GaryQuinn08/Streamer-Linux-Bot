"""Runtime: el núcleo asíncrono que vive en un hilo propio.

La interfaz Qt corre en el hilo principal; todo lo demás (bus de eventos,
motor de triggers, servidor de overlays, conectores) corre en un bucle asyncio
en un hilo aparte. La interfaz se comunica con él mediante `submit()` / `emit()`
y recibe el registro por el callback `on_log` (que debe ser seguro entre hilos,
p. ej. una señal de Qt).
"""
from __future__ import annotations

import asyncio
import copy
import errno
import logging
import shutil
import tempfile
import threading
import time
from collections import deque
from dataclasses import dataclass, replace
from itertools import count
from pathlib import Path
from typing import Any, Callable, Coroutine

from .audio import MusicQueue
from .chat_tts import CONFIG_KEY as CHAT_TTS_KEY, ChatTts, ChatTtsSettings
from .connectors.base import Connector
from .connectors.obs import ObsConnector
from .connectors.kick import KickConnector
from .connectors.platforms import TwitchConnector, YoutubeConnector
from .connectors.tiktok import TiktokConnector
from .connectors.spotify import SpotifyConnector
from .connectors.simulator import sample_event
from .core.actions import run_action, overlay_variables
from .core.config import Config, DEFAULT_ACTIONS, DEFAULT_TRIGGERS, Action, Trigger
from .core.engine import Engine
from .core.editing import update_rules
from .core.events import Event, EventBus
from .core.timers import Timer, TimerService, read_timers, without_timers
from .overlay_manager import find_overlay, validate_overlay_values
from .overlay_server import CHAT_PLATFORMS, OverlayServer
from .paths import user_overlays_dir

log = logging.getLogger("slb.runtime")


@dataclass(frozen=True)
class ActionRun:
    id: int
    at: float
    action: str
    origin: str
    platform: str
    event: str
    state: str = "En curso"
    failures: int = 0
    duration_ms: int | None = None


@dataclass(frozen=True)
class ChatLine:
    at: float
    platform: str
    user: str
    text: str
    simulated: bool


class Runtime:
    def __init__(
        self,
        on_log: Callable[[str], None] | None = None,
        config: Config | None = None,
        port: int | None = None,
        editor_only: bool = False,
    ) -> None:
        self.config = config or Config.load()
        self._on_log = on_log or (lambda _msg: None)
        self._port_override = port
        self.editor_only = editor_only
        self.log_history: deque[str] = deque(maxlen=500)
        self._monitor_lock = threading.Lock()
        self.goal_counts = {"gift": 0, "follow": 0}
        self._chat: deque[ChatLine] = deque(maxlen=400)
        self._action_history: deque[ActionRun] = deque(maxlen=300)
        self._running_actions: deque[ActionRun] = deque(maxlen=300)
        self._action_ids = count(1)

        self.loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._startup_error: BaseException | None = None
        self._background: set[asyncio.Task[Any]] = set()

        self.bus = EventBus()
        self.engine = Engine(self)
        self.timers = TimerService(self)
        self._timer_task: asyncio.Task | None = None
        self.music = MusicQueue(self)
        self.voice_lock = asyncio.Lock()
        self.chat_tts = ChatTts(self, ChatTtsSettings.from_config(self.config.settings))
        self.overlays = OverlayServer(self)
        self.overlay_port_message = ""
        self._overlay_lock = asyncio.Lock()
        self.obs = ObsConnector(self)
        self.connectors: dict[str, Connector] = {
            "obs": self.obs,
            "twitch": TwitchConnector(self),
            "youtube": YoutubeConnector(self),
            "kick": KickConnector(self),
            "tiktok": TiktokConnector(self),
            "spotify": SpotifyConnector(self),
        }

    # -- utilidades --------------------------------------------------------

    @property
    def port(self) -> int | None:
        return self.overlays.port

    def log(self, message: str) -> None:
        line = f"{time.strftime('%H:%M:%S')}  {message}"
        self.log_history.append(line)
        log.info(message)
        try:
            self._on_log(line)
        except Exception:
            log.exception("Fallo en el callback de registro")

    def spawn(self, coro: Coroutine[Any, Any, Any]) -> asyncio.Task:
        """Lanza una tarea en segundo plano (solo desde el hilo del bucle)."""
        task = asyncio.ensure_future(coro)
        self._background.add(task)
        task.add_done_callback(self._background.discard)
        return task

    def submit(self, coro: Coroutine[Any, Any, Any]):
        """Ejecuta una corrutina en el bucle desde cualquier hilo."""
        if self.loop is None:
            raise RuntimeError("El runtime no está iniciado")
        return asyncio.run_coroutine_threadsafe(coro, self.loop)

    def emit(self, ev: Event) -> None:
        self.submit(self.bus.publish(ev))

    def chat_snapshot(self) -> tuple[ChatLine, ...]:
        with self._monitor_lock:
            return tuple(self._chat)

    def action_snapshot(self) -> tuple[ActionRun, ...]:
        with self._monitor_lock:
            return tuple(self._running_actions) + tuple(self._action_history)

    async def _track_chat(self, event: Event) -> None:
        if event.type == "chat" and isinstance(event.data.get("text"), str):
            line = ChatLine(event.ts, event.platform, event.user, event.data["text"][:500],
                            event.data.get("simulated") is True)
            with self._monitor_lock:
                self._chat.append(line)

    async def configure_chat_tts(self, enabled: bool, platforms) -> ChatTtsSettings:
        preference = ChatTtsSettings.from_selection(enabled, platforms)
        settings = {**self.config.settings, CHAT_TTS_KEY: preference.to_dict()}
        Config(settings=settings, triggers=self.config.triggers, actions=self.config.actions,
               path=self.config.path).save()
        self.config.settings = settings
        await self.chat_tts.apply(preference)
        return preference

    async def reload_chat_tts(self, settings) -> None:
        preference = ChatTtsSettings.from_config(settings)
        self.config.settings[CHAT_TTS_KEY] = preference.to_dict()
        await self.chat_tts.apply(preference)

    async def preview_chat_tts(self) -> None:
        if self.editor_only:
            raise ValueError("El editor de perfil no reproduce la voz.")
        await self.chat_tts.preview()

    async def clear_chat_tts(self) -> None:
        await self.chat_tts.clear()

    async def execute_action(self, action: Action, event: Event, origin: str) -> None:
        if self.editor_only:
            raise ValueError("El editor de perfil no ejecuta acciones.")
        run = ActionRun(next(self._action_ids), time.time(), action.name, origin, event.platform, event.type)
        start = time.monotonic()
        with self._monitor_lock:
            self._running_actions.append(run)
        state, failures = "Cancelada", 0
        try:
            failures = await run_action(self, action, event)
            state = "Con errores" if failures else "Completada"
        except Exception:
            state, failures = "Con errores", 1
            raise
        finally:
            result = replace(run, state=state, failures=failures,
                             duration_ms=int((time.monotonic() - start) * 1000))
            with self._monitor_lock:
                if run in self._running_actions:
                    self._running_actions.remove(run)
                self._action_history.append(result)

    async def edit_rule(self, kind: str, data: dict, *, delete: bool = False) -> None:
        update_rules(self.config, kind, data, delete=delete)

    async def edit_timer(self, data: dict, *, delete: bool = False) -> None:
        if delete:
            ident = data.get("id")
            if not isinstance(ident, str) or not ident:
                raise ValueError("Selecciona un temporizador.")
            settings = without_timers(self.config.settings, {ident})
        else:
            existing = {item.id: item for item in read_timers(self.config.settings)}
            timer = Timer.parse(data)
            if self.config.action_by_id(timer.action_id) is None:
                raise ValueError("Elige una acción existente.")
            if timer.id not in existing and len(existing) >= 100:
                raise ValueError("El perfil admite hasta 100 temporizadores.")
            existing[timer.id] = timer
            settings = {**self.config.settings, "timers": [item.to_dict() for item in existing.values()]}
        Config(settings=settings, triggers=self.config.triggers, actions=self.config.actions,
               path=self.config.path).save()
        self.config.settings = settings

    async def save_gift_rule(self, enabled: bool, gift_name: str, cooldown: int,
                             title: str, sound: str = "", overlay_id: str = "gift-alert") -> None:
        if find_overlay(overlay_id) is None:
            raise ValueError("El overlay seleccionado ya no existe.")

        triggers = copy.deepcopy(self.config.triggers)
        actions = copy.deepcopy(self.config.actions)
        trigger = next((t for t in triggers if t.id == "tiktok-gift"), None)
        if trigger is None:
            trigger = Trigger.from_dict(copy.deepcopy(DEFAULT_TRIGGERS[0]))
            triggers.append(trigger)
        action = next((a for a in actions if a.id == trigger.action_id), None)
        if action is None:
            action = Action(trigger.action_id, "Alerta de regalo",
                            copy.deepcopy(DEFAULT_ACTIONS[0]["steps"]))
            actions.append(action)
        trigger.enabled = enabled
        trigger.cooldown_s = cooldown
        if gift_name:
            trigger.filters["gift_name"] = gift_name
        else:
            trigger.filters.pop("gift_name", None)
        step = next((s for s in action.steps if s.get("type") == "overlay_alert"), None)
        if step is None:
            step = {"type": "overlay_alert", "overlay": "gift-alert", "text": "x{count}"}
            action.steps.insert(0, step)
        step["overlay"] = overlay_id
        step["title"] = title
        action.steps = [s for s in action.steps if s.get("id") != "quick-gift-sound"]
        if sound:
            action.steps.append({"type": "play_sound", "id": "quick-gift-sound", "file": sound})
        saved = Config(settings=self.config.settings, triggers=triggers,
                       actions=actions, path=self.config.path)
        saved.save()
        self.config.triggers, self.config.actions = triggers, actions
        self.log("Regla de regalos actualizada.")

    async def _forward_overlay_event(self, event: Event) -> None:
        if (event.platform == "tiktok" and event.type in self.goal_counts
                and event.data.get("simulated") is not True):
            count = event.data.get("count", 1) if event.type == "gift" else 1
            if type(count) is int and count > 0:
                self.goal_counts[event.type] += min(count, 100_000)
                await self.overlays.broadcast("live-goal", {
                    "channel": "goal", "counts": self.goal_counts,
                })
        await self.overlays.forward_event(event)

    async def change_overlay_port(self, port: int) -> int:
        if type(port) is not int or not 1 <= port <= 65535:
            raise ValueError("Escribe un puerto entre 1 y 65535.")
        async with self._overlay_lock:
            if port == self.port:
                return port
            candidate = OverlayServer(self)
            try:
                await candidate.start(port)
            except OSError as exc:
                if exc.errno == errno.EADDRINUSE:
                    raise ValueError(f"El puerto {port} ya está ocupado. Elige otro.") from exc
                raise ValueError(f"No se pudo usar el puerto {port}: {exc.strerror or exc}") from exc
            settings = {**self.config.settings, "overlay_port": port}
            try:
                Config(settings=settings, triggers=self.config.triggers, actions=self.config.actions,
                       path=self.config.path).save()
            except BaseException:
                await candidate.stop()
                raise
            previous, self.overlays = self.overlays, candidate
            self.config.settings = settings
            self.overlay_port_message = ""
            await previous.stop()
            self.log(f"Servidor de overlays en http://127.0.0.1:{port}/")
            return port

    async def save_overlay_preset(self, overlay_id: str, values: dict[str, str]) -> None:
        info = find_overlay(overlay_id)
        if info is None:
            raise ValueError("Ese overlay ya no existe.")
        checked = validate_overlay_values(info, values)
        existing = self.config.settings.get("overlay_presets", {})
        presets = dict(existing) if isinstance(existing, dict) else {}
        if checked:
            presets[overlay_id] = checked
        else:
            presets.pop(overlay_id, None)
        settings = {**self.config.settings, "overlay_presets": presets}
        Config(settings=settings, triggers=self.config.triggers, actions=self.config.actions,
               path=self.config.path).save()
        self.config.settings = settings
        if overlay_id == "multi-chat":
            await self.overlays.broadcast(overlay_id, {"channel": "chat-settings", "values": checked})

    def overlay_use_count(self, overlay_id: str) -> int:
        return sum(step.get("type") == "overlay_alert" and step.get("overlay") == overlay_id
                   for action in self.config.actions for step in action.steps)

    async def delete_user_overlay(self, overlay_id: str, confirmed_uses: int) -> None:
        info = find_overlay(overlay_id)
        root = user_overlays_dir().resolve()
        candidate = root / overlay_id
        if info is None or info.source != "user" or candidate.is_symlink() or info.path != candidate:
            raise ValueError("Solo puedes eliminar un overlay propio o importado.")
        if self.overlay_use_count(overlay_id) != confirmed_uses:
            raise ValueError("Cambió el número de acciones que lo usan. Confirma de nuevo.")
        raw = self.config.settings.get("overlay_presets", {})
        presets = dict(raw) if isinstance(raw, dict) else {}
        presets.pop(overlay_id, None)
        settings = {**self.config.settings, "overlay_presets": presets}
        actions = []
        for action in self.config.actions:
            steps = [step for step in action.steps
                     if not (step.get("type") == "overlay_alert" and step.get("overlay") == overlay_id)]
            actions.append(replace(action, steps=steps))
        stage = Path(tempfile.mkdtemp(prefix=".slb-delete-", dir=root))
        removed = stage / "overlay"
        try:
            candidate.rename(removed)
            try:
                Config(settings=settings, triggers=self.config.triggers, actions=actions, path=self.config.path).save()
            except BaseException:
                removed.rename(candidate)
                raise
            self.config.settings, self.config.actions = settings, actions
        finally:
            # Never destroy the staged overlay if a failed save could not be reversed.
            if candidate.exists() or self.config.settings is settings or not removed.exists():
                shutil.rmtree(stage, ignore_errors=True)
        await asyncio.gather(*(ws.close(drain=False) for ws, oid in list(self.overlays.clients.items())
                               if oid == overlay_id), return_exceptions=True)
        self.log(f"Overlay eliminado: {info.name} ({overlay_id})")

    async def preview_overlay(self, overlay_id: str) -> None:
        if self.port is None:
            raise ValueError("Asigna un puerto de overlays primero.")
        info = find_overlay(overlay_id)
        if info is None:
            raise ValueError("Ese overlay ya no existe.")
        kind = info.appearance.kind if info.appearance else None
        if overlay_id == "live-goal":
            await self.overlays.broadcast(overlay_id, {
                "channel": "goal-preview", "counts": {"gift": 3, "follow": 1},
            })
        elif overlay_id == "event-feed" or kind == "events":
            await self.overlays.forward_event(Event("tiktok", "gift", "viewer_demo",
                                                    {"gift_name": "Rose", "count": 3}))
        elif overlay_id == "multi-chat" or kind == "chat":
            for platform in CHAT_PLATFORMS:
                await self.overlays.forward_chat(Event(platform, "chat", "viewer_demo", {
                    "text": "Así se verá el chat en tu transmisión.", "simulated": True,
                }))
        else:
            await self.overlays.broadcast(overlay_id, {
                "channel": "alert", "overlay": overlay_id, "title": "viewer_demo envió Rose", "text": "x3",
                "variables": overlay_variables(sample_event("gift")),
            })

    # -- ciclo de vida -----------------------------------------------------

    def start(self, timeout: float = 10.0) -> None:
        self._thread = threading.Thread(target=self._run, name="slb-runtime", daemon=True)
        self._thread.start()
        if not self._ready.wait(timeout):
            raise RuntimeError("El runtime tardó demasiado en iniciar")
        if self._startup_error is not None:
            raise RuntimeError(str(self._startup_error)) from self._startup_error

    def stop(self) -> None:
        loop, thread = self.loop, self._thread
        if loop is not None and thread is not None and thread.is_alive():
            loop.call_soon_threadsafe(loop.stop)
            thread.join(timeout=5)

    def _run(self) -> None:
        loop = asyncio.new_event_loop()
        self.loop = loop
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._startup())
        except BaseException as exc:  # noqa: BLE001 - se informa al hilo principal
            self._startup_error = exc
            self._ready.set()
            loop.close()
            return
        self._ready.set()
        loop.run_forever()
        loop.run_until_complete(self._shutdown())
        loop.close()

    async def _startup(self) -> None:
        if self.editor_only:
            self.overlay_port_message = "Editor de perfil: no abre puertos ni transmite."
            return
        self.bus.subscribe(self._track_chat)
        self.bus.subscribe(self.chat_tts.on_event)
        self.bus.subscribe(self.engine.on_event)
        self.bus.subscribe(self._forward_overlay_event)
        port = self._port_override if self._port_override is not None else self.config.settings.get("overlay_port")
        if type(port) is int and 0 <= port <= 65535:
            try:
                await self.overlays.start(port)
                self.log(f"Servidor de overlays en http://127.0.0.1:{self.overlays.port}/")
            except OSError as exc:
                if exc.errno == errno.EADDRINUSE:
                    self.overlay_port_message = f"El puerto {port} está ocupado. Asigna otro puerto para activar los overlays."
                else:
                    self.overlay_port_message = f"No se pudo usar el puerto {port}. Asigna otro para activar los overlays."
        else:
            self.overlay_port_message = "Asigna un puerto para activar los overlays."
        if self.overlay_port_message:
            self.log(self.overlay_port_message)
        self._timer_task = asyncio.create_task(self.timers.run())
        if self.config.settings["obs"].get("autoconnect"):
            self.spawn(self.obs.start())

    async def _shutdown(self) -> None:
        await self.chat_tts.close()
        if self._timer_task is not None:
            self._timer_task.cancel()
            await asyncio.gather(self._timer_task, return_exceptions=True)
            self._timer_task = None
        tasks = list(self._background)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        for connector in self.connectors.values():
            await connector.stop()
        await self.overlays.stop()
