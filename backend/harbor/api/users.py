"""ZIP preview, sign-up, the current user, household and accounts."""

from fastapi import APIRouter, Depends, Path
from sqlmodel import Session

from harbor.bank import NessieError, from_dollars
from harbor.clock import iso
from harbor.deps import BankDep, ClockDep, SessionDep, UserDep, require_demo
from harbor.errors import HarborError
from harbor.geo import lookup_zip
from harbor.models import DEFAULT_SETTINGS, Household, User, new_id
from harbor.schemas import AccountOut, CreateUser, HouseholdModel, HouseholdPatch, UserOut, UserPatch, ZipOut
from harbor.seed import provision_user, user_accounts

router = APIRouter(tags=["users"])


def zip_or_400(zip_code: str, field: str = "zip") -> dict:
    place = lookup_zip(zip_code)
    if place is None:
        raise HarborError(
            400,
            "zip_not_supported",
            f"We don't have a location for ZIP {zip_code}. Harbor covers Florida home ZIPs; "
            "PO-box ZIPs aren't supported, so try the ZIP of your street address.",
            {field: "Unknown ZIP"},
        )
    return place


def user_out(session: Session, user: User) -> UserOut:
    household = session.get(Household, user.id) or Household(user_id=user.id)
    return UserOut(
        id=user.id,
        name=user.name,
        zip=user.zip,
        location={"lat": user.lat, "lon": user.lon},
        location_source=user.location_source,
        household=HouseholdModel(
            adults=household.adults,
            children_ages=household.children_ages or [],
            seniors=household.seniors,
            pets=household.pets or [],
            mobility=household.mobility,
            medical=household.medical or {},
            has_car=household.has_car,
            home_type=household.home_type,
            evac_zone=household.evac_zone,
        ),
        settings={**DEFAULT_SETTINGS, **(user.settings or {})},
        nessie_customer_id=user.nessie_customer_id,
        risk_level=user.risk_level,
    )


@router.get("/zip/{zip}", response_model=ZipOut)
def get_zip(zip: str = Path(pattern=r"^\d{5}$", examples=["33602"])) -> dict:
    return zip_or_400(zip)


async def new_user(body: CreateUser, session: Session, bank, now) -> User:
    """Create a user with their Nessie customer, accounts and starter portfolio. Caller commits."""
    place = zip_or_400(body.zip)
    user = User(
        id=new_id("usr"),
        name=body.name.strip(),
        zip=body.zip,
        lat=body.location.lat if body.location else place["lat"],
        lon=body.location.lon if body.location else place["lon"],
        location_source="gps" if body.location else "zcta",
        settings=dict(DEFAULT_SETTINGS),
        created_at=now,
        risk_changed_at=now,
    )
    household = (body.household or HouseholdModel()).model_dump()
    await provision_user(session, bank, user, household, now, city=place["city"])
    return user


@router.post("/users", response_model=UserOut, status_code=201, dependencies=[Depends(require_demo)])
async def create_user(body: CreateUser, session: SessionDep, bank: BankDep, clock: ClockDep) -> UserOut:
    """Demo only: a user without a password, used with the X-User-Id header. Real accounts use
    POST /auth/signup."""
    user = await new_user(body, session, bank, clock.now())
    session.commit()
    session.refresh(user)
    return user_out(session, user)


@router.get("/me", response_model=UserOut)
def get_me(user: UserDep, session: SessionDep) -> UserOut:
    return user_out(session, user)


@router.patch("/me", response_model=UserOut)
def patch_me(body: UserPatch, user: UserDep, session: SessionDep) -> UserOut:
    if body.name is not None:
        user.name = body.name.strip()
    if body.zip is not None and body.zip != user.zip:
        place = zip_or_400(body.zip)
        user.zip = body.zip
        user.lat, user.lon, user.location_source = place["lat"], place["lon"], "zcta"
    if body.location is not None:
        user.lat, user.lon, user.location_source = body.location.lat, body.location.lon, "gps"
    if body.settings is not None:
        changes = body.settings.model_dump(exclude_none=True)
        user.settings = {**DEFAULT_SETTINGS, **(user.settings or {}), **changes}
    session.add(user)
    session.commit()
    session.refresh(user)
    return user_out(session, user)


@router.patch("/me/household", response_model=UserOut)
def patch_household(body: HouseholdPatch, user: UserDep, session: SessionDep) -> UserOut:
    # TODO(H14-20): re-run the plan and the evacuation guide when one exists.
    household = session.get(Household, user.id) or Household(user_id=user.id)
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(household, field, value)
    session.add(household)
    session.commit()
    return user_out(session, user)


@router.get("/me/accounts", response_model=list[AccountOut])
async def get_accounts(user: UserDep, session: SessionDep, bank: BankDep, clock: ClockDep) -> list[AccountOut]:
    """Live Nessie balances. If Nessie can't be reached, the last balances read are returned with
    their `balance_synced_at`, so the UI can show "as of"."""
    accounts = user_accounts(session, user.id)
    now = clock.now()
    for acct in accounts:
        if not acct.nessie_id:
            continue
        try:
            live = await bank.get_account(acct.nessie_id)
        except NessieError:
            break  # bank down: keep every cached balance
        if live is not None:
            acct.balance_cents = from_dollars(live.get("balance", 0))
            acct.balance_synced_at = now
            session.add(acct)
    session.commit()
    return [
        AccountOut(
            id=a.id,
            nessie_id=a.nessie_id,
            type=a.type,
            nessie_type=a.nessie_type,
            nickname=a.nickname,
            balance_cents=a.balance_cents,
            balance_synced_at=iso(a.balance_synced_at),
        )
        for a in accounts
    ]
