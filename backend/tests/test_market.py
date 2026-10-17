from datetime import datetime, timezone

from harbor.sources.market import FixturePrices

UTC = timezone.utc
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
