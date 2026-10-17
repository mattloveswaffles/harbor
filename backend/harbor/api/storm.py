"""GET /me/storm and GET /me/map: what the forecast says about the user's home right now."""

from fastapi import APIRouter, Request

from harbor.clock import iso
from harbor.context import evacuation_for, sensors_for
from harbor.deps import ClockDep, SessionDep, UserDep
from harbor.engine.risk import MONITOR_P34
from harbor.schemas import MapOut, StormStatusOut
from harbor.sources.forecast import empty_fc
from harbor.ticker import forecast_source

router = APIRouter(tags=["storm"])

NO_STORM = "No storm threatens your ZIP."
EMPTY_LAYERS = ("route", "destinations", "shelters", "lodging", "atms", "sensors")
EVAC_LAYERS = ("route", "destinations", "shelters", "lodging", "atms")


@router.get("/me/storm", response_model=StormStatusOut)
def get_storm(request: Request, user: UserDep, clock: ClockDep) -> dict:
    """The user's risk level (from the last scheduler tick) and the forecast at their home now.
    `storm` is null when nothing threatens the ZIP."""
    now = clock.now()
    source = forecast_source(request.app)
    exp = source.exposure(user.lat, user.lon, user.zip, now) if source else None
    adv = exp.advisory if exp else None
    threatens = adv is not None and (
        user.risk_level != "clear" or exp.in_cone or exp.p34 >= MONITOR_P34 or exp.alerts
    )
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
            "is_replay": source.is_replay,
            "headline": adv.headline,
            "position": {"lat": adv.lat, "lon": adv.lon},
            "max_wind_mph": adv.max_wind_mph,
        }
    at_zip = exp.out() if exp else {
        "ts_wind_probability_5day": 0.0, "hurricane_wind_probability_5day": 0.0, "in_forecast_cone": False,
        "earliest_ts_winds_eta": None, "eta_source": None, "alerts": [],
    }
    return {
        "server_time": iso(now),
        "risk_level": user.risk_level,
        "risk_reason": user.risk_reason or NO_STORM,
        "storm": storm,
        "at_your_zip": at_zip,
    }


@router.get("/me/map", response_model=MapOut)
def get_map(request: Request, session: SessionDep, user: UserDep, clock: ClockDep) -> dict:
    """Every map layer as GeoJSON ([lon, lat]). Sensors show from the start of a replay; route,
    destinations, shelters, lodging and ATMs appear once the user reaches prepare."""
    now = clock.now()
    source = forecast_source(request.app)
    home = {"type": "FeatureCollection", "features": [{
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [user.lon, user.lat]},
        "properties": {"id": "home", "label": "Home", "zip": user.zip, "location_source": user.location_source},
    }]}
    layers = {
        "home": home,
        "cone": source.cone_layer(now) if source else empty_fc(),
        "track": source.track_layer(now) if source else empty_fc(),
        **{name: empty_fc() for name in EMPTY_LAYERS},
    }
    sensors = sensors_for(request.app)
    if sensors:
        layers["sensors"] = {"type": "FeatureCollection", "features": [{
            "type": "Feature", "geometry": {"type": "Point", "coordinates": [r.station.lon, r.station.lat]},
            "properties": {"id": r.station.id, "source": r.station.source, "label": r.station.name,
                           "status": "stale" if r.stale else r.status, "distance_miles": r.distance_miles},
        } for r in sensors.readings(now, user.lat, user.lon)]}
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
