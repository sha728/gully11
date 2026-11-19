"""Auction rooms over the API and WebSocket (need the loaded database)."""

import pytest
from fastapi.testclient import TestClient

from gully_api.main import app
from gully_api.auction.pool import TOP_PRICE
from test_players import _db_loaded

pytestmark = pytest.mark.skipif(not _db_loaded(), reason="Postgres not running or not loaded")
A = "/api/v1"


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def until(ws, pred, limit=400):
    """Read messages until one matches."""
    for _ in range(limit):
        m = ws.receive_json()
        if pred(m):
            return m
    raise AssertionError("never saw the expected message")


def test_pool_is_priced_and_sorted(client):
    from gully_api import db
    from gully_api.auction.pool import build_pool
    with db._pool.connection() as conn:
        pool = build_pool(conn, "mega", 10)
    assert len(pool) == 10 * 25 + 20
    assert pool[0]["fair"] == TOP_PRICE and all(p["base"] <= p["fair"] for p in pool)
    assert sum(p["overseas"] for p in pool) > 50
    rashid = next((p for p in pool if p["short_name"] == "Rashid Khan" and p["country"] == "Afghanistan"), None)
    assert rashid and rashid["overseas"] and rashid["capped"]          # filled in by hand


def test_room_flow(client):
    r = client.post(f"{A}/rooms", json={"nickname": "Host", "teams": 2, "humans": 2, "speed": "fast"})
    assert r.status_code == 200, r.text
    host = r.json()
    code = host["code"]
    guest = client.post(f"{A}/rooms/{code.lower()}/join", json={"nickname": "Guest"}).json()
    assert guest["franchise"] != host["franchise"]
    assert client.post(f"{A}/rooms/{code}/join", json={"nickname": "Late"}).status_code == 409
    assert client.post(f"{A}/rooms/NOPE00/join", json={"nickname": "x"}).status_code == 404

    with client.websocket_connect(f"{A}/ws/rooms/{code}?token={guest['token']}") as gws:
        first = gws.receive_json()
        assert first["phase"] == "lobby" and first["you"] == guest["franchise"] and not first["host"]
        gws.send_json({"type": "start"})
        assert "host" in until(gws, lambda m: m["type"] == "error")["message"]

        with client.websocket_connect(f"{A}/ws/rooms/{code}?token={host['token']}") as hws:
            assert hws.receive_json()["host"]
            hws.send_json({"type": "start"})
            live = until(hws, lambda m: m["type"] == "state" and m["phase"] == "live")
            lot = live["lot"]
            hws.send_json({"type": "bid", "amount": lot["next"]})
            led = until(hws, lambda m: m["type"] == "state" and m["lot"] and m["lot"]["leader"] == host["franchise"])
            assert led["lot"]["price"] == lot["next"]
            hws.send_json({"type": "bid", "amount": led["lot"]["next"]})
            assert "already" in until(hws, lambda m: m["type"] == "error")["message"]
            # Guest passes; the lot closes on the clock and the host owns the player.
            gws.send_json({"type": "pass"})
            sold = until(hws, lambda m: m["type"] == "state" and m["log"] and m["log"][-1]["player"] == lot["player"]["id"])
            mine = next(f for f in sold["franchises"] if f["id"] == host["franchise"])
            assert mine["squad"][0]["id"] == lot["player"]["id"]

    state = client.get(f"{A}/rooms/{code}").json()
    assert state["live"] and state["code"] == code and "token" not in str(state)


def test_watchers_cannot_bid(client):
    host = client.post(f"{A}/rooms", json={"nickname": "Solo", "teams": 2, "humans": 1}).json()
    with client.websocket_connect(f"{A}/ws/rooms/{host['code']}") as ws:
        assert ws.receive_json()["you"] is None
        ws.send_json({"type": "pass"})
        assert "watching" in until(ws, lambda m: m["type"] == "error")["message"]


def test_bot_auction_on_the_real_pool_looks_like_a_market(client):
    """Not every star at the same price, and nobody sits on half their purse."""
    import statistics
    from gully_api import db
    from gully_api.auction.pool import RULES, build_pool
    from gully_api.auction.room import Room
    with db._pool.connection() as conn:
        pool = build_pool(conn, "mega", 10)
    r = Room("TESTAA", "mega", RULES["mega"], pool, teams=10, humans=1, seed=11)
    r.start(0, r.host_token)
    me = r.by_token(r.host_token)
    t = 0.0
    while r.phase == "live":
        if r.lot and me.id not in r.lot.passed:
            r.pass_(me.id)
        t += 0.5
        r.tick(t)
    sold = {e["player"]: e["price"] for e in r.log if e["result"] == "sold"}
    marquee = [sold[p["id"]] for p in pool[:12] if p["id"] in sold]
    assert max(marquee) - min(marquee) >= 500                # a ₹5 cr+ spread, not one going rate
    assert statistics.median(marquee) <= 1.25 * TOP_PRICE
    spent = [RULES["mega"]["purse_lakh"] - f.purse for f in r.franchises.values() if f.bot]
    assert min(spent) >= 0.6 * RULES["mega"]["purse_lakh"]
