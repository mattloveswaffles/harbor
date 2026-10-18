"""OpenStreetMap hotels priced by GSA per diem. Never claims a real price or a free room."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from harbor.evac.destination import Destination
from harbor.evac.household import PlaceFilter
from harbor.evac.route import maps_links

DATA = Path(__file__).resolve().parents[2] / "data" / "evac"
NOTE = "Estimated cost. Call to confirm availability."


@dataclass
class LodgingPlan:
    nights: int
    rooms: int
    nightly_estimate_cents: int
    estimate_source: str
    options: list[dict] = field(default_factory=list)
    attribution: str = "© OpenStreetMap contributors"

    @property
    def total_cents(self) -> int:
        return self.nightly_estimate_cents * self.rooms * self.nights

    def to_api(self) -> dict:
        return {
            "band": "standard",
            "nights": self.nights,
            "rooms": self.rooms,
            "nightly_estimate_cents": self.nightly_estimate_cents,
            "estimate_source": self.estimate_source,
            "options": self.options,
            "attribution": self.attribution,
        }


@lru_cache
def _snapshot() -> dict:
    path = DATA / "lodging.json"
    return json.loads(path.read_text(encoding="utf-8"))["by_destination"] if path.exists() else {}


def plan_lodging(
    dest: Destination,
    origin: tuple[float, float],
    nights: int,
    rooms: int,
    needs: PlaceFilter,
    limit: int = 6,
) -> LodgingPlan:
    options = []
    for p in _snapshot().get(dest.id, []):
        if needs.pets and p["pets"] == "no":
            continue
        if needs.wheelchair and p["wheelchair"] == "no":
            continue
        options.append(
            {
                "id": p["id"],
                "name": p["name"],
                "type": p["type"],
                "pets": "call_to_confirm" if needs.pets and p["pets"] == "unknown" else p["pets"],
                "wheelchair": "call_to_confirm"
                if needs.wheelchair and p["wheelchair"] == "unknown"
                else p["wheelchair"],
                "location": {"lat": p["lat"], "lon": p["lon"]},
                "phone": p.get("phone"),
                "website": p.get("website"),
                "source": "osm",
                "note": NOTE,
                "links": maps_links(origin[0], origin[1], p["lat"], p["lon"]),
            }
        )
    options.sort(
        key=lambda o: (
            needs.pets and o["pets"] != "yes",
            needs.wheelchair and o["wheelchair"] != "yes",
            o["phone"] is None,
        )
    )
    return LodgingPlan(nights, rooms, dest.lodging_cents, dest.basis, options[:limit])
