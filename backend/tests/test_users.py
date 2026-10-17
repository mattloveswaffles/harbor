import asyncio
from datetime import date, timedelta

from sqlmodel import Session, select

from harbor.geo import lookup_zip
from harbor.models import Lot

API = "/api/v1"
LAT_33901, LON_33901 = lookup_zip("33901")["lat"], lookup_zip("33901")["lon"]


# GET /zip/{zip} ---------------------------------------------------------------------------
def test_zip_preview(client):
    res = client.get(f"{API}/zip/33602")
    assert res.status_code == 200
    assert res.json() == {"zip": "33602", "city": "Tampa", "state": "FL", "lat": 27.953704, "lon": -82.45631}


def test_zip_po_box_and_out_of_state_are_not_supported(client):
    for z in ("33601", "10001"):
        res = client.get(f"{API}/zip/{z}")
        assert res.status_code == 400
        assert res.json()["error"]["code"] == "zip_not_supported"
        assert res.json()["error"]["fields"] == {"zip": "Unknown ZIP"}


def test_zip_must_be_five_digits(client):
    res = client.get(f"{API}/zip/3360")
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "validation_error"


# POST /users -----------------------------------------------------------------------------
def test_sign_up_creates_user_accounts_and_portfolio(client, bank, app):
    res = client.post(f"{API}/users", json={"name": "Ana Real-Person", "zip": "33901"})
    assert res.status_code == 201, res.text
    user = res.json()
    assert user["id"].startswith("usr_")
    assert user["location"] == {"lat": LAT_33901, "lon": LON_33901}
    assert user["location_source"] == "zcta"
    assert user["risk_level"] == "clear"
    assert user["settings"] == {
        "auto_approve": False,
        "max_etf_sell_cents": 300000,
        "cancel_window_minutes": 120,
        "rebuy_opt_in": False,
    }
    assert user["household"]["adults"] == 1 and user["household"]["evac_zone"] == "unsure"

    # Nessie gets a pseudonym, never the person's real name.
    cust = bank.customers[user["nessie_customer_id"]]
    assert cust["first_name"] == "Harbor" and cust["last_name"] == f"User {user['id']}"
    assert "Ana" not in str(bank.customers)

    accounts = client.get(f"{API}/me/accounts", headers={"X-User-Id": user["id"]}).json()
    assert [(a["type"], a["nessie_type"], a["nickname"], a["balance_cents"]) for a in accounts] == [
        ("checking", "Checking", "Everyday", 42000),
        ("savings", "Savings", "Emergency fund", 50000),
        ("brokerage_cash", "Savings", "Brokerage Settlement (Harbor)", 0),
    ]
    with Session(app.state.engine) as s:
        lots = s.exec(select(Lot).where(Lot.user_id == user["id"])).all()
    assert sorted({lot.symbol for lot in lots}) == ["TBUX", "TCAF", "TSPA"]


def test_sign_up_with_gps_and_household(client):
    body = {
        "name": "Sam",
        "zip": "33602",
        "location": {"lat": 27.96, "lon": -82.46},
        "household": {"adults": 2, "children_ages": [4, 9], "pets": [{"type": "cat", "count": 2}], "has_car": False, "evac_zone": "B"},
    }
    user = client.post(f"{API}/users", json=body).json()
    assert user["location"] == {"lat": 27.96, "lon": -82.46} and user["location_source"] == "gps"
    hh = user["household"]
    assert hh["children_ages"] == [4, 9] and hh["pets"] == [{"type": "cat", "count": 2}]
    assert hh["has_car"] is False and hh["evac_zone"] == "B" and hh["mobility"] == "none"


def test_sign_up_rejects_unknown_zip_and_bad_fields(client, bank):
    res = client.post(f"{API}/users", json={"name": "Sam", "zip": "33601"})
    assert res.status_code == 400 and res.json()["error"]["code"] == "zip_not_supported"
    res = client.post(f"{API}/users", json={"name": "", "zip": "33602", "household": {"children_ages": [30]}})
    assert res.status_code == 422
    locs = [f["loc"] for f in res.json()["error"]["fields"]]
    assert ["body", "name"] in locs and ["body", "household", "children_ages", 0] in locs
    assert bank.customers == {}


def test_sign_up_when_nessie_is_down(client, bank):
    bank.down = True
    res = client.post(f"{API}/users", json={"name": "Sam", "zip": "33602"})
    assert res.status_code == 503 and res.json()["error"]["code"] == "bank_unavailable"


# Auth ------------------------------------------------------------------------------------
def test_me_needs_a_known_user_id(client):
    res = client.get(f"{API}/me")
    assert res.status_code == 401 and res.json()["error"]["code"] == "auth_required"
    res = client.get(f"{API}/me", headers={"X-User-Id": "usr_nope"})
    assert res.status_code == 401 and res.json()["error"]["code"] == "user_not_found"


# GET / PATCH /me -------------------------------------------------------------------------
def test_get_me(client, auth, maria):
    assert client.get(f"{API}/me", headers=auth).json() == maria


def test_patch_me_settings_merge(client, auth):
    res = client.patch(f"{API}/me", headers=auth, json={"settings": {"auto_approve": True, "cancel_window_minutes": 30}})
    assert res.status_code == 200
    assert res.json()["settings"] == {
        "auto_approve": True,
        "max_etf_sell_cents": 300000,
        "cancel_window_minutes": 30,
        "rebuy_opt_in": False,
    }
    res = client.patch(f"{API}/me", headers=auth, json={"settings": {"max_etf_sell_cents": -5}})
    assert res.status_code == 422


def test_patch_me_zip_and_location(client, auth):
    user = client.patch(f"{API}/me", headers=auth, json={"zip": "34236", "name": "Maria L."}).json()
    assert user["zip"] == "34236" and user["name"] == "Maria L." and user["location_source"] == "zcta"
    assert user["location"]["lat"] != 27.953704
    user = client.patch(f"{API}/me", headers=auth, json={"location": {"lat": 27.3, "lon": -82.5}}).json()
    assert user["location"] == {"lat": 27.3, "lon": -82.5} and user["location_source"] == "gps"
    res = client.patch(f"{API}/me", headers=auth, json={"zip": "33601"})
    assert res.status_code == 400 and res.json()["error"]["code"] == "zip_not_supported"


# PATCH /me/household ---------------------------------------------------------------------
def test_patch_household_is_partial(client, auth):
    res = client.patch(f"{API}/me/household", headers=auth, json={"seniors": 1, "mobility": "walker"})
    assert res.status_code == 200
    hh = res.json()["household"]
    assert hh["seniors"] == 1 and hh["mobility"] == "walker"
    assert hh["adults"] == 2 and hh["children_ages"] == [7] and hh["pets"] == [{"type": "dog", "count": 1}]
    res = client.patch(f"{API}/me/household", headers=auth, json={"mobility": "skateboard"})
    assert res.status_code == 422


# GET /me/accounts ------------------------------------------------------------------------
def test_accounts_read_live_nessie_balances(client, auth, bank, clock):
    accounts = client.get(f"{API}/me/accounts", headers=auth).json()
    chk, sav = accounts[0], accounts[1]
    assert chk["balance_synced_at"] == "2024-10-06T03:00:00Z"

    clock.advance(timedelta(hours=1))
    asyncio.run(bank.transfer(sav["nessie_id"], chk["nessie_id"], 20000, rounding="up", on=date(2024, 10, 6), move_id="mv_t"))
    accounts = client.get(f"{API}/me/accounts", headers=auth).json()
    assert accounts[0]["balance_cents"] == 62000 and accounts[1]["balance_cents"] == 30000
    assert accounts[0]["balance_synced_at"] == "2024-10-06T04:00:00Z"


def test_accounts_fall_back_to_cached_balances_when_nessie_is_down(client, auth, bank, clock):
    client.get(f"{API}/me/accounts", headers=auth)
    clock.advance(timedelta(hours=3))
    bank.down = True
    res = client.get(f"{API}/me/accounts", headers=auth)
    assert res.status_code == 200
    assert [a["balance_cents"] for a in res.json()] == [42000, 50000, 0]
    assert res.json()[0]["balance_synced_at"] == "2024-10-06T03:00:00Z"

