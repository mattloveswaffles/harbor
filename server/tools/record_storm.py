"""Download Milton sensor readings (tide gauge, river gauge, buoy) into data/sensors/milton-2024/.

uv run python tools/record_storm.py
"""

import gzip
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import httpx

START, END = "2024-10-05", "2024-10-20"  # Sat before Milton until the Alafia River is back below flood stage
OUT = Path(__file__).resolve().parents[1] / "data" / "sensors" / "milton-2024"
UA = {"User-Agent": os.environ.get("NOAA_USER_AGENT") or "Harbor hackathon project"}
MS_TO_MPH = 2.23694
M_TO_FT = 3.28084

STATIONS = [
    {
        "id": "coops_8726520",
        "source": "noaa_tide",
        "name": "St. Petersburg tide gauge",
        "lat": 27.7606,
        "lon": -82.6269,
        "attribution": "NOAA CO-OPS",
    },
    {
        "id": "usgs_02301500",
        "source": "usgs_gauge",
        "name": "Alafia River at Lithia",
        "lat": 27.8717,
        "lon": -82.2115,
        "attribution": "USGS, flood categories NOAA NWPS",
    },
    {
        "id": "ndbc_42036",
        "source": "noaa_buoy",
        "name": "West Tampa buoy (42036)",
        "lat": 28.501,
        "lon": -84.508,
        "attribution": "NOAA NDBC",
    },
]


def iso(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def coops(client: httpx.Client) -> dict:
    base = "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter"
    common = {
        "station": "8726520",
        "begin_date": START.replace("-", ""),
        "end_date": END.replace("-", ""),
        "time_zone": "gmt",
        "units": "english",
        "format": "json",
        "application": "harbor_hackathon",
    }
    rows: dict[str, dict] = {}

    def get(product, **extra):
        r = client.get(base, params={**common, "product": product, **extra})
        r.raise_for_status()
        body = r.json()
        if "error" in body:
            print(f"  CO-OPS {product}: {body['error']}")
            return []
        return body.get("data") or body.get("predictions") or []

    for d in get("water_level", datum="MLLW"):
        rows.setdefault(d["t"], {})["water_level_ft"] = num(d["v"])
    for d in get("predictions", datum="MLLW", interval="6"):
        rows.setdefault(d["t"], {})["predicted_ft"] = num(d["v"])
    for d in get("air_pressure"):
        rows.setdefault(d["t"], {})["pressure_mb"] = num(d["v"])
    for d in get("wind"):
        rows.setdefault(d["t"], {}).update(wind_speed_mph=_kt_to_mph(d.get("s")), wind_gust_mph=_kt_to_mph(d.get("g")))

    out = []
    for t in sorted(rows):
        r = rows[t]
        if r.get("water_level_ft") is not None and r.get("predicted_ft") is not None:
            r["surge_ft"] = round(r["water_level_ft"] - r["predicted_ft"], 2)
        out.append({"t": iso(datetime.strptime(t, "%Y-%m-%d %H:%M").replace(tzinfo=UTC)), **r})
    return {"station": STATIONS[0], "units": {"level": "ft MLLW", "wind": "mph", "pressure": "mb"}, "rows": out}


def _kt_to_mph(v):
    # CO-OPS english units report wind in knots
    v = num(v)
    return None if v is None else round(v * 1.15078, 1)


def usgs(client: httpx.Client) -> dict:
    rows = []
    try:
        r = client.get(
            "https://waterservices.usgs.gov/nwis/iv/",
            params={"format": "json", "sites": "02301500", "parameterCd": "00065", "startDT": START, "endDT": END},
        )
        r.raise_for_status()
        for ts in r.json()["value"]["timeSeries"]:
            for v in ts["values"][0]["value"]:
                rows.append({"t": iso(datetime.fromisoformat(v["dateTime"])), "stage_ft": num(v["value"])})
        source = "waterservices.usgs.gov/nwis/iv"
    except Exception as exc:  # the legacy service is being retired; fall back to the OGC API
        print(f"  USGS legacy service failed ({exc}); trying the Water Data OGC API")
        r = client.get(
            "https://api.waterdata.usgs.gov/ogcapi/v0/collections/continuous/items",
            params={
                "monitoring_location_id": "USGS-02301500",
                "parameter_code": "00065",
                "time": f"{START}T00:00:00Z/{END}T23:59:59Z",
                "limit": 10000,
                "f": "json",
            },
        )
        r.raise_for_status()
        for f in r.json()["features"]:
            p = f["properties"]
            rows.append(
                {"t": iso(datetime.fromisoformat(p["time"].replace("Z", "+00:00"))), "stage_ft": num(p["value"])}
            )
        source = "api.waterdata.usgs.gov/ogcapi/v0"
    rows.sort(key=lambda r: r["t"])

    stages = {}
    try:
        g = client.get("https://api.water.noaa.gov/nwps/v1/gauges/LITF1")
        g.raise_for_status()
        cats = g.json().get("flood", {}).get("categories", {})
        stages = {k: num(v.get("stage")) for k, v in cats.items() if k in ("action", "minor", "moderate", "major")}
    except Exception as exc:
        print(f"  NWPS flood categories failed: {exc}")
    return {"station": STATIONS[1], "source": source, "flood_stages_ft": stages, "rows": rows}


def ndbc(client: httpx.Client) -> dict:
    r = client.get("https://www.ndbc.noaa.gov/data/historical/stdmet/42036h2024.txt.gz")
    r.raise_for_status()
    text = gzip.decompress(r.content).decode()
    lines = [l.split() for l in text.splitlines() if l.strip()]
    header = [h.lstrip("#") for h in lines[0]]
    rows = []
    start, end = datetime.fromisoformat(START), datetime.fromisoformat(END + "T23:59")
    for parts in lines[2:]:
        rec = dict(zip(header, parts, strict=False))
        t = datetime(int(rec["YY"]), int(rec["MM"]), int(rec["DD"]), int(rec["hh"]), int(rec["mm"]))
        if not (start <= t <= end):
            continue

        def clean(key, missing, rec=rec):
            v = num(rec.get(key))
            return None if v is None or v >= missing else v

        wspd, gst, wvht, pres = clean("WSPD", 99), clean("GST", 99), clean("WVHT", 99), clean("PRES", 9999)
        rows.append(
            {
                "t": iso(t.replace(tzinfo=UTC)),
                "wind_speed_mph": None if wspd is None else round(wspd * MS_TO_MPH, 1),
                "wind_gust_mph": None if gst is None else round(gst * MS_TO_MPH, 1),
                "wave_height_ft": None if wvht is None else round(wvht * M_TO_FT, 1),
                "pressure_mb": pres,
            }
        )
    return {"station": STATIONS[2], "rows": rows}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    with httpx.Client(headers=UA, timeout=60, follow_redirects=True) as client:
        for name, fetch in (("coops_8726520", coops), ("usgs_02301500", usgs), ("ndbc_42036", ndbc)):
            print(f"Fetching {name}...")
            try:
                data = fetch(client)
            except Exception as exc:
                print(f"  FAILED: {exc}")
                continue
            data["recorded_window"] = [START, END]
            (OUT / f"{name}.json").write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
            print(f"  {len(data['rows'])} rows")
    (OUT / "stations.json").write_text(json.dumps(STATIONS, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
