"""App settings, read from environment variables or backend/.env."""

from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]
ENV_FILE = BACKEND_DIR / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, env_file_encoding="utf-8", extra="ignore")

    harbor_mode: Literal["demo", "live"] = "demo"

    nessie_mode: Literal["live", "fake"] = "live"
    nessie_api_key: SecretStr = SecretStr("")  # SecretStr keeps the key out of reprs and logs
    nessie_base_url: str = "https://api.nessieisreal.com"

    anthropic_api_key: str = ""
    harbor_model: str = "claude-opus-5-5"

    ors_api_key: str = ""
    gsa_api_key: str = ""
    noaa_user_agent: str = "Harbor hackathon project"

    database_url: str = f"sqlite:///{(BACKEND_DIR / 'harbor.db').as_posix()}"

    # The demo clock waits paused at the Milton replay start until /demo/start
    demo_start: datetime = datetime(2024, 10, 6, 3, 0, tzinfo=timezone.utc)
    demo_speed: float = 1800
    demo_cancel_window_s: int = 20
    evac_lead_hours: int = 6  # money must be in checking this many hours before tropical-storm winds

    # Storm replays built by tools/fetch_replay.py
    replay_dir: Path = BACKEND_DIR / "data" / "replays"
    # The one scheduler job (forecast -> risk); None means 2 s in demo mode, 60 s in live mode
    tick_seconds: float | None = None
    scheduler_enabled: bool = True

    cors_origins: list[str] = ["http://localhost:3000"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
