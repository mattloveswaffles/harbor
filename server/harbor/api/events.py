"""GET /me/events and its SSE stream. Events are `data:` JSON (read `data.type`); `seq` is the SSE id and
`Last-Event-ID` replays what was missed.
"""

from collections.abc import AsyncIterable
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.sse import EventSourceResponse, ServerSentEvent
from sqlmodel import Session, select

from harbor.deps import SessionDep, UserDep, user_from_authorization
from harbor.errors import HarborError
from harbor.events import bus, event_to_api, events_after, feed
from harbor.models import Event
from harbor.schemas import EventOut

router = APIRouter(tags=["events"])

RETRY_MS = 3000  # how long the browser waits before reconnecting


def _seq_of(session: Session, user_id: str, event_id: str) -> int | None:
    event = session.exec(select(Event).where(Event.id == event_id, Event.user_id == user_id)).first()
    return event.seq if event else None


@router.get("/me/events", response_model=list[EventOut])
def list_events(
    session: SessionDep,
    user: UserDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    before: Annotated[str | None, Query(description="An event id: return only events older than it")] = None,
) -> list[dict]:
    """The activity feed, newest first. Page back with `before=<id of the last event you have>`."""
    before_seq = None
    if before is not None:
        before_seq = _seq_of(session, user.id, before)
        if before_seq is None:
            raise HarborError(404, "event_not_found", "No event with this id in your feed.")
    return [event_to_api(e) for e in feed(session, user.id, limit, before_seq)]


def stream_user(
    request: Request,
    token: Annotated[str | None, Query(description="The login token (EventSource can't send headers)")] = None,
) -> str:
    # Its own short session: a yield dependency's session would stay open for the whole stream.
    with Session(request.app.state.engine) as session:
        return user_from_authorization(session, f"Bearer {token}" if token else None).id


def _last_seq(engine, user_id: str, last_event_id: str | None) -> int | None:
    """Last-Event-ID is the seq we sent as the SSE id; an event id (evt_...) works too."""
    if not last_event_id:
        return None
    value = last_event_id.strip()
    if value.isdigit():
        return int(value)
    with Session(engine) as session:
        return _seq_of(session, user_id, value)


@router.get(
    "/me/events/stream",
    response_class=EventSourceResponse,
    responses={200: {"description": "Each Event as `data:` JSON; the SSE `id` is the event's seq."}},
)
async def stream_events(
    request: Request,
    user_id: Annotated[str, Depends(stream_user)],
    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
) -> AsyncIterable[ServerSentEvent]:
    """Live activity feed as Server-Sent Events. Reconnects replay from `Last-Event-ID`."""
    engine = request.app.state.engine
    sub = bus.subscribe(user_id)  # subscribe before the replay, so nothing slips between the two
    try:
        yield ServerSentEvent(comment="connected", retry=RETRY_MS)
        last = _last_seq(engine, user_id, last_event_id)
        if last is not None:
            with Session(engine) as session:
                missed = events_after(session, user_id, last)
            for e in missed:
                yield ServerSentEvent(data=event_to_api(e), id=str(e.seq))
                last = e.seq
        while True:
            item = await sub.get()
            if item is None:  # a newer connection for this user replaced this one
                return
            seq, payload = item
            if last is not None and seq <= last:
                continue  # already sent in the replay
            last = seq
            yield ServerSentEvent(data=payload, id=str(seq))
    finally:
        bus.unsubscribe(sub)
