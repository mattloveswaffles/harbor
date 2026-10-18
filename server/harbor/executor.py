"""Runs approved moves exactly once.

Each move's tag is saved before its bank write, so retries never double-send. A move waits while the
user is in shelter or a dependency is unfinished. ETF sales settle T+1, then deposit and transfer to
checking. Bank outages retry later; refusals fail the move. Moves are dated with their scheduled day.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlmodel import Session, col, select

from harbor.bank import NessieError, NessieUnavailable
from harbor.bank.base import tag_for
from harbor.clock import iso
from harbor.events import record
from harbor.models import Bill, Lot, Move, Plan, User
from harbor.planning import MONEY_KINDS, accounts_by_type, level_at, plan_moves

RUNNABLE_PLANS = ("approved", "running", "restoring")


def _money(cents: int) -> str:
    return f"${cents / 100:,.2f}".replace(".00", "")


async def _refresh(session: Session, bank, accounts) -> None:
    for acct in accounts:
        if acct.nessie_id:
            bal = await bank.get_balance_cents(acct.nessie_id)
            if bal is not None:
                acct.balance_cents = bal
                session.add(acct)


def _sell_lots(session: Session, move: Move, now: datetime) -> None:
    """Mark the sold shares: whole lots get sold_at; part of a lot is split off into a sold row."""
    for sale in move.lots or []:
        lot = session.get(Lot, sale["lot_id"])
        if lot is None or lot.sold_at is not None:
            continue
        if sale["shares_micro"] >= lot.shares_micro:
            lot.sold_at, lot.sold_move_id = now, move.id
        else:
            basis = round(lot.cost_basis_cents * sale["shares_micro"] / lot.shares_micro)
            session.add(
                Lot(
                    user_id=lot.user_id,
                    symbol=lot.symbol,
                    shares_micro=sale["shares_micro"],
                    cost_basis_cents=basis,
                    acquired=lot.acquired,
                    sold_at=now,
                    sold_move_id=move.id,
                )
            )
            lot.shares_micro -= sale["shares_micro"]
            lot.cost_basis_cents -= basis
        session.add(lot)


async def _execute(session: Session, bank, user: User, move: Move, now: datetime) -> str:
    """Do one move. Returns the event message."""
    accts = accounts_by_type(session, user.id)
    chk, sav, brk = accts["checking"], accts["savings"], accts.get("brokerage_cash")
    on = move.scheduled_for.date()
    if move.kind == "transfer":
        w = await bank.transfer(
            sav.nessie_id,
            chk.nessie_id,
            move.amount_cents,
            rounding="up",
            on=on,
            move_id=move.id,
            memo="Harbor: savings to checking for evacuation",
        )
        msg = f"Moved {_money(move.amount_cents)} from savings to checking."
    elif move.kind == "withdraw_cash":
        w = await bank.withdraw(
            chk.nessie_id, move.amount_cents, rounding="up20", on=on, move_id=move.id, memo="Harbor: evacuation cash"
        )
        msg = f"Withdrew ${w.dollars} in cash before landfall."
    elif move.kind == "restore_transfer":
        w = await bank.transfer(
            chk.nessie_id,
            sav.nessie_id,
            move.amount_cents,
            rounding="down",
            on=on,
            move_id=move.id,
            memo="Harbor: unspent evacuation money back to savings",
        )
        msg = f"Moved {_money(move.amount_cents)} you didn't spend back to savings."
    elif move.kind == "sell_etf":
        _sell_lots(session, move, now)
        move.status = "pending_settlement"
        session.add(move)
        return f"Sold {(move.shares_micro or 0) / 1_000_000:.2f} shares of {move.symbol}; the cash settles T+1."
    elif move.kind == "rebuy_etf":
        # Money goes checking -> Brokerage Settlement (Harbor), then out to buy the shares.
        fund = await bank.transfer(
            chk.nessie_id,
            brk.nessie_id,
            move.amount_cents,
            rounding="down",
            on=on,
            move_id=f"{move.id}:fund",
            memo=f"Harbor: money to rebuy {move.symbol}",
        )
        w = await bank.withdraw(
            brk.nessie_id,
            fund.dollars * 100,
            rounding="down",
            on=on,
            move_id=f"{move.id}:buy",
            memo=f"Harbor: bought {move.symbol}",
        )
        session.add(
            Lot(
                user_id=user.id,
                symbol=move.symbol,
                shares_micro=move.shares_micro or 0,
                cost_basis_cents=fund.dollars * 100,
                acquired=on,
            )
        )
        move.nessie_object_id, move.nessie_object_type = w.object_id, w.object_type
        move.nessie_amount_dollars, move.rounding_cents = w.dollars, fund.rounding_cents
        move.status = "done"
        session.add(move)
        await _refresh(session, bank, [chk, brk])
        return f"Bought back {(move.shares_micro or 0) / 1_000_000:.2f} shares of {move.symbol}."
    elif move.kind == "defer_bill":
        bill = session.get(Bill, (move.extra or {}).get("bill_id"))
        if bill is None or not bill.nessie_id:
            raise ValueError("the bill is no longer in Nessie")
        to_date = date.fromisoformat(move.extra["to_date"])
        await bank.update_bill_date(bill.nessie_id, to_date)
        bill.due_date = to_date
        session.add(bill)
        move.nessie_object_id, move.nessie_object_type, move.status = bill.nessie_id, "bill", "done"
        session.add(move)
        return f"Bill shield: your {bill.payee} bill moved from {bill.original_due_date:%b} {bill.original_due_date.day} to {to_date:%b} {to_date.day}."
    else:
        raise ValueError(f"Harbor can't run {move.kind} moves yet")
    move.nessie_object_id, move.nessie_object_type = w.object_id, w.object_type
    move.nessie_amount_dollars, move.rounding_cents = w.dollars, w.rounding_cents
    move.status = "done"
    session.add(move)
    await _refresh(session, bank, [a for a in (chk, sav, brk) if a])
    return msg


async def _settle(session: Session, bank, user: User, move: Move) -> str:
    accts = accounts_by_type(session, user.id)
    chk, brk = accts["checking"], accts["brokerage_cash"]
    on = move.expected_available_at.date()
    dep = await bank.deposit(
        brk.nessie_id,
        move.amount_cents,
        rounding="down",
        on=on,
        move_id=f"{move.id}:settle",
        memo=f"Harbor: {move.symbol} sale settled",
    )
    w = await bank.transfer(
        brk.nessie_id,
        chk.nessie_id,
        dep.dollars * 100,
        rounding="down",
        on=on,
        move_id=f"{move.id}:to_checking",
        memo="Harbor: sale proceeds to checking",
    )
    move.nessie_object_id, move.nessie_object_type = w.object_id, "transfer"
    move.nessie_amount_dollars, move.rounding_cents = w.dollars, dep.rounding_cents
    move.status = "done"
    session.add(move)
    await _refresh(session, bank, [chk, brk])
    return f"The {move.symbol} sale settled: {_money(move.amount_cents)} is now in checking."


def _update_plan_status(session: Session, plan: Plan, user: User, now: datetime) -> None:
    moves = plan_moves(session, plan.id)
    live = [m for m in moves if m.status != "cancelled"]
    if plan.status == "approved" and any(m.status != "scheduled" for m in live):
        plan.status = "running"
    if plan.status == "running" and all(m.status in ("done", "failed") for m in live if m.kind in MONEY_KINDS):
        plan.status = "complete"
        record(
            session,
            user.id,
            now,
            "plan_complete",
            "Every planned move has finished. Your evacuation money is ready.",
            {"plan_id": plan.id},
        )
    if plan.status == "restoring" and all(
        m.status in ("done", "failed") for m in live if m.kind in ("restore_transfer", "rebuy_etf")
    ):
        plan.status = "restored"
        record(
            session,
            user.id,
            now,
            "plan_restored",
            "Your money is back where it was before the storm.",
            {"plan_id": plan.id},
        )
    session.add(plan)


def next_due(app, after: datetime, until: datetime) -> datetime | None:
    """The earliest scheduled move or settlement time in (after, until]."""
    with Session(app.state.engine) as session:
        rows = session.exec(
            select(Move)
            .join(Plan, Move.plan_id == Plan.id)
            .where(col(Plan.status).in_(RUNNABLE_PLANS), col(Move.status).in_(("scheduled", "pending_settlement")))
        ).all()
    times = [m.expected_available_at if m.status == "pending_settlement" else m.scheduled_for for m in rows]
    times = [t for t in times if t is not None and after < t <= until]
    return min(times) if times else None


async def catch_up(app, until: datetime) -> None:
    """Advance to `until`, interleaving risk ticks and money moves in time order."""
    from harbor.ticker import tick  # the ticker imports planning, which imports this package's helpers

    cursor = app.state.tick_cursor or app.state.clock.now()
    for _ in range(500):
        t = next_due(app, cursor, until)
        if t is None:
            break
        tick(app, t)
        await run_due(app, t)
        cursor = t
    tick(app, until)
    await run_due(app, until)


async def run_due(app, now: datetime | None = None) -> int:
    """Run every due move for every user. Returns how many moves changed."""
    now = now or app.state.clock.now()
    bank = app.state.bank
    changed = 0
    with Session(app.state.engine) as session:
        rows = session.exec(
            select(Move, Plan)
            .join(Plan, Move.plan_id == Plan.id)
            .where(col(Plan.status).in_(RUNNABLE_PLANS), col(Move.status).in_(("scheduled", "pending_settlement")))
            .order_by(col(Move.scheduled_for), col(Move.seq))
        ).all()
        for move, plan in rows:
            user = session.get(User, plan.user_id)
            due_at = move.expected_available_at if move.status == "pending_settlement" else move.scheduled_for
            if due_at is None or due_at > now:
                continue
            if level_at(session, user, due_at) == "shelter":
                continue  # no bank writes during landfall; the move waits
            deps = [session.get(Move, d) for d in (move.depends_on or [])]
            if any(d is not None and d.status not in ("done", "cancelled", "failed") for d in deps):
                continue
            move.attempts += 1
            move.last_attempt_at = now
            move.nessie_request_tag = move.nessie_request_tag or tag_for(move.id)
            session.add(move)
            session.commit()  # intent is saved before the bank call
            try:
                msg = await (
                    _settle(session, bank, user, move)
                    if move.status == "pending_settlement"
                    else _execute(session, bank, user, move, now)
                )
                record(
                    session,
                    user.id,
                    now,
                    "move_done",
                    msg,
                    {
                        "move_id": move.id,
                        "plan_id": plan.id,
                        "kind": move.kind,
                        "status": move.status,
                        "nessie_object_id": move.nessie_object_id,
                        "ran_for": iso(due_at),
                    },
                )
            except NessieUnavailable as exc:
                move.error = {"code": "bank_unavailable", "message": exc.message, "retryable": True}
                session.add(move)
            except (NessieError, ValueError) as exc:
                move.status = "failed"
                move.error = {
                    "code": "bank_rejected" if isinstance(exc, NessieError) else "not_supported",
                    "message": getattr(exc, "message", str(exc)),
                    "retryable": False,
                }
                session.add(move)
                record(
                    session,
                    user.id,
                    now,
                    "move_failed",
                    f"A move failed: {move.error['message']}",
                    {"move_id": move.id, "plan_id": plan.id},
                )
            _update_plan_status(session, plan, user, now)
            session.commit()
            changed += 1
    return changed
