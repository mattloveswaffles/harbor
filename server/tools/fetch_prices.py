"""Download real closes for the demo's ETFs into data/prices/milton-2024.json.

uv run python tools/fetch_prices.py
"""

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import httpx

SYMBOLS = ["TBUX", "TCAF", "TSPA", "TOUS", "TOTR", "TCHP", "TEQI", "TDVG"]
START, END = datetime(2024, 9, 23, tzinfo=UTC), datetime(2024, 11, 1, tzinfo=UTC)
OUT = Path(__file__).resolve().parents[1] / "data" / "prices" / "milton-2024.json"


def main() -> int:
    out = {"source": "Yahoo Finance daily closes", "fetched_for": "Hurricane Milton replay", "symbols": {}}
    with httpx.Client(headers={"User-Agent": "Mozilla/5.0 (Harbor hackathon project)"}, timeout=30) as client:
        for symbol in SYMBOLS:
            r = client.get(
                f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}",
                params={"period1": int(START.timestamp()), "period2": int(END.timestamp()), "interval": "1d"},
            )
            r.raise_for_status()
            res = r.json()["chart"]["result"][0]
            closes = [
                {"date": datetime.fromtimestamp(ts, UTC).date().isoformat(), "close_cents": round(c * 100)}
                for ts, c in zip(res["timestamp"], res["indicators"]["quote"][0]["close"], strict=False)
                if c is not None
            ]
            out["symbols"][symbol] = {"name": res["meta"].get("longName", symbol), "closes": closes}
            print(f"{symbol}: {len(closes)} closes")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
