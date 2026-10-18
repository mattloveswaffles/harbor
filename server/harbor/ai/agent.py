"""Ask Harbor: the chat agent (Pydantic AI). Its tools reuse the dashboard's handlers; only regenerate_advice writes."""

from __future__ import annotations

import time
from collections import deque
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Literal

from fastapi import HTTPException, Request
from pydantic_ai import Agent, RunContext
from pydantic_ai.messages import (
    FunctionToolCallEvent,
    ModelMessage,
    ModelRequest,
    ModelResponse,
    PartDeltaEvent,
    PartStartEvent,
    TextPart,
    TextPartDelta,
    ThinkingPart,
    ThinkingPartDelta,
    UserPromptPart,
)
from pydantic_ai.models import Model
from sqlmodel import Session

from harbor import connections
from harbor import profile as household_profile
from harbor.ai import advisor
from harbor.ai.llm import TIME_BUDGET_S
from harbor.api import evacuation, plan, portfolio, sensors, storm, users, weather
from harbor.clock import Clock
from harbor.models import User

RATE_LIMIT = 10  # messages per user per real minute

INSTRUCTIONS = """\
You are Harbor, a calm, practical hurricane-evacuation assistant for one US household.

Call the tools to look up the household's real data before answering anything about their home,
storm, money, plan, route or shelters. Call them straight away: never reply that you will check. Only state facts a tool returned in this conversation: never
invent a car, an amount, a road, a shelter, a version or a status. If no tool has it, say you don't
know. Never guess a number; quote it from a tool. Amounts named
*_cents are in cents: show them as dollars ($1,363). Times are UTC: show them in Eastern time
(hurricane season is daylight time, UTC-4: 12:07Z is 8:07 AM).

Make clear recommendations: when to leave, where to go, which shelter fits the household (pets,
mobility, medical needs), how much cash to carry, what to pack, and what to approve in the plan.
Harbor's evacuation advice (written by Harbor's AI) picks the destination, backup shelter and steps; when they
change something or ask for a fresh plan, call regenerate_advice and tell them it's updating.
You can't move money. To move money, the user approves the plan on My plan.
Don't recommend buying or selling specific investments beyond explaining what the plan does.
If someone is in danger now, tell them to follow local officials and call 911.

Keep answers short: two to five sentences, or a few "- " bullets. Use simple Markdown: **bold** for the
key time, place or amount, and "- " bullets for steps. No headings, tables or code.
"""


@dataclass
class ChatDeps:
    request: Request
    session: Session
    user: User
    clock: Clock


agent = Agent(deps_type=ChatDeps, instructions=INSTRUCTIONS, name="harbor")


@agent.tool
async def household(ctx: RunContext[ChatDeps]) -> dict[str, Any]:
    """The user's name, home ZIP and location, and household: adults, children, seniors, pets,
    mobility, medical needs, car and home type, evacuation zone."""
    return users.get_me(ctx.deps.user, ctx.deps.session).model_dump()


@agent.tool
async def storm_status(ctx: RunContext[ChatDeps]) -> dict[str, Any]:
    """The storm threatening the home now: risk level and reason, storm name, category and winds,
    wind probability at the ZIP, when tropical-storm winds arrive, and watches/warnings."""
    d = ctx.deps
    return storm.get_storm(d.request, d.user, d.clock)


@agent.tool
async def bank_accounts(ctx: RunContext[ChatDeps]) -> list[dict[str, Any]]:
    """Checking, savings and brokerage-cash balances (read-only, from the bank)."""
    d = ctx.deps
    accounts = await users.get_accounts(d.user, d.session, d.request.app.state.bank, d.clock)
    return [a.model_dump() for a in accounts]


@agent.tool
async def investments(ctx: RunContext[ChatDeps]) -> dict[str, Any]:
    """ETF holdings with values and gains (a simulated portfolio priced with real closes)."""
    d = ctx.deps
    return portfolio.get_portfolio(d.session, d.user, d.clock)


@agent.tool
async def evacuation_plan(ctx: RunContext[ChatDeps]) -> dict[str, Any]:
    """The money plan: total budget and its lines, where the money comes from, each step with its
    time and status, the approval deadline, and alternatives. `plan` is null when none is needed."""
    d = ctx.deps
    return plan.get_plan(d.session, d.user, d.clock)


@agent.tool
async def evacuation_guide(ctx: RunContext[ChatDeps]) -> dict[str, Any]:
    """Whether to evacuate, when to leave, destinations with drive times, the chosen route,
    public shelters (pets, accessibility), lodging estimates and checklists."""
    d = ctx.deps
    guide = evacuation.get_evacuation(d.request, d.session, d.user, d.clock)
    if guide.get("route"):
        guide["route"] = {k: v for k, v in guide["route"].items() if k != "steps"}  # turn-by-turn is noise here
    return guide


@agent.tool
async def bills(ctx: RunContext[ChatDeps]) -> list[dict[str, Any]]:
    """Upcoming bills, and whether each falls in the storm window (the plan can delay those)."""
    d = ctx.deps
    return plan.get_bills(d.session, d.user, d.clock)


@agent.tool
async def nearby_atms(ctx: RunContext[ChatDeps]) -> list[dict[str, Any]]:
    """The best ATMs for cash: outside the forecast cone and on the evacuation route first."""
    d = ctx.deps
    return evacuation.get_atms(d.request, d.session, d.user, d.clock, radius_miles=150)[:6]


@agent.tool
async def nearby_sensors(ctx: RunContext[ChatDeps]) -> list[dict[str, Any]]:
    """Live tide gauges, river gauges and buoys near the home, with storm surge and flood status."""
    d = ctx.deps
    return sensors.get_sensors(d.request, d.user, d.clock, radius_miles=200)[:5]


@agent.tool
async def household_details(ctx: RunContext[ChatDeps]) -> dict[str, Any]:
    """The Settings profile: people and ages, pets, medications with days left, medical equipment,
    mobility, the car (mpg, tank, gas now, range), places they'd go and emergency contacts."""
    d = ctx.deps
    data = household_profile.load(d.session, d.user)
    return data.model_dump(exclude={"privacy", "alerts"}) | {"car_range_mi": data.range_mi}


@agent.tool
async def connected_accounts(ctx: RunContext[ChatDeps]) -> list[dict[str, Any]]:
    """Banks, brokerages and wallets (PayPal, Venmo, Cash App): which are connected and their balances."""
    d = ctx.deps
    return connections.listing(d.session, d.user)


@agent.tool
async def weather_at_home(ctx: RunContext[ChatDeps]) -> dict[str, Any]:
    """The storm's category and closest pass, hazards at the home (wind arrival and peak gusts, surge
    zone, rain total, tornadoes, power outages) and wind and rain over the coming days."""
    d = ctx.deps
    return weather.get_weather(d.request, d.session, d.user, d.clock)


@agent.tool
async def evacuation_advice(ctx: RunContext[ChatDeps]) -> dict[str, Any]:
    """Harbor's evacuation advice: summary, destination, backup shelter and the next steps. While `status`
    is running the AI is still writing it."""
    d = ctx.deps
    return advisor.current(d.request.app, d.session, d.user)


@agent.tool
async def regenerate_advice(ctx: RunContext[ChatDeps]) -> dict[str, str]:
    """Rebuild the evacuation advice from the latest data. It updates in the background."""
    d = ctx.deps
    return {"status": advisor.regenerate(d.request.app, d.session, d.user)["status"]}


# --- Running a chat turn
def history(messages: list[tuple[Literal["user", "assistant"], str]]) -> list[ModelMessage]:
    """Earlier turns as Pydantic AI messages (the client keeps the conversation; the server is stateless)."""
    return [
        ModelRequest(parts=[UserPromptPart(content=text)]) if role == "user" else ModelResponse(parts=[TextPart(text)])
        for role, text in messages
    ]


def check_rate(app, user_id: str, now_s: float | None = None) -> None:
    """At most RATE_LIMIT messages per real minute per user, else 429 with Retry-After."""
    now_s = time.monotonic() if now_s is None else now_s
    hits: deque[float] = app.state.__dict__.setdefault("chat_hits", {}).setdefault(user_id, deque())
    while hits and now_s - hits[0] >= 60:
        hits.popleft()
    if len(hits) >= RATE_LIMIT:
        retry = max(1, int(60 - (now_s - hits[0])) + 1)
        raise HTTPException(
            429,
            detail={"code": "rate_limited", "message": "Too many messages. Try again in a minute."},
            headers={"Retry-After": str(retry)},
        )
    hits.append(now_s)


async def stream_reply(
    model: Model, deps: ChatDeps, turns: list[tuple[Literal["user", "assistant"], str]]
) -> AsyncIterator[dict]:
    """Answer the last user turn as events: `thinking` and `text` deltas, each `tool` as it's called, then `done`.
    Tools run one at a time: they share one database session."""
    *earlier, (_, question) = turns
    used: list[str] = []
    # A stalled model times out and the next one answers; models that can reason stream their thinking
    settings = {"timeout": TIME_BUDGET_S, "openrouter_reasoning": {"effort": "low"}}
    with agent.parallel_tool_call_execution_mode("sequential"):
        async with agent.run_stream_events(
            question, deps=deps, model=model, message_history=history(earlier), model_settings=settings
        ) as events:
            async for event in events:
                if isinstance(event, FunctionToolCallEvent):
                    used.append(event.part.tool_name)
                    yield {"type": "tool", "name": event.part.tool_name}
                    continue
                part = event.part if isinstance(event, PartStartEvent) else None
                delta = event.delta if isinstance(event, PartDeltaEvent) else None
                if isinstance(part, TextPart | ThinkingPart) and part.content:
                    yield {"type": "text" if isinstance(part, TextPart) else "thinking", "text": part.content}
                elif isinstance(delta, TextPartDelta | ThinkingPartDelta) and delta.content_delta:
                    yield {
                        "type": "text" if isinstance(delta, TextPartDelta) else "thinking",
                        "text": delta.content_delta,
                    }
    yield {"type": "done", "tools_used": list(dict.fromkeys(used))}
