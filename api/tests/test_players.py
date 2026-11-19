"""Integration tests: need Postgres up (docker compose) and `gully-pipeline load` run."""

import os
import time

import psycopg
import pytest
from fastapi.testclient import TestClient

from gully_api.main import app
from gully_api.settings import settings


def _db_loaded() -> bool:
    try:
        with psycopg.connect(settings.database_url, connect_timeout=2) as c:
            return c.execute("SELECT count(*) FROM players").fetchone()[0] > 0
    except Exception:
        return False


# Locally these skip without a loaded database; the integration workflow sets
# REQUIRE_DB=1 so a missing database fails loudly instead of skipping silently.
if os.environ.get("REQUIRE_DB") and not _db_loaded():
    raise RuntimeError("REQUIRE_DB is set but Postgres is not reachable or not loaded")
pytestmark = pytest.mark.skipif(not _db_loaded(), reason="Postgres not running or not loaded")


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_search_fuzzy_surname(client):
    r = client.get("/api/v1/players", params={"q": "kohli"})
    assert r.status_code == 200
    top = r.json()["items"][0]
    assert top["name"] == "V Kohli" and top["country"] == "India"


def test_search_by_full_name(client):
    """Cricsheet says "RG Sharma"; fans type "Rohit Sharma". Two lesser players are
    literally named Rohit Sharma, so ties must go to the one with more matches."""
    top = client.get("/api/v1/players", params={"q": "rohit sharma"}).json()["items"][0]
    assert top["name"] == "RG Sharma" and top["full_name"] == "Rohit Sharma"
    top = client.get("/api/v1/players", params={"q": "virat"}).json()["items"][0]
    assert top["name"] == "V Kohli"


def test_search_typo(client):
    r = client.get("/api/v1/players", params={"q": "bumrha"})
    names = [p["name"] for p in r.json()["items"][:5]]
    assert "JJ Bumrah" in names


def test_search_filters_with_format_stats(client):
    r = client.get("/api/v1/players",
                   params={"format": "Test", "role": "BOWL", "country": "England", "limit": 5})
    body = r.json()
    assert body["total"] > 5
    top = body["items"][0]
    assert top["name"] == "JM Anderson" and top["wickets"] > 600
    assert all(p["role"] == "BOWL" for p in body["items"])


def test_search_sort_by_runs_and_wickets(client):
    runs = client.get("/api/v1/players", params={"format": "IPL", "sort": "runs", "limit": 3}).json()["items"]
    assert runs[0]["name"] == "V Kohli" and runs[0]["runs"] >= runs[1]["runs"] >= runs[2]["runs"]
    wkts = client.get("/api/v1/players", params={"format": "IPL", "sort": "wickets", "limit": 2}).json()["items"]
    assert wkts[0]["name"] == "YS Chahal"
    assert client.get("/api/v1/players", params={"sort": "sixes"}).status_code == 422


def test_search_validation(client):
    assert client.get("/api/v1/players", params={"format": "Hundred"}).status_code == 422
    assert client.get("/api/v1/players", params={"q": "k"}).status_code == 422


def test_profile(client):
    pid = client.get("/api/v1/players", params={"q": "kohli"}).json()["items"][0]["id"]
    r = client.get(f"/api/v1/players/{pid}")
    assert r.status_code == 200
    body = r.json()
    test = next(f for f in body["formats"] if f["format"] == "Test")
    assert (test["matches"], test["runs"]) == (123, 9230)
    assert {s["format"] for s in body["seasons"]} >= {"Test", "ODI", "IPL"}
    assert {p["phase"] for p in body["phases"]} == {"PP", "middle", "death"}

    ipl = client.get(f"/api/v1/players/{pid}", params={"format": "IPL"}).json()
    assert {s["format"] for s in ipl["seasons"]} == {"IPL"}
    assert len(ipl["formats"]) == len(body["formats"])


def test_profile_404(client):
    assert client.get("/api/v1/players/nope").status_code == 404


def test_fast_enough(client):
    # Plan goal: lookups feel instant. Generous bound for a cold local DB.
    t0 = time.perf_counter()
    for q in ("smith", "sharma", "khan", "de villiers"):
        assert client.get("/api/v1/players", params={"q": q}).status_code == 200
    assert (time.perf_counter() - t0) / 4 < 0.5
