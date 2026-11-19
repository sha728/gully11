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
    for c in (c for x in s1 for c in x["candidates"]):
        assert c["slots"] == service.eligible_slots(c)
    picks, slots = auto_draft(s1, 4 if fmt == "IPL" else None)
    assert len(set(picks)) == 11 and sorted(slots) == list(range(1, 12))


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
    picks, slots = auto_draft(s, 4)
    body = {"format": "IPL", "seed": 99, "picks": picks, "slots": slots}
    a = client.post("/api/v1/xi/series", json=body).json()
    b = client.post("/api/v1/xi/series", json=body).json()
    assert a["slug"] == b["slug"] and a["result"] == b["result"] and a["matches"] == b["matches"]
    r = a["result"]
    assert r["won"] + r["lost"] + r["drawn"] + r["tied"] == 5
    saved = client.get(f"/api/v1/xi/challenge/{a['slug']}").json()
    assert saved["picks"] == picks and saved["slots"] == slots
    assert saved["spins"] == s and saved["result"] == r
    # The XI bats in the chosen order.
    assert [p["order"] for p in a["xi"]] == list(range(1, 12))
    assert [p["id"] for p in a["xi"]] == [picks[slots.index(n)] for n in range(1, 12)]
    m = client.get(f"/api/v1/xi/challenge/{a['slug']}/match/1").json()
    assert m["commentary"] and len(m["innings"]) == 2


def test_test_series_runs(client):
    s = spin(client, "Test", 5)
    picks, slots = auto_draft(s)
    out = client.post("/api/v1/xi/series", json={"format": "Test", "seed": 5, "picks": picks,
                                                  "slots": slots}).json()
    assert out["opponent"] == "All-time Test XI"
    assert all(2 <= len(m["scores"]) <= 4 for m in out["matches"])


def test_draft_rules_are_enforced(client):
    s = spin(client, "ODI", 11)
    picks, slots = auto_draft(s)

    def post(p, sl):
        return client.post("/api/v1/xi/series", json={"format": "ODI", "seed": 11, "picks": p, "slots": sl})

    bad = picks[:]
    bad[0] = "not-a-player"
    r = post(bad, slots)
    assert r.status_code == 422 and "isn't on the" in r.json()["detail"]
    assert post(picks[:10], slots[:10]).status_code == 422
    assert "position" in post(picks, [1] * 11).json()["detail"]
    # Swap the keeper's spot with the No. 11's: neither fits the other's position.
    keeper = slots.index(6)
    last = slots.index(11)
    swapped = slots[:]
    swapped[keeper], swapped[last] = 11, 6
    assert "can't bat at" in post(picks, swapped).json()["detail"]


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
                                                "daily": True, **dict(zip(("picks", "slots"),
                                                                          auto_draft(d["spins"])))})
    assert r.status_code == 422 and "daily" in r.json()["detail"]
    assert client.get("/api/v1/xi/challenge/nope").status_code == 404
    assert client.post("/api/v1/xi/spin", json={"format": "Hundred"}).status_code == 422


def test_eligible_slots_unit():
    slots = service.eligible_slots
    assert slots({"role": "BAT", "opener": True}) == [1, 2, 3, 4, 5, 6]
    assert slots({"role": "BAT", "opener": False}) == [3, 4, 5, 6]
    assert slots({"role": "WK", "opener": True}) == [1, 2, 3, 4, 5, 6]
    assert slots({"role": "AR"}) == [3, 4, 5, 6, 7, 8, 9, 10, 11]
    assert slots({"role": "BOWL", "spinner": True}) == [7, 8, 9, 10, 11]
    assert slots({"role": "BOWL", "spinner": False}) == [9, 10, 11]


def test_keeper_must_bat_in_top_six():
    xi = [{"person": str(i), "role": r, "country": "India", "slot": i + 1}
          for i, r in enumerate(["BAT"] * 5 + ["BAT", "AR", "AR"] + ["BOWL"] * 3)]
    with pytest.raises(service.DraftError, match="wicketkeeper"):
        service.check_rules("ODI", xi)
    opening_keeper = [dict(xi[0], role="WK")] + xi[1:]
    service.check_rules("ODI", opening_keeper)                     # keeper opens, 6 is a batter
    low_keeper = xi[:8] + [dict(xi[8], role="WK")] + xi[9:]
    with pytest.raises(service.DraftError, match="top six"):
        service.check_rules("ODI", low_keeper)


def test_feasibility_needs_every_slot():
    def c(role, **kw):
        d = {"role": role, **kw}
        return {**d, "slots": service.eligible_slots(d)}
    full = [[c("BAT", opener=True)]] * 2 + [[c("BAT")]] * 3 + [[c("WK")]] + [[c("AR")]] * 2 + [[c("BOWL")]] * 3
    assert service._feasible(full)
    assert not service._feasible([[c("BAT")]] + full[1:])          # only one opener
    assert not service._feasible(full[:5] + [[c("BAT")]] + full[6:])  # no keeper
    assert not service._feasible(full[:8] + [[c("BAT")]] + full[9:])  # a bowler short
