from datetime import datetime, timedelta, timezone

import pytest

from harbor.clock import DemoClock, FrozenClock, RealClock, iso, utc
from tests.conftest import REPLAY_START, Timer


def test_iso_is_utc_with_z():
    assert iso(datetime(2024, 10, 6, 15, 0, 0, 123456, tzinfo=timezone.utc)) == "2024-10-06T15:00:00Z"
    assert iso(datetime(2024, 10, 6, 11, 0, tzinfo=timezone(timedelta(hours=-4)))) == "2024-10-06T15:00:00Z"
    assert iso(None) is None
    assert utc(datetime(2024, 1, 1)).tzinfo is timezone.utc


def test_real_clock_is_aware_utc():
    now = RealClock().now()
    assert now.tzinfo is not None and now.utcoffset() == timedelta(0)


def test_demo_clock_waits_paused_at_replay_start():
    timer = Timer()
    clock = DemoClock(REPLAY_START, speed=1800, real=timer)
    timer.t += 100
    assert clock.now() == REPLAY_START
    assert clock.state() == {
        "running": False,
        "storm": None,
        "now": "2024-10-06T03:00:00Z",
        "speed": 1800,
        "paused_reason": None,
    }


def test_demo_clock_runs_at_speed_and_pauses():
    timer = Timer()
    clock = DemoClock(REPLAY_START, speed=1800, real=timer)
    clock.start("milton-2024")
    timer.t += 2  # 2 real seconds × 1800 = 1 storm hour
    assert clock.now() == REPLAY_START + timedelta(hours=1)
    assert clock.running

    clock.pause("awaiting_approval")
    timer.t += 60
    assert clock.now() == REPLAY_START + timedelta(hours=1)
    assert clock.state()["paused_reason"] == "awaiting_approval"
    assert not clock.running

    clock.resume()
    timer.t += 4
    assert clock.now() == REPLAY_START + timedelta(hours=3)


def test_demo_clock_speed_change_does_not_jump():
    timer = Timer()
    clock = DemoClock(REPLAY_START, speed=3600, real=timer)
    clock.start("milton-2024")
    timer.t += 1
    clock.set_speed(60)
    assert clock.now() == REPLAY_START + timedelta(hours=1)
    timer.t += 60
    assert clock.now() == REPLAY_START + timedelta(hours=2)
    with pytest.raises(ValueError):
        clock.set_speed(0)


def test_demo_clock_advance_and_reset():
    timer = Timer()
    clock = DemoClock(REPLAY_START, real=timer)
    assert clock.advance(timedelta(hours=6)) == REPLAY_START + timedelta(hours=6)
    assert clock.now() == REPLAY_START + timedelta(hours=6)
    with pytest.raises(ValueError):
        clock.advance(timedelta(hours=-1))
    clock.start("milton-2024", speed=900)
    clock.reset()
    assert clock.now() == REPLAY_START and clock.storm is None and clock.speed == 1800


def test_frozen_clock():
    clock = FrozenClock(REPLAY_START)
    clock.tick(hours=6)
    assert clock.now() == REPLAY_START + timedelta(hours=6)


def test_server_time_header_follows_demo_clock(client, clock, timer):
    assert client.get("/health").headers["X-Server-Time"] == "2024-10-06T03:00:00Z"
    clock.advance(timedelta(hours=12))
    assert client.get("/health").headers["X-Server-Time"] == "2024-10-06T15:00:00Z"
    assert client.get("/api/v1/demo/clock").json()["now"] == "2024-10-06T15:00:00Z"
