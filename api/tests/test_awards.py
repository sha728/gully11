"""Player of the match and of the series (sim/awards.py)."""

from gully_api.sim import Team, from_phase_rows, load_env, simulate_match
from gully_api.sim.awards import impact, player_of_match, player_of_series

ROLES = ["BAT", "BAT", "WK", "BAT", "BAT", "AR", "AR", "BOWL", "BOWL", "BOWL", "BOWL"]


def bat(pid, name, runs, balls, how="caught"):
    return {"id": pid, "name": name, "runs": runs, "balls": balls, "fours": 0, "sixes": 0, "how_out": how}


def bowl(pid, name, overs, runs, wickets):
    return {"id": pid, "name": name, "overs": overs, "runs": runs, "wickets": wickets}


def match(winner, a_bat, a_bowl, b_bat, b_bowl, a_total=(160, "20", 6), b_total=(150, "20", 8)):
    return {
        "winner": winner,
        "innings": [
            {"batting": "A", "bowling": "B", "runs": a_total[0], "overs": a_total[1], "wickets": a_total[2],
             "batting_card": a_bat, "bowling_card": b_bowl},
            {"batting": "B", "bowling": "A", "runs": b_total[0], "overs": b_total[1], "wickets": b_total[2],
             "batting_card": b_bat, "bowling_card": a_bowl},
        ],
    }


def test_big_innings_on_the_winning_side_takes_the_award():
    m = match("A", [bat("a1", "Opener", 90, 50), bat("a2", "Two", 20, 25)], [bowl("a9", "Bowler", "4", 30, 2)],
              [bat("b1", "Rival", 60, 45)], [bowl("b9", "Quick", "4", 25, 2)])
    pom = player_of_match(m, is_test=False)
    assert pom["id"] == "a1" and pom["team"] == "A" and pom["figures"] == "90 (50)"


def test_outstanding_effort_in_defeat_can_still_win_it():
    m = match("A", [bat("a1", "Steady", 35, 30)], [bowl("a9", "Bowler", "4", 35, 1)],
              [bat("b1", "Lone hand", 110, 55, "not out")], [bowl("b9", "Quick", "4", 30, 1)])
    pom = player_of_match(m, is_test=False)
    assert pom["id"] == "b1" and pom["figures"] == "110* (55)"


def test_losing_side_is_discounted():
    m = match("A", [bat("a1", "X", 50, 40)], [], [bat("b1", "Y", 50, 40)], [])
    s = impact(m, is_test=False)
    assert s["b1"]["score"] < s["a1"]["score"]


def test_all_round_figures_and_wickets_count():
    m = match("A", [bat("a1", "All-rounder", 40, 30)], [bowl("a1", "All-rounder", "4", 20, 3)],
              [bat("b1", "Bat", 45, 40)], [bowl("b9", "Quick", "4", 30, 1)])
    pom = player_of_match(m, is_test=False)
    assert pom["id"] == "a1" and pom["figures"] == "40 (30) and 3/20"


def test_every_simulated_match_names_one_from_either_side():
    env = load_env("IPL_recent")
    a = Team("A", [from_phase_rows({"id": f"A{i}", "name": f"A {i}", "role": r}, [], env) for i, r in enumerate(ROLES)])
    b = Team("B", [from_phase_rows({"id": f"B{i}", "name": f"B {i}", "role": r}, [], env) for i, r in enumerate(ROLES)])
    results = [simulate_match(a, b, env, seed, commentary=False).to_dict() for seed in range(5)]
    ids = {p.id for p in a.players + b.players}
    for d in results:
        assert d["player_of_match"]["id"] in ids
    series = player_of_series(results, is_test=False)
    assert series["id"] in ids and series["matches"] == 5


def test_test_match_award():
    from gully_api.sim import simulate_test
    env = load_env("Test")
    a = Team("A", [from_phase_rows({"id": f"A{i}", "name": f"A {i}", "role": r}, [], env) for i, r in enumerate(ROLES)])
    b = Team("B", [from_phase_rows({"id": f"B{i}", "name": f"B {i}", "role": r}, [], env) for i, r in enumerate(ROLES)])
    d = simulate_test(a, b, env, 3, commentary=False).to_dict()
    assert d["player_of_match"]["id"].startswith(("A", "B"))
