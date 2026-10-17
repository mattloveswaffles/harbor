"""Dollar rounding and the FakeNessie behaviour every bank client shares."""

import asyncio
from datetime import date

import pytest

from harbor.bank import FakeNessie, NessieRejected, NessieUnavailable, from_dollars, tag_for, to_dollars

DAY = date(2024, 10, 7)


@pytest.mark.parametrize(
    "cents, rounding, dollars, rounding_cents",
    [
        (50000, "up", 500, 0),  # exact stays exact
        (50001, "up", 501, 99),  # toward safety: never short the user
        (36086, "up", 361, 14),
        (99, "up", 1, 1),
        (36086, "down", 360, -86),  # restores: never put back more than was moved
        (50099, "down", 500, -99),
        (100, "down", 1, 0),
        (32000, "up20", 320, 0),  # ATM notes
        (32001, "up20", 340, 1999),
        (33950, "up20", 340, 50),
        (1, "up20", 20, 1999),
        (0, "up", 0, 0),
    ],
)
def test_to_dollars(cents, rounding, dollars, rounding_cents):
    assert to_dollars(cents, rounding) == (dollars, rounding_cents)


def test_to_dollars_rejects_bad_input():
    with pytest.raises(ValueError):
        to_dollars(-1, "up")
    with pytest.raises(ValueError):
        to_dollars(100, "sideways")


def test_from_dollars():
    assert from_dollars(420) == 42000
    assert from_dollars(73.96) == 7396


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def fake():
    bank = FakeNessie()
    cust = run(bank.create_customer("Maria", "Lopez (Harbor demo)", {"zip": "33602"}))
    bank.chk = run(bank.create_account(cust["_id"], "Checking", "Everyday", 420))["_id"]
    bank.sav = run(bank.create_account(cust["_id"], "Savings", "Emergency fund", 500))["_id"]
    return bank


def test_transfer_rounds_up_toward_safety(fake):
    write = run(fake.transfer(fake.sav, fake.chk, 30050, rounding="up", on=DAY, move_id="mv_01", memo="Evacuation fund"))
    assert (write.dollars, write.rounding_cents, write.object_type) == (301, 50, "transfer")
    assert run(fake.get_balance_cents(fake.sav)) == 19900
    assert run(fake.get_balance_cents(fake.chk)) == 72100
    tx = fake.transactions["transfers"][0]
    assert tx["description"] == "[harbor:mv_01] Evacuation fund"
    assert tx["amount"] == 301 and tx["transaction_date"] == "2024-10-07" and tx["status"] == "completed"


def test_restore_rounds_down(fake):
    write = run(fake.transfer(fake.chk, fake.sav, 12099, rounding="down", on=DAY, move_id="mv_09"))
    assert (write.dollars, write.rounding_cents) == (120, -99)
    assert run(fake.get_balance_cents(fake.sav)) == 62000


def test_withdrawal_rounds_to_twenty(fake):
    write = run(fake.withdraw(fake.chk, 33950, on=DAY, move_id="mv_04"))
    assert (write.dollars, write.rounding_cents) == (340, 50)
    assert run(fake.get_balance_cents(fake.chk)) == 8000


def test_deposit(fake):
    write = run(fake.deposit(fake.sav, 36086, on=DAY, move_id="mv_03"))
    assert write.dollars == 361
    assert run(fake.get_balance_cents(fake.sav)) == 86100


def test_overdraft_is_rejected(fake):
    with pytest.raises(NessieRejected):
        run(fake.withdraw(fake.chk, 50000, on=DAY, move_id="mv_05"))
    assert run(fake.get_balance_cents(fake.chk)) == 42000


def test_amount_that_rounds_to_zero_is_refused(fake):
    with pytest.raises(ValueError):
        run(fake.transfer(fake.chk, fake.sav, 50, rounding="down", on=DAY, move_id="mv_06"))


def test_find_by_tag_after_a_dropped_response(fake):
    fake.drop_response_next = True
    with pytest.raises(NessieUnavailable):
        run(fake.transfer(fake.sav, fake.chk, 10000, rounding="up", on=DAY, move_id="mv_07"))
    # The money moved even though the caller saw a timeout; reconcile finds it by tag.
    found = run(fake.find_by_tag(fake.sav, "transfers", tag_for("mv_07")))
    assert found and found["amount"] == 100
    assert run(fake.find_by_tag(fake.sav, "transfers", tag_for("mv_99"))) is None


def test_down_and_fail_next(fake):
    fake.down = True
    with pytest.raises(NessieUnavailable):
        run(fake.get_account(fake.chk))
    fake.down = False
    fake.fail_next.append(NessieUnavailable("boom", 503))
    with pytest.raises(NessieUnavailable):
        run(fake.get_account(fake.chk))
    assert run(fake.get_account(fake.chk))["balance"] == 420
