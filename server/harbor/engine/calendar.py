"""NYSE trading days, T+1 settlement (NYSE and Fed both open) and the latest safe approval.

UTC in and out; Eastern time comes from the US DST rule, so no timezone database is needed (Windows).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta

UTC = UTC

SELL_TIME = time(10, 0)  # Harbor places sales 30 minutes after the open
MARKET_CLOSE = time(16, 0)
EARLY_CLOSE = time(13, 0)
ORDER_CUTOFF = timedelta(minutes=15)  # last sale 15 minutes before the close
SETTLED_CASH_AT = time(9, 0)  # settled cash is usable from 09:00 ET on the settlement date

# Full-day NYSE closures. Years outside this table are treated as weekdays only.
NYSE_HOLIDAYS = {
    date(2024, 1, 1),
    date(2024, 1, 15),
    date(2024, 2, 19),
    date(2024, 3, 29),
    date(2024, 5, 27),
    date(2024, 6, 19),
    date(2024, 7, 4),
    date(2024, 9, 2),
    date(2024, 11, 28),
    date(2024, 12, 25),
    date(2025, 1, 1),
    date(2025, 1, 9),
    date(2025, 1, 20),
    date(2025, 2, 17),
    date(2025, 4, 18),
    date(2025, 5, 26),
    date(2025, 6, 19),
    date(2025, 7, 4),
    date(2025, 9, 1),
    date(2025, 11, 27),
    date(2025, 12, 25),
    date(2026, 1, 1),
    date(2026, 1, 19),
    date(2026, 2, 16),
    date(2026, 4, 3),
    date(2026, 5, 25),
    date(2026, 6, 19),
    date(2026, 7, 3),
    date(2026, 9, 7),
    date(2026, 11, 26),
    date(2026, 12, 25),
    date(2027, 1, 1),
    date(2027, 1, 18),
    date(2027, 2, 15),
    date(2027, 3, 26),
    date(2027, 5, 31),
    date(2027, 6, 18),
    date(2027, 7, 5),
    date(2027, 9, 6),
    date(2027, 11, 25),
    date(2027, 12, 24),
}

# 1 pm ET closes (2027 not yet published, so none listed).
NYSE_EARLY_CLOSES = {
    date(2024, 7, 3),
    date(2024, 11, 29),
    date(2024, 12, 24),
    date(2025, 7, 3),
    date(2025, 11, 28),
    date(2025, 12, 24),
    date(2026, 11, 27),
    date(2026, 12, 24),
}


# --- US Eastern time
def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """n-th given weekday (Mon=0) of a month; n=-1 means the last one."""
    if n > 0:
        first = date(year, month, 1)
        return first + timedelta(days=(weekday - first.weekday()) % 7 + 7 * (n - 1))
    nxt = date(year + (month == 12), month % 12 + 1, 1)
    last = nxt - timedelta(days=1)
    return last - timedelta(days=(last.weekday() - weekday) % 7)


def _et_offset(utc_dt: datetime) -> timedelta:
    y = utc_dt.year
    dst_start = datetime.combine(_nth_weekday(y, 3, 6, 2), time(7), UTC)  # 2 am EST
    dst_end = datetime.combine(_nth_weekday(y, 11, 6, 1), time(6), UTC)  # 2 am EDT
    return timedelta(hours=-4) if dst_start <= utc_dt < dst_end else timedelta(hours=-5)


def to_et(utc_dt: datetime) -> datetime:
    """UTC -> naive US Eastern wall-clock time."""
    return (utc_dt + _et_offset(utc_dt)).replace(tzinfo=None)


def from_et(d: date, t: time) -> datetime:
    """US Eastern wall-clock date and time -> UTC."""
    naive = datetime.combine(d, t)
    for hours in (-4, -5):
        candidate = (naive - timedelta(hours=hours)).replace(tzinfo=UTC)
        if _et_offset(candidate) == timedelta(hours=hours):
            return candidate
    return (naive + timedelta(hours=5)).replace(tzinfo=UTC)  # inside the 2 am DST gap


# --- Holidays and business days
def fed_holidays(year: int) -> set[date]:
    """Federal Reserve holidays. A fixed date on Sunday moves to Monday; on Saturday it isn't observed."""
    fixed = [date(year, 1, 1), date(year, 6, 19), date(year, 7, 4), date(year, 11, 11), date(year, 12, 25)]
    days = {d + timedelta(days=1) if d.weekday() == 6 else d for d in fixed if d.weekday() != 5}
    days |= {
        _nth_weekday(year, 1, 0, 3),  # Martin Luther King Jr. Day
        _nth_weekday(year, 2, 0, 3),  # Presidents' Day
        _nth_weekday(year, 5, 0, -1),  # Memorial Day
        _nth_weekday(year, 9, 0, 1),  # Labor Day
        _nth_weekday(year, 10, 0, 2),  # Columbus Day
        _nth_weekday(year, 11, 3, 4),  # Thanksgiving
    }
    return days


def is_trading_day(d: date) -> bool:
    return d.weekday() < 5 and d not in NYSE_HOLIDAYS


def is_settlement_day(d: date) -> bool:
    return is_trading_day(d) and d not in fed_holidays(d.year)


def close_time(d: date) -> time:
    return EARLY_CLOSE if d in NYSE_EARLY_CLOSES else MARKET_CLOSE


def order_cutoff(d: date) -> datetime:
    """Latest moment (UTC) Harbor will place a sale on trading day d."""
    return from_et(d, close_time(d)) - ORDER_CUTOFF


def settlement_date(trade_date: date) -> date:
    """T+1: the next settlement day after the trade date."""
    d = trade_date + timedelta(days=1)
    while not is_settlement_day(d):
        d += timedelta(days=1)
    return d


# --- What the plan engine asks
def next_sell_time(after: datetime) -> datetime:
    """Earliest moment at or after `after` when Harbor can place a sale."""
    d = to_et(after).date()
    for _ in range(14):
        if is_trading_day(d):
            open_at = from_et(d, SELL_TIME)
            if after <= open_at:
                return open_at
            if after <= order_cutoff(d):
                return after
        d += timedelta(days=1)
    raise ValueError("no trading day within 14 days")


def cash_available_at(sale_at: datetime) -> datetime:
    """When the cash from a sale placed at `sale_at` becomes usable (T+1, 09:00 ET)."""
    return from_et(settlement_date(to_et(sale_at).date()), SETTLED_CASH_AT)


def latest_sale_time(cash_needed_by: datetime) -> datetime | None:
    """The last moment a sale can be placed and still settle by `cash_needed_by`."""
    d = to_et(cash_needed_by).date()
    for _ in range(14):
        if is_trading_day(d) and cash_available_at(from_et(d, SELL_TIME)) <= cash_needed_by:
            return order_cutoff(d)
        d -= timedelta(days=1)
    return None


def latest_safe_approval_at(cash_needed_by: datetime, now: datetime, cancel_window: timedelta) -> datetime | None:
    """Latest approval that still settles the sale in time (order cutoff minus the cancel window), or None."""
    latest_sale = latest_sale_time(cash_needed_by)
    if latest_sale is None:
        return None
    deadline = latest_sale - cancel_window
    return deadline if deadline >= now else None


def arrives_late(now: datetime, cash_needed_by: datetime, cancel_window: timedelta = timedelta(0)) -> bool:
    """True if even the earliest possible sale would settle after the cash is needed."""
    return cash_available_at(next_sell_time(now + cancel_window)) > cash_needed_by
