"""XI Builder integration tests (need the loaded database, like test_players)."""

import json
from datetime import date

import pytest
from fastapi.testclient import TestClient

from gully_api.main import app
from gully_api.xi import service
from test_players import _db_loaded
from xi_helpers import auto_draft

pytestmark = pytest.mark.skipif(not _db_loaded(), reason="Postgres not running or not loaded")
FORMATS = ["Test", "ODI", "T20I", "IPL"]
X = "/api/v1/xi"


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def server_spins(fmt, seed):
    from gully_api import db
    with db._pool.connection() as conn:
        return service.spins(conn, fmt, seed)


def draft(client, **body):
    r = client.post(f"{X}/drafts", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def fill(client, d):
    """Spin and pick through a whole draft, taking the first pickable player each time."""
    for _ in range(d["total"] - d["revealed"]):
        d = client.post(f"{X}/drafts/{d['id']}/spin").json()
        spin = d["spins"][-1]
        c = next(c for c in spin["candidates"] if c["options"])
        r = client.post(f"{X}/drafts/{d['id']}/pick", json={"spin": spin["spin"], "player": c["id"]})
        assert r.status_code == 200, r.text
        d = r.json()
    return d


@pytest.mark.parametrize("fmt", FORMATS)
def test_spins_are_seeded_and_fillable(client, fmt):
    s1 = server_spins(fmt, 123)
    assert s1 == server_spins(fmt, 123) and len(s1) == 11
    assert server_spins(fmt, 124) != s1
    for s in s1:
        assert s["era"] in service.FORMATS[fmt].eras
        assert len(s["candidates"]) >= service.MIN_CANDIDATES
        for c in s["candidates"]:
            assert c["slots"] == service.eligible_slots(c)
    picks, slots = auto_draft(s1, 4 if fmt == "IPL" else None)
    assert len(set(picks)) == 11 and sorted(slots) == list(range(1, 12))


def test_spins_depend_on_the_server_secret(monkeypatch):
    from gully_api.settings import settings
    a = service._rng("ODI", 5, 0).random()
    monkeypatch.setattr(settings, "xi_secret", "something-else")
    assert service._rng("ODI", 5, 0).random() != a


def test_unrevealed_spins_never_reach_the_browser(client):
    d = draft(client, format="ODI", seed=77)
    assert d["revealed"] == 0 and d["spins"] == []
    hidden = server_spins("ODI", 77)
    d = client.post(f"{X}/drafts/{d['id']}/spin").json()
    assert d["revealed"] == 1 and len(d["spins"]) == 1
    shown = {c["id"] for c in d["spins"][0]["candidates"]}
    secret = {c["id"] for s in hidden[1:] for c in s["candidates"]} - shown
    body = json.dumps(d)
    assert not any(pid in body for pid in secret)
    # No second spin until the first has a pick; no picks from spins not yet out.
    assert client.post(f"{X}/drafts/{d['id']}/spin").status_code == 409
    other = hidden[1]["candidates"][0]["id"]
    r = client.post(f"{X}/drafts/{d['id']}/pick", json={"spin": 2, "player": other})
    assert r.status_code == 422 and "revealed" in r.json()["detail"]
    # The endpoints that handed out whole draws are gone.
    assert client.post(f"{X}/spin", json={"format": "ODI", "seed": 77}).status_code in (404, 405)
    assert client.get(f"{X}/daily/ODI").status_code in (404, 405)
    assert client.post(f"{X}/series", json={}).status_code in (404, 405)


def test_draft_to_series(client):
    d = fill(client, draft(client, format="IPL", seed=99))
    assert d["status"]["ready"] and not d["can_spin"]
    assert [p["slot"] for p in d["lineup"]] == list(range(1, 12))
    assert all(p["player"] for p in d["lineup"])
    # Same draft id, same lineup, same slug; the draft is then closed.
    a = client.post(f"{X}/drafts/{d['id']}/play").json()
    assert client.post(f"{X}/drafts/{d['id']}/play").json()["slug"] == a["slug"]
    assert client.post(f"{X}/drafts/{d['id']}/spin").status_code == 409
    c = client.get(f"{X}/challenge/{a['slug']}").json()
    assert "spins" not in c and len(c["picks"]) == 11 and sorted(c["slots"]) == list(range(1, 12))
    assert [p["name"] for p in c["xi"]] == [p["player"]["name"] for p in d["lineup"]]
    r = c["result"]
    assert r["won"] + r["lost"] + r["drawn"] + r["tied"] == 5
    m = client.get(f"{X}/challenge/{a['slug']}/match/1").json()
    assert m["commentary"] and len(m["innings"]) == 2
    # A friend chasing it gets the same draw and the rival recorded.
    f = draft(client, format="IPL", seed=99, vs=a["slug"])
    assert f["rival"] == a["slug"] and f["id"] != d["id"]


def test_moves_follow_the_rules(client):
    d = fill(client, draft(client, format="Test", seed=5))
    by = {p["slot"]: p for p in d["lineup"]}
    src = next(p for p in d["lineup"] if p["targets"])
    dst = src["targets"][0]
    moved = client.post(f"{X}/drafts/{d['id']}/move", json={"from": src["slot"], "to": dst}).json()
    after = {p["slot"]: p for p in moved["lineup"]}
    assert after[dst]["player"]["id"] == src["player"]["id"]
    assert after[src["slot"]]["player"]["id"] == by[dst]["player"]["id"]
    # A bowler can't open.
    bowler = next(p for p in moved["lineup"] if p["slot"] == 11)
    r = client.post(f"{X}/drafts/{d['id']}/move", json={"from": bowler["slot"], "to": 1})
    assert r.status_code == 422
    # Removing a pick reopens its spin.
    gone = client.delete(f"{X}/drafts/{d['id']}/pick/{bowler['spin']}").json()
    assert gone["status"]["picked"] == 10 and not gone["status"]["ready"]


def test_daily_and_errors(client):
    d = draft(client, format="T20I", daily=True)
    assert d["seed"] == service.daily_seed("T20I", date.fromisoformat(d["daily"]))
    assert client.get(f"{X}/drafts/nope").status_code == 404
    assert client.get(f"{X}/challenge/nope").status_code == 404
    assert client.post(f"{X}/drafts", json={"format": "Hundred"}).status_code == 422
    r = client.post(f"{X}/drafts/{d['id']}/play")
    assert r.status_code == 422


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


def test_captain_choice_leads_the_series(client):
    d = fill(client, draft(client, format="IPL", seed=4242))
    ids = [slot["player"]["id"] for slot in d["lineup"] if slot["player"]]
    assert len(ids) == 11 and d["captain"] is None and d["captain_auto"] in ids
    bad = client.post(f"{X}/drafts/{d['id']}/captain", json={"player": "not-in-the-xi"})
    assert bad.status_code == 422
    chosen = ids[-1]                                       # the No. 11 as captain
    v = client.post(f"{X}/drafts/{d['id']}/captain", json={"player": chosen}).json()
    assert v["captain"] == chosen
    slug = client.post(f"{X}/drafts/{d['id']}/play").json()["slug"]
    c = client.get(f"{X}/challenge/{slug}").json()
    assert c["captain"] == chosen and c["captains"]["mine"]["id"] == chosen
    them = c["captains"]["them"]
    assert them["id"] and them["rating"] > 0                 # the Greats are led by a real captain
    m = client.get(f"{X}/challenge/{slug}/match/1").json()
    assert m["toss"]["winner"] in m["teams"] and m["toss"]["decision"] in ("bat", "bowl")


def test_daily_leaderboard(client):
    d = fill(client, draft(client, format="ODI", daily=True))
    r = client.post(f"{X}/drafts/{d['id']}/play")
    assert r.status_code == 200, r.text
    slug = r.json()["slug"]
    board = client.get(f"{X}/leaderboard/ODI", params={"draft": d["id"]}).json()
    assert board["day"] == d["daily"] == board["today"] and board["total"] >= 1
    you = board["you"]
    assert you and you["slug"] == slug and you["you"] and you["name"] is None
    assert you["points"] == 2 * you["won"] + you["tied"] + you["drawn"]
    ranks = [row["rank"] for row in board["rows"]]
    assert ranks == sorted(ranks) and ranks[0] == 1
    assert all("draft_id" not in row for row in board["rows"])   # the draft id is a secret
    # Playing again doesn't add a second entry.
    client.post(f"{X}/drafts/{d['id']}/play")
    assert client.get(f"{X}/leaderboard/ODI").json()["total"] == board["total"]
    # Naming: allowed characters only; only for real entries.
    put = lambda name, did=d["id"]: client.put(f"{X}/leaderboard/entries/{did}/name", json={"name": name})
    assert put("x").status_code == 422 and put("<script>").status_code == 422
    assert put("Gully Boy", "nope").status_code == 404
    assert put("  Gully   Boy ").json()["name"] == "Gully Boy"
    assert client.get(f"{X}/leaderboard/ODI", params={"draft": d["id"]}).json()["you"]["name"] == "Gully Boy"
    # Another day, or a non-daily series: not on today's board.
    assert client.get(f"{X}/leaderboard/ODI", params={"day": "2001-01-01"}).json()["rows"] == []
    plain = fill(client, draft(client, format="ODI", seed=777))
    client.post(f"{X}/drafts/{plain['id']}/play")
    assert client.get(f"{X}/leaderboard/ODI", params={"draft": plain["id"]}).json()["you"] is None


def test_captain_the_series_over_by_over(client):
    d = fill(client, draft(client, format="IPL", seed=4242))
    base = f"{X}/drafts/{d['id']}/live"
    assert client.get(f"{base}/2").status_code == 422          # match 1 first
    s = client.get(f"{base}/1").json()
    assert s["status"] == "bowl" and s["suggested"] in {o["id"] for o in s["options"]}
    first_key = s["key"]
    inns, over = (int(x) for x in first_key.split(":"))
    # Bowl that over yourself with someone the engine wouldn't have picked.
    pick = next(o for o in s["options"] if o["id"] != s["suggested"])
    s = client.post(f"{base}/1/bowl", json={"key": first_key, "bowler": pick["id"]}).json()
    assert client.post(f"{base}/1/bowl", json={"key": first_key, "bowler": pick["id"]}).status_code == 409
    assert s["status"] == "bowl" and s["key"] != first_key
    bowled = {e["bowler"] for e in s["match"]["commentary"] if e["inns"] == inns and e["ball"].startswith(f"{over}.")}
    assert bowled == {pick["name"]}
    # Sim the rest of match 1: it's finished and match 2 opens.
    s = client.post(f"{base}/1/bowl", json={"key": s["key"], "bowler": "rest"}).json()
    assert s["status"] == "done"
    live_one = s["match"]["commentary"]
    assert client.get(f"{base}/2").json()["status"] == "bowl"
    # Playing the series keeps your choices; after that the draft is closed.
    a = client.post(f"{X}/drafts/{d['id']}/play").json()
    assert client.get(f"{X}/challenge/{a['slug']}/match/1").json()["commentary"] == live_one
    assert client.get(f"{base}/1").status_code == 409


def test_only_t20_series_can_be_captained(client):
    d = fill(client, draft(client, format="ODI", seed=7))
    assert client.get(f"{X}/drafts/{d['id']}/live/1").status_code == 422
