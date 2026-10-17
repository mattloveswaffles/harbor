import asyncio
from datetime import date, timedelta

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from harbor.main import create_app
from harbor.models import Event, Lot, Move, Plan
from tests.conftest import make_settings

API = "/api/v1"


def test_persona_seeds_maria(maria, bank):
    assert maria["name"] == "Maria Lopez" and maria["zip"] == "33602"
    assert maria["location"] == {"lat": 27.953704, "lon": -82.45631}
    hh = maria["household"]
    assert hh["adults"] == 2 and hh["children_ages"] == [7] and hh["pets"] == [{"type": "dog", "count": 1}]
    assert hh["evac_zone"] == "A" and hh["has_car"] is True
    cust = bank.customers[maria["nessie_customer_id"]]
    assert (cust["first_name"], cust["last_name"], cust["address"]["zip"]) == ("Maria", "Lopez (Harbor demo)", "33602")
    nicknames = sorted(a["nickname"] for a in bank.accounts.values())
    assert nicknames == ["Brokerage Settlement (Harbor)", "Emergency fund", "Everyday"]


def test_persona_seeds_the_etf_lots(maria, app):
    with Session(app.state.engine) as s:
        lots = s.exec(select(Lot).where(Lot.user_id == maria["id"])).all()
    tbux = [lot for lot in lots if lot.symbol == "TBUX"]
    assert len(tbux) == 1 and tbux[0].shares_micro == 7_200_000 and tbux[0].cost_basis_cents == 35800
    assert tbux[0].acquired == date(2023, 3, 14)
    assert {lot.symbol for lot in lots} == {"TBUX", "TCAF", "TSPA"}


def test_persona_is_idempotent(client, maria, bank):
    again = client.post(f"{API}/demo/persona", json={"persona": "maria"}).json()
    assert again["id"] == maria["id"]
    assert len(bank.customers) == 1 and len(bank.accounts) == 3
    # The body is optional.
    assert client.post(f"{API}/demo/persona").json()["id"] == maria["id"]


def test_persona_repairs_a_wiped_bank(client, maria, bank):
    bank.customers.clear()
    bank.accounts.clear()
    again = client.post(f"{API}/demo/persona").json()
    assert again["id"] == maria["id"]
    assert again["nessie_customer_id"] in bank.customers and len(bank.accounts) == 3
    balances = [a["balance_cents"] for a in client.get(f"{API}/me/accounts", headers={"X-User-Id": maria["id"]}).json()]
    assert balances == [42000, 50000, 0]


def test_unknown_persona_is_a_validation_error(client):
    res = client.post(f"{API}/demo/persona", json={"persona": "bob"})
    assert res.status_code == 422 and res.json()["error"]["code"] == "validation_error"


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
    assert body["clock"] == {"running": False, "storm": None, "now": "2024-10-06T03:00:00Z", "speed": 1800, "paused_reason": None}

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
        for method, path in (("post", "/demo/persona"), ("post", "/demo/reset"), ("get", "/demo/clock")):
            res = getattr(c, method)(f"{API}{path}")
            assert res.status_code == 403 and res.json()["error"]["code"] == "demo_mode_only"
