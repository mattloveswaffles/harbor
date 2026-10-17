"""Build the evacuation data for the Milton demo (run once, then commit the output).

Run from backend/ (needs internet; GSA_API_KEY optional, DEMO_KEY is used otherwise):

    python tools/build_demo_evac.py

Writes data/evac/:
- destinations.json  inland cities with GSA per-diem lodging and meal rates (FY2025, October)
- routes_33602.json  driving routes from Tampa 33602 to each destination (OSRM public server)
- shelters_milton.json  Hillsborough County's Milton shelters, located via OpenStreetMap
- lodging.json  hotels and motels near the main destinations (OpenStreetMap snapshot)
- atms.json  ATMs near Tampa and the destinations (OpenStreetMap; Nessie's own ATMs are all in VA/MD/DC)

OSRM's demo server allows 1 request per second and Overpass asks for light use, so this script
paces itself. Hotel prices are never invented: cost comes from the GSA rate at run time.
"""

import json
import os
import sys
import time
from pathlib import Path

import httpx

OUT = Path(__file__).resolve().parents[1] / "data" / "evac"
UA = {"User-Agent": os.environ.get("NOAA_USER_AGENT") or "Harbor hackathon project (evacuation demo data)"}
ORIGIN = {"zip": "33602", "lat": 27.9506, "lon": -82.4572}
MI = 1609.344

# Inland candidates: name, state, lat, lon, main corridor from Tampa, hotel hub?
CITIES = [
    ("Brandon", "FL", 27.9378, -82.2859, "SR-60 E / I-75", False),
    ("Plant City", "FL", 28.0186, -82.1129, "I-4 E", False),
    ("Lakeland", "FL", 28.0395, -81.9498, "I-4 E", True),
    ("Winter Haven", "FL", 28.0222, -81.7329, "I-4 E / US-27", False),
    ("Orlando", "FL", 28.5383, -81.3792, "I-4 E", True),
    ("Sebring", "FL", 27.4956, -81.4409, "US-27 S", False),
    ("Brooksville", "FL", 28.5553, -82.3879, "I-75 N", False),
    ("Leesburg", "FL", 28.8108, -81.8779, "I-75 N / US-27", False),
    ("Ocala", "FL", 29.1872, -82.1401, "I-75 N", True),
    ("Gainesville", "FL", 29.6516, -82.3248, "I-75 N", True),
    ("Lake City", "FL", 30.1897, -82.6393, "I-75 N", True),
    ("Tallahassee", "FL", 30.4383, -84.2807, "I-75 N / I-10 W", True),
    ("Valdosta", "GA", 30.8327, -83.2785, "I-75 N", True),
    ("Macon", "GA", 32.8407, -83.6324, "I-75 N", True),
    ("Atlanta", "GA", 33.7490, -84.3880, "I-75 N", True),
    ("Dothan", "AL", 31.2232, -85.3905, "I-75 N / US-231", True),
]
LODGING_CITIES = ["Lakeland", "Ocala", "Gainesville", "Lake City", "Tallahassee", "Valdosta", "Macon", "Atlanta", "Dothan", "Orlando", "Sebring"]

SHELTERS = [  # Hillsborough County releases, 7-9 Oct 2024 (hcfl.gov) and WUSF's shelter list
    ("Burnett Middle School", "general", True), ("Durant High School", "general", True),
    ("Middleton High School", "general", True), ("Shields Middle School", "general", True),
    ("Sickles High School", "general", True), ("Steinbrenner High School", "general", True),
    ("Pizzo Elementary School", "general", False), ("Reddick Elementary School", "general", False),
    ("Mulrennan Middle School", "general", False), ("Lockhart Elementary School", "general", False),
    ("Collins", "general", False),
    ("Erwin Technical College", "special_needs", True), ("Sumner High School", "special_needs", True),
    ("Strawberry Crest High School", "special_needs", True),
]
REPORTED_FULL = {  # reported full during Milton; the replay times are approximate
    "Erwin Technical College": "2024-10-09T12:00:00Z",
    "Durant High School": "2024-10-09T15:00:00Z",
}
SHELTER_SOURCES = [
    "https://hcfl.gov/newsroom/2024/10/09/hillsborough-county-opens-three-more-shelters-ahead-of-hurricane-milton",
    "https://www.wusf.org/weather/2024-10-08/hurricane-milton-tampa-bay-county-by-county-shelter-list",
]


def slug(name: str) -> str:
    return name.lower().replace(" ", "_").replace(".", "")


# Rates the research step fetched from the GSA API (FY2025, October), used if the API is busy now.
KNOWN_RATES = {("Atlanta", "GA"): (18200, 8600)}


def gsa_rates(client: httpx.Client, city: str, state: str, previous: dict | None = None) -> dict:
    if previous and previous.get("rate_checked"):
        return {k: previous[k] for k in ("lodging_cents", "meals_cents", "basis", "standard_rate", "rate_checked")}
    key = os.environ.get("GSA_API_KEY") or "DEMO_KEY"
    try:
        r = client.get(f"https://api.gsa.gov/travel/perdiem/v2/rates/city/{city}/state/{state}/year/2025",
                       params={"api_key": key})
        r.raise_for_status()
        rates = r.json()["rates"][0]["rate"]
        best = next((x for x in rates if x.get("city", "").lower() == city.lower()), None) or next(
            (x for x in rates if x.get("standardRate") in ("true", True)), rates[0])
        october = next(m["value"] for m in best["months"]["month"] if m["number"] == 10)
        return {"lodging_cents": round(october * 100), "meals_cents": round(best["meals"] * 100),
                "basis": f"GSA per diem FY2025, {best.get('city') or 'standard rate'}, October",
                "standard_rate": best.get("standardRate") in ("true", True), "rate_checked": True}
    except Exception as exc:
        if (city, state) in KNOWN_RATES:
            lodging, meals = KNOWN_RATES[(city, state)]
            return {"lodging_cents": lodging, "meals_cents": meals, "basis": f"GSA per diem FY2025, {city}, October",
                    "standard_rate": False, "rate_checked": True}
        print(f"  GSA failed for {city} ({type(exc).__name__}); assuming the FY2025 standard rate. "
              "Rerun with GSA_API_KEY set to check it.")
        return {"lodging_cents": 11000, "meals_cents": 6800,
                "basis": "GSA per diem FY2025 standard rate (assumed; city rate not checked)",
                "standard_rate": True, "rate_checked": False}


def step_text(step: dict) -> str:
    m = step["maneuver"]
    kind, mod = m.get("type", ""), m.get("modifier", "")
    road = step.get("ref") or step.get("name") or "the road"
    if kind == "depart":
        return f"Head {m.get('bearing_after') and _compass(m['bearing_after'])} on {road}".replace("Head  on", "Start on")
    if kind == "arrive":
        return "Arrive at your destination"
    if kind in ("on ramp", "merge"):
        return f"Take the ramp onto {road}" if kind == "on ramp" else f"Merge onto {road}"
    if kind == "off ramp":
        return f"Take the exit toward {step.get('destinations') or road}"
    if kind == "fork":
        return f"Keep {mod.replace('slight ', '')} at the fork onto {road}"
    if kind in ("roundabout", "rotary"):
        return f"At the roundabout, take the exit onto {road}"
    if kind == "new name" or (kind == "continue" and mod == "straight"):
        return f"Continue onto {road}"
    if kind in ("turn", "end of road", "continue"):
        return f"Turn {mod} onto {road}" if mod else f"Continue on {road}"
    return f"Continue on {road}"


def _compass(bearing: float) -> str:
    return ["north", "northeast", "east", "southeast", "south", "southwest", "west", "northwest"][round(bearing / 45) % 8]


def osrm_route(client: httpx.Client, lat: float, lon: float) -> dict:
    url = (f"https://router.project-osrm.org/route/v1/driving/{ORIGIN['lon']},{ORIGIN['lat']};{lon},{lat}"
           "?overview=simplified&geometries=geojson&steps=true")
    r = client.get(url)
    r.raise_for_status()
    route = r.json()["routes"][0]
    steps = []
    for leg in route["legs"]:
        for s in leg["steps"]:
            dist = s["distance"] / MI
            if s["maneuver"]["type"] in ("depart", "arrive") or dist >= 0.2:
                steps.append({"text": step_text(s), "distance_mi": round(dist, 1)})
    return {
        "provider": "osrm", "distance_mi": round(route["distance"] / MI, 1),
        "drive_time_min_normal": round(route["duration"] / 60),
        "geometry": route["geometry"], "steps": steps,
        "attribution": "Routing © OSRM, map data © OpenStreetMap contributors",
    }


OVERPASS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter"]


def overpass(client: httpx.Client, query: str) -> list[dict]:
    for attempt in range(4):
        r = client.post(OVERPASS[attempt % len(OVERPASS)], data={"data": query})
        if r.status_code in (429, 500, 502, 503, 504):
            time.sleep(10 * (attempt + 1))
            continue
        r.raise_for_status()
        return r.json()["elements"]
    raise RuntimeError("Overpass busy")


def _center(el: dict) -> tuple[float, float]:
    if "lat" in el:
        return el["lat"], el["lon"]
    return el["center"]["lat"], el["center"]["lon"]


def find_shelters(client: httpx.Client) -> list[dict]:
    names = "|".join(n for n, _, _ in SHELTERS)
    q = (f'[out:json][timeout:60];(nwr["name"~"{names}",i]["amenity"~"school|college"]'
         "(27.55,-82.75,28.20,-82.05););out center tags;")
    found = overpass(client, q)
    # Looser second pass (first word of the name, any tag) for schools OSM names differently
    missing = [n for n, _, _ in SHELTERS if not any(n.lower() in e.get("tags", {}).get("name", "").lower() for e in found)]
    if missing:
        loose = "|".join(n.split()[0] for n in missing)
        time.sleep(5)
        found += overpass(client, f'[out:json][timeout:60];nwr["name"~"^({loose})",i]["amenity"](27.55,-82.75,28.20,-82.05);out center tags;')
    out = []
    for name, kind, pets in SHELTERS:
        first = name.split()[0].lower()
        match = next((e for e in found if name.lower() in e.get("tags", {}).get("name", "").lower()), None) or next(
            (e for e in found if e.get("tags", {}).get("name", "").lower().startswith(first)
             and e.get("tags", {}).get("amenity") in ("school", "college")), None)
        if match is None:
            print(f"  shelter not found in OSM: {name}")
            continue
        lat, lon = _center(match)
        tags = match.get("tags", {})
        address = " ".join(x for x in (tags.get("addr:housenumber"), tags.get("addr:street"), tags.get("addr:city")) if x)
        out.append({
            "id": f"hc_{slug(name)}", "name": tags.get("name", name), "kind": kind,
            "pets": "yes" if pets else "no", "ada": "unknown",
            "lat": round(lat, 5), "lon": round(lon, 5), "address": address or None,
            "full_from": REPORTED_FULL.get(name),
            "source": "curated: hcfl.gov and WUSF, 7-9 Oct 2024; location from OpenStreetMap",
        })
    return out


def find_lodging(client: httpx.Client, city: dict) -> list[dict]:
    q = (f'[out:json][timeout:60];nwr["tourism"~"^(hotel|motel)$"](around:12000,{city["lat"]},{city["lon"]});'
         "out center tags;")
    out = []
    for el in overpass(client, q):
        tags = el.get("tags", {})
        if not tags.get("name"):
            continue
        lat, lon = _center(el)
        dog = tags.get("dog") or tags.get("pets") or tags.get("pets_allowed")
        out.append({
            "id": f"osm_{el['type']}_{el['id']}", "name": tags["name"], "type": tags["tourism"],
            "lat": round(lat, 5), "lon": round(lon, 5),
            "pets": {"yes": "yes", "leashed": "yes", "no": "no"}.get(dog, "unknown"),
            "wheelchair": {"yes": "yes", "limited": "unknown", "no": "no"}.get(tags.get("wheelchair"), "unknown"),
            "phone": tags.get("phone"), "website": tags.get("website"), "stars": tags.get("stars"),
        })
    # Prefer places with more known details, keep the list short
    out.sort(key=lambda p: (p["pets"] == "unknown", p["wheelchair"] == "unknown", p["phone"] is None, p["name"]))
    return out[:10]


def find_atms(client: httpx.Client, lat: float, lon: float, radius_m: int) -> list[dict]:
    q = f'[out:json][timeout:60];nwr["amenity"="atm"](around:{radius_m},{lat},{lon});out center tags;'
    out = []
    for el in overpass(client, q):
        tags = el.get("tags", {})
        a_lat, a_lon = _center(el)
        operator = tags.get("operator") or tags.get("brand") or tags.get("name")
        address = " ".join(x for x in (tags.get("addr:housenumber"), tags.get("addr:street"), tags.get("addr:city")) if x)
        out.append({
            "id": f"osm_atm_{el['type']}_{el['id']}", "name": f"ATM ({operator})" if operator else "ATM",
            "lat": round(a_lat, 5), "lon": round(a_lon, 5), "address": address or None,
            "hours": tags.get("opening_hours"),
            "accessibility": {"yes": "yes", "no": "no"}.get(tags.get("wheelchair"), "unknown"),
        })
    return out


def _read(name: str, default):
    path = OUT / name
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    previous = {d["id"]: d for d in _read("destinations.json", [])}  # rerunning keeps checked rates
    with httpx.Client(headers=UA, timeout=90, follow_redirects=True) as client:
        print("Destinations + GSA rates")
        destinations = []
        for name, state, lat, lon, corridor, hub in CITIES:
            rates = gsa_rates(client, name, state, previous.get(f"{slug(name)}_{state.lower()}"))
            destinations.append({"id": f"{slug(name)}_{state.lower()}", "name": f"{name}, {state}", "lat": lat, "lon": lon,
                                 "corridor": corridor, "hotel_hub": hub, "evac_zone_free": True, **rates})
            print(f"  {name}: ${rates['lodging_cents'] / 100:.0f} lodging, ${rates['meals_cents'] / 100:.0f} meals")
            time.sleep(1)
        (OUT / "destinations.json").write_text(json.dumps(destinations, indent=1), encoding="utf-8")

        print("Routes from 33602 (OSRM)")
        routes = _read("routes_33602.json", {}).get("routes", {})
        for d in destinations:
            if d["id"] in routes:
                continue
            try:
                routes[d["id"]] = osrm_route(client, d["lat"], d["lon"])
                print(f"  {d['name']}: {routes[d['id']]['distance_mi']} mi, {routes[d['id']]['drive_time_min_normal']} min")
            except Exception as exc:
                print(f"  {d['name']}: FAILED {exc}")
            time.sleep(1.2)
        (OUT / "routes_33602.json").write_text(json.dumps({"origin": ORIGIN, "routes": routes}), encoding="utf-8")

        print("Shelters (Overpass)")
        old = {s["id"]: s for s in _read("shelters_milton.json", {}).get("shelters", [])}
        try:
            shelters = find_shelters(client)
            shelters += [s for sid, s in old.items() if sid not in {x["id"] for x in shelters}]
        except Exception as exc:
            print(f"  FAILED {exc}; keeping the {len(old)} shelters found before")
            shelters = list(old.values())
        (OUT / "shelters_milton.json").write_text(json.dumps({"sources": SHELTER_SOURCES, "shelters": shelters}, indent=1),
                                                  encoding="utf-8")
        print(f"  {len(shelters)} of {len(SHELTERS)} located")

        print("Lodging (Overpass)")
        lodging = _read("lodging.json", {}).get("by_destination", {})
        by_name = {d["name"].split(",")[0]: d for d in destinations}
        for name in LODGING_CITIES:
            if lodging.get(by_name[name]["id"]):
                continue
            time.sleep(5)
            try:
                lodging[by_name[name]["id"]] = find_lodging(client, by_name[name])
                print(f"  {name}: {len(lodging[by_name[name]['id']])} places")
            except Exception as exc:
                print(f"  {name}: FAILED {exc}")
        print("ATMs (Overpass)")
        atms = _read("atms.json", {}).get("by_area", {})
        areas = [("origin_33602", ORIGIN["lat"], ORIGIN["lon"], 15000)] + [
            (by_name[n]["id"], by_name[n]["lat"], by_name[n]["lon"], 8000) for n in LODGING_CITIES]
        for area, a_lat, a_lon, radius in areas:
            if atms.get(area):
                continue
            time.sleep(5)
            try:
                atms[area] = find_atms(client, a_lat, a_lon, radius)
                print(f"  {area}: {len(atms[area])} ATMs")
            except Exception as exc:
                print(f"  {area}: FAILED {exc}")
        (OUT / "atms.json").write_text(json.dumps({"source": "OpenStreetMap snapshot", "attribution":
                                                   "© OpenStreetMap contributors", "by_area": atms}), encoding="utf-8")
        (OUT / "lodging.json").write_text(json.dumps({"source": "OpenStreetMap snapshot", "attribution":
                                                      "© OpenStreetMap contributors", "by_destination": lodging}, indent=1),
                                          encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
