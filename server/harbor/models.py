"""SQLModel tables. Money in cents, shares in millionths, times in UTC."""

import secrets
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import JSON, Column, DateTime, TypeDecorator
from sqlmodel import Field, SQLModel

from harbor.clock import utc


def new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(5)}"


class UTCDateTime(TypeDecorator):
    """SQLite drops time zones; store naive UTC and hand back aware UTC."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return utc(value).replace(tzinfo=None) if value is not None else None

    def process_result_value(self, value, dialect):
        return value.replace(tzinfo=UTC) if value is not None else None


def json_col() -> Any:
    # Reassign JSON fields (don't mutate in place) so SQLAlchemy sees the change.
    return Field(default=None, sa_column=Column(JSON))


def time_col(**kw) -> Any:
    return Field(default=None, sa_type=UTCDateTime, **kw)


DEFAULT_SETTINGS = {
    "auto_approve": False,
    "max_etf_sell_cents": 300000,
    "cancel_window_minutes": 120,
    "rebuy_opt_in": False,
}


class User(SQLModel, table=True):
    id: str = Field(default_factory=lambda: new_id("usr"), primary_key=True)
    name: str
    zip: str = Field(index=True)
    lat: float
    lon: float
    location_source: str = "zcta"  # zcta | gps
    settings: dict | None = json_col()
    nessie_customer_id: str | None = None
    risk_level: str = "clear"
    risk_reason: str | None = None
    risk_changed_at: datetime | None = time_col()
    created_at: datetime | None = time_col()


class Household(SQLModel, table=True):
    user_id: str = Field(foreign_key="user.id", primary_key=True)
    adults: int = 1
    children_ages: list | None = json_col()
    seniors: int = 0
    pets: list | None = json_col()  # [{"type": "dog", "count": 1}]
    mobility: str = "none"  # none | walker | wheelchair
    medical: dict | None = json_col()
    has_car: bool = True
    home_type: str = "site_built"  # site_built | mobile
    evac_zone: str = "unsure"  # A-E | none | unsure


class Account(SQLModel, table=True):
    id: str = Field(default_factory=lambda: new_id("acc"), primary_key=True)
    user_id: str = Field(foreign_key="user.id", index=True)
    type: str  # checking | savings | brokerage_cash
    nessie_type: str  # Checking | Savings
    nessie_id: str | None = None
    nickname: str
    balance_cents: int = 0  # last balance read from Nessie
    balance_synced_at: datetime | None = time_col()
    starting_balance_cents: int = 0  # what /demo/reset puts back


class Lot(SQLModel, table=True):
    id: str = Field(default_factory=lambda: new_id("lot"), primary_key=True)
    user_id: str = Field(foreign_key="user.id", index=True)
    symbol: str
    shares_micro: int
    cost_basis_cents: int
    acquired: date
    sold_at: datetime | None = time_col()
    sold_move_id: str | None = None


class Plan(SQLModel, table=True):
    id: str = Field(default_factory=lambda: new_id("pln"), primary_key=True)
    user_id: str = Field(foreign_key="user.id", index=True)
    version: int = 1
    status: str = "draft"
    decided_by: str = "rules"
    storm_id: str | None = None
    created_at: datetime | None = time_col()
    approved_at: datetime | None = time_col()
    cash_needed_by: datetime | None = time_col()
    latest_safe_approval_at: datetime | None = time_col()
    budget: dict | None = json_col()
    sources: dict | None = json_col()
    shortfall_cents: int = 0
    help_resources: list | None = json_col()
    alternatives: list | None = json_col()
    summary: str | None = None
    tax_note: str | None = None
    warnings: list | None = json_col()
    ai: dict | None = json_col()


class Move(SQLModel, table=True):
    id: str = Field(default_factory=lambda: new_id("mv"), primary_key=True)
    plan_id: str = Field(foreign_key="plan.id", index=True)
    seq: int = 0
    kind: str
    status: str = "proposed"
    from_ref: str | None = None
    to_ref: str | None = None
    symbol: str | None = None
    shares_micro: int | None = None
    lots: list | None = json_col()
    price_locked_cents: int | None = None
    amount_cents: int = 0
    nessie_amount_dollars: int | None = None
    rounding_cents: int = 0
    scheduled_for: datetime | None = time_col()
    expected_available_at: datetime | None = time_col()
    cancel_deadline: datetime | None = time_col()
    arrives_late: bool = False
    requires_explicit_approval: bool = False
    depends_on: list | None = json_col()
    why: str | None = None
    nessie_object_id: str | None = None
    nessie_object_type: str | None = None
    attempts: int = 0
    last_attempt_at: datetime | None = time_col()
    error: dict | None = json_col()
    extra: dict | None = json_col()  # bill_id, from_date, to_date, atm_id


class Credential(SQLModel, table=True):
    """Email + password login. Nessie only ever sees a pseudonym."""

    user_id: str = Field(foreign_key="user.id", primary_key=True)
    email: str = Field(unique=True, index=True)  # stored lowercased
    password_hash: str  # scrypt, see harbor/auth.py
    created_at: datetime | None = time_col()


class AuthToken(SQLModel, table=True):
    """A login token. Only its SHA-256 is stored, so a leaked database can't be used to log in."""

    id: str = Field(primary_key=True)  # sha256 hex of the token
    user_id: str = Field(foreign_key="user.id", index=True)
    created_at: datetime | None = time_col()
    expires_at: datetime | None = time_col()
    revoked_at: datetime | None = time_col()


class Bill(SQLModel, table=True):
    """A bill in Nessie that the bill shield can move to after the storm."""

    id: str = Field(default_factory=lambda: new_id("bill"), primary_key=True)
    user_id: str = Field(foreign_key="user.id", index=True)
    account_id: str  # Harbor account the bill is paid from
    nessie_id: str | None = None
    payee: str
    amount_cents: int
    due_date: date
    original_due_date: date
    status: str = "pending"


class Profile(SQLModel, table=True):
    """Everything the Settings popup holds (see harbor/profile.py for the shape)."""

    user_id: str = Field(foreign_key="user.id", primary_key=True)
    data: dict | None = json_col()
    updated_at: datetime | None = time_col()


class Connection(SQLModel, table=True):
    """A bank, brokerage or wallet the user connected; its money lives in Nessie accounts."""

    id: str = Field(default_factory=lambda: new_id("con"), primary_key=True)
    user_id: str = Field(foreign_key="user.id", index=True)
    institution: str  # see harbor/connections.py INSTITUTIONS
    account_ids: list | None = json_col()  # Harbor Account ids
    connected_at: datetime | None = time_col()


class Advice(SQLModel, table=True):
    """The latest evacuation advice, written by the AI in the background (harbor/ai/advisor.py)."""

    user_id: str = Field(foreign_key="user.id", primary_key=True)
    status: str = "running"  # running | ready | error
    inputs_hash: str | None = None  # the facts it was written for
    result: dict | None = json_col()
    error: str | None = None
    updated_at: datetime | None = time_col()


class Event(SQLModel, table=True):
    seq: int | None = Field(default=None, primary_key=True)  # ordering and Last-Event-ID
    id: str = Field(default_factory=lambda: new_id("evt"), unique=True, index=True)
    user_id: str = Field(foreign_key="user.id", index=True)
    at: datetime | None = time_col()
    type: str
    message: str
    data: dict | None = json_col()
