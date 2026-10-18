"""Storm: NHC forecasts, the Milton replay, sensors, risk levels and the storm API."""

import time
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, col, select

from harbor.config import Settings
from harbor.engine.risk import Level, RiskInputs, next_level
from harbor.main import create_app
from harbor.models import Event, User
from harbor.sources.forecast import list_replays, load_replay, parse_time
from harbor.sources.sensors import SensorSource, Series, Station, recovery_gate, status_of
from harbor.ticker import evaluate, replay_end, steps_between, tick
from tests.conftest import make_settings
from tests.households import make_household

TAMPA = (27.953704, -82.45631)  # ZIP 33602, Maria


def at(s: str) -> datetime:
    return parse_time(s)


@pytest.fixture(scope="module")
def milton():
    src = load_replay(Settings(_env_file=None).replay_dir, "milton-2024")
    assert src is not None, "run tools/fetch_replay.py to build the replay"
    return src


def test_manifest_times_come_from_the_archive(milton):
    advs = milton.advisories
    assert len(advs) == 41
    assert [a.issued_at for a in advs] == sorted(a.issued_at for a in advs)
    assert len({a.issued_at for a in advs}) == 41
    assert advs[0].adv == "001" and advs[0].issued_at == at("2024-10-05T15:00:00Z")
    by_adv = {a.adv: a for a in advs}
    # DESIGN.md checked advisory 15 against the TCM: 2100 UTC TUE OCT 08 2024.
    assert by_adv["015"].issued_at == at("2024-10-08T21:00:00Z")
    assert by_adv["015A"].issued_at == at("2024-10-09T00:00:00Z") and by_adv["015A"].intermediate
    assert by_adv["015"].classification == "hurricane" and by_adv["015"].category == 5
    assert by_adv["023"].classification == "post_tropical" and by_adv["023"].category is None
    # Special advisory 9 was off the usual cycle; it reuses advisory 8's wind probabilities.
    assert by_adv["009"].wsp == by_adv["008"].wsp
    # Intermediate advisories reuse the last full advisory's products.
    assert by_adv["015A"].wsp == by_adv["015"].wsp and by_adv["015A"].products_from == "015"
    assert milton.manifest["landfall_at"] == "2024-10-10T00:30:00Z"
    assert all(a["issued_from"] == "tcm" for a in milton.manifest["advisories"] if not a["intermediate"])


def test_positions_keep_their_decimals(milton):
    adv = milton.advisory_at(at("2024-10-08T21:00:00Z"))
    assert adv.lat != round(adv.lat) or adv.lon != round(adv.lon)
    assert 20 < adv.lat < 26 and -90 < adv.lon < -83


def test_advisory_at_never_sees_the_future(milton):
    assert milton.advisory_at(at("2024-10-05T14:59:59Z")) is None
    assert milton.advisory_at(at("2024-10-08T20:59:59Z")).adv == "014A"
    assert milton.advisory_at(at("2024-10-08T21:00:00Z")).adv == "015"
    assert milton.next_advisory_time(at("2024-10-08T21:00:00Z")) == at("2024-10-09T00:00:00Z")
    assert milton.advisory_at(milton.end) is None
    assert milton.next_advisory_time(at("2024-10-10T21:00:00Z")) is None


def test_tampa_exposure_at_advisory_15(milton):
    exp = milton.exposure(*TAMPA, "33602", at("2024-10-08T21:30:00Z"))
    assert exp.advisory.adv == "015"
    assert 0.8 <= exp.p34 <= 0.9 and 0.2 <= exp.p64 <= 0.4
    assert exp.in_cone is True
    assert exp.eta == at("2024-10-09T21:00:00Z") and exp.eta_source == "toa_kmz"
    assert {a["type"] for a in exp.alerts} == {"hurricane_warning", "storm_surge_warning"}


def test_tampa_band_check_from_the_design_notes(milton):
    # DESIGN.md: in the 2024100812 file Tampa falls in the 80-90% band (advisory 14, 15Z).
    exp = milton.exposure(*TAMPA, "33602", at("2024-10-08T15:00:00Z"))
    assert milton.advisory_at(at("2024-10-08T15:00:00Z")).wsp == "wsp/2024100812.json"
    assert 0.8 <= exp.p34 <= 0.9


def test_alerts_follow_the_iem_archive(milton):
    def kinds(t):
        return {a["type"] for a in milton.alerts("33602", at(t))}

    assert kinds("2024-10-07T09:32:00Z") == set()
    assert kinds("2024-10-07T09:33:00Z") == {"hurricane_watch", "storm_surge_watch"}
    assert kinds("2024-10-07T21:07:00Z") == {"hurricane_warning", "storm_surge_warning"}
    assert "extreme_wind_warning" in kinds("2024-10-09T23:00:00Z")
    assert kinds("2024-10-10T08:56:00Z") == {"hurricane_warning", "storm_surge_warning"}
    assert kinds("2024-10-10T08:57:00Z") == set()
    assert milton.alerts("32601", at("2024-10-09T00:00:00Z")) == []  # no archived alerts for other ZIPs


def test_eta_is_null_far_away_and_now_once_winds_arrive(milton):
    far = milton.exposure(30.44, -84.28, None, at("2024-10-06T03:00:00Z"))  # Tallahassee, early on
    assert far.p34 < 0.5
    landfall = milton.exposure(*TAMPA, "33602", at("2024-10-10T01:00:00Z"))
    assert landfall.eta <= at("2024-10-10T01:00:00Z")


def test_points_outside_florida_still_work(milton):
    exp = milton.exposure(33.749, -84.388, None, at("2024-10-09T00:00:00Z"))  # Atlanta
    assert 0.0 <= exp.p34 <= 1.0 and exp.in_cone is False


def test_storm_passed_after_landfall(milton):
    assert milton.storm_passed(*TAMPA, at("2024-10-08T21:00:00Z")) is False
    assert milton.storm_passed(*TAMPA, at("2024-10-10T09:00:00Z")) is True


def test_boundaries_include_advisories_and_alert_edges(milton):
    b = milton.boundaries(at("2024-10-07T09:00:00Z"), at("2024-10-07T22:00:00Z"))
    assert at("2024-10-07T09:33:00Z") in b and at("2024-10-07T21:07:00Z") in b
    assert at("2024-10-07T12:00:00Z") in b and at("2024-10-07T09:00:00Z") not in b  # (after, until]
    assert b == sorted(b)


def test_map_layers(milton):
    t = at("2024-10-08T21:00:00Z")
    cone = milton.cone_layer(t)
    assert len(cone["features"]) == 1
    assert cone["features"][0]["geometry"]["type"] in ("Polygon", "MultiPolygon")
    assert cone["features"][0]["properties"]["advisory"] == "15"
    track = milton.track_layer(t)
    kinds = [f["properties"]["kind"] for f in track["features"]]
    assert kinds.count("line") == 1 and kinds.count("point") >= 5
    points = [f["properties"] for f in track["features"] if f["properties"]["kind"] == "point"]
    assert points[0]["valid_time"] == "2024-10-08T18:00:00Z" and points[0]["intensity_kt"] == 145
    assert [p["valid_time"] for p in points] == sorted(p["valid_time"] for p in points)
    assert milton.cone_layer(at("2024-10-01T00:00:00Z")) == {"type": "FeatureCollection", "features": []}


def test_toa_times_increase_and_follow_publication(milton):
    for adv in milton.advisories:
        if adv.intermediate or not adv.toa:
            continue
        toa = milton._toa(adv.toa)
        times = [t for t, _ in toa.lines]
        assert times == sorted(times) and len(set(times)) == len(times)
        assert times[0] >= toa.published_at - timedelta(hours=1)
        assert times[-1] - toa.published_at <= timedelta(days=6)


def test_list_replays():
    rows = list_replays(Settings(_env_file=None).replay_dir)
    milton = next(r for r in rows if r["id"] == "milton-2024")
    assert milton["name"] == "Milton" and milton["year"] == 2024 and milton["demo_zips"][0] == "33602"
    assert milton["start"] == "2024-10-06T03:00:00Z" and milton["advisories"] == 41
    assert datetime.fromisoformat(milton["end"].replace("Z", "+00:00")) > datetime(2024, 10, 10, tzinfo=UTC)


ORDERED = ["monitor", "prepare", "act", "shelter", "recover"]


def run(milton, lat, lon, zip_code, start=None):
    """Every level change from `start` (default: the replay start) to after the replay ends."""
    start = start or milton.start
    level, changes = Level.clear, []
    for t in steps_between(milton, start - timedelta(seconds=1), replay_end(milton)):
        decision, _ = evaluate(milton, level, lat, lon, zip_code, t)
        if decision.changed:
            changes.append((decision.level.value, t))
        level = decision.level
    return changes


def first_entries_in_order(changes) -> bool:
    firsts = []
    for level, _ in changes:
        if level not in firsts:
            firsts.append(level)
    ranked = [ORDERED.index(x) for x in firsts if x in ORDERED]
    return ranked == sorted(ranked)


def test_maria_in_tampa(milton):
    changes = run(milton, 27.953704, -82.45631, "33602")
    assert changes == [
        ("act", parse_time("2024-10-06T03:00:00Z")),  # 68% wind chance at the replay start
        ("shelter", parse_time("2024-10-09T09:00:00Z")),  # hurricane warning + winds due within 12 h
        # The hurricane warning ends 10-10 08:57 (IEM), but the Alafia River is in major flood until
        # 10-13; the sensor recovery gate opens once it is below major and falling for 6 h.
        ("recover", parse_time("2024-10-13T20:00:00Z")),
    ]
    assert first_entries_in_order(changes)


def test_sarasota(milton):
    changes = run(milton, 27.325788, -82.559997, "34236")
    assert [level for level, _ in changes] == ["act", "shelter", "recover"]
    assert first_entries_in_order(changes)
    # Landfall was at Siesta Key, Sarasota County: shelter comes before it and recover after.
    landfall = parse_time(milton.manifest["landfall_at"])
    assert changes[1][1] < landfall < changes[2][1]


def test_shelter_comes_after_act_and_before_landfall(milton):
    changes = dict(run(milton, 27.953704, -82.45631, "33602"))
    landfall = parse_time(milton.manifest["landfall_at"])
    assert changes["act"] < changes["shelter"] < landfall < changes["recover"]


@pytest.mark.parametrize(
    ("zip_code", "lat", "lon"),
    [
        ("32060", 30.27, -82.97),  # Live Oak
        ("32046", 30.70, -81.92),  # Hilliard
    ],
)
def test_inland_north_florida_climbs_the_whole_ladder(milton, zip_code, lat, lon):
    # From before advisory 1, so the first advisory's numbers count.
    changes = run(milton, lat, lon, None, start=milton.advisories[0].issued_at - timedelta(hours=1))
    levels = [lvl for lvl, _ in changes]
    assert levels[:2] == ["monitor", "prepare"]
    first = dict(reversed(changes))
    assert first["monitor"] < first["prepare"] < first["act"]


@pytest.mark.parametrize(
    ("zip_code", "lat", "lon"),
    [
        ("33602", 27.953704, -82.45631),
        ("34236", 27.325788, -82.559997),
        ("33701", 27.77, -82.64),  # St. Petersburg
        ("33901", 26.62, -81.87),  # Fort Myers
        ("32801", 28.54, -81.38),  # Orlando
        ("32202", 30.33, -81.66),  # Jacksonville
        ("32301", 30.44, -84.28),  # Tallahassee
        ("33131", 25.77, -80.19),  # Miami
    ],
)
def test_levels_never_go_backwards_out_of_shelter(milton, zip_code, lat, lon):
    changes = run(milton, lat, lon, zip_code)
    levels = [lvl for lvl, _ in changes]
    if "shelter" in levels:
        assert levels[levels.index("shelter") + 1 :] in ([], ["recover"])
    times = [t for _, t in changes]
    assert times == sorted(times)


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
        "ts_wind_probability_5day": 0.0,
        "hurricane_wind_probability_5day": 0.0,
        "in_forecast_cone": False,
        "earliest_ts_winds_eta": None,
        "eta_source": None,
        "alerts": [],
    }
    layers = client.get(f"{API}/me/map", headers=auth).json()["layers"]
    assert layers["cone"] == {"type": "FeatureCollection", "features": []}
    assert layers["home"]["features"][0]["geometry"]["coordinates"] == [-82.45631, 27.953704]


def test_start_puts_maria_at_act_with_a_reason(client, auth, maria, app):
    res = client.post(f"{API}/demo/start", json={"storm": "milton-2024", "speed": 900})
    assert res.status_code == 200, res.text
    # Maria is at act from the first advisory, so Harbor makes her plan and the clock waits for approval.
    assert res.json() == {
        "running": False,
        "storm": "milton-2024",
        "now": "2024-10-06T03:00:00Z",
        "speed": 900,
        "paused_reason": "awaiting_approval",
    }
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
    feed = [e for e in events(app, maria["id"]) if e.type != "connection_added"]  # the storm's own events
    assert [e.type for e in feed] == ["advisory_issued", "risk_changed", "plan_created"]
    assert feed[1].message == "Risk raised to ACT: The chance of tropical-storm winds at your ZIP reached 68%."
    assert feed[1].data["from"] == "clear" and feed[1].data["to"] == "act"


def test_map_has_cone_and_track_after_start(client, auth):
    client.post(f"{API}/demo/start")
    body = client.get(f"{API}/me/map", headers=auth).json()
    layers = body["layers"]
    assert set(layers) == {
        "home",
        "cone",
        "track",
        "route",
        "route_options",
        "destinations",
        "shelters",
        "lodging",
        "atms",
        "sensors",
    }
    assert layers["cone"]["features"][0]["properties"]["advisory"] == "3"
    kinds = {f["properties"]["kind"] for f in layers["track"]["features"]}
    assert kinds == {"line", "point"}
    # Maria starts the replay at act, so the evacuation layers are filled; ATMs come later.
    assert layers["route"]["features"][0]["geometry"]["type"] == "LineString"
    for name in ("destinations", "shelters", "lodging", "sensors"):
        assert layers[name]["features"], name
    assert {f["properties"]["id"] for f in layers["sensors"]["features"]} == {
        "coops_8726520",
        "usgs_02301500",
        "ndbc_42036",
    }
    assert layers["atms"]["features"]  # OpenStreetMap ATMs
    assert "NOAA NHC" in body["attribution"] and "USGS" in body["attribution"]


def test_advance_hours_records_each_advisory_at_its_time(client, maria, app):
    client.post(f"{API}/demo/start")
    res = client.post(f"{API}/demo/advance", json={"hours": 7})
    assert res.json()["now"] == "2024-10-06T10:00:00Z"
    adv = [(e.data["advisory"], e.at.isoformat()) for e in events(app, maria["id"], {"advisory_issued"})]
    assert adv == [
        ("003", "2024-10-06T03:00:00+00:00"),
        ("003A", "2024-10-06T06:00:00+00:00"),
        ("004", "2024-10-06T09:00:00+00:00"),
    ]


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
        ("act", "2024-10-06T03:00:00Z"),
        ("shelter", "2024-10-09T09:00:00Z"),
        ("recover", "2024-10-13T20:00:00Z"),
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
        for method, path in (
            ("get", "/demo/storms"),
            ("post", "/demo/start"),
            ("post", "/demo/advance"),
            ("post", "/demo/pause"),
            ("post", "/demo/resume"),
        ):
            res = getattr(c, method)(f"{API}{path}")
            assert res.status_code == 403 and res.json()["error"]["code"] == "demo_mode_only"


def test_scheduler_runs_the_tick(tmp_path, bank, clock):
    app = create_app(make_settings(tmp_path, scheduler_enabled=True, tick_seconds=0.05), clock=clock, bank=bank)
    with TestClient(app) as c:
        user_id = make_household(c, "maria")["id"]
        clock.start("milton-2024")  # straight on the clock, not via /demo/start, so only the scheduler ticks
        deadline = time.monotonic() + 5
        level = "clear"
        while time.monotonic() < deadline and level == "clear":
            time.sleep(0.05)
            level = c.get(f"{API}/me/storm", headers={"X-User-Id": user_id}).json()["risk_level"]
        assert level == "act"


storm = {"storm_active": True}


@pytest.mark.parametrize(
    ("current", "inputs", "expected"),
    [
        (Level.clear, RiskInputs(), Level.clear),
        (Level.clear, RiskInputs(**storm, p34=0.06), Level.monitor),
        (Level.clear, RiskInputs(**storm, p34=0.02, in_cone=True), Level.monitor),
        (Level.monitor, RiskInputs(**storm, p34=0.23), Level.prepare),
        (Level.monitor, RiskInputs(**storm, p34=0.08, sensor_flag=True), Level.prepare),
        (Level.prepare, RiskInputs(**storm, p34=0.55), Level.act),
        (Level.prepare, RiskInputs(**storm, p34=0.40, alerts=frozenset({"hurricane_watch"})), Level.act),
        (Level.clear, RiskInputs(**storm, p34=0.70), Level.act),  # escalation can jump levels
        (
            Level.act,
            RiskInputs(**storm, p34=0.9, alerts=frozenset({"hurricane_warning"}), ts_winds_eta_hours=10),
            Level.shelter,
        ),
        (Level.act, RiskInputs(**storm, p34=0.9, sustained_wind_mph=41), Level.shelter),
        # A warning still 30 h out is act, not shelter.
        (
            Level.act,
            RiskInputs(**storm, p34=0.9, alerts=frozenset({"hurricane_warning"}), ts_winds_eta_hours=30),
            Level.act,
        ),
    ],
)
def test_escalation(current, inputs, expected):
    assert next_level(current, inputs).level == expected


def test_strong_wind_without_a_storm_is_ignored():
    assert next_level(Level.clear, RiskInputs(sustained_wind_mph=45)).level == Level.clear


def test_hysteresis_keeps_prepare_through_a_small_dip():
    d = next_level(Level.prepare, RiskInputs(**storm, p34=0.15))
    assert d.level == Level.prepare and not d.changed


def test_storm_turns_away_stands_down_to_monitor():
    d = next_level(Level.act, RiskInputs(**storm, p34=0.06))
    assert d.level == Level.monitor and d.changed
    assert "turned away" in d.reason


def test_storm_gone_entirely_goes_to_clear():
    assert next_level(Level.prepare, RiskInputs()).level == Level.clear


def test_recovery_hold_when_alerts_end_but_rivers_still_rising():
    d = next_level(Level.shelter, RiskInputs(storm_passed=True, sensors_all_clear=False))
    assert d.level == Level.shelter
    assert d.recovery_hold is True
    assert "sensors" in d.reason


def test_recover_once_sensors_give_all_clear():
    d = next_level(Level.shelter, RiskInputs(storm_passed=True, sensors_all_clear=True))
    assert d.level == Level.recover and d.changed


def test_shelter_never_drops_while_alerts_are_in_force():
    d = next_level(Level.shelter, RiskInputs(alerts=frozenset({"tropical_storm_warning"}), sensors_all_clear=True))
    assert d.level == Level.shelter


def test_storm_that_passed_without_shelter_still_goes_through_the_gate():
    held = next_level(Level.act, RiskInputs(storm_passed=True))
    assert held.level == Level.act and held.recovery_hold
    assert next_level(Level.act, RiskInputs(storm_passed=True, sensors_all_clear=True)).level == Level.recover


def test_recover_to_clear_after_restore():
    assert next_level(Level.recover, RiskInputs()).level == Level.recover
    assert next_level(Level.recover, RiskInputs(restore_done=True)).level == Level.clear


def test_milton_style_sequence():
    """Walks a Milton-like week and checks the levels come in order."""
    steps = [
        RiskInputs(**storm, p34=0.07),
        RiskInputs(**storm, p34=0.23, in_cone=True),
        RiskInputs(**storm, p34=0.45, in_cone=True),
        RiskInputs(**storm, p34=0.80, in_cone=True, alerts=frozenset({"hurricane_watch"})),
        RiskInputs(**storm, p34=0.95, in_cone=True, alerts=frozenset({"hurricane_warning"}), ts_winds_eta_hours=8),
        RiskInputs(storm_passed=True, sensors_all_clear=False),  # alerts over, Alafia still rising
        RiskInputs(storm_passed=True, sensors_all_clear=True),
        RiskInputs(restore_done=True),
    ]
    level, seen = Level.clear, []
    for x in steps:
        level = next_level(level, x).level
        seen.append(level)
    assert seen == [
        Level.monitor,
        Level.prepare,
        Level.prepare,
        Level.act,
        Level.shelter,
        Level.shelter,
        Level.recover,
        Level.clear,
    ]


def test_reasons_mention_the_number():
    assert "23%" in next_level(Level.monitor, RiskInputs(**storm, p34=0.23)).reason


UTC = UTC


GAUGE_HOME = (27.9506, -82.4572)


src = SensorSource()


def utc(*args) -> datetime:
    return datetime(*args, tzinfo=UTC)


def reading(station_id: str, now: datetime):
    return next(r for r in src.readings(now, *GAUGE_HOME) if r.station.id == station_id)


def test_all_three_sensors_are_near_tampa():
    ids = [r.station.id for r in src.readings(utc(2024, 10, 7, 12), *GAUGE_HOME)]
    assert set(ids) == {"coops_8726520", "usgs_02301500", "ndbc_42036"}
    assert reading("usgs_02301500", utc(2024, 10, 7, 12)).distance_miles == 16


def test_calm_before_the_storm():
    facts = src.risk_facts(utc(2024, 10, 7, 12), *GAUGE_HOME)
    assert facts["sensor_flag"] is False
    assert facts["sustained_wind_mph"] < 39


def test_reverse_surge_warning_at_st_pete():
    r = reading("coops_8726520", utc(2024, 10, 10, 2, 30))
    assert r.status == "warning"
    assert r.readings["surge_ft"] < -2
    assert "bay floor" in r.status_reason


def test_tropical_storm_winds_trigger_the_shelter_freeze():
    facts = src.risk_facts(utc(2024, 10, 9, 23), *GAUGE_HOME)
    assert facts["sustained_wind_mph"] >= 39
    d = next_level(Level.act, RiskInputs(storm_active=True, p34=0.9, sustained_wind_mph=facts["sustained_wind_mph"]))
    assert d.level == Level.shelter


def test_alafia_river_crest_is_major_flood():
    r = reading("usgs_02301500", utc(2024, 10, 11, 14))
    assert r.readings["stage_ft"] == 24.36
    assert r.flood_category == "major" and r.status == "warning"
    assert r.to_api()["flood_stages"] == {"action": 11.0, "minor": 13.0, "moderate": 16.0, "major": 19.0}


def test_recovery_hold_after_nhc_alerts_end():
    # NHC alerts ended around 2024-10-10T09Z, but the river was still rising.
    facts = src.risk_facts(utc(2024, 10, 10, 9), *GAUGE_HOME)
    assert facts["sensors_all_clear"] is False
    assert "Alafia" in facts["all_clear_reason"]
    d = next_level(Level.shelter, RiskInputs(storm_passed=True, sensors_all_clear=facts["sensors_all_clear"]))
    assert d.level == Level.shelter and d.recovery_hold


def test_still_held_at_the_crest_then_clear_on_sunday_evening():
    assert src.risk_facts(utc(2024, 10, 11, 14), *GAUGE_HOME)["sensors_all_clear"] is False
    assert src.risk_facts(utc(2024, 10, 13, 12), *GAUGE_HOME)["sensors_all_clear"] is False
    assert src.risk_facts(utc(2024, 10, 13, 20), *GAUGE_HOME)["sensors_all_clear"] is True


def test_replay_never_sees_the_future():
    r = reading("usgs_02301500", utc(2024, 10, 10, 9))
    assert r.observed_at <= utc(2024, 10, 10, 9)


def test_stale_data_is_never_all_clear():
    station = Station("t", "noaa_tide", "Test gauge", 27.8, -82.6, "test")
    rows = [
        {"t": "2024-10-10T00:00:00Z", "water_level_ft": 1.0, "predicted_ft": 1.0, "surge_ft": 0.0, "pressure_mb": 1012}
    ]
    s = Series(station, rows)
    later = utc(2024, 10, 10, 3)
    assert status_of(s, later).stale
    clear, reason = recovery_gate([s], later)
    assert clear is False and "no fresh reading" in reason


def test_history_for_charts():
    rows = src.history("coops_8726520", utc(2024, 10, 10, 12), hours=48, metrics=["surge_ft", "predicted_ft"])
    assert 0 < len(rows) <= 480
    assert set(rows[0]["readings"]) <= {"surge_ft", "predicted_ft"}
    assert rows[-1]["observed_at"] <= "2024-10-10T12:00:00Z"
    assert src.history("nope", utc(2024, 10, 10, 12)) == []
