"""Runtime: el núcleo asíncrono que vive en un hilo propio.

La interfaz Qt corre en el hilo principal; todo lo demás (bus de eventos,
motor de triggers, servidor de overlays, conectores) corre en un bucle asyncio
en un hilo aparte. La interfaz se comunica con él mediante `submit()` / `emit()`
y recibe el registro por el callback `on_log` (que debe ser seguro entre hilos,
p. ej. una señal de Qt).
"""
from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections import deque
from typing import Any, Callable, Coroutine

from .connectors.base import Connector
from .connectors.obs import ObsConnector
from .connectors.platforms import KickConnector, TiktokConnector, TwitchConnector, YoutubeConnector
from .core.config import Config
from .core.engine import Engine
from .core.events import Event, EventBus
from .overlay_server import OverlayServer

log = logging.getLogger("slb.runtime")


class Runtime:
    def __init__(
        self,
        on_log: Callable[[str], None] | None = None,
        config: Config | None = None,
        port: int | None = None,
    ) -> None:
        self.config = config or Config.load()
        self._on_log = on_log or (lambda _msg: None)
        self._port_override = port
        self.log_history: deque[str] = deque(maxlen=500)

        self.loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._startup_error: BaseException | None = None
        self._background: set[asyncio.Task[Any]] = set()

        self.bus = EventBus()
        self.engine = Engine(self)
        self.overlays = OverlayServer(self)
        self.obs = ObsConnector(self)
        self.connectors: dict[str, Connector] = {
            "obs": self.obs,
            "twitch": TwitchConnector(self),
            "youtube": YoutubeConnector(self),
            "kick": KickConnector(self),
            "tiktok": TiktokConnector(self),
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

    def spawn(self, coro: Coroutine[Any, Any, Any]) -> None:
        """Lanza una tarea en segundo plano (solo desde el hilo del bucle)."""
        task = asyncio.ensure_future(coro)
        self._background.add(task)
        task.add_done_callback(self._background.discard)

    def submit(self, coro: Coroutine[Any, Any, Any]):
        """Ejecuta una corrutina en el bucle desde cualquier hilo."""
        if self.loop is None:
            raise RuntimeError("El runtime no está iniciado")
        return asyncio.run_coroutine_threadsafe(coro, self.loop)

    def emit(self, ev: Event) -> None:
        self.submit(self.bus.publish(ev))

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
        self.bus.subscribe(self.engine.on_event)
        self.bus.subscribe(self.overlays.forward_event)
        port = self._port_override if self._port_override is not None else int(self.config.settings["overlay_port"])
        await self.overlays.start(port)
        self.log(f"Servidor de overlays en http://127.0.0.1:{self.overlays.port}/")
        if self.config.settings["obs"].get("autoconnect"):
            self.spawn(self.obs.start())

    async def _shutdown(self) -> None:
        for task in list(self._background):
            task.cancel()
        for connector in self.connectors.values():
            await connector.stop()
        await self.overlays.stop()
