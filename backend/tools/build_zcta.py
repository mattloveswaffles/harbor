"""Build harbor/data/zcta_fl.csv: Florida ZIP centre points for GET /zip/{zip}.

Inputs (download once, unzip, pass the paths):
- Census 2024 Gazetteer ZCTA file (centre points; no PO-box ZIPs):
  https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2024_Gazetteer/2024_Gaz_zcta_national.zip
- GeoNames US postal codes (city and state names, CC BY 4.0): https://download.geonames.org/export/zip/US.zip

    python tools/build_zcta.py 2024_Gaz_zcta_national.txt US.txt

Only ZIPs present in the Census file are kept, so PO-box-only ZIPs (33601) stay unsupported.
"""

import csv
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "harbor" / "data" / "zcta_fl.csv"


def main(gazetteer: str, geonames: str) -> None:
    places = {}
    with open(geonames, encoding="utf-8") as f:
        for row in csv.reader(f, delimiter="\t"):
            # country, zip, place, state name, state code, ...
            if row[4] == "FL":
                places[row[1]] = row[2]

    rows = []
    with open(gazetteer, encoding="utf-8") as f:
        reader = csv.reader(f, delimiter="\t")
        header = [h.strip() for h in next(reader)]
        geoid, lat, lon = header.index("GEOID"), header.index("INTPTLAT"), header.index("INTPTLONG")
        for row in reader:
            row = [c.strip() for c in row]
            if row[geoid] in places:
                rows.append((row[geoid], places[row[geoid]], "FL", f"{float(row[lat]):.6f}", f"{float(row[lon]):.6f}"))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["zip", "city", "state", "lat", "lon"])
        w.writerows(sorted(rows))
    print(f"wrote {len(rows)} Florida ZIPs to {OUT}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
