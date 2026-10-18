"""Evacuation advice: written by the AI in the background, its ids checked against the facts."""

import json
import threading

from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.models.function import FunctionModel

API = "/api/v1"
STEPS = [
    {"title": "Refill Lisinopril", "detail": "4 days left", "kind": "medicine"},
    {"title": "Fill the tank", "detail": "379 mi to drive", "kind": "car"},
]
ANSWER = {"summary": "Go to Macon.", "destination_id": "macon_ga", "shelter_id": None, "steps": STEPS}


def ai(answer: dict) -> FunctionModel:
    """A stand-in model that answers in JSON, like the OpenRouter ones."""
    reply = ModelResponse(parts=[TextPart(json.dumps(answer))])
    return FunctionModel(lambda messages, info: reply, profile={"supports_json_schema_output": True})


def wait_for_ai() -> None:
    for t in threading.enumerate():
        if t.name.startswith("advisor-"):
            t.join(10)


def advice(client, auth) -> dict:
    return client.get(f"{API}/me/advice", headers=auth).json()


def test_the_ai_writes_the_advice_in_the_background(client, auth, app):
    app.state.llm_model = ai(ANSWER)
    body = advice(client, auth)
    assert body["status"] == "running" and body["advice"] is None
    wait_for_ai()
    body = advice(client, auth)
    assert body["status"] == "ready" and body["advice"]["summary"] == "Go to Macon."
    assert body["advice"]["steps"] == STEPS and body["facts"]["range_mi"] == 210


def test_made_up_destinations_and_shelters_are_replaced(client, auth, app):
    client.post(f"{API}/demo/start")  # Milton: destinations and shelters to choose from
    app.state.llm_model = ai(ANSWER | {"destination_id": "atlantis", "shelter_id": "nowhere"})
    advice(client, auth)
    wait_for_ai()
    body = advice(client, auth)["advice"]
    assert body["destination_id"] == "macon_ga" and body["shelter_id"]  # Rosa's house, and a real shelter


def test_without_the_ai_there_is_no_advice(client, auth):
    body = advice(client, auth)
    assert (body["status"], body["advice"], body["error"]) == ("error", None, "The AI is off.")


def test_new_facts_start_a_fresh_run_and_keep_the_last_advice_up(client, auth, app):
    app.state.llm_model = ai(ANSWER)
    advice(client, auth)
    wait_for_ai()
    client.post(f"{API}/me/connections/paypal", headers=auth)
    body = advice(client, auth)
    assert body["status"] == "running" and body["advice"]["summary"] == "Go to Macon."
    wait_for_ai()
    assert advice(client, auth)["status"] == "ready"


def test_regenerate_waits_for_a_run_in_progress(client, auth, app):
    app.state.llm_model = ai(ANSWER)
    assert client.post(f"{API}/me/advice/regenerate", headers=auth).json()["status"] == "running"
    assert client.post(f"{API}/me/advice/regenerate", headers=auth).json()["status"] in ("running", "ready")
    wait_for_ai()
    assert advice(client, auth)["status"] == "ready"
