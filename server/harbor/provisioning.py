"""A new user's Nessie side: a pseudonymous customer, three accounts and a sample portfolio. Idempotent.

Nessie's customer list is public, so it only ever gets pseudonyms.
"""

import contextlib
from dataclasses import dataclass
from datetime import date, datetime

from sqlmodel import Session, delete, select

from harbor.bank import Bank, NessieNotFound, from_dollars
from harbor.events import record
from harbor.geo import lookup_zip
from harbor.models import Account, Bill, Event, Household, Lot, Move, Plan, User


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

# Sample portfolio, not a recommendation. TBUX is the "storm sleeve" sold first.
STARTER_LOTS = (
    ("TBUX", 7_200_000, 35800, date(2023, 3, 14)),
    ("TCAF", 50_000_000, 135500, date(2023, 9, 12)),
    ("TCAF", 30_000_000, 91200, date(2024, 2, 20)),
    ("TSPA", 40_000_000, 114000, date(2023, 11, 7)),
)


def starter_lots(user_id: str) -> list[Lot]:
    return [
        Lot(user_id=user_id, symbol=s, shares_micro=sh, cost_basis_cents=cb, acquired=acq)
        for s, sh, cb, acq in STARTER_LOTS
    ]


def user_accounts(session: Session, user_id: str) -> list[Account]:
    order = {a.type: i for i, a in enumerate(STARTER_ACCOUNTS)}
    accounts = session.exec(select(Account).where(Account.user_id == user_id)).all()
    return sorted(accounts, key=lambda a: order.get(a.type, 99))


async def ensure_customer(bank: Bank, user: User) -> str:
    """The user's Nessie customer id: the stored one if it still exists, else a new pseudonymous customer."""
    if user.nessie_customer_id and await bank.get_customer(user.nessie_customer_id):
        return user.nessie_customer_id
    address = {
        "street_number": "1",
        "street_name": "Harbor Way",
        "city": (lookup_zip(user.zip) or {}).get("city", "Unknown"),
        "state": "FL",
        "zip": user.zip,
    }
    return (await bank.create_customer("Harbor", f"User {user.id}", address))["_id"]


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


async def provision_user(session: Session, bank: Bank, user: User, household: dict, now: datetime) -> User:
    """Create the Nessie customer, the three accounts and the starter portfolio. Caller commits."""
    session.add(user)
    session.flush()  # no ORM relationships, so insert the user before rows that point at it
    session.add(Household(user_id=user.id, **household))
    user.nessie_customer_id = await ensure_customer(bank, user)
    await ensure_accounts(session, bank, user, now)
    for lot in starter_lots(user.id):
        session.add(lot)
    return user


async def reset_user(session: Session, bank: Bank, user: User, now: datetime) -> None:
    """Reset accounts, portfolio and plans (caller commits). Nessie can't set balances, so accounts are recreated."""
    user.nessie_customer_id = await ensure_customer(bank, user)
    for acct in user_accounts(session, user.id):
        if acct.nessie_id:
            with contextlib.suppress(NessieNotFound):
                await bank.delete_account(acct.nessie_id)
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
    session.exec(delete(Event).where(Event.user_id == user.id))
    record(session, user.id, now, "demo_reset", "The demo was reset to its starting state.")
    user.risk_level = "clear"
    user.risk_reason = None
    user.risk_changed_at = now
    session.add(user)
