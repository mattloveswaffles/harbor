"""Download a storm's NOAA archive and write the replay files Harbor reads in demo mode.

Run from backend/ (needs the `tools` extra: pip install -e ".[dev,tools]"):

    python tools/fetch_replay.py                       # milton-2024
    python tools/fetch_replay.py --cache D:/nhc-cache  # keep the raw downloads somewhere else

Writes backend/data/replays/<storm>/:

    manifest.json                     every advisory, its issue time and the files it uses
    advisories/<atcf>_<NNN>.geojson   cone, forecast track and points, coastal watches/warnings
    wsp/<YYYYMMDDHH>.json             wind speed probabilities (34 and 64 kt), clipped to Florida
    toa/<atcf>_<NNN>.json             earliest reasonable arrival of tropical-storm winds
    alerts/<zip>.json                 archived NWS watches/warnings for the ZIP's zones (IEM)

Every time comes from the archive itself: full advisories from the UTC line of the forecast
advisory (TCM), intermediate "A" advisories from the shapefile's ADVDATE, arrival times from the
KML labels resolved against the advisory's publication time, landfall from the public advisory.
Nothing is hard-coded except the replay window start, which is a demo choice.

Raw downloads are cached (default backend/data/replays/.cache/, git-ignored), so a re-run only
fetches what's missing. Requests go out at most once a second with the NOAA_USER_AGENT header.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
import time
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from xml.etree import ElementTree

import httpx
import shapefile  # pyshp
from shapely.geometry import LineString, MultiPolygon, Polygon, box, mapping
from shapely.validation import make_valid

UTC = timezone.utc
BACKEND = Path(__file__).resolve().parents[1]
REPLAYS = BACKEND / "data" / "replays"

NHC = "https://www.nhc.noaa.gov"
IEM = "https://mesonet.agron.iastate.edu"

STORMS = {
    "milton-2024": {
        "atcf": "al142024",
        "name": "Milton",
        "year": 2024,
        "demo_zips": ["33602", "34236"],
        "start": "2024-10-06T03:00:00Z",  # demo choice: Maria's story starts here
        "alert_dates": ("2024-10-04", "2024-10-13"),
        "description": "Category 5 in the Gulf, landfall near Siesta Key as a Category 3. "
        "Replays the real NHC advisories and NWS alerts for Tampa Bay.",
    },
}

# Florida plus a margin: Harbor only signs up Florida ZIPs, so the wind grids are clipped here.
FL_BOX = (-88.0, 24.3, -79.5, 31.1)  # lon_min, lat_min, lon_max, lat_max
GRID_MARGIN = 0.5
SIMPLIFY_DEG = 0.005  # about 500 m: well under the 0.1° cone buffer the replay applies
BAND_SIMPLIFY_DEG = 0.05  # one 5 km cell: the bands are raster staircases, so this is the product's own resolution
TZ_OFFSETS = {"EDT": -4, "EST": -5, "CDT": -5, "CST": -6, "AST": -4, "ADT": -3, "UTC": 0, "GMT": 0}
ALERT_TYPES = {
    ("HU", "A"): "hurricane_watch",
    ("HU", "W"): "hurricane_warning",
    ("TR", "A"): "tropical_storm_watch",
    ("TR", "W"): "tropical_storm_warning",
    ("SS", "A"): "storm_surge_watch",
    ("SS", "W"): "storm_surge_warning",
    ("EW", "W"): "extreme_wind_warning",
}
CLASSIFICATIONS = {
    "TD": "tropical_depression",
    "TS": "tropical_storm",
    "HU": "hurricane",
    "MH": "hurricane",
    "STD": "subtropical_depression",
    "SS": "subtropical_storm",
    "PTC": "post_tropical",
    "EX": "post_tropical",
    "LO": "post_tropical",
    "DB": "post_tropical",
}
MONTHS = {m: i for i, m in enumerate("JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split(), 1)}
WEEKDAYS = {d: i for i, d in enumerate("Mon Tue Wed Thu Fri Sat Sun".split())}


def iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


# ---------------------------------------------------------------------------------------------
# Downloads


class Fetcher:
    """Polite cached GETs: at most one request a second, raw bytes kept on disk."""

    def __init__(self, cache: Path, user_agent: str):
        self.cache = cache
        self.cache.mkdir(parents=True, exist_ok=True)
        self.client = httpx.Client(headers={"User-Agent": user_agent}, timeout=60, follow_redirects=True)
        self._last = 0.0
        self.fetched = 0

    def get(self, url: str, name: str) -> bytes | None:
        """The file's bytes, or None on a 404 (a product NHC didn't issue)."""
        path = self.cache / name
        missing = path.with_suffix(path.suffix + ".404")
        if path.exists():
            return path.read_bytes()
        if missing.exists():
            return None
        for attempt in range(3):
            wait = 1.0 - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()
            try:
                res = self.client.get(url)
            except httpx.TransportError as exc:
                print(f"  retry {url}: {exc}", file=sys.stderr)
                time.sleep(2 * (attempt + 1))
                continue
            if res.status_code == 404:
                missing.parent.mkdir(parents=True, exist_ok=True)
                missing.write_bytes(b"")
                return None
            if res.status_code >= 500:
                time.sleep(2 * (attempt + 1))
                continue
            res.raise_for_status()
            self.fetched += 1
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(res.content)
            return res.content
        raise RuntimeError(f"giving up on {url}")


def text_of(html: bytes) -> str:
    """The <pre> text of an NHC .shtml product, without tags."""
    s = html.decode("utf-8", "replace")
    m = re.search(r"<pre[^>]*>(.*?)</pre>", s, re.S | re.I)
    s = m.group(1) if m else s
    return re.sub(r"<[^>]+>", "", s).replace("&amp;", "&")


# ---------------------------------------------------------------------------------------------
# Parsing helpers


def rnd(geom_mapping: dict, nd: int = 4) -> dict:
    """Round GeoJSON coordinates to 4 decimals (about 10 m) to keep the files small."""

    def r(c):
        if isinstance(c, (int, float)):
            return round(c, nd)
        return [r(x) for x in c]

    return {"type": geom_mapping["type"], "coordinates": r(geom_mapping["coordinates"])}


def shapes_in(zf: zipfile.ZipFile, suffix: str) -> list[tuple[dict, dict]]:
    """(record, __geo_interface__) for every shape in the layer whose name ends with `suffix`."""
    stems = [n[:-4] for n in zf.namelist() if n.endswith(suffix + ".shp")]
    if not stems:
        return []
    stem = stems[0]
    reader = shapefile.Reader(
        shp=io.BytesIO(zf.read(stem + ".shp")),
        shx=io.BytesIO(zf.read(stem + ".shx")),
        dbf=io.BytesIO(zf.read(stem + ".dbf")),
    )
    out = []
    for sr in reader.iterShapeRecords():
        if sr.shape.shapeType == shapefile.NULL:
            continue  # NHC writes empty records (e.g. a probability band with no area)
        if sr.shape.shapeType in (shapefile.POLYGON, shapefile.POLYGONZ, shapefile.POLYGONM):
            # Raw rings: the wind-probability bands are read with the even-odd rule, so ring
            # orientation (which __geo_interface__ uses to guess holes) doesn't matter.
            pts, parts = sr.shape.points, list(sr.shape.parts) + [len(sr.shape.points)]
            geom = {"type": "Rings", "coordinates": [pts[a:b] for a, b in zip(parts, parts[1:])]}
        else:
            geom = sr.shape.__geo_interface__
        out.append((sr.record.as_dict(), geom))
    return out


def parse_local(text: str) -> datetime:
    """'400 PM CDT Tue Oct 08 2024' or '1100 AM EDT Sat Oct 05 2024' -> aware UTC datetime."""
    m = re.match(r"\s*(\d{1,4})\s+(AM|PM)\s+([A-Z]{3})\s+\w{3}\s+(\w{3})\s+(\d{1,2})\s+(\d{4})", text, re.I)
    if not m:
        raise ValueError(f"unrecognised local time {text!r}")
    hhmm, ampm, tz, mon, day, year = m.groups()
    hhmm = hhmm.zfill(4) if len(hhmm) > 2 else hhmm.zfill(2) + "00"
    hour, minute = int(hhmm[:2]) % 12, int(hhmm[2:])
    if ampm.upper() == "PM":
        hour += 12
    local = datetime(int(year), MONTHS[mon.upper()], int(day), hour, minute)
    return (local - timedelta(hours=TZ_OFFSETS[tz.upper()])).replace(tzinfo=UTC)


def tcm_issued(text: str) -> datetime:
    """The '2100 UTC TUE OCT 08 2024' line of a forecast advisory."""
    m = re.search(r"(\d{4}) UTC \w{3} (\w{3}) (\d{2}) (\d{4})", text)
    if not m:
        raise ValueError("no UTC line in the forecast advisory")
    hhmm, mon, day, year = m.groups()
    return datetime(int(year), MONTHS[mon], int(day), int(hhmm[:2]), int(hhmm[2:]), tzinfo=UTC)


TITLE_CLASSES = {
    "POTENTIAL TROPICAL CYCLONE": "potential_tropical_cyclone",
    "POST-TROPICAL CYCLONE": "post_tropical",
    "REMNANTS OF": "post_tropical",
    "SUBTROPICAL DEPRESSION": "subtropical_depression",
    "SUBTROPICAL STORM": "subtropical_storm",
    "TROPICAL DEPRESSION": "tropical_depression",
    "TROPICAL STORM": "tropical_storm",
    "HURRICANE": "hurricane",
}


def title_class(text: str) -> str | None:
    """'Post-Tropical Cyclone Milton Advisory Number 23' -> post_tropical (the product title is
    authoritative; the shapefile's STORMTYPE describes the forecast and can differ)."""
    alts = "|".join(re.escape(t) for t in TITLE_CLASSES)
    m = re.search(rf"\b({alts})\s+\w+\s+(?:FORECAST/ADVISORY|INTERMEDIATE ADVISORY|ADVISORY)", text, re.I)
    return TITLE_CLASSES[m.group(1).upper()] if m else None


def public_headline(text: str) -> str | None:
    """The '...MILTON FORECAST TO ...' summary line at the top of a public advisory."""
    m = re.search(r"\n\s*\.\.\.(.+?)\.\.\.\s*\n", text, re.S)
    return re.sub(r"\s+", " ", m.group(1)).strip() if m else None


def update_landfall(text: str, issued: datetime) -> datetime | None:
    """A Tropical Cyclone Update announcing landfall -> the landfall time.

    NHC issues the update at landfall ("...MILTON MAKES LANDFALL NEAR SIESTA KEY...", "the eye has
    made landfall"), so the time is the update's own UTC stamp, unless the text names an explicit
    '(HHMM UTC)' time for it.
    """
    flat = re.sub(r"\s+", " ", text)
    if not re.search(r"made landfall|makes landfall", flat, re.I):
        return None
    m = re.search(r"landfall[^.]*?\((\d{4}) UTC\)", flat, re.I)
    if not m:
        return issued
    at = issued.replace(hour=int(m.group(1)[:2]), minute=int(m.group(1)[2:]), second=0)
    return at - timedelta(days=1) if at > issued else at


def valid_time(validtime: str, issued: datetime) -> datetime:
    """'08/1800' (day/HHMM UTC) in the advisory's month, rolling into the next month if needed."""
    day, hhmm = validtime.split("/")
    at = datetime(issued.year, issued.month, int(day), int(hhmm[:2]), int(hhmm[2:]), tzinfo=UTC)
    if at < issued - timedelta(days=2):  # e.g. a 30 Sep advisory forecasting 02 Oct
        month = issued.month % 12 + 1
        at = at.replace(year=issued.year + (issued.month == 12), month=month)
    return at


# ---------------------------------------------------------------------------------------------
# Products


def build_advisory(zf: zipfile.ZipFile, atcf: str, adv: str) -> tuple[dict, dict]:
    """5-day zip -> (GeoJSON FeatureCollection, advisory facts for the manifest)."""
    pts = sorted(shapes_in(zf, "_5day_pts"), key=lambda s: s[0]["TAU"])
    if not pts:
        raise ValueError(f"{adv}: no forecast points")
    first = pts[0][0]
    lon0, lat0 = pts[0][1]["coordinates"][:2]  # the DBF LAT/LON fields are rounded to whole degrees
    advdate_utc = parse_local(first["ADVDATE"])
    features = []
    for rec, geom in shapes_in(zf, "_5day_pgn"):
        rings = sorted((Polygon(r) for r in geom["coordinates"] if len(r) >= 4), key=lambda p: -p.area)
        poly = make_valid(rings[0]).simplify(SIMPLIFY_DEG, preserve_topology=True)  # the cone is one ring
        features.append({"type": "Feature", "geometry": rnd(mapping(poly)),
                         "properties": {"layer": "cone", "advisory": adv, "storm_type": rec["STORMTYPE"]}})
    for rec, geom in shapes_in(zf, "_5day_lin"):
        features.append({"type": "Feature", "geometry": rnd(geom),
                         "properties": {"layer": "track", "kind": "forecast_line", "advisory": adv}})
    for rec, geom in pts:
        features.append({"type": "Feature", "geometry": rnd(geom), "properties": {
            "layer": "track", "kind": "forecast_point", "advisory": adv, "tau_h": rec["TAU"],
            "valid_time": iso(valid_time(rec["VALIDTIME"], advdate_utc)),
            "max_wind_kt": rec["MAXWIND"], "gust_kt": rec["GUST"],
            "pressure_mb": rec["MSLP"] if rec["MSLP"] < 9000 else None,
            "category": rec["SSNUM"] or None, "storm_type": rec["STORMTYPE"],
            "development": rec.get("TCDVLP"), "label": rec.get("DATELBL"),
        }})
    for rec, geom in shapes_in(zf, "_ww_wwlin"):
        features.append({"type": "Feature", "geometry": rnd(geom),
                         "properties": {"layer": "watches_warnings", "advisory": adv, "tcww": rec["TCWW"]}})
    facts = {
        "advisory_number": str(first["ADVISNUM"]),
        "advdate": first["ADVDATE"],
        "advdate_utc": advdate_utc,
        "classification": CLASSIFICATIONS.get(first["STORMTYPE"], first["STORMTYPE"].lower()),
        "storm_type": first["STORMTYPE"],
        "category": first["SSNUM"] or None,
        "lat": round(lat0, 2),
        "lon": round(lon0, 2),
        "max_wind_kt": first["MAXWIND"],
        "pressure_mb": first["MSLP"] if first["MSLP"] < 9000 else None,
        "movement_dir_deg": first["TCDIR"] if first["TCDIR"] < 9000 else None,
        "movement_kt": first["TCSPD"] if first["TCSPD"] < 9000 else None,
    }
    return {"type": "FeatureCollection", "features": features}, facts


def band_range(label: str) -> tuple[float, float]:
    """'<5%' -> (0, .05), '10-20%' -> (.1, .2), '>90%' -> (.9, 1)."""
    s = label.strip().rstrip("%")
    if s.startswith("<"):
        return 0.0, float(s[1:]) / 100
    if s.startswith(">"):
        return float(s[1:]) / 100, 1.0
    lo, hi = s.split("-")
    return float(lo) / 100, float(hi) / 100


def build_wsp(half_deg: zipfile.ZipFile, five_km: zipfile.ZipFile | None, synoptic: str) -> dict:
    """Half-degree grid values + 5 km bands for 34 and 64 kt, clipped to Florida.

    Bands are stored as their individual rings (each one a polygon). A point is inside a band when
    an odd number of that band's rings contain it: the even-odd rule, which is how the NHC rings
    with holes are meant to be read.
    """
    lon0, lat0, lon1, lat1 = FL_BOX
    clip = box(*FL_BOX)
    out = {"synoptic": synoptic, "units": "probability 0..1, cumulative 0-120 h", "grid_step_deg": 0.5,
           "clip_box": list(FL_BOX), "grid": {}, "bands": {}}
    for kt in ("34", "64"):
        cells = []
        for rec, geom in shapes_in(half_deg, f"_wsp{kt}knt120hr_halfDeg"):
            lon, lat = geom["coordinates"][:2]
            if lon0 - GRID_MARGIN <= lon <= lon1 + GRID_MARGIN and lat0 - GRID_MARGIN <= lat <= lat1 + GRID_MARGIN:
                if abs(lon * 2 - round(lon * 2)) > 1e-6 or abs(lat * 2 - round(lat * 2)) > 1e-6:
                    raise ValueError(f"{synoptic}: grid point off the 0.5° lattice: {lon}, {lat}")
                cells.append([round(lon, 2), round(lat, 2), round(float(rec["PWIND120"]) / 100, 4)])
        out["grid"][kt] = cells
        bands = []
        if five_km is not None:
            for rec, geom in shapes_in(five_km, f"_wsp{kt}knt120hr_5km"):
                lo, hi = band_range(rec["PERCENTAGE"])
                rings = []
                for ring in geom["coordinates"]:
                    if len(ring) < 4:
                        continue
                    piece = make_valid(Polygon(ring))
                    if not piece.intersects(clip):
                        continue
                    piece = piece.intersection(clip).simplify(BAND_SIMPLIFY_DEG, preserve_topology=True)
                    for p in getattr(piece, "geoms", [piece]):
                        if isinstance(p, Polygon) and not p.is_empty:
                            rings.append(rnd(mapping(Polygon(p.exterior)), 3)["coordinates"][0])
                        elif isinstance(p, MultiPolygon):
                            rings.extend(rnd(mapping(Polygon(q.exterior)), 3)["coordinates"][0] for q in p.geoms)
                if rings:
                    bands.append({"label": rec["PERCENTAGE"], "lo": lo, "hi": hi, "rings": rings})
        out["bands"][kt] = bands
    return out


KML = "{http://earth.google.com/kml/2.2}"


def build_toa(kmz: zipfile.ZipFile) -> dict:
    """Earliest-reasonable arrival KMZ -> isochrones with UTC times, plus the 5% ring."""
    kml_name = next(n for n in kmz.namelist() if n.endswith(".kml"))
    root = ElementTree.fromstring(kmz.read(kml_name))
    ns = KML if root.tag.startswith(KML) else ""
    data = {d.get("name"): (d.findtext(f"{ns}value") or "").strip() for d in root.iter(f"{ns}Data")}
    published = parse_local(data["pubAdvTime"])
    tz = data.get("timezone", "UTC").upper()
    offset = timedelta(hours=TZ_OFFSETS[tz])
    local_pub = published + offset  # naive-style local wall time, kept tz-aware only for arithmetic

    isochrones, ring5 = [], None
    previous = None
    for pm in root.iter(f"{ns}Placemark"):
        lines = list(pm.iter(f"{ns}LineString"))
        if not lines:
            continue
        cells = re.findall(r"<td>([^<]*)</td>", pm.findtext(f"{ns}description") or "")
        label = cells[-1].strip() if cells else (pm.findtext(f"{ns}name") or "").strip()
        coords = []
        for ls in lines:
            for tok in (ls.findtext(f"{ns}coordinates") or "").split():
                lon, lat = tok.split(",")[:2]
                coords.append((float(lon), float(lat)))
        if "5%" in label:
            ring5 = rnd(mapping(Polygon(coords).simplify(SIMPLIFY_DEG)))["coordinates"][0]
            continue
        m = re.match(r"(\w{3})\s+(\d{1,2})\s*(am|pm)", label, re.I)
        if not m:
            print(f"  skipping TOA line with label {label!r}", file=sys.stderr)
            continue
        wday, hour, ampm = WEEKDAYS[m.group(1).title()], int(m.group(2)) % 12, m.group(3).lower()
        hour += 12 if ampm == "pm" else 0
        # The first matching weekday on or after the publication day, strictly increasing.
        day = local_pub.date()
        while True:
            cand = datetime(day.year, day.month, day.day, hour, tzinfo=UTC) - offset
            if day.weekday() == wday and (previous is None or cand > previous) and cand >= published - timedelta(hours=1):
                break
            day += timedelta(days=1)
        previous = cand
        line = LineString(coords).simplify(SIMPLIFY_DEG)
        isochrones.append({"time": iso(cand), "label": label, "coordinates": rnd(mapping(line))["coordinates"]})
    return {"product": "earliest_reasonable_toa_34", "published_at": iso(published), "timezone": tz,
            "isochrones": isochrones, "ring5": ring5}


def build_alerts(raw: dict, zip_code: str, lat: float, lon: float) -> dict:
    zones = sorted({e["ugc"] for e in raw.get("events", [])})
    events = []
    for e in raw.get("events", []):
        kind = ALERT_TYPES.get((e["phenomena"], e["significance"]))
        if not kind:
            continue  # flood, tornado and surf products aren't storm watches/warnings
        events.append({
            "type": kind, "headline": f"{e['name']} for {e['ugc']} (NWS {e['wfo']})",
            "issued": e["issue"], "expires": e["expire"], "ugc": e["ugc"],
            "vtec": f"{e['phenomena']}.{e['significance']}.{e['eventid']:04d}", "source": "iem",
            "url": IEM + e["url"],
        })
    events.sort(key=lambda e: (e["issued"], e["type"]))
    return {"zip": zip_code, "lat": lat, "lon": lon, "zones": zones, "source": "Iowa Environmental Mesonet VTEC archive",
            "events": events}


# ---------------------------------------------------------------------------------------------


def zip_point(zip_code: str) -> tuple[float, float]:
    sys.path.insert(0, str(BACKEND))
    from harbor.geo import lookup_zip

    place = lookup_zip(zip_code)
    if not place:
        raise SystemExit(f"ZIP {zip_code} isn't in harbor/data/zcta_fl.csv")
    return place["lat"], place["lon"]


def write_json(path: Path, data, compact: bool = True) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, separators=(",", ":")) if compact else json.dumps(data, indent=2)
    path.write_text(text + "\n", encoding="utf-8")
    return len(text)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("storm", nargs="?", default="milton-2024", choices=sorted(STORMS))
    ap.add_argument("--cache", type=Path, default=REPLAYS / ".cache", help="where raw downloads are kept")
    ap.add_argument("--out", type=Path, default=None, help="output folder (default data/replays/<storm>)")
    args = ap.parse_args()

    cfg = STORMS[args.storm]
    atcf, year = cfg["atcf"], cfg["year"]
    basin_num = atcf[:4]  # al14
    out = args.out or REPLAYS / args.storm
    ua = os.environ.get("NOAA_USER_AGENT") or "Harbor hackathon project (replay builder)"
    f = Fetcher(args.cache / args.storm, ua)

    # 1. Which advisories exist: the NHC GIS archive page lists every 5-day cone file.
    page = f.get(f"{NHC}/gis/archive_forecast_results.php?id={basin_num}&year={year}", "archive_index.html")
    advs = sorted(set(re.findall(rf"{atcf}_5day_(\d{{3}}A?)\.zip", page.decode("utf-8", "replace"))),
                  key=lambda a: (int(a[:3]), a))
    if not advs:
        raise SystemExit("no advisories found in the NHC archive index")
    print(f"{atcf}: {len(advs)} advisories ({advs[0]}..{advs[-1]})")

    manifest_advs = []
    sizes = {"advisories": 0, "wsp": 0, "toa": 0, "alerts": 0}
    last_full = None
    landfall_at = None
    for adv in advs:
        intermediate = adv.endswith("A")
        z = f.get(f"{NHC}/gis/forecast/archive/{atcf}_5day_{adv}.zip", f"5day/{atcf}_5day_{adv}.zip")
        if z is None:
            print(f"  {adv}: cone zip missing, skipped")
            continue
        fc, facts = build_advisory(zipfile.ZipFile(io.BytesIO(z)), atcf, adv)
        num = adv[:3]

        if intermediate:
            issued, issued_from = facts["advdate_utc"], "advdate"
            pub = f.get(f"{NHC}/archive/{year}/{basin_num}/{atcf}.public_a.{num}.shtml", f"text/{atcf}.public_a.{num}.shtml")
        else:
            tcm = f.get(f"{NHC}/archive/{year}/{basin_num}/{atcf}.fstadv.{num}.shtml", f"text/{atcf}.fstadv.{num}.shtml")
            if tcm is not None:
                issued, issued_from = tcm_issued(text_of(tcm)), "tcm"
                if abs((issued - facts["advdate_utc"]).total_seconds()) > 3600:
                    print(f"  {adv}: TCM {iso(issued)} vs ADVDATE {iso(facts['advdate_utc'])}", file=sys.stderr)
            else:
                issued, issued_from = facts["advdate_utc"], "advdate"
            pub = f.get(f"{NHC}/archive/{year}/{basin_num}/{atcf}.public.{num}.shtml", f"text/{atcf}.public.{num}.shtml")
        headline = public_headline(text_of(pub)) if pub else None
        if pub and (cls := title_class(text_of(pub))):
            facts["classification"] = cls
        if facts["classification"] != "hurricane":
            facts["category"] = None

        sizes["advisories"] += write_json(out / "advisories" / f"{atcf}_{adv}.geojson", fc)
        entry = {
            "adv": adv, "advisory_number": facts["advisory_number"], "issued_at": iso(issued),
            "issued_from": issued_from, "intermediate": intermediate, "headline": headline,
            **{k: facts[k] for k in ("classification", "storm_type", "category", "lat", "lon", "max_wind_kt",
                                     "pressure_mb", "movement_dir_deg", "movement_kt")},
            "file": f"advisories/{atcf}_{adv}.geojson",
        }

        if intermediate:
            # NHC issues no wind probabilities or arrival times for "A" advisories: reuse the last full one.
            entry["wsp"] = last_full["wsp"] if last_full else None
            entry["toa"] = last_full["toa"] if last_full else None
            entry["products_from"] = last_full["adv"] if last_full else None
        else:
            # Wind probabilities are named by synoptic time (00/06/12/18Z), normally issue time - 3 h.
            # A special advisory off the usual cycle (Milton's 009 at 12Z) uses the latest synoptic
            # time before it, i.e. the same probabilities as the advisory before.
            base = issued - timedelta(hours=3)
            synoptic = base.replace(hour=base.hour - base.hour % 6, minute=0).strftime("%Y%m%d%H")
            half = f.get(f"{NHC}/gis/forecast/archive/{synoptic}_wsp_120hrhalfDeg.zip", f"wsp/{synoptic}_wsp_120hrhalfDeg.zip")
            five = f.get(f"{NHC}/gis/forecast/archive/{synoptic}_wsp_120hr5km.zip", f"wsp/{synoptic}_wsp_120hr5km.zip")
            entry["wsp"] = None
            if half is not None:
                wsp = build_wsp(zipfile.ZipFile(io.BytesIO(half)), zipfile.ZipFile(io.BytesIO(five)) if five else None, synoptic)
                sizes["wsp"] += write_json(out / "wsp" / f"{synoptic}.json", wsp)
                entry["wsp"] = f"wsp/{synoptic}.json"
            else:
                print(f"  {adv}: no wind probabilities for {synoptic}")
            kmz = f.get(f"{NHC}/storm_graphics/api/{atcf.upper()}_{num}adv_earliest_reasonable_toa_34.kmz",
                        f"toa/{atcf.upper()}_{num}adv_earliest_reasonable_toa_34.kmz")
            entry["toa"] = None
            if kmz is not None:
                toa = build_toa(zipfile.ZipFile(io.BytesIO(kmz)))
                sizes["toa"] += write_json(out / "toa" / f"{atcf}_{adv}.json", toa)
                entry["toa"] = f"toa/{atcf}_{adv}.json"
            else:
                print(f"  {adv}: no arrival-time product")
            entry["products_from"] = adv
            last_full = entry
        manifest_advs.append(entry)
        print(f"  {adv:>4} {entry['issued_at']} ({issued_from}) {entry['classification']} "
              f"cat {entry['category']} wsp={'y' if entry['wsp'] else '-'} toa={'y' if entry['toa'] else '-'}")

    manifest_advs.sort(key=lambda e: e["issued_at"])

    # Landfall: the first Tropical Cyclone Update (listed on the storm's archive page) that says
    # "made landfall ... (HHMM UTC)". File names carry their UTC issue time: update.MMDDHHMM.
    storm_page = f.get(f"{NHC}/archive/{year}/{cfg['name'].upper()}.shtml", "storm_page.html") or b""
    updates = sorted(set(re.findall(rf"{atcf}\.update\.(\d{{8}})\.shtml", storm_page.decode("utf-8", "replace"))))
    for stamp in updates:
        at = datetime(year, int(stamp[:2]), int(stamp[2:4]), int(stamp[4:6]), int(stamp[6:]), tzinfo=UTC)
        tcu = f.get(f"{NHC}/archive/{year}/{basin_num}/{atcf}.update.{stamp}.shtml", f"text/{atcf}.update.{stamp}.shtml")
        if tcu and (landfall_at := update_landfall(text_of(tcu), at)):
            break
    if landfall_at is None:
        print("  landfall: not found in the update products", file=sys.stderr)

    # 2. Archived NWS watches and warnings for each demo ZIP (IEM matches by the ZIP's zones).
    sdate, edate = cfg["alert_dates"]
    zones = {}
    for z in cfg["demo_zips"]:
        lat, lon = zip_point(z)
        raw = f.get(f"{IEM}/json/vtec_events_bypoint.py?lat={lat}&lon={lon}&sdate={sdate}&edate={edate}&fmt=json",
                    f"iem/{z}.json")
        alerts = build_alerts(json.loads(raw), z, lat, lon)
        sizes["alerts"] += write_json(out / "alerts" / f"{z}.json", alerts, compact=False)
        zones[z] = alerts["zones"]
        print(f"  alerts {z}: {len(alerts['events'])} storm alerts on {', '.join(alerts['zones'])}")

    last = datetime.fromisoformat(manifest_advs[-1]["issued_at"].replace("Z", "+00:00"))
    manifest = {
        "id": args.storm,
        "storm_id": atcf,
        "name": cfg["name"],
        "year": year,
        "description": cfg["description"],
        "landfall_at": iso(landfall_at) if landfall_at else None,
        "demo_zips": cfg["demo_zips"],
        "zones": zones,
        "start": cfg["start"],
        "end": iso(last + timedelta(hours=12)),
        "advisories": manifest_advs,
        "attribution": ["NOAA National Hurricane Center", "NWS via Iowa Environmental Mesonet"],
        "sources": {
            "cones": f"{NHC}/gis/forecast/archive/{atcf}_5day_<NNN>.zip",
            "wind_probabilities": f"{NHC}/gis/forecast/archive/<YYYYMMDDHH>_wsp_120hr{{5km,halfDeg}}.zip",
            "arrival_times": f"{NHC}/storm_graphics/api/{atcf.upper()}_<NNN>adv_earliest_reasonable_toa_34.kmz",
            "advisory_text": f"{NHC}/archive/{year}/{basin_num}/{atcf}.{{fstadv,public}}.<NNN>.shtml",
            "alerts": f"{IEM}/json/vtec_events_bypoint.py",
        },
        "generated_by": "tools/fetch_replay.py",
    }
    write_json(out / "manifest.json", manifest, compact=False)
    total = sum(sizes.values())
    print(f"landfall: {manifest['landfall_at']}; replay {manifest['start']} -> {manifest['end']}")
    print(f"wrote {out} ({total / 1e6:.2f} MB: " + ", ".join(f"{k} {v / 1e3:.0f} KB" for k, v in sizes.items())
          + f"); {f.fetched} new downloads")


if __name__ == "__main__":
    main()
