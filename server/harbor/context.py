"""Per-user inputs shared by routes and the scheduler: household, storm, sensors and the evacuation guide."""

from __future__ import annotations

from datetime import datetime

from sqlmodel import Session

from harbor import models, profile
from harbor.evac.guide import build_guide
from harbor.evac.household import Household, Pet
from harbor.sources.sensors import SensorSource
from harbor.ticker import forecast_source, sensor_source

GUIDE_LEVELS = {"prepare", "act", "shelter", "recover"}


def household_of(session: Session, user: models.User) -> Household:
    row = session.get(models.Household, user.id)
    med = row.medical
    return Household(
        adults=row.adults,
        children_ages=tuple(row.children_ages),
        seniors=row.seniors,
        pets=tuple(Pet(p["type"], p["count"]) for p in row.pets),
        mobility=row.mobility,
        power_dependent_device=med["power_dependent_device"],
        oxygen=med["oxygen"],
        dialysis=med["dialysis"],
        refrigerated_meds=med["refrigerated_meds"],
        has_car=row.has_car,
        home_type=row.home_type,
        evac_zone=row.evac_zone,
    )


def storm_inputs(app, user: models.User, now: datetime) -> dict:
    """Cone, track, forecast peak category and tropical-storm-wind ETA for the user's home, and whether it's a replay."""
    source = forecast_source(app)
    if source is None:
        return {"cone": None, "track": None, "category": None, "eta": None, "replay": False}
    cone = source.cone_layer(now)
    track = source.track_layer(now)
    lines = [f for f in track["features"] if f["geometry"]["type"] == "LineString"]
    cats = [f["properties"].get("category") or 0 for f in track["features"] if f["geometry"]["type"] == "Point"]
    exp = source.exposure(user.lat, user.lon, user.zip, now)
    return {
        "cone": cone if cone["features"] else None,
        "track": lines[0] if lines else None,
        "category": max(cats) if cats else None,
        "eta": exp.eta,
        "replay": True,
    }


def sensors_for(app) -> SensorSource | None:
    source = forecast_source(app)
    return sensor_source(source.root.name) if source else None


def guide_for(app, session: Session, user: models.User, now: datetime) -> dict:
    """The evacuation guide bundle (guide, budget_lines, layers, atms) for the user's home now."""
    storm = storm_inputs(app, user, now)
    return build_guide(
        now,
        (user.lat, user.lon),
        user.zip,
        household_of(session, user),
        cone=storm["cone"],
        track=storm["track"],
        category=storm["category"],
        ts_winds_eta=storm["eta"],
        demo=storm["replay"],
        ors_key=app.state.settings.ors_api_key,
        choose=profile.choice(session, user),
    )


def evacuation_for(app, session: Session, user: models.User, now: datetime) -> dict | None:
    """The evacuation guide bundle, or None before `prepare`."""
    return guide_for(app, session, user, now) if user.risk_level in GUIDE_LEVELS else None
