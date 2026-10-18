"""GET /me/storm and GET /me/map: what the forecast says about the user's home right now."""

from fastapi import APIRouter, Request

from harbor.clock import iso
from harbor.context import evacuation_for, sensors_for
from harbor.deps import ClockDep, SessionDep, UserDep
from harbor.engine.risk import MONITOR_P34
from harbor.geo import feature_collection, point
from harbor.schemas import MapOut, StormStatusOut
from harbor.sources.forecast import Exposure
from harbor.ticker import forecast_source

router = APIRouter(tags=["storm"])

NO_STORM = "No storm threatens your ZIP."
EMPTY_LAYERS = ("route", "route_options", "destinations", "shelters", "lodging", "atms", "sensors")
EVAC_LAYERS = ("route", "route_options", "destinations", "shelters", "lodging", "atms")


@router.get("/me/storm", response_model=StormStatusOut)
def get_storm(request: Request, user: UserDep, clock: ClockDep) -> dict:
    """Risk level (last tick) and the forecast at the home now; `storm` is null when nothing threatens."""
    now = clock.now()
    source = forecast_source(request.app)
    exp = source.exposure(user.lat, user.lon, user.zip, now) if source else Exposure(None)
    adv = exp.advisory
    threatens = adv is not None and (user.risk_level != "clear" or exp.in_cone or exp.p34 >= MONITOR_P34 or exp.alerts)
    storm = None
    if threatens:
        nxt = source.next_advisory_time(now)
        storm = {
            "id": source.storm_id,
            "name": source.name,
            "classification": adv.classification,
            "category": adv.category,
            "advisory_number": adv.advisory_number,
            "advisory_time": iso(adv.issued_at),
            "next_advisory_time": iso(nxt) if nxt and nxt < source.end else None,
            "is_replay": True,
            "headline": adv.headline,
            "position": {"lat": adv.lat, "lon": adv.lon},
            "max_wind_mph": adv.max_wind_mph,
        }
    return {
        "server_time": iso(now),
        "risk_level": user.risk_level,
        "risk_reason": user.risk_reason or NO_STORM,
        "storm": storm,
        "at_your_zip": exp.out(),
    }


@router.get("/me/map", response_model=MapOut)
def get_map(request: Request, session: SessionDep, user: UserDep, clock: ClockDep) -> dict:
    """Every map layer as GeoJSON ([lon, lat]); evacuation layers appear from prepare."""
    now = clock.now()
    source = forecast_source(request.app)
    layers = {
        "home": feature_collection(
            [point(user.lat, user.lon, id="home", label="Home", zip=user.zip, location_source=user.location_source)]
        ),
        "cone": source.cone_layer(now) if source else feature_collection([]),
        "track": source.track_layer(now) if source else feature_collection([]),
        **{name: feature_collection([]) for name in EMPTY_LAYERS},
    }
    sensors = sensors_for(request.app)
    if sensors:
        layers["sensors"] = feature_collection(
            [
                point(
                    r.station.lat,
                    r.station.lon,
                    id=r.station.id,
                    source=r.station.source,
                    label=r.station.name,
                    status="stale" if r.stale else r.status,
                    distance_miles=r.distance_miles,
                )
                for r in sensors.readings(now, user.lat, user.lon)
            ]
        )
    bundle = evacuation_for(request.app, session, user, now)
    if bundle:
        layers.update({name: bundle["layers"][name] for name in EVAC_LAYERS})
    attribution = ["NOAA NHC"] if layers["cone"]["features"] else []
    if layers["sensors"]["features"]:
        attribution += ["NOAA CO-OPS", "USGS", "NOAA NDBC"]
    if bundle:
        attribution.append("© OpenStreetMap contributors")
    attribution.append("U.S. Census Bureau ZCTA, GeoNames (CC BY 4.0)")
    return {"server_time": iso(now), "layers": layers, "attribution": attribution}
