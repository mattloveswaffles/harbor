"""One injectable clock: RealClock for live mode, DemoClock for storm replays (speed, pause, advance).

Nothing in Harbor calls datetime.now() directly. Routes get the clock with Depends(get_clock), and
services take `now` as an argument.
"""

import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Callable, Protocol

from fastapi import Request

UTC = timezone.utc


def utc(dt: datetime) -> datetime:
    """Treat naive datetimes as UTC and convert aware ones to UTC."""
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


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

    def state(self) -> dict:
        return {"running": True, "storm": None, "now": iso(self.now()), "speed": 1, "paused_reason": None}


class DemoClock:
    """Storm time = anchor_sim + (real time since anchor_real) × speed, frozen while paused.

    Before a replay starts the clock sits paused at the replay start, so every demo timestamp
    stays in October 2024. `real` is injectable so tests never sleep.
    """

    def __init__(
        self,
        start: datetime,
        speed: float = 1800,
        real: Callable[[], float] = time.monotonic,
    ):
        self._real = real
        self._lock = threading.Lock()
        self.default_start = utc(start)
        self.default_speed = speed
        self.reset()

    def reset(self) -> None:
        """Back to 'not started': paused at the replay start, no storm."""
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

    def set_speed(self, speed: float) -> None:
        if speed <= 0:
            raise ValueError("speed must be positive")
        with self._lock:
            self._rebase()
            self.speed = speed

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

    def set(self, at: datetime) -> None:
        with self._lock:
            self._anchor_sim = utc(at)
            self._anchor_real = self._real()

    @property
    def running(self) -> bool:
        return self.storm is not None and not self.paused

    def state(self) -> dict:
        with self._lock:
            return {
                "running": self.storm is not None and not self.paused,
                "storm": self.storm,
                "now": iso(self._now()),
                "speed": self.speed,
                "paused_reason": self.paused_reason,
            }


class FrozenClock:
    """For tests: time only moves when the test says so."""

    def __init__(self, at: datetime):
        self._now = utc(at)

    def now(self) -> datetime:
        return self._now

    def set(self, at: datetime) -> None:
        self._now = utc(at)

    def tick(self, **kwargs) -> datetime:
        self._now += timedelta(**kwargs)
        return self._now

    def state(self) -> dict:
        return {"running": False, "storm": None, "now": iso(self._now), "speed": 0, "paused_reason": None}


def get_clock(request: Request) -> Clock:
    return request.app.state.clock
