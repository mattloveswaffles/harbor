"""Ask Harbor: the chat agent, its tools and the streaming /me/chat endpoint."""

import json
import os

import pytest
from fastapi.testclient import TestClient
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.test import TestModel

from harbor.main import create_app
from tests.conftest import make_settings
from tests.households import make_household

API = "/api/v1"
TOOLS = {
    "household",
    "storm_status",
    "bank_accounts",
    "investments",
    "evacuation_plan",
    "evacuation_guide",
    "bills",
    "nearby_atms",
    "nearby_sensors",
    "household_details",
    "connected_accounts",
    "weather_at_home",
    "evacuation_advice",
    "regenerate_advice",
}


def ask(client, auth, *messages: str):
    turns = [{"role": "user" if i % 2 == 0 else "assistant", "content": m} for i, m in enumerate(messages)]
    return client.post(f"{API}/me/chat", headers=auth, json={"messages": turns})


def events(res) -> list[dict]:
    """The server-sent events of a /me/chat answer."""
    return [json.loads(line[6:]) for line in res.text.splitlines() if line.startswith("data: ")]


def answer(res) -> tuple[str, list[str]]:
    """(the streamed reply, the tools it used)."""
    ev = events(res)
    return "".join(e["text"] for e in ev if e["type"] == "text"), ev[-1]["tools_used"]


@pytest.fixture
def storm(client):
    assert client.post(f"{API}/demo/start").status_code == 200


def test_unavailable_without_a_key(client, auth):
    res = ask(client, auth, "How much cash do I have?")
    assert res.status_code == 503 and res.json()["error"]["code"] == "chat_unavailable"
    assert client.get("/health").json()["chat"] == "off"


def test_every_tool_works_and_reads_only(client, auth, app, storm):
    app.state.llm_model = TestModel()  # calls every tool, then answers
    before = (client.get(f"{API}/me/accounts", headers=auth).json(), client.get(f"{API}/me/plan", headers=auth).json())
    res = ask(client, auth, "What should I do?")
    assert res.status_code == 200, res.text
    assert res.headers["content-type"].startswith("text/event-stream")
    ev = events(res)
    assert [e["name"] for e in ev if e["type"] == "tool"] == list(ev[-1]["tools_used"])
    assert set(ev[-1]["tools_used"]) == TOOLS
    after = (client.get(f"{API}/me/accounts", headers=auth).json(), client.get(f"{API}/me/plan", headers=auth).json())
    assert [a["balance_cents"] for a in after[0]] == [a["balance_cents"] for a in before[0]]
    assert after[1]["plan"]["status"] == before[1]["plan"]["status"] == "awaiting_approval"
    assert client.get("/health").json()["chat"] == "ok"


def test_the_conversation_is_passed_along(client, auth, app):
    seen = []

    async def model(messages, info: AgentInfo):
        seen.append(len(messages))
        yield "Leave by "
        yield "Tuesday."

    app.state.llm_model = FunctionModel(stream_function=model)
    res = ask(client, auth, "When should I leave?", "Tuesday morning.", "Why then?")
    assert answer(res) == ("Leave by Tuesday.", [])
    assert seen == [3]  # two earlier turns + the new question


def test_bad_requests(client, auth, app):
    app.state.llm_model = TestModel(call_tools=[])
    assert ask(client, auth, "Hi", "Hello").status_code == 422  # last turn must be the user's
    assert client.post(f"{API}/me/chat", headers=auth, json={"messages": []}).status_code == 422


def test_model_errors_end_the_stream_with_an_error(client, auth, app):
    async def broken(messages, info):
        raise RuntimeError("quota")
        yield ""

    app.state.llm_model = FunctionModel(stream_function=broken)
    res = ask(client, auth, "Hi")
    assert res.status_code == 200 and events(res)[-1]["type"] == "error"
    assert events(res)[-1]["code"] == "chat_failed"


def test_limited_to_ten_a_minute(client, auth, app):
    app.state.llm_model = TestModel(call_tools=[])
    for _ in range(10):
        assert ask(client, auth, "Hi").status_code == 200
    res = ask(client, auth, "Hi")
    assert res.status_code == 429 and int(res.headers["Retry-After"]) >= 1


def test_the_ai_offline_toggle_turns_chat_off(tmp_path, clock, bank):
    app = create_app(make_settings(tmp_path, openrouter_api_key="test-key"), clock=clock, bank=bank)
    with TestClient(app) as c:
        assert c.get("/health").json()["chat"] == "ok"
        c.post(f"{API}/demo/ai", json={"enabled": False})
        assert c.get("/health").json()["chat"] == "off"


@pytest.mark.skipif(
    not (os.environ.get("HARBOR_LIVE_TESTS") and os.environ.get("OPENROUTER_API_KEY")),
    reason="live: set HARBOR_LIVE_TESTS=1 and OPENROUTER_API_KEY",
)
def test_live_model_answers_from_the_bank(tmp_path, clock, bank):
    app = create_app(
        make_settings(tmp_path, openrouter_api_key=os.environ["OPENROUTER_API_KEY"]), clock=clock, bank=bank
    )
    with TestClient(app) as c:
        maria = make_household(c, "maria")
        res = ask(c, {"X-User-Id": maria["id"]}, "How much money is in my checking and savings combined?")
        assert res.status_code == 200, res.text
        reply, tools = answer(res)
        assert "bank_accounts" in tools and "920" in reply
