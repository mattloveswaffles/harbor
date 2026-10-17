"""The whole Milton manifest through engine.risk (DESIGN.md §1.8: "Milton risk levels come out in the
right order").

What the real archive shows: Milton's first advisory (2024-10-05 15Z) already gave Tampa a 50%
chance of tropical-storm winds, and 68% by the replay start, so Maria goes straight from clear to
act; monitor and prepare never happen for 33602 or 34236. Inland North Florida ZIPs do climb the
full monitor -> prepare -> act ladder. These tests pin both.
"""

from datetime import timedelta

import pytest

from harbor.config import Settings
from harbor.engine.risk import Level
from harbor.sources.forecast import load_replay, parse_time
from harbor.ticker import evaluate, replay_end, steps_between

ORDERED = ["monitor", "prepare", "act", "shelter", "recover"]


@pytest.fixture(scope="module")
def milton():
    return load_replay(Settings(_env_file=None).replay_dir, "milton-2024")


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
        ("act", parse_time("2024-10-06T03:00:00Z")),       # 68% wind chance at the replay start
        ("shelter", parse_time("2024-10-09T09:00:00Z")),   # hurricane warning + winds due within 12 h
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
    changes = dict((lvl, t) for lvl, t in run(milton, 27.953704, -82.45631, "33602"))
    landfall = parse_time(milton.manifest["landfall_at"])
    assert changes["act"] < changes["shelter"] < landfall < changes["recover"]


@pytest.mark.parametrize("zip_code,lat,lon", [
    ("32060", 30.27, -82.97),   # Live Oak
    ("32046", 30.70, -81.92),   # Hilliard
])
def test_inland_north_florida_climbs_the_whole_ladder(milton, zip_code, lat, lon):
    # From before advisory 1, so the first advisory's numbers count.
    changes = run(milton, lat, lon, None, start=milton.advisories[0].issued_at - timedelta(hours=1))
    levels = [lvl for lvl, _ in changes]
    assert levels[:2] == ["monitor", "prepare"]
    first = {lvl: t for lvl, t in reversed(changes)}
    assert first["monitor"] < first["prepare"] < first["act"]


@pytest.mark.parametrize("zip_code,lat,lon", [
    ("33602", 27.953704, -82.45631),
    ("34236", 27.325788, -82.559997),
    ("33701", 27.77, -82.64),   # St. Petersburg
    ("33901", 26.62, -81.87),   # Fort Myers
    ("32801", 28.54, -81.38),   # Orlando
    ("32202", 30.33, -81.66),   # Jacksonville
    ("32301", 30.44, -84.28),   # Tallahassee
    ("33131", 25.77, -80.19),   # Miami
])
def test_levels_never_go_backwards_out_of_shelter(milton, zip_code, lat, lon):
    changes = run(milton, lat, lon, zip_code)
    levels = [lvl for lvl, _ in changes]
    if "shelter" in levels:
        assert levels[levels.index("shelter") + 1:] in ([], ["recover"])
    times = [t for _, t in changes]
    assert times == sorted(times)
