"""Scheduler tick: read the forecast at now, update each user's risk level and record what changed.

Catches up across clock jumps by evaluating every change point since the last tick.
"""

from __future__ import annotations

import threading
from datetime import datetime, timedelta
from functools import lru_cache

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlmodel import Session, select

from harbor.clock import iso
from harbor.engine.risk import ORDER, WARNINGS, WATCHES, Level, RiskDecision, RiskInputs, next_level
from harbor.events import latest, record
from harbor.models import User
from harbor.sources.forecast import Exposure, ReplaySource, load_replay
from harbor.sources.sensors import DATA as SENSOR_DATA
from harbor.sources.sensors import SensorSource

STORM_ALERTS = WATCHES | WARNINGS | {"extreme_wind_warning"}
MAX_CATCH_UP = timedelta(days=21)  # the Milton replay plus its sensor aftermath is ~15 days


def forecast_source(app) -> ReplaySource | None:
    """The replay the demo clock is playing, or None (live mode, or before /demo/start)."""
    storm = getattr(app.state.clock, "storm", None)
    if storm is None:
        return None
    return load_replay(app.state.settings.replay_dir, storm)


@lru_cache
def sensor_source(storm: str) -> SensorSource | None:
    """Recorded sensors for a replayed storm (data/sensors/<storm>/), or None if none were recorded."""
    return SensorSource(storm) if (SENSOR_DATA / storm).is_dir() else None


def sensor_facts(source: ReplaySource | None, lat: float, lon: float, now: datetime) -> dict:
    sensors = sensor_source(source.root.name) if source else None
    if sensors is None:
        return {"sensor_flag": False, "sustained_wind_mph": None, "sensors_all_clear": True, "all_clear_reason": None}
    return sensors.risk_facts(now, lat, lon)


def risk_inputs(
    source: ReplaySource | None, lat: float, lon: float, zip_code: str | None, now: datetime, restore_done: bool = False
) -> tuple[RiskInputs, Exposure]:
    """Build the risk engine's inputs for one point from the forecast and sensors at `now`."""
    exp = source.exposure(lat, lon, zip_code, now) if source else Exposure(None)
    alerts = exp.alert_types
    eta_hours = (exp.eta - now) / timedelta(hours=1) if exp.eta else None
    sensors = sensor_facts(source, lat, lon, now)
    inputs = RiskInputs(
        storm_active=exp.advisory is not None,
        p34=exp.p34,
        in_cone=exp.in_cone,
        alerts=alerts,
        ts_winds_eta_hours=eta_hours,
        # Sensors: tide gauge, river gauge and buoy readings near the user (see sources/sensors.py).
        # The recovery gate also needs the storm alerts to be over.
        sustained_wind_mph=sensors["sustained_wind_mph"],
        sensor_flag=sensors["sensor_flag"],
        sensors_all_clear=sensors["sensors_all_clear"] and not (alerts & STORM_ALERTS),
        storm_passed=source.storm_passed(lat, lon, now) if source else False,
        restore_done=restore_done,  # the restore plan finished: recover -> clear
    )
    return inputs, exp


def evaluate(
    source: ReplaySource | None,
    level: Level,
    lat: float,
    lon: float,
    zip_code: str | None,
    now: datetime,
    restore_done: bool = False,
) -> tuple[RiskDecision, Exposure]:
    inputs, exp = risk_inputs(source, lat, lon, zip_code, now, restore_done)
    return next_level(level, inputs), exp


def steps_between(source: ReplaySource | None, after: datetime | None, until: datetime) -> list[datetime]:
    """The moments to evaluate in (after, until]: input boundaries and whole hours, then `until`."""
    if source is None or after is None or after >= until:
        return [until]
    after = max(after, until - MAX_CATCH_UP)
    times = {t for t in source.boundaries(after, until) if t < until}
    hour = after.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    while hour < until:
        times.add(hour)
        hour += timedelta(hours=1)
    return [*sorted(times), until]


def _verb(old: Level, new: Level) -> str:
    if new == Level.recover:
        return "moved to"
    if old == Level.recover:
        return "raised to" if new == Level.shelter else "lowered to"
    return "raised to" if ORDER.index(new) > ORDER.index(old) else "lowered to"


def _apply(app, session: Session, source: ReplaySource | None, user: User, now: datetime) -> int:
    """Evaluate one user at `now`; write events. Returns how many events were written."""
    from harbor import planning  # planning imports context, which imports this module

    old = Level(user.risk_level)
    done = old == Level.recover and planning.restore_done(session, user)
    decision, exp = evaluate(source, old, user.lat, user.lon, user.zip, now, done)
    written = 0
    adv = exp.advisory
    if adv is not None and source is not None:
        last = latest(session, user.id, ("advisory_issued",))
        seen = last.data if last else {}
        if seen.get("storm_id") != source.storm_id or seen.get("advisory") != adv.adv:
            kind = adv.classification.replace("_", " ").title()
            record(
                session,
                user.id,
                now,
                "advisory_issued",
                f"NHC advisory {adv.advisory_number} for {kind} {source.name}.",
                {
                    "storm_id": source.storm_id,
                    "advisory": adv.adv,
                    "advisory_number": adv.advisory_number,
                    "issued_at": iso(adv.issued_at),
                    "headline": adv.headline,
                    "ts_wind_probability_5day": round(exp.p34, 2),
                    "in_forecast_cone": exp.in_cone,
                },
            )
            written += 1
    if decision.changed:
        new = decision.level
        record(
            session,
            user.id,
            now,
            "risk_changed",
            f"Risk {_verb(old, new)} {new.value.upper()}: {decision.reason}",
            {
                "from": old.value,
                "to": new.value,
                "reason": decision.reason,
                "storm_id": source.storm_id if source and adv else None,
                "advisory": adv.advisory_number if adv else None,
                "ts_wind_probability_5day": round(exp.p34, 2),
                "in_forecast_cone": exp.in_cone,
                "alerts": sorted(exp.alert_types),
            },
        )
        user.risk_level = new.value
        user.risk_changed_at = now
        written += 1
        session.flush()
        planning.on_level_change(
            app,
            session,
            user,
            old.value,
            new.value,
            now,
            source.storm_id if source else None,
            source.name if source else None,
        )
    elif decision.recovery_hold:
        last = latest(session, user.id, ("risk_changed", "recovery_hold"))
        if last is None or last.type != "recovery_hold":
            record(
                session,
                user.id,
                now,
                "recovery_hold",
                f"Recovery hold: {decision.reason}",
                {"level": old.value, "reason": decision.reason},
            )
            written += 1
    user.risk_reason = decision.reason
    session.add(user)
    return written


def tick(app, now: datetime | None = None) -> int:
    """Catch every user up to `now` (default: the clock). Returns how many events were written."""
    lock: threading.Lock = app.state.tick_lock
    with lock:
        now = now or app.state.clock.now()
        source = forecast_source(app)
        cursor = app.state.tick_cursor
        written = 0
        with Session(app.state.engine) as session:
            users = session.exec(select(User)).all()
            for t in steps_between(source, cursor, now):
                for user in users:
                    written += _apply(app, session, source, user, t)
                session.flush()  # later steps see this step's events
            session.commit()
        app.state.tick_cursor = now
        return written


def reset_cursor(app) -> None:
    """After the clock jumps back (demo start or reset), start catching up from the new time."""
    with app.state.tick_lock:
        app.state.tick_cursor = None


async def _scheduled_catch_up(app) -> None:
    from harbor.executor import catch_up

    await catch_up(app, app.state.clock.now())


def start_scheduler(app) -> AsyncIOScheduler:
    settings = app.state.settings
    seconds = settings.tick_seconds or (2 if settings.harbor_mode == "demo" else 60)
    sched = AsyncIOScheduler(timezone="UTC")
    # Risk ticks and money moves share one job (interleaved in time order by executor.catch_up).
    sched.add_job(
        _scheduled_catch_up, "interval", seconds=seconds, args=[app], id="tick", max_instances=1, coalesce=True
    )
    sched.start()
    return sched
