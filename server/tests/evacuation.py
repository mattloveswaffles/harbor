"""Evacuation: destinations, routes, shelters, lodging and the evacuation API."""

import json
from datetime import UTC, datetime
from pathlib import Path

import httpx

from harbor.engine.plan import Balances, PlanInputs, build_plan
from harbor.evac.destination import DATA, decide, load_destinations
from harbor.evac.guide import build_guide
from harbor.evac.household import Household, Pet, place_filter
from harbor.evac.lodging import plan_lodging
from harbor.evac.route import demo_route, maps_links, osrm_route
from harbor.evac.shelters import demo_shelters, rank
from tests.conftest import advance
from tests.households import make_household

UTC = UTC


REPLAY = Path(__file__).resolve().parents[1] / "data" / "replays" / "milton-2024"


TAMPA = (27.9506, -82.4572)


MARIA = Household(adults=2, children_ages=(7,), pets=(Pet("dog"),), evac_zone="A")


ETA = datetime(2024, 10, 9, 12, tzinfo=UTC)


def advisory(when: str):
    manifest = json.loads((REPLAY / "manifest.json").read_text(encoding="utf-8"))
    adv = [a for a in manifest["advisories"] if a["issued_at"] <= when][-1]
    g = json.loads((REPLAY / adv["file"]).read_text(encoding="utf-8"))
    cone = next(f for f in g["features"] if f["properties"]["layer"] == "cone")
    track = next(f for f in g["features"] if f["properties"].get("kind") == "forecast_line")
    cat = max(
        (f["properties"].get("category") or 0) for f in g["features"] if f["properties"].get("kind") == "forecast_point"
    )
    return cone, track, cat


def guide_at(when: str, household=MARIA, **kw):
    cone, track, cat = advisory(when)
    now = datetime.fromisoformat(when.replace("Z", "+00:00"))
    return build_guide(now, TAMPA, "33602", household, cone=cone, track=track, category=cat, ts_winds_eta=ETA, **kw)


def test_sunday_avoids_everywhere_inside_the_cone():
    g = guide_at("2024-10-06T15:02:00Z")["guide"]
    assert g["decision"]["action"] == "evacuate" and g["decision"]["tier"] == "B"
    assert "MAJOR_HURRICANE_IN_CONE" in g["decision"]["reason_codes"]
    names = [d["name"] for d in g["destinations"]]
    assert names[0] == "Valdosta, GA" and g["destinations"][0]["recommended"]
    assert not {"Orlando, FL", "Gainesville, FL", "Ocala, FL"} & set(names)
    assert any(d["tier"] == "A" for d in g["destinations"])  # a local option is still offered


def test_tuesday_cone_has_moved_and_gainesville_opens_up():
    names = [d["name"] for d in guide_at("2024-10-08T15:00:00Z")["guide"]["destinations"] if d["tier"] == "B"]
    assert "Gainesville, FL" in names


def test_route_leave_by_and_links():
    g = guide_at("2024-10-06T15:02:00Z")["guide"]
    r = g["route"]
    assert r["provider"] == "osrm" and r["distance_mi"] > 200
    assert r["drive_time_min_evac"] == r["drive_time_min_normal"] + min(round(r["drive_time_min_normal"] * 1.5), 300)
    assert r["steps"][0]["text"] and r["links"]["google"].startswith("https://www.google.com/maps/dir/?api=1")
    assert g["leave_by"] < "2024-10-09T12:00:00Z"


def test_lodging_for_a_family_with_a_dog():
    g = guide_at("2024-10-06T15:02:00Z")["guide"]
    lodging = g["lodging"]
    assert lodging["rooms"] == 1 and lodging["nights"] == 3
    assert lodging["options"] and all(o["pets"] in ("yes", "call_to_confirm") for o in lodging["options"])
    assert all(o["note"] == "Estimated cost. Call to confirm availability." for o in lodging["options"])
    assert "assumed" in lodging["estimate_source"]  # Valdosta's GSA rate wasn't checked yet, and says so


def test_shelters_near_home_respect_the_dog():
    g = guide_at("2024-10-06T15:02:00Z")["guide"]
    assert g["shelters"] and all(s["pets"] == "yes" for s in g["shelters"])
    assert all(s["kind"] == "general" for s in g["shelters"])


def test_special_needs_shelters_come_first_and_fill_up():
    needs = place_filter(Household(adults=1, oxygen=True))
    before = rank(demo_shelters(datetime(2024, 10, 8, tzinfo=UTC)), TAMPA, needs)
    after = rank(demo_shelters(datetime(2024, 10, 9, 13, tzinfo=UTC)), TAMPA, needs)
    assert before[0].kind == "special_needs"
    erwin = next(s for s in after if s.id == "hc_erwin_technical_college")
    assert erwin.status == "full" and after[-1].status == "full"


def test_no_car_means_shelter_and_transport_not_a_route():
    g = guide_at("2024-10-06T15:02:00Z", household=Household(adults=0, seniors=2, has_car=False))["guide"]
    assert g["decision"]["action"] == "use_public_shelter"
    assert g["route"] is None and g["lodging"] is None
    assert any(c["kind"] == "no_car" for c in g["advice_cards"])


def test_user_can_choose_another_destination():
    g = guide_at("2024-10-06T15:02:00Z", choose="tallahassee_fl")["guide"]
    assert g["chosen"] == "tallahassee_fl"
    assert next(d for d in g["destinations"] if d["id"] == "tallahassee_fl")["recommended"]


def test_map_layers_are_drawable_geojson():
    layers = guide_at("2024-10-06T15:02:00Z")["layers"]
    assert layers["route"]["features"][0]["geometry"]["type"] == "LineString"
    for name in ("destinations", "shelters", "lodging"):
        assert layers[name]["type"] == "FeatureCollection" and layers[name]["features"]
        assert layers[name]["features"][0]["geometry"]["type"] == "Point"


def test_guide_budget_feeds_the_plan_engine():
    out = guide_at("2024-10-06T15:02:00Z")
    plan = build_plan(
        PlanInputs(
            now=datetime(2024, 10, 6, 15, 2, tzinfo=UTC),
            cash_needed_by=datetime(2024, 10, 8, 18, tzinfo=UTC),
            lines=tuple(out["budget_lines"]),
            balances=Balances(42_000, 50_000),
            lots=(),
            prices_cents={},
        )
    )
    labels = [l.label for l in plan.lines]
    assert labels[0].startswith("Lodging: Valdosta") and labels[1].startswith("Fuel")
    assert plan.total_cents == sum(l.amount_cents for l in plan.lines)


def test_destinations_have_gsa_rates_and_say_when_unchecked():
    dests = {d.id: d for d in load_destinations()}
    assert dests["atlanta_ga"].lodging_cents == 18_200 and dests["gainesville_fl"].lodging_cents == 11_000
    rows = {r["id"]: r for r in json.loads((DATA / "destinations.json").read_text(encoding="utf-8"))}
    assert rows["atlanta_ga"]["rate_checked"] and rows["gainesville_fl"]["rate_checked"]
    assert all(r.get("rate_checked") or "assumed" in r["basis"] for r in rows.values())


def test_mobile_home_goes_regional_even_without_a_cone():
    d = decide(TAMPA, Household(adults=1, home_type="mobile"), route_for=lambda dest: demo_route("33602", dest.id))
    assert d.action == "evacuate" and d.tier == "B"


def test_quiet_forecast_offers_local_options_without_ordering_evacuation():
    d = decide(
        TAMPA, Household(adults=2, evac_zone="none"), category=1, route_for=lambda dest: demo_route("33602", dest.id)
    )
    assert d.action == "shelter_in_place"


def test_maps_links():
    links = maps_links(27.95, -82.46, 29.65, -82.32)
    assert "destination=29.6500%2C-82.3200" in links["google"] and links["apple"].startswith("https://maps.apple.com/?")


def test_live_osrm_parsing_with_a_fake_server():
    body = {
        "routes": [
            {
                "distance": 16093.44,
                "duration": 1200,
                "geometry": {"type": "LineString", "coordinates": [[0, 0], [1, 1]]},
                "legs": [
                    {
                        "steps": [
                            {"distance": 500, "maneuver": {"type": "depart"}, "name": "Main St"},
                            {"distance": 15000, "maneuver": {"type": "turn", "modifier": "left"}, "ref": "I-75 N"},
                            {"distance": 0, "maneuver": {"type": "arrive"}, "name": ""},
                        ]
                    }
                ],
            }
        ]
    }
    client = httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200, json=body)))
    r = osrm_route(client, (27.9, -82.4), (28.0, -82.3))
    assert r.distance_mi == 10.0 and r.drive_time_min_normal == 20
    assert [s["text"] for s in r.steps] == ["Start on Main St", "Turn left onto I-75 N", "Arrive at your destination"]


def test_unfiltered_lodging_lists_snapshot_places():
    gainesville = next(d for d in load_destinations() if d.id == "gainesville_fl")
    plan = plan_lodging(gainesville, TAMPA, nights=2, rooms=1, needs=place_filter(Household(adults=1)))
    assert plan.nightly_estimate_cents == 11_000 and plan.total_cents == 22_000 and plan.options


API = "/api/v1"


def test_sensors_endpoint(client, auth):
    client.post(f"{API}/demo/start")
    advance(client, to_risk="shelter")
    res = client.get(f"{API}/me/sensors", headers=auth)
    sensors = res.json()
    ids = [s["id"] for s in sensors]
    assert ids[0] == "usgs_02301500"  # closest first: the Alafia gauge is 16 mi away
    tide = next(s for s in sensors if s["id"] == "coops_8726520")
    assert tide["status"] in ("normal", "watch", "warning") and tide["observed_at"] <= res.headers["X-Server-Time"]


def test_no_guide_before_the_storm(client, auth):
    assert client.get(f"{API}/me/evacuation", headers=auth).json()["guide"] is None


def test_guide_for_maria_and_choosing_a_destination(client, auth):
    client.post(f"{API}/demo/start")
    advance(client, to_risk="act")
    guide = client.get(f"{API}/me/evacuation", headers=auth).json()
    assert guide["decision"]["action"] == "evacuate"
    assert guide["route"]["links"]["google"].startswith("https://www.google.com/maps/dir/")
    assert all(s["pets"] == "yes" for s in guide["shelters"])  # Maria has a dog
    other = next(d for d in guide["destinations"] if not d["recommended"])
    res = client.post(f"{API}/me/evacuation/destination", headers=auth, json={"destination_id": other["id"]})
    assert res.status_code == 200 and res.json()["chosen"] == other["id"]
    assert client.get(f"{API}/me/evacuation", headers=auth).json()["chosen"] == other["id"]


def test_destinations_inside_the_cone_are_refused(client, auth):
    client.post(f"{API}/demo/start")
    advance(client, to_risk="act")
    res = client.post(f"{API}/me/evacuation/destination", headers=auth, json={"destination_id": "orlando_fl"})
    assert res.status_code == 409 and res.json()["error"]["code"] == "destination_not_safe"
    assert (
        client.post(f"{API}/me/evacuation/destination", headers=auth, json={"destination_id": "atlantis"}).status_code
        == 404
    )


def test_atms_outside_the_cone_and_on_the_route_come_first(client, auth):
    assert client.get(f"{API}/me/atms", headers=auth).json()  # before the storm: nearby ATMs by distance
    client.post(f"{API}/demo/start")
    atms = client.get(f"{API}/me/atms", headers=auth).json()
    assert atms and all(a["source"] == "osm" for a in atms)
    keys = [(a["in_forecast_cone"], not a["on_evacuation_route"], a["distance_miles"]) for a in atms]
    assert keys == sorted(keys)
    layer = client.get(f"{API}/me/map", headers=auth).json()["layers"]["atms"]
    assert layer["features"] and layer["features"][0]["properties"]["source"] == "osm"


def test_ruth_gets_a_shelter_and_transport_not_a_drive(client):
    h = make_household(client, "ruth")["auth"]
    client.post(f"{API}/demo/start")  # Sarasota is at act from the replay start
    guide = client.get(f"{API}/me/evacuation", headers=h).json()
    assert guide["decision"]["action"] == "use_public_shelter"
    assert {"MOBILE_HOME", "NO_CAR", "POWER_OR_MEDICAL"} <= set(guide["decision"]["reason_codes"])
    assert guide["route"] is None and guide["shelters"][0]["kind"] == "special_needs"
    kinds = {c["kind"] for c in guide["advice_cards"]}
    assert {"no_car", "special_needs_shelter", "early_refill"} <= kinds
    plan = client.get(f"{API}/me/plan", headers=h).json()["plan"]
    assert plan and not any(l["label"].startswith(("Lodging", "Fuel")) for l in plan["budget"]["lines"])
