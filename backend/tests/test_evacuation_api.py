"""/me/sensors, /me/evacuation and the evacuation map layers, over the Milton replay."""

API = "/api/v1"


def test_sensors_endpoint_and_history(client, auth):
    client.post(f"{API}/demo/start")
    client.post(f"{API}/demo/advance", json={"to_risk": "shelter"})
    res = client.get(f"{API}/me/sensors", headers=auth)
    sensors = res.json()
    ids = [s["id"] for s in sensors]
    assert ids[0] == "usgs_02301500"  # closest first: the Alafia gauge is 16 mi away
    tide = next(s for s in sensors if s["id"] == "coops_8726520")
    assert tide["status"] in ("normal", "watch", "warning") and tide["observed_at"] <= res.headers["X-Server-Time"]
    hist = client.get(f"{API}/me/sensors/coops_8726520/history?hours=24&metrics=surge_ft", headers=auth).json()
    assert hist and set(hist[0]["readings"]) <= {"surge_ft"}
    assert client.get(f"{API}/me/sensors/nope/history", headers=auth).json()["error"]["code"] == "sensor_not_found"


def test_no_guide_before_the_storm(client, auth):
    assert client.get(f"{API}/me/evacuation", headers=auth).json()["guide"] is None


def test_guide_for_maria_and_choosing_a_destination(client, auth):
    client.post(f"{API}/demo/start")
    client.post(f"{API}/demo/advance", json={"to_risk": "act"})
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
    client.post(f"{API}/demo/advance", json={"to_risk": "act"})
    res = client.post(f"{API}/me/evacuation/destination", headers=auth, json={"destination_id": "orlando_fl"})
    assert res.status_code == 409 and res.json()["error"]["code"] == "destination_not_safe"
    assert client.post(f"{API}/me/evacuation/destination", headers=auth,
                       json={"destination_id": "atlantis"}).status_code == 404


def test_atms_outside_the_cone_and_on_the_route_come_first(client, auth):
    assert client.get(f"{API}/me/atms", headers=auth).json()  # before the storm: nearby ATMs by distance
    client.post(f"{API}/demo/start")
    atms = client.get(f"{API}/me/atms", headers=auth).json()
    assert atms and all(a["source"] == "osm" for a in atms)
    keys = [(a["in_forecast_cone"], not a["on_evacuation_route"], a["distance_miles"]) for a in atms]
    assert keys == sorted(keys)
    layer = client.get(f"{API}/me/map", headers=auth).json()["layers"]["atms"]
    assert layer["features"] and layer["features"][0]["properties"]["source"] == "osm"


def test_second_persona_ruth_gets_shelter_and_transport_not_a_drive(client):
    res = client.post(f"{API}/demo/persona", json={"persona": "ruth"})
    assert res.status_code == 200, res.text
    h = {"X-User-Id": res.json()["id"]}
    client.post(f"{API}/demo/start")
    client.post(f"{API}/demo/advance", json={"to_risk": "prepare"})
    guide = client.get(f"{API}/me/evacuation", headers=h).json()
    assert guide["decision"]["action"] == "use_public_shelter"
    assert {"MOBILE_HOME", "NO_CAR", "POWER_OR_MEDICAL"} <= set(guide["decision"]["reason_codes"])
    assert guide["route"] is None and guide["shelters"][0]["kind"] == "special_needs"
    kinds = {c["kind"] for c in guide["advice_cards"]}
    assert {"no_car", "special_needs_shelter", "early_refill"} <= kinds
    plan = client.get(f"{API}/me/plan", headers=h).json()["plan"]
    assert plan and not any(l["label"].startswith(("Lodging", "Fuel")) for l in plan["budget"]["lines"])
