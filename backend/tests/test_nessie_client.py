"""NessieClient against a mocked HTTP transport: Nessie's quirks, retries and tag reconcile."""

import asyncio
import logging
from datetime import date

import httpx
import pytest

from harbor.bank import NessieClient, NessieConfigError, NessieNotFound, NessieRejected, NessieUnavailable

KEY = "secret-test-key-123"
DAY = date(2024, 10, 7)


def run(coro):
    return asyncio.run(coro)


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
        return httpx.Response(200, json=[{"_id": "tx-old", "description": "other"}, {"_id": "tx-9", "description": posted["description"]}])

    write = run(client_with(handler).transfer("sav", "chk", 50000, rounding="up", on=DAY, move_id="mv_02", memo="Evac fund"))
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
        return httpx.Response(200, json=[{"_id": "acc-7", "type": "Savings", "nickname": "Brokerage Settlement (Harbor)", "balance": 0}])

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
