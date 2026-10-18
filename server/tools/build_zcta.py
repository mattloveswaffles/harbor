"""Build harbor/data/zcta_us.csv (US ZIP centres) from the Census Gazetteer and GeoNames (CC BY 4.0).

uv run python tools/build_zcta.py 2024_Gaz_zcta_national.txt US.txt
"""

import csv
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "harbor" / "data" / "zcta_us.csv"


def main(gazetteer: str, geonames: str) -> None:
    places = {}  # zip -> (city, state code)
    with open(geonames, encoding="utf-8") as f:
        for row in csv.reader(f, delimiter="\t"):  # country, zip, place, state name, state code, ...
            places[row[1]] = (row[2], row[4])

    rows = []
    with open(gazetteer, encoding="utf-8") as f:
        reader = csv.reader(f, delimiter="\t")
        header = [h.strip() for h in next(reader)]
        geoid, lat, lon = header.index("GEOID"), header.index("INTPTLAT"), header.index("INTPTLONG")
        for row in reader:
            row = [c.strip() for c in row]
            if row[geoid] in places:
                city, state = places[row[geoid]]
                rows.append((row[geoid], city, state, f"{float(row[lat]):.6f}", f"{float(row[lon]):.6f}"))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["zip", "city", "state", "lat", "lon"])
        w.writerows(sorted(rows))
    print(f"wrote {len(rows)} ZIPs to {OUT}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
