"""GET /me/weather: NHC storm data plus Open-Meteo wind and rain (faked in conftest)."""

API = "/api/v1"


def test_weather_before_any_storm(client, auth):
    body = client.get(f"{API}/me/weather", headers=auth).json()
    assert body["storm"] is None
    assert len(body["series"]) == 10 and body["step_hours"] == 6
    assert body["hazards"]["power"]["level"] == "likely"  # the fake peaks at 98 mph gusts
    assert body["hazards"]["surge"] == {"zone": "A", "level": "low"}
    assert body["source"] == "Open-Meteo forecast"  # no storm is being replayed


def test_weather_during_milton(client, auth):
    client.post(f"{API}/demo/start")  # Maria is at act from the replay start
    body = client.get(f"{API}/me/weather", headers=auth).json()
    storm = body["storm"]
    assert storm["name"] == "Milton" and storm["category_at_closest"] >= 1
    assert storm["closest_at"] and storm["closest_miles"] < 150
    assert body["hazards"]["wind"]["arrives_at"]
    assert body["hazards"]["surge"]["level"] == "evacuate"
