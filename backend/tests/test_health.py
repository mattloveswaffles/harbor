from fastapi.testclient import TestClient

from harbor.bank import FakeNessie
from harbor.main import create_app
from tests.conftest import make_settings


class LiveLikeNessie(FakeNessie):
    """FakeNessie that /health treats as the real bank."""

    kind = "nessie"


def live_client(tmp_path, bank, key="test-key"):
    return TestClient(create_app(make_settings(tmp_path, nessie_mode="live", nessie_api_key=key), bank=bank))


def test_health_reports_status(client):
    res = client.get("/health")
    assert res.status_code == 200
    body = res.json()
    assert body == {"ok": True, "mode": "demo", "nessie": "fake", "nhc": "replay", "ai": "off", "clock": "2024-10-06T03:00:00Z"}
    assert res.headers["X-Server-Time"] == "2024-10-06T03:00:00Z"


def test_health_missing_key(tmp_path):
    with live_client(tmp_path, LiveLikeNessie(), key="") as c:
        assert c.get("/health").json()["nessie"] == "missing_key"


def test_health_ok_when_the_seeded_customer_exists(tmp_path):
    bank = LiveLikeNessie()
    with live_client(tmp_path, bank) as c:
        c.post("/api/v1/demo/persona")
        assert c.get("/health").json()["nessie"] == "ok"


def test_health_ok_before_seeding_if_maria_is_in_nessie(tmp_path):
    import asyncio

    bank = LiveLikeNessie()
    asyncio.run(bank.create_customer("Maria", "Lopez (Harbor demo)", {"zip": "33602"}))
    with live_client(tmp_path, bank) as c:
        assert c.get("/health").json()["nessie"] == "ok"


def test_health_degraded_with_a_wrong_key(tmp_path):
    # A wrong key gives an empty bank, not an error.
    with live_client(tmp_path, LiveLikeNessie()) as c:
        assert c.get("/health").json()["nessie"] == "degraded"


def test_health_degraded_when_nessie_is_down(tmp_path):
    bank = LiveLikeNessie()
    bank.down = True
    with live_client(tmp_path, bank) as c:
        assert c.get("/health").json()["nessie"] == "degraded"


def test_unknown_route_uses_error_envelope(client):
    res = client.get("/api/v1/does-not-exist")
    assert res.status_code == 404
    error = res.json()["error"]
    assert error["code"] == "http_404"
    assert "message" in error


def test_openapi_lists_the_h2_8_endpoints(app):
    paths = app.openapi()["paths"]
    for path in (
        "/health",
        "/api/v1/zip/{zip}",
        "/api/v1/users",
        "/api/v1/me",
        "/api/v1/me/household",
        "/api/v1/me/accounts",
        "/api/v1/demo/persona",
        "/api/v1/demo/reset",
        "/api/v1/demo/clock",
    ):
        assert path in paths, path
