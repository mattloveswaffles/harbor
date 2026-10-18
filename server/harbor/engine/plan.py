"""Plan builder (pure): budget, money sources, alternatives and the restore.

Money comes from checking, then savings, then ETFs (capped; the TBUX storm sleeve first, then the lots
with the least gain). Sales that can't settle before `cash_needed_by` stay, marked `arrives_late`.
Cents and micro-shares are integers.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from harbor.engine import calendar as cal
from harbor.evac.household import BudgetLine

MICRO = 1_000_000
STORM_SLEEVE = ("TBUX",)
BUFFER_MIN_CENTS = 15_000  # Harbor estimate: emergency buffer floor
BUFFER_FRACTION = 0.10  # ...or 10% of everything else, whichever is larger
CASH_FRACTION = 0.25  # withdraw a quarter of the budget as cash, in $20 notes
CASH_NOTE_CENTS = 2_000
CANCEL_LEAD = timedelta(minutes=5)  # cancel up to 5 minutes before a move runs
BILL_SHIELD_DAYS = 7  # deferred bills move to a week after the cash-needed date
MIN_REBUY_CENTS = 100
MPG_DEFAULT = 25
GAS_PRICE_CENTS = 320  # Harbor estimate; live mode can pass AAA's state average
EVAC_FUEL_FACTOR = 1.3  # idling and slow traffic during evacuations

HELP_RESOURCES = [
    {"label": "211: local help with money, food and shelter", "phone": "211", "url": "https://www.211.org"},
    {
        "label": "American Red Cross shelters",
        "phone": "1-800-733-2767",
        "url": "https://www.redcross.org/get-help/disaster-relief-and-recovery-services/find-an-open-shelter.html",
    },
    {"label": "FEMA disaster assistance", "phone": "1-800-621-3362", "url": "https://www.disasterassistance.gov"},
]


# --- Inputs
@dataclass(frozen=True)
class Balances:
    checking_cents: int
    savings_cents: int
    brokerage_cash_cents: int = 0


@dataclass(frozen=True)
class LotIn:
    id: str
    symbol: str
    shares_micro: int
    cost_basis_cents: int
    acquired: date


@dataclass(frozen=True)
class BillIn:
    id: str
    payee: str
    amount_cents: int
    due_date: date


@dataclass(frozen=True)
class PlanSettings:
    max_etf_sell_cents: int = 300_000
    cancel_window: timedelta = timedelta(minutes=120)
    etf_cap_fraction: float = 0.25
    checking_reserved_cents: int = 0  # money in checking already promised elsewhere


@dataclass(frozen=True)
class PlanInputs:
    now: datetime
    cash_needed_by: datetime
    lines: tuple[BudgetLine, ...]
    balances: Balances
    lots: tuple[LotIn, ...]
    prices_cents: dict[str, int]
    settings: PlanSettings = PlanSettings()
    bills: tuple[BillIn, ...] = ()


# --- Outputs
@dataclass
class LotSale:
    lot_id: str
    shares_micro: int
    proceeds_cents: int
    cost_basis_cents: int
    long_term: bool

    @property
    def gain_cents(self) -> int:
        return self.proceeds_cents - self.cost_basis_cents


@dataclass
class MoveDraft:
    key: str
    kind: str
    amount_cents: int
    from_ref: str
    to_ref: str
    scheduled_for: datetime
    expected_available_at: datetime
    cancel_deadline: datetime
    why: str
    symbol: str | None = None
    shares_micro: int | None = None
    price_locked_cents: int | None = None
    lot_sales: list[LotSale] = field(default_factory=list)
    arrives_late: bool = False
    requires_explicit_approval: bool = False
    depends_on: list[str] = field(default_factory=list)
    extra: dict = field(default_factory=dict)

    @property
    def gain_cents(self) -> int:
        return sum(s.gain_cents for s in self.lot_sales)


@dataclass
class Alternative:
    id: str
    label: str
    feasible: bool
    why_not: str | None
    total_cents: int
    etf_sale_cents: int
    delta_tax_cents: int  # change in realised gains vs the main plan (negative = less tax)


@dataclass
class PlanDraft:
    total_cents: int
    lines: list[BudgetLine]
    sources: dict[str, int]
    shortfall_cents: int
    moves: list[MoveDraft]
    alternatives: list[Alternative]
    latest_safe_approval_at: datetime | None
    tax_note: str | None
    warnings: list[str]
    help_resources: list[dict]
    facts: dict


# --- Budget
def fuel_line(round_trip_miles: float, mpg: float = MPG_DEFAULT, gas_price_cents: int = GAS_PRICE_CENTS) -> BudgetLine:
    cents = round_trip_miles / mpg * gas_price_cents * EVAC_FUEL_FACTOR
    return BudgetLine(f"Fuel: {round(round_trip_miles)} mi round trip", math.ceil(cents / 100) * 100, "route")


def lodging_line(place: str, nightly_cents: int, rooms: int, nights: int, source: str) -> BudgetLine:
    room_txt = f"{rooms} room{'s' if rooms != 1 else ''}"
    return BudgetLine(f"Lodging: {place}, {room_txt} × {nights} nights", nightly_cents * rooms * nights, source)


def with_buffer(lines: list[BudgetLine] | tuple[BudgetLine, ...]) -> list[BudgetLine]:
    subtotal = sum(line.amount_cents for line in lines)
    buffer = max(BUFFER_MIN_CENTS, math.ceil(subtotal * BUFFER_FRACTION / 100) * 100)
    return [*lines, BudgetLine("Emergency buffer", buffer, "rules")]


# --- ETF selection
def portfolio_value(lots: tuple[LotIn, ...], prices: dict[str, int]) -> int:
    return sum(lot.shares_micro * prices[lot.symbol] // MICRO for lot in lots)


def _lot_order(lot: LotIn, price: int) -> tuple:
    value = lot.shares_micro * price / MICRO
    gain_per_dollar = (value - lot.cost_basis_cents) / value if value else 0
    return (lot.symbol not in STORM_SLEEVE, gain_per_dollar, lot.acquired)


def select_lots(
    amount_cents: int, lots: tuple[LotIn, ...], prices: dict[str, int], sale_day: date
) -> dict[str, list[LotSale]]:
    """Choose which shares to sell to raise at least `amount_cents`. Returns sales grouped by symbol."""
    remaining = amount_cents
    out: dict[str, list[LotSale]] = {}
    for lot in sorted(lots, key=lambda l: _lot_order(l, prices[l.symbol])):
        if remaining <= 0:
            break
        price = prices[lot.symbol]
        shares = min(lot.shares_micro, math.ceil(remaining * MICRO / price))
        proceeds = shares * price // MICRO
        basis = round(lot.cost_basis_cents * shares / lot.shares_micro)
        long_term = (sale_day - lot.acquired).days > 365
        out.setdefault(lot.symbol, []).append(LotSale(lot.id, shares, proceeds, basis, long_term))
        remaining -= proceeds
    return out


# --- The waterfall
def _waterfall(total: int, x: PlanInputs) -> tuple[int, int, int, int]:
    """(from_checking, from_savings, from_etf, shortfall) before timing is considered."""
    checking = max(0, x.balances.checking_cents - x.settings.checking_reserved_cents)
    from_checking = min(checking, total)
    from_savings = min(x.balances.savings_cents, total - from_checking)
    need = total - from_checking - from_savings
    cap = min(x.settings.max_etf_sell_cents, int(portfolio_value(x.lots, x.prices_cents) * x.settings.etf_cap_fraction))
    from_etf = min(need, cap)
    return from_checking, from_savings, from_etf, need - from_etf


def _cancel_deadline(at: datetime) -> datetime:
    return at - CANCEL_LEAD


def _day(at: datetime) -> str:
    local = cal.to_et(at)
    return f"{local:%a} {local.day} {local:%b}"  # strftime's %-d doesn't work on Windows


def _money(cents: int) -> str:
    return f"${cents / 100:,.2f}".replace(".00", "")


def build_plan(x: PlanInputs) -> PlanDraft:
    lines = with_buffer(x.lines)
    total = sum(line.amount_cents for line in lines)
    from_checking, from_savings, from_etf, shortfall = _waterfall(total, x)
    window = x.settings.cancel_window
    first_run = x.now + window
    moves: list[MoveDraft] = []
    warnings: list[str] = []

    if from_savings:
        moves.append(
            MoveDraft(
                key="mv_transfer",
                kind="transfer",
                amount_cents=from_savings,
                from_ref="savings",
                to_ref="checking",
                scheduled_for=first_run,
                expected_available_at=first_run,
                cancel_deadline=_cancel_deadline(first_run),
                why="Savings moves instantly and costs nothing, so it's used before selling anything.",
            )
        )

    sale_total = 0
    gain_total = 0
    if from_etf:
        sale_at = cal.next_sell_time(first_run)
        available = cal.cash_available_at(sale_at)
        late = available > x.cash_needed_by
        sale_day = cal.to_et(sale_at).date()
        for symbol, sales in select_lots(from_etf, x.lots, x.prices_cents, sale_day).items():
            proceeds = sum(s.proceeds_cents for s in sales)
            move = MoveDraft(
                key=f"mv_sell_{symbol.lower()}",
                kind="sell_etf",
                amount_cents=proceeds,
                from_ref="brokerage",
                to_ref="checking",
                scheduled_for=sale_at,
                expected_available_at=available,
                cancel_deadline=_cancel_deadline(sale_at),
                symbol=symbol,
                shares_micro=sum(s.shares_micro for s in sales),
                price_locked_cents=x.prices_cents[symbol],
                lot_sales=sales,
                arrives_late=late,
                requires_explicit_approval=True,
                why=(
                    f"Sold {_day(sale_at)} so it settles (T+1) and reaches checking "
                    f"{'too late' if late else 'before you need it'}."
                ),
            )
            moves.append(move)
            if late:
                warnings.append(f"Selling {symbol} now would settle after you need the cash, so it isn't counted.")
            else:
                sale_total += proceeds
                gain_total += move.gain_cents
            if any(s.gain_cents < 0 for s in sales):
                warnings.append(
                    f"Rebuying {symbol} within 30 days of selling it at a loss would trigger the wash-sale rule."
                )
        if sale_total < from_etf:
            shortfall += from_etf - sale_total

    # Cash comes out as soon as the savings transfer lands (ATMs run dry before storms), so it can
    # only use money already in checking or coming from savings, not ETF proceeds still settling.
    cash = min(from_checking + from_savings, math.ceil(total * CASH_FRACTION / CASH_NOTE_CENTS) * CASH_NOTE_CENTS)
    cash -= cash % CASH_NOTE_CENTS
    if cash:
        at = first_run
        moves.append(
            MoveDraft(
                key="mv_cash",
                kind="withdraw_cash",
                amount_cents=cash,
                from_ref="checking",
                to_ref="cash",
                scheduled_for=at,
                expected_available_at=at,
                cancel_deadline=_cancel_deadline(at),
                depends_on=[m.key for m in moves if m.kind == "transfer"],
                why="Cash in hand in case card machines and ATMs go down after landfall.",
            )
        )

    window_end = x.cash_needed_by.date() + timedelta(days=BILL_SHIELD_DAYS)
    for bill in x.bills:
        if x.now.date() <= bill.due_date <= window_end:
            moves.append(
                MoveDraft(
                    key=f"mv_bill_{bill.id}",
                    kind="defer_bill",
                    amount_cents=bill.amount_cents,
                    from_ref="checking",
                    to_ref=bill.payee,
                    scheduled_for=first_run,
                    expected_available_at=first_run,
                    cancel_deadline=_cancel_deadline(first_run),
                    requires_explicit_approval=True,
                    extra={
                        "bill_id": bill.id,
                        "from_date": bill.due_date.isoformat(),
                        "to_date": window_end.isoformat(),
                    },
                    why=f"Your {bill.payee} bill is due during the storm, so it moves to after recovery.",
                )
            )

    approval = None
    if any(m.kind == "sell_etf" and not m.arrives_late for m in moves):
        approval = cal.latest_safe_approval_at(x.cash_needed_by, x.now, window)

    sells = [m for m in moves if m.kind == "sell_etf" and not m.arrives_late]
    tax_note = None
    if sells:
        parts = [f"{m.shares_micro / MICRO:.2f} shares of {m.symbol}" for m in sells]
        terms = {s.long_term for m in sells for s in m.lot_sales}
        kind = "long-term" if terms == {True} else "short-term" if terms == {False} else "mixed short- and long-term"
        word = "gains" if gain_total >= 0 else "losses"
        tax_note = f"Selling {', '.join(parts)} realises about {_money(abs(gain_total))} of {kind} {word}."

    alternatives = _alternatives(x, lines, total, gain_total)
    sources = {
        "already_in_checking_cents": from_checking,
        "from_savings_cents": from_savings,
        "from_etf_sales_cents": sale_total,
    }
    draft = PlanDraft(
        total_cents=total,
        lines=lines,
        sources=sources,
        shortfall_cents=shortfall,
        moves=moves,
        alternatives=alternatives,
        latest_safe_approval_at=approval,
        tax_note=tax_note,
        warnings=warnings,
        help_resources=HELP_RESOURCES if shortfall else [],
        facts={},
    )
    draft.facts = plan_facts(draft, x)
    return draft


def _alternatives(x: PlanInputs, lines: list[BudgetLine], total: int, gain_total: int) -> list[Alternative]:
    out = []
    checking = max(0, x.balances.checking_cents - x.settings.checking_reserved_cents)
    cash_only = checking + x.balances.savings_cents
    out.append(
        Alternative(
            id="alt_no_etf",
            label="Use only checking and savings (no ETF sale)",
            feasible=cash_only >= total,
            why_not=None
            if cash_only >= total
            else f"Checking and savings only cover {_money(cash_only)} of {_money(total)}.",
            total_cents=total,
            etf_sale_cents=0,
            delta_tax_cents=-gain_total,
        )
    )
    lodging = [line for line in lines if line.label.startswith("Lodging")]
    if lodging:
        without = [line for line in lines if not line.label.startswith("Lodging")]
        alt_total = sum(line.amount_cents for line in without)
        _, _, etf, short = _waterfall(alt_total, x)
        out.append(
            Alternative(
                id="alt_public_shelter",
                label="Stay at a free public shelter instead of a hotel",
                feasible=short == 0,
                why_not=None if short == 0 else "Still short even without lodging.",
                total_cents=alt_total,
                etf_sale_cents=etf,
                delta_tax_cents=0 if etf else -gain_total,
            )
        )
    return out


def plan_facts(draft: PlanDraft, x: PlanInputs) -> dict:
    """The plan's facts, kept on plan.ai (the restore reads the balances from here)."""

    def et(dt: datetime | None) -> str | None:
        return None if dt is None else f"{cal.to_et(dt):%a %b %d, %I:%M %p} ET".replace(" 0", " ")

    return {
        "total_cents": draft.total_cents,
        "budget_lines": [{"label": l.label, "amount_cents": l.amount_cents, "source": l.source} for l in draft.lines],
        "sources": draft.sources,
        "shortfall_cents": draft.shortfall_cents,
        "balances": {"checking_cents": x.balances.checking_cents, "savings_cents": x.balances.savings_cents},
        "cash_needed_by": x.cash_needed_by.isoformat(),
        "cash_needed_by_display": et(x.cash_needed_by),
        "latest_safe_approval_display": et(draft.latest_safe_approval_at),
        "settlement": "T+1",
        "moves": [
            {
                "id": m.key,
                "kind": m.kind,
                "amount_cents": m.amount_cents,
                "symbol": m.symbol,
                "shares": round(m.shares_micro / MICRO, 2) if m.shares_micro else None,
                "gain_cents": m.gain_cents if m.lot_sales else None,
                "runs_display": et(m.scheduled_for),
                "available_display": et(m.expected_available_at),
                "arrives_late": m.arrives_late,
            }
            for m in draft.moves
        ],
        "alternatives": [
            {
                "id": a.id,
                "label": a.label,
                "feasible": a.feasible,
                "why_not": a.why_not,
                "total_cents": a.total_cents,
                "etf_sale_cents": a.etf_sale_cents,
                "delta_tax_cents": a.delta_tax_cents,
            }
            for a in draft.alternatives
        ],
        "tax_note": draft.tax_note,
        "warnings": draft.warnings,
    }


# --- Restore
@dataclass(frozen=True)
class SoldPosition:
    symbol: str
    shares_micro: int
    proceeds_cents: int
    at_loss: bool
    sold_at: datetime


@dataclass(frozen=True)
class RestoreInputs:
    now: datetime
    checking_now_cents: int
    checking_before_cents: int  # checking balance when the plan was made
    moved_from_savings_cents: int
    sold: tuple[SoldPosition, ...]
    prices_cents: dict[str, int]
    rebuy_opt_in: bool = False


@dataclass
class RestoreDraft:
    unspent_cents: int
    moves: list[MoveDraft]
    warnings: list[str]
    left_in_checking_cents: int


def build_restore(r: RestoreInputs) -> RestoreDraft:
    """Return unspent money: savings first (up to what came from it), then ETF rebuys if opted in."""
    unspent = max(0, r.checking_now_cents - r.checking_before_cents)
    remaining = unspent
    moves: list[MoveDraft] = []
    warnings: list[str] = []
    run_at = r.now + timedelta(minutes=10)

    to_savings = min(remaining, r.moved_from_savings_cents)
    remaining -= to_savings

    if r.rebuy_opt_in:
        sale_at = cal.next_sell_time(run_at)
        for pos in r.sold:
            if remaining <= 0:
                break
            if pos.at_loss and (sale_at - pos.sold_at) < timedelta(days=30):
                warnings.append(
                    f"Skipped rebuying {pos.symbol}: it was sold at a loss less than 30 days ago "
                    "(wash-sale rule). You can rebuy it yourself after the 30 days."
                )
                continue
            price = r.prices_cents[pos.symbol]
            spend = min(remaining, pos.proceeds_cents)
            shares = spend * MICRO // price
            cost = shares * price // MICRO
            if cost < MIN_REBUY_CENTS:
                continue  # not worth a trade (and Nessie can't move less than $1)
            moves.append(
                MoveDraft(
                    key=f"mv_rebuy_{pos.symbol.lower()}",
                    kind="rebuy_etf",
                    amount_cents=cost,
                    from_ref="checking",
                    to_ref="brokerage",
                    scheduled_for=sale_at,
                    expected_available_at=sale_at,
                    cancel_deadline=_cancel_deadline(sale_at),
                    symbol=pos.symbol,
                    shares_micro=shares,
                    price_locked_cents=price,
                    requires_explicit_approval=True,
                    why=f"Buys back the {pos.symbol} sold before the storm, as you asked.",
                )
            )
            remaining -= cost

    to_savings += remaining
    remaining = 0
    if to_savings:
        moves.insert(
            0,
            MoveDraft(
                key="mv_restore",
                kind="restore_transfer",
                amount_cents=to_savings,
                from_ref="checking",
                to_ref="savings",
                scheduled_for=run_at,
                expected_available_at=run_at,
                cancel_deadline=_cancel_deadline(run_at),
                why="Moves the money you didn't spend back to savings.",
            ),
        )
    return RestoreDraft(unspent, moves, warnings, r.checking_now_cents - unspent)
