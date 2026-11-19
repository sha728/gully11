"""Simulator unit tests: no database needed (synthetic player profiles)."""

import statistics
from collections import Counter

import pytest

from gully_api.sim import Team, from_career, from_phase_rows, load_env, simulate_match
from gully_api.sim.profiles import Profile, expected
from gully_api.sim.rates import PHASES, RUNS

ROLES = ["BAT", "BAT", "WK", "BAT", "BAT", "AR", "AR", "BOWL", "BOWL", "BOWL", "BOWL"]


@pytest.fixture(scope="module")
def env():
    return load_env("IPL_recent")


@pytest.fixture(scope="module")
def raw_env():
    """No calibration, no conditions spread: the bare log5 model."""
    return load_env("IPL_recent").with_calibration(None, 0.0)


def avg_team(name, env, roles=ROLES):
    return Team(name, [from_phase_rows({"id": f"{name}{i}", "name": f"{name} {i}", "role": r}, [], env)
                       for i, r in enumerate(roles)])


def league_player(pid, env, role="BAT"):
    """Exactly league-average with the bat and ball (ratio 1 everywhere)."""
    return Profile(id=pid, name=pid, role=role,
                   bat={p: list(env.bat_base[p]) for p in PHASES},
                   bowl={p: list(env.bowl_base[p]) for p in PHASES},
                   wide=dict(env.wide_rate), noball=dict(env.noball_rate), balls_bowled=1000)


def career_team(name, env, bat_avg, bat_sr, bowl_avg, bowl_econ):
    players = [from_career(f"{name}{i}", f"{name} {i}", r, env,
                           bat_avg=bat_avg if r != "BOWL" else bat_avg / 3, bat_sr=bat_sr,
                           bowl_avg=bowl_avg if r in ("BOWL", "AR") else None,
                           bowl_econ=bowl_econ if r in ("BOWL", "AR") else None)
               for i, r in enumerate(ROLES)]
    return Team(name, players)


# ------------------------------------------------------------- determinism

def test_same_seed_same_match(env):
    a, b = avg_team("A", env), avg_team("B", env)
    r1 = simulate_match(a, b, env, seed=42).to_dict()
    r2 = simulate_match(a, b, env, seed=42).to_dict()
    r3 = simulate_match(a, b, env, seed=43).to_dict()
    assert r1 == r2
    assert r1 != r3


def test_commentary_does_not_change_result(env):
    a, b = avg_team("A", env), avg_team("B", env)
    for seed in range(20):
        on = simulate_match(a, b, env, seed, commentary=True)
        off = simulate_match(a, b, env, seed, commentary=False)
        assert [(i.runs, i.wickets, i.legal_balls) for i in on.innings] == \
               [(i.runs, i.wickets, i.legal_balls) for i in off.innings]
        assert off.commentary == [] and on.commentary


# ------------------------------------------------------------- cricket rules

@pytest.mark.parametrize("env_name,overs", [("IPL_recent", 20), ("ODI_recent", 50)])
def test_innings_and_scorecard_rules(env_name, overs):
    env = load_env(env_name)
    a, b = avg_team("A", env), avg_team("B", env)
    quota_balls = env.max_overs_per_bowler * 6
    for seed in range(40):
        r = simulate_match(a, b, env, seed)
        i1, i2 = r.innings
        assert i2.target == i1.runs + 1
        for inn in r.innings:
            assert inn.wickets <= 10 and inn.legal_balls <= overs * 6
            assert inn.wickets == 10 or inn.legal_balls == overs * 6 or inn is i2
            # every run is accounted for, from the batting side and the bowling side
            bat_runs = sum(x.runs for x in inn.bat.values())
            assert bat_runs + sum(inn.extras.values()) == inn.runs
            assert sum(x.runs for x in inn.bowl.values()) + inn.extras["byes"] == inn.runs
            assert sum(x.balls for x in inn.bowl.values()) == inn.legal_balls
            assert all(x.balls <= quota_balls for x in inn.bowl.values())
            outs = [x for x in inn.bat.values() if x.how_out not in (None, "not out")]
            assert len(outs) == inn.wickets == len(inn.fall_of_wickets)
        # the chase stops as soon as the target is reached
        if r.winner == r.teams[1]:
            assert 0 <= i2.runs - i2.target <= 6
            assert "wicket" in r.margin
        # no bowler bowls two overs in a row
        for n in (1, 2):
            overs_by = {}
            for e in r.commentary:
                if e["inns"] == n:
                    overs_by[int(e["ball"].split(".")[0])] = e["bowler"]
            seq = [overs_by[k] for k in sorted(overs_by)]
            assert all(x != y for x, y in zip(seq, seq[1:]))


def test_team_validation(env):
    players = avg_team("A", env).players
    with pytest.raises(ValueError, match="11 players"):
        Team("X", players[:10])
    with pytest.raises(ValueError, match="5 bowling"):
        Team("X", players, bowlers=[p.id for p in players[:4]])
    with pytest.raises(ValueError, match="duplicate"):
        Team("X", players[:10] + players[:1])


# ------------------------------------------------------------- the model

def test_league_average_players_reproduce_environment(raw_env):
    """log5 identity: average batters vs average bowlers produce the environment's
    own outcome rates (first innings only, so no chase adjustment)."""
    env = raw_env
    a = Team("A", [league_player(f"a{i}", env, "BOWL" if i > 6 else "BAT") for i in range(11)])
    b = Team("B", [league_player(f"b{i}", env, "BOWL" if i > 6 else "BAT") for i in range(11)])
    counts = {p: [0] * 7 for p in PHASES}
    for seed in range(600):
        inn = simulate_match(a, b, env, seed, bat_first=0, commentary=False).innings[0]
        for p in PHASES:
            counts[p] = [x + y for x, y in zip(counts[p], inn.outcomes[p])]
    for p in PHASES:
        n = sum(counts[p])
        for i in (0, 1, 2, 5, 6):  # W, dot, single, four, six
            assert counts[p][i] / n == pytest.approx(env.bat_env[p][i], rel=0.08), (p, i)


def test_stronger_team_wins_more(env):
    strong = career_team("S", env, bat_avg=40, bat_sr=165, bowl_avg=20, bowl_econ=7.0)
    weak = career_team("W", env, bat_avg=20, bat_sr=120, bowl_avg=38, bowl_econ=10.0)
    wins = Counter(simulate_match(strong, weak, env, s, commentary=False).winner for s in range(300))
    assert wins["S"] / 300 > 0.8


def test_equal_teams_are_balanced(env):
    a, b = avg_team("A", env), avg_team("B", env)
    res = [simulate_match(a, b, env, s, commentary=False) for s in range(1500)]
    chase = sum(r.winner == r.teams[1] for r in res) / len(res)
    assert 0.45 < chase < 0.60  # chasing helps a little (target known), never decisive
    firsts = [r.innings[0].runs for r in res]
    assert 140 < statistics.mean(firsts) < 230 and statistics.stdev(firsts) > 20


def test_shrinkage_pulls_small_samples_to_prior(raw_env):
    env = raw_env
    hero = {"balls": 0, "wickets": 0, "dots": 0, "ones": 0, "twos": 0, "threes": 0,
            "fours": 0, "sixes": 0}

    def rows(per_phase):  # a batter who hits a six every 3 balls and never gets out
        return [{**hero, "role": "bat", "phase": p, "balls": per_phase, "dots": per_phase // 3,
                 "ones": per_phase // 3, "sixes": per_phase - 2 * (per_phase // 3)}
                for p in PHASES]

    tiny = from_phase_rows({"id": "t", "name": "t", "role": "BAT"}, rows(10), env)
    big = from_phase_rows({"id": "b", "name": "b", "role": "BAT"}, rows(3000), env)
    base = env.bat_base["middle"]
    # 30 balls of fireworks: a decent hitter, not a superstar (plan requirement)
    assert tiny.bat["middle"][6] < 2 * base[6]
    assert tiny.bat["middle"][0] > 0.5 * base[0]
    # 9,000 balls: the data wins
    assert big.bat["middle"][6] > 0.25 and big.bat["middle"][0] < 0.2 * base[0]


def test_from_career_matches_average_and_strike_rate(env):
    p = from_career("x", "Legend", "BAT", env, bat_avg=50, bat_sr=140)
    vec = [sum(p.bat[ph][i] for ph in PHASES) / 3 for i in range(7)]
    rpb, w = expected(vec)
    assert rpb == pytest.approx(1.40, rel=0.08)
    assert rpb / w == pytest.approx(50, rel=0.12)  # runs per dismissal = average
    assert p.estimated


def test_win_probability_series(env):
    a, b = avg_team("A", env), avg_team("B", env)
    for seed in range(10):
        r = simulate_match(a, b, env, seed)
        probs = [p for _, p in r.win_prob]
        assert len(probs) == len(r.commentary)
        assert all(0.0 <= p <= 1.0 for p in probs)
        assert 0.2 < probs[0] < 0.8
        final = probs[-1]
        if r.winner == r.teams[0]:
            assert final > 0.9
        elif r.winner == r.teams[1]:
            assert final < 0.1


def test_runs_lookup_matches_outcomes():
    assert RUNS == (0, 0, 1, 2, 3, 4, 6)


# ------------------------------------------------------------- Tests (beta)

def xi_side(name, env):
    return avg_team(name, env, ["BAT", "BAT", "BAT", "BAT", "WK", "AR", "AR", "BOWL", "BOWL", "BOWL", "BOWL"])


def test_test_matches_follow_the_laws():
    from gully_api.sim import simulate_test
    from gully_api.sim.engine import TEST_MATCH_OVERS
    env = load_env("Test")
    a, b = xi_side("A", env), xi_side("B", env)
    results = Counter()
    for seed in range(60):
        r = simulate_test(a, b, env, seed)
        results[r.result] += 1
        assert 2 <= len(r.innings) <= 4
        assert sum(i.legal_balls for i in r.innings) <= TEST_MATCH_OVERS * 6
        assert r.win_prob == []                                  # no win-probability model for Tests
        for inn in r.innings:
            assert inn.wickets <= 10
            assert sum(x.runs for x in inn.bat.values()) + sum(inn.extras.values()) == inn.runs
        if r.result == "win":
            assert r.winner in r.teams and r.margin.startswith("won by")
        elif r.result == "draw":
            assert r.winner is None and r.margin == "match drawn"
        if len(r.innings) == 4 and r.winner == r.innings[3].batting:
            assert r.innings[3].runs >= r.innings[3].target
        if "innings" in r.margin:                                # beaten by an innings: 3 innings only
            assert len(r.innings) == 3
    assert results["win"] > 30                                   # most Tests have a winner


def test_test_match_is_deterministic_and_separate_from_limited_overs():
    from gully_api.sim import simulate_test
    env = load_env("Test")
    a, b = xi_side("A", env), xi_side("B", env)
    assert simulate_test(a, b, env, 5).to_dict() == simulate_test(a, b, env, 5).to_dict()
    with pytest.raises(ValueError, match="simulate_test"):
        simulate_match(a, b, env, 1)
    with pytest.raises(ValueError, match="simulate_match"):
        simulate_test(a, b, load_env("ODI"), 1)


def test_follow_on_and_declarations_happen():
    """A far stronger side should sometimes enforce the follow-on, and declare."""
    from gully_api.sim import simulate_test
    env = load_env("Test")
    strong = career_team("S", env, bat_avg=60, bat_sr=60, bowl_avg=20, bowl_econ=2.6)
    weak = career_team("W", env, bat_avg=18, bat_sr=45, bowl_avg=45, bowl_econ=3.8)
    follow_ons = declarations = 0
    for seed in range(40):
        r = simulate_test(strong, weak, env, seed, bat_first=0)
        declarations += any(i.declared for i in r.innings)
        if len(r.innings) >= 3 and r.innings[2].batting == r.innings[1].batting:
            follow_ons += 1
    assert follow_ons > 0 and declarations > 0


def test_legend_profile_reproduces_career():
    from gully_api.sim import from_legend
    env = load_env("Test")
    p = from_legend({"id": "L-x", "name": "X", "role": "BOWL", "bat_avg": 7.4, "bat_sr": None,
                     "wickets": 563, "bowl_avg": 21.6, "bowl_econ": 2.49}, env)
    vec = [sum(p.bowl[ph][i] for ph in PHASES) / 3 for i in range(7)]
    rpb, w = expected(vec)
    assert rpb / w == pytest.approx(21.6, rel=0.05) and 6 * rpb == pytest.approx(2.49, rel=0.05)
    assert p.estimated and p.meta["sr_estimated"]
