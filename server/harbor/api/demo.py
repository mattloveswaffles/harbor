"""Demo controls: start the Milton replay and reset everything."""

from fastapi import APIRouter, Depends, Request
from sqlmodel import select

from harbor.clock import iso
from harbor.deps import BankDep, ClockDep, SessionDep, SettingsDep, require_demo
from harbor.errors import HarborError
from harbor.models import User
from harbor.provisioning import reset_user
from harbor.schemas import ClockOut, DemoStartIn, ResetOut
from harbor.sources.forecast import load_replay
from harbor.ticker import reset_cursor, tick

router = APIRouter(prefix="/demo", tags=["demo"], dependencies=[Depends(require_demo)])


@router.post("/reset", response_model=ResetOut)
async def demo_reset(request: Request, session: SessionDep, bank: BankDep, clock: ClockDep) -> ResetOut:
    """Reset accounts, portfolio and plans; the clock goes back to the replay start, paused."""
    clock.reset()
    reset_cursor(request.app)
    now = clock.now()
    users = session.exec(select(User)).all()
    for user in users:
        await reset_user(session, bank, user, now)
    session.commit()
    return ResetOut(ok=True, server_time=iso(now), users_reset=len(users), clock=clock.state())


@router.post("/start", response_model=ClockOut)
def demo_start(
    request: Request, clock: ClockDep, settings: SettingsDep, session: SessionDep, body: DemoStartIn | None = None
) -> dict:
    """Restart the replay: clock to its start, every user back to clear. Data stays; /demo/reset clears it."""
    body = body or DemoStartIn()
    replay = load_replay(settings.replay_dir, body.storm)
    if replay is None:
        raise HarborError(404, "storm_not_found", f"No replay called {body.storm!r}.")
    clock.start(replay.id, at=replay.start, speed=body.speed)
    reset_cursor(request.app)
    for user in session.exec(select(User)).all():
        user.risk_level, user.risk_reason, user.risk_changed_at = "clear", None, replay.start
        session.add(user)
    session.commit()
    tick(request.app)
    return clock.state()
