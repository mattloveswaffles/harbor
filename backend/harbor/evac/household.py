"""Household checklists and budget effects for kids, older adults, medical needs, pets and no car.

Pure rules: a `Household` in; rooms, budget lines, route needs, shelter/lodging filters,
checklists and advice cards out. Checklist items cite Ready.gov pages. Amounts marked
"Harbor estimate" are our own heuristics, not sourced figures, and say so in their labels.
Phone numbers are Hillsborough County's (the Milton demo); live mode looks them up per county.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal

PEOPLE_PER_ROOM = 4                    # 2 queen beds; confirm with each hotel
CHILD_MEAL_FACTOR = 0.75               # Harbor estimate: children eat ~3/4 of the GSA meal rate
PET_FEE_PER_NIGHT_CENTS = 2_500        # Harbor estimate; hotels charge roughly $25-75
SUPPLIES_BASE_CENTS = 3_000            # Harbor estimate: kit top-up (batteries, chargers, first aid)
SUPPLIES_PER_PERSON_DAY_CENTS = 1_000  # Harbor estimate: water and snacks on the road
INFANT_SUPPLIES_PER_DAY_CENTS = 1_500  # Harbor estimate: formula, diapers, wipes
MAX_DRIVE_HOURS_CAREFUL = 6            # Harbor estimate for older adults and medical needs
REST_STOP_HOURS_WITH_KIDS = 2          # Harbor estimate
EARLY_LEAVE_EXTRA_HOURS = 3            # on top of the normal 3 h buffer

READY_KIT = "https://www.ready.gov/kit"
READY_PETS = "https://www.ready.gov/pets"
READY_OLDER = "https://www.ready.gov/older-adults"
READY_DISABILITY = "https://www.ready.gov/disability"
READY_EVACUATION = "https://www.ready.gov/evacuation"


@dataclass(frozen=True)
class Pet:
    type: str
    count: int = 1


@dataclass(frozen=True)
class Household:
    adults: int = 1
    children_ages: tuple[int, ...] = ()
    seniors: int = 0
    pets: tuple[Pet, ...] = ()
    mobility: Literal["none", "walker", "wheelchair"] = "none"
    power_dependent_device: bool = False
    oxygen: bool = False
    dialysis: bool = False
    refrigerated_meds: bool = False
    has_car: bool = True
    home_type: Literal["site_built", "mobile"] = "site_built"
    evac_zone: str = "unsure"  # A-E, none or unsure

    @property
    def people(self) -> int:
        return self.adults + self.seniors + len(self.children_ages)

    @property
    def pet_count(self) -> int:
        return sum(p.count for p in self.pets)

    @property
    def has_infant(self) -> bool:
        return any(age < 2 for age in self.children_ages)

    @property
    def medical(self) -> bool:
        return self.power_dependent_device or self.oxygen or self.dialysis or self.refrigerated_meds


@dataclass(frozen=True)
class BudgetLine:
    label: str
    amount_cents: int
    source: str


@dataclass(frozen=True)
class RouteNeeds:
    drives: bool
    max_drive_hours_per_day: int | None
    rest_stop_every_hours: int | None
    extra_leave_buffer_hours: int
    prefer_regional_destination: bool  # tier B: outside the cone, not just the evacuation zone


@dataclass(frozen=True)
class PlaceFilter:
    pets: bool
    wheelchair: bool
    ground_floor: bool
    fridge: bool
    special_needs_shelter: bool


@dataclass(frozen=True)
class Checklist:
    need: str
    items: tuple[str, ...]
    source_url: str


@dataclass(frozen=True)
class AdviceCard:
    kind: str
    title: str
    text: str
    phone: str | None = None
    url: str | None = None
    deadline_hours_before_landfall: int | None = None


@dataclass
class HouseholdGuide:
    needs: list[str]
    rooms: int
    route: RouteNeeds
    shelter_filter: PlaceFilter
    checklists: list[Checklist] = field(default_factory=list)
    advice: list[AdviceCard] = field(default_factory=list)
    evacuation_reasons: list[str] = field(default_factory=list)


def rooms_needed(h: Household) -> int:
    return max(1, math.ceil(h.people / PEOPLE_PER_ROOM))


def meal_units(h: Household) -> float:
    return h.adults + h.seniors + CHILD_MEAL_FACTOR * len(h.children_ages)


def needs(h: Household) -> list[str]:
    out = ["everyone"]
    if h.children_ages:
        out.append("kids")
    if h.has_infant:
        out.append("infants")
    if h.seniors:
        out.append("seniors")
    if h.medical:
        out.append("medical")
    if h.mobility != "none":
        out.append("disability")
    if h.pets:
        out.append("pets")
    if not h.has_car:
        out.append("no_car")
    return out


def evacuation_reasons(h: Household) -> list[str]:
    """Reason codes that make evacuating the right call for this household."""
    reasons = []
    if h.home_type == "mobile":
        reasons.append("MOBILE_HOME")  # mobile homes are always told to evacuate
    if h.evac_zone in ("A", "B", "C", "D", "E"):
        reasons.append(f"ZONE_{h.evac_zone}")
    if h.power_dependent_device or h.oxygen or h.dialysis:
        reasons.append("POWER_OR_MEDICAL")
    return reasons


def route_needs(h: Household) -> RouteNeeds:
    careful = h.seniors > 0 or h.medical or h.mobility != "none"
    early = h.power_dependent_device or h.oxygen or h.dialysis or h.seniors > 0
    return RouteNeeds(
        drives=h.has_car,
        max_drive_hours_per_day=MAX_DRIVE_HOURS_CAREFUL if careful else None,
        rest_stop_every_hours=REST_STOP_HOURS_WITH_KIDS if h.children_ages else None,
        extra_leave_buffer_hours=EARLY_LEAVE_EXTRA_HOURS if early else 0,
        prefer_regional_destination=h.home_type == "mobile" or h.power_dependent_device or h.oxygen or h.dialysis,
    )


def place_filter(h: Household) -> PlaceFilter:
    return PlaceFilter(
        pets=bool(h.pets),
        wheelchair=h.mobility == "wheelchair",
        ground_floor=h.mobility != "none" or h.seniors > 0,
        fridge=h.refrigerated_meds or h.has_infant,
        special_needs_shelter=h.medical or h.mobility != "none",
    )


def budget_lines(h: Household, days: int, nights: int, meals_rate_cents: int, meals_source: str) -> list[BudgetLine]:
    """Food, pets and supplies lines. Lodging and fuel come from the lodging and route modules."""
    who = f"{h.adults + h.seniors} adult{'s' if h.adults + h.seniors != 1 else ''}"
    if h.children_ages:
        who += f" + {len(h.children_ages)} child{'ren' if len(h.children_ages) != 1 else ''}"
    lines = [
        BudgetLine(f"Food and water: {who}, {days} days",
                   round(meals_rate_cents * meal_units(h) * days), meals_source),
    ]
    if h.pets:
        kinds = ", ".join(f"{p.count} {p.type}{'s' if p.count != 1 else ''}" if p.count != 1 else p.type for p in h.pets)
        lines.append(BudgetLine(f"Pets: {kinds}, {nights} nights (Harbor estimate)",
                                PET_FEE_PER_NIGHT_CENTS * h.pet_count * nights, "household"))
    supplies = SUPPLIES_BASE_CENTS + SUPPLIES_PER_PERSON_DAY_CENTS * h.people * days
    if h.has_infant:
        supplies += INFANT_SUPPLIES_PER_DAY_CENTS * days
    lines.append(BudgetLine("Supplies: kit, water, chargers (Harbor estimate)", supplies, "household"))
    return lines


def checklists(h: Household) -> list[Checklist]:
    n = needs(h)
    out = [Checklist("everyone", (
        "1 gallon of water per person per day for several days",
        "Non-perishable food",
        "Battery or hand-crank radio, flashlight, spare batteries",
        "Phone chargers and a backup battery",
        "Copies of IDs, insurance and bank details in a waterproof bag",
        "Cash in small bills",
    ), READY_KIT)]
    if "kids" in n:
        out.append(Checklist("kids", ("Comfort items and games", "Snacks and drinks", "Children's medicines"), READY_KIT))
    if "infants" in n:
        out.append(Checklist("infants", ("Formula and bottles", "Diapers and wipes", "Diaper cream"), READY_KIT))
    if "seniors" in n:
        out.append(Checklist("seniors", (
            "Medicines and a written list of drugs, doses and allergies",
            "Copies of Medicare, Medicaid and insurance cards",
            "Glasses, hearing aids and other assistive devices",
            "A support contact who knows your plan",
        ), READY_OLDER))
    if "medical" in n or "disability" in n:
        items = ["Several days of medicines", "Contact details for your doctors and pharmacy"]
        if h.refrigerated_meds:
            items.append("A cooler and ice packs for refrigerated medicines")
        if h.oxygen:
            items.append("Backup oxygen; call your oxygen supplier before you leave")
        if h.power_dependent_device:
            items.append("Backup power for your device and its charger")
        if h.mobility == "wheelchair":
            items.append("Spare wheelchair battery or a manual chair")
        out.append(Checklist("medical", tuple(items), READY_DISABILITY))
    if "pets" in n:
        out.append(Checklist("pets", (
            "A sturdy carrier for each pet",
            "Collar, leash and ID tags",
            "7 days of food, water and medicines",
            "Vaccination records and a recent photo of you with your pet",
        ), READY_PETS))
    return out


def advice_cards(h: Household) -> list[AdviceCard]:
    cards = [AdviceCard("official_orders", "Follow local officials",
                        "If officials say evacuate, go. Leave early enough to avoid being trapped.",
                        url=READY_EVACUATION)]
    if not h.has_car:
        cards.append(AdviceCard(
            "no_car", "Getting out without a car",
            "Hillsborough County can arrange a ride to a shelter. Call early: transport stops once winds rise.",
            phone="(813) 236-3800"))
    if h.medical or h.mobility != "none":
        cards.append(AdviceCard(
            "special_needs_shelter", "Special-needs shelters",
            "Register with the county special-needs shelter program. Bring a caregiver, your medicines "
            "and supplies. Registration doesn't guarantee a space.",
            phone="(813) 307-8063", deadline_hours_before_landfall=72))
    if h.dialysis or h.power_dependent_device:
        cards.append(AdviceCard(
            "leave_early_medical", "Plan with your doctor and leave early",
            "Special-needs shelters can't provide dialysis or full ventilator support. "
            "Ask your clinic for its emergency plan and a backup provider near your destination."))
    if h.medical or h.seniors:
        cards.append(AdviceCard(
            "early_refill", "Refill prescriptions early",
            "Under a hurricane warning, Florida law (s. 252.358) lets you refill prescriptions early, "
            "for up to 30 days."))
    if h.pets:
        cards.append(AdviceCard(
            "pets", "Not every shelter or hotel takes pets",
            "Use a pet-friendly shelter, or call the hotel to confirm before you go. "
            "Hillsborough's pet line is 813-301-PETS.", phone="813-301-7387"))
    return cards


def guide(h: Household) -> HouseholdGuide:
    return HouseholdGuide(
        needs=needs(h),
        rooms=rooms_needed(h),
        route=route_needs(h),
        shelter_filter=place_filter(h),
        checklists=checklists(h),
        advice=advice_cards(h),
        evacuation_reasons=evacuation_reasons(h),
    )
