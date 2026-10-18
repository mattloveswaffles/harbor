"""Hourly wind, gusts and rain at the home from Open-Meteo.

Live mode reads its forecast API; replays read its historical-forecast archive for the replay's dates.
Answers are cached for 30 minutes per place and day range.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_URL = "https://historical-forecast-api.open-meteo.com/v1/forecast"
ATTRIBUTION = "Weather data by Open-Meteo.com (CC BY 4.0)"
CACHE_S = 1800

_cache: dict[tuple, tuple[float, list[Hour]]] = {}


@dataclass(frozen=True)
class Hour:
    at: datetime
    wind_mph: float
    gust_mph: float
    rain_in: float


def fetch(url: str, params: dict) -> dict:
    """One Open-Meteo request (tests replace this)."""
    res = httpx.get(url, params=params, timeout=15, headers={"User-Agent": "Harbor hackathon project"})
    res.raise_for_status()
    return res.json()


def hourly(lat: float, lon: float, start: datetime, end: datetime, *, archive: bool) -> list[Hour]:
    day0, day1 = start.date(), end.date()
    key = (round(lat, 2), round(lon, 2), day0, day1, archive)
    hit = _cache.get(key)
    if hit is None or time.monotonic() - hit[0] > CACHE_S:
        body = fetch(
            ARCHIVE_URL if archive else FORECAST_URL,
            {
                "latitude": round(lat, 3),
                "longitude": round(lon, 3),
                "hourly": "wind_speed_10m,wind_gusts_10m,precipitation",
                "wind_speed_unit": "mph",
                "precipitation_unit": "inch",
                "timezone": "UTC",
                "start_date": day0.isoformat(),
                "end_date": day1.isoformat(),
            },
        )
        h = body["hourly"]
        rows = [
            Hour(datetime.fromisoformat(t).replace(tzinfo=UTC), w or 0.0, g or 0.0, p or 0.0)
            for t, w, g, p in zip(h["time"], h["wind_speed_10m"], h["wind_gusts_10m"], h["precipitation"], strict=True)
        ]
        hit = _cache[key] = (time.monotonic(), rows)
    return [r for r in hit[1] if start <= r.at < end]


def buckets(rows: list[Hour], start: datetime, step_h: int, count: int) -> list[dict]:
    """Strongest wind and gust and total rain per step, from `start`."""
    out = []
    for i in range(count):
        a = start + timedelta(hours=i * step_h)
        part = [r for r in rows if a <= r.at < a + timedelta(hours=step_h)]
        out.append(
            {
                "at": a,
                "wind_mph": round(max((r.wind_mph for r in part), default=0)),
                "gust_mph": round(max((r.gust_mph for r in part), default=0)),
                "rain_in": round(sum(r.rain_in for r in part), 2),
            }
        )
    return out
