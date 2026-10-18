"""Event bus: `record` adds a row; subscribers get it only after the commit, with `seq` set.
Publishing is thread-safe (scheduler and sync routes commit from worker threads).
"""

from __future__ import annotations

import asyncio
import contextlib
import threading
from datetime import datetime

from sqlalchemy import event as sa_event
from sqlalchemy.orm import Session as OrmSession
from sqlmodel import Session, col, select

from harbor.clock import iso
from harbor.models import Event

MAX_STREAMS_PER_USER = 5  # a 6th connection closes the oldest one (stale tabs, reconnect storms)

_PENDING = "harbor_events_pending"  # Event objects not flushed yet
_FLUSHED = "harbor_events_flushed"  # serialised events waiting for the commit


def event_to_api(e: Event) -> dict:
    return {"id": e.id, "at": iso(e.at), "type": e.type, "message": e.message, "data": e.data or {}}


class Subscription:
    """One open SSE connection: an asyncio queue that belongs to the loop that created it."""

    def __init__(self, user_id: str):
        self.user_id = user_id
        self.loop = asyncio.get_running_loop()
        self.queue: asyncio.Queue[tuple[int, dict] | None] = asyncio.Queue()

    def put(self, item: tuple[int, dict] | None) -> None:
        with contextlib.suppress(RuntimeError):  # the loop is closed: the connection is gone
            self.loop.call_soon_threadsafe(self.queue.put_nowait, item)

    async def get(self) -> tuple[int, dict] | None:
        return await self.queue.get()


class EventBus:
    """In-process fan-out of committed events to each user's open streams (one process, 1 worker)."""

    def __init__(self):
        self._lock = threading.Lock()
        self._subs: dict[str, list[Subscription]] = {}

    def subscribe(self, user_id: str) -> Subscription:
        sub = Subscription(user_id)
        with self._lock:
            subs = self._subs.setdefault(user_id, [])
            subs.append(sub)
            evicted = subs[:-MAX_STREAMS_PER_USER]
            del subs[:-MAX_STREAMS_PER_USER]
        for old in evicted:
            old.put(None)  # tells that stream to end
        return sub

    def unsubscribe(self, sub: Subscription) -> None:
        with self._lock:
            subs = self._subs.get(sub.user_id, [])
            if sub in subs:
                subs.remove(sub)
            if not subs:
                self._subs.pop(sub.user_id, None)

    def subscribers(self, user_id: str) -> int:
        with self._lock:
            return len(self._subs.get(user_id, []))

    def publish(self, user_id: str, seq: int, payload: dict) -> None:
        with self._lock:
            subs = list(self._subs.get(user_id, []))
        for sub in subs:
            sub.put((seq, payload))


bus = EventBus()


def record(session: Session, user_id: str, at: datetime, type: str, message: str, data: dict | None = None) -> Event:
    """Add an event to the session. It reaches the activity feed and open streams when the session commits."""
    event = Event(user_id=user_id, at=at, type=type, message=message, data=data or {})
    session.add(event)
    session.info.setdefault(_PENDING, []).append(event)
    return event


@sa_event.listens_for(OrmSession, "after_flush")
def _serialise_flushed(session, _flush_context) -> None:
    pending = session.info.get(_PENDING)
    if not pending:
        return
    still = []
    for e in pending:
        if e.seq is None:
            still.append(e)
        else:
            session.info.setdefault(_FLUSHED, []).append((e.user_id, e.seq, event_to_api(e)))
    session.info[_PENDING] = still


@sa_event.listens_for(OrmSession, "after_commit")
def _publish_committed(session) -> None:
    flushed = session.info.pop(_FLUSHED, None)
    for user_id, seq, payload in flushed or ():
        bus.publish(user_id, seq, payload)


@sa_event.listens_for(OrmSession, "after_rollback")
def _drop_rolled_back(session) -> None:
    session.info.pop(_FLUSHED, None)
    session.info.pop(_PENDING, None)


def latest(session: Session, user_id: str, types: tuple[str, ...]) -> Event | None:
    return session.exec(
        select(Event).where(Event.user_id == user_id, col(Event.type).in_(types)).order_by(col(Event.seq).desc())
    ).first()


def events_after(session: Session, user_id: str, seq: int, limit: int = 500) -> list[Event]:
    """Events newer than `seq`, oldest first (the SSE replay after a reconnect)."""
    return list(
        session.exec(
            select(Event).where(Event.user_id == user_id, col(Event.seq) > seq).order_by(col(Event.seq)).limit(limit)
        ).all()
    )


def feed(session: Session, user_id: str, limit: int, before_seq: int | None = None) -> list[Event]:
    """The activity feed page: newest first, optionally only events older than `before_seq`."""
    q = select(Event).where(Event.user_id == user_id)
    if before_seq is not None:
        q = q.where(col(Event.seq) < before_seq)
    return list(session.exec(q.order_by(col(Event.seq).desc()).limit(limit)).all())
