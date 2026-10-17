"""CO-OPS tide gauges, USGS river gauges and NDBC buoys: readings, trends and normal/watch/warning/stale status.

`SensorSource` serves recorded readings (demo) filtered by the clock, so the replay only ever
sees the past. Everything that judges safety is a pure function of those readings:

- `status_of` turns one station's latest reading and recent trend into normal/watch/warning
  with a plain-English reason. Readings older than the station's staleness limit are `stale`.
- `sensor_flag` is true when sensors near the user show the storm's effects arriving.
- `max_sustained_wind_mph` feeds the shelter rule.
- `recovery_gate` is the all-clear for moving money back: pressure recovered, surge gone for
  3 hours, rivers out of major flood and falling. Stale or missing data never counts as clear.

Thresholds live in the constants below and are tuned against the Milton recording.
"""

from __future__ import annotations

import json
import math
from bisect import bisect_right
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).resolve().parents[2] / "data" / "sensors"

# Staleness limits: a reading older than this is not trusted.
STALE_AFTER = {"noaa_tide": timedelta(minutes=30), "usgs_gauge": timedelta(hours=2), "noaa_buoy": timedelta(hours=2)}

SURGE_WATCH_FT, SURGE_WARNING_FT = 1.0, 3.0
REVERSE_SURGE_WATCH_FT, REVERSE_SURGE_WARNING_FT = -1.5, -2.0
WIND_WATCH_MPH, WIND_WARNING_MPH = 25.0, 39.0
PRESSURE_DROP_WATCH_MB, PRESSURE_DROP_WARNING_MB = 3.0, 6.0  # fall over 3 hours
PRESSURE_LOW_WARNING_MB = 990.0
WAVES_WATCH_FT, WAVES_WARNING_FT = 8.0, 12.0
RIVER_FALLING_HOURS = 6
SURGE_CLEAR_HOURS = 3
PRESSURE_RECOVERED_MB = 1005.0

# How close a sensor must be to count. Wind and the all-clear are about the user's own area; the
# early-warning flag may use offshore sensors further out, which see the storm first.
LOCAL_RADIUS_MI = 50
FLAG_RADIUS_MI = 150

RANK = {"normal": 0, "watch": 1, "warning": 2}


@dataclass(frozen=True)
class Station:
    id: str
    source: str
    name: str
    lat: float
    lon: float
    attribution: str
    flood_stages_ft: dict[str, float] = field(default_factory=dict)


@dataclass
class Reading:
    station: Station
    observed_at: datetime | None
    readings: dict
    status: str
    status_reason: str
    stale: bool
    distance_miles: float | None = None
    flood_category: str | None = None
    crest_rising: bool | None = None

    def to_api(self) -> dict:
        out = {
            "id": self.station.id, "source": self.station.source, "name": self.station.name,
            "location": {"lat": self.station.lat, "lon": self.station.lon},
            "distance_miles": self.distance_miles,
            "observed_at": None if self.observed_at is None else self.observed_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "readings": self.readings, "status": "stale" if self.stale else self.status,
            "status_reason": self.status_reason, "stale": self.stale, "attribution": self.station.attribution,
        }
        if self.station.source == "usgs_gauge":
            out.update(flood_stages=self.station.flood_stages_ft, flood_category=self.flood_category,
                       crest_rising=self.crest_rising)
        return out


def miles_between(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 3958.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _parse(t: str) -> datetime:
    return datetime.fromisoformat(t.replace("Z", "+00:00"))


class Series:
    """One station's rows, sorted by time, with lookups that never peek past `now`."""

    def __init__(self, station: Station, rows: list[dict]):
        self.station = station
        self.rows = rows
        self.times = [_parse(r["t"]) for r in rows]

    def at(self, now: datetime) -> tuple[datetime, dict] | None:
        i = bisect_right(self.times, now)
        return (self.times[i - 1], self.rows[i - 1]) if i else None

    def value_at(self, now: datetime, key: str, within: timedelta = timedelta(hours=1)) -> float | None:
        """Latest non-null value of `key` at or before `now`, no older than `within`."""
        i = bisect_right(self.times, now) - 1
        while i >= 0 and now - self.times[i] <= within:
            v = self.rows[i].get(key)
            if v is not None:
                return v
            i -= 1
        return None

    def window(self, start: datetime, end: datetime) -> list[tuple[datetime, dict]]:
        lo, hi = bisect_right(self.times, start), bisect_right(self.times, end)
        return list(zip(self.times[lo:hi], self.rows[lo:hi]))


# --- Status rules ------------------------------------------------------------------------------

def _worst(parts: list[tuple[str, str]]) -> tuple[str, str]:
    if not parts:
        return "normal", "Readings are normal."
    return max(parts, key=lambda p: RANK[p[0]])


def _pressure_parts(s: Series, now: datetime, row: dict) -> list[tuple[str, str]]:
    parts = []
    p = row.get("pressure_mb")
    before = s.value_at(now - timedelta(hours=3), "pressure_mb")
    if p is not None and before is not None:
        drop = round(before - p, 1)
        row["pressure_change_3h_mb"] = -drop
        if drop >= PRESSURE_DROP_WARNING_MB or p < PRESSURE_LOW_WARNING_MB:
            parts.append(("warning", f"Air pressure is {p:.0f} mb and fell {drop} mb in 3 hours: the storm is close."))
        elif drop >= PRESSURE_DROP_WATCH_MB:
            parts.append(("watch", f"Air pressure fell {drop} mb in 3 hours."))
    elif p is not None and p < PRESSURE_LOW_WARNING_MB:
        parts.append(("warning", f"Air pressure is very low ({p:.0f} mb)."))
    return parts


def _wind_parts(row: dict) -> list[tuple[str, str]]:
    w = row.get("wind_speed_mph")
    if w is None:
        return []
    if w >= WIND_WARNING_MPH:
        return [("warning", f"Sustained winds of {w:.0f} mph: tropical-storm force.")]
    if w >= WIND_WATCH_MPH:
        return [("watch", f"Sustained winds of {w:.0f} mph.")]
    return []


def status_of(s: Series, now: datetime) -> Reading:
    st = s.station
    latest = s.at(now)
    if latest is None:
        return Reading(st, None, {}, "normal", "No readings yet.", stale=True)
    observed, raw = latest
    row = {k: v for k, v in raw.items() if k != "t"}
    stale = now - observed > STALE_AFTER.get(st.source, timedelta(hours=1))
    parts: list[tuple[str, str]] = []
    category = rising = None

    if st.source == "noaa_tide":
        surge = row.get("surge_ft")
        if surge is not None:
            if surge >= SURGE_WARNING_FT:
                parts.append(("warning", f"Water is {surge:.1f} ft above the predicted tide: dangerous storm surge."))
            elif surge >= SURGE_WATCH_FT:
                parts.append(("watch", f"Water is {surge:.1f} ft above the predicted tide."))
            elif surge <= REVERSE_SURGE_WARNING_FT:
                parts.append(("warning", f"Water is {abs(surge):.1f} ft below the predicted tide (reverse surge). "
                                         "Stay off the exposed bay floor: the water will rush back."))
            elif surge <= REVERSE_SURGE_WATCH_FT:
                parts.append(("watch", f"Water is {abs(surge):.1f} ft below the predicted tide."))
        parts += _wind_parts(row) + _pressure_parts(s, now, row)

    elif st.source == "usgs_gauge":
        stage = row.get("stage_ft")
        stages = st.flood_stages_ft
        hour_ago = s.value_at(now - timedelta(hours=1), "stage_ft", within=timedelta(hours=2))
        rising = stage is not None and hour_ago is not None and stage > hour_ago
        category = "none"
        for name in ("action", "minor", "moderate", "major"):
            if stage is not None and name in stages and stage >= stages[name]:
                category = name
        trend = "and rising" if rising else "and falling"
        if category == "major" or (category == "moderate" and rising):
            parts.append(("warning", f"The river is at {stage:.1f} ft, {category} flood stage {trend}."))
        elif category in ("minor", "moderate"):
            parts.append(("watch", f"The river is at {stage:.1f} ft, {category} flood stage {trend}."))
        elif category == "action" and rising:
            parts.append(("watch", f"The river is at {stage:.1f} ft and rising toward flood stage."))

    elif st.source == "noaa_buoy":
        waves = row.get("wave_height_ft")
        if waves is not None and waves >= WAVES_WARNING_FT:
            parts.append(("warning", f"Offshore waves are {waves:.0f} ft."))
        elif waves is not None and waves >= WAVES_WATCH_FT:
            parts.append(("watch", f"Offshore waves are {waves:.0f} ft."))
        parts += _wind_parts(row) + _pressure_parts(s, now, row)

    status, reason = _worst(parts)
    if stale:
        reason = f"No fresh reading since {observed:%b %d %H:%M} UTC; Harbor doesn't treat old data as safe."
    return Reading(st, observed, row, status, reason, stale, flood_category=category, crest_rising=rising)


def sensor_flag(readings: list[Reading]) -> bool:
    """Storm effects arriving near the user: one warning, or watches from two different kinds of sensor."""
    fresh = [r for r in readings if not r.stale]
    if any(r.status == "warning" for r in fresh):
        return True
    return len({r.station.source for r in fresh if r.status == "watch"}) >= 2


def max_sustained_wind_mph(readings: list[Reading]) -> float | None:
    winds = [r.readings.get("wind_speed_mph") for r in readings if not r.stale]
    winds = [w for w in winds if w is not None]
    return max(winds) if winds else None


def recovery_gate(series: list[Series], now: datetime) -> tuple[bool, str]:
    """All-clear for moving money back. Returns (clear, reason). Rivers are checked first: they
    stay dangerous longest, so they give the most useful reason."""
    order = {"usgs_gauge": 0, "noaa_tide": 1, "noaa_buoy": 2}
    for s in sorted(series, key=lambda s: order.get(s.station.source, 9)):
        r = status_of(s, now)
        if r.stale:
            return False, f"{s.station.name} has no fresh reading, so Harbor can't confirm it's safe yet."
        src = s.station.source
        if src in ("noaa_tide", "noaa_buoy"):
            p = r.readings.get("pressure_mb")
            if p is not None and p < PRESSURE_RECOVERED_MB:
                return False, f"Air pressure at {s.station.name} is still low ({p:.0f} mb)."
        if src == "noaa_tide":
            recent = [row.get("surge_ft") for _, row in s.window(now - timedelta(hours=SURGE_CLEAR_HOURS), now)]
            recent = [v for v in recent if v is not None]
            if not recent or any(abs(v) >= SURGE_WATCH_FT for v in recent):
                return False, f"Water at {s.station.name} hasn't been back to normal for {SURGE_CLEAR_HOURS} hours yet."
        if src == "usgs_gauge":
            stage = r.readings.get("stage_ft")
            major = s.station.flood_stages_ft.get("major")
            minor = s.station.flood_stages_ft.get("minor")
            if stage is None:
                return False, f"{s.station.name} has no stage reading."
            if minor is not None and stage < minor:
                continue
            ago3 = s.value_at(now - timedelta(hours=RIVER_FALLING_HOURS / 2), "stage_ft", within=timedelta(hours=2))
            ago6 = s.value_at(now - timedelta(hours=RIVER_FALLING_HOURS), "stage_ft", within=timedelta(hours=2))
            falling = ago3 is not None and ago6 is not None and stage < ago3 < ago6
            if (major is not None and stage >= major) or not falling:
                return False, (f"The {s.station.name} is at {stage:.1f} ft"
                               f"{' (major flood)' if major is not None and stage >= major else ''} and "
                               f"{'falling' if falling else 'not yet falling steadily'}. Your cash stays in checking.")
    return True, "Pressure has recovered, the water is back to normal and rivers are falling."


# --- Replay source -----------------------------------------------------------------------------

@lru_cache
def load_replay(storm: str = "milton-2024") -> tuple[Series, ...]:
    folder = DATA / storm
    out = []
    for path in sorted(folder.glob("*.json")):
        if path.name == "stations.json":
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        st = data["station"]
        station = Station(st["id"], st["source"], st["name"], st["lat"], st["lon"], st["attribution"],
                          data.get("flood_stages_ft", {}))
        out.append(Series(station, data["rows"]))
    return tuple(out)


class SensorSource:
    """Recorded sensors for a storm, seen through the clock."""

    def __init__(self, storm: str = "milton-2024", series: tuple[Series, ...] | None = None):
        self.series = list(series if series is not None else load_replay(storm))

    def near(self, lat: float, lon: float, radius_miles: float = 200) -> list[Series]:
        return [s for s in self.series if miles_between(lat, lon, s.station.lat, s.station.lon) <= radius_miles]

    def readings(self, now: datetime, lat: float, lon: float, radius_miles: float = 200) -> list[Reading]:
        out = []
        for s in self.near(lat, lon, radius_miles):
            r = status_of(s, now)
            r.distance_miles = round(miles_between(lat, lon, s.station.lat, s.station.lon))
            out.append(r)
        return sorted(out, key=lambda r: r.distance_miles)

    @property
    def end(self) -> datetime | None:
        """When the recording stops: the replay keeps running until then so recovery can happen."""
        ends = [s.times[-1] for s in self.series if s.times]
        return min(ends) if ends else None

    def history(self, station_id: str, now: datetime, hours: int = 48, metrics: list[str] | None = None) -> list[dict]:
        s = next((s for s in self.series if s.station.id == station_id), None)
        if s is None:
            return []
        rows = s.window(now - timedelta(hours=hours), now)
        step = max(1, len(rows) // 400)  # keep charts light
        return [
            {"observed_at": t.strftime("%Y-%m-%dT%H:%M:%SZ"),
             "readings": {k: v for k, v in row.items() if k != "t" and (not metrics or k in metrics)}}
            for t, row in rows[::step]
        ]

    def risk_facts(self, now: datetime, lat: float, lon: float) -> dict:
        """Inputs for engine.risk.RiskInputs: sensor_flag, sustained_wind_mph, sensors_all_clear."""
        readings = self.readings(now, lat, lon, FLAG_RADIUS_MI)
        local = [r for r in readings if r.distance_miles <= LOCAL_RADIUS_MI]
        clear, reason = recovery_gate(self.near(lat, lon, LOCAL_RADIUS_MI), now)
        return {
            "sensor_flag": sensor_flag(readings),
            "sustained_wind_mph": max_sustained_wind_mph(local),
            "sensors_all_clear": clear,
            "all_clear_reason": reason,
        }
