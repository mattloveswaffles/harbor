"""Hotels and motels from OpenStreetMap, priced with GSA per-diem estimates and filtered by household needs.

No free hotel API with real prices exists any more, so Harbor never claims a price or that a room
is free: every option says "Estimated cost. Call to confirm availability." The nightly estimate
is the GSA per-diem lodging rate for the destination and month, times the chosen band.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from harbor.evac.destination import Destination
from harbor.evac.household import PlaceFilter
from harbor.evac.route import maps_links

DATA = Path(__file__).resolve().parents[2] / "data" / "evac"
BANDS = {"economy": 0.75, "standard": 1.0, "comfort": 1.3}  # Harbor estimate, not sourced
GOUGING_MULTIPLE = 2.0  # Harbor heuristic: a quote over 2x the estimate gets the price-gouging card
NOTE = "Estimated cost. Call to confirm availability."


@dataclass
class LodgingPlan:
    band: str
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
        return {"band": self.band, "nights": self.nights, "rooms": self.rooms,
                "nightly_estimate_cents": self.nightly_estimate_cents, "estimate_source": self.estimate_source,
                "options": self.options, "attribution": self.attribution}


@lru_cache
def _snapshot() -> dict:
    path = DATA / "lodging.json"
    return json.loads(path.read_text(encoding="utf-8"))["by_destination"] if path.exists() else {}


def nightly_estimate(dest: Destination, band: str = "standard") -> tuple[int, str]:
    cents = round(dest.lodging_cents * BANDS[band])
    basis = dest.basis + ("" if band == "standard" else f", × {BANDS[band]} for {band} (Harbor estimate)")
    return cents, basis


def plan_lodging(dest: Destination, origin: tuple[float, float], nights: int, rooms: int,
                 needs: PlaceFilter, band: str = "standard", limit: int = 6) -> LodgingPlan:
    cents, basis = nightly_estimate(dest, band)
    options = []
    for p in _snapshot().get(dest.id, []):
        if needs.pets and p["pets"] == "no":
            continue
        if needs.wheelchair and p["wheelchair"] == "no":
            continue
        options.append({
            "id": p["id"], "name": p["name"], "type": p["type"],
            "pets": "call_to_confirm" if needs.pets and p["pets"] == "unknown" else p["pets"],
            "wheelchair": "call_to_confirm" if needs.wheelchair and p["wheelchair"] == "unknown" else p["wheelchair"],
            "location": {"lat": p["lat"], "lon": p["lon"]}, "phone": p.get("phone"), "website": p.get("website"),
            "source": "osm", "note": NOTE, "links": maps_links(origin[0], origin[1], p["lat"], p["lon"]),
        })
    options.sort(key=lambda o: (needs.pets and o["pets"] != "yes", needs.wheelchair and o["wheelchair"] != "yes",
                                o["phone"] is None))
    return LodgingPlan(band, nights, rooms, cents, basis, options[:limit])


def looks_like_gouging(quote_cents: int, estimate_cents: int) -> bool:
    return quote_cents > GOUGING_MULTIPLE * estimate_cents
