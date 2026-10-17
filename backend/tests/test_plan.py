from datetime import date, datetime, timedelta, timezone

from harbor.ai.guard import validate
from harbor.engine.plan import (
    Balances, BillIn, LotIn, PlanInputs, PlanSettings, RestoreInputs, SoldPosition,
    build_plan, build_restore, fuel_line, lodging_line,
)
from harbor.evac.household import Household, Pet, budget_lines

UTC = timezone.utc
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
    base = dict(now=SUN, cash_needed_by=NEED_BY, lines=maria_lines(), balances=Balances(42_000, 50_000),
                lots=LOTS, prices_cents=PRICES)
    base.update(kw)
    return PlanInputs(**base)


def test_maria_budget_and_sources_match_the_api_example():
    p = build_plan(maria())
    assert [l.amount_cents for l in p.lines] == [33_000, 4_400, 56_100, 7_500, 12_000, 15_000]
    assert p.total_cents == 128_000
    assert p.sources == {"already_in_checking_cents": 42_000, "from_savings_cents": 50_000, "from_etf_sales_cents": 36_000}
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
    lots = (LotIn("gain", "TCAF", 10_000_000, 20_000, date(2023, 1, 3)),
            LotIn("loss", "TCAF", 10_000_000, 40_000, date(2023, 1, 3)))
    p = build_plan(maria(lots=lots, prices_cents={"TCAF": 3_300}, balances=Balances(42_000, 75_000)))
    sell = next(m for m in p.moves if m.kind == "sell_etf")
    assert sell.lot_sales[0].lot_id == "loss"
    assert any("wash-sale" in w for w in p.warnings)


def test_bill_shield_only_for_bills_due_during_the_storm():
    bills = (BillIn("b1", "Sunshine Auto Insurance", 18_900, date(2024, 10, 9)),
             BillIn("b2", "Phone", 6_000, date(2024, 11, 30)))
    p = build_plan(maria(bills=bills))
    deferred = [m for m in p.moves if m.kind == "defer_bill"]
    assert len(deferred) == 1 and deferred[0].extra == {"bill_id": "b1", "from_date": "2024-10-09", "to_date": "2024-10-15"}


def test_ai_can_quote_every_number_in_the_facts():
    p = build_plan(maria())
    summary = ("The plan gathers $1,280: $420 already in checking, $500 from savings and $360 from selling "
               "7.18 shares of TBUX, about $2.86 of gains. It sells Mon Oct 7 and the cash is ready "
               "Tue Oct 8, 9:00 AM ET. Approve by Mon Oct 7, 1:45 PM ET. $320 is withdrawn as cash.")
    assert validate([summary], p.facts) == []
    assert validate(["Selling 12 shares raises $600."], p.facts) == ["12", "$600"]


def test_restore_refills_savings_first():
    r = build_restore(RestoreInputs(
        now=datetime(2024, 10, 11, 22, tzinfo=UTC), checking_now_cents=60_000, checking_before_cents=42_000,
        moved_from_savings_cents=50_000, sold=(), prices_cents=PRICES,
    ))
    assert r.unspent_cents == 18_000
    assert [(m.kind, m.amount_cents) for m in r.moves] == [("restore_transfer", 18_000)]


def test_restore_rebuys_when_opted_in_and_respects_wash_sales():
    sold = (
        SoldPosition("TBUX", 7_182_762, 36_000, at_loss=False, sold_at=datetime(2024, 10, 7, 14, tzinfo=UTC)),
        SoldPosition("TSPA", 1_000_000, 3_200, at_loss=True, sold_at=datetime(2024, 10, 7, 14, tzinfo=UTC)),
    )
    r = build_restore(RestoreInputs(
        now=datetime(2024, 10, 11, 22, tzinfo=UTC), checking_now_cents=132_000, checking_before_cents=42_000,
        moved_from_savings_cents=50_000, sold=sold, prices_cents={"TBUX": 5_000, "TSPA": 3_200}, rebuy_opt_in=True,
    ))
    by_kind = {m.kind: m for m in r.moves}
    assert by_kind["rebuy_etf"].symbol == "TBUX" and by_kind["rebuy_etf"].amount_cents == 36_000
    assert by_kind["rebuy_etf"].scheduled_for == datetime(2024, 10, 14, 14, tzinfo=UTC)  # Fri night -> Mon 10:00 ET
    assert by_kind["restore_transfer"].amount_cents == 90_000 - 36_000
    assert any("wash-sale" in w for w in r.warnings)


def test_restore_skips_tiny_rebuys():
    sold = (SoldPosition("TBUX", 1_000_000, 5_000, at_loss=False, sold_at=datetime(2024, 10, 7, 14, tzinfo=UTC)),
            SoldPosition("TCAF", 1_000_000, 3_300, at_loss=False, sold_at=datetime(2024, 10, 7, 14, tzinfo=UTC)))
    r = build_restore(RestoreInputs(
        now=datetime(2024, 10, 11, 22, tzinfo=UTC), checking_now_cents=47_001, checking_before_cents=42_000,
        moved_from_savings_cents=0, sold=sold, prices_cents={"TBUX": 5_000, "TCAF": 3_300}, rebuy_opt_in=True,
    ))
    assert [m.symbol for m in r.moves if m.kind == "rebuy_etf"] == ["TBUX"]  # 1 cent left: no TCAF trade
