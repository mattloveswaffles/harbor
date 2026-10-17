"""The one place Harbor calls the Claude API.

Claude only writes text. The caller passes a Pydantic model for structured output, and every
result goes through `guard.guarded` (numbers must come from the plan facts) before anyone sees it.

- Key: only from ANTHROPIC_API_KEY (settings). No key, or the demo "AI offline" toggle, means no call.
- Model: settings.harbor_model (claude-opus-5-5). Thinking is always on for Opus 5.5; effort `low`
  keeps it quick.
- Time: one 20 s budget per answer, shared by the first try and the one regeneration, so a request
  never waits longer than that before the template takes over.
- The static system prompt carries `cache_control`. Caching only applies above the model's minimum
  prefix length, so short prompts simply aren't cached; that's fine.
- `fallbacks: "default"`: if a safety classifier declines, the API retries on Anthropic's
  recommended fallback model inside the same call. A refusal that survives that raises, and the
  caller uses the template.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from typing import Any, TypeVar

from pydantic import BaseModel

log = logging.getLogger("harbor.ai")

T = TypeVar("T", bound=BaseModel)

TIME_BUDGET_S = 20.0
MAX_TOKENS = 8000
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class AIUnavailable(Exception):
    """Claude gave no usable answer (refusal, empty output, out of time)."""


def has_key(app) -> bool:
    return bool(app.state.settings.anthropic_api_key)


def ai_enabled(app) -> bool:
    """True when Harbor may call Claude: a key is set and the demo toggle is on."""
    return has_key(app) and getattr(app.state, "ai_enabled", True)


_client_lock = threading.Lock()


def get_client(app):
    """The Anthropic client, made on first use. Tests put a fake on app.state.anthropic_client."""
    with _client_lock:
        if getattr(app.state, "anthropic_client", None) is None:
            import anthropic

            app.state.anthropic_client = anthropic.Anthropic(
                api_key=app.state.settings.anthropic_api_key, timeout=TIME_BUDGET_S, max_retries=0,
            )
        return app.state.anthropic_client


def model_id(app) -> str:
    return app.state.settings.harbor_model


class Deadline:
    def __init__(self, seconds: float = TIME_BUDGET_S):
        self.end = time.monotonic() + seconds

    def remaining(self) -> float:
        left = self.end - time.monotonic()
        if left < 1.0:
            raise AIUnavailable("the 20 s AI time budget is used up")
        return left


def ask(app, *, system: str, user: str, output: type[T], deadline: Deadline) -> T:
    """One structured-output call. Raises on refusal, empty output or timeout (guarded falls back)."""
    client = get_client(app)
    response = client.beta.messages.parse(
        model=model_id(app),
        max_tokens=MAX_TOKENS,
        system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user}],
        output_format=output,
        output_config={"effort": "low"},
        betas=[FALLBACK_BETA],
        fallbacks="default",
        timeout=deadline.remaining(),
    )
    if response.stop_reason == "refusal":
        raise AIUnavailable("Claude declined to answer")
    if response.stop_reason == "max_tokens":
        raise AIUnavailable("Claude's answer was cut off")
    parsed = getattr(response, "parsed_output", None)
    if parsed is None:
        raise AIUnavailable("Claude returned no structured output")
    return parsed


def audit(kind: str, prompt: str, source: str, violations: list[str], error: str | None) -> None:
    """Every AI answer is logged as (input hash, result, validation): never the key, never a name."""
    digest = hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16]
    log.info("ai %s input=%s source=%s violations=%s error=%s", kind, digest, source, violations, error)


def facts_json(data: Any) -> str:
    """Stable JSON for prompts (sorted keys, so identical facts give identical prompts)."""
    return json.dumps(data, sort_keys=True, ensure_ascii=False, default=str)
