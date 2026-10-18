"""Plans in the database: create at prepare, approve, cancel, stand down and restore (decisions: engine/plan.py).

Status: awaiting_approval -> approved -> running -> complete -> restoring -> restored,
or cancelled / expired / superseded.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlmodel import Session, col, select

from harbor.clock import iso
from harbor.context import evacuation_for, storm_inputs
from harbor.engine import calendar as cal
from harbor.engine.plan import (
    Balances,
    BillIn,
    LotIn,
    PlanInputs,
    PlanSettings,
    RestoreInputs,
    SoldPosition,
    build_plan,
    build_restore,
    money,
)
from harbor.events import record
from harbor.models import Account, Bill, Event, Lot, Move, Plan, User
from harbor.provisioning import user_accounts
from harbor.sources.market import FixturePrices

ACTIVE = ("awaiting_approval", "approved", "running", "complete", "restoring")
MONEY_KINDS = ("transfer", "sell_etf", "withdraw_cash")
UNRUN = ("proposed", "scheduled")
DEFAULT_LEAD = timedelta(hours=48)  # when the forecast has no wind ETA yet

_prices: FixturePrices | None = None


def prices() -> FixturePrices:
    global _prices
    if _prices is None:
        _prices = FixturePrices()
    return _prices


# --- Queries
def active_plan(session: Session, user_id: str) -> Plan | None:
    return session.exec(
        select(Plan).where(Plan.user_id == user_id, col(Plan.status).in_(ACTIVE)).order_by(col(Plan.created_at).desc())
    ).first()


def plan_moves(session: Session, plan_id: str) -> list[Move]:
    return list(session.exec(select(Move).where(Move.plan_id == plan_id).order_by(col(Move.seq))).all())


def accounts_by_type(session: Session, user_id: str) -> dict[str, Account]:
    return {a.type: a for a in user_accounts(session, user_id)}


def level_at(session: Session, user: User, t: datetime) -> str:
    """The user's risk level at moment `t`, from the risk_changed events (used to replay catch-up)."""
    ev = session.exec(
        select(Event)
        .where(Event.user_id == user.id, Event.type == "risk_changed", Event.at <= t)
        .order_by(col(Event.seq).desc())
    ).first()
    return ev.data["to"] if ev else user.risk_level


# --- Create
def _template_summary(user: User, storm_name: str | None, draft, cash_needed_by: datetime) -> str:
    s = draft.sources
    parts = [f"{money(s['already_in_checking_cents'])} already in checking"]
    if s["from_savings_cents"]:
        parts.append(f"{money(s['from_savings_cents'])} from savings")
    if s["from_etf_sales_cents"]:
        parts.append(f"{money(s['from_etf_sales_cents'])} from selling ETF shares")
    storm = storm_name or "The storm"
    text = (
        f"{storm} could bring dangerous winds to your area. Harbor proposes gathering {money(draft.total_cents)} "
        f"for your evacuation: {', '.join(parts)}. The cash is ready by "
        f"{draft.facts['cash_needed_by_display']}."
    )
    if draft.shortfall_cents:
        text += f" That still leaves {money(draft.shortfall_cents)} short, so help resources are listed below."
    return text


def create_plan(app, session: Session, user: User, now: datetime, storm_id: str | None, storm_name: str | None) -> Plan:
    storm = storm_inputs(app, user, now)
    bundle = evacuation_for(app, session, user, now)
    # Money must be in checking a few hours before tropical-storm winds, when banking may go down.
    # The family can already be on the road: money in checking still works by card.
    eta = storm["eta"] or now + DEFAULT_LEAD
    cash_needed_by = max(eta - timedelta(hours=app.state.settings.evac_lead_hours), now + timedelta(hours=1))

    accounts = accounts_by_type(session, user.id)
    lots = session.exec(select(Lot).where(Lot.user_id == user.id, col(Lot.sold_at).is_(None))).all()
    price_map = prices().prices_at({lot.symbol for lot in lots}, now)
    lots = [lot for lot in lots if lot.symbol in price_map]
    inputs = PlanInputs(
        now=now,
        cash_needed_by=cash_needed_by,
        lines=tuple(bundle["budget_lines"]),
        balances=Balances(accounts["checking"].balance_cents, accounts["savings"].balance_cents),
        lots=tuple(LotIn(l.id, l.symbol, l.shares_micro, l.cost_basis_cents, l.acquired) for l in lots),
        prices_cents=price_map,
        bills=tuple(
            BillIn(b.id, b.payee, b.amount_cents, b.due_date)
            for b in session.exec(select(Bill).where(Bill.user_id == user.id, Bill.status == "pending")).all()
        ),
        settings=PlanSettings(
            max_etf_sell_cents=user.settings["max_etf_sell_cents"],
            cancel_window=timedelta(minutes=user.settings["cancel_window_minutes"]),
        ),
    )
    draft = build_plan(inputs)
    plan = Plan(
        user_id=user.id,
        status="awaiting_approval",
        storm_id=storm_id,
        created_at=now,
        cash_needed_by=cash_needed_by,
        latest_safe_approval_at=draft.latest_safe_approval_at,
        budget={
            "total_cents": draft.total_cents,
            "lines": [{"label": l.label, "amount_cents": l.amount_cents, "source": l.source} for l in draft.lines],
        },
        sources=draft.sources,
        shortfall_cents=draft.shortfall_cents,
        help_resources=draft.help_resources,
        alternatives=draft.facts["alternatives"],
        tax_note=draft.tax_note,
        warnings=draft.warnings,
        summary=_template_summary(user, storm_name, draft, cash_needed_by),
        ai={"source": "template", "model": None, "validated": True, "facts": draft.facts},
    )
    session.add(plan)
    session.flush()
    refs = {
        "checking": accounts["checking"].id,
        "savings": accounts["savings"].id,
        "brokerage": "brokerage",
        "cash": "cash",
    }
    key_to_id: dict[str, str] = {}
    for seq, m in enumerate(draft.moves):
        row = Move(
            plan_id=plan.id,
            seq=seq,
            kind=m.kind,
            status="proposed",
            from_ref=refs.get(m.from_ref, m.from_ref),
            to_ref=refs.get(m.to_ref, m.to_ref),
            symbol=m.symbol,
            shares_micro=m.shares_micro,
            price_locked_cents=m.price_locked_cents,
            lots=[
                {
                    "lot_id": s.lot_id,
                    "shares_micro": s.shares_micro,
                    "proceeds_cents": s.proceeds_cents,
                    "cost_basis_cents": s.cost_basis_cents,
                    "long_term": s.long_term,
                }
                for s in m.lot_sales
            ]
            or None,
            amount_cents=m.amount_cents,
            scheduled_for=m.scheduled_for,
            expected_available_at=m.expected_available_at,
            cancel_deadline=m.cancel_deadline,
            arrives_late=m.arrives_late,
            requires_explicit_approval=m.requires_explicit_approval,
            depends_on=[key_to_id[k] for k in m.depends_on if k in key_to_id] or None,
            why=m.why,
            extra=m.extra or None,
        )
        session.add(row)
        session.flush()
        key_to_id[m.key] = row.id
    pause_for_approval(app)
    record(
        session,
        user.id,
        now,
        "plan_created",
        f"Harbor made an evacuation plan: {money(draft.total_cents)}. Review and approve it.",
        {"plan_id": plan.id, "total_cents": draft.total_cents, "shortfall_cents": draft.shortfall_cents},
    )
    return plan


# --- Demo clock: wait for the human
def pause_for_approval(app) -> None:
    """In a replay, pause the clock while a plan awaits approval."""
    if getattr(app.state.clock, "running", False):
        app.state.clock.pause("awaiting_approval")


def resume_after_approval(app) -> None:
    if getattr(app.state.clock, "paused_reason", None) == "awaiting_approval":
        app.state.clock.resume()


# --- Approve and cancel
def approve(session: Session, user: User, plan: Plan, now: datetime) -> Plan:
    window = timedelta(minutes=user.settings["cancel_window_minutes"])
    earliest = now + window
    for m in plan_moves(session, plan.id):
        if m.status != "proposed":
            continue
        if m.kind == "sell_etf":
            at = cal.next_sell_time(max(m.scheduled_for, earliest))
            m.scheduled_for, m.expected_available_at = at, cal.cash_available_at(at)
            m.arrives_late = m.expected_available_at > plan.cash_needed_by
        else:
            m.scheduled_for = max(m.scheduled_for, earliest)
            m.expected_available_at = max(m.expected_available_at or m.scheduled_for, m.scheduled_for)
        m.cancel_deadline = m.scheduled_for - timedelta(minutes=5)
        m.status = "cancelled" if m.arrives_late else "scheduled"
        session.add(m)
    plan.status, plan.approved_at = "approved", now
    session.add(plan)
    record(
        session,
        user.id,
        now,
        "plan_approved",
        "You approved the plan. Harbor will move the money on schedule.",
        {"plan_id": plan.id, "version": plan.version},
    )
    return plan


def cancel_unrun(session: Session, plan: Plan) -> int:
    n = 0
    for m in plan_moves(session, plan.id):
        if m.status in UNRUN:
            m.status = "cancelled"
            session.add(m)
            n += 1
    return n


# --- Stand-down and restore
def _donemoney(session: Session, plan: Plan) -> list[Move]:
    return [
        m for m in plan_moves(session, plan.id) if m.kind in MONEY_KINDS and m.status in ("done", "pending_settlement")
    ]


def start_restore(session: Session, user: User, plan: Plan, now: datetime, reason: str) -> None:
    """Cancel what hasn't run and schedule moving unspent money back to savings."""
    cancel_unrun(session, plan)
    done = _donemoney(session, plan)
    if not done:
        plan.status = "expired" if plan.status == "awaiting_approval" else "cancelled"
        session.add(plan)
        record(session, user.id, now, "plan_expired", f"The plan was closed: {reason}", {"plan_id": plan.id})
        return
    accounts = accounts_by_type(session, user.id)
    before = plan.ai["facts"]["balances"]["checking_cents"]  # balance when planned
    sold = tuple(
        SoldPosition(
            m.symbol,
            m.shares_micro or 0,
            m.amount_cents,
            any(l["proceeds_cents"] < l["cost_basis_cents"] for l in (m.lots or [])),
            m.scheduled_for,
        )
        for m in done
        if m.kind == "sell_etf"
    )
    draft = build_restore(
        RestoreInputs(
            now=now,
            checking_now_cents=accounts["checking"].balance_cents,
            checking_before_cents=before,
            moved_from_savings_cents=sum(m.amount_cents for m in done if m.kind == "transfer"),
            sold=sold,
            prices_cents=prices().prices_at({p.symbol for p in sold}, now),
            rebuy_opt_in=user.settings["rebuy_opt_in"],
        )
    )
    seq = len(plan_moves(session, plan.id))
    refs = {"checking": accounts["checking"].id, "savings": accounts["savings"].id, "brokerage": "brokerage"}
    for i, m in enumerate(draft.moves):
        session.add(
            Move(
                plan_id=plan.id,
                seq=seq + i,
                kind=m.kind,
                status="scheduled",
                from_ref=refs.get(m.from_ref, m.from_ref),
                to_ref=refs.get(m.to_ref, m.to_ref),
                symbol=m.symbol,
                shares_micro=m.shares_micro,
                price_locked_cents=m.price_locked_cents,
                amount_cents=m.amount_cents,
                scheduled_for=m.scheduled_for,
                expected_available_at=m.expected_available_at,
                cancel_deadline=m.cancel_deadline,
                requires_explicit_approval=m.requires_explicit_approval,
                why=m.why,
            )
        )
    plan.status = "restoring" if draft.moves else "restored"
    plan.warnings = [*plan.warnings, *draft.warnings]
    session.add(plan)
    msg = (
        f"{reason} Harbor is moving {money(sum(m.amount_cents for m in draft.moves))} back to savings."
        if draft.moves
        else f"{reason} There was nothing to move back."
    )
    record(
        session,
        user.id,
        now,
        "plan_restoring" if draft.moves else "plan_restored",
        msg,
        {"plan_id": plan.id, "unspent_cents": draft.unspent_cents},
    )


def on_level_change(
    app, session: Session, user: User, old: str, new: str, now: datetime, storm_id: str | None, storm_name: str | None
) -> None:
    """The scheduler calls this after each risk change."""
    plan = active_plan(session, user.id)
    if new in ("prepare", "act") and plan is None:
        create_plan(app, session, user, now, storm_id, storm_name)
    elif new in ("monitor", "clear") and old in ("prepare", "act") and plan is not None:
        start_restore(session, user, plan, now, "The storm turned away.")
    elif (
        new == "recover"
        and plan is not None
        and plan.status in ("awaiting_approval", "approved", "running", "complete")
    ):
        start_restore(session, user, plan, now, "The storm has passed and the sensors say it's safe.")


def restore_done(session: Session, user: User) -> bool:
    """True once the latest plan is fully restored (moves the user from recover to clear)."""
    plan = session.exec(select(Plan).where(Plan.user_id == user.id).order_by(col(Plan.created_at).desc())).first()
    return plan is not None and plan.status in ("restored", "expired", "cancelled")


# --- API shapes
def move_to_api(m: Move) -> dict:
    return {
        "id": m.id,
        "kind": m.kind,
        "status": m.status,
        "from": m.from_ref,
        "to": m.to_ref,
        "symbol": m.symbol,
        "shares_micro": m.shares_micro,
        "lots": [l["lot_id"] for l in (m.lots or [])],
        "price_locked_cents": m.price_locked_cents,
        "amount_cents": m.amount_cents,
        "nessie_amount_dollars": m.nessie_amount_dollars,
        "rounding_cents": m.rounding_cents,
        "scheduled_for": iso(m.scheduled_for),
        "expected_available_at": iso(m.expected_available_at),
        "cancel_deadline": iso(m.cancel_deadline),
        "arrives_late": m.arrives_late,
        "requires_explicit_approval": m.requires_explicit_approval,
        "depends_on": m.depends_on or [],
        "why": m.why,
        "nessie_object_id": m.nessie_object_id,
        "nessie_object_type": m.nessie_object_type,
        "attempts": m.attempts,
        "error": m.error,
        **({"extra": m.extra} if m.extra else {}),
    }


def plan_to_api(session: Session, plan: Plan, now: datetime) -> dict:
    return {
        "id": plan.id,
        "version": plan.version,
        "status": plan.status,
        "decided_by": plan.decided_by,
        "server_time": iso(now),
        "created_at": iso(plan.created_at),
        "approved_at": iso(plan.approved_at),
        "storm_id": plan.storm_id,
        "cash_needed_by": iso(plan.cash_needed_by),
        "latest_safe_approval_at": iso(plan.latest_safe_approval_at),
        "budget": plan.budget,
        "sources": plan.sources,
        "shortfall_cents": plan.shortfall_cents,
        "help_resources": plan.help_resources or [],
        "moves": [move_to_api(m) for m in plan_moves(session, plan.id)],
        "alternatives": plan.alternatives or [],
        "summary": plan.summary,
        "tax_note": plan.tax_note,
        "warnings": plan.warnings or [],
        "ai": {k: v for k, v in plan.ai.items() if k != "facts"},
    }
