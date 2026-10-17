"""Public shelters from FEMA Open Shelters (live) or the curated Milton list (demo).

Pets and accessibility are tri-state: yes, no or unknown. FEMA's own fields are often blank, so
"unknown" is common, and Harbor never shows "unknown" as "yes". A household's known needs are a
hard filter only against a known "no". Special-needs shelters are offered only to households with
medical or mobility needs, and first.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path

import httpx

from harbor.evac.household import PlaceFilter
from harbor.evac.route import maps_links
from harbor.sources.sensors import miles_between

DATA = Path(__file__).resolve().parents[2] / "data" / "evac"
FEMA_URL = "https://gis.fema.gov/arcgis/rest/services/NSS/OpenShelters/FeatureServer/0/query"


@dataclass
class Shelter:
    id: str
    name: str
    kind: str          # general | special_needs
    status: str        # open | full
    pets: str          # yes | no | unknown
    ada: str           # yes | no | unknown
    lat: float
    lon: float
    address: str | None
    capacity_left: int | None
    source: str
    distance_mi: float | None = None

    def to_api(self, origin: tuple[float, float]) -> dict:
        return {
            "id": self.id, "name": self.name, "kind": self.kind, "status": self.status,
            "pets": self.pets, "ada": self.ada, "capacity_left": self.capacity_left,
            "distance_mi": self.distance_mi, "location": {"lat": self.lat, "lon": self.lon},
            "address": self.address, "source": self.source,
            "links": maps_links(origin[0], origin[1], self.lat, self.lon),
        }


@lru_cache
def _curated() -> dict:
    return json.loads((DATA / "shelters_milton.json").read_text(encoding="utf-8"))


def demo_shelters(now: datetime) -> list[Shelter]:
    out = []
    for s in _curated()["shelters"]:
        full_from = s.get("full_from")
        full = full_from is not None and datetime.fromisoformat(full_from.replace("Z", "+00:00")) <= now
        out.append(Shelter(s["id"], s["name"], s["kind"], "full" if full else "open", s["pets"], s["ada"],
                           s["lat"], s["lon"], s.get("address"), None, s["source"]))
    return out


def _tri(value) -> str:
    v = str(value or "").strip().lower()
    return "yes" if v in ("yes", "y", "true", "1") else "no" if v in ("no", "n", "false", "0") else "unknown"


def fema_shelters(lat: float, lon: float, radius_mi: float = 60, client: httpx.Client | None = None) -> list[Shelter]:
    own = client is None
    client = client or httpx.Client(timeout=15)
    try:
        res = client.get(FEMA_URL, params={
            "where": "shelter_status='OPEN'", "geometry": f"{lon},{lat}", "geometryType": "esriGeometryPoint",
            "inSR": 4326, "distance": radius_mi, "units": "esriSRUnit_StatuteMile", "outFields": "*", "f": "json"})
        res.raise_for_status()
        out = []
        for f in res.json().get("features", []):
            a = f["attributes"]
            cap, pop = a.get("evacuation_capacity"), a.get("total_population")
            out.append(Shelter(
                f"fema_{a.get('shelter_id')}", a.get("shelter_name") or "Shelter", "general", "open",
                "yes" if str(a.get("pet_accommodations_code") or "").strip() not in ("", "NONE", "None") else "unknown",
                _tri(a.get("ada_compliant")), a.get("latitude"), a.get("longitude"),
                " ".join(str(a.get(k) or "") for k in ("address", "city", "state")).strip() or None,
                cap - pop if isinstance(cap, int) and isinstance(pop, int) else None, "FEMA Open Shelters"))
        return out
    finally:
        if own:
            client.close()


def rank(shelters: list[Shelter], origin: tuple[float, float], needs: PlaceFilter, radius_mi: float = 60) -> list[Shelter]:
    out = []
    for s in shelters:
        s.distance_mi = round(miles_between(origin[0], origin[1], s.lat, s.lon), 1)
        if s.distance_mi > radius_mi:
            continue
        if needs.pets and s.pets == "no":
            continue
        if needs.wheelchair and s.ada == "no":
            continue
        if s.kind == "special_needs" and not needs.special_needs_shelter:
            continue
        out.append(s)
    return sorted(out, key=lambda s: (
        s.status != "open",
        not (needs.special_needs_shelter and s.kind == "special_needs"),
        needs.pets and s.pets != "yes",
        s.distance_mi,
    ))
