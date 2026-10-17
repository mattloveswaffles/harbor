"""Sensor rules, checked against the real Hurricane Milton recording."""

from datetime import datetime, timedelta, timezone

from harbor.engine.risk import Level, RiskInputs, next_level
from harbor.sources.sensors import Series, SensorSource, Station, recovery_gate, status_of

UTC = timezone.utc
TAMPA = (27.9506, -82.4572)
src = SensorSource()


def at(*args) -> datetime:
    return datetime(*args, tzinfo=UTC)


def reading(station_id: str, now: datetime):
    return next(r for r in src.readings(now, *TAMPA) if r.station.id == station_id)


def test_all_three_sensors_are_near_tampa():
    ids = [r.station.id for r in src.readings(at(2024, 10, 7, 12), *TAMPA)]
    assert set(ids) == {"coops_8726520", "usgs_02301500", "ndbc_42036"}
    assert reading("usgs_02301500", at(2024, 10, 7, 12)).distance_miles == 16


def test_calm_before_the_storm():
    facts = src.risk_facts(at(2024, 10, 7, 12), *TAMPA)
    assert facts["sensor_flag"] is False
    assert facts["sustained_wind_mph"] < 39


def test_reverse_surge_warning_at_st_pete():
    r = reading("coops_8726520", at(2024, 10, 10, 2, 30))
    assert r.status == "warning"
    assert r.readings["surge_ft"] < -2
    assert "bay floor" in r.status_reason


def test_tropical_storm_winds_trigger_the_shelter_freeze():
    facts = src.risk_facts(at(2024, 10, 9, 23), *TAMPA)
    assert facts["sustained_wind_mph"] >= 39
    d = next_level(Level.act, RiskInputs(storm_active=True, p34=0.9, sustained_wind_mph=facts["sustained_wind_mph"]))
    assert d.level == Level.shelter


def test_alafia_river_crest_is_major_flood():
    r = reading("usgs_02301500", at(2024, 10, 11, 14))
    assert r.readings["stage_ft"] == 24.36
    assert r.flood_category == "major" and r.status == "warning"
    assert r.to_api()["flood_stages"] == {"action": 11.0, "minor": 13.0, "moderate": 16.0, "major": 19.0}


def test_recovery_hold_after_nhc_alerts_end():
    # NHC alerts ended around 2024-10-10T09Z, but the river was still rising.
    facts = src.risk_facts(at(2024, 10, 10, 9), *TAMPA)
    assert facts["sensors_all_clear"] is False
    assert "Alafia" in facts["all_clear_reason"]
    d = next_level(Level.shelter, RiskInputs(storm_passed=True, sensors_all_clear=facts["sensors_all_clear"]))
    assert d.level == Level.shelter and d.recovery_hold


def test_still_held_at_the_crest_then_clear_on_sunday_evening():
    assert src.risk_facts(at(2024, 10, 11, 14), *TAMPA)["sensors_all_clear"] is False
    assert src.risk_facts(at(2024, 10, 13, 12), *TAMPA)["sensors_all_clear"] is False
    assert src.risk_facts(at(2024, 10, 13, 20), *TAMPA)["sensors_all_clear"] is True


def test_replay_never_sees_the_future():
    r = reading("usgs_02301500", at(2024, 10, 10, 9))
    assert r.observed_at <= at(2024, 10, 10, 9)


def test_stale_data_is_never_all_clear():
    station = Station("t", "noaa_tide", "Test gauge", 27.8, -82.6, "test")
    rows = [{"t": "2024-10-10T00:00:00Z", "water_level_ft": 1.0, "predicted_ft": 1.0, "surge_ft": 0.0, "pressure_mb": 1012}]
    s = Series(station, rows)
    later = at(2024, 10, 10, 3)
    assert status_of(s, later).stale
    clear, reason = recovery_gate([s], later)
    assert clear is False and "no fresh reading" in reason


def test_history_for_charts():
    rows = src.history("coops_8726520", at(2024, 10, 10, 12), hours=48, metrics=["surge_ft", "predicted_ft"])
    assert 0 < len(rows) <= 480
    assert set(rows[0]["readings"]) <= {"surge_ft", "predicted_ft"}
    assert rows[-1]["observed_at"] <= "2024-10-10T12:00:00Z"
    assert src.history("nope", at(2024, 10, 10, 12)) == []
