import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

# Importing harbor.main builds a module-level app; keep it away from the real harbor.db and Nessie.
os.environ["DATABASE_URL"] = f"sqlite:///{(Path(tempfile.mkdtemp()) / 'import.db').as_posix()}"
os.environ["NESSIE_MODE"] = "fake"
os.environ["HARBOR_MODE"] = "demo"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from harbor.bank import FakeNessie  # noqa: E402
from harbor.clock import DemoClock  # noqa: E402
from harbor.config import Settings  # noqa: E402
from harbor.main import create_app  # noqa: E402

REPLAY_START = datetime(2024, 10, 6, 3, 0, tzinfo=timezone.utc)


class Timer:
    """A fake monotonic clock: tests move real time by hand."""

    def __init__(self):
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


def make_settings(tmp_path, **overrides) -> Settings:
    values = {
        "harbor_mode": "demo",
        "nessie_mode": "fake",
        "nessie_api_key": "",
        "anthropic_api_key": "",
        "database_url": f"sqlite:///{(tmp_path / 'test.db').as_posix()}",
        "scheduler_enabled": False,  # tests run ticks themselves
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


@pytest.fixture
def timer():
    return Timer()


@pytest.fixture
def clock(timer):
    return DemoClock(REPLAY_START, speed=1800, real=timer)


@pytest.fixture
def bank():
    return FakeNessie()


@pytest.fixture
def app(tmp_path, clock, bank):
    return create_app(make_settings(tmp_path), clock=clock, bank=bank)


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


@pytest.fixture
def maria(client):
    res = client.post("/api/v1/demo/persona", json={"persona": "maria"})
    assert res.status_code == 200, res.text
    return res.json()


@pytest.fixture
def auth(maria):
    return {"X-User-Id": maria["id"]}
