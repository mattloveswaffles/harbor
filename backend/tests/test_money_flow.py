"""The whole money loop over the real Milton replay: plan, approve, move, freeze, hold, restore."""

from sqlmodel import Session, col, select

from harbor.models import Event

API = "/api/v1"


def balances(client, auth):
    return {a["type"]: a["balance_cents"] for a in client.get(f"{API}/me/accounts", headers=auth).json()}


def event_types(app, user_id):
    with Session(app.state.engine) as s:
        return [e.type for e in s.exec(select(Event).where(Event.user_id == user_id).order_by(col(Event.seq))).all()]


def start(client, auth):
    client.post(f"{API}/demo/start")
    return client.get(f"{API}/me/plan", headers=auth).json()["plan"]


def test_plan_is_made_when_maria_reaches_act(client, auth):
    plan = start(client, auth)
    assert plan["status"] == "awaiting_approval" and plan["decided_by"] == "rules"
    assert plan["budget"]["lines"][0]["label"].startswith("Lodging: ")
    assert plan["sources"]["already_in_checking_cents"] == 42_000 and plan["sources"]["from_savings_cents"] == 50_000
    assert plan["sources"]["from_etf_sales_cents"] > 0 and plan["shortfall_cents"] == 0
    kinds = [m["kind"] for m in plan["moves"]]
    assert kinds[0] == "transfer" and "sell_etf" in kinds and "withdraw_cash" in kinds and kinds[-1] == "defer_bill"
    sale = next(m for m in plan["moves"] if m["kind"] == "sell_etf")
    assert sale["symbol"] == "TBUX" and sale["requires_explicit_approval"]
    assert sale["scheduled_for"] == "2024-10-07T14:00:00Z"  # Sunday plan: the sale waits for Monday 10 am ET
    assert all(m["status"] == "proposed" for m in plan["moves"])


def test_full_storm_with_real_bank_writes(client, auth, app, maria):
    plan = start(client, auth)
    gathered = plan["budget"]["total_cents"]
    assert client.post(f"{API}/me/plan/approve", headers=auth, json={"plan_version": 1}).json()["plan"]["status"] == "approved"

    client.post(f"{API}/demo/advance", json={"to_risk": "shelter"})
    plan = client.get(f"{API}/me/plan", headers=auth).json()["plan"]
    assert plan["status"] == "complete"
    money = [m for m in plan["moves"] if m["kind"] in ("transfer", "sell_etf", "withdraw_cash")]
    assert all(m["status"] == "done" and m["nessie_object_id"] for m in money)
    cash = next(m for m in money if m["kind"] == "withdraw_cash")
    assert cash["nessie_amount_dollars"] % 20 == 0
    b = balances(client, auth)
    assert b["savings"] == 0 and b["brokerage_cash"] == 0
    assert b["checking"] >= gathered - cash["amount_cents"] - 100 * len(money)  # whole-dollar rounding

    # Alerts end on 10 Oct, but the river holds recovery until Sunday evening.
    client.post(f"{API}/demo/advance", json={"to_risk": "recover"})
    assert client.get(f"{API}/me/storm", headers=auth).json()["risk_level"] == "recover"
    client.post(f"{API}/demo/advance", json={"hours": 2})
    assert client.get(f"{API}/me/storm", headers=auth).json()["risk_level"] == "clear"
    b2 = balances(client, auth)
    assert b2["checking"] == 42_000  # back to where it was before the plan
    assert b2["savings"] == b["checking"] - 42_000
    types = event_types(app, maria["id"])
    for t in ("plan_created", "plan_approved", "move_done", "plan_complete", "recovery_hold", "plan_restoring", "plan_restored"):
        assert t in types, t
    assert types.index("recovery_hold") < types.index("plan_restoring")
    sold = client.get(f"{API}/me/portfolio", headers=auth).json()["holdings"]
    assert "TBUX" not in {h["symbol"] for h in sold}  # the storm sleeve was sold whole


def test_approving_at_shelter_moves_nothing_until_recovery(client, auth):
    start(client, auth)
    client.post(f"{API}/demo/advance", json={"to_risk": "shelter"})
    client.post(f"{API}/me/plan/approve", headers=auth, json={"plan_version": 1})
    client.post(f"{API}/demo/advance", json={"hours": 6})
    plan = client.get(f"{API}/me/plan", headers=auth).json()["plan"]
    assert all(m["status"] in ("scheduled", "cancelled") for m in plan["moves"])
    assert balances(client, auth)["savings"] == 50_000  # no bank writes during landfall


def test_approve_checks_version_and_status(client, auth):
    start(client, auth)
    assert client.post(f"{API}/me/plan/approve", headers=auth, json={"plan_version": 2}).json()["error"]["code"] == "plan_version_stale"
    client.post(f"{API}/me/plan/approve", headers=auth, json={"plan_version": 1})
    again = client.post(f"{API}/me/plan/approve", headers=auth, json={"plan_version": 1})
    assert again.status_code == 409 and again.json()["error"]["code"] == "plan_not_awaiting_approval"


def test_cancel_one_move_inside_its_window(client, auth):
    plan = start(client, auth)
    client.post(f"{API}/me/plan/approve", headers=auth, json={"plan_version": 1})
    sale = next(m for m in plan["moves"] if m["kind"] == "sell_etf")
    res = client.post(f"{API}/me/plan/moves/{sale['id']}/cancel", headers=auth)
    assert res.status_code == 200
    assert next(m for m in res.json()["plan"]["moves"] if m["id"] == sale["id"])["status"] == "cancelled"
    transfer = plan["moves"][0]
    client.post(f"{API}/demo/advance", json={"hours": 3})  # the transfer has run
    late = client.post(f"{API}/me/plan/moves/{transfer['id']}/cancel", headers=auth)
    assert late.status_code == 409 and late.json()["error"]["code"] == "move_already_running"


def test_cancelling_the_plan_puts_money_back(client, auth):
    start(client, auth)
    client.post(f"{API}/me/plan/approve", headers=auth, json={"plan_version": 1})
    client.post(f"{API}/demo/advance", json={"hours": 3})  # savings moved, cash withdrawn
    assert balances(client, auth)["savings"] == 0
    assert client.post(f"{API}/me/plan/cancel", headers=auth).json()["plan"]["status"] == "restoring"
    client.post(f"{API}/demo/advance", json={"hours": 1})
    b = balances(client, auth)
    assert b["checking"] == 42_000 and b["savings"] > 0


def test_storm_turning_away_expires_an_unapproved_plan(client):
    # Live Oak, inland north Florida: prepare on Monday, then the storm turns away on Wednesday.
    user = client.post(f"{API}/users", json={"name": "Sam Rivera", "zip": "32060"}).json()
    h = {"X-User-Id": user["id"]}
    client.post(f"{API}/demo/start")
    client.post(f"{API}/demo/advance", json={"to_risk": "prepare"})
    assert client.get(f"{API}/me/plan", headers=h).json()["plan"]["status"] == "awaiting_approval"
    client.post(f"{API}/demo/advance", json={"to": "next_advisory"})
    for _ in range(12):
        if client.get(f"{API}/me/storm", headers=h).json()["risk_level"] == "monitor":
            break
        client.post(f"{API}/demo/advance", json={"hours": 6})
    assert client.get(f"{API}/me/storm", headers=h).json()["risk_level"] == "monitor"
    assert client.get(f"{API}/me/plan", headers=h).json()["plan"] is None
    past = client.get(f"{API}/me/plans", headers=h).json()["plans"]
    assert past[0]["status"] == "expired"


def test_bill_shield_moves_marias_bill_in_nessie(client, auth, bank):
    bills = client.get(f"{API}/me/bills", headers=auth).json()
    assert [b["payee"] for b in bills] == ["Sunshine Auto Insurance (demo)"] and bills[0]["due_date"] == "2024-10-09"
    plan = start(client, auth)
    shield = next(m for m in plan["moves"] if m["kind"] == "defer_bill")
    assert shield["requires_explicit_approval"] and shield["extra"]["to_date"] > "2024-10-13"
    assert client.get(f"{API}/me/bills", headers=auth).json()[0]["in_storm_window"]
    client.post(f"{API}/me/plan/approve", headers=auth, json={"plan_version": 1})
    client.post(f"{API}/demo/advance", json={"hours": 3})
    bill = client.get(f"{API}/me/bills", headers=auth).json()[0]
    assert bill["deferred"] and bill["due_date"] == shield["extra"]["to_date"]
    assert bank.bills[bill["nessie_id"]]["payment_date"] == shield["extra"]["to_date"]  # really moved in Nessie


def test_rebuy_after_the_storm_when_opted_in(client, auth):
    client.patch(f"{API}/me", headers=auth, json={"settings": {"rebuy_opt_in": True}})
    start(client, auth)
    client.post(f"{API}/me/plan/approve", headers=auth, json={"plan_version": 1})
    client.post(f"{API}/demo/advance", json={"to_risk": "recover"})
    plan = client.get(f"{API}/me/plan", headers=auth).json()["plan"]
    rebuys = [m for m in plan["moves"] if m["kind"] == "rebuy_etf"]
    assert rebuys and all(m["requires_explicit_approval"] for m in rebuys)
    client.post(f"{API}/demo/advance", json={"hours": 24 * 2})  # Sunday evening -> Monday's market open
    plan_after = client.get(f"{API}/me/plans", headers=auth).json()["plans"][0]
    done = [m for m in plan_after["moves"] if m["kind"] == "rebuy_etf"]
    assert done and all(m["status"] == "done" for m in done)
    symbols = {h["symbol"] for h in client.get(f"{API}/me/portfolio", headers=auth).json()["holdings"]}
    assert {m["symbol"] for m in done} <= symbols
    assert balances(client, auth)["brokerage_cash"] == 0


def test_demo_clock_waits_for_approval(client, auth):
    start(client, auth)  # Maria reaches act at the replay start, so a plan is waiting
    clock = client.get(f"{API}/demo/clock").json()
    assert clock["running"] is False and clock["paused_reason"] == "awaiting_approval"
    client.post(f"{API}/me/plan/approve", headers=auth, json={"plan_version": 1})
    clock = client.get(f"{API}/demo/clock").json()
    assert clock["running"] is True and clock["paused_reason"] is None
