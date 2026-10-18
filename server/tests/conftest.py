import os
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

# Importing harbor.main builds a module-level app; keep it away from the real harbor.db and Nessie.
os.environ["DATABASE_URL"] = f"sqlite:///{(Path(tempfile.mkdtemp()) / 'import.db').as_posix()}"
os.environ["HARBOR_MODE"] = "demo"

import pytest
from fastapi.testclient import TestClient

from harbor.clock import DemoClock
from harbor.config import Settings
from harbor.main import create_app
from tests.households import make_household
from tests.nessie_double import NessieDouble

REPLAY_START = datetime(2024, 10, 6, 3, 0, tzinfo=UTC)


class Timer:
    """A fake monotonic clock: tests move real time by hand."""

    def __init__(self):
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


def make_settings(tmp_path, **overrides) -> Settings:
    values = {
        "harbor_mode": "demo",
        "nessie_api_key": "test-key",
        "openrouter_api_key": "",
        "database_url": f"sqlite:///{(tmp_path / 'test.db').as_posix()}",
        "scheduler_enabled": False,  # tests run ticks themselves
        "site_dir": tmp_path / "site",  # empty unless a test builds one
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def fake_open_meteo(url: str, params: dict) -> dict:
    """Hourly weather that builds to a storm peak on the second day."""
    start = datetime.fromisoformat(params["start_date"]).replace(tzinfo=UTC)
    hours = (datetime.fromisoformat(params["end_date"]).replace(tzinfo=UTC) - start).days * 24 + 24
    times = [start + timedelta(hours=h) for h in range(hours)]
    wind = [round(10 + 60 * max(0.0, 1 - abs(h - 40) / 20), 1) for h in range(hours)]
    return {
        "hourly": {
            "time": [t.strftime("%Y-%m-%dT%H:%M") for t in times],
            "wind_speed_10m": wind,
            "wind_gusts_10m": [round(w * 1.4, 1) for w in wind],
            "precipitation": [0.2 if w > 40 else 0.0 for w in wind],
        }
    }


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    """Tests never call Open-Meteo, OSRM or FEMA."""
    monkeypatch.setattr("harbor.sources.weather.fetch", fake_open_meteo)
    monkeypatch.setattr("harbor.sources.weather._cache", {})
    monkeypatch.setattr("harbor.evac.route._live_route", lambda *args: None)
    monkeypatch.setattr("harbor.evac.shelters.fema_shelters", lambda *args, **kw: [])


@pytest.fixture
def timer():
    return Timer()


@pytest.fixture
def clock(timer):
    return DemoClock(REPLAY_START, speed=1800, real=timer)


@pytest.fixture
def bank():
    return NessieDouble()


@pytest.fixture
def app(tmp_path, clock, bank):
    return create_app(make_settings(tmp_path), clock=clock, bank=bank)


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


@pytest.fixture
def maria(client):
    return make_household(client, "maria")


@pytest.fixture
def auth(maria):
    return {"X-User-Id": maria["id"]}
