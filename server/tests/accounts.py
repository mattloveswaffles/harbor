"""Accounts: signup, login, tokens, users and households."""

import asyncio
import json
from datetime import date, timedelta

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from harbor.auth import LoginLimiter, hash_password, verify_password
from harbor.evac.household import (
    Household,
    Pet,
    budget_lines,
    evacuation_reasons,
    guide,
    needs,
    rooms_needed,
    route_needs,
)
from harbor.geo import lookup_zip
from harbor.main import create_app
from harbor.models import AuthToken, Credential, Lot
from tests.conftest import make_settings
from tests.live_updates import Stream

API = "/api/v1"


SIGNUP = {"email": "Sam.Rivera@Example.com", "password": "correct horse battery", "name": "Sam Rivera", "zip": "33602"}


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def signup(client, **over):
    res = client.post(f"{API}/auth/signup", json={**SIGNUP, **over})
    assert res.status_code == 201, res.text
    return res.json()


def test_signup_returns_a_token_that_works_everywhere(client, bank):
    body = signup(client)
    assert body["token"].startswith("hbr_") and body["token_type"] == "bearer"
    assert body["user"]["name"] == "Sam Rivera" and body["user"]["zip"] == "33602"
    h = bearer(body["token"])
    assert client.get(f"{API}/me", headers=h).json()["id"] == body["user"]["id"]
    accounts = client.get(f"{API}/me/accounts", headers=h).json()
    assert {a["type"] for a in accounts} == {"checking", "savings", "brokerage_cash"}
    # The email never reaches Nessie: the bank only sees a pseudonym.
    assert not any("example.com" in json.dumps(c).lower() or "Rivera" in json.dumps(c) for c in bank.customers.values())


def test_password_is_stored_hashed_and_email_lowercased(client, app):
    signup(client)
    with Session(app.state.engine) as s:
        cred = s.exec(select(Credential)).one()
    assert cred.email == "sam.rivera@example.com"
    assert cred.password_hash.startswith("scrypt$") and "correct horse" not in cred.password_hash
    assert verify_password("correct horse battery", cred.password_hash)
    assert not verify_password("wrong", cred.password_hash) and not verify_password("x", "garbage")


def test_duplicate_email_and_bad_input(client):
    signup(client)
    dup = client.post(f"{API}/auth/signup", json={**SIGNUP, "email": "sam.rivera@example.com"})
    assert dup.status_code == 409 and dup.json()["error"]["code"] == "email_taken"
    assert client.post(f"{API}/auth/signup", json={**SIGNUP, "email": "b@x.co", "password": "abc"}).status_code == 422
    assert client.post(f"{API}/auth/signup", json={**SIGNUP, "email": "not an email"}).status_code == 422
    bad_zip = client.post(f"{API}/auth/signup", json={**SIGNUP, "email": "c@x.co", "zip": "00000"})
    assert bad_zip.status_code == 400 and bad_zip.json()["error"]["code"] == "zip_not_supported"


def test_login_and_wrong_passwords(client):
    user = signup(client)["user"]
    ok = client.post(f"{API}/auth/login", json={"email": "SAM.rivera@example.com", "password": "correct horse battery"})
    assert ok.status_code == 200 and ok.json()["user"]["id"] == user["id"]
    wrong = client.post(f"{API}/auth/login", json={"email": SIGNUP["email"], "password": "nope"})
    unknown = client.post(f"{API}/auth/login", json={"email": "ghost@example.com", "password": "nope"})
    # Same answer either way, so nobody can find out which emails have accounts.
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["error"] == unknown.json()["error"]


def test_five_wrong_passwords_lock_the_email(client):
    signup(client)
    for _ in range(5):
        client.post(f"{API}/auth/login", json={"email": SIGNUP["email"], "password": "nope"})
    locked = client.post(f"{API}/auth/login", json={"email": SIGNUP["email"], "password": SIGNUP["password"]})
    assert locked.status_code == 429 and locked.json()["error"]["code"] == "too_many_attempts"


def test_lockout_wears_off():
    t = [0.0]
    lim = LoginLimiter(max_failures=2, window_s=60, clock=lambda: t[0])
    lim.failed("a@b.co")
    lim.failed("A@B.co ")
    assert lim.locked("a@b.co")
    t[0] = 61
    assert not lim.locked("a@b.co")


def test_logout_revokes_the_token(client):
    token = signup(client)["token"]
    assert client.post(f"{API}/auth/logout", headers=bearer(token)).status_code == 204
    res = client.get(f"{API}/me", headers=bearer(token))
    assert res.status_code == 401 and res.json()["error"]["code"] == "invalid_token"


def test_expired_and_garbage_tokens_are_refused(client, app):
    token = signup(client)["token"]
    with Session(app.state.engine) as s:
        tok = s.exec(select(AuthToken)).one()
        tok.expires_at = tok.created_at - timedelta(seconds=1)
        s.add(tok)
        s.commit()
    assert client.get(f"{API}/me", headers=bearer(token)).json()["error"]["code"] == "invalid_token"
    assert client.get(f"{API}/me", headers=bearer("hbr_made_up")).status_code == 401
    assert client.get(f"{API}/me", headers={"Authorization": "Basic abc"}).json()["error"]["code"] == "invalid_token"
    assert client.get(f"{API}/me").json()["error"]["code"] == "auth_required"


def test_live_mode_logs_in_the_same_way(tmp_path, bank):
    app = create_app(make_settings(tmp_path, harbor_mode="live"), bank=bank)
    with TestClient(app) as c:
        body = signup(c)
        assert c.get(f"{API}/me", headers=bearer(body["token"])).status_code == 200


def test_live_stream_accepts_a_token(app, client):
    token = signup(client)["token"]

    async def run():
        async with Stream(app, token) as s:
            assert s.status == 200
        async with Stream(app, "hbr_nope") as bad:
            assert bad.status == 401

    asyncio.run(run())


def test_hashes_are_salted():
    assert hash_password("same") != hash_password("same")


LAT_33901, LON_33901 = lookup_zip("33901")["lat"], lookup_zip("33901")["lon"]


def test_zip_preview(client):
    res = client.get(f"{API}/zip/33602")
    assert res.status_code == 200
    assert res.json() == {"zip": "33602", "city": "Tampa", "state": "FL", "lat": 27.953704, "lon": -82.45631}


def test_zip_lookup_covers_the_us(client):
    assert client.get(f"{API}/zip/10001").json() == {
        "zip": "10001",
        "city": "New York",
        "state": "NY",
        "lat": 40.750649,
        "lon": -73.997298,
    }
    for z in ("33601", "00000"):  # a PO-box ZIP and a ZIP that doesn't exist
        res = client.get(f"{API}/zip/{z}")
        assert res.status_code == 400
        assert res.json()["error"]["code"] == "zip_not_supported"
        assert res.json()["error"]["fields"] == {"zip": "Unknown ZIP"}


def test_zip_must_be_five_digits(client):
    res = client.get(f"{API}/zip/3360")
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "validation_error"


def test_sign_up_creates_user_accounts_and_portfolio(client, bank, app):
    body = signup(client, name="Ana Real-Person", zip="33901")
    user = body["user"]
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

    accounts = client.get(f"{API}/me/accounts", headers=bearer(body["token"])).json()
    assert [(a["type"], a["nessie_type"], a["nickname"], a["balance_cents"]) for a in accounts] == [
        ("checking", "Checking", "Everyday", 42000),
        ("savings", "Savings", "Emergency fund", 50000),
        ("brokerage_cash", "Savings", "Brokerage Settlement (Harbor)", 0),
    ]
    with Session(app.state.engine) as s:
        lots = s.exec(select(Lot).where(Lot.user_id == user["id"])).all()
    assert sorted({lot.symbol for lot in lots}) == ["TBUX", "TCAF", "TSPA"]


def test_sign_up_with_gps_and_household(client):
    user = signup(
        client,
        location={"lat": 27.96, "lon": -82.46},
        household={
            "adults": 2,
            "children_ages": [4, 9],
            "pets": [{"type": "cat", "count": 2}],
            "has_car": False,
            "evac_zone": "B",
        },
    )["user"]
    assert user["location"] == {"lat": 27.96, "lon": -82.46} and user["location_source"] == "gps"
    hh = user["household"]
    assert hh["children_ages"] == [4, 9] and hh["pets"] == [{"type": "cat", "count": 2}]
    assert hh["has_car"] is False and hh["evac_zone"] == "B" and hh["mobility"] == "none"


def test_sign_up_rejects_unknown_zip_and_bad_fields(client, bank):
    res = client.post(f"{API}/auth/signup", json={**SIGNUP, "zip": "33601"})
    assert res.status_code == 400 and res.json()["error"]["code"] == "zip_not_supported"
    res = client.post(f"{API}/auth/signup", json={**SIGNUP, "name": "", "household": {"children_ages": [30]}})
    assert res.status_code == 422
    locs = [f["loc"] for f in res.json()["error"]["fields"]]
    assert ["body", "name"] in locs and ["body", "household", "children_ages", 0] in locs
    assert bank.customers == {}


def test_sign_up_when_nessie_is_down(client, bank):
    bank.down = True
    res = client.post(f"{API}/auth/signup", json=SIGNUP)
    assert res.status_code == 503 and res.json()["error"]["code"] == "bank_unavailable"


def test_get_me(client, auth, maria):
    assert {**client.get(f"{API}/me", headers=auth).json(), "auth": auth} == maria


def test_patch_me_settings_merge(client, auth):
    res = client.patch(
        f"{API}/me", headers=auth, json={"settings": {"auto_approve": True, "cancel_window_minutes": 30}}
    )
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


def test_accounts_read_live_nessie_balances(client, auth, bank, clock):
    accounts = client.get(f"{API}/me/accounts", headers=auth).json()
    chk, sav = accounts[0], accounts[1]
    assert chk["balance_synced_at"] == "2024-10-06T03:00:00Z"

    clock.advance(timedelta(hours=1))
    asyncio.run(
        bank.transfer(sav["nessie_id"], chk["nessie_id"], 20000, rounding="up", on=date(2024, 10, 6), move_id="mv_t")
    )
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


MARIA = Household(adults=2, children_ages=(7,), pets=(Pet("dog"),), evac_zone="A")


GSA_GAINESVILLE_MEALS = 6_800


def test_maria_budget_matches_the_api_example():
    lines = budget_lines(
        MARIA, days=3, nights=3, meals_rate_cents=GSA_GAINESVILLE_MEALS, meals_source="gsa_per_diem_fy2025"
    )
    assert [(l.label, l.amount_cents) for l in lines] == [
        ("Food and water: 2 adults + 1 child, 3 days", 56_100),
        ("Pets: dog, 3 nights (Harbor estimate)", 7_500),
        ("Supplies: kit, water, chargers (Harbor estimate)", 12_000),
    ]


def test_maria_guide():
    g = guide(MARIA)
    assert needs(MARIA) == ["everyone", "kids", "pets"]
    assert g.rooms == 1
    assert g.shelter_filter.pets and not g.shelter_filter.wheelchair
    assert {c.need for c in g.checklists} == {"everyone", "kids", "pets"}
    assert evacuation_reasons(MARIA) == ["ZONE_A"]
    assert any(c.kind == "pets" for c in g.advice)


def test_rooms_scale_with_people():
    assert rooms_needed(Household(adults=2, children_ages=(3, 6))) == 1
    assert rooms_needed(Household(adults=2, children_ages=(3, 6, 9))) == 2


def test_older_couple_without_a_car():
    h = Household(adults=0, seniors=2, has_car=False, oxygen=True, mobility="walker")
    g = guide(h)
    route = route_needs(h)
    assert route.max_drive_hours_per_day == 6 and route.extra_leave_buffer_hours == 3
    assert route.prefer_regional_destination
    assert g.shelter_filter.special_needs_shelter
    kinds = {c.kind for c in g.advice}
    assert {"no_car", "special_needs_shelter", "early_refill"} <= kinds
    medical = next(c for c in g.checklists if c.need == "medical")
    assert any("oxygen" in item for item in medical.items)


def test_dialysis_means_leave_early_and_plan_with_doctor():
    h = Household(adults=1, dialysis=True)
    g = guide(h)
    assert "POWER_OR_MEDICAL" in evacuation_reasons(h)
    assert any(c.kind == "leave_early_medical" for c in g.advice)
    special = next(c for c in g.advice if c.kind == "special_needs_shelter")
    assert special.deadline_hours_before_landfall == 72


def test_mobile_home_always_evacuates_and_goes_regional():
    h = Household(adults=1, home_type="mobile", evac_zone="none")
    assert evacuation_reasons(h) == ["MOBILE_HOME"]
    assert route_needs(h).prefer_regional_destination


def test_infant_adds_supplies():
    h = Household(adults=2, children_ages=(1,))
    supplies = budget_lines(h, days=2, nights=2, meals_rate_cents=6_800, meals_source="gsa")[-1]
    assert supplies.amount_cents == 3_000 + 1_000 * 3 * 2 + 1_500 * 2
    assert "infants" in needs(h)


def test_every_checklist_cites_a_ready_gov_page():
    g = guide(
        Household(
            adults=1,
            seniors=1,
            children_ages=(0,),
            pets=(Pet("cat", 2),),
            mobility="wheelchair",
            refrigerated_meds=True,
        )
    )
    assert all(c.source_url.startswith("https://www.ready.gov/") for c in g.checklists)


def test_the_demo_account_signs_in_with_a_username(client):
    assert client.post(f"{API}/auth/signup", json={**SIGNUP, "email": "demo", "password": "1111"}).status_code == 201
    assert client.post(f"{API}/auth/login", json={"email": "Demo", "password": "1111"}).status_code == 200
