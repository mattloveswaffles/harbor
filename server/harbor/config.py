"""App settings, read from environment variables or the repo's .env (see .env.example)."""

from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

SERVER_DIR = Path(__file__).resolve().parents[1]
ENV_FILE = SERVER_DIR.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, env_file_encoding="utf-8", extra="ignore")

    harbor_mode: Literal["demo", "live"] = "demo"

    nessie_api_key: SecretStr = SecretStr("")  # SecretStr keeps the key out of reprs and logs
    nessie_base_url: str = "https://api.nessieisreal.com"

    # Every agent (Ask Harbor, the advisor): OpenRouter through Pydantic AI.
    # LLM_MODEL is a comma-separated list; later models answer when the first one fails.
    openrouter_api_key: SecretStr = SecretStr("")
    llm_model: str = "poolside/laguna-s-2.1:free,nvidia/nemotron-3-super-120b-a12b:free,openrouter/free"

    ors_api_key: str = ""

    database_url: str = f"sqlite:///{(SERVER_DIR / 'harbor.db').as_posix()}"

    # The demo clock waits paused at the Milton replay start until /demo/start
    demo_start: datetime = datetime(2024, 10, 6, 3, 0, tzinfo=UTC)
    demo_speed: float = 1800
    evac_lead_hours: int = 6  # money must be in checking this many hours before tropical-storm winds

    # Storm replays built by tools/fetch_replay.py
    replay_dir: Path = SERVER_DIR / "data" / "replays"
    # The one scheduler job (forecast -> risk); None means 2 s in demo mode, 60 s in live mode
    tick_seconds: float | None = None
    scheduler_enabled: bool = True

    cors_origins: list[str] = ["http://localhost:3000"]
    # The built website (app/: bun run build); served at / when it exists
    site_dir: Path = SERVER_DIR.parent / "app" / "dist"


@lru_cache
def get_settings() -> Settings:
    return Settings()
