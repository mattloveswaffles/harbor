"""The evacuation money plan: GET /me/plan, approve, cancel, past plans, and the AI review and explain."""

from datetime import timedelta

from fastapi import APIRouter, Request
from pydantic import BaseModel
from sqlmodel import col, select

from harbor.ai.explain import check_rate, explain, move_facts
from harbor.ai.review import get_review, plan_context
from harbor.clock import iso
from harbor.deps import ClockDep, SessionDep, UserDep
from harbor.errors import HarborError
from harbor.models import Bill, Move, Plan
from harbor.engine.plan import BILL_SHIELD_DAYS
from harbor.planning import UNRUN, active_plan, approve, cancel_move, plan_to_api, resume_after_approval, start_restore
from harbor.schemas import ExplainIn, ExplainOut, PlanReviewOut

router = APIRouter(tags=["plan"])


class ApproveIn(BaseModel):
    plan_version: int


@router.get("/me/plan")
def get_plan(session: SessionDep, user: UserDep, clock: ClockDep) -> dict:
    """The current plan, or `{"plan": null}`. Harbor makes one when the user reaches prepare."""
    now = clock.now()
    plan = active_plan(session, user.id)
    return {"server_time": iso(now), "plan": plan_to_api(session, plan, now) if plan else None}


def _plan_or_404(session, user) -> Plan:
    plan = active_plan(session, user.id)
    if plan is None:
        raise HarborError(404, "plan_not_found", "No active plan for this user.")
    return plan


@router.post("/me/plan/approve")
def approve_plan(body: ApproveIn, request: Request, session: SessionDep, user: UserDep, clock: ClockDep) -> dict:
    """Approve the plan: its moves become scheduled (each after the cancel window). In a replay
    this also restarts the demo clock if it paused to wait for approval."""
    now = clock.now()
    plan = _plan_or_404(session, user)
    if plan.version != body.plan_version:
        raise HarborError(409, "plan_version_stale", "The plan changed since you loaded it. Reload and review it again.")
    if plan.status != "awaiting_approval":
        raise HarborError(409, "plan_not_awaiting_approval", f"This plan is already {plan.status}.")
    approve(session, user, plan, now)
    session.commit()
    resume_after_approval(request.app)
    return {"server_time": iso(now), "plan": plan_to_api(session, plan, now)}


@router.post("/me/plan/cancel")
def cancel_plan(session: SessionDep, user: UserDep, clock: ClockDep) -> dict:
    """Cancel every move that hasn't run. Money already moved is put back."""
    now = clock.now()
    plan = _plan_or_404(session, user)
    start_restore(session, user, plan, now, "You cancelled the plan.")
    session.commit()
    return {"server_time": iso(now), "plan": plan_to_api(session, plan, now)}


@router.post("/me/plan/moves/{move_id}/cancel")
def cancel_one(move_id: str, session: SessionDep, user: UserDep, clock: ClockDep) -> dict:
    now = clock.now()
    plan = _plan_or_404(session, user)
    move = session.get(Move, move_id)
    if move is None or move.plan_id != plan.id:
        raise HarborError(404, "move_not_found", "No move with this id in your plan.")
    if move.status not in UNRUN:
        raise HarborError(409, "move_already_running", f"This move is already {move.status}.")
    if move.cancel_deadline and now > move.cancel_deadline:
        raise HarborError(409, "cancel_window_closed", "Too late to cancel: this move is about to run.")
    cancel_move(session, user, move, now)
    session.commit()
    return {"server_time": iso(now), "plan": plan_to_api(session, plan, now)}


@router.get("/me/bills")
def get_bills(session: SessionDep, user: UserDep, clock: ClockDep) -> list[dict]:
    """Bills in Nessie. `in_storm_window` marks the ones the bill shield can move."""
    now = clock.now()
    plan = active_plan(session, user.id)
    end = plan.cash_needed_by.date() + timedelta(days=BILL_SHIELD_DAYS) if plan and plan.cash_needed_by else None
    bills = session.exec(select(Bill).where(Bill.user_id == user.id).order_by(col(Bill.due_date))).all()
    return [{
        "id": b.id, "nessie_id": b.nessie_id, "payee": b.payee, "amount_cents": b.amount_cents,
        "due_date": b.due_date.isoformat(), "original_due_date": b.original_due_date.isoformat(),
        "deferred": b.due_date != b.original_due_date, "status": b.status,
        "in_storm_window": bool(end and now.date() <= b.original_due_date <= end),
    } for b in bills]


@router.get("/me/plans")
def past_plans(session: SessionDep, user: UserDep, clock: ClockDep) -> dict:
    now = clock.now()
    plans = session.exec(select(Plan).where(Plan.user_id == user.id).order_by(col(Plan.created_at).desc())).all()
    return {"server_time": iso(now), "plans": [plan_to_api(session, p, now) for p in plans]}


# --- AI: review and explain (text only; the rules engine already decided every number) ---------

@router.get("/me/plan/review", response_model=PlanReviewOut)
def plan_review(request: Request, session: SessionDep, user: UserDep, clock: ClockDep) -> dict:
    """The AI allocation review for the current plan version: a suggestion, not advice. Every
    number comes from the plan. Without AI (or if Claude fails) it's the template
    (`generated_by: "template"`) with the same numbers."""
    now = clock.now()
    plan = _plan_or_404(session, user)
    return get_review(request.app, session, user, plan, now)


@router.post("/me/plan/explain", response_model=ExplainOut)
def plan_explain(body: ExplainIn, request: Request, session: SessionDep, user: UserDep, clock: ClockDep) -> dict:
    """Answer a "why?" question about the plan. Personal investment-advice questions get a fixed
    refusal. Max 500 characters, 10 per minute."""
    check_rate(request.app, user.id)
    now = clock.now()
    plan = _plan_or_404(session, user)
    move = None
    if body.move_id is not None:
        move = session.get(Move, body.move_id)
        if move is None or move.plan_id != plan.id:
            raise HarborError(404, "move_not_found", "No move with this id in your plan.")
    ctx = plan_context(request.app, session, user, plan, now)
    return explain(request.app, ctx, body.question, move_facts(ctx, move), now)
