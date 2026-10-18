"""GET /me/weather: the storm, its hazards at the home, and wind and rain over the coming days."""

from datetime import datetime, timedelta

import httpx
from fastapi import APIRouter, Request

from harbor.clock import iso
from harbor.context import evacuation_for
from harbor.deps import ClockDep, SessionDep, UserDep
from harbor.errors import HarborError
from harbor.models import Household
from harbor.sources import weather
from harbor.sources.forecast import parse_time
from harbor.sources.sensors import miles_between
from harbor.ticker import forecast_source

router = APIRouter(tags=["weather"])

WARNINGS = (
    "Hurricane Warning",
    "Storm Surge Warning",
    "Hurricane Watch",
    "Tropical Storm Warning",
    "Tropical Storm Watch",
)
SURGE_ZONES = {"A", "B"}
BUCKETS = 10


def _closest(track: dict, lat: float, lon: float, now: datetime) -> dict | None:
    """The forecast point nearest the home from now on."""
    points = [
        f["properties"] | {"lon": f["geometry"]["coordinates"][0], "lat": f["geometry"]["coordinates"][1]}
        for f in track["features"]
        if f["geometry"]["type"] == "Point" and parse_time(f["properties"]["valid_time"]) >= now
    ]
    if not points:
        return None
    best = min(points, key=lambda p: miles_between(lat, lon, p["lat"], p["lon"]))
    return best | {"miles": round(miles_between(lat, lon, best["lat"], best["lon"]))}


@router.get("/me/weather")
def get_weather(request: Request, session: SessionDep, user: UserDep, clock: ClockDep) -> dict:
    """NHC storm and alerts plus Open-Meteo wind, gusts and rain at the home (archived forecasts in replays)."""
    now = clock.now()
    app = request.app
    source = forecast_source(app)
    exp = source.exposure(user.lat, user.lon, user.zip, now) if source else None
    adv = exp.advisory if exp else None
    alerts = {a["type"] for a in exp.alerts} if exp else set()

    storm, closest = None, None
    if adv is not None:
        closest = _closest(source.track_layer(now), user.lat, user.lon, now)
        storm = {
            "name": source.name,
            "classification": adv.classification,
            "category": adv.category,
            "max_wind_mph": adv.max_wind_mph,
            "advisory_time": iso(adv.issued_at),
            "warning": next((w for w in WARNINGS if w in alerts), None),
            "closest_at": closest["valid_time"] if closest else None,
            "closest_miles": closest["miles"] if closest else None,
            "category_at_closest": closest["category"] if closest else None,
        }

    # Ten steps that reach past the storm's closest pass: 6-hour steps, or 12-hour ones when it's days away
    until = parse_time(closest["valid_time"]) + timedelta(hours=18) if closest else now + timedelta(hours=60)
    step = 6 if until - now <= timedelta(hours=60) else 12
    start = now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=now.hour % step)
    archive = source is not None and source.is_replay  # a replayed storm reads archived forecasts
    try:
        rows = weather.hourly(user.lat, user.lon, start, start + timedelta(hours=step * BUCKETS), archive=archive)
    except httpx.HTTPError as exc:
        raise HarborError(503, "weather_unavailable", "Open-Meteo didn't answer. Try again in a minute.") from exc
    series = weather.buckets(rows, start, step, BUCKETS)

    peak_wind = max((s["wind_mph"] for s in series), default=0)
    peak_gust = max((s["gust_mph"] for s in series), default=0)
    zone = (session.get(Household, user.id) or Household(user_id=user.id)).evac_zone
    surge_alert = "Storm Surge Warning" in alerts or "Hurricane Warning" in alerts
    bundle = evacuation_for(app, session, user, now)
    return {
        "server_time": iso(now),
        "storm": storm,
        "hazards": {
            "wind": {
                "arrives_at": iso(exp.eta) if exp else None,
                "peak_wind_mph": peak_wind,
                "peak_gust_mph": peak_gust,
            },
            "surge": {
                "zone": zone,
                "level": "evacuate" if zone in SURGE_ZONES and (surge_alert or (exp and exp.in_cone)) else "low",
            },
            "rain": {"total_in": round(sum(s["rain_in"] for s in series), 1)},
            "tornado": {"level": "watch" if any("Tornado" in a for a in alerts) else "possible" if adv else "unlikely"},
            "power": {"level": "likely" if peak_gust >= 58 else "possible" if peak_gust >= 39 else "unlikely"},
        },
        "step_hours": step,
        "series": [s | {"at": iso(s["at"])} for s in series],
        "marks": {
            "leave_by": bundle["guide"]["leave_by"] if bundle else None,
            "closest_at": storm["closest_at"] if storm else None,
        },
        "source": "Open-Meteo historical forecast" if archive else "Open-Meteo forecast",
        "attribution": ["NOAA NHC", weather.ATTRIBUTION],
    }
