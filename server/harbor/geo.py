"""ZIP -> centre point, from the bundled Census ZCTA table for the US (tools/build_zcta.py)."""

import csv
from functools import lru_cache
from pathlib import Path

ZCTA_FILE = Path(__file__).resolve().parent / "data" / "zcta_us.csv"


@lru_cache
def _zctas() -> dict[str, dict]:
    with open(ZCTA_FILE, encoding="utf-8", newline="") as f:
        return {
            row["zip"]: {
                "zip": row["zip"],
                "city": row["city"],
                "state": row["state"],
                "lat": float(row["lat"]),
                "lon": float(row["lon"]),
            }
            for row in csv.DictReader(f)
        }


def lookup_zip(zip_code: str) -> dict | None:
    hit = _zctas().get(zip_code)
    return dict(hit) if hit else None
