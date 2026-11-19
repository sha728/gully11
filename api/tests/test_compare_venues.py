"""Integration tests for /compare, /venues and the richer profile.
Need Postgres up and `gully-pipeline load` run; skipped otherwise."""

import pytest
from fastapi.testclient import TestClient

from gully_api.main import app
from test_players import _db_loaded

pytestmark = pytest.mark.skipif(not _db_loaded(), reason="Postgres not running or not loaded")


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def pid(client, q, fmt=None):
    params = {"q": q, **({"format": fmt} if fmt else {})}
    return client.get("/api/v1/players", params=params).json()["items"][0]["id"]


def test_compare_career_and_year_range(client):
    kohli, smith = pid(client, "kohli"), pid(client, "steve smith", "Test")
    r = client.get("/api/v1/compare", params={"a": kohli, "b": smith, "format": "Test"})
    assert r.status_code == 200
    k, s = r.json()["players"]
    assert k["name"] == "V Kohli" and k["totals"]["runs"] == 9230
    metrics = {m["key"]: m for m in k["metrics"]}
    assert metrics["bat_avg"]["value"] == pytest.approx(46.85, abs=0.01)
    assert 80 < metrics["bat_avg"]["percentile"] <= 100      # elite among 500+ ball batters
    assert metrics["bowl_econ"]["higher_is_better"] is False
    ranged = client.get("/api/v1/compare", params={"a": kohli, "b": smith, "format": "Test",
                                                   "from_year": 2016, "to_year": 2019}).json()
    assert 0 < ranged["players"][0]["totals"]["runs"] < 9230


def test_compare_bowler_percentiles_and_errors(client):
    bumrah, kohli = pid(client, "bumrah"), pid(client, "kohli")
    r = client.get("/api/v1/compare", params={"a": bumrah, "b": kohli, "format": "IPL"}).json()
    b = {m["key"]: m for m in r["players"][0]["metrics"]}
    assert b["bowl_econ"]["percentile"] > 80   # among the most economical (early-era bowlers rank higher)
    assert client.get("/api/v1/compare", params={"a": "nope", "b": kohli, "format": "IPL"}).status_code == 404
    assert client.get("/api/v1/compare", params={"a": bumrah, "b": kohli, "format": "IPL",
                                                 "from_year": 2020, "to_year": 2010}).status_code == 422


def test_venues(client):
    hits = client.get("/api/v1/venues", params={"q": "chinnaswamy"}).json()
    assert hits[0]["id"] == "m-chinnaswamy-stadium"
    page = client.get("/api/v1/venues/m-chinnaswamy-stadium").json()
    fmts = {f["format"]: f for f in page["formats"]}
    assert fmts["IPL"]["matches"] > 90 and 150 < fmts["IPL"]["avg_first_innings"] < 220
    assert page["top_batters"][0]["name"] == "V Kohli"       # leaders default to most-played format
    delhi = client.get("/api/v1/venues/arun-jaitley-stadium").json()
    assert {f["format"]: f for f in delhi["formats"]}["IPL"]["matches"] > 100   # Kotla merged in
    assert client.get("/api/v1/venues/nowhere").status_code == 404


def test_profile_has_dismissals_and_venues(client):
    kohli = pid(client, "kohli")
    p = client.get(f"/api/v1/players/{kohli}", params={"format": "IPL"}).json()
    assert p["dismissals"][0]["kind"] == "caught"
    assert p["venues"][0]["venue_name"] == "M Chinnaswamy Stadium"
    assert all(v["format"] == "IPL" for v in p["venues"])
    assert "exp_sixes" not in p["phases"][0]      # simulator-only columns stay out of the API
