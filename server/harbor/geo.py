"""Geography helpers: ZIP -> centre point (the bundled Census ZCTA table, tools/build_zcta.py), distances and GeoJSON."""

import csv
import math
from functools import lru_cache
from pathlib import Path

ZCTA_FILE = Path(__file__).resolve().parent / "data" / "zcta_us.csv"
EARTH_RADIUS_MI = 3958.8


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


def miles_between(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in miles."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_MI * math.asin(math.sqrt(a))


def feature_collection(features: list[dict]) -> dict:
    return {"type": "FeatureCollection", "features": features}


def point(lat: float, lon: float, **props) -> dict:
    return {"type": "Feature", "geometry": {"type": "Point", "coordinates": [lon, lat]}, "properties": props}
