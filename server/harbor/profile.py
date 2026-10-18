"""The household profile behind the Settings popup: people, medical needs, vehicle, places and preferences.

The engine still reads models.Household; `save` keeps it in sync so routes, shelters and budgets follow the profile.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field
from sqlmodel import Session

from harbor.evac.destination import load_destinations
from harbor.models import Household, Profile, User


class Personal(BaseModel):
    name: str = ""
    dob: str = ""
    phone: str = ""
    email: str = ""
    language: Literal["en", "es"] = "en"


class Home(BaseModel):
    address: str = ""
    home_type: Literal["house", "apartment", "mobile"] = "house"
    evac_zone: str = "unsure"  # A-E | none | unsure


class Person(BaseModel):
    name: str
    age: int | None = Field(default=None, ge=0, le=120)
    relation: str = ""


class Pet(BaseModel):
    name: str = ""
    type: str = "dog"
    weight_lb: int | None = Field(default=None, ge=0)
    notes: str = ""


class Medication(BaseModel):
    name: str
    dose: str = ""
    person: str = ""
    schedule: str = ""
    days_left: int | None = Field(default=None, ge=0)


class Medical(BaseModel):
    medications: list[Medication] = []
    equipment: list[str] = []  # "CPAP", "Oxygen concentrator"
    needs_power: bool = False
    oxygen: bool = False
    dialysis: bool = False
    refrigerated_meds: bool = False
    mobility: Literal["none", "walker", "wheelchair"] = "none"
    allergies: str = ""
    pharmacy: str = ""


class Vehicle(BaseModel):
    has_car: bool = True
    make_model: str = ""
    mpg: float | None = Field(default=None, gt=0, le=150)
    tank_gal: float | None = Field(default=None, gt=0, le=60)
    fuel_level: float = Field(default=0.5, ge=0, le=1)
    seats: int | None = Field(default=None, ge=1, le=15)
    towing: bool = False


class Place(BaseModel):
    label: str
    address: str = ""
    kind: Literal["destination", "work", "school", "other"] = "other"


class Contact(BaseModel):
    name: str
    relation: str = ""
    phone: str = ""
    gets_plan: bool = False


class Alerts(BaseModel):
    sms: bool = True
    email: bool = True
    push: bool = False
    quiet_hours: bool = True
    tell_contacts: bool = True


class Privacy(BaseModel):
    share_location: bool = True
    medical_for_planning_only: bool = True


class ProfileData(BaseModel):
    personal: Personal = Personal()
    home: Home = Home()
    people: list[Person] = []
    pets: list[Pet] = []
    medical: Medical = Medical()
    vehicle: Vehicle = Vehicle()
    places: list[Place] = []
    contacts: list[Contact] = []
    alerts: Alerts = Alerts()
    privacy: Privacy = Privacy()

    @property
    def range_mi(self) -> float | None:
        """Miles on the gas in the tank now (None without mpg and tank size)."""
        v = self.vehicle
        return round(v.mpg * v.tank_gal * v.fuel_level) if v.has_car and v.mpg and v.tank_gal else None


def _from_household(user: User, hh: Household) -> ProfileData:
    """A starting profile for users who never opened Settings."""
    people = [Person(name=user.name, relation="you")]
    people += [Person(name=f"Adult {i + 2}") for i in range(max(hh.adults - 1, 0))]
    people += [Person(name=f"Child {i + 1}", age=age) for i, age in enumerate(hh.children_ages or [])]
    people += [Person(name=f"Senior {i + 1}", age=70) for i in range(hh.seniors)]
    med = hh.medical or {}
    return ProfileData(
        personal=Personal(name=user.name),
        home=Home(home_type="mobile" if hh.home_type == "mobile" else "house", evac_zone=hh.evac_zone),
        people=people,
        pets=[Pet(type=p.get("type", "pet")) for p in hh.pets or [] for _ in range(p.get("count", 1))],
        medical=Medical(
            needs_power=bool(med.get("power_dependent_device")),
            oxygen=bool(med.get("oxygen")),
            dialysis=bool(med.get("dialysis")),
            refrigerated_meds=bool(med.get("refrigerated_meds")),
            mobility=hh.mobility,
        ),
        vehicle=Vehicle(has_car=hh.has_car),
    )


def load(session: Session, user: User) -> ProfileData:
    row = session.get(Profile, user.id)
    if row and row.data:
        return ProfileData.model_validate(row.data)
    return _from_household(user, session.get(Household, user.id) or Household(user_id=user.id))


def preferred_destination(session: Session, user: User) -> str | None:
    """The engine's destination in the city of the family's own place to go (Rosa's house in Macon -> macon_ga)."""
    wanted = [p.address.lower() for p in load(session, user).places if p.kind == "destination"]
    for d in load_destinations():
        city = d.name.split(",")[0].lower()
        if any(city in w for w in wanted):
            return d.id
    return None


def choice(session: Session, user: User) -> str | None:
    """The destination the family picked on Route, else their own place to go."""
    return (user.settings or {}).get("evac_destination") or preferred_destination(session, user)


def save(session: Session, user: User, data: ProfileData, now: datetime) -> None:
    """Store the profile and mirror it onto Household and User. Caller commits."""
    row = session.get(Profile, user.id) or Profile(user_id=user.id)
    row.data, row.updated_at = data.model_dump(), now
    session.add(row)

    hh = session.get(Household, user.id) or Household(user_id=user.id)
    if data.people:
        ages = [p.age for p in data.people]
        hh.children_ages = sorted(a for a in ages if a is not None and a < 18)
        hh.seniors = sum(1 for a in ages if a is not None and a >= 65)
        hh.adults = len(ages) - len(hh.children_ages) - hh.seniors
    hh.pets = [{"type": t, "count": n} for t, n in Counter(p.type for p in data.pets).items()]
    m = data.medical
    hh.mobility = m.mobility
    hh.medical = {
        "power_dependent_device": m.needs_power,
        "oxygen": m.oxygen,
        "dialysis": m.dialysis,
        "refrigerated_meds": m.refrigerated_meds,
    }
    hh.has_car = data.vehicle.has_car
    hh.home_type = "mobile" if data.home.home_type == "mobile" else "site_built"
    hh.evac_zone = data.home.evac_zone
    session.add(hh)

    if data.personal.name.strip():
        user.name = data.personal.name.strip()
        session.add(user)
