"""ETF prices: committed real closes (demo) or Alpaca (live). price_at never returns a future close."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path

from harbor.engine import calendar as cal

DATA = Path(__file__).resolve().parents[2] / "data" / "prices"


@dataclass(frozen=True)
class Price:
    symbol: str
    name: str
    price_cents: int
    as_of: datetime


@lru_cache
def _load(name: str) -> dict:
    return json.loads((DATA / f"{name}.json").read_text(encoding="utf-8"))


class FixturePrices:
    def __init__(self, fixture: str = "milton-2024"):
        data = _load(fixture)
        self.names = {s: v["name"] for s, v in data["symbols"].items()}
        self.closes: dict[str, list[tuple[date, int]]] = {
            s: [(date.fromisoformat(c["date"]), c["close_cents"]) for c in v["closes"]]
            for s, v in data["symbols"].items()
        }

    def price_at(self, symbol: str, now: datetime) -> Price | None:
        best = None
        for d, cents in self.closes.get(symbol, []):
            closed_at = cal.from_et(d, cal.close_time(d))
            if closed_at <= now:
                best = (closed_at, cents)
        if best is None:
            return None
        return Price(symbol, self.names[symbol], best[1], best[0])

    def prices_at(self, symbols: list[str] | set[str], now: datetime) -> dict[str, int]:
        """{symbol: price_cents} for the plan engine; symbols without a price are left out."""
        out = {}
        for s in symbols:
            p = self.price_at(s, now)
            if p is not None:
                out[s] = p.price_cents
        return out
