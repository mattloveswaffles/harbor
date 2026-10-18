"""Test households, made the way the app makes them: sign up, save the profile, connect the bank through Nessie.

Maria: a Tampa family with a child, a dog and a car. Ruth: a Sarasota couple in a mobile home, on home oxygen,
with no car. Maria also has one bill due during Milton, so the bill shield has something to move.
"""

import asyncio
import itertools
from datetime import date

from sqlmodel import Session

from harbor.models import Bill
from harbor.provisioning import user_accounts

API = "/api/v1"
_count = itertools.count()

HOUSEHOLDS = {
    "maria": {
        "name": "Maria Lopez",
        "zip": "33602",
        "bills": [{"payee": "Sunshine Auto Insurance (demo)", "amount_cents": 18900, "due": date(2024, 10, 9)}],
        "profile": {
            "personal": {"name": "Maria Lopez", "dob": "1987-03-14", "phone": "(813) 555-0142"},
            "home": {"address": "412 E Madison St, Tampa, FL 33602", "home_type": "house", "evac_zone": "A"},
            "people": [
                {"name": "Maria Lopez", "age": 37, "relation": "you"},
                {"name": "Daniel Lopez", "age": 40, "relation": "spouse"},
                {"name": "Sofia Lopez", "age": 7, "relation": "child"},
            ],
            "pets": [{"name": "Biscuit", "type": "dog", "weight_lb": 45, "notes": "crate trained"}],
            "medical": {
                "medications": [
                    {
                        "name": "Metformin",
                        "dose": "500 mg",
                        "person": "Maria",
                        "schedule": "Twice a day",
                        "days_left": 21,
                    },
                    {"name": "Lisinopril", "dose": "10 mg", "person": "Daniel", "schedule": "Mornings", "days_left": 4},
                    {"name": "Albuterol inhaler", "person": "Sofia", "schedule": "As needed", "days_left": 30},
                ],
                "equipment": ["CPAP (Daniel)"],
                "allergies": "Sofia: penicillin",
                "pharmacy": "CVS, 1101 N Florida Ave, Tampa",
            },
            "vehicle": {"make_model": "2018 Toyota Sienna", "mpg": 21, "tank_gal": 20, "fuel_level": 0.5, "seats": 7},
            "places": [
                {"label": "Rosa's house", "address": "1840 Vineville Ave, Macon, GA 31201", "kind": "destination"},
            ],
            "contacts": [{"name": "Rosa Lopez", "relation": "sister", "phone": "(478) 555-0199", "gets_plan": True}],
        },
    },
    "ruth": {
        "name": "Ruth Diaz",
        "zip": "34236",
        "bills": [],
        "profile": {
            "personal": {"name": "Ruth Diaz"},
            "home": {"address": "200 Palm Ave, Sarasota, FL 34236", "home_type": "mobile", "evac_zone": "A"},
            "people": [{"name": "Ruth Diaz", "age": 74, "relation": "you"}, {"name": "Hector Diaz", "age": 77}],
            "medical": {"oxygen": True, "refrigerated_meds": True, "mobility": "walker", "equipment": ["Home oxygen"]},
            "vehicle": {"has_car": False},
        },
    },
}


def _add_bills(app, user_id: str, bills: list[dict]) -> None:
    """Bills on the household's checking, in Nessie and in Harbor."""
    with Session(app.state.engine) as s:
        checking = next(a for a in user_accounts(s, user_id) if a.type == "checking")
        for b in bills:
            nessie_id = asyncio.run(
                app.state.bank.create_bill(checking.nessie_id, b["payee"], b["amount_cents"], b["due"], b["payee"])
            )
            s.add(
                Bill(
                    user_id=user_id,
                    account_id=checking.id,
                    nessie_id=nessie_id,
                    payee=b["payee"],
                    amount_cents=b["amount_cents"],
                    due_date=b["due"],
                    original_due_date=b["due"],
                )
            )
        s.commit()


def make_household(client, who: str = "maria") -> dict:
    """Sign a household up through the API; returns its GET /me, with its login headers under `auth`."""
    spec = HOUSEHOLDS[who]
    email = f"{who}{next(_count)}@example.com"
    res = client.post(
        f"{API}/auth/signup",
        json={"name": spec["name"], "email": email, "password": "correct horse battery", "zip": spec["zip"]},
    )
    assert res.status_code == 201, res.text
    token = res.json()["token"]
    h = {"Authorization": f"Bearer {token}"}
    assert client.put(f"{API}/me/profile", json=spec["profile"], headers=h).status_code == 200
    for institution in ("chase", "robinhood"):
        assert client.post(f"{API}/me/connections/{institution}", headers=h).status_code == 200
    _add_bills(client.app, res.json()["user"]["id"], spec["bills"])
    return {**client.get(f"{API}/me", headers=h).json(), "auth": h}
