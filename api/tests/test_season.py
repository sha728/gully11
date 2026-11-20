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
        assert s["you"] == guest.id and not s["host"] and not s["played"] and len(s["teams"]) == 4
        mine = next(t for t in s["teams"] if t["id"] == guest.id)
        bad = client.put(f"{A}/lineup", json={"token": guest.token, "xi": mine["xi"][:10] + [mine["xi"][0]]})
        assert bad.status_code == 422
        new_xi = mine["xi"][1:] + mine["xi"][:1]                 # same players, different order
        assert client.put(f"{A}/lineup", json={"token": guest.token, "xi": new_xi, "impact": mine["impact"]}).status_code == 200
        assert client.put(f"{A}/lineup", json={"token": "nope", "xi": new_xi}).status_code == 403
        assert client.post(f"{A}/play", json={"token": guest.token}).status_code == 403   # host only
        played = client.post(f"{A}/play", json={"token": r.host_token}).json()["season"]
        assert len(played["matches"]) == 12 + 4 and played["lineups"][guest.id]["xi"] == new_xi
        assert played["lineups"][guest.id]["picked"] and played["champion"]["id"] in {t["id"] for t in s["teams"]}
        m = client.get(f"{A}/match/1").json()
        assert m["innings"] and m["commentary"]
        again = client.get(A).json()
        assert again["played"] and again["season"]["champion"] == played["champion"]
