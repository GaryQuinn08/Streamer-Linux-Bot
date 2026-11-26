"""Private, bounded, thread-safe telemetry for the desktop session."""
from __future__ import annotations

import math
import re
import threading
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation

PLATFORMS = {"twitch": "Twitch", "tiktok": "TikTok", "youtube": "YouTube", "kick": "Kick"}
KINDS = {"chat", "follow", "sub", "gift", "donation", "bits", "points", "like", "share", "raid"}


def number(value) -> int | None:
    if isinstance(value, str) and re.fullmatch(r"[0-9]{1,15}", value):
        value = int(value)
    return value if type(value) is int and 0 <= value <= 10**15 else None


def timestamp(value) -> float | None:
    if not isinstance(value, str) or len(value) > 40:
        return None
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return stamp.timestamp() if stamp.tzinfo else None
    except (ValueError, OverflowError, OSError):
        return None


def _label(value) -> str:
    return " ".join(value.split())[:160] if isinstance(value, str) else ""


@dataclass
class _Platform:
    totals: Counter = field(default_factory=Counter)
    currencies: Counter = field(default_factory=Counter)
    last_event: float | None = None
    live: bool | None = None
    live_at: float | None = None
    live_ttl: int | None = None
    viewers: int | None = None
    viewer_at: float | None = None
    peak: int | None = None
    title: str = ""
    identity: str = ""
    started_at: float | None = None
    session_id: str = ""
    note: str = ""
    event_order: float = 0


@dataclass(frozen=True)
class PlatformSnapshot:
    platform: str
    totals: tuple[tuple[str, int], ...]
    currencies: tuple[tuple[str, Decimal], ...]
    last_event: float | None
    live: bool | None
    live_at: float | None
    viewers: int | None
    peak: int | None
    title: str
    identity: str
    started_at: float | None
    note: str


class LiveDashboard:
    def __init__(self):
        self._lock = threading.Lock()
        self._items = {key: _Platform() for key in (*PLATFORMS, "obs")}

    def reset_connection(self, key):
        """Keep app-session counts, but never inherit an old channel's live status."""
        with self._lock:
            row = self._items[key]
            row.live = row.viewers = row.live_at = row.viewer_at = row.peak = row.started_at = None
            row.last_event = None
            row.title = row.identity = row.session_id = row.note = ""
            row.event_order = 0

    def invalidate(self, key, *, keep_offline=False):
        with self._lock:
            row = self._items[key]
            if not (keep_offline and row.live is False):
                row.live = row.viewers = row.live_at = row.viewer_at = row.started_at = None
            row.note = ""

    def signal(self, key, live, *, viewers=None, title=None, identity=None, started_at=None,
               session_id=None, keep_viewers=False, ttl=140, note=None, order=None):
        now = time.time()
        with self._lock:
            row = self._items[key]
            if order is not None and order < row.event_order:
                return
            if order is not None:
                row.event_order = order
            if live is True and (row.live is False or (session_id and session_id != row.session_id)):
                row.viewers = row.viewer_at = row.peak = row.started_at = None
                row.title = ""
            if session_id:
                row.session_id = str(session_id)[:100]
            row.live, row.live_at, row.live_ttl = live, now, ttl
            if note is not None:
                row.note = note
            if title is not None:
                row.title = _label(title)
            if identity is not None:
                row.identity = _label(identity)
            if started_at is not None:
                row.started_at = started_at
            if live is False:
                row.viewers = row.viewer_at = row.started_at = None
            elif viewers is not None or not keep_viewers:
                row.viewers = number(viewers)
                row.viewer_at = now if row.viewers is not None else None
                if row.viewers is not None:
                    row.peak = row.viewers if row.peak is None else max(row.peak, row.viewers)

    def unavailable(self, key, note, *, clear_viewers=False):
        with self._lock:
            row = self._items[key]
            row.note = note
            if clear_viewers:
                row.viewers = row.viewer_at = None

    def activity(self, key):
        with self._lock:
            self._items[key].last_event = time.time()

    def event(self, event):
        if event.platform not in PLATFORMS or event.type not in KINDS or event.data.get("simulated"):
            return
        kind, data = event.type, event.data
        with self._lock:
            row = self._items[event.platform]
            row.last_event = time.time()
            row.totals[kind] += 1
            if kind in {"gift", "like"}:
                row.totals[kind + "_units"] += number(data.get("count")) or 1
            if kind in {"bits", "gift"}:
                units = number(data.get("diamonds" if kind == "gift" and event.platform == "tiktok" else "value"))
                if units is not None:
                    row.totals[kind + "_value"] += units
            if kind == "donation":
                currency, amount = data.get("currency"), data.get("amount")
                if isinstance(currency, str) and re.fullmatch("[A-Z]{3}", currency) and (
                    isinstance(amount, (int, str)) and not isinstance(amount, bool) and len(str(amount)) <= 24
                ):
                    try:
                        amount = Decimal(amount)
                        if amount.is_finite() and 0 <= amount <= 10**12 and amount.as_tuple().exponent >= -6:
                            row.currencies[currency] += amount
                    except InvalidOperation:
                        pass

    def snapshot(self):
        now = time.time()
        with self._lock:
            snapshots = {}
            for key, item in self._items.items():
                fresh = item.live_at is not None and (item.live_ttl is None or now - item.live_at <= item.live_ttl)
                live = item.live if fresh else None
                viewers = (item.viewers if live is True and item.viewer_at is not None and
                           now - item.viewer_at <= 150 else None)
                snapshots[key] = PlatformSnapshot(
                    key, tuple(sorted(item.totals.items())), tuple(sorted(item.currencies.items())),
                    item.last_event, live, item.live_at, viewers, item.peak, item.title if fresh else "",
                    item.identity, item.started_at if live is True and
                    isinstance(item.started_at, (int, float)) and math.isfinite(item.started_at) else None, item.note,
                )
            return snapshots
