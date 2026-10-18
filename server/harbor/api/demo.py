"""Demo controls: reset, replays, clock and the AI toggle. Clock changes tick the scheduler at once."""

from datetime import timedelta

from fastapi import APIRouter, Depends, Request
from sqlmodel import select

from harbor.ai.llm import ai_enabled
from harbor.clock import Clock, DemoClock, iso
from harbor.deps import BankDep, ClockDep, SessionDep, SettingsDep, require_demo
from harbor.engine.risk import Level
from harbor.errors import HarborError
from harbor.executor import catch_up
from harbor.models import User
from harbor.provisioning import reset_user
from harbor.schemas import (
    ClockOut,
    DemoAdvanceIn,
    DemoAiIn,
    DemoAiOut,
    DemoStartIn,
    DemoStormOut,
    ResetOut,
)
from harbor.sources.forecast import list_replays, load_replay
from harbor.ticker import first_time_at, forecast_source, replay_end, reset_cursor, tick

router = APIRouter(prefix="/demo", tags=["demo"], dependencies=[Depends(require_demo)])


@router.post("/reset", response_model=ResetOut)
async def demo_reset(request: Request, session: SessionDep, bank: BankDep, clock: ClockDep) -> ResetOut:
    """Reset accounts, portfolio and plans; the clock goes back to the replay start, paused."""
    if hasattr(clock, "reset"):
        clock.reset()
    reset_cursor(request.app)
    now = clock.now()
    users = session.exec(select(User)).all()
    for user in users:
        await reset_user(session, bank, user, now)
    session.commit()
    return ResetOut(ok=True, server_time=iso(now), users_reset=len(users), clock=clock.state())


@router.get("/clock", response_model=ClockOut)
def demo_clock(clock: ClockDep) -> dict:
    return clock.state()


def demo_clock_or_409(clock: Clock) -> DemoClock:
    if not isinstance(clock, DemoClock):
        raise HarborError(409, "demo_clock_unavailable", "The server isn't running the demo clock.")
    return clock


def started_or_409(clock: Clock) -> DemoClock:
    demo = demo_clock_or_409(clock)
    if demo.storm is None:
        raise HarborError(409, "demo_not_started", "Start a replay first with POST /demo/start.")
    return demo


@router.get("/storms", response_model=list[DemoStormOut])
def demo_storms(settings: SettingsDep) -> list[dict]:
    """The storm replays on disk (built by tools/fetch_replay.py)."""
    return list_replays(settings.replay_dir)


@router.post("/start", response_model=ClockOut)
def demo_start(
    request: Request, clock: ClockDep, settings: SettingsDep, session: SessionDep, body: DemoStartIn | None = None
) -> dict:
    """Restart the replay: clock to its start, every user back to clear. Data stays; /demo/reset clears it."""
    body = body or DemoStartIn()
    replay = load_replay(settings.replay_dir, body.storm)
    if replay is None:
        raise HarborError(404, "storm_not_found", f"No replay called {body.storm!r}. See GET /demo/storms.")
    demo = demo_clock_or_409(clock)
    demo.start(replay.id, at=replay.start, speed=body.speed)
    reset_cursor(request.app)
    for user in session.exec(select(User)).all():
        user.risk_level, user.risk_reason, user.risk_changed_at = "clear", None, replay.start
        session.add(user)
    session.commit()
    tick(request.app)
    return demo.state()


@router.post("/advance", response_model=ClockOut)
async def demo_advance(request: Request, body: DemoAdvanceIn, clock: ClockDep) -> dict:
    """Move the clock: `{"hours"}`, `{"to": "next_advisory"}` or `{"to_risk"}`. Running/paused state is kept;
    every advisory and alert on the way is evaluated in order.
    """
    demo = started_or_409(clock)
    given = [x for x in (body.hours, body.to, body.to_risk) if x is not None]
    if len(given) != 1:
        raise HarborError(
            422,
            "validation_error",
            "Send exactly one of hours, to or to_risk.",
            [{"loc": ["body"], "msg": "exactly one of hours, to, to_risk"}],
        )
    app = request.app
    await catch_up(app, demo.now())  # catch up to now first, so the jump starts from current levels
    now = demo.now()
    if body.hours is not None:
        target = now + timedelta(hours=body.hours)
    elif body.to == "next_advisory":
        source = forecast_source(app)
        target = source.next_advisory_time(now) if source else None
        if target is None:
            raise HarborError(409, "no_more_advisories", "This replay has no more advisories.")
    else:
        source = forecast_source(app)
        target = first_time_at(app, Level(body.to_risk), replay_end(source) if source else now)
        if target is None:
            raise HarborError(409, "risk_level_not_reached", f"No user reaches {body.to_risk} before the replay ends.")
    if target > now:
        demo.advance(target - now)
    await catch_up(app, target)  # risk changes and money moves, in time order
    return demo.state()


@router.post("/pause", response_model=ClockOut)
def demo_pause(request: Request, clock: ClockDep) -> dict:
    demo = started_or_409(clock)
    demo.pause("manual")
    tick(request.app)
    return demo.state()


@router.post("/resume", response_model=ClockOut)
def demo_resume(request: Request, clock: ClockDep) -> dict:
    demo = started_or_409(clock)
    demo.resume()
    return demo.state()


@router.post("/ai", response_model=DemoAiOut)
def demo_ai(request: Request, body: DemoAiIn) -> dict:
    """AI toggle. Off: no chat and rules-only advice; the plan's numbers are unchanged."""
    request.app.state.ai_enabled = body.enabled
    return {"enabled": body.enabled, "ai": "ok" if ai_enabled(request.app) else "off"}
