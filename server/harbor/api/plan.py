"""The evacuation money plan: GET /me/plan, approve and cancel, and the bills it can move."""

from datetime import timedelta

from fastapi import APIRouter, Request
from pydantic import BaseModel
from sqlmodel import col, select

from harbor.clock import iso
from harbor.deps import ClockDep, SessionDep, UserDep
from harbor.engine.plan import BILL_SHIELD_DAYS
from harbor.errors import HarborError
from harbor.models import Bill, Plan
from harbor.planning import active_plan, approve, plan_to_api, resume_after_approval, start_restore

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
    """Schedule the plan's moves; in a replay, resume a clock paused for approval."""
    now = clock.now()
    plan = _plan_or_404(session, user)
    if plan.version != body.plan_version:
        raise HarborError(
            409, "plan_version_stale", "The plan changed since you loaded it. Reload and review it again."
        )
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


@router.get("/me/bills")
def get_bills(session: SessionDep, user: UserDep, clock: ClockDep) -> list[dict]:
    """Bills in Nessie. `in_storm_window` marks the ones the bill shield can move."""
    now = clock.now()
    plan = active_plan(session, user.id)
    end = plan.cash_needed_by.date() + timedelta(days=BILL_SHIELD_DAYS) if plan and plan.cash_needed_by else None
    bills = session.exec(select(Bill).where(Bill.user_id == user.id).order_by(col(Bill.due_date))).all()
    return [
        {
            "id": b.id,
            "nessie_id": b.nessie_id,
            "payee": b.payee,
            "amount_cents": b.amount_cents,
            "due_date": b.due_date.isoformat(),
            "original_due_date": b.original_due_date.isoformat(),
            "deferred": b.due_date != b.original_due_date,
            "status": b.status,
            "in_storm_window": bool(end and now.date() <= b.original_due_date <= end),
        }
        for b in bills
    ]
