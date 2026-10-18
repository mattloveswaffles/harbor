"""Shelters from FEMA Open Shelters (ESF6-SS, formerly NSS): live, or Hillsborough County's Milton shelters recorded
as FEMA records for the replay. Both go through the same parser. Pets, ADA and wheelchair access are yes/no/unknown
and only a known "no" filters. Special-needs shelters go only, and first, to households that need them.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path

import httpx

from harbor.evac.household import PlaceFilter
from harbor.evac.route import maps_links
from harbor.sources.sensors import miles_between

DATA = Path(__file__).resolve().parents[2] / "data" / "evac"
FEMA_URL = "https://gis.fema.gov/arcgis/rest/services/NSS/OpenShelters/FeatureServer/0/query"
NO_PETS = ("NONE", "SERVICE ANIMALS ONLY")


@dataclass
class Shelter:
    id: str
    name: str
    address: str | None
    city: str | None
    state: str | None
    zip: str | None
    status: str  # open | full | closed
    capacity: int | None  # evacuation capacity
    population: int | None  # people sheltered now
    org: str | None  # who runs it
    hours: str | None
    kind: str  # general | special_needs
    pets: str  # yes | no | unknown
    ada: str
    wheelchair: str
    lat: float
    lon: float
    source: str
    distance_mi: float | None = None

    def to_api(self, origin: tuple[float, float]) -> dict:
        data = asdict(self)
        lat, lon = data.pop("lat"), data.pop("lon")
        return data | {"location": {"lat": lat, "lon": lon}, "links": maps_links(origin[0], origin[1], lat, lon)}


def _tri(value) -> str:
    v = str(value or "").strip().lower()
    return "yes" if v in ("yes", "y", "true", "1") else "no" if v in ("no", "n", "false", "0") else "unknown"


def from_fema(a: dict, source: str, status: str | None = None) -> Shelter:
    """One FEMA Open Shelters record."""
    pets = str(a.get("pet_accommodations_code") or "").strip().upper()
    code = str(a.get("subfacility_code") or "").upper()
    hours = " to ".join(str(a[k]) for k in ("hours_open", "hours_close") if a.get(k))
    return Shelter(
        id=str(a["shelter_id"]),
        name=a.get("shelter_name") or "Shelter",
        address=a.get("address"),
        city=a.get("city"),
        state=a.get("state"),
        zip=a.get("zip"),
        status=status or str(a.get("shelter_status") or "open").lower(),
        capacity=a.get("evacuation_capacity"),
        population=a.get("total_population"),
        org=a.get("org_name"),
        hours=hours or None,
        kind="special_needs" if "SPECIAL" in code or "MEDICAL" in code else "general",
        pets="unknown" if not pets else "no" if pets in NO_PETS else "yes",
        ada=_tri(a.get("ada_compliant")),
        wheelchair=_tri(a.get("wheelchair_accessible")),
        lat=a["latitude"],
        lon=a["longitude"],
        source=source,
    )


@lru_cache
def _recorded() -> list[dict]:
    return [
        f["attributes"] for f in json.loads((DATA / "shelters_milton.json").read_text(encoding="utf-8"))["features"]
    ]


def demo_shelters(now: datetime) -> list[Shelter]:
    """The Milton shelters as FEMA listed them at `now` in the replay."""
    out = []
    for a in _recorded():
        full = a["full_from"] is not None and datetime.fromisoformat(a["full_from"]) <= now
        out.append(from_fema(a, "FEMA Open Shelters (Milton 2024)", "full" if full else None))
    return out


def fema_shelters(lat: float, lon: float, radius_mi: float = 60, client: httpx.Client | None = None) -> list[Shelter]:
    own = client is None
    client = client or httpx.Client(timeout=15)
    try:
        res = client.get(
            FEMA_URL,
            params={
                "where": "shelter_status='OPEN'",
                "geometry": f"{lon},{lat}",
                "geometryType": "esriGeometryPoint",
                "inSR": 4326,
                "distance": radius_mi,
                "units": "esriSRUnit_StatuteMile",
                "outFields": "*",
                "f": "json",
            },
        )
        res.raise_for_status()
        return [from_fema(f["attributes"], "FEMA Open Shelters") for f in res.json().get("features", [])]
    finally:
        if own:
            client.close()


def rank(
    shelters: list[Shelter], origin: tuple[float, float], needs: PlaceFilter, radius_mi: float = 60
) -> list[Shelter]:
    out = []
    for s in shelters:
        s.distance_mi = round(miles_between(origin[0], origin[1], s.lat, s.lon), 1)
        if s.distance_mi > radius_mi:
            continue
        if needs.pets and s.pets == "no":
            continue
        if needs.wheelchair and "no" in (s.ada, s.wheelchair):
            continue
        if s.kind == "special_needs" and not needs.special_needs_shelter:
            continue
        out.append(s)
    return sorted(
        out,
        key=lambda s: (
            s.status != "open",
            not (needs.special_needs_shelter and s.kind == "special_needs"),
            needs.pets and s.pets != "yes",
            s.distance_mi,
        ),
    )
