"""The evacuation guide: destination, route, shelters, lodging and household advice in one call.

`build_guide` returns three things the API needs:
- `guide`: the GET /me/evacuation body (docs/API.md "Evacuation guide")
- `budget_lines`: lodging and fuel lines for engine.plan (food, pets and supplies come from household)
- `layers`: GeoJSON map layers (route, destinations, shelters, lodging) for GET /me/map
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime

from harbor.engine.plan import fuel_line, lodging_line
from harbor.evac import destination as dest_mod
from harbor.evac.atms import rank_atms
from harbor.evac import lodging as lodging_mod
from harbor.evac import shelters as shelter_mod
from harbor.evac.household import Household, budget_lines, guide as household_guide
from harbor.evac.route import DRIVE_NOTE, find_route, maps_links

NIGHTS_DEFAULT = 3  # Harbor estimate for a Milton-sized storm

GOUGING_CARD = {
    "kind": "price_gouging", "title": "Price gouging is illegal during a declared emergency",
    "text": "Book a refundable room early and screenshot the price. If a quote looks far above normal, "
            "report it to the Florida Attorney General: 1-866-9-NO-SCAM.",
}


def _iso(dt: datetime | None) -> str | None:
    return None if dt is None else dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _fc(features: list[dict]) -> dict:
    return {"type": "FeatureCollection", "features": features}


def _point(lat: float, lon: float, **props) -> dict:
    return {"type": "Feature", "geometry": {"type": "Point", "coordinates": [lon, lat]}, "properties": props}


def build_guide(
    now: datetime,
    origin: tuple[float, float],
    origin_zip: str,
    household: Household,
    *,
    cone=None,
    track=None,
    category: int | None = None,
    ts_winds_eta: datetime | None = None,
    demo: bool = True,
    ors_key: str = "",
    band: str = "standard",
    choose: str | None = None,
    meals_source: str | None = None,
) -> dict:
    hh = household_guide(household)

    def route_for(d):
        return find_route(origin, (d.lat, d.lon), origin_zip=origin_zip, destination_id=d.id, demo=demo, ors_key=ors_key)

    decision = dest_mod.decide(origin, household, cone=cone, track=track, category=category,
                               ts_winds_eta=ts_winds_eta, now=now, route_for=route_for, choose=choose)
    chosen = decision.chosen
    shelters = shelter_mod.rank(
        shelter_mod.demo_shelters(now) if demo else shelter_mod.fema_shelters(*origin), origin, hh.shelter_filter)

    route_json, lodging_json, lines = None, None, []
    nights = NIGHTS_DEFAULT
    if chosen is not None:
        r = chosen.route
        route_json = {
            "provider": r.provider, "distance_mi": r.distance_mi,
            "drive_time_min_normal": r.drive_time_min_normal, "drive_time_min_evac": r.drive_time_min_evac,
            "drive_time_note": DRIVE_NOTE, "cone_overlap_pct": chosen.cone_overlap_pct,
            "corridor": chosen.destination.corridor, "steps": r.steps,
            "links": maps_links(origin[0], origin[1], chosen.destination.lat, chosen.destination.lon),
            "attribution": r.attribution,
        }
        lodging = lodging_mod.plan_lodging(chosen.destination, origin, nights, hh.rooms, hh.shelter_filter, band)
        lodging_json = lodging.to_api()
        place = chosen.destination.name.split(",")[0]
        lines = [
            lodging_line(place, lodging.nightly_estimate_cents, hh.rooms, nights, lodging.estimate_source),
            fuel_line(2 * r.distance_mi),
        ]
        meals_cents = chosen.destination.meals_cents
        source = meals_source or chosen.destination.basis
    else:
        meals_cents, source = 6_800, "GSA per diem FY2025 standard rate"
    lines += budget_lines(household, days=nights, nights=nights, meals_rate_cents=meals_cents, meals_source=source)

    destinations = [{
        "id": o.destination.id, "name": o.destination.name, "tier": o.tier,
        "location": {"lat": o.destination.lat, "lon": o.destination.lon},
        "drive_time_min_normal": o.route.drive_time_min_normal, "drive_time_min_evac": o.route.drive_time_min_evac,
        "outside_cone": o.outside_cone, "leave_by": _iso(o.leave_by), "feasible": o.feasible,
        "recommended": o.recommended,
    } for o in decision.options]

    guide = {
        "server_time": _iso(now),
        "decision": {"action": decision.action, "tier": decision.tier, "reason_codes": decision.reason_codes},
        "leave_by": _iso(chosen.leave_by) if chosen else None,
        "destinations": destinations,
        "chosen": chosen.destination.id if chosen else None,
        "route": route_json,
        "shelters": [s.to_api(origin) for s in shelters[:6]],
        "lodging": lodging_json,
        "checklists": [asdict(c) | {"items": list(c.items)} for c in hh.checklists],
        "advice_cards": [{k: v for k, v in asdict(a).items() if v is not None} for a in hh.advice] + [GOUGING_CARD],
        "explanation": None,
    }

    atms = rank_atms(origin, cone=dest_mod._to_shape(cone),
                     route_geometry=chosen.route.geometry if chosen and chosen.route else None)
    layers = {
        "route": _fc([{"type": "Feature", "geometry": chosen.route.geometry,
                       "properties": {"distance_mi": chosen.route.distance_mi, "corridor": chosen.destination.corridor}}]
                     if chosen and chosen.route.geometry else []),
        "destinations": _fc([_point(d["location"]["lat"], d["location"]["lon"], id=d["id"], name=d["name"],
                                    recommended=d["recommended"], tier=d["tier"]) for d in destinations]),
        "shelters": _fc([_point(s.lat, s.lon, id=s.id, name=s.name, kind=s.kind, status=s.status, pets=s.pets,
                                ada=s.ada) for s in shelters]),
        "lodging": _fc([_point(o["location"]["lat"], o["location"]["lon"], id=o["id"], name=o["name"], type=o["type"],
                               pets=o["pets"]) for o in (lodging_json or {}).get("options", [])]),
    }
    layers["atms"] = _fc([_point(a["location"]["lat"], a["location"]["lon"], id=a["id"], name=a["name"], source="osm",
                                 in_cone=a["in_forecast_cone"], on_route=a["on_evacuation_route"]) for a in atms])
    return {"guide": guide, "budget_lines": lines, "layers": layers, "atms": atms, "rooms": hh.rooms, "nights": nights}
