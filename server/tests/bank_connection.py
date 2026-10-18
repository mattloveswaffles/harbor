"""Bank connection: the Nessie client and the shared bank behaviour (on the test double)."""

import asyncio
import logging
from datetime import date

import httpx
import pytest

from harbor.bank import (
    NessieClient,
    NessieConfigError,
    NessieNotFound,
    NessieRejected,
    NessieUnavailable,
    from_dollars,
    tag_for,
    to_dollars,
)
from tests.nessie_double import NessieDouble

DAY = date(2024, 10, 7)


@pytest.mark.parametrize(
    ("cents", "rounding", "dollars", "rounding_cents"),
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
    with pytest.raises(ValueError, match="never negative"):
        to_dollars(-1, "up")
    with pytest.raises(ValueError, match="unknown rounding"):
        to_dollars(100, "sideways")


def test_from_dollars():
    assert from_dollars(420) == 42000
    assert from_dollars(73.96) == 7396


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def fake():
    bank = NessieDouble()
    cust = run(bank.create_customer("Maria", "Lopez (Harbor demo)", {"zip": "33602"}))
    bank.chk = run(bank.create_account(cust["_id"], "Checking", "Everyday", 420))["_id"]
    bank.sav = run(bank.create_account(cust["_id"], "Savings", "Emergency fund", 500))["_id"]
    return bank


def test_transfer_rounds_up_toward_safety(fake):
    write = run(
        fake.transfer(fake.sav, fake.chk, 30050, rounding="up", on=DAY, move_id="mv_01", memo="Evacuation fund")
    )
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
    with pytest.raises(ValueError, match="rounds to"):
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


KEY = "secret-test-key-123"


def client_with(handler, **kw) -> NessieClient:
    kw.setdefault("backoff", (0, 0, 0))
    kw.setdefault("lookup_delay", 0)
    return NessieClient("https://nessie.test", KEY, transport=httpx.MockTransport(handler), **kw)


def test_rejects_plain_http_base_url():
    with pytest.raises(NessieConfigError):
        NessieClient("http://api.nessieisreal.com", KEY)


def test_missing_key_is_a_config_error():
    c = NessieClient("https://nessie.test", "", transport=httpx.MockTransport(lambda r: httpx.Response(200, json=[])))
    with pytest.raises(NessieConfigError):
        run(c.list_customers())


def test_key_goes_in_the_query_and_never_in_repr():
    seen = []

    def handler(request):
        seen.append(request.url.params.get("key"))
        return httpx.Response(200, json={"_id": "a1", "balance": 420})

    c = client_with(handler)
    assert run(c.get_account("a1"))["balance"] == 420
    assert seen == [KEY]
    assert KEY not in repr(c)


def test_bare_string_errors_become_typed_exceptions():
    def handler(request):
        if request.method == "POST":
            return httpx.Response(400, json="Invalid fields in account")
        return httpx.Response(404, json="Account with this id does not exist")

    c = client_with(handler)
    assert run(c.get_account("nope")) is None
    with pytest.raises(NessieNotFound, match="does not exist"):
        run(c.delete_account("nope"))
    with pytest.raises(NessieRejected, match="Invalid fields"):
        run(c.create_account("cust", "Checking", "Everyday", 420))


def test_none_found_404_is_an_empty_list():
    c = client_with(lambda r: httpx.Response(404, json="No transfers found for this account"))
    assert run(c.list_transactions("acc", "transfers")) == []


def test_gets_retry_on_503_then_succeed():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(503, json={"message": "busy"}) if len(calls) < 3 else httpx.Response(200, json=[])

    assert run(client_with(handler).list_customers()) == []
    assert len(calls) == 3


def test_gets_give_up_after_retries():
    def handler(request):
        raise httpx.ConnectTimeout("timed out", request=request)

    with pytest.raises(NessieUnavailable):
        run(client_with(handler).get_account("a1"))


def test_post_id_from_object_created():
    def handler(request):
        assert request.method == "POST"
        return httpx.Response(201, json={"code": 201, "message": "Created", "objectCreated": {"_id": "tx-1"}})

    write = run(client_with(handler).transfer("sav", "chk", 30050, rounding="up", on=DAY, move_id="mv_01"))
    assert (write.object_id, write.dollars, write.rounding_cents, write.reused) == ("tx-1", 301, 50, False)


def test_post_bare_string_looks_up_id_by_tag():
    posted = {}

    def handler(request):
        if request.method == "POST":
            import json

            posted.update(json.loads(request.content))
            return httpx.Response(201, json="Transfer created")
        return httpx.Response(
            200, json=[{"_id": "tx-old", "description": "other"}, {"_id": "tx-9", "description": posted["description"]}]
        )

    write = run(
        client_with(handler).transfer("sav", "chk", 50000, rounding="up", on=DAY, move_id="mv_02", memo="Evac fund")
    )
    assert write.object_id == "tx-9"
    assert posted == {
        "medium": "balance",
        "amount": 500,
        "transaction_date": "2024-10-07",
        "status": "completed",
        "description": "[harbor:mv_02] Evac fund",
        "payee_id": "chk",
    }


def test_post_timeout_finds_the_landed_write_and_does_not_post_twice():
    posts = []

    def handler(request):
        if request.method == "POST":
            posts.append(1)
            raise httpx.ReadTimeout("timed out", request=request)
        return httpx.Response(200, json=[{"_id": "wd-1", "description": "[harbor:mv_04] Cash"}])

    write = run(client_with(handler).withdraw("chk", 33950, on=DAY, move_id="mv_04", memo="Cash"))
    assert (write.object_id, write.dollars, write.reused) == ("wd-1", 340, True)
    assert len(posts) == 1


def test_post_500_not_landed_is_retried_then_succeeds():
    posts = []

    def handler(request):
        if request.method == "POST":
            posts.append(1)
            if len(posts) == 1:
                return httpx.Response(500, json={"message": "Internal server error"})
            return httpx.Response(201, json={"objectCreated": {"_id": "dep-2"}})
        return httpx.Response(404, json="No deposits found for this account")

    write = run(client_with(handler).deposit("set", 36086, on=DAY, move_id="mv_03"))
    assert write.object_id == "dep-2" and len(posts) == 2


def test_post_4xx_is_never_retried():
    posts = []

    def handler(request):
        posts.append(1)
        return httpx.Response(400, json="Insufficient funds")

    with pytest.raises(NessieRejected, match="Insufficient"):
        run(client_with(handler).withdraw("chk", 100000, on=DAY, move_id="mv_05"))
    assert len(posts) == 1


def test_post_gives_up_after_max_attempts():
    def handler(request):
        if request.method == "POST":
            return httpx.Response(502, json={"message": "Internal server error"})
        return httpx.Response(200, json=[])

    with pytest.raises(NessieUnavailable):
        run(client_with(handler, max_post_attempts=2).transfer("a", "b", 100, rounding="up", on=DAY, move_id="mv_6"))


def test_create_account_without_id_matches_by_nickname():
    def handler(request):
        if request.method == "POST":
            return httpx.Response(201, json="Account created")
        return httpx.Response(
            200, json=[{"_id": "acc-7", "type": "Savings", "nickname": "Brokerage Settlement (Harbor)", "balance": 0}]
        )

    acct = run(client_with(handler).create_account("cust", "Savings", "Brokerage Settlement (Harbor)", 0))
    assert acct["_id"] == "acc-7"


def test_key_never_reaches_logs_or_errors(caplog):
    def handler(request):
        raise httpx.ConnectError("connection refused", request=request)

    caplog.set_level(logging.DEBUG)
    with pytest.raises(NessieUnavailable) as err:
        run(client_with(handler).get_customer("c1"))
    assert KEY not in str(err.value)
    assert KEY not in caplog.text
