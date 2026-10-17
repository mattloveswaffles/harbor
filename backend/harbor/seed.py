"""Starting state for users: Nessie customer, three accounts and a sample T. Rowe Price ETF portfolio.

The demo persona is Maria Lopez (fictional), ZIP 33602 Tampa. Everything here is idempotent, so
POST /demo/persona and `python -m harbor.seed` can run any number of times.

Privacy: Nessie's enterprise routes let anyone read every customer, so Harbor never sends a real
person's name or address to Nessie. Signed-up users get a pseudonym ("Harbor" / "User usr_...")
and a placeholder street address; only fictional demo personas use a name.
"""

import asyncio
from dataclasses import dataclass
from datetime import date, datetime

from sqlmodel import Session, delete, select

from harbor.bank import Bank, NessieNotFound, from_dollars
from harbor.events import record
from harbor.models import DEFAULT_SETTINGS, Account, Bill, Event, Household, Lot, Move, Plan, User, new_id

MARIA_LAST_NAME = "Lopez (Harbor demo)"


@dataclass(frozen=True)
class StarterAccount:
    type: str  # Harbor type
    nessie_type: str
    nickname: str
    balance_cents: int  # whole dollars only: Nessie can't hold cents


STARTER_ACCOUNTS = (
    StarterAccount("checking", "Checking", "Everyday", 42000),
    StarterAccount("savings", "Savings", "Emergency fund", 50000),
    StarterAccount("brokerage_cash", "Savings", "Brokerage Settlement (Harbor)", 0),
)

# Sample portfolio for the demo, not a recommendation. TBUX is the "storm sleeve" sold first.
STARTER_LOTS = (
    ("TBUX", 7_200_000, 35800, date(2023, 3, 14)),
    ("TCAF", 50_000_000, 135500, date(2023, 9, 12)),
    ("TCAF", 30_000_000, 91200, date(2024, 2, 20)),
    ("TSPA", 40_000_000, 114000, date(2023, 11, 7)),
)

PERSONAS = {
    "maria": {
        "name": "Maria Lopez",
        "zip": "33602",
        "nessie_name": ("Maria", MARIA_LAST_NAME),
        "nessie_address": {
            "street_number": "100",
            "street_name": "Demo Harbor St",
            "city": "Tampa",
            "state": "FL",
            "zip": "33602",
        },
        "household": {
            "adults": 2,
            "children_ages": [7],
            "seniors": 0,
            "pets": [{"type": "dog", "count": 1}],
            "mobility": "none",
            "medical": {"power_dependent_device": False, "oxygen": False, "dialysis": False, "refrigerated_meds": False},
            "has_car": True,
            "home_type": "site_built",
            "evac_zone": "A",
        },
        # A fictional bill due during Milton, so the bill shield has something to move.
        "bills": [{"payee": "Sunshine Auto Insurance (demo)", "amount_cents": 18900, "due": date(2024, 10, 9)}],
    },
    # Second persona: shows the household rules. Fictional older couple in Sarasota (landfall was at
    # Siesta Key) in a mobile home, no car, one of them on home oxygen.
    "ruth": {
        "name": "Ruth Diaz",
        "zip": "34236",
        "nessie_name": ("Ruth", "Diaz (Harbor demo)"),
        "nessie_address": {
            "street_number": "200",
            "street_name": "Demo Palm Ave",
            "city": "Sarasota",
            "state": "FL",
            "zip": "34236",
        },
        "household": {
            "adults": 0,
            "children_ages": [],
            "seniors": 2,
            "pets": [],
            "mobility": "walker",
            "medical": {"power_dependent_device": False, "oxygen": True, "dialysis": False, "refrigerated_meds": True},
            "has_car": False,
            "home_type": "mobile",
            "evac_zone": "A",
        },
        "bills": [],
    },
}


def pseudonym_address(user: User, city: str) -> dict:
    return {"street_number": "1", "street_name": "Harbor Way", "city": city or "Unknown", "state": "FL", "zip": user.zip}


def starter_lots(user_id: str) -> list[Lot]:
    return [
        Lot(user_id=user_id, symbol=s, shares_micro=sh, cost_basis_cents=cb, acquired=acq) for s, sh, cb, acq in STARTER_LOTS
    ]


def user_accounts(session: Session, user_id: str) -> list[Account]:
    order = {a.type: i for i, a in enumerate(STARTER_ACCOUNTS)}
    accounts = session.exec(select(Account).where(Account.user_id == user_id)).all()
    return sorted(accounts, key=lambda a: order.get(a.type, 99))


async def ensure_customer(bank: Bank, user: User, first: str, last: str, address: dict) -> str:
    """Return a Nessie customer id that exists, reusing the stored or a same-named one."""
    if user.nessie_customer_id and await bank.get_customer(user.nessie_customer_id):
        return user.nessie_customer_id
    for cust in await bank.list_customers():
        if cust.get("first_name") == first and cust.get("last_name") == last:
            return cust["_id"]
    return (await bank.create_customer(first, last, address))["_id"]


async def ensure_accounts(session: Session, bank: Bank, user: User, now: datetime) -> list[Account]:
    """Match each Harbor account to a live Nessie account (by id, then nickname); create what's missing."""
    existing = {a.type: a for a in user_accounts(session, user.id)}
    nessie = await bank.list_accounts(user.nessie_customer_id)
    by_id = {a["_id"]: a for a in nessie}
    by_name = {(a.get("type"), a.get("nickname")): a for a in nessie}
    out = []
    for spec in STARTER_ACCOUNTS:
        acct = existing.get(spec.type) or Account(
            user_id=user.id,
            type=spec.type,
            nessie_type=spec.nessie_type,
            nickname=spec.nickname,
            starting_balance_cents=spec.balance_cents,
        )
        live = by_id.get(acct.nessie_id) or by_name.get((acct.nessie_type, acct.nickname))
        if live is None:
            live = await bank.create_account(
                user.nessie_customer_id, acct.nessie_type, acct.nickname, acct.starting_balance_cents // 100
            )
        acct.nessie_id = live["_id"]
        acct.balance_cents = from_dollars(live.get("balance", 0))
        acct.balance_synced_at = now
        session.add(acct)
        out.append(acct)
    return out


async def ensure_bills(session: Session, bank: Bank, user: User) -> None:
    """Create the persona's demo bills in Nessie (on checking) if they aren't there yet."""
    spec = PERSONAS.get(user.persona or "", {})
    if not spec.get("bills") or session.exec(select(Bill).where(Bill.user_id == user.id)).first():
        return
    checking = next(a for a in user_accounts(session, user.id) if a.type == "checking")
    for b in spec["bills"]:
        nessie_id = await bank.create_bill(checking.nessie_id, b["payee"], b["amount_cents"], b["due"],
                                           f"[harbor:bill] {b['payee']}")
        session.add(Bill(user_id=user.id, account_id=checking.id, nessie_id=nessie_id, payee=b["payee"],
                         amount_cents=b["amount_cents"], due_date=b["due"], original_due_date=b["due"]))


async def provision_user(
    session: Session, bank: Bank, user: User, household: dict, now: datetime, *, city: str = "", persona: dict | None = None
) -> User:
    """Create the Nessie customer, the three accounts and the starter portfolio. Caller commits."""
    session.add(user)
    session.flush()  # no ORM relationships, so insert the user before rows that point at it
    session.add(Household(user_id=user.id, **household))
    if persona:
        first, last = persona["nessie_name"]
        address = persona["nessie_address"]
    else:
        first, last, address = "Harbor", f"User {user.id}", pseudonym_address(user, city)
    user.nessie_customer_id = await ensure_customer(bank, user, first, last, address)
    await ensure_accounts(session, bank, user, now)
    for lot in starter_lots(user.id):
        session.add(lot)
    await ensure_bills(session, bank, user)
    return user


async def seed_persona(session: Session, bank: Bank, now: datetime, persona: str = "maria") -> User:
    """Return the persona's user, creating it (and repairing its Nessie side) as needed."""
    from harbor.geo import lookup_zip

    spec = PERSONAS[persona]
    user = session.exec(select(User).where(User.persona == persona)).first()
    if user is None:
        place = lookup_zip(spec["zip"])
        user = User(
            id=new_id("usr"),
            name=spec["name"],
            zip=spec["zip"],
            lat=place["lat"],
            lon=place["lon"],
            settings=dict(DEFAULT_SETTINGS),
            persona=persona,
            created_at=now,
            risk_changed_at=now,
        )
        await provision_user(session, bank, user, spec["household"], now, persona=spec)
    else:
        first, last = spec["nessie_name"]
        user.nessie_customer_id = await ensure_customer(bank, user, first, last, spec["nessie_address"])
        await ensure_accounts(session, bank, user, now)
        if not session.exec(select(Lot).where(Lot.user_id == user.id)).first():
            for lot in starter_lots(user.id):
                session.add(lot)
        await ensure_bills(session, bank, user)
        session.add(user)
    session.commit()
    session.refresh(user)
    return user


async def reset_user(session: Session, bank: Bank, user: User, now: datetime) -> None:
    """Put accounts, portfolio and plans back to the starting state. Caller commits.

    Nessie can't set a balance or bulk-delete, so each account is deleted and recreated.
    """
    if user.persona:
        spec = PERSONAS[user.persona]
        first, last = spec["nessie_name"]
        address = spec["nessie_address"]
    else:
        from harbor.geo import lookup_zip

        first, last = "Harbor", f"User {user.id}"
        address = pseudonym_address(user, (lookup_zip(user.zip) or {}).get("city", ""))
    user.nessie_customer_id = await ensure_customer(bank, user, first, last, address)
    for acct in user_accounts(session, user.id):
        if acct.nessie_id:
            try:
                await bank.delete_account(acct.nessie_id)
            except NessieNotFound:
                pass
        live = await bank.create_account(
            user.nessie_customer_id, acct.nessie_type, acct.nickname, acct.starting_balance_cents // 100
        )
        acct.nessie_id = live["_id"]
        acct.balance_cents = from_dollars(live.get("balance", 0))
        acct.balance_synced_at = now
        session.add(acct)

    plan_ids = session.exec(select(Plan.id).where(Plan.user_id == user.id)).all()
    if plan_ids:
        session.exec(delete(Move).where(Move.plan_id.in_(plan_ids)))
        session.exec(delete(Plan).where(Plan.user_id == user.id))
    session.exec(delete(Lot).where(Lot.user_id == user.id))
    for lot in starter_lots(user.id):
        session.add(lot)
    session.exec(delete(Bill).where(Bill.user_id == user.id))  # the old accounts took their bills with them
    session.flush()
    await ensure_bills(session, bank, user)
    session.exec(delete(Event).where(Event.user_id == user.id))
    record(session, user.id, now, "demo_reset", "The demo was reset to its starting state.")
    user.risk_level = "clear"
    user.risk_reason = None
    user.risk_changed_at = now
    session.add(user)


async def _main() -> None:
    from harbor.bank import make_bank
    from harbor.clock import DemoClock, RealClock
    from harbor.config import get_settings
    from harbor.db import init_db, make_engine

    settings = get_settings()
    engine = make_engine(settings.database_url)
    init_db(engine)
    bank = make_bank(settings)
    clock = DemoClock(settings.demo_start) if settings.harbor_mode == "demo" else RealClock()
    try:
        with Session(engine) as session:
            user = await seed_persona(session, bank, clock.now())
            print(f"Seeded {user.name}: user id {user.id}, Nessie customer {user.nessie_customer_id} ({bank.kind})")
    finally:
        await bank.close()


if __name__ == "__main__":
    asyncio.run(_main())
