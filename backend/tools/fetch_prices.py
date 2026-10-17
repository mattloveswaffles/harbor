"""Download real daily closes for T. Rowe Price ETFs around Hurricane Milton.

Run from backend/ (needs internet, no keys):

    python tools/fetch_prices.py

Writes data/prices/milton-2024.json. The demo prices the simulated portfolio from this file, so it
never depends on a live market feed. Prices are for the demo only, not a recommendation.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

SYMBOLS = ["TBUX", "TCAF", "TSPA", "TOUS", "TOTR", "TCHP", "TEQI", "TDVG"]
START, END = datetime(2024, 9, 23, tzinfo=timezone.utc), datetime(2024, 11, 1, tzinfo=timezone.utc)
OUT = Path(__file__).resolve().parents[1] / "data" / "prices" / "milton-2024.json"


def main() -> int:
    out = {"source": "Yahoo Finance daily closes", "fetched_for": "Hurricane Milton replay", "symbols": {}}
    with httpx.Client(headers={"User-Agent": "Mozilla/5.0 (Harbor hackathon project)"}, timeout=30) as client:
        for symbol in SYMBOLS:
            r = client.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}",
                           params={"period1": int(START.timestamp()), "period2": int(END.timestamp()), "interval": "1d"})
            r.raise_for_status()
            res = r.json()["chart"]["result"][0]
            closes = [
                {"date": datetime.fromtimestamp(ts, timezone.utc).date().isoformat(), "close_cents": round(c * 100)}
                for ts, c in zip(res["timestamp"], res["indicators"]["quote"][0]["close"]) if c is not None
            ]
            out["symbols"][symbol] = {"name": res["meta"].get("longName", symbol), "closes": closes}
            print(f"{symbol}: {len(closes)} closes")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
