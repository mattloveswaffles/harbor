"""Accounts: sign up, log in, log out, tokens, lockout, and the demo-only shortcuts."""

import asyncio
import json
from datetime import timedelta

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from harbor.auth import LoginLimiter, hash_password, verify_password
from harbor.main import create_app
from harbor.models import AuthToken, Credential
from tests.conftest import make_settings
from tests.test_events import Stream

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
    assert client.get(f"{API}/auth/me", headers=h).json()["id"] == body["user"]["id"]
    assert client.get(f"{API}/me", headers=h).status_code == 200
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
    assert client.post(f"{API}/auth/signup", json={**SIGNUP, "email": "b@x.co", "password": "short"}).status_code == 422
    assert client.post(f"{API}/auth/signup", json={**SIGNUP, "email": "not-an-email"}).status_code == 422
    bad_zip = client.post(f"{API}/auth/signup", json={**SIGNUP, "email": "c@x.co", "zip": "10001"})
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


def test_demo_login_gives_maria_a_token(client):
    body = client.post(f"{API}/auth/demo-login").json()
    assert body["user"]["name"] == "Maria Lopez"
    assert client.get(f"{API}/me/plan", headers=bearer(body["token"])).status_code == 200
    ruth = client.post(f"{API}/auth/demo-login?persona=ruth").json()
    assert ruth["user"]["zip"] == "34236"


def test_live_mode_needs_a_real_login(tmp_path, bank):
    app = create_app(make_settings(tmp_path, harbor_mode="live"), bank=bank)
    with TestClient(app) as c:
        body = signup(c)
        assert c.get(f"{API}/me", headers=bearer(body["token"])).status_code == 200
        res = c.get(f"{API}/me", headers={"X-User-Id": body["user"]["id"]})
        assert res.status_code == 401 and res.json()["error"]["code"] == "auth_required"  # no impersonating by id
        assert c.post(f"{API}/users", json={"name": "X", "zip": "33602"}).status_code == 403
        assert c.post(f"{API}/auth/demo-login").status_code == 403


def test_live_stream_accepts_a_token(app, client):
    token = signup(client)["token"]

    async def run():
        s = Stream(app, "ignored")
        s.scope["query_string"] = f"token={token}".encode()
        async with s:
            assert s.status == 200
        bad = Stream(app, "ignored")
        bad.scope["query_string"] = b"token=hbr_nope"
        async with bad:
            assert bad.status == 401

    asyncio.run(run())


def test_hashes_are_salted():
    assert hash_password("same") != hash_password("same")
