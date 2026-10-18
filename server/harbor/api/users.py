"""ZIP preview, sign-up, the current user and accounts."""

from fastapi import APIRouter, Path
from sqlmodel import Session

from harbor.bank import NessieError, from_dollars
from harbor.clock import iso
from harbor.deps import BankDep, ClockDep, SessionDep, UserDep
from harbor.errors import HarborError
from harbor.geo import lookup_zip
from harbor.models import DEFAULT_SETTINGS, Household, User
from harbor.provisioning import provision_user, user_accounts
from harbor.schemas import AccountOut, CreateUser, HouseholdModel, UserOut, UserPatch, ZipOut

router = APIRouter(tags=["users"])


def zip_or_400(zip_code: str, field: str = "zip") -> dict:
    place = lookup_zip(zip_code)
    if place is None:
        raise HarborError(
            400,
            "zip_not_supported",
            f"We don't have a location for ZIP {zip_code}. PO-box ZIPs aren't supported, "
            "so try the ZIP of your street address.",
            {field: "Unknown ZIP"},
        )
    return place


def user_out(session: Session, user: User) -> UserOut:
    return UserOut(
        id=user.id,
        name=user.name,
        zip=user.zip,
        location={"lat": user.lat, "lon": user.lon},
        location_source=user.location_source,
        household=HouseholdModel.model_validate(session.get(Household, user.id).model_dump()),
        settings=user.settings,
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
    await provision_user(session, bank, user, household, now)
    return user


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
        user.settings = {**user.settings, **changes}
    session.add(user)
    session.commit()
    session.refresh(user)
    return user_out(session, user)


@router.get("/me/accounts", response_model=list[AccountOut])
async def get_accounts(user: UserDep, session: SessionDep, bank: BankDep, clock: ClockDep) -> list[AccountOut]:
    """Live Nessie balances; the cached ones (with `balance_synced_at`) when Nessie is down."""
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
