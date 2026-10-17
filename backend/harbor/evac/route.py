"""Route geometry, distance, drive times and steps (ORS -> OSRM -> Maps link only).

Demo mode reads routes precomputed by tools/build_demo_evac.py, so it makes no network calls.
Live mode tries OpenRouteService (needs ORS_API_KEY), then the public OSRM server, then gives up
on geometry; the Google/Apple Maps links always work because the phone does the routing.

Free routers return normal-traffic times. Evacuation traffic is far slower, worst near the coast,
so every route also carries `drive_time_min_evac`: a Harbor estimate of normal time plus 1.5x
extra, capped at 5 extra hours (Tampa to Gainesville: 2.5 h becomes about 6 h).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlencode

import httpx
from shapely.geometry import shape

DATA = Path(__file__).resolve().parents[2] / "data" / "evac"
EVAC_EXTRA_FACTOR = 1.5
EVAC_EXTRA_CAP_MIN = 300
MI = 1609.344
ORS_URL = "https://api.openrouteservice.org/v2/directions/driving-car/geojson"
OSRM_URL = "https://router.project-osrm.org/route/v1/driving"
DRIVE_NOTE = "Evacuation estimate (normal time plus up to 5 hours of traffic); traffic during Milton was severe."


@dataclass
class Route:
    provider: str
    distance_mi: float
    drive_time_min_normal: int
    geometry: dict | None = None
    steps: list[dict] = field(default_factory=list)
    attribution: str = ""

    @property
    def drive_time_min_evac(self) -> int:
        return self.drive_time_min_normal + round(min(self.drive_time_min_normal * EVAC_EXTRA_FACTOR, EVAC_EXTRA_CAP_MIN))


def maps_links(o_lat: float, o_lon: float, d_lat: float, d_lon: float) -> dict:
    origin, dest = f"{o_lat:.4f},{o_lon:.4f}", f"{d_lat:.4f},{d_lon:.4f}"
    google = "https://www.google.com/maps/dir/?" + urlencode(
        {"api": 1, "origin": origin, "destination": dest, "travelmode": "driving"})
    apple = "https://maps.apple.com/?" + urlencode({"saddr": origin, "daddr": dest, "dirflg": "d"})
    return {"google": google, "apple": apple}


def cone_overlap_pct(geometry: dict | None, cone) -> int | None:
    """Share of the route's length inside the forecast cone (a shapely geometry)."""
    if geometry is None or cone is None:
        return None
    line = shape(geometry)
    if line.length == 0:
        return 0
    return round(100 * line.intersection(cone).length / line.length)


@lru_cache
def _demo_routes(origin_zip: str) -> dict[str, dict]:
    path = DATA / f"routes_{origin_zip}.json"
    return json.loads(path.read_text(encoding="utf-8"))["routes"] if path.exists() else {}


def demo_route(origin_zip: str, destination_id: str) -> Route | None:
    r = _demo_routes(origin_zip).get(destination_id)
    if r is None:
        return None
    return Route(r["provider"], r["distance_mi"], r["drive_time_min_normal"], r.get("geometry"), r.get("steps", []),
                 r.get("attribution", ""))


def ors_route(client: httpx.Client, key: str, o: tuple[float, float], d: tuple[float, float]) -> Route:
    res = client.post(ORS_URL, headers={"Authorization": key},
                      json={"coordinates": [[o[1], o[0]], [d[1], d[0]]], "instructions": True})
    res.raise_for_status()
    feat = res.json()["features"][0]
    summary = feat["properties"]["summary"]
    steps = [{"text": s["instruction"], "distance_mi": round(s["distance"] / MI, 1)}
             for seg in feat["properties"]["segments"] for s in seg["steps"]]
    return Route("ors", round(summary["distance"] / MI, 1), round(summary["duration"] / 60), feat["geometry"], steps,
                 "© openrouteservice.org by HeiGIT | © OpenStreetMap contributors")


def osrm_route(client: httpx.Client, o: tuple[float, float], d: tuple[float, float]) -> Route:
    res = client.get(f"{OSRM_URL}/{o[1]},{o[0]};{d[1]},{d[0]}",
                     params={"overview": "simplified", "geometries": "geojson", "steps": "true"})
    res.raise_for_status()
    route = res.json()["routes"][0]
    steps = []
    for leg in route["legs"]:
        for s in leg["steps"]:
            m = s["maneuver"]
            road = s.get("ref") or s.get("name") or "the road"
            if m["type"] == "arrive":
                steps.append({"text": "Arrive at your destination", "distance_mi": 0})
            elif s["distance"] / MI >= 0.2 or m["type"] == "depart":
                verb = {"depart": "Start on", "turn": f"Turn {m.get('modifier', '')} onto",
                        "merge": "Merge onto", "on ramp": "Take the ramp onto", "off ramp": "Take the exit to",
                        "fork": f"Keep {m.get('modifier', '').replace('slight ', '')} onto"}.get(m["type"], "Continue on")
                steps.append({"text": f"{verb} {road}".replace("  ", " "), "distance_mi": round(s["distance"] / MI, 1)})
    return Route("osrm", round(route["distance"] / MI, 1), round(route["duration"] / 60), route["geometry"], steps,
                 "Routing © OSRM, map data © OpenStreetMap contributors")


def find_route(o: tuple[float, float], d: tuple[float, float], *, origin_zip: str | None = None,
               destination_id: str | None = None, demo: bool = True, ors_key: str = "",
               client: httpx.Client | None = None) -> Route | None:
    """Best available route, or None (callers then show only the Maps links)."""
    if demo and origin_zip and destination_id:
        return demo_route(origin_zip, destination_id)
    own = client is None
    client = client or httpx.Client(timeout=15, headers={"User-Agent": "Harbor hackathon project"})
    try:
        if ors_key:
            try:
                return ors_route(client, ors_key, o, d)
            except Exception:
                pass
        try:
            return osrm_route(client, o, d)
        except Exception:
            return None
    finally:
        if own:
            client.close()
