"""XI Builder integration tests (need the loaded database, like test_players)."""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from gully_api.main import app
from gully_api.xi import service
from test_players import _db_loaded
from xi_helpers import auto_draft

pytestmark = pytest.mark.skipif(not _db_loaded(), reason="Postgres not running or not loaded")
FORMATS = ["Test", "ODI", "T20I", "IPL"]


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def spin(client, fmt, seed):
    r = client.post("/api/v1/xi/spin", json={"format": fmt, "seed": seed})
    assert r.status_code == 200
    return r.json()["spins"]


@pytest.mark.parametrize("fmt", FORMATS)
def test_spins_are_seeded_and_draftable(client, fmt):
    s1, s2 = spin(client, fmt, 123), spin(client, fmt, 123)
    assert s1 == s2 and len(s1) == 11
    assert spin(client, fmt, 124) != s1
    for s in s1:
        assert s["era"] in service.FORMATS[fmt].eras
        assert len(s["candidates"]) >= service.MIN_CANDIDATES
    picks = auto_draft(s1, 4 if fmt == "IPL" else None)
    assert len(set(picks)) == 11


@pytest.mark.parametrize("fmt", FORMATS)
def test_world_xis_obey_the_draft_rules(client, fmt):
    from gully_api import db
    with db._pool.connection() as conn:
        cfg = service.WORLD_XI[fmt]
        prof = service.profiles(conn, fmt, cfg["players"])
        rows = []
        for pid in cfg["players"]:
            if pid.startswith("L-"):
                r = conn.execute("SELECT cricsheet_id, role, country FROM legends WHERE id = %s LIMIT 1",
                                 (pid,)).fetchone()
                rows.append({"person": r["cricsheet_id"] or pid, "role": r["role"], "country": r["country"]})
            else:
                r = conn.execute("SELECT role, country FROM players WHERE id = %s", (pid,)).fetchone()
                rows.append({"person": pid, "role": r["role"], "country": r["country"]})
        service.check_rules(fmt, rows)
        assert len(prof) == 11 and cfg["keeper"] in cfg["players"]


def test_series_is_deterministic_saved_and_shareable(client):
    s = spin(client, "IPL", 99)
    picks = auto_draft(s, 4)
    a = client.post("/api/v1/xi/series", json={"format": "IPL", "seed": 99, "picks": picks}).json()
    b = client.post("/api/v1/xi/series", json={"format": "IPL", "seed": 99, "picks": picks}).json()
    assert a["slug"] == b["slug"] and a["result"] == b["result"] and a["matches"] == b["matches"]
    r = a["result"]
    assert r["won"] + r["lost"] + r["drawn"] + r["tied"] == 5
    saved = client.get(f"/api/v1/xi/challenge/{a['slug']}").json()
    assert saved["picks"] == picks and saved["spins"] == s and saved["result"] == r
    m = client.get(f"/api/v1/xi/challenge/{a['slug']}/match/1").json()
    assert m["commentary"] and len(m["innings"]) == 2


def test_test_series_runs(client):
    s = spin(client, "Test", 5)
    out = client.post("/api/v1/xi/series", json={"format": "Test", "seed": 5, "picks": auto_draft(s)}).json()
    assert out["opponent"] == "All-time Test XI"
    assert all(2 <= len(m["scores"]) <= 4 for m in out["matches"])


def test_draft_rules_are_enforced(client):
    s = spin(client, "ODI", 11)
    picks = auto_draft(s)
    bad = picks[:]
    bad[0] = "not-a-player"
    r = client.post("/api/v1/xi/series", json={"format": "ODI", "seed": 11, "picks": bad})
    assert r.status_code == 422 and "isn't on the" in r.json()["detail"]
    r = client.post("/api/v1/xi/series", json={"format": "ODI", "seed": 11, "picks": picks[:10]})
    assert r.status_code == 422


def test_rules_unit():
    ok = [{"person": str(i), "role": r, "country": "India"}
          for i, r in enumerate(["BAT"] * 5 + ["WK"] + ["BOWL"] * 5)]
    service.check_rules("IPL", ok)
    with pytest.raises(service.DraftError, match="wicketkeeper"):
        service.check_rules("ODI", [dict(r, role="BAT") if r["role"] == "WK" else r for r in ok])
    with pytest.raises(service.DraftError, match="five bowling"):
        service.check_rules("ODI", [dict(r, role="BAT") if i == 6 else r for i, r in enumerate(ok)])
    with pytest.raises(service.DraftError, match="twice"):
        service.check_rules("ODI", ok[:10] + [dict(ok[0])])
    os5 = [dict(r, country="Australia") if i < 5 else r for i, r in enumerate(ok)]
    with pytest.raises(service.DraftError, match="overseas"):
        service.check_rules("IPL", os5)
    service.check_rules("ODI", os5)                              # overseas cap is IPL-only


def test_daily_and_errors(client):
    d = client.get("/api/v1/xi/daily/T20I").json()
    assert d["seed"] == service.daily_seed("T20I", date.fromisoformat(d["date"]))
    r = client.post("/api/v1/xi/series", json={"format": "T20I", "seed": (d["seed"] + 1) % 2**32,
                                                "daily": True, "picks": auto_draft(d["spins"])})
    assert r.status_code == 422 and "daily" in r.json()["detail"]
    assert client.get("/api/v1/xi/challenge/nope").status_code == 404
    assert client.post("/api/v1/xi/spin", json={"format": "Hundred"}).status_code == 422
