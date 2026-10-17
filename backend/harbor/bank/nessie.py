"""Nessie API client: tagged writes, find_by_tag reconcile, cents <-> whole-dollar conversion.

Nessie quirks this handles (DESIGN.md "Nessie bank layer"):
- HTTPS only; the key travels as ?key=, so URLs are never logged and errors only carry the path.
- Errors are often bare JSON strings ("Customer not found"), not {code, message}.
- An empty list can come back as 404 "No transfers found for this account".
- A POST may return only "Transfer created" with no id, so every write is tagged [harbor:{move_id}]
  and looked up by that tag. A POST is never retried blindly: after a timeout or 5xx Harbor first
  checks whether the write landed.
"""

import asyncio
import logging
import random
import re
from urllib.parse import urlparse

import httpx

from harbor.bank.base import (
    Bank,
    NessieConfigError,
    NessieError,
    NessieNotFound,
    NessieRejected,
    NessieUnavailable,
    TxKind,
)

log = logging.getLogger("harbor.nessie")
# httpx logs every request URL at INFO, and our URLs carry the key. Keep it quiet.
logging.getLogger("httpx").setLevel(logging.WARNING)

RETRY_STATUSES = {502, 503, 504}
NONE_FOUND = re.compile(r"^no .* found", re.IGNORECASE)


def error_message(body) -> str:
    if isinstance(body, str):
        return body
    if isinstance(body, dict):
        return str(body.get("message") or body.get("error") or body)
    return str(body)


def created_id(body) -> str | None:
    """Classic Nessie returns {"objectCreated": {"_id": ...}}; the current spec says a bare string."""
    if isinstance(body, dict):
        obj = body.get("objectCreated") or body
        if isinstance(obj, dict):
            return obj.get("_id") or obj.get("id")
    return None


class NessieClient(Bank):
    kind = "nessie"

    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = 8.0,
        backoff: tuple[float, ...] = (0.3, 1.0, 2.5),
        lookup_delay: float = 1.0,
        max_post_attempts: int = 3,
    ):
        if urlparse(base_url).scheme != "https":
            raise NessieConfigError("NESSIE_BASE_URL must start with https:// (Nessie refuses plain HTTP).")
        self._key = api_key
        self._backoff = backoff
        self._lookup_delay = lookup_delay
        self._max_post_attempts = max_post_attempts
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=httpx.Timeout(timeout, connect=min(timeout, 4.0)),
            transport=transport,
        )

    def __repr__(self) -> str:
        return f"NessieClient(base_url={str(self._client.base_url)!r}, key={'set' if self._key else 'missing'})"

    async def close(self) -> None:
        await self._client.aclose()

    # HTTP ------------------------------------------------------------------------------
    async def _send(self, method: str, path: str, json=None, retry: bool = True) -> tuple[int, object]:
        """One request (GETs and DELETEs retry on timeouts and 502/503/504). Returns (status, body)."""
        if not self._key:
            raise NessieConfigError("NESSIE_API_KEY is not set. Add it to backend/.env or use NESSIE_MODE=fake.")
        tries = (len(self._backoff) + 1) if retry else 1
        for attempt in range(tries):
            last = attempt == tries - 1
            try:
                res = await self._client.request(method, path, params={"key": self._key}, json=json)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                log.warning("nessie %s %s failed: %s", method, path, type(exc).__name__)
                if last:
                    raise NessieUnavailable(f"Nessie did not answer {method} {path} ({type(exc).__name__}).") from None
                await self._sleep(attempt)
                continue
            try:
                body = res.json()
            except ValueError:
                body = res.text
            log.info("nessie %s %s -> %s", method, path, res.status_code)
            if res.status_code in RETRY_STATUSES and not last:
                await self._sleep(attempt)
                continue
            return res.status_code, body
        raise AssertionError("unreachable")

    async def _sleep(self, attempt: int) -> None:
        delay = self._backoff[min(attempt, len(self._backoff) - 1)]
        if delay:
            await asyncio.sleep(delay * random.uniform(0.8, 1.2))

    @staticmethod
    def _raise(status: int, body, method: str, path: str) -> None:
        message = error_message(body)
        if status == 404:
            raise NessieNotFound(message, status)
        if 400 <= status < 500:
            raise NessieRejected(message, status)
        raise NessieUnavailable(f"Nessie returned {status} for {method} {path}: {message}", status)

    async def _get(self, path: str) -> object | None:
        """GET one object; None on 404."""
        status, body = await self._send("GET", path)
        if status == 404:
            return None
        if status >= 300:
            self._raise(status, body, "GET", path)
        return body

    async def _list(self, path: str) -> list[dict]:
        status, body = await self._send("GET", path)
        if status == 404 and NONE_FOUND.match(error_message(body)):
            return []
        if status >= 300:
            self._raise(status, body, "GET", path)
        return body if isinstance(body, list) else []

    async def _create(self, path: str, body: dict) -> tuple[int, object]:
        """A POST that can't carry a tag (customers, accounts). Not retried."""
        status, resp = await self._send("POST", path, json=body, retry=False)
        if status >= 300:
            self._raise(status, resp, "POST", path)
        return status, resp

    # Customers and accounts -------------------------------------------------------------
    async def create_customer(self, first_name: str, last_name: str, address: dict) -> dict:
        body = {"first_name": first_name, "last_name": last_name, "address": address}
        _, resp = await self._create("/customers", body)
        if created_id(resp):
            return {**body, **(resp.get("objectCreated") or resp)}
        matches = [
            c for c in await self.list_customers() if c.get("first_name") == first_name and c.get("last_name") == last_name
        ]
        if not matches:
            raise NessieUnavailable("Nessie said the customer was created but it isn't listed yet.")
        return matches[-1]

    async def get_customer(self, customer_id: str) -> dict | None:
        return await self._get(f"/customers/{customer_id}")

    async def list_customers(self) -> list[dict]:
        return await self._list("/customers")

    async def create_account(self, customer_id: str, type: str, nickname: str, balance_dollars: int) -> dict:
        body = {"type": type, "nickname": nickname, "rewards": 0, "balance": int(balance_dollars)}
        _, resp = await self._create(f"/customers/{customer_id}/accounts", body)
        if created_id(resp):
            return {**body, "customer_id": customer_id, **(resp.get("objectCreated") or resp)}
        matches = [a for a in await self.list_accounts(customer_id) if a.get("nickname") == nickname and a.get("type") == type]
        if not matches:
            raise NessieUnavailable("Nessie said the account was created but it isn't listed yet.")
        return matches[-1]

    async def list_accounts(self, customer_id: str) -> list[dict]:
        return await self._list(f"/customers/{customer_id}/accounts")

    async def get_account(self, account_id: str) -> dict | None:
        return await self._get(f"/accounts/{account_id}")

    async def delete_account(self, account_id: str) -> None:
        path = f"/accounts/{account_id}"
        status, body = await self._send("DELETE", path)
        if status >= 300:
            self._raise(status, body, "DELETE", path)

    # Bills (bodies from the Nessie OpenAPI spec; the PUT body is UNVERIFIED until the hour-1 probe)
    async def create_bill(self, account_id, payee, amount_cents, due, nickname):
        body = {"status": "pending", "payee": payee, "nickname": nickname,
                "payment_date": due.isoformat(), "payment_amount": round(amount_cents / 100, 2)}
        _, resp = await self._create(f"/accounts/{account_id}/bills", body)
        if created_id(resp):
            return created_id(resp)
        match = [b for b in await self._list(f"/accounts/{account_id}/bills") if b.get("nickname") == nickname]
        return match[-1].get("_id") if match else None

    async def update_bill_date(self, bill_id, due):
        path = f"/bills/{bill_id}"
        status, body = await self._send("PUT", path, json={"payment_date": due.isoformat()})
        if status >= 300:
            self._raise(status, body, "PUT", path)

    # Transactions ---------------------------------------------------------------------
    async def list_transactions(self, account_id: str, kind: TxKind) -> list[dict]:
        return await self._list(f"/accounts/{account_id}/{kind}")

    async def _lookup(self, account_id: str, kind: TxKind, tag: str) -> dict | None:
        """Look for a tagged write twice, a moment apart (Nessie may list it late)."""
        for attempt in range(2):
            try:
                found = await self.find_by_tag(account_id, kind, tag)
            except NessieError:
                found = None
            if found:
                return found
            if attempt == 0 and self._lookup_delay:
                await asyncio.sleep(self._lookup_delay)
        return None

    async def _write(self, account_id: str, kind: TxKind, body: dict, tag: str) -> tuple[str | None, bool]:
        path = f"/accounts/{account_id}/{kind}"
        for _ in range(self._max_post_attempts):
            try:
                status, resp = await self._send("POST", path, json=body, retry=False)
            except NessieUnavailable:
                status, resp = None, None
            if status is not None and status < 300:
                object_id = created_id(resp)
                if object_id:
                    return object_id, False
                found = await self._lookup(account_id, kind, tag)
                return (found or {}).get("_id"), False
            if status is not None and status < 500:
                self._raise(status, resp, "POST", path)  # 4xx: Nessie said no; never retry
            # Timeout or 5xx: the write may still have landed. Check before sending it again.
            found = await self._lookup(account_id, kind, tag)
            if found:
                return found.get("_id"), True
        raise NessieUnavailable(f"Nessie did not accept POST {path} after {self._max_post_attempts} tries.")
