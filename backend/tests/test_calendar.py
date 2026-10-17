from datetime import date, datetime, timedelta, timezone

from harbor.engine import calendar as cal

UTC = timezone.utc


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
    assert cal.settlement_date(date(2024, 10, 4)) == date(2024, 10, 7)    # Fri -> Mon
    assert cal.settlement_date(date(2024, 10, 11)) == date(2024, 10, 15)  # Columbus Day: Fed closed
    assert cal.is_trading_day(date(2024, 10, 14))                         # ...but the NYSE is open
    assert cal.settlement_date(date(2024, 10, 14)) == date(2024, 10, 15)
    assert cal.settlement_date(date(2024, 11, 27)) == date(2024, 11, 29)  # over Thanksgiving


def test_market_holidays_and_early_closes():
    assert not cal.is_trading_day(date(2024, 11, 28))  # Thanksgiving
    assert not cal.is_trading_day(date(2026, 7, 3))    # July 4 observed on Friday
    assert cal.order_cutoff(date(2024, 11, 29)) == utc(2024, 11, 29, 17, 45)  # 1 pm close, EST
    assert cal.next_sell_time(utc(2024, 11, 28, 15)) == utc(2024, 11, 29, 15)


def test_fed_holiday_observance():
    assert date(2027, 7, 5) in cal.fed_holidays(2027)      # Sunday July 4 -> Monday
    assert date(2026, 7, 3) not in cal.fed_holidays(2026)  # Saturday July 4 -> not observed
    assert date(2024, 10, 14) in cal.fed_holidays(2024)    # Columbus Day
    assert date(2024, 11, 11) in cal.fed_holidays(2024)    # Veterans Day


def test_sale_during_market_hours_runs_immediately():
    now = utc(2024, 10, 7, 16)  # Monday noon ET
    assert cal.next_sell_time(now) == now
