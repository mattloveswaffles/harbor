"""Probe live Nessie behaviour (DESIGN.md §1.8) with a tagged test customer; deletes its accounts after.

uv run python tools/probe_nessie.py
"""

import os
import sys
import time
from datetime import date
from pathlib import Path

import httpx

TAG = "[harbor:probe]"
BACKEND = Path(__file__).resolve().parents[1]
findings: dict[str, str] = {}
limit_headers: set[str] = set()
too_many = 0


def load_env() -> dict[str, str]:
    env = {}
    path = BACKEND / ".env"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


def call(client: httpx.Client, method: str, path: str, json=None):
    global too_many
    res = client.request(method, path, json=json)
    too_many += res.status_code == 429
    limit_headers.update(h for h in res.headers if "ratelimit" in h.lower() or h.lower() == "retry-after")
    try:
        body = res.json()
    except ValueError:
        body = res.text
    shown = str(body)
    print(f"  {method} {path} -> {res.status_code} {shown[:200]}")
    return res.status_code, body


def created_id(body) -> str | None:
    """Classic Nessie returns {"objectCreated": {"_id": ...}}; the current spec says a bare string."""
    if isinstance(body, dict):
        obj = body.get("objectCreated") or body
        return obj.get("_id") or obj.get("id")
    return None


def find(items, **match) -> str | None:
    if isinstance(items, list):
        for item in items:
            if all(item.get(k) == v for k, v in match.items()):
                return item.get("_id")
    return None


def balance(client, account_id) -> int | None:
    status, body = call(client, "GET", f"/accounts/{account_id}")
    return body.get("balance") if status == 200 and isinstance(body, dict) else None


def main() -> int:
    env = load_env()
    key = os.environ.get("NESSIE_API_KEY") or env.get("NESSIE_API_KEY", "")
    base = os.environ.get("NESSIE_BASE_URL") or env.get("NESSIE_BASE_URL") or "https://api.nessieisreal.com"
    if not key:
        print("No NESSIE_API_KEY found.")
        print("Get one: log in at https://nessieisreal.com with GitHub, open Profile, copy the key,")
        print("then put NESSIE_API_KEY=<your key> in server/.env (copy .env.example first).")
        return 1

    today = date.today().isoformat()
    run = str(int(time.time()))
    client = httpx.Client(base_url=base, params={"key": key}, timeout=25)
    accounts: list[str] = []

    try:
        print("\n0. Key check")
        status, body = call(client, "GET", "/customers")
        findings["key_check"] = (
            f"GET /customers -> {status}, {len(body) if isinstance(body, list) else '?'} customers (a wrong key also returns 200 [])"
        )

        print("\na. What POST returns")
        last_name = f"Probe{run}"
        status, body = call(
            client,
            "POST",
            "/customers",
            {
                "first_name": "Harbor",
                "last_name": last_name,
                "address": {
                    "street_number": "1",
                    "street_name": "Probe St",
                    "city": "Tampa",
                    "state": "FL",
                    "zip": "33602",
                },
            },
        )
        customer = created_id(body)
        findings["post_returns_id"] = "yes (objectCreated)" if customer else f"no, body was {str(body)[:80]!r}"
        if not customer:
            _, listing = call(client, "GET", "/customers")
            customer = find(listing, last_name=last_name)
        if not customer:
            print("Could not find the new customer; stopping.")
            return 1

        for nickname, kind, start in ((f"{TAG} checking", "Checking", 500), (f"{TAG} savings", "Savings", 1000)):
            status, body = call(
                client,
                "POST",
                f"/customers/{customer}/accounts",
                {"type": kind, "nickname": nickname, "rewards": 0, "balance": start},
            )
            acc = created_id(body)
            if not acc:
                _, listing = call(client, "GET", f"/customers/{customer}/accounts")
                acc = find(listing, nickname=nickname)
            accounts.append(acc)
        checking, savings = accounts
        if not (checking and savings):
            print("Could not create both accounts; stopping.")
            return 1

        print("\nb. Transfer savings -> checking ($100): does the balance update right away?")
        call(
            client,
            "POST",
            f"/accounts/{savings}/transfers",
            {
                "medium": "balance",
                "payee_id": checking,
                "amount": 100,
                "transaction_date": today,
                "description": f"{TAG} transfer",
            },
        )
        now = (balance(client, checking), balance(client, savings))
        time.sleep(5)
        later = (balance(client, checking), balance(client, savings))
        _, transfers = call(client, "GET", f"/accounts/{savings}/transfers?type=payer")
        status_seen = (
            next((t.get("status") for t in transfers if TAG in str(t.get("description"))), "?")
            if isinstance(transfers, list)
            else "?"
        )
        findings["transfer"] = (
            f"balances right after {now}, after 5 s {later} (started 500/1000); transfer status {status_seen!r}"
        )

        print("\nc. Overdraft: transfer $100000 from checking")
        status, body = call(
            client,
            "POST",
            f"/accounts/{checking}/transfers",
            {
                "medium": "balance",
                "payee_id": savings,
                "amount": 100000,
                "transaction_date": today,
                "description": f"{TAG} overdraft",
            },
        )
        findings["overdraft"] = f"{status} {str(body)[:80]!r}; checking now {balance(client, checking)}"

        print("\nd. Withdrawal ($40) and GET /withdrawal/{id} (singular)")
        status, body = call(
            client,
            "POST",
            f"/accounts/{checking}/withdrawals",
            {
                "medium": "balance",
                "transaction_date": today,
                "amount": 40,
                "description": f"{TAG} withdrawal",
            },
        )
        wid = created_id(body)
        if not wid:
            _, listing = call(client, "GET", f"/accounts/{checking}/withdrawals")
            wid = find(listing, description=f"{TAG} withdrawal")
        if wid:
            singular, _ = call(client, "GET", f"/withdrawal/{wid}")
            plural, _ = call(client, "GET", f"/withdrawals/{wid}")
            findings["withdrawal"] = (
                f"created; GET /withdrawal/id -> {singular}, /withdrawals/id -> {plural}; checking now {balance(client, checking)}"
            )
        else:
            findings["withdrawal"] = f"POST -> {status}, could not find the new withdrawal"

        print("\ne. Deposit ($25)")
        status, body = call(
            client,
            "POST",
            f"/accounts/{checking}/deposits",
            {
                "medium": "balance",
                "transaction_date": today,
                "status": "completed",
                "amount": 25,
                "description": f"{TAG} deposit",
            },
        )
        findings["deposit"] = f"POST -> {status}; checking now {balance(client, checking)}"

        print("\nf. Purchase ($10) at a new merchant")
        status, body = call(
            client,
            "POST",
            "/merchants",
            {
                "name": f"{TAG} Gas {run}",
                "category": ["gas"],
                "address": {
                    "street_number": "1",
                    "street_name": "Main St",
                    "city": "Gainesville",
                    "state": "FL",
                    "zip": "32601",
                },
                "geocode": {"lat": 29.65, "lng": -82.32},
            },
        )
        merchant = created_id(body)
        if merchant:
            status, body = call(
                client,
                "POST",
                f"/accounts/{checking}/purchases",
                {
                    "merchant_id": merchant,
                    "medium": "balance",
                    "purchase_date": today,
                    "amount": 10,
                    "status": "pending",
                    "description": f"{TAG} purchase",
                },
            )
            findings["purchase"] = f"POST -> {status} {str(body)[:80]!r}; checking now {balance(client, checking)}"
        else:
            findings["purchase"] = f"merchant POST -> {status}, no id returned; purchase not tested"

    finally:
        print("\nCleanup")
        for acc in accounts:
            if acc:
                call(client, "DELETE", f"/accounts/{acc}")
        client.close()

    findings["rate_limits"] = f"429s seen: {too_many}; limit headers: {sorted(limit_headers) or 'none'}"
    print("\n=== Findings (copy these into DESIGN.md §1.8) ===")
    for k, v in findings.items():
        print(f"- {k}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
