"""Evacuation advice, written by the AI from everything Harbor knows: Nessie balances, the household and its medical
needs, the car, routes, shelters and the storm.

The model answers in a background thread with forced JSON (a json_schema response format, served only by OpenRouter
providers that honour it). New facts or Regenerate start a fresh run; the last advice stays up meanwhile.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_ai import Agent, NativeOutput
from sqlmodel import Session

from harbor import connections, profile
from harbor.ai.llm import TIME_BUDGET_S
from harbor.ai.llm import model as llm_model
from harbor.clock import iso
from harbor.context import guide_for, storm_inputs
from harbor.models import Advice, User
from harbor.planning import active_plan, plan_moves
from harbor.provisioning import user_accounts

log = logging.getLogger("harbor.advisor")


class Step(BaseModel):
    title: str = Field(description="A short imperative, like 'Refill Lisinopril'")
    detail: str = Field(description="One short line")
    kind: Literal["money", "car", "medicine", "pet", "packing", "shelter"] = Field(description="What the step is about")


class AdviceOut(BaseModel):
    summary: str = Field(max_length=280, description="At most two short sentences to the family: where to go and why")
    destination_id: str
    shelter_id: str | None
    steps: list[Step] = Field(min_length=2, max_length=4, description="Things to do before leaving, most urgent first")


INSTRUCTIONS = """You plan one US household's hurricane evacuation from the JSON facts: bank balances, household, medical needs, car,
storm, routes and shelters. Pick the destination and backup shelter that fit their money, kids, car range, medical
needs and pets, using ids from the facts.
summary: at most two short sentences to the family on where to go and why, naming the backup shelter (a public
shelter from the list). No ids, dates, times or Markdown.
steps: 2 to 4 concrete things to do before leaving, such as refilling a medicine that runs out soon, filling the tank
or packing for a pet. Use only the facts; never invent numbers.
"""

advisor = Agent(output_type=NativeOutput(AdviceOut), instructions=INSTRUCTIONS, name="harbor-advisor")
SETTINGS = {
    "timeout": TIME_BUDGET_S,
    "openrouter_provider": {"require_parameters": True},  # only providers that enforce the JSON schema
    "openrouter_reasoning": {"enabled": False},  # an answer in seconds, not minutes
}


def facts(app, session: Session, user: User, now: datetime) -> dict:
    """Everything the advice is built from, as plain JSON."""
    prof = profile.load(session, user)
    storm = storm_inputs(app, user, now)
    bundle = guide_for(app, session, user, now)
    guide = bundle["guide"]
    linked = connections.connections(session, user.id)
    linked_ids = {i for c in linked.values() for i in c.account_ids or []}
    balances = {
        a.type if a.type != "wallet" else a.nickname: a.balance_cents
        for a in user_accounts(session, user.id)
        if a.id in linked_ids
    }
    plan = active_plan(session, user.id)
    lines = [{"label": line.label, "amount_cents": line.amount_cents} for line in bundle["budget_lines"]]
    total = plan.budget["total_cents"] if plan else sum(line["amount_cents"] for line in lines)
    route = guide["route"]
    return {
        "now": iso(now),
        "risk_level": user.risk_level,
        "storm_winds_at": iso(storm["eta"]),
        "storm_category": storm["category"],
        "household": prof.model_dump(include={"people", "pets", "medical", "places", "home"}),
        "car": prof.vehicle.model_dump() | {"range_mi": prof.range_mi},
        "connected": sorted(linked),
        "balances_cents": balances,
        "available_cents": sum(balances.values()),
        "trip_total_cents": total,
        "budget_lines": plan.budget["lines"] if plan else lines,
        "plan": None
        if plan is None
        else {
            "status": plan.status,
            "sources": plan.sources,
            "shortfall_cents": plan.shortfall_cents,
            "steps": [
                {"when": iso(m.scheduled_for), "kind": m.kind, "amount_cents": m.amount_cents, "why": m.why}
                for m in plan_moves(session, plan.id)
                if m.status != "cancelled"
            ],
        },
        "leave_by": guide["leave_by"],
        "chosen_destination": guide["chosen"],
        "destinations": [
            {k: d[k] for k in ("id", "name", "drive_time_min_evac", "outside_cone", "feasible", "recommended")}
            for d in guide["destinations"][:6]
        ],
        "route": None if route is None else {"distance_mi": route["distance_mi"], "corridor": route["corridor"]},
        "shelters": [
            {k: s.get(k) for k in ("id", "name", "kind", "status", "pets", "ada", "distance_mi")}
            for s in guide["shelters"][:4]
        ],
        "lodging_nightly_cents": (guide["lodging"] or {}).get("nightly_estimate_cents"),
    }


def checked(out: AdviceOut, f: dict) -> dict:
    """The model's advice, with any destination or shelter it made up swapped for Harbor's pick."""
    feasible = {d["id"] for d in f["destinations"] if d["feasible"]}
    shelters = [s["id"] for s in f["shelters"]]
    advice = out.model_dump()
    if advice["destination_id"] not in feasible:
        advice["destination_id"] = f["chosen_destination"]
    if advice["shelter_id"] not in shelters:
        advice["shelter_id"] = shelters[0] if shelters else None
    advice["steps"] = advice["steps"][:4]
    return advice


def inputs_hash(f: dict) -> str:
    """What the advice depends on, without the clock."""
    keep = {k: v for k, v in f.items() if k not in ("now", "storm_winds_at", "leave_by")}
    return hashlib.sha256(json.dumps(keep, sort_keys=True).encode()).hexdigest()[:16]


def _store(session: Session, user_id: str, now: datetime, **values) -> Advice:
    row = session.get(Advice, user_id) or Advice(user_id=user_id)
    for k, v in values.items():
        setattr(row, k, v)
    row.updated_at = now
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def _write(app, user_id: str) -> None:
    """Background thread: ask the model and store its advice."""
    with Session(app.state.engine) as session:
        user = session.get(User, user_id)
        now = app.state.clock.now()
        f = facts(app, session, user, now)
        try:
            prompt = json.dumps(f, separators=(",", ":"))
            out = advisor.run_sync(prompt, model=llm_model(app), model_settings=SETTINGS).output
            _store(
                session, user_id, now, status="ready", error=None, result=checked(out, f), inputs_hash=inputs_hash(f)
            )
        except Exception as exc:
            log.warning("advisor failed: %s", exc)
            _store(
                session,
                user_id,
                now,
                status="error",
                error="The AI didn't answer. Try again.",
                inputs_hash=inputs_hash(f),
            )


def _start(app, session: Session, user: User, f: dict, now: datetime) -> Advice:
    if llm_model(app) is None:
        return _store(session, user.id, now, status="error", error="The AI is off.", inputs_hash=inputs_hash(f))
    row = _store(session, user.id, now, status="running", error=None, inputs_hash=inputs_hash(f))
    threading.Thread(target=_write, args=(app, user.id), daemon=True, name=f"advisor-{user.id}").start()
    return row


def _payload(row: Advice, f: dict) -> dict:
    return {
        "status": row.status,
        "error": row.error,
        "updated_at": iso(row.updated_at),
        "advice": row.result,
        "facts": {
            k: f[k]
            for k in ("available_cents", "trip_total_cents", "budget_lines", "connected", "leave_by", "storm_winds_at")
        }
        | {"range_mi": f["car"]["range_mi"], "route_mi": (f["route"] or {}).get("distance_mi")},
    }


def regenerate(app, session: Session, user: User) -> dict:
    """Write the advice again, unless the AI is already at it."""
    now = app.state.clock.now()
    f = facts(app, session, user, now)
    row = session.get(Advice, user.id)
    if row is None or row.status != "running":
        row = _start(app, session, user, f, now)
    return _payload(row, f)


def current(app, session: Session, user: User) -> dict:
    """The stored advice; the AI starts on it when there's none yet or the facts have changed."""
    now = app.state.clock.now()
    f = facts(app, session, user, now)
    row = session.get(Advice, user.id)
    if row is None or (row.status != "running" and row.inputs_hash != inputs_hash(f)):
        row = _start(app, session, user, f, now)
    return _payload(row, f)
