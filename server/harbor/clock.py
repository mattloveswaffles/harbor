"""RealClock (live) and DemoClock (replays). Nothing calls datetime.now() directly."""

import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Protocol

from fastapi import Request


def utc(dt: datetime) -> datetime:
    """Treat naive datetimes as UTC and convert aware ones to UTC."""
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


def parse_time(s: str) -> datetime:
    """ISO 8601 (Z or an offset) -> aware UTC."""
    return utc(datetime.fromisoformat(s.replace("Z", "+00:00")))


def iso(dt: datetime | None) -> str | None:
    """ISO 8601 UTC with a Z, to the second: 2024-10-06T15:00:00Z."""
    if dt is None:
        return None
    return utc(dt).isoformat(timespec="seconds").replace("+00:00", "Z")


class Clock(Protocol):
    def now(self) -> datetime: ...  # always tz-aware UTC


class RealClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class DemoClock:
    """Storm time = anchor + real time elapsed × speed, frozen while paused.

    Before a scenario starts (and after a reset) the clock is idle: `idle()` gives the time, real time in the app,
    so Harbor runs normally until a storm is replayed. Without `idle` it waits at the replay start (tests)."""

    def __init__(
        self,
        start: datetime,
        speed: float = 1800,
        real: Callable[[], float] = time.monotonic,
        idle: Callable[[], datetime] | None = None,
    ):
        self._real = real
        self._idle = idle
        self._lock = threading.Lock()
        self.default_start = utc(start)
        self.default_speed = speed
        self.reset()

    def reset(self) -> None:
        """Back to idle: no scenario, paused at the replay start."""
        with self._lock:
            self.storm: str | None = None
            self.speed = self.default_speed
            self.paused = True
            self.paused_reason: str | None = None
            self._anchor_sim = self.default_start
            self._anchor_real = self._real()

    def now(self) -> datetime:
        with self._lock:
            return self._now()

    def _now(self) -> datetime:
        if self.storm is None and self._idle is not None:
            return self._idle()
        if self.paused:
            return self._anchor_sim
        elapsed = (self._real() - self._anchor_real) * self.speed
        return self._anchor_sim + timedelta(seconds=elapsed)

    def _rebase(self) -> None:
        # Fold elapsed time into the anchor so a speed or pause change doesn't jump the clock.
        self._anchor_sim = self._now()
        self._anchor_real = self._real()

    def start(self, storm: str, at: datetime | None = None, speed: float | None = None) -> None:
        with self._lock:
            self.storm = storm
            self.speed = speed if speed is not None else self.default_speed
            self._anchor_sim = utc(at) if at else self.default_start
            self._anchor_real = self._real()
            self.paused = False
            self.paused_reason = None

    def pause(self, reason: str | None = None) -> None:
        with self._lock:
            self._rebase()
            self.paused = True
            self.paused_reason = reason

    def resume(self) -> None:
        with self._lock:
            self._rebase()
            self.paused = False
            self.paused_reason = None

    def advance(self, delta: timedelta) -> datetime:
        if delta < timedelta(0):
            raise ValueError("the demo clock only moves forward")
        with self._lock:
            self._rebase()
            self._anchor_sim += delta
            return self._anchor_sim

    @property
    def running(self) -> bool:
        return self.storm is not None and not self.paused

    def state(self) -> dict:
        with self._lock:
            return {
                "running": self.running,
                "storm": self.storm,
                "now": iso(self._now()),
                "speed": self.speed,
                "paused_reason": self.paused_reason,
            }


def get_clock(request: Request) -> Clock:
    return request.app.state.clock
