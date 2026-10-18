"""The Settings profile: people, medical needs, the car and places, mirrored onto the household."""

API = "/api/v1"


def test_maria_has_a_full_profile(client, auth):
    body = client.get(f"{API}/me/profile", headers=auth).json()
    assert [p["name"] for p in body["people"]] == ["Maria Lopez", "Daniel Lopez", "Sofia Lopez"]
    assert body["pets"][0]["name"] == "Biscuit"
    assert {m["name"] for m in body["medical"]["medications"]} >= {"Lisinopril", "Metformin"}
    assert (body["vehicle"]["make_model"], body["vehicle"]["mpg"]) == ("2018 Toyota Sienna", 21)


def test_saving_updates_the_household(client, auth):
    body = client.get(f"{API}/me/profile", headers=auth).json()
    body["people"].append({"name": "Grandpa Luis", "age": 71})
    body["pets"] = []
    body["vehicle"] = {"has_car": False}
    res = client.put(f"{API}/me/profile", json=body, headers=auth)
    assert res.status_code == 200, res.text
    hh = client.get(f"{API}/me", headers=auth).json()["household"]
    assert (hh["adults"], hh["children_ages"], hh["seniors"]) == (2, [7], 1)
    assert hh["pets"] == [] and hh["has_car"] is False


def test_a_new_address_moves_the_home(client, auth):
    body = client.get(f"{API}/me/profile", headers=auth).json()
    body |= {"zip": "34236", "location": {"lat": 27.33, "lon": -82.54}}
    assert client.put(f"{API}/me/profile", json=body, headers=auth).status_code == 200
    me = client.get(f"{API}/me", headers=auth).json()
    assert me["zip"] == "34236" and me["location"] == {"lat": 27.33, "lon": -82.54}


def test_bad_values_are_rejected(client, auth):
    body = client.get(f"{API}/me/profile", headers=auth).json()
    body["vehicle"]["mpg"] = -3
    assert client.put(f"{API}/me/profile", json=body, headers=auth).status_code == 422
