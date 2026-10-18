"""Demo controls, the demo clock and /health."""

import asyncio
from datetime import UTC, date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from harbor.clock import DemoClock, RealClock, iso, utc
from harbor.main import create_app
from harbor.models import Event, Lot, Move, Plan
from tests.conftest import REPLAY_START, Timer, make_settings
from tests.nessie_double import NessieDouble

API = "/api/v1"


def test_signup_makes_a_pseudonymous_nessie_customer(maria, bank):
    assert maria["name"] == "Maria Lopez" and maria["zip"] == "33602"
    assert maria["location"] == {"lat": 27.953704, "lon": -82.45631}
    hh = maria["household"]
    assert hh["adults"] == 2 and hh["children_ages"] == [7] and hh["pets"] == [{"type": "dog", "count": 1}]
    assert hh["evac_zone"] == "A" and hh["has_car"] is True
    cust = bank.customers[maria["nessie_customer_id"]]
    assert (cust["first_name"], cust["last_name"], cust["address"]["zip"]) == ("Harbor", f"User {maria['id']}", "33602")
    nicknames = sorted(a["nickname"] for a in bank.accounts.values())
    assert nicknames == ["Brokerage Settlement (Harbor)", "Emergency fund", "Everyday"]


def test_signup_gets_the_starter_portfolio(maria, app):
    with Session(app.state.engine) as s:
        lots = s.exec(select(Lot).where(Lot.user_id == maria["id"])).all()
    tbux = [lot for lot in lots if lot.symbol == "TBUX"]
    assert len(tbux) == 1 and tbux[0].shares_micro == 7_200_000 and tbux[0].cost_basis_cents == 35800
    assert tbux[0].acquired == date(2023, 3, 14)
    assert {lot.symbol for lot in lots} == {"TBUX", "TCAF", "TSPA"}


def test_reset_restores_accounts_portfolio_plans_and_clock(client, maria, auth, bank, app, clock):
    accounts = client.get(f"{API}/me/accounts", headers=auth).json()
    chk, sav = accounts[0]["nessie_id"], accounts[1]["nessie_id"]
    asyncio.run(bank.transfer(sav, chk, 50000, rounding="up", on=date(2024, 10, 7), move_id="mv_x"))
    with Session(app.state.engine) as s:
        plan = Plan(user_id=maria["id"], status="running")
        s.add(plan)
        s.commit()
        s.add(Move(plan_id=plan.id, kind="transfer", amount_cents=50000))
        for lot in s.exec(select(Lot).where(Lot.user_id == maria["id"])).all():
            s.delete(lot)
        s.commit()
    clock.start("milton-2024")
    clock.advance(timedelta(hours=30))

    res = client.post(f"{API}/demo/reset")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["ok"] is True and body["users_reset"] == 1
    assert body["server_time"] == "2024-10-06T03:00:00Z"
    assert body["clock"] == {
        "running": False,
        "storm": None,
        "now": "2024-10-06T03:00:00Z",
        "speed": 1800,
        "paused_reason": None,
    }

    after = client.get(f"{API}/me/accounts", headers=auth).json()
    assert [a["balance_cents"] for a in after] == [42000, 50000, 0]
    assert after[0]["nessie_id"] != chk  # Nessie can't set balances, so accounts are recreated
    assert len(bank.accounts) == 3
    with Session(app.state.engine) as s:
        assert s.exec(select(Plan)).all() == [] and s.exec(select(Move)).all() == []
        assert len(s.exec(select(Lot).where(Lot.user_id == maria["id"])).all()) == 4
        events = s.exec(select(Event).where(Event.user_id == maria["id"])).all()
        assert [e.type for e in events] == ["demo_reset"]


def test_demo_clock_endpoint(client, clock, timer):
    assert client.get(f"{API}/demo/clock").json() == {
        "running": False,
        "storm": None,
        "now": "2024-10-06T03:00:00Z",
        "speed": 1800,
        "paused_reason": None,
    }
    clock.start("milton-2024", speed=3600)
    timer.t += 6
    assert client.get(f"{API}/demo/clock").json() == {
        "running": True,
        "storm": "milton-2024",
        "now": "2024-10-06T09:00:00Z",
        "speed": 3600,
        "paused_reason": None,
    }


def test_demo_routes_are_off_in_live_mode(tmp_path, bank):
    app = create_app(make_settings(tmp_path, harbor_mode="live"), bank=bank)
    with TestClient(app) as c:
        for method, path in (("post", "/demo/reset"), ("get", "/demo/clock")):
            res = getattr(c, method)(f"{API}{path}")
            assert res.status_code == 403 and res.json()["error"]["code"] == "demo_mode_only"


def test_iso_is_utc_with_z():
    assert iso(datetime(2024, 10, 6, 15, 0, 0, 123456, tzinfo=UTC)) == "2024-10-06T15:00:00Z"
    assert iso(datetime(2024, 10, 6, 11, 0, tzinfo=timezone(timedelta(hours=-4)))) == "2024-10-06T15:00:00Z"
    assert iso(None) is None
    assert utc(datetime(2024, 1, 1)).tzinfo is UTC


def test_real_clock_is_aware_utc():
    now = RealClock().now()
    assert now.tzinfo is not None and now.utcoffset() == timedelta(0)


def test_demo_clock_waits_paused_at_replay_start():
    timer = Timer()
    clock = DemoClock(REPLAY_START, speed=1800, real=timer)
    timer.t += 100
    assert clock.now() == REPLAY_START
    assert clock.state() == {
        "running": False,
        "storm": None,
        "now": "2024-10-06T03:00:00Z",
        "speed": 1800,
        "paused_reason": None,
    }


def test_demo_clock_runs_at_speed_and_pauses():
    timer = Timer()
    clock = DemoClock(REPLAY_START, speed=1800, real=timer)
    clock.start("milton-2024")
    timer.t += 2  # 2 real seconds × 1800 = 1 storm hour
    assert clock.now() == REPLAY_START + timedelta(hours=1)
    assert clock.running

    clock.pause("awaiting_approval")
    timer.t += 60
    assert clock.now() == REPLAY_START + timedelta(hours=1)
    assert clock.state()["paused_reason"] == "awaiting_approval"
    assert not clock.running

    clock.resume()
    timer.t += 4
    assert clock.now() == REPLAY_START + timedelta(hours=3)


def test_demo_clock_advance_and_reset():
    timer = Timer()
    clock = DemoClock(REPLAY_START, real=timer)
    assert clock.advance(timedelta(hours=6)) == REPLAY_START + timedelta(hours=6)
    assert clock.now() == REPLAY_START + timedelta(hours=6)
    with pytest.raises(ValueError, match="only moves forward"):
        clock.advance(timedelta(hours=-1))
    clock.start("milton-2024", speed=900)
    clock.reset()
    assert clock.now() == REPLAY_START and clock.storm is None and clock.speed == 1800


def test_frozen_clock():
    clock = FrozenClock(REPLAY_START)
    clock.tick(hours=6)
    assert clock.now() == REPLAY_START + timedelta(hours=6)


def test_server_time_header_follows_demo_clock(client, clock, timer):
    assert client.get("/health").headers["X-Server-Time"] == "2024-10-06T03:00:00Z"
    clock.advance(timedelta(hours=12))
    assert client.get("/health").headers["X-Server-Time"] == "2024-10-06T15:00:00Z"
    assert client.get("/api/v1/demo/clock").json()["now"] == "2024-10-06T15:00:00Z"


def live_client(tmp_path, bank, key="test-key"):
    return TestClient(create_app(make_settings(tmp_path, nessie_api_key=key), bank=bank))


def test_health_reports_status(client):
    res = client.get("/health")
    assert res.status_code == 200
    body = res.json()
    assert body == {
        "ok": True,
        "mode": "demo",
        "nessie": "ok",
        "nhc": "replay",
        "ai": "off",
        "chat": "off",
        "clock": "2024-10-06T03:00:00Z",
    }
    assert res.headers["X-Server-Time"] == "2024-10-06T03:00:00Z"


def test_health_missing_key(tmp_path):
    with live_client(tmp_path, NessieDouble(), key="") as c:
        assert c.get("/health").json()["nessie"] == "missing_key"


def test_health_ok_when_nessie_answers(tmp_path):
    with live_client(tmp_path, NessieDouble()) as c:
        assert c.get("/health").json()["nessie"] == "ok"


def test_health_degraded_when_nessie_is_down(tmp_path):
    bank = NessieDouble()
    bank.down = True
    with live_client(tmp_path, bank) as c:
        assert c.get("/health").json()["nessie"] == "degraded"


def test_unknown_route_uses_error_envelope(client):
    res = client.get("/api/v1/does-not-exist")
    assert res.status_code == 404
    error = res.json()["error"]
    assert error["code"] == "http_404"
    assert "message" in error


def test_openapi_lists_the_h2_8_endpoints(app):
    paths = app.openapi()["paths"]
    for path in (
        "/health",
        "/api/v1/zip/{zip}",
        "/api/v1/users",
        "/api/v1/me",
        "/api/v1/me/household",
        "/api/v1/me/accounts",
        "/api/v1/demo/reset",
        "/api/v1/demo/clock",
    ):
        assert path in paths, path


def test_the_app_clock_is_real_time_until_a_scenario_starts():
    real = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)
    clock = DemoClock(datetime(2024, 10, 6, 3, 0, tzinfo=UTC), idle=lambda: real)
    assert clock.now() == real and clock.state()["storm"] is None
    clock.start("milton-2024")
    assert clock.now().year == 2024
    clock.reset()
    assert clock.now() == real


class FrozenClock:
    """For tests: time only moves when the test says so."""

    def __init__(self, at: datetime):
        self._now = utc(at)

    def now(self) -> datetime:
        return self._now

    def set(self, at: datetime) -> None:
        self._now = utc(at)

    def tick(self, **kwargs) -> datetime:
        self._now += timedelta(**kwargs)
        return self._now

    def state(self) -> dict:
        return {"running": False, "storm": None, "now": iso(self._now), "speed": 0, "paused_reason": None}
