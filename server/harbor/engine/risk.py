"""Risk levels: clear, monitor, prepare, act, shelter, recover.

Escalation can skip levels. Before shelter, a fading threat steps down to monitor. Shelter ends only in
recover, once alerts have ended and sensors give the all-clear. Recover becomes clear after the restore.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class Level(StrEnum):
    clear = "clear"
    monitor = "monitor"
    prepare = "prepare"
    act = "act"
    shelter = "shelter"
    recover = "recover"


ORDER = [Level.clear, Level.monitor, Level.prepare, Level.act, Level.shelter]

MONITOR_P34 = 0.05
PREPARE_P34 = 0.20
ACT_P34 = 0.50
STAND_DOWN_P34 = 0.10  # hysteresis: drop out of prepare/act only well below the entry bar
SHELTER_ETA_HOURS = 12
SHELTER_WIND_MPH = 39

WATCHES = {"hurricane_watch", "tropical_storm_watch", "storm_surge_watch"}
WARNINGS = {"hurricane_warning", "tropical_storm_warning", "storm_surge_warning"}


@dataclass(frozen=True)
class RiskInputs:
    storm_active: bool = False  # a storm in the latest advisory could reach the ZIP
    p34: float = 0.0  # 5-day tropical-storm wind probability at the ZIP, 0..1
    in_cone: bool = False
    alerts: frozenset[str] = field(default_factory=frozenset)  # e.g. {"hurricane_warning"}
    ts_winds_eta_hours: float | None = None  # hours until tropical-storm winds, if forecast
    sustained_wind_mph: float | None = None  # strongest fresh sensor reading near the user
    sensor_flag: bool = False  # sensors near the user at watch/warning
    sensors_all_clear: bool = False  # recovery gate passed (pressure, surge, rivers)
    storm_passed: bool = False  # the track has already gone by the ZIP
    restore_done: bool = False  # the restore plan has finished


@dataclass(frozen=True)
class RiskDecision:
    level: Level
    reason: str
    changed: bool
    recovery_hold: bool = False


def _pct(p: float) -> str:
    return f"{round(p * 100)}%"


def _threat(x: RiskInputs) -> tuple[Level, str]:
    """The level the current inputs justify on their own, before history is considered."""
    warning = x.alerts & WARNINGS
    watch = x.alerts & WATCHES
    if warning and x.ts_winds_eta_hours is not None and x.ts_winds_eta_hours <= SHELTER_ETA_HOURS:
        return (
            Level.shelter,
            f"A {_alert_name(warning)} is in force and storm winds are due within {SHELTER_ETA_HOURS} hours.",
        )
    if (x.storm_active or x.alerts) and x.sustained_wind_mph is not None and x.sustained_wind_mph >= SHELTER_WIND_MPH:
        return Level.shelter, f"Sensors near you measure sustained winds of {round(x.sustained_wind_mph)} mph."
    if warning or watch:
        return Level.act, f"A {_alert_name(warning or watch)} is in force for your area."
    if x.storm_active and x.p34 >= ACT_P34:
        return Level.act, f"The chance of tropical-storm winds at your ZIP reached {_pct(x.p34)}."
    if x.storm_active and x.p34 >= PREPARE_P34:
        return Level.prepare, f"The chance of tropical-storm winds at your ZIP reached {_pct(x.p34)}."
    if x.storm_active and x.sensor_flag and (x.p34 >= MONITOR_P34 or x.in_cone):
        return Level.prepare, "Sensors near you show the storm's effects arriving."
    if x.storm_active and (x.p34 >= MONITOR_P34 or x.in_cone):
        return Level.monitor, f"A storm could reach your area (wind chance {_pct(x.p34)})."
    return Level.clear, "No storm threatens your ZIP."


def _alert_name(alerts: set[str]) -> str:
    worst = sorted(alerts, key=lambda a: ("warning" not in a, "hurricane" not in a))[0]
    return worst.replace("_", " ")


def _rank(level: Level) -> int:
    return ORDER.index(level)


def next_level(current: Level, x: RiskInputs) -> RiskDecision:
    def stay(reason: str, hold: bool = False) -> RiskDecision:
        return RiskDecision(current, reason, False, hold)

    def move(level: Level, reason: str) -> RiskDecision:
        return RiskDecision(level, reason, level != current)

    threat, why = _threat(x)
    alerts_over = not (x.alerts & (WATCHES | WARNINGS))

    if current == Level.recover:
        if threat == Level.shelter:
            return move(Level.shelter, why)
        if x.restore_done:
            return move(Level.clear, "The storm has passed and your money is back where it was.")
        return stay("The storm has passed. Harbor is putting your money back.")

    if current == Level.shelter:
        if alerts_over and not x.in_cone:
            if x.sensors_all_clear:
                return move(Level.recover, "Alerts have ended and nearby sensors show it's safe.")
            return stay(
                "Forecast alerts have ended, but nearby sensors haven't given the all-clear yet. "
                "Your cash stays in checking.",
                hold=True,
            )
        return stay(why if threat == Level.shelter else "The storm is still affecting your area.")

    if _rank(threat) > _rank(current):
        return move(threat, why)

    # Stand-down rules for prepare and act: only when the threat has clearly faded.
    if current in (Level.prepare, Level.act) and alerts_over and x.p34 < STAND_DOWN_P34:
        if current == Level.act and x.storm_passed:
            if x.sensors_all_clear:
                return move(Level.recover, "The storm has passed and nearby sensors show it's safe.")
            return stay("The storm has passed, but nearby sensors haven't given the all-clear yet.", hold=True)
        if x.storm_active and (x.p34 >= MONITOR_P34 or x.in_cone):
            return move(Level.monitor, f"The storm turned away (wind chance down to {_pct(x.p34)}).")
        return move(Level.monitor if x.storm_active else Level.clear, "The storm turned away from your area.")

    if current == Level.monitor and threat == Level.clear:
        return move(Level.clear, why)

    return stay(why if threat == current else _holding_reason(current))


def _holding_reason(level: Level) -> str:
    return {
        Level.prepare: "Harbor is keeping your plan ready while the forecast settles.",
        Level.act: "Harbor is keeping your plan running while the forecast settles.",
    }.get(level, "No change.")
