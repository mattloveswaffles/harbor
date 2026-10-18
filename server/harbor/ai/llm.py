"""The one LLM behind every agent (Ask Harbor and the advisor): OpenRouter through Pydantic AI.

OPENROUTER_API_KEY and LLM_MODEL configure it. LLM_MODEL is a comma-separated list: the first model answers,
the rest take over when it fails. The demo AI toggle turns every agent off; tests set app.state.llm_model.
"""

from __future__ import annotations

from pydantic_ai.models import Model
from pydantic_ai.models.fallback import FallbackModel
from pydantic_ai.models.openrouter import OpenRouterModel
from pydantic_ai.providers.openrouter import OpenRouterProvider

TIME_BUDGET_S = 90.0  # per answer; free models are slow


def model(app) -> Model | None:
    """The configured model, made once per app; None without a key or with the AI toggle off."""
    if not getattr(app.state, "ai_enabled", True):
        return None
    if getattr(app.state, "llm_model", None) is None:
        settings = app.state.settings
        key = settings.openrouter_api_key.get_secret_value()
        if not key:
            return None
        provider = OpenRouterProvider(api_key=key, app_title="Harbor")
        models = [
            # every model may be asked for a JSON schema; OpenRouter routes to providers that honour it
            OpenRouterModel(
                name, provider=provider, profile=provider.model_profile(name) | {"supports_json_schema_output": True}
            )
            for name in (n.strip() for n in settings.llm_model.split(","))
        ]
        app.state.llm_model = models[0] if len(models) == 1 else FallbackModel(*models)
    return app.state.llm_model


def ai_enabled(app) -> bool:
    return model(app) is not None
