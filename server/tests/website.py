"""Website: the built React app is served next to the API, with deep links falling back to index.html."""

import pytest
from fastapi.testclient import TestClient

from harbor.main import create_app
from tests.conftest import make_settings


@pytest.fixture
def site(tmp_path, clock, bank):
    pages = tmp_path / "site"
    pages.mkdir()
    (pages / "index.html").write_text("<div id=root></div>")
    (pages / "chunk-1a2b.js").write_text("console.log(1)")
    with TestClient(create_app(make_settings(tmp_path), clock=clock, bank=bank)) as c:
        yield c


@pytest.mark.parametrize("path", ["/", "/how-it-works", "/app", "/app/plan", "/anything/else"])
def test_routes_get_the_app(site, path):
    res = site.get(path)
    assert res.status_code == 200
    assert res.text == "<div id=root></div>"


def test_assets(site):
    assert site.get("/chunk-1a2b.js").text == "console.log(1)"
    assert site.get("/missing.js").status_code == 404


def test_api_still_wins(site):
    assert site.get("/health").json()["ok"] is True
    assert site.get("/api/v1/demo/clock").status_code == 200
    assert site.get("/api/v1/nope").status_code == 404


def test_no_site_built(client):
    assert client.get("/").status_code == 404
    assert client.get("/health").status_code == 200
