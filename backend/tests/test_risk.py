import pytest

from harbor.engine.risk import Level, RiskInputs, next_level

storm = dict(storm_active=True)


@pytest.mark.parametrize(
    "current, inputs, expected",
    [
        (Level.clear, RiskInputs(), Level.clear),
        (Level.clear, RiskInputs(**storm, p34=0.06), Level.monitor),
        (Level.clear, RiskInputs(**storm, p34=0.02, in_cone=True), Level.monitor),
        (Level.monitor, RiskInputs(**storm, p34=0.23), Level.prepare),
        (Level.monitor, RiskInputs(**storm, p34=0.08, sensor_flag=True), Level.prepare),
        (Level.prepare, RiskInputs(**storm, p34=0.55), Level.act),
        (Level.prepare, RiskInputs(**storm, p34=0.40, alerts=frozenset({"hurricane_watch"})), Level.act),
        (Level.clear, RiskInputs(**storm, p34=0.70), Level.act),  # escalation can jump levels
        (Level.act, RiskInputs(**storm, p34=0.9, alerts=frozenset({"hurricane_warning"}), ts_winds_eta_hours=10), Level.shelter),
        (Level.act, RiskInputs(**storm, p34=0.9, sustained_wind_mph=41), Level.shelter),
        # A warning still 30 h out is act, not shelter.
        (Level.act, RiskInputs(**storm, p34=0.9, alerts=frozenset({"hurricane_warning"}), ts_winds_eta_hours=30), Level.act),
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
        Level.monitor, Level.prepare, Level.prepare, Level.act,
        Level.shelter, Level.shelter, Level.recover, Level.clear,
    ]


def test_reasons_mention_the_number():
    assert "23%" in next_level(Level.monitor, RiskInputs(**storm, p34=0.23)).reason
