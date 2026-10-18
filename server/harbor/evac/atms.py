"""ATMs from an OpenStreetMap snapshot (Nessie's are all in VA/MD/DC); outside the cone and on the route first."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from shapely.geometry import Point, shape

from harbor.geo import miles_between

DATA = Path(__file__).resolve().parents[2] / "data" / "evac"
ROUTE_BUFFER_DEG = 0.03  # about 2 miles either side of the route


@lru_cache
def _snapshot() -> dict:
    path = DATA / "atms.json"
    return json.loads(path.read_text(encoding="utf-8"))["by_area"] if path.exists() else {}


def all_atms() -> list[dict]:
    seen, out = set(), []
    for rows in _snapshot().values():
        for a in rows:
            if a["id"] not in seen:
                seen.add(a["id"])
                out.append(a)
    return out


def rank_atms(
    origin: tuple[float, float],
    radius_miles: float = 150,
    cone=None,
    route_geometry: dict | None = None,
    limit: int = 25,
) -> list[dict]:
    route = shape(route_geometry).buffer(ROUTE_BUFFER_DEG) if route_geometry else None
    out = []
    for a in all_atms():
        dist = round(miles_between(origin[0], origin[1], a["lat"], a["lon"]), 1)
        if dist > radius_miles:
            continue
        pt = Point(a["lon"], a["lat"])
        out.append(
            {
                "id": a["id"],
                "source": "osm",
                "name": a["name"],
                "location": {"lat": a["lat"], "lon": a["lon"]},
                "address": a.get("address"),
                "distance_miles": dist,
                "in_forecast_cone": bool(cone is not None and cone.contains(pt)),
                "on_evacuation_route": bool(route is not None and route.contains(pt)),
                "amount_left_cents": None,
                "accessibility": a.get("accessibility", "unknown"),
                "hours": [a["hours"]] if a.get("hours") else [],
            }
        )
    out.sort(key=lambda a: (a["in_forecast_cone"], not a["on_evacuation_route"], a["distance_miles"]))
    return out[:limit]
