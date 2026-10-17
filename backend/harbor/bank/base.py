"""What every bank client shares: errors, cents <-> whole-dollar rounding, tags and the public methods.

Harbor keeps exact cents. Nessie stores whole dollars, so amounts are converted only here:
- "up":   ceil, for money moving toward the user's safety (savings -> checking, settlement deposits)
- "down": floor, for restores (checking -> savings), so Harbor never puts back more than was moved
- "up20": ceil to a multiple of $20, for cash withdrawals (ATM notes)
The difference is returned as `rounding_cents` so the Move can store it.
"""

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

Rounding = Literal["up", "down", "up20"]
TxKind = Literal["transfers", "withdrawals", "deposits"]


class NessieError(Exception):
    retryable = False

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.message = message
        self.status = status


class NessieUnavailable(NessieError):
    """Timeouts, connection errors and 5xx: try again later."""

    retryable = True


class NessieNotFound(NessieError):
    pass


class NessieRejected(NessieError):
    """A 4xx: Nessie refused the request. Never retried."""


class NessieConfigError(NessieError):
    """Missing key or a bad base URL. Fix the .env, don't retry."""


def to_dollars(cents: int, rounding: Rounding) -> tuple[int, int]:
    """Return (whole dollars for Nessie, rounding_cents = dollars*100 - cents)."""
    if cents < 0:
        raise ValueError("amounts are never negative")
    if rounding == "up":
        dollars = math.ceil(cents / 100)
    elif rounding == "down":
        dollars = cents // 100
    elif rounding == "up20":
        dollars = math.ceil(cents / 2000) * 20
    else:
        raise ValueError(f"unknown rounding {rounding!r}")
    return dollars, dollars * 100 - cents


def from_dollars(dollars: int | float) -> int:
    return round(dollars * 100)


def tag_for(move_id: str) -> str:
    return f"[harbor:{move_id}]"


@dataclass
class BankWrite:
    object_id: str | None
    object_type: str  # transfer | withdrawal | deposit
    dollars: int
    rounding_cents: int
    tag: str
    reused: bool = False  # True when find_by_tag found an earlier write instead of POSTing again


class Bank(ABC):
    """Same interface for NessieClient and FakeNessie. Ids are Nessie ids."""

    kind: str = "base"

    # Customers and accounts -------------------------------------------------------------
    @abstractmethod
    async def create_customer(self, first_name: str, last_name: str, address: dict) -> dict: ...

    @abstractmethod
    async def get_customer(self, customer_id: str) -> dict | None: ...

    @abstractmethod
    async def list_customers(self) -> list[dict]: ...

    @abstractmethod
    async def create_account(self, customer_id: str, type: str, nickname: str, balance_dollars: int) -> dict: ...

    @abstractmethod
    async def list_accounts(self, customer_id: str) -> list[dict]: ...

    @abstractmethod
    async def get_account(self, account_id: str) -> dict | None: ...

    @abstractmethod
    async def delete_account(self, account_id: str) -> None: ...

    # Transactions ---------------------------------------------------------------------
    @abstractmethod
    async def list_transactions(self, account_id: str, kind: TxKind) -> list[dict]: ...

    @abstractmethod
    async def _write(self, account_id: str, kind: TxKind, body: dict, tag: str) -> tuple[str | None, bool]:
        """POST one transaction; return (nessie id or None, reused)."""

    async def close(self) -> None:
        pass

    # Bills (the bill shield) ------------------------------------------------------------
    @abstractmethod
    async def create_bill(self, account_id: str, payee: str, amount_cents: int, due: date, nickname: str) -> str | None:
        """Create a pending bill; return its Nessie id."""

    @abstractmethod
    async def update_bill_date(self, bill_id: str, due: date) -> None:
        """Move a bill's payment date."""

    async def find_by_tag(self, account_id: str, kind: TxKind, tag: str) -> dict | None:
        for tx in await self.list_transactions(account_id, kind):
            if tag in (tx.get("description") or ""):
                return tx
        return None

    async def get_balance_cents(self, account_id: str) -> int | None:
        acct = await self.get_account(account_id)
        return from_dollars(acct.get("balance", 0)) if acct else None

    async def _money(
        self,
        kind: TxKind,
        object_type: str,
        account_id: str,
        amount_cents: int,
        rounding: Rounding,
        on: date,
        move_id: str,
        memo: str,
        extra: dict[str, Any] | None = None,
    ) -> BankWrite:
        dollars, rounding_cents = to_dollars(amount_cents, rounding)
        if dollars <= 0:
            raise ValueError("amount rounds to $0; nothing to send")
        tag = tag_for(move_id)
        body = {
            "medium": "balance",
            "amount": dollars,
            "transaction_date": on.isoformat(),
            "status": "completed",
            "description": f"{tag} {memo}".strip(),
            **(extra or {}),
        }
        object_id, reused = await self._write(account_id, kind, body, tag)
        return BankWrite(object_id, object_type, dollars, rounding_cents, tag, reused)

    async def transfer(
        self, from_id: str, to_id: str, amount_cents: int, *, rounding: Rounding, on: date, move_id: str, memo: str = ""
    ) -> BankWrite:
        return await self._money(
            "transfers", "transfer", from_id, amount_cents, rounding, on, move_id, memo, {"payee_id": to_id}
        )

    async def withdraw(
        self, account_id: str, amount_cents: int, *, rounding: Rounding = "up20", on: date, move_id: str, memo: str = ""
    ) -> BankWrite:
        return await self._money("withdrawals", "withdrawal", account_id, amount_cents, rounding, on, move_id, memo)

    async def deposit(
        self, account_id: str, amount_cents: int, *, rounding: Rounding = "up", on: date, move_id: str, memo: str = ""
    ) -> BankWrite:
        return await self._money("deposits", "deposit", account_id, amount_cents, rounding, on, move_id, memo)
