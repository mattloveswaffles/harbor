"""Picks 2-3 safe destinations outside the cone and evacuation zones, and the leave_by time.

Pure apart from the `route_for` callable it's given. Two tiers (see docs/DESIGN.md §1.4):

- Tier A, local: a nearby inland town (under an hour's normal drive). People in surge zones often
  only need to go "tens of miles", so this suits a sturdy home in an evacuation zone.
- Tier B, regional: outside the forecast cone plus a 40 km margin. Recommended for mobile homes,
  Category 4+ storms, a major hurricane (Category 3+) whose cone covers the home, and
  power-dependent medical needs.

Score = evacuation drive time + cone overlap penalty + "heading toward the storm" penalty
        - hotel hub bonus. Lower is better.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Callable

from shapely.geometry import Point, shape

from harbor.evac.household import Household, evacuation_reasons, route_needs
from harbor.evac.route import Route, cone_overlap_pct

DATA = Path(__file__).resolve().parents[2] / "data" / "evac"
TIER_A_MAX_MIN = 60
CONE_MARGIN_DEG = 0.36          # about 40 km
LEAVE_BUFFER = timedelta(hours=3)
OVERLAP_PENALTY_PER_PCT = 3     # minutes of score per % of the route inside the cone
TOWARD_TRACK_PENALTY = 60
HUB_BONUS = 30


@dataclass(frozen=True)
class Destination:
    id: str
    name: str
    lat: float
    lon: float
    corridor: str
    hotel_hub: bool
    lodging_cents: int
    meals_cents: int
    basis: str
    rate_checked: bool


@dataclass
class Option:
    destination: Destination
    tier: str
    route: Route | None
    outside_cone: bool
    cone_overlap_pct: int | None
    score: float
    leave_by: datetime | None
    feasible: bool
    recommended: bool = False


@dataclass
class Decision:
    action: str              # evacuate | shelter_in_place | use_public_shelter
    tier: str | None
    reason_codes: list[str]
    options: list[Option] = field(default_factory=list)

    @property
    def chosen(self) -> Option | None:
        return next((o for o in self.options if o.recommended), self.options[0] if self.options else None)


@lru_cache
def load_destinations() -> tuple[Destination, ...]:
    rows = json.loads((DATA / "destinations.json").read_text(encoding="utf-8"))
    return tuple(Destination(r["id"], r["name"], r["lat"], r["lon"], r["corridor"], r["hotel_hub"],
                             r["lodging_cents"], r["meals_cents"], r["basis"], r.get("rate_checked", False))
                 for r in rows)


def _to_shape(geo):
    if geo is None:
        return None
    if isinstance(geo, dict):
        if geo.get("type") == "FeatureCollection":
            from shapely.ops import unary_union
            return unary_union([shape(f["geometry"]) for f in geo["features"]])
        if geo.get("type") == "Feature":
            return shape(geo["geometry"])
        return shape(geo)
    return geo


def decide(
    origin: tuple[float, float],
    household: Household,
    *,
    cone=None,
    track=None,
    category: int | None = None,
    ts_winds_eta: datetime | None = None,
    now: datetime | None = None,
    route_for: Callable[[Destination], Route | None],
    candidates: tuple[Destination, ...] | None = None,
    choose: str | None = None,
) -> Decision:
    candidates = candidates if candidates is not None else load_destinations()
    needs = route_needs(household)
    reasons = evacuation_reasons(household)
    cone_shape, track_shape = _to_shape(cone), _to_shape(track)
    if category is not None and category >= 4:
        reasons.append("CAT4_PLUS")
    elif category is not None and category >= 3 and cone_shape is not None and cone_shape.contains(Point(origin[1], origin[0])):
        reasons.append("MAJOR_HURRICANE_IN_CONE")  # a nearby town would still be in the storm's core
    regional = needs.prefer_regional_destination or bool({"CAT4_PLUS", "MAJOR_HURRICANE_IN_CONE"} & set(reasons))

    if not household.has_car:
        return Decision("use_public_shelter", None, [*reasons, "NO_CAR"])

    buffered = cone_shape.buffer(CONE_MARGIN_DEG) if cone_shape is not None else None
    origin_pt = Point(origin[1], origin[0])
    options: list[Option] = []
    for d in candidates:
        r = route_for(d)
        if r is None:
            continue
        pt = Point(d.lon, d.lat)
        outside = cone_shape is None or not cone_shape.contains(pt)
        tier = "B" if (buffered is None or not buffered.contains(pt)) else ("A" if r.drive_time_min_normal <= TIER_A_MAX_MIN else None)
        if tier is None:
            continue
        if needs.max_drive_hours_per_day and r.drive_time_min_normal > needs.max_drive_hours_per_day * 60:
            continue
        overlap = cone_overlap_pct(r.geometry, cone_shape) or 0
        toward = track_shape is not None and pt.distance(track_shape) < origin_pt.distance(track_shape)
        score = (r.drive_time_min_evac + OVERLAP_PENALTY_PER_PCT * overlap
                 + (TOWARD_TRACK_PENALTY if toward else 0) - (HUB_BONUS if d.hotel_hub else 0))
        leave_by = None
        feasible = True
        if ts_winds_eta is not None:
            extra = timedelta(hours=needs.extra_leave_buffer_hours)
            leave_by = ts_winds_eta - timedelta(minutes=r.drive_time_min_evac) - LEAVE_BUFFER - extra
            feasible = now is None or leave_by >= now
        options.append(Option(d, tier, r, outside, overlap, score, leave_by, feasible))

    if not options:
        return Decision("use_public_shelter", None, [*reasons, "NO_SAFE_DESTINATION"])

    def best(tier: str | None):
        pool = [o for o in options if (tier is None or o.tier == tier) and o.feasible] or \
               [o for o in options if tier is None or o.tier == tier]
        return sorted(pool, key=lambda o: o.score)

    tier_b, tier_a = best("B"), best("A")
    main_tier = "B" if (regional and tier_b) or not tier_a else "A"
    ranked = tier_b if main_tier == "B" else tier_a
    other = tier_a if main_tier == "B" else tier_b
    picked = ranked[:2] + other[:1]
    if choose:
        chosen = next((o for o in options if o.destination.id == choose), None)
        if chosen and chosen not in picked:
            picked = [chosen, *picked[:2]]
    for o in picked:
        o.recommended = o.destination.id == (choose or picked[0].destination.id)
    action = "evacuate" if reasons else "shelter_in_place"
    return Decision(action, main_tier, reasons, picked)
