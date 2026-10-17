"""Activity feed, the event bus and the SSE stream (driven through the real ASGI app)."""

import asyncio
import json

from sqlmodel import Session

from harbor.clock import iso
from harbor.events import MAX_STREAMS_PER_USER, bus, record

API = "/api/v1"


def add_event(app, user_id, type_="sensor_alert", message="test event", data=None):
    """Commit one event the way the scheduler does: its own session, from any thread."""
    with Session(app.state.engine) as s:
        e = record(s, user_id, app.state.clock.now(), type_, message, data or {"n": 1})
        s.commit()
        return e.seq


# --- The feed ----------------------------------------------------------------------------------

def test_feed_is_newest_first_and_pages_with_before(client, auth, app, maria):
    for i in range(5):
        add_event(app, maria["id"], message=f"event {i}")
    page = client.get(f"{API}/me/events?limit=3", headers=auth).json()
    assert [e["message"] for e in page] == ["event 4", "event 3", "event 2"]
    assert set(page[0]) == {"id", "at", "type", "message", "data"} and page[0]["id"].startswith("evt_")
    older = client.get(f"{API}/me/events?limit=50&before={page[-1]['id']}", headers=auth).json()
    assert [e["message"] for e in older][:2] == ["event 1", "event 0"]
    assert all(e["id"] not in {p["id"] for p in page} for e in older)


def test_feed_errors(client, auth):
    assert client.get(f"{API}/me/events").json()["error"]["code"] == "auth_required"
    res = client.get(f"{API}/me/events?before=evt_nope", headers=auth)
    assert res.status_code == 404 and res.json()["error"]["code"] == "event_not_found"
    assert client.get(f"{API}/me/events?limit=0", headers=auth).status_code == 422


def test_storm_events_reach_the_feed(client, auth):
    client.post(f"{API}/demo/start")
    types = [e["type"] for e in client.get(f"{API}/me/events", headers=auth).json()]
    assert {"advisory_issued", "risk_changed", "plan_created"} <= set(types)


# --- The bus -----------------------------------------------------------------------------------

def test_commit_pushes_to_subscribers_and_rollback_does_not(app, maria, client):
    async def run():
        sub = bus.subscribe(maria["id"])
        try:
            # A rolled-back event never reaches the stream.
            def rolled_back():
                with Session(app.state.engine) as s:
                    record(s, maria["id"], app.state.clock.now(), "sensor_alert", "never happened")
                    s.flush()
                    s.rollback()
            await asyncio.to_thread(rolled_back)
            # The scheduler commits from a worker thread: the event still arrives on this loop.
            seq = await asyncio.to_thread(add_event, app, maria["id"], "balance_changed", "moved")
            got_seq, payload = await asyncio.wait_for(sub.get(), 2)
            assert got_seq == seq and payload["type"] == "balance_changed" and payload["message"] == "moved"
            assert sub.queue.empty()
        finally:
            bus.unsubscribe(sub)
        assert bus.subscribers(maria["id"]) == 0

    asyncio.run(run())


def test_a_sixth_stream_closes_the_oldest(maria, client):
    async def run():
        subs = [bus.subscribe(maria["id"]) for _ in range(MAX_STREAMS_PER_USER + 1)]
        try:
            assert bus.subscribers(maria["id"]) == MAX_STREAMS_PER_USER
            assert await asyncio.wait_for(subs[0].get(), 1) is None
        finally:
            for s in subs:
                bus.unsubscribe(s)

    asyncio.run(run())


def test_demo_reset_event_is_pushed(client, maria, app):
    async def run():
        sub = bus.subscribe(maria["id"])
        try:
            await asyncio.to_thread(client.post, f"{API}/demo/reset")
            _, payload = await asyncio.wait_for(sub.get(), 2)
            assert payload["type"] == "demo_reset"
        finally:
            bus.unsubscribe(sub)

    asyncio.run(run())


# --- The SSE stream ----------------------------------------------------------------------------

class Stream:
    """Calls the ASGI app directly and reads the SSE body as it arrives (TestClient buffers)."""

    def __init__(self, app, user_id, last_event_id=None):
        self.app = app
        headers = [(b"host", b"test"), (b"accept", b"text/event-stream")]
        if last_event_id is not None:
            headers.append((b"last-event-id", str(last_event_id).encode()))
        self.scope = {
            "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "GET", "scheme": "http",
            "path": f"{API}/me/events/stream", "raw_path": f"{API}/me/events/stream".encode(),
            "query_string": f"user_id={user_id}".encode(), "headers": headers, "root_path": "",
            "client": ("test", 1), "server": ("test", 80),
        }
        self.messages: asyncio.Queue = asyncio.Queue()
        self.gone = asyncio.Event()
        self.requested = False
        self.buffer = b""
        self.status = None
        self.headers = {}

    async def _receive(self):
        if not self.requested:
            self.requested = True
            return {"type": "http.request", "body": b"", "more_body": False}
        await self.gone.wait()
        return {"type": "http.disconnect"}

    async def _send(self, message):
        await self.messages.put(message)

    async def __aenter__(self):
        self.task = asyncio.create_task(self.app(self.scope, self._receive, self._send))
        start = await asyncio.wait_for(self.messages.get(), 5)
        self.status = start["status"]
        self.headers = {k.decode().lower(): v.decode() for k, v in start["headers"]}
        return self

    async def __aexit__(self, *exc):
        self.gone.set()
        try:
            await asyncio.wait_for(self.task, 5)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            self.task.cancel()

    async def frame(self, timeout=5) -> str:
        """The next SSE frame (lines up to the blank line), as text."""
        while b"\n\n" not in self.buffer:
            msg = await asyncio.wait_for(self.messages.get(), timeout)
            if msg["type"] == "http.response.body":
                self.buffer += msg.get("body", b"")
                if not msg.get("more_body", False) and b"\n\n" not in self.buffer:
                    raise EOFError("stream ended")
        frame, self.buffer = self.buffer.split(b"\n\n", 1)
        return frame.decode()

    async def event(self, timeout=5) -> tuple[str | None, dict]:
        """The next frame with data: returns (id, data). Comments and pings are skipped."""
        while True:
            lines = (await self.frame(timeout)).splitlines()
            assert not any(l.startswith("event:") for l in lines), "the type lives in data.type, not event:"
            data = [l[len("data: "):] for l in lines if l.startswith("data: ")]
            if data:
                ids = [l[len("id: "):] for l in lines if l.startswith("id: ")]
                return (ids[0] if ids else None), json.loads("\n".join(data))


def test_stream_rejects_an_unknown_user(app, client):
    async def run():
        async with Stream(app, "usr_nobody") as s:
            assert s.status == 401
            msg = await asyncio.wait_for(s.messages.get(), 5)
            assert json.loads(msg["body"])["error"]["code"] == "user_not_found"

    asyncio.run(run())


def test_stream_pushes_new_events_instantly(app, maria, client):
    async def run():
        async with Stream(app, maria["id"]) as s:
            assert s.status == 200 and s.headers["content-type"].startswith("text/event-stream")
            first = await s.frame()
            assert ": connected" in first and "retry: 3000" in first
            seq = await asyncio.to_thread(add_event, app, maria["id"], "move_done", "Savings moved", {"x": 1})
            event_id, data = await s.event()
            assert event_id == str(seq)
            assert data["type"] == "move_done" and data["message"] == "Savings moved" and data["data"] == {"x": 1}
            assert data["at"] == iso(app.state.clock.now())
        assert bus.subscribers(maria["id"]) == 0  # the connection cleaned up after itself

    asyncio.run(run())


def test_stream_replays_after_last_event_id_then_goes_live(app, maria, client):
    seqs = [add_event(app, maria["id"], message=f"e{i}") for i in range(4)]

    async def run():
        async with Stream(app, maria["id"], last_event_id=seqs[1]) as s:
            await s.frame()  # connected
            replayed = [await s.event() for _ in range(2)]
            assert [d["message"] for _, d in replayed] == ["e2", "e3"]
            assert [i for i, _ in replayed] == [str(seqs[2]), str(seqs[3])]
            await asyncio.to_thread(add_event, app, maria["id"], message="live")
            _, live = await s.event()
            assert live["message"] == "live"

    asyncio.run(run())


def test_last_event_id_can_be_an_event_id(app, maria, client):
    add_event(app, maria["id"], message="old")
    feed = client.get(f"{API}/me/events?limit=1", headers={"X-User-Id": maria["id"]}).json()
    add_event(app, maria["id"], message="newer")

    async def run():
        async with Stream(app, maria["id"], last_event_id=feed[0]["id"]) as s:
            await s.frame()
            _, data = await s.event()
            assert data["message"] == "newer"

    asyncio.run(run())


def test_stream_sends_a_ping_when_idle(app, maria, client, monkeypatch):
    import fastapi.routing

    monkeypatch.setattr(fastapi.routing, "_PING_INTERVAL", 0.05)

    async def run():
        async with Stream(app, maria["id"]) as s:
            await s.frame()  # connected
            assert (await s.frame()).strip() == ": ping"

    asyncio.run(run())


def test_events_from_another_user_are_not_streamed(app, maria, client):
    other = client.post(f"{API}/users", json={"name": "Sam", "zip": "33602"}).json()

    async def run():
        async with Stream(app, maria["id"]) as s:
            await s.frame()
            await asyncio.to_thread(add_event, app, other["id"], message="not yours")
            await asyncio.to_thread(add_event, app, maria["id"], message="yours")
            _, data = await s.event()
            assert data["message"] == "yours"

    asyncio.run(run())
