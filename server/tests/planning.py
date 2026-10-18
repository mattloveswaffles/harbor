"""Planning: the rules engine, market calendar, prices and the money moves it runs."""

from datetime import UTC, date, datetime, timedelta

from sqlmodel import Session, col, select

from harbor.engine import calendar as cal
from harbor.engine.plan import (
    Balances,
    BillIn,
    LotIn,
    PlanInputs,
    PlanSettings,
    RestoreInputs,
    SoldPosition,
    build_plan,
    build_restore,
    fuel_line,
    lodging_line,
)
from harbor.evac.household import Household, Pet, budget_lines
from harbor.models import Event
from harbor.sources.market import FixturePrices

UTC = UTC


MARIA = Household(adults=2, children_ages=(7,), pets=(Pet("dog"),), evac_zone="A")


PRICES = {"TBUX": 5012, "TCAF": 3300, "TSPA": 3200}


LOTS = (
    LotIn("lot_tbux", "TBUX", 7_200_000, 35_800, date(2023, 3, 14)),
    LotIn("lot_tcaf1", "TCAF", 50_000_000, 135_500, date(2023, 9, 12)),
    LotIn("lot_tcaf2", "TCAF", 30_000_000, 91_200, date(2024, 2, 20)),
    LotIn("lot_tspa", "TSPA", 40_000_000, 114_000, date(2023, 11, 7)),
)


SUN = datetime(2024, 10, 6, 15, 2, tzinfo=UTC)


NEED_BY = datetime(2024, 10, 8, 18, tzinfo=UTC)


def maria_lines():
    return (
        lodging_line("Gainesville", 11_000, rooms=1, nights=3, source="gsa_per_diem_fy2025"),
        fuel_line(262),
        *budget_lines(MARIA, days=3, nights=3, meals_rate_cents=6_800, meals_source="gsa_per_diem_fy2025"),
    )


def maria(**kw) -> PlanInputs:
    base = {
        "now": SUN,
        "cash_needed_by": NEED_BY,
        "lines": maria_lines(),
        "balances": Balances(42_000, 50_000),
        "lots": LOTS,
        "prices_cents": PRICES,
    }
    base.update(kw)
    return PlanInputs(**base)


def test_maria_budget_and_sources_match_the_api_example():
    p = build_plan(maria())
    assert [l.amount_cents for l in p.lines] == [33_000, 4_400, 56_100, 7_500, 12_000, 15_000]
    assert p.total_cents == 128_000
    assert p.sources == {
        "already_in_checking_cents": 42_000,
        "from_savings_cents": 50_000,
        "from_etf_sales_cents": 36_000,
    }
    assert p.shortfall_cents == 0 and p.help_resources == []


def test_maria_moves_and_timing():
    p = build_plan(maria())
    kinds = [m.kind for m in p.moves]
    assert kinds == ["transfer", "sell_etf", "withdraw_cash"]
    transfer, sell, cash = p.moves
    assert transfer.amount_cents == 50_000 and transfer.scheduled_for == SUN + timedelta(hours=2)
    # Weekend: the sale waits for Monday 10:00 ET and settles Tuesday 09:00 ET.
    assert sell.symbol == "TBUX" and sell.requires_explicit_approval
    assert sell.scheduled_for == datetime(2024, 10, 7, 14, tzinfo=UTC)
    assert sell.expected_available_at == datetime(2024, 10, 8, 13, tzinfo=UTC)
    assert sell.amount_cents == 36_000 and not sell.arrives_late
    assert cash.amount_cents == 32_000 and cash.amount_cents % 2_000 == 0
    assert cash.depends_on == ["mv_transfer"] and cash.scheduled_for == transfer.scheduled_for
    # Approve by Monday 15:45 ET minus the 2 h cancel window.
    assert p.latest_safe_approval_at == datetime(2024, 10, 7, 17, 45, tzinfo=UTC)


def test_tax_note_and_lot_choice():
    p = build_plan(maria())
    sell = p.moves[1]
    assert [s.lot_id for s in sell.lot_sales] == ["lot_tbux"]  # the storm sleeve goes first
    assert sell.gain_cents == 286
    assert p.tax_note == "Selling 7.18 shares of TBUX realises about $2.86 of long-term gains."


def test_alternatives_are_priced():
    alts = {a.id: a for a in build_plan(maria()).alternatives}
    assert not alts["alt_no_etf"].feasible and "$920" in alts["alt_no_etf"].why_not
    shelter = alts["alt_public_shelter"]
    assert shelter.feasible and shelter.total_cents == 95_000 and shelter.etf_sale_cents == 3_000


def test_sale_that_settles_too_late_is_shown_but_not_counted():
    p = build_plan(maria(now=datetime(2024, 10, 8, 14, tzinfo=UTC)))
    sell = next(m for m in p.moves if m.kind == "sell_etf")
    assert sell.arrives_late
    assert p.sources["from_etf_sales_cents"] == 0
    assert p.shortfall_cents == 36_000
    assert p.help_resources and p.latest_safe_approval_at is None
    assert any("settle after you need the cash" in w for w in p.warnings)


def test_etf_cap_leaves_a_shortfall_with_help():
    p = build_plan(maria(settings=PlanSettings(max_etf_sell_cents=10_000)))
    assert p.sources["from_etf_sales_cents"] == 10_000
    assert p.shortfall_cents == 26_000
    assert p.help_resources[0]["phone"] == "211"


def test_no_etf_needed_when_savings_cover_it():
    p = build_plan(maria(balances=Balances(42_000, 200_000)))
    assert [m.kind for m in p.moves] == ["transfer", "withdraw_cash"]
    assert p.latest_safe_approval_at is None and p.tax_note is None


def test_loss_lots_sell_first_and_warn_about_wash_sales():
    lots = (
        LotIn("gain", "TCAF", 10_000_000, 20_000, date(2023, 1, 3)),
        LotIn("loss", "TCAF", 10_000_000, 40_000, date(2023, 1, 3)),
    )
    p = build_plan(maria(lots=lots, prices_cents={"TCAF": 3_300}, balances=Balances(42_000, 75_000)))
    sell = next(m for m in p.moves if m.kind == "sell_etf")
    assert sell.lot_sales[0].lot_id == "loss"
    assert any("wash-sale" in w for w in p.warnings)


def test_bill_shield_only_for_bills_due_during_the_storm():
    bills = (
        BillIn("b1", "Sunshine Auto Insurance", 18_900, date(2024, 10, 9)),
        BillIn("b2", "Phone", 6_000, date(2024, 11, 30)),
    )
    p = build_plan(maria(bills=bills))
    deferred = [m for m in p.moves if m.kind == "defer_bill"]
    assert len(deferred) == 1 and deferred[0].extra == {
        "bill_id": "b1",
        "from_date": "2024-10-09",
        "to_date": "2024-10-15",
    }


def test_restore_refills_savings_first():
    r = build_restore(
        RestoreInputs(
            now=datetime(2024, 10, 11, 22, tzinfo=UTC),
            checking_now_cents=60_000,
            checking_before_cents=42_000,
            moved_from_savings_cents=50_000,
            sold=(),
            prices_cents=PRICES,
        )
    )
    assert r.unspent_cents == 18_000
    assert [(m.kind, m.amount_cents) for m in r.moves] == [("restore_transfer", 18_000)]


def test_restore_rebuys_when_opted_in_and_respects_wash_sales():
    sold = (
        SoldPosition("TBUX", 7_182_762, 36_000, at_loss=False, sold_at=datetime(2024, 10, 7, 14, tzinfo=UTC)),
        SoldPosition("TSPA", 1_000_000, 3_200, at_loss=True, sold_at=datetime(2024, 10, 7, 14, tzinfo=UTC)),
    )
    r = build_restore(
        RestoreInputs(
            now=datetime(2024, 10, 11, 22, tzinfo=UTC),
            checking_now_cents=132_000,
            checking_before_cents=42_000,
            moved_from_savings_cents=50_000,
            sold=sold,
            prices_cents={"TBUX": 5_000, "TSPA": 3_200},
            rebuy_opt_in=True,
        )
    )
    by_kind = {m.kind: m for m in r.moves}
    assert by_kind["rebuy_etf"].symbol == "TBUX" and by_kind["rebuy_etf"].amount_cents == 36_000
    assert by_kind["rebuy_etf"].scheduled_for == datetime(2024, 10, 14, 14, tzinfo=UTC)  # Fri night -> Mon 10:00 ET
    assert by_kind["restore_transfer"].amount_cents == 90_000 - 36_000
    assert any("wash-sale" in w for w in r.warnings)


def test_restore_skips_tiny_rebuys():
    sold = (
        SoldPosition("TBUX", 1_000_000, 5_000, at_loss=False, sold_at=datetime(2024, 10, 7, 14, tzinfo=UTC)),
        SoldPosition("TCAF", 1_000_000, 3_300, at_loss=False, sold_at=datetime(2024, 10, 7, 14, tzinfo=UTC)),
    )
    r = build_restore(
        RestoreInputs(
            now=datetime(2024, 10, 11, 22, tzinfo=UTC),
            checking_now_cents=47_001,
            checking_before_cents=42_000,
            moved_from_savings_cents=0,
            sold=sold,
            prices_cents={"TBUX": 5_000, "TCAF": 3_300},
            rebuy_opt_in=True,
        )
    )
    assert [m.symbol for m in r.moves if m.kind == "rebuy_etf"] == ["TBUX"]  # 1 cent left: no TCAF trade


def utc(*args) -> datetime:
    return datetime(*args, tzinfo=UTC)


def test_eastern_time_follows_daylight_saving():
    assert cal.from_et(date(2024, 10, 7), cal.SELL_TIME) == utc(2024, 10, 7, 14)  # EDT, UTC-4
    assert cal.from_et(date(2024, 11, 4), cal.SELL_TIME) == utc(2024, 11, 4, 15)  # EST, UTC-5
    assert cal.from_et(date(2024, 3, 8), cal.SELL_TIME) == utc(2024, 3, 8, 15)
    assert cal.from_et(date(2024, 3, 11), cal.SELL_TIME) == utc(2024, 3, 11, 14)
    assert cal.to_et(utc(2024, 10, 7, 14)) == datetime(2024, 10, 7, 10)


def test_milton_weekend_gap():
    # First advisories came on the weekend: the sale waits for Monday 10:00 ET.
    sale = cal.next_sell_time(utc(2024, 10, 5, 15))
    assert sale == utc(2024, 10, 7, 14)
    assert cal.cash_available_at(sale) == utc(2024, 10, 8, 13)  # Tuesday 09:00 ET


def test_milton_latest_safe_approval_is_monday_1545_et():
    deadline = cal.latest_safe_approval_at(
        cash_needed_by=utc(2024, 10, 8, 18), now=utc(2024, 10, 6, 15), cancel_window=timedelta(0)
    )
    assert deadline == utc(2024, 10, 7, 19, 45)


def test_cancel_window_moves_the_approval_deadline_earlier():
    deadline = cal.latest_safe_approval_at(utc(2024, 10, 8, 18), utc(2024, 10, 6, 15), timedelta(hours=2))
    assert deadline == utc(2024, 10, 7, 17, 45)


def test_too_late_returns_none_and_flags_arrives_late():
    now = utc(2024, 10, 7, 20, 30)  # Monday after the cutoff
    need = utc(2024, 10, 8, 18)
    assert cal.latest_safe_approval_at(need, now, timedelta(0)) is None
    assert cal.arrives_late(now, need) is True
    assert cal.arrives_late(utc(2024, 10, 6, 15), need) is False


def test_settlement_skips_weekends_and_bank_holidays():
    assert cal.settlement_date(date(2024, 10, 4)) == date(2024, 10, 7)  # Fri -> Mon
    assert cal.settlement_date(date(2024, 10, 11)) == date(2024, 10, 15)  # Columbus Day: Fed closed
    assert cal.is_trading_day(date(2024, 10, 14))  # ...but the NYSE is open
    assert cal.settlement_date(date(2024, 10, 14)) == date(2024, 10, 15)
    assert cal.settlement_date(date(2024, 11, 27)) == date(2024, 11, 29)  # over Thanksgiving


def test_market_holidays_and_early_closes():
    assert not cal.is_trading_day(date(2024, 11, 28))  # Thanksgiving
    assert not cal.is_trading_day(date(2026, 7, 3))  # July 4 observed on Friday
    assert cal.order_cutoff(date(2024, 11, 29)) == utc(2024, 11, 29, 17, 45)  # 1 pm close, EST
    assert cal.next_sell_time(utc(2024, 11, 28, 15)) == utc(2024, 11, 29, 15)


def test_fed_holiday_observance():
    assert date(2027, 7, 5) in cal.fed_holidays(2027)  # Sunday July 4 -> Monday
    assert date(2026, 7, 3) not in cal.fed_holidays(2026)  # Saturday July 4 -> not observed
    assert date(2024, 10, 14) in cal.fed_holidays(2024)  # Columbus Day
    assert date(2024, 11, 11) in cal.fed_holidays(2024)  # Veterans Day


def test_sale_during_market_hours_runs_immediately():
    now = utc(2024, 10, 7, 16)  # Monday noon ET
    assert cal.next_sell_time(now) == now


prices = FixturePrices()


def test_all_t_rowe_etfs_have_milton_prices():
    for symbol in ("TBUX", "TCAF", "TSPA", "TOUS", "TOTR"):
        p = prices.price_at(symbol, datetime(2024, 10, 7, 21, tzinfo=UTC))
        assert p is not None and p.price_cents > 0
        assert p.name.startswith("T. Rowe Price")


def test_no_peeking_at_todays_close_before_4pm():
    before = prices.price_at("TBUX", datetime(2024, 10, 7, 19, tzinfo=UTC))  # Mon 3 pm ET
    after = prices.price_at("TBUX", datetime(2024, 10, 7, 20, 1, tzinfo=UTC))  # Mon 4:01 pm ET
    assert before.as_of.date().isoformat() == "2024-10-04"  # Friday's close
    assert after.as_of.date().isoformat() == "2024-10-07"


def test_weekend_uses_fridays_close_and_unknown_symbols_are_skipped():
    sunday = datetime(2024, 10, 6, 15, tzinfo=UTC)
    assert prices.price_at("TCAF", sunday).as_of.date().isoformat() == "2024-10-04"
    assert set(prices.prices_at({"TBUX", "NOPE"}, sunday)) == {"TBUX"}


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
    assert (
        client.post(f"{API}/me/plan/approve", headers=auth, json={"plan_version": 1}).json()["plan"]["status"]
        == "approved"
    )

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
    for t in (
        "plan_created",
        "plan_approved",
        "move_done",
        "plan_complete",
        "recovery_hold",
        "plan_restoring",
        "plan_restored",
    ):
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
    assert (
        client.post(f"{API}/me/plan/approve", headers=auth, json={"plan_version": 2}).json()["error"]["code"]
        == "plan_version_stale"
    )
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
