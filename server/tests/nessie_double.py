"""Test stand-in for the Nessie API: same request bodies, instant balances, fault flags. Tests never call Nessie."""

import uuid

from harbor.bank.base import (
    Bank,
    NessieError,
    NessieNotFound,
    NessieRejected,
    NessieUnavailable,
    TxKind,
)

ACCOUNT_TYPES = ("Checking", "Savings", "Credit Card")


class NessieDouble(Bank):
    def __init__(self):
        self.customers: dict[str, dict] = {}
        self.accounts: dict[str, dict] = {}
        self.transactions: dict[TxKind, list[dict]] = {"transfers": [], "withdrawals": [], "deposits": []}
        self.bills: dict[str, dict] = {}
        self.calls: list[str] = []
        # Fault injection
        self.down = False  # every call raises NessieUnavailable
        self.fail_next: list[NessieError] = []  # raised one by one on the next calls
        self.drop_response_next = False  # the next write happens, but the caller sees a timeout

    def _call(self, name: str) -> None:
        self.calls.append(name)
        if self.down:
            raise NessieUnavailable("Nessie is down (NessieDouble.down)", 503)
        if self.fail_next:
            raise self.fail_next.pop(0)

    @staticmethod
    def _id() -> str:
        return str(uuid.uuid4())

    # --- Customers and accounts
    async def create_customer(self, first_name: str, last_name: str, address: dict) -> dict:
        self._call("create_customer")
        cust = {"_id": self._id(), "first_name": first_name, "last_name": last_name, "address": dict(address)}
        self.customers[cust["_id"]] = cust
        return dict(cust)

    async def get_customer(self, customer_id: str) -> dict | None:
        self._call("get_customer")
        cust = self.customers.get(customer_id)
        return dict(cust) if cust else None

    async def list_customers(self) -> list[dict]:
        self._call("list_customers")
        return [dict(c) for c in self.customers.values()]

    async def create_account(self, customer_id: str, type: str, nickname: str, balance_dollars: int) -> dict:
        self._call("create_account")
        if customer_id not in self.customers:
            raise NessieNotFound("Customer not found", 404)
        if type not in ACCOUNT_TYPES or balance_dollars < 0 or int(balance_dollars) != balance_dollars:
            raise NessieRejected("Invalid account fields", 400)
        acct = {
            "_id": self._id(),
            "type": type,
            "nickname": nickname,
            "rewards": 0,
            "balance": int(balance_dollars),
            "account_number": str(uuid.uuid4().int)[:16],
            "customer_id": customer_id,
        }
        self.accounts[acct["_id"]] = acct
        return dict(acct)

    async def list_accounts(self, customer_id: str) -> list[dict]:
        self._call("list_accounts")
        return [dict(a) for a in self.accounts.values() if a["customer_id"] == customer_id]

    async def get_account(self, account_id: str) -> dict | None:
        self._call("get_account")
        acct = self.accounts.get(account_id)
        return dict(acct) if acct else None

    async def delete_account(self, account_id: str) -> None:
        self._call("delete_account")
        if self.accounts.pop(account_id, None) is None:
            raise NessieNotFound("Account with this id does not exist", 404)

    # --- Bills
    async def create_bill(self, account_id, payee, amount_cents, due, nickname):
        self._call("create_bill")
        if account_id not in self.accounts:
            raise NessieNotFound("Account with this id does not exist", 404)
        bill = {
            "_id": self._id(),
            "account_id": account_id,
            "payee": payee,
            "nickname": nickname,
            "payment_amount": amount_cents / 100,
            "payment_date": due.isoformat(),
            "status": "pending",
        }
        self.bills[bill["_id"]] = bill
        return bill["_id"]

    async def update_bill_date(self, bill_id, due):
        self._call("update_bill_date")
        if bill_id not in self.bills:
            raise NessieNotFound("Bill not found", 404)
        self.bills[bill_id]["payment_date"] = due.isoformat()

    # --- Transactions
    async def list_transactions(self, account_id: str, kind: TxKind) -> list[dict]:
        self._call(f"list_{kind}")
        return [dict(t) for t in self.transactions[kind] if account_id in (t.get("payer_id"), t.get("payee_id"))]

    def _debit(self, account_id: str, dollars: int) -> dict:
        acct = self.accounts.get(account_id)
        if acct is None:
            raise NessieNotFound("Account with this id does not exist", 404)
        if acct["balance"] < dollars:
            # Real Nessie overdraft behaviour is UNVERIFIED; the double refuses, which is the safe assumption.
            raise NessieRejected("Insufficient funds", 400)
        return acct

    async def _write(self, account_id: str, kind: TxKind, body: dict, tag: str) -> tuple[str | None, bool]:
        self._call(f"post_{kind}")
        dollars = body["amount"]
        if not isinstance(dollars, int) or dollars <= 0:
            raise NessieRejected("amount must be a positive whole number of dollars", 400)
        tx = {"_id": self._id(), "type": kind[:-1], **body}
        if kind == "transfers":
            payee = self.accounts.get(body["payee_id"])
            if payee is None:
                raise NessieNotFound("Payee account not found", 404)
            self._debit(account_id, dollars)["balance"] -= dollars
            payee["balance"] += dollars
            tx.update(payer_id=account_id)
        elif kind == "withdrawals":
            self._debit(account_id, dollars)["balance"] -= dollars
            tx.update(payer_id=account_id)
        else:  # deposits
            acct = self.accounts.get(account_id)
            if acct is None:
                raise NessieNotFound("Account with this id does not exist", 404)
            acct["balance"] += dollars
            tx.update(payee_id=account_id)
        self.transactions[kind].append(tx)
        if self.drop_response_next:
            self.drop_response_next = False
            raise NessieUnavailable("timed out (NessieDouble.drop_response_next)")
        return tx["_id"], False
