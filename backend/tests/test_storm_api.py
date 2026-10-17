"""/me/storm, /me/map, the demo clock routes and the scheduler tick, over the real Milton replay."""

import time

from fastapi.testclient import TestClient
from sqlmodel import Session, col, select

from harbor.main import create_app
from harbor.models import Event, User
from harbor.ticker import tick
from tests.conftest import make_settings

API = "/api/v1"


def events(app, user_id, types=None):
    with Session(app.state.engine) as s:
        q = select(Event).where(Event.user_id == user_id).order_by(col(Event.seq))
        rows = s.exec(q).all()
    return [e for e in rows if types is None or e.type in types]


def risk_changes(app, user_id):
    return [(e.data["to"], e.at.isoformat().replace("+00:00", "Z")) for e in events(app, user_id, {"risk_changed"})]


def test_demo_storms(client):
    rows = client.get(f"{API}/demo/storms").json()
    milton = next(r for r in rows if r["id"] == "milton-2024")
    assert milton["landfall_at"] == "2024-10-10T00:30:00Z" and milton["demo_zips"] == ["33602", "34236"]
    assert milton["start"] == "2024-10-06T03:00:00Z" and milton["advisories"] == 41


def test_storm_before_the_demo_starts(client, auth):
    body = client.get(f"{API}/me/storm", headers=auth).json()
    assert body["server_time"] == "2024-10-06T03:00:00Z"
    assert body["risk_level"] == "clear" and body["storm"] is None
    assert body["risk_reason"] == "No storm threatens your ZIP."
    assert body["at_your_zip"] == {
        "ts_wind_probability_5day": 0.0, "hurricane_wind_probability_5day": 0.0, "in_forecast_cone": False,
        "earliest_ts_winds_eta": None, "eta_source": None, "alerts": [],
    }
    layers = client.get(f"{API}/me/map", headers=auth).json()["layers"]
    assert layers["cone"] == {"type": "FeatureCollection", "features": []}
    assert layers["home"]["features"][0]["geometry"]["coordinates"] == [-82.45631, 27.953704]


def test_start_puts_maria_at_act_with_a_reason(client, auth, maria, app):
    res = client.post(f"{API}/demo/start", json={"storm": "milton-2024", "speed": 900})
    assert res.status_code == 200, res.text
    # Maria is at act from the first advisory, so Harbor makes her plan and the clock waits for approval.
    assert res.json() == {"running": False, "storm": "milton-2024", "now": "2024-10-06T03:00:00Z", "speed": 900,
                          "paused_reason": "awaiting_approval"}
    body = client.get(f"{API}/me/storm", headers=auth).json()
    assert body["risk_level"] == "act"
    assert body["risk_reason"] == "The chance of tropical-storm winds at your ZIP reached 68%."
    storm = body["storm"]
    assert storm["id"] == "al142024" and storm["name"] == "Milton" and storm["is_replay"] is True
    assert storm["advisory_number"] == "3" and storm["advisory_time"] == "2024-10-06T03:00:00Z"
    assert storm["next_advisory_time"] == "2024-10-06T06:00:00Z"
    assert storm["classification"] == "tropical_storm" and storm["category"] is None
    z = body["at_your_zip"]
    assert z["ts_wind_probability_5day"] == 0.68 and z["in_forecast_cone"] is True
    assert z["earliest_ts_winds_eta"] == "2024-10-09T03:00:00Z" and z["eta_source"] == "toa_kmz"
    feed = events(app, maria["id"])
    assert [e.type for e in feed] == ["advisory_issued", "risk_changed", "plan_created"]
    assert feed[1].message == "Risk raised to ACT: The chance of tropical-storm winds at your ZIP reached 68%."
    assert feed[1].data["from"] == "clear" and feed[1].data["to"] == "act"


def test_map_has_cone_and_track_after_start(client, auth):
    client.post(f"{API}/demo/start")
    body = client.get(f"{API}/me/map", headers=auth).json()
    layers = body["layers"]
    assert set(layers) == {"home", "cone", "track", "route", "destinations", "shelters", "lodging", "atms", "sensors"}
    assert layers["cone"]["features"][0]["properties"]["advisory"] == "3"
    kinds = {f["properties"]["kind"] for f in layers["track"]["features"]}
    assert kinds == {"line", "point"}
    # Maria starts the replay at act, so the evacuation layers are filled; ATMs come later.
    assert layers["route"]["features"][0]["geometry"]["type"] == "LineString"
    for name in ("destinations", "shelters", "lodging", "sensors"):
        assert layers[name]["features"], name
    assert {f["properties"]["id"] for f in layers["sensors"]["features"]} == {"coops_8726520", "usgs_02301500", "ndbc_42036"}
    assert layers["atms"]["features"]  # OpenStreetMap ATMs
    assert "NOAA NHC" in body["attribution"] and "USGS" in body["attribution"]


def test_advance_hours_records_each_advisory_at_its_time(client, maria, app):
    client.post(f"{API}/demo/start")
    res = client.post(f"{API}/demo/advance", json={"hours": 7})
    assert res.json()["now"] == "2024-10-06T10:00:00Z"
    adv = [(e.data["advisory"], e.at.isoformat()) for e in events(app, maria["id"], {"advisory_issued"})]
    assert adv == [("003", "2024-10-06T03:00:00+00:00"), ("003A", "2024-10-06T06:00:00+00:00"),
                   ("004", "2024-10-06T09:00:00+00:00")]


def test_advance_to_next_advisory(client):
    client.post(f"{API}/demo/start")
    assert client.post(f"{API}/demo/advance", json={"to": "next_advisory"}).json()["now"] == "2024-10-06T06:00:00Z"
    assert client.post(f"{API}/demo/advance", json={"to": "next_advisory"}).json()["now"] == "2024-10-06T09:00:00Z"


def test_advance_to_risk_walks_the_whole_storm(client, auth, maria, app):
    client.post(f"{API}/demo/start")
    res = client.post(f"{API}/demo/advance", json={"to_risk": "shelter"})
    assert res.status_code == 200, res.text
    assert res.json()["now"] == "2024-10-09T09:00:00Z"
    body = client.get(f"{API}/me/storm", headers=auth).json()
    assert body["risk_level"] == "shelter"
    assert {a["type"] for a in body["at_your_zip"]["alerts"]} == {"hurricane_warning", "storm_surge_warning"}
    assert body["at_your_zip"]["alerts"][0]["source"] == "iem"

    res = client.post(f"{API}/demo/advance", json={"to_risk": "recover"})
    assert res.json()["now"] == "2024-10-13T20:00:00Z"
    assert risk_changes(app, maria["id"]) == [
        ("act", "2024-10-06T03:00:00Z"), ("shelter", "2024-10-09T09:00:00Z"), ("recover", "2024-10-13T20:00:00Z"),
    ]
    # Every advisory crossed on the way was recorded once, in order.
    seen = [e.data["advisory"] for e in events(app, maria["id"], {"advisory_issued"})]
    # The replay now runs past the last advisory (023) into the sensor aftermath.
    assert seen[0] == "003" and seen[-1] == "023" and len(seen) == len(set(seen)) == 39


def test_advance_to_the_current_level_is_a_no_op(client, maria):
    client.post(f"{API}/demo/start")
    assert client.post(f"{API}/demo/advance", json={"to_risk": "act"}).json()["now"] == "2024-10-06T03:00:00Z"


def test_advance_to_an_unreachable_level(client, maria):
    client.post(f"{API}/demo/start")
    res = client.post(f"{API}/demo/advance", json={"to_risk": "prepare"})  # Tampa skips prepare
    assert res.status_code == 409 and res.json()["error"]["code"] == "risk_level_not_reached"
    assert client.get(f"{API}/demo/clock").json()["now"] == "2024-10-06T03:00:00Z"


def test_advance_needs_exactly_one_target(client):
    client.post(f"{API}/demo/start")
    for body in ({}, {"hours": 1, "to": "next_advisory"}):
        res = client.post(f"{API}/demo/advance", json=body)
        assert res.status_code == 422 and res.json()["error"]["code"] == "validation_error"
    assert client.post(f"{API}/demo/advance", json={"hours": -1}).status_code == 422


def test_no_more_advisories(client):
    client.post(f"{API}/demo/start")
    client.post(f"{API}/demo/advance", json={"hours": 150})
    res = client.post(f"{API}/demo/advance", json={"to": "next_advisory"})
    assert res.status_code == 409 and res.json()["error"]["code"] == "no_more_advisories"


def test_clock_routes_need_a_started_demo(client):
    for path in ("/demo/advance", "/demo/pause", "/demo/resume"):
        res = client.post(f"{API}{path}", json={"hours": 1})
        assert res.status_code == 409 and res.json()["error"]["code"] == "demo_not_started"


def test_unknown_storm(client):
    res = client.post(f"{API}/demo/start", json={"storm": "andrew-1992"})
    assert res.status_code == 404 and res.json()["error"]["code"] == "storm_not_found"


def test_pause_and_resume(client, timer):
    client.post(f"{API}/demo/start", json={"speed": 3600})
    paused = client.post(f"{API}/demo/pause").json()
    assert paused["running"] is False and paused["paused_reason"] == "manual"
    timer.t += 10
    assert client.get(f"{API}/demo/clock").json()["now"] == "2024-10-06T03:00:00Z"
    # Advancing while paused keeps the clock paused.
    assert client.post(f"{API}/demo/advance", json={"hours": 1}).json()["running"] is False
    resumed = client.post(f"{API}/demo/resume").json()
    assert resumed["running"] is True and resumed["paused_reason"] is None
    timer.t += 1
    assert client.get(f"{API}/demo/clock").json()["now"] == "2024-10-06T05:00:00Z"


def test_restart_resets_risk_but_not_the_feed(client, auth, maria, app):
    client.post(f"{API}/demo/start")
    client.post(f"{API}/demo/advance", json={"to_risk": "shelter"})
    client.post(f"{API}/demo/start")
    assert client.get(f"{API}/me/storm", headers=auth).json()["risk_level"] == "act"
    assert [lvl for lvl, _ in risk_changes(app, maria["id"])] == ["act", "shelter", "act"]


def test_reset_puts_everyone_back_to_clear(client, auth):
    client.post(f"{API}/demo/start")
    client.post(f"{API}/demo/reset")
    body = client.get(f"{API}/me/storm", headers=auth).json()
    assert body["risk_level"] == "clear" and body["storm"] is None


def test_tick_catches_up_after_real_time_passes(client, maria, app, clock, timer):
    clock.start("milton-2024", speed=3600)
    tick(app)
    clock.resume()  # the new plan paused the clock for approval; carry on without approving
    timer.t += 12  # 12 storm hours
    tick(app)
    seen = [e.data["advisory"] for e in events(app, maria["id"], {"advisory_issued"})]
    assert seen == ["003", "003A", "004", "004A", "005"]


def test_tick_is_idempotent(client, maria, app, clock):
    clock.start("milton-2024")
    assert tick(app) == 2
    assert tick(app) == 0
    with Session(app.state.engine) as s:
        assert s.get(User, maria["id"]).risk_level == "act"


def test_new_demo_routes_are_off_in_live_mode(tmp_path, bank):
    app = create_app(make_settings(tmp_path, harbor_mode="live"), bank=bank)
    with TestClient(app) as c:
        for method, path in (("get", "/demo/storms"), ("post", "/demo/start"), ("post", "/demo/advance"),
                             ("post", "/demo/pause"), ("post", "/demo/resume")):
            res = getattr(c, method)(f"{API}{path}")
            assert res.status_code == 403 and res.json()["error"]["code"] == "demo_mode_only"


def test_scheduler_runs_the_tick(tmp_path, bank, clock):
    app = create_app(make_settings(tmp_path, scheduler_enabled=True, tick_seconds=0.05), clock=clock, bank=bank)
    with TestClient(app) as c:
        user_id = c.post(f"{API}/demo/persona").json()["id"]
        clock.start("milton-2024")  # straight on the clock, not via /demo/start, so only the scheduler ticks
        deadline = time.monotonic() + 5
        level = "clear"
        while time.monotonic() < deadline and level == "clear":
            time.sleep(0.05)
            level = c.get(f"{API}/me/storm", headers={"X-User-Id": user_id}).json()["risk_level"]
        assert level == "act"
