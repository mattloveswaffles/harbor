"""Connected institutions, all backed by Nessie accounts."""

API = "/api/v1"


def by_id(listing: list[dict]) -> dict[str, dict]:
    return {c["id"]: c for c in listing}


def test_maria_starts_with_her_bank_and_brokerage(client, auth):
    c = by_id(client.get(f"{API}/me/connections", headers=auth).json())
    assert c["chase"]["connected"] and c["robinhood"]["connected"] and not c["paypal"]["connected"]
    assert {a["type"] for a in c["chase"]["accounts"]} == {"checking", "savings"}
    assert c["chase"]["total_cents"] == 92000


def test_a_wallet_opens_a_nessie_account_and_closes_it_on_disconnect(client, auth, bank, maria):
    c = by_id(client.post(f"{API}/me/connections/paypal", headers=auth).json())
    assert c["paypal"]["connected"] and c["paypal"]["total_cents"] == 12000
    nessie = [a["nickname"] for a in bank.accounts.values() if a["customer_id"] == maria["nessie_customer_id"]]
    assert "PayPal balance (Harbor)" in nessie
    assert "wallet" in {a["type"] for a in client.get(f"{API}/me/accounts", headers=auth).json()}

    c = by_id(client.delete(f"{API}/me/connections/paypal", headers=auth).json())
    assert not c["paypal"]["connected"]
    nessie = [a["nickname"] for a in bank.accounts.values() if a["customer_id"] == maria["nessie_customer_id"]]
    assert "PayPal balance (Harbor)" not in nessie


def test_connecting_twice_is_harmless_and_unknown_banks_are_404(client, auth):
    client.post(f"{API}/me/connections/venmo", headers=auth)
    c = by_id(client.post(f"{API}/me/connections/venmo", headers=auth).json())
    assert len(c["venmo"]["accounts"]) == 1
    assert client.post(f"{API}/me/connections/mybank", headers=auth).status_code == 404


def test_a_new_user_connects_their_bank(client):
    res = client.post(
        f"{API}/auth/signup", json={"email": "a@b.co", "password": "long enough pw", "name": "Al", "zip": "33602"}
    )
    h = {"Authorization": f"Bearer {res.json()['token']}"}
    assert not any(c["connected"] for c in client.get(f"{API}/me/connections", headers=h).json())
    c = by_id(client.post(f"{API}/me/connections/chase", headers=h).json())
    assert {a["type"] for a in c["chase"]["accounts"]} == {"checking", "savings"}
