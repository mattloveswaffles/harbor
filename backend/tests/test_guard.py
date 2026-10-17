from harbor.ai.guard import guarded, numbers_in, validate

SNAPSHOT = {
    "budget": {"total_cents": 128000, "lines": [{"label": "Lodging: 1 room × 3 nights", "amount_cents": 33000}]},
    "sources": {"from_savings_cents": 50000, "from_etf_sales_cents": 36000},
    "storm": {"p34": 0.23, "name": "Milton"},
    "moves": [{"symbol": "TBUX", "shares": 7.18, "gain_cents": 286, "deadline_display": "Mon 3:45 pm ET"}],
    "settlement": "T+1",
    "cash_needed_by": "2024-10-08T18:00:00Z",
}


def test_finds_money_percent_and_decimals():
    assert numbers_in("Move $1,280 now; 23% chance; 7.18 shares") == ["$1,280", "23%", "7.18"]


def test_numbers_from_the_plan_pass():
    text = (
        "The plan gathers $1,280: $500 from savings and $360 from selling 7.18 shares of TBUX, "
        "which realises about $3 (exactly $2.86) of gains. Wind chance is 23%. Approve by Mon 3:45 pm ET "
        "so the sale settles T+1 by Oct 8, 2024. Lodging is 3 nights."
    )
    assert validate([text], SNAPSHOT) == []


def test_invented_numbers_are_caught():
    assert validate(["You could also move $2,000 or sell 10 shares."], SNAPSHOT) == ["$2,000", "10"]


def test_validator_checks_every_text_field():
    assert validate(["Fine: $1,280.", "Bad: 60%."], SNAPSHOT) == ["60%"]


def test_timestamps_only_allow_year_and_day():
    # "2024-10-08T18:00:00Z" must not make 10 or 18 look sourced.
    assert validate(["Arrives by Oct 8, 2024."], SNAPSHOT) == []
    assert validate(["Leave by 18:00."], SNAPSHOT) == ["18"]


def test_words_and_tickers_are_not_numbers():
    assert validate(["Selling TBUX keeps your mix steady. T+1 settlement."], SNAPSHOT) == []


def test_guarded_keeps_valid_ai_text():
    r = guarded(lambda: "The plan gathers $1,280.", lambda t: [t], lambda: "template", SNAPSHOT)
    assert r.source == "claude" and r.value == "The plan gathers $1,280."


def test_guarded_retries_then_falls_back_on_bad_numbers():
    calls = []

    def bad():
        calls.append(1)
        return "Move $9,999."

    r = guarded(bad, lambda t: [t], lambda: "template text", SNAPSHOT)
    assert len(calls) == 2
    assert r.source == "template" and r.value == "template text"
    assert r.violations == ["$9,999"]


def test_guarded_falls_back_on_errors_and_when_ai_is_off():
    def boom():
        raise TimeoutError("20 s")

    r = guarded(boom, lambda t: [t], lambda: "template", SNAPSHOT)
    assert r.source == "template" and "TimeoutError" in r.error
    assert guarded(None, lambda t: [t], lambda: "template", SNAPSHOT).source == "template"
