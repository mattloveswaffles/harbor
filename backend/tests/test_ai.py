"""AI plan review, explain and the AI-offline toggle. The Anthropic client is a fake: no real calls.

The point of every test here: Claude can change words, never numbers. Amounts, move ids and
alternatives come from the rules engine's facts; a forged number sends the template instead.
"""

import json
import re
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from tests.conftest import make_settings
from harbor.ai import claude
from harbor.ai.explain import OFF_TOPIC, REFUSAL, ExplainText, is_advice_request
from harbor.ai.guard import validate
from harbor.ai.review import LABEL, ReviewText, plan_context, review_texts, template_text
from harbor.main import create_app
from harbor.models import Plan, User
from harbor.planning import active_plan

API = "/api/v1"
MODEL = "claude-opus-5-5"


class FakeClaude:
    """Stands in for anthropic.Anthropic: `client.beta.messages.parse(**kwargs)`.

    `script` is a list of answers used in order; each is a callable(kwargs) returning the parsed
    output, an Exception to raise, or a ready response namespace.
    """

    def __init__(self, *script):
        self.script = list(script)
        self.calls: list[dict] = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(parse=self.parse))

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        if not self.script:
            raise AssertionError("Claude was called more often than the test expected")
        step = self.script.pop(0)
        if isinstance(step, Exception):
            raise step
        if isinstance(step, SimpleNamespace):
            return step
        return SimpleNamespace(stop_reason="end_turn", parsed_output=step(kwargs), model=kwargs["model"])


def tag(kwargs, name):
    text = kwargs["messages"][0]["content"]
    return json.loads(re.search(rf"<{name}>(.*?)</{name}>", text, re.S).group(1))


def good_review(summary="Your family has a calm plan. The money is ready before you need to leave.", **edits):
    """A valid ReviewText for whatever plan is in the prompt, written without any numbers."""
    def build(kwargs):
        ctx, facts = tag(kwargs, "context"), tag(kwargs, "plan_facts")
        data = {
            "summary": summary,
            "per_source": [{"source": r["source"], "move_id": r["move_id"],
                            "reasoning": f"Claude says {r['source']} is used in this order."} for r in ctx["per_source"]],
            "alternatives": [{"alt_id": a["id"], "why_consider": "It avoids a step.", "tradeoff": "It costs more."}
                             for a in facts["alternatives"]],
            "risks": [{"kind": "settlement", "text": "The sale needs a business day to settle."}],
            "double_check": ["Is the money in checking already set aside for a bill?"],
        }
        data.update(edits)
        return ReviewText(**data)
    return build


@pytest.fixture
def ai_app(tmp_path, clock, bank):
    # A placeholder key: the fake client never sends it anywhere.
    app = create_app(make_settings(tmp_path, anthropic_api_key="test-key-not-real"), clock=clock, bank=bank)
    app.state.anthropic_client = FakeClaude()
    return app


@pytest.fixture
def ai_client(ai_app):
    with TestClient(ai_app) as c:
        yield c


@pytest.fixture
def ai_auth(ai_client):
    maria = ai_client.post(f"{API}/demo/persona").json()
    ai_client.post(f"{API}/demo/start")  # Tampa reaches act at once: the plan exists
    return {"X-User-Id": maria["id"]}


def script(app, *steps) -> FakeClaude:
    app.state.anthropic_client = FakeClaude(*steps)
    return app.state.anthropic_client


def amounts(review):
    return [(s["source"], s["move_id"], s["amount_cents"]) for s in review["per_source"]]


def plan_facts_and_ctx(app, user_id):
    with Session(app.state.engine) as s:
        user = s.get(User, user_id)
        plan = active_plan(s, user_id)
        return plan_context(app, s, user, plan, app.state.clock.now())


# --- Review: template ----------------------------------------------------------------------------

def test_review_without_a_key_is_the_template(client, auth, app):
    client.post(f"{API}/demo/start")
    fake = app.state.anthropic_client = FakeClaude()  # must never be called
    res = client.get(f"{API}/me/plan/review", headers=auth)
    assert res.status_code == 200, res.text
    review = res.json()
    plan = client.get(f"{API}/me/plan", headers=auth).json()["plan"]
    assert review["generated_by"] == "template" and review["validated"] is True and review["label"] == LABEL
    assert review["plan_id"] == plan["id"] and review["plan_version"] == plan["version"]
    assert fake.calls == []
    # Every amount is the plan's own.
    s = plan["sources"]
    by_source = {}
    for row in review["per_source"]:
        by_source[row["source"]] = by_source.get(row["source"], 0) + row["amount_cents"]
    assert by_source == {"checking": s["already_in_checking_cents"], "savings": s["from_savings_cents"],
                         "etf_sale": s["from_etf_sales_cents"]}
    move_ids = {m["id"] for m in plan["moves"]}
    assert all(r["move_id"] in move_ids for r in review["per_source"] if r["source"] != "checking")
    assert {a["alt_id"] for a in review["alternatives"]} == {a["id"] for a in plan["alternatives"]}
    assert any(r["kind"] == "settlement" for r in review["risks"])
    assert review["household_notes"] and all(n["source_url"].startswith("https://") for n in review["household_notes"])
    assert review["lodging_comments"] and all("confirm" in c["comment"] for c in review["lodging_comments"])


def test_template_text_only_uses_numbers_from_the_facts(client, auth, app, maria):
    client.post(f"{API}/demo/start")
    ctx = plan_facts_and_ctx(app, maria["id"])
    assert validate(review_texts(template_text(ctx)), ctx.snapshot) == []


def test_review_needs_a_plan(client, auth):
    res = client.get(f"{API}/me/plan/review", headers=auth)
    assert res.status_code == 404 and res.json()["error"]["code"] == "plan_not_found"


# --- Review: Claude ------------------------------------------------------------------------------

def test_claude_review_passes_and_the_request_is_built_right(ai_client, ai_auth, ai_app):
    ai_app.state.ai_enabled = False
    template = ai_client.get(f"{API}/me/plan/review", headers=ai_auth).json()
    ai_app.state.ai_enabled = True
    fake = script(ai_app, good_review())
    review = ai_client.get(f"{API}/me/plan/review", headers=ai_auth).json()
    assert review["generated_by"] == MODEL and review["validated"] is True
    assert review["summary"].startswith("Your family has a calm plan")
    assert all(r["reasoning"].startswith("Claude says") for r in review["per_source"])
    assert amounts(review) == amounts(template)  # same numbers, only words changed

    (call,) = fake.calls
    assert call["model"] == MODEL
    assert call["output_format"] is ReviewText
    assert call["output_config"] == {"effort": "low"}
    assert call["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert call["fallbacks"] == "default" and call["betas"] == [claude.FALLBACK_BETA]
    assert 0 < call["timeout"] <= claude.TIME_BUDGET_S
    prompt = call["messages"][0]["content"]
    assert "<plan_facts>" in prompt and "Maria" not in prompt and "nessie" not in prompt.lower()


def test_a_forged_number_is_rejected_and_the_template_is_used(ai_client, ai_auth, ai_app):
    forged = good_review(summary="Harbor will gather $9,999 for your trip.")
    fake = script(ai_app, forged, forged)  # one regeneration, then the template
    review = ai_client.get(f"{API}/me/plan/review", headers=ai_auth).json()
    assert len(fake.calls) == 2
    assert review["generated_by"] == "template" and "9,999" not in json.dumps(review)


def test_a_forged_number_then_a_clean_answer_uses_claude(ai_client, ai_auth, ai_app):
    fake = script(ai_app, good_review(summary="You need 17 nights away."), good_review())
    review = ai_client.get(f"{API}/me/plan/review", headers=ai_auth).json()
    assert len(fake.calls) == 2 and review["generated_by"] == MODEL


def test_numbers_from_the_facts_are_allowed(ai_client, ai_auth, ai_app):
    plan = ai_client.get(f"{API}/me/plan", headers=ai_auth).json()["plan"]
    total = plan["budget"]["total_cents"] // 100
    script(ai_app, good_review(summary=f"The plan gathers ${total:,} so your family can leave on time."))
    review = ai_client.get(f"{API}/me/plan/review", headers=ai_auth).json()
    assert review["generated_by"] == MODEL and f"${total:,}" in review["summary"]


@pytest.mark.parametrize("bad", [
    good_review(per_source=[]),                                    # skips the plan's sources
    good_review(alternatives=[{"alt_id": "alt_made_up", "why_consider": "x", "tradeoff": "y"}]),
    good_review(summary="x" * 900),                                # too long
])
def test_a_badly_shaped_answer_falls_back(ai_client, ai_auth, ai_app, bad):
    script(ai_app, bad, bad)
    assert ai_client.get(f"{API}/me/plan/review", headers=ai_auth).json()["generated_by"] == "template"


@pytest.mark.parametrize("failure", [
    TimeoutError("read timed out"),
    SimpleNamespace(stop_reason="refusal", parsed_output=None, model=MODEL),
    SimpleNamespace(stop_reason="end_turn", parsed_output=None, model=MODEL),
])
def test_errors_and_refusals_fall_back_to_the_template(ai_client, ai_auth, ai_app, failure):
    script(ai_app, failure, failure)
    review = ai_client.get(f"{API}/me/plan/review", headers=ai_auth).json()
    assert review["generated_by"] == "template" and review["per_source"]


def test_a_failure_is_not_retried_straight_away(ai_client, ai_auth, ai_app):
    fake = script(ai_app, TimeoutError(), TimeoutError())
    ai_client.get(f"{API}/me/plan/review", headers=ai_auth)
    ai_client.get(f"{API}/me/plan/review", headers=ai_auth)  # no new call: the fake would raise
    assert len(fake.calls) == 2


def test_claude_review_is_cached_per_plan_version(ai_client, ai_auth, ai_app):
    fake = script(ai_app, good_review())
    first = ai_client.get(f"{API}/me/plan/review", headers=ai_auth).json()
    second = ai_client.get(f"{API}/me/plan/review", headers=ai_auth).json()
    assert len(fake.calls) == 1 and first == second
    plan = ai_client.get(f"{API}/me/plan", headers=ai_auth).json()["plan"]
    assert set(plan["ai"]) == {"source", "model", "validated"}  # the cache and facts stay internal
    # A new plan version is a new review.
    with Session(ai_app.state.engine) as s:
        row = s.get(Plan, plan["id"])
        row.version += 1
        s.add(row)
        s.commit()
    script(ai_app, good_review(summary="A fresh review for the new version."))
    assert ai_client.get(f"{API}/me/plan/review", headers=ai_auth).json()["summary"].startswith("A fresh review")


def test_the_ai_offline_toggle_keeps_the_numbers(ai_client, ai_auth, ai_app):
    script(ai_app, good_review())
    with_ai = ai_client.get(f"{API}/me/plan/review", headers=ai_auth).json()
    plan_before = ai_client.get(f"{API}/me/plan", headers=ai_auth).json()["plan"]

    res = ai_client.post(f"{API}/demo/ai", json={"enabled": False})
    assert res.json() == {"enabled": False, "ai": "off"}
    assert ai_client.get("/health").json()["ai"] == "off"
    without = ai_client.get(f"{API}/me/plan/review", headers=ai_auth).json()
    plan_after = ai_client.get(f"{API}/me/plan", headers=ai_auth).json()["plan"]
    assert without["generated_by"] == "template" and with_ai["generated_by"] == MODEL
    assert amounts(without) == amounts(with_ai)
    assert {k: v for k, v in plan_after.items() if k != "server_time"} == \
           {k: v for k, v in plan_before.items() if k != "server_time"}

    assert ai_client.post(f"{API}/demo/ai", json={"enabled": True}).json() == {"enabled": True, "ai": "ok"}
    assert ai_client.get(f"{API}/me/plan/review", headers=ai_auth).json()["generated_by"] == MODEL  # cached


def test_toggle_on_without_a_key_stays_off(client):
    assert client.post(f"{API}/demo/ai", json={"enabled": True}).json() == {"enabled": True, "ai": "off"}


def test_deadline_runs_out():
    with pytest.raises(claude.AIUnavailable):
        claude.Deadline(0.5).remaining()


# --- Explain -------------------------------------------------------------------------------------

def ask(c, auth, question, **extra):
    return c.post(f"{API}/me/plan/explain", headers=auth, json={"question": question, **extra})


@pytest.mark.parametrize("question", [
    "Should I put the leftover in Tesla?",
    "should i buy TSLA with the leftover?",
    "Is TCAF a good fund?",
    "Which stock should I buy after the storm?",
    "Will TBUX go up next week?",
    "Can you recommend an ETF for me?",
])
def test_advice_questions_are_detected(question):
    assert is_advice_request(question)


@pytest.mark.parametrize("question", [
    "Why sell TBUX and not TCAF?",
    "What is T+1 settlement?",
    "Is the river going down?",
    "Why put the savings into checking first?",
    "When do I need to approve?",
])
def test_plan_questions_are_not_advice(question):
    assert not is_advice_request(question)


def test_advice_gets_the_fixed_refusal_without_calling_claude(ai_client, ai_auth, ai_app):
    fake = script(ai_app)
    body = ask(ai_client, ai_auth, "Should I put the leftover in Tesla?").json()
    assert body["category"] == "personal_advice_request" and body["answer"] == REFUSAL
    assert fake.calls == [] and body["suggested_questions"]


def test_claude_spotting_advice_still_gets_the_fixed_refusal(ai_client, ai_auth, ai_app):
    script(ai_app, lambda kw: ExplainText(category="personal_advice_request", answer="Sure, buy some Amazon."))
    body = ask(ai_client, ai_auth, "Is now a smart moment to grab some Amazon?").json()
    assert body["category"] == "personal_advice_request" and body["answer"] == REFUSAL
    assert "Amazon" not in body["answer"]


def test_claude_off_topic_gets_fixed_text(ai_client, ai_auth, ai_app):
    script(ai_app, lambda kw: ExplainText(category="off_topic", answer="Paris is sunny."))
    body = ask(ai_client, ai_auth, "What's the weather in Paris?").json()
    assert body["category"] == "off_topic" and body["answer"] == OFF_TOPIC


def test_claude_explains_with_numbers_from_the_facts(ai_client, ai_auth, ai_app):
    def answer(kw):
        sale = next(m for m in tag(kw, "plan_facts")["moves"] if m["kind"] == "sell_etf")
        assert "<question>Why sell TBUX and not TCAF?</question>" in kw["messages"][0]["content"]
        return ExplainText(category="plan_explanation",
                           answer=f"TBUX is the storm sleeve, so it's sold first: {sale['shares']} shares.")
    fake = script(ai_app, answer)
    body = ask(ai_client, ai_auth, "Why sell TBUX and not TCAF?").json()
    assert body["ai"] == {"source": "claude", "model": MODEL, "validated": True}
    assert body["category"] == "plan_explanation" and "storm sleeve" in body["answer"]
    ask(ai_client, ai_auth, "why sell TBUX and not TCAF")  # same question: cached, no second call
    assert len(fake.calls) == 1


def test_a_forged_number_in_an_answer_falls_back(ai_client, ai_auth, ai_app):
    forged = lambda kw: ExplainText(category="plan_explanation", answer="You will make $9,999 on this sale.")  # noqa: E731
    script(ai_app, forged, forged)
    body = ask(ai_client, ai_auth, "Why sell TBUX and not TCAF?").json()
    assert body["ai"]["source"] == "template" and "9,999" not in body["answer"] and "TBUX" in body["answer"]


def test_template_answers_without_ai(client, auth):
    client.post(f"{API}/demo/start")
    plan = client.get(f"{API}/me/plan", headers=auth).json()["plan"]
    cases = {
        "Why sell TBUX and not TCAF?": "plan_explanation",
        "What does T+1 mean?": "general_education",
        "When do I need to approve?": "plan_explanation",
        "What happens if I cancel?": "plan_explanation",
        "What's the weather in Paris?": "off_topic",
    }
    for question, category in cases.items():
        body = ask(client, auth, question).json()
        assert body["category"] == category, question
        assert body["ai"] == {"source": "template", "model": None, "validated": True}
    sale = next(m for m in plan["moves"] if m["kind"] == "sell_etf")
    body = ask(client, auth, "Why this one?", move_id=sale["id"]).json()
    assert body["category"] == "plan_explanation" and f"${sale['amount_cents'] / 100:,.2f}" in body["answer"]


def test_explain_input_errors(client, auth):
    assert ask(client, auth, "Why?").json()["error"]["code"] == "plan_not_found"
    client.post(f"{API}/demo/start")
    res = ask(client, auth, "x" * 501)
    assert res.status_code == 422 and res.json()["error"]["code"] == "validation_error"
    res = ask(client, auth, "Why?", move_id="mv_nope")
    assert res.status_code == 404 and res.json()["error"]["code"] == "move_not_found"


def test_explain_is_limited_to_ten_a_minute(client, auth):
    client.post(f"{API}/demo/start")
    for _ in range(10):
        assert ask(client, auth, "What is T+1?").status_code == 200
    res = ask(client, auth, "What is T+1?")
    assert res.status_code == 429 and res.json()["error"]["code"] == "rate_limited"
    assert int(res.headers["Retry-After"]) >= 1
