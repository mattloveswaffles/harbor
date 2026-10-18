"""Connected institutions. Every connection is backed by Nessie accounts, so money moves through Nessie.

The first bank links the user's Nessie checking and savings (the plan draws from them) and the brokerage
links the settlement account. Wallets and any other bank get a new Nessie account with a mock balance.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
from datetime import datetime

from sqlmodel import Session, select

from harbor.bank import Bank, NessieNotFound, from_dollars
from harbor.events import record
from harbor.models import Account, Connection, User
from harbor.provisioning import ensure_accounts, user_accounts


@dataclass(frozen=True)
class Institution:
    id: str
    name: str
    kind: str  # bank | brokerage | wallet
    mock_balance_dollars: int = 0  # for accounts Harbor opens in Nessie


INSTITUTIONS = {
    i.id: i
    for i in (
        Institution("chase", "Chase", "bank", 260),
        Institution("bankofamerica", "Bank of America", "bank", 310),
        Institution("wellsfargo", "Wells Fargo", "bank", 280),
        Institution("robinhood", "Robinhood", "brokerage"),
        Institution("paypal", "PayPal", "wallet", 120),
        Institution("venmo", "Venmo", "wallet", 45),
        Institution("cashapp", "Cash App", "wallet", 80),
    )
}


def connections(session: Session, user_id: str) -> dict[str, Connection]:
    return {c.institution: c for c in session.exec(select(Connection).where(Connection.user_id == user_id)).all()}


def listing(session: Session, user: User) -> list[dict]:
    """Every institution with its status and the Nessie-backed accounts it holds."""
    linked = connections(session, user.id)
    accounts = {a.id: a for a in user_accounts(session, user.id)}
    out = []
    for inst in INSTITUTIONS.values():
        con = linked.get(inst.id)
        accts = [accounts[i] for i in (con.account_ids if con else []) if i in accounts]
        out.append(
            {
                "id": inst.id,
                "name": inst.name,
                "kind": inst.kind,
                "connected": con is not None,
                "connected_at": con.connected_at.isoformat() if con and con.connected_at else None,
                "accounts": [
                    {"id": a.id, "type": a.type, "nickname": a.nickname, "balance_cents": a.balance_cents}
                    for a in accts
                ],
                "total_cents": sum(a.balance_cents for a in accts),
            }
        )
    return out


async def connect(session: Session, bank: Bank, user: User, institution: str, now: datetime) -> Connection:
    """Link an institution through Nessie (idempotent). Caller commits."""
    inst = INSTITUTIONS[institution]
    linked = connections(session, user.id)
    if institution in linked:
        return linked[institution]
    core = {a.type: a for a in await ensure_accounts(session, bank, user, now)}  # syncs balances from Nessie
    primary_bank = not any(INSTITUTIONS[i].kind == "bank" for i in linked)
    if inst.kind == "bank" and primary_bank:
        ids = [core["checking"].id, core["savings"].id]
    elif inst.kind == "brokerage":
        ids = [core["brokerage_cash"].id]
    else:
        nickname = f"{inst.name} balance (Harbor)"
        live = await bank.create_account(user.nessie_customer_id, "Savings", nickname, inst.mock_balance_dollars)
        acct = Account(
            user_id=user.id,
            type="wallet",
            nessie_type="Savings",
            nessie_id=live["_id"],
            nickname=nickname,
            balance_cents=from_dollars(live.get("balance", 0)),
            balance_synced_at=now,
            starting_balance_cents=inst.mock_balance_dollars * 100,
        )
        session.add(acct)
        session.flush()
        ids = [acct.id]
    con = Connection(user_id=user.id, institution=institution, account_ids=ids, connected_at=now)
    session.add(con)
    record(session, user.id, now, "connection_added", f"{inst.name} is connected.", {"institution": institution})
    return con


async def disconnect(session: Session, bank: Bank, user: User, institution: str, now: datetime) -> None:
    """Unlink an institution. Accounts Harbor opened are closed in Nessie. Caller commits."""
    con = connections(session, user.id).get(institution)
    if con is None:
        return
    for acct_id in con.account_ids or []:
        acct = session.get(Account, acct_id)
        if acct is not None and acct.type == "wallet":
            if acct.nessie_id:
                with contextlib.suppress(NessieNotFound):
                    await bank.delete_account(acct.nessie_id)
            session.delete(acct)
    session.delete(con)
    name = INSTITUTIONS[institution].name
    record(session, user.id, now, "connection_removed", f"{name} is disconnected.", {"institution": institution})
