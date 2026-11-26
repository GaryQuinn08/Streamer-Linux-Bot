"""Colas de acciones en memoria. Solo el bucle del runtime modifica trabajos."""
from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, replace
from itertools import count

from .actions import run_action
from .config import Action
from .events import Event

log = logging.getLogger("slb.action_queue")
MAX_PENDING = 128
MAX_ACTIVE = 16
ACTIVE_STATES = ("En espera", "En curso")


@dataclass(frozen=True)
class ActionRun:
    id: int
    at: float
    action: str
    origin: str
    platform: str
    event: str
    queue: str = ""
    state: str = "En espera"
    failures: int = 0
    duration_ms: int | None = None


@dataclass
class _Job:
    run: ActionRun
    task: asyncio.Task
    queue_key: str
    started: float | None = None


class ActionQueue:
    def __init__(self, runtime):
        self._runtime = runtime
        self._ids = count(1)
        self._jobs: dict[int, _Job] = {}
        self._active = 0
        self._busy: set[str] = set()
        self._history: deque[ActionRun] = deque(maxlen=300)
        self._lock = threading.Lock()  # instantánea para Qt
        self._changed = asyncio.Event()
        self._paused = False

    def snapshot(self):
        with self._lock:
            return tuple(job.run for job in self._jobs.values()) + tuple(self._history)

    @property
    def paused(self):
        with self._lock:
            return self._paused

    def set_paused(self, paused: bool):
        with self._lock:
            self._paused = bool(paused)
        self._changed.set()

    def cancel(self, ident: int) -> bool:
        job = self._jobs.get(ident)
        if job is None or job.task is asyncio.current_task() or job.task.cancelling():
            return False
        job.task.cancel()
        return True

    def _eligible(self, job: _Job) -> bool:
        if self._paused or self._active >= MAX_ACTIVE or job.queue_key in self._busy:
            return False
        for earlier in self._jobs.values():
            if earlier is job:
                return True
            if earlier.started is None and (
                not earlier.queue_key or earlier.queue_key not in self._busy
            ):
                return False
        return False

    async def execute(self, action: Action, event: Event, origin: str):
        ident = next(self._ids)
        run = ActionRun(ident, time.time(), action.name, origin, event.platform, event.type, action.queue)
        task = asyncio.current_task()
        job = _Job(run, task, action.queue.casefold())
        with self._lock:
            if len(self._jobs) - self._active >= MAX_PENDING:
                result = replace(run, state="Descartada: cola llena")
                self._history.append(result)
                return result
            self._jobs[ident] = job
        state, failures = "Cancelada", 0
        try:
            while not self._eligible(job):
                self._changed.clear()
                await self._changed.wait()
            job.started = time.monotonic()
            self._active += 1
            if job.queue_key:
                self._busy.add(job.queue_key)
            with self._lock:
                job.run = replace(run, state="En curso")
            # Otro carril libre puede empezar sin esperar a que este termine.
            self._changed.set()
            failures = await run_action(self._runtime, action, event)
            state = "Con errores" if failures else "Completada"
        except asyncio.CancelledError:
            raise
        except Exception:
            state, failures = "Con errores", 1
            log.exception("Error inesperado al ejecutar una acción")
        finally:
            elapsed = None if job.started is None else int((time.monotonic() - job.started) * 1000)
            if job.started is not None:
                self._active -= 1
                self._busy.discard(job.queue_key)
            result = replace(run, state=state, failures=failures, duration_ms=elapsed)
            with self._lock:
                self._jobs.pop(ident, None)
                self._history.append(result)
            self._changed.set()
        return result
