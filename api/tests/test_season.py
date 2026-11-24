"""Season: lineups, fixtures, table, playoffs (no database), and the API end to end."""

from collections import Counter

import pytest

from gully_api.season import lineup
from gully_api.season.run import table
from gully_api.season.schedule import league, playoff_plan


def squad(n_os=6):
    roles = ["BAT"] * 7 + ["WK"] * 2 + ["AR"] * 4 + ["BOWL"] * 7
    out = {}
    for i, r in enumerate(roles):
        out[f"p{i}"] = {"id": f"p{i}", "name": f"P{i}", "role": r, "overseas": i % 3 == 0 and i < n_os * 3,
                        "fair": 100, "opener": i in (1, 2), "bat": 30 - i if r != "BOWL" else 5 - i / 10,
                        "bowl": (i if r in ("BOWL", "AR") else -10)}
    return out


def test_auto_xi_is_legal_and_ordered():
    players = squad()
    xi, impact = lineup.auto(players)
    lineup.check(players, xi, impact)                          # passes every rule
    assert xi[:2] == ["p1", "p2"]                              # tagged openers open
    assert players[xi[-1]]["role"] == "BOWL"                   # bowlers at the tail
    assert impact not in xi and players[impact]["role"] in ("BOWL", "AR")


@pytest.mark.parametrize("change,msg", [
    (lambda xi, P: (xi[:10] + [xi[0]], None), "eleven different"),
    (lambda xi, P: (([p for p in xi if P[p]["role"] != "WK"]
                     + [p for p in P if p not in xi and P[p]["role"] == "AR" and not P[p]["overseas"]])[:11], None),
     "wicketkeeper"),
    (lambda xi, P: ([p for p in P if P[p]["role"] in ("BAT", "WK")][:9] + [p for p in P if P[p]["role"] == "BOWL"][:2], None), "bowling options"),
    (lambda xi, P: (xi, xi[0]), "bench"),
])
def test_lineup_rules(change, msg):
    players = squad()
    xi, _ = lineup.auto(players)
    bad_xi, bad_impact = change(xi, players)
    with pytest.raises(lineup.LineupError, match=msg):
        lineup.check(players, bad_xi, bad_impact)


def test_thin_squads_are_not_held_to_impossible_rules():
    players = {k: v for k, v in squad().items() if v["role"] != "WK"}   # no keeper at all
    xi, impact = lineup.auto(players)
    lineup.check(players, xi, impact)                                  # legal without one


def test_an_opening_bowler_can_open():
    players = squad()
    players["p19"]["opener"] = True                                    # a Narine
    players["p19"]["bat"] = 40
    xi, _ = lineup.auto(players)
    if "p19" in xi:
        assert xi.index("p19") < 2


def test_overseas_limits():
    players = squad()
    os_ids = [p for p in players if players[p]["overseas"]]
    others = [p for p in players if not players[p]["overseas"]]
    xi = os_ids[:5] + others[:6]
    for p in xi:
        players[p]["role"] = "WK" if p == xi[0] else "AR"
    with pytest.raises(lineup.LineupError, match="overseas"):
        lineup.check(players, xi, None)
    xi = os_ids[:4] + others[:7]
    with pytest.raises(lineup.LineupError, match="Impact sub must be Indian"):
        lineup.check(players, xi, os_ids[4])


def test_ten_teams_play_the_ipl_format():
    teams = [f"T{i}" for i in range(10)]
    games = league(teams, 7)
    assert len(games) == 70 and set(Counter(t for g in games for t in g).values()) == {14}
    pairs = Counter(frozenset(g) for g in games)
    assert Counter(pairs.values()) == {2: 25, 1: 20}           # group + counterpart twice, the rest once
    assert not any(set(a) & set(b) for a, b in zip(games, games[1:]))
    assert len(league(teams[:4], 1)) == 12                     # smaller rooms: double round robin
    assert [s for s, *_ in playoff_plan(10)] == ["Qualifier 1", "Eliminator", "Qualifier 2", "Final"]
    assert [s for s, *_ in playoff_plan(3)] == ["Final"]


def test_table_points_and_net_run_rate():
    m = lambda a, b, w, sa, sb: {"stage": "League", "teams": [a, b], "winner": w,      # noqa: E731
                                 "scores": [{"team": a, **sa}, {"team": b, **sb}]}
    games = [
        m("A", "B", "A", {"runs": 200, "wickets": 5, "overs": "20"}, {"runs": 150, "wickets": 10, "overs": "17.2"}),
        m("B", "A", None, {"runs": 160, "wickets": 6, "overs": "20"}, {"runs": 160, "wickets": 8, "overs": "20"}),
    ]
    a, b = table(games, ["A", "B"])
    assert (a["team"], a["points"], a["won"], a["tied"]) == ("A", 3, 1, 1)
    # A: 360 runs off 40 overs; conceded 150 (all out: counted as 20 overs) + 160 off 20.
    assert a["nrr"] == round(360 / 40 - 310 / 40, 3) and b["points"] == 1


# ---------------------------------------------------------------- API

from test_players import _db_loaded  # noqa: E402


@pytest.mark.skipif(not _db_loaded(), reason="Postgres not running or not loaded")
def test_season_end_to_end():
    from fastapi.testclient import TestClient

    from gully_api import db
    from gully_api.auction.live import save_room
    from gully_api.auction.pool import RULES, build_pool
    from gully_api.auction.room import Room
    from gully_api.main import app

    with TestClient(app) as client:
        with db._pool.connection() as conn:
            pool = build_pool(conn, "mega", 4)
        r = Room("SEASNA", "mega", RULES["mega"], pool, teams=4, humans=2, seed=5)
        guest = r.claim("Guest")
        r.start(0, r.host_token)
        t = 0.0
        while r.phase == "live":
            for f in (r.by_token(r.host_token), guest):
                if r.lot and f.id not in r.lot.passed and r.lot.leader != f.id:
                    if r.lot.price is None and r.why_not(f) is None and len(f.squad) < 15:
                        r.bid(f.id, r.next_amount(), t)        # each human buys a squad at base price
                    else:
                        r.pass_(f.id)
            t += 0.5
            r.tick(t)
        with db._pool.connection() as conn:
            conn.execute("DELETE FROM sim_results WHERE context = 'season' AND ref = 'SEASNA'")
            conn.execute("DELETE FROM seasons WHERE code = 'SEASNA'")
            conn.commit()
        save_room(db._pool.connection)(r)

        A = "/api/v1/rooms/SEASNA/season"
        s = client.get(A, params={"token": guest.token}).json()
        assert s["you"] == guest.id and not s["host"] and not s["started"] and len(s["teams"]) == 4
        mine = next(t for t in s["teams"] if t["id"] == guest.id)
        bad = client.put(f"{A}/lineup", json={"token": guest.token, "xi": mine["xi"][:10] + [mine["xi"][0]]})
        assert bad.status_code == 422
        new_xi = mine["xi"][1:] + mine["xi"][:1]                 # same players, different order
        assert client.put(f"{A}/lineup", json={"token": guest.token, "xi": new_xi, "impact": mine["impact"]}).status_code == 200
        assert client.put(f"{A}/lineup", json={"token": "nope", "xi": new_xi}).status_code == 403
        assert client.post(f"{A}/start", json={"token": guest.token}).status_code == 403    # host only
        host = r.host_token
        s = client.post(f"{A}/start", json={"token": host}).json()
        assert s["started"] and s["season"]["matches"] == [] and s["total"] == 12 + 4
        assert client.post(f"{A}/advance", json={"token": guest.token}).status_code == 403
        s = client.post(f"{A}/advance", json={"token": host, "how": "next"}).json()
        assert len(s["season"]["matches"]) == 1
        # Change the guest's XI mid-season: their next match uses it.
        changed = new_xi[::-1]
        bench = next(p["id"] for p in mine["players"] if p["id"] not in changed)
        bad_cap = client.put(f"{A}/lineup", json={"token": guest.token, "xi": changed, "impact": mine["impact"],
                                                  "captain": bench})
        assert bad_cap.status_code == 422                   # a bench player can't captain
        assert client.put(f"{A}/lineup", json={"token": guest.token, "xi": changed, "impact": mine["impact"],
                                               "captain": changed[5]}).status_code == 200
        before = len(s["season"]["matches"])
        while True:
            s = client.post(f"{A}/advance", json={"token": host, "how": "next"}).json()
            last = s["season"]["matches"][-1]
            if guest.id in last["lineups"]:
                break
        assert last["match"] > before and last["lineups"][guest.id]["xi"] == changed
        assert last["lineups"][guest.id]["captain"] == changed[5]
        bot = next(f for f in last["lineups"] if f != guest.id)
        assert last["lineups"][bot]["captain"] in last["lineups"][bot]["xi"]
        s = client.post(f"{A}/advance", json={"token": host, "how": "end"}).json()
        assert s["finished"] and len(s["season"]["matches"]) == 16 and s["season"]["champion"]
        assert {m["stage"] for m in s["season"]["matches"][-4:]} == {"Qualifier 1", "Eliminator", "Qualifier 2", "Final"}
        orange, purple = s["season"]["caps"]["orange"], s["season"]["caps"]["purple"]
        assert orange and purple
        top = orange[0]
        assert top["sr"] == round(100 * top["runs"] / top["balls"], 1)
        assert all(w["econ"] and 2 < w["econ"] < 20 and w["balls"] > 0 for w in purple)
        assert client.put(f"{A}/lineup", json={"token": guest.token, "xi": changed}).status_code == 422   # over
        m = client.get(f"{A}/match/1").json()
        assert m["innings"] and m["commentary"]


@pytest.mark.skipif(not _db_loaded(), reason="Postgres not running or not loaded")
def test_season_waits_for_a_captains_bowling_change():
    from fastapi.testclient import TestClient

    from gully_api import db
    from gully_api.auction.live import save_room
    from gully_api.auction.pool import RULES, build_pool
    from gully_api.auction.room import Room
    from gully_api.main import app

    with TestClient(app) as client:
        with db._pool.connection() as conn:
            pool = build_pool(conn, "mega", 4)
        r = Room("SEASNB", "mega", RULES["mega"], pool, teams=4, humans=2, seed=6)
        guest = r.claim("Guest")
        r.start(0, r.host_token)
        t = 0.0
        while r.phase == "live":
            for f in (r.by_token(r.host_token), guest):
                if r.lot and f.id not in r.lot.passed and r.lot.leader != f.id:
                    if r.lot.price is None and r.why_not(f) is None and len(f.squad) < 15:
                        r.bid(f.id, r.next_amount(), t)
                    else:
                        r.pass_(f.id)
            t += 0.5
            r.tick(t)
        with db._pool.connection() as conn:
            conn.execute("DELETE FROM sim_results WHERE context = 'season' AND ref = 'SEASNB'")
            conn.execute("DELETE FROM seasons WHERE code = 'SEASNB'")
            conn.commit()
        save_room(db._pool.connection)(r)

        A = "/api/v1/rooms/SEASNB/season"
        host = r.host_token
        s = client.put(f"{A}/choose", json={"token": guest.token, "on": True}).json()
        assert next(t for t in s["teams"] if t["id"] == guest.id)["choose"]
        client.post(f"{A}/start", json={"token": host})
        # Play on until the guest's side has to bowl: the season stops there.
        for _ in range(20):
            s = client.post(f"{A}/advance", json={"token": host, "how": "next"}).json()
            if s["season"].get("live"):
                break
        wait = s["season"]["live"]
        assert wait["waiting"] == guest.id
        played = len(s["season"]["matches"])
        assert client.post(f"{A}/advance", json={"token": host, "how": "next"}).json()["season"]["live"] == wait
        # Only the guest sees who may bowl; the host can only sim it for them.
        mine = client.get(f"{A}/live", params={"token": guest.token}).json()
        theirs = client.get(f"{A}/live", params={"token": host}).json()
        assert mine["yours"] and mine["options"] and "options" not in theirs
        pick = mine["options"][0]["id"]
        assert client.post(f"{A}/live/bowl", json={"token": host, "key": wait["key"], "bowler": pick}).status_code == 422
        s = client.post(f"{A}/live/bowl", json={"token": guest.token, "key": wait["key"], "bowler": pick}).json()
        nxt = s["season"].get("live")
        assert nxt is None or nxt["key"] != wait["key"]
        # The host lets the engine finish the match for them.
        while s["season"].get("live") and len(s["season"]["matches"]) == played:
            w = s["season"]["live"]
            s = client.post(f"{A}/live/bowl", json={"token": host, "key": w["key"], "bowler": "rest"}).json()
        assert len(s["season"]["matches"]) == played + 1
        m = client.get(f"{A}/match/{played + 1}").json()
        inns = int(wait["key"].split(":")[0])
        over = int(wait["key"].split(":")[1])
        names = {o["id"]: o["name"] for o in mine["options"]}
        bowled = {e["bowler"] for e in m["commentary"] if e["inns"] == inns and e["ball"].startswith(f"{over}.")}
        assert bowled == {names[pick]}
