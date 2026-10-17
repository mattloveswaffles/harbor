"""ReplaySource over the committed Milton replay (data/replays/milton-2024, built by tools/fetch_replay.py)."""

from datetime import datetime, timedelta, timezone

import pytest

from harbor.config import Settings
from harbor.sources.forecast import list_replays, load_replay, parse_time

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
    assert datetime.fromisoformat(milton["end"].replace("Z", "+00:00")) > datetime(2024, 10, 10, tzinfo=timezone.utc)
