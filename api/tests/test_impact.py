"""IPL Impact Player: the sub replaces one of the XI at the start or the innings break."""

from gully_api.sim import Team, from_phase_rows, load_env, simulate_match
from gully_api.sim.engine import impact_plan

ROLES = ["BAT", "BAT", "WK", "BAT", "BAT", "AR", "AR", "BOWL", "BOWL", "BOWL", "BOWL"]
ENV = load_env("IPL_recent")


def side(name, sub_role=None, **kw):
    players = [from_phase_rows({"id": f"{name}{i}", "name": f"{name} {i}", "role": r}, [], ENV) for i, r in enumerate(ROLES)]
    impact = [from_phase_rows({"id": f"{name}S", "name": f"{name} Sub", "role": sub_role}, [], ENV)] if sub_role else []
    return Team(name, players, impact=impact, **kw)


def cards(d, team):
    """(ids who batted or could bat, ids who bowled) per innings for ``team``."""
    out = []
    for inn in d["innings"]:
        bat = {b["id"] for b in inn["batting_card"]} if inn["batting"] == team else set()
        bowl = {b["id"] for b in inn["bowling_card"]} if inn["bowling"] == team else set()
        out.append((bat, bowl))
    return out


def test_chosen_sub_replaces_the_chosen_player_at_the_break():
    a = side("A", "BAT", impact_out="A10", impact_when="break")
    b = side("B")
    for seed in range(4):
        d = simulate_match(a, b, ENV, seed, commentary=False).to_dict()
        rec = d["impact"][0]
        assert (rec["team"], rec["in"], rec["out"], rec["when"], rec["from_innings"]) == ("A", "AS", "A10", "break", 2)
        first, second = cards(d, "A")
        assert "AS" not in first[0] | first[1]                 # not on before the break
        assert "A10" not in second[0] | second[1]              # replaced: no further part
        if d["innings"][1]["batting"] == "A":                  # batting second: he bats
            assert "AS" in second[0]


def test_from_the_start_the_replaced_player_never_plays():
    a = side("A", "BOWL", impact_out="A0", impact_when="start")
    d = simulate_match(a, side("B"), ENV, 3, commentary=False).to_dict()
    for bat, bowl in cards(d, "A"):
        assert "A0" not in bat | bowl
    bat = next(inn for inn in d["innings"] if inn["batting"] == "A")["batting_card"]
    assert bat[-1]["id"] == "AS"                                # a bowling sub bats last


def test_auto_uses_the_sub_in_the_innings_that_needs_him():
    a = side("A", "BOWL")
    plan_first = impact_plan(a, bats_first=True)
    assert plan_first["record"]["in"] == "AS" and plan_first["record"]["when"] == "break"
    assert "AS" not in {p.id for p in plan_first["sides"][1].players}
    assert "AS" in {p.id for p in plan_first["sides"][2].players}
    # Bowling first: he's named in the XI and the batter he replaced comes on at the break.
    plan_second = impact_plan(a, bats_first=False)
    rec = plan_second["record"]
    assert rec["out"] == "AS" and rec["when"] == "break"
    assert "AS" in {p.id for p in plan_second["sides"][1].players}
    assert {p.id for p in plan_second["sides"][2].players} == {p.id for p in a.players}


def test_no_sub_no_change():
    d = simulate_match(side("A"), side("B"), ENV, 1, commentary=False).to_dict()
    assert d["impact"] == []


def test_engine_picks_from_five_named_subs_by_the_toss():
    subs = [from_phase_rows({"id": f"S{i}", "name": f"Sub {i}", "role": r}, [], ENV)
            for i, r in enumerate(["BAT", "BOWL", "WK", "BOWL", "BAT"])]
    a = Team("A", side("A").players, impact=subs)
    batting_first = impact_plan(a, bats_first=True)["record"]
    bowling_first = impact_plan(a, bats_first=False)["record"]
    # Batting first: a bowler comes on at the break for the second innings.
    assert batting_first["in"] in {"S1", "S3"} and batting_first["when"] == "break"
    # Bowling first: a batter comes on at the break for the chase.
    assert bowling_first["in"] in {"S0", "S2", "S4"} and bowling_first["when"] == "break"
    # A chosen sub is used whatever the toss: a batter on a side batting first bats
    # (named in the XI), and the bowler he kept out comes on at the break.
    chosen = impact_plan(Team("A", side("A").players, impact=subs, impact_pick="S4"), bats_first=True)
    assert "S4" in {p.id for p in chosen["sides"][1].players}
    assert chosen["record"]["out"] == "S4" and chosen["record"]["when"] == "break"


def test_lineup_names_up_to_five_subs_from_the_bench():
    import pytest

    from gully_api.season import lineup
    players = {f"P{i}": {"id": f"P{i}", "role": r, "overseas": False}
               for i, r in enumerate(ROLES + ["BAT", "BOWL", "AR", "BAT", "BOWL", "BOWL"])}
    xi = [f"P{i}" for i in range(11)]
    lineup.check(players, xi, None, subs=["P11", "P12", "P13", "P14", "P15"])
    lineup.check(players, xi, "P12", "P0", "break", subs=["P11", "P12"])
    with pytest.raises(lineup.LineupError):
        lineup.check(players, xi, None, subs=["P11", "P12", "P13", "P14", "P15", "P16"])
    with pytest.raises(lineup.LineupError):
        lineup.check(players, xi, "P16", subs=["P11"])            # the Impact Player must be a named sub
    with pytest.raises(lineup.LineupError):
        lineup.check(players, xi, None, subs=["P3"])              # subs come from the bench
