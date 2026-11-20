"""A season played one match at a time.

The state is plain JSON (kept in ``seasons.result``): the league fixtures, the
results so far, playoff outcomes and running cap tallies. ``play_next`` simulates
the next fixture with whatever XIs the teams field *at that moment*, so a team
can change its XI between matches. Results don't exist until they're played.

Points: 2 for a win, 1 each for a tie (the engine has no super over). The table
is sorted by points, then net run rate, IPL style: runs per over scored minus
conceded, a side bowled out counted as having faced its full 20 overs. A tied
playoff goes to the team higher in the table. Playoff fixtures are drawn once the
league stage is over.
"""

from __future__ import annotations

from ..sim.engine import Team, simulate_match
from ..sim.rates import Env
from .schedule import league, playoff_plan


def _balls(overs: str) -> int:
    o, _, b = str(overs).partition(".")
    return int(o) * 6 + int(b or 0)


def _summary(n: int, stage: str, m, lineups: dict) -> dict:
    d = m.to_dict()
    bats = [b for inn in d["innings"] for b in inn["batting_card"]]
    bowls = [b for inn in d["innings"] for b in inn["bowling_card"]]
    top = max(bats, key=lambda b: (b["runs"], -b["balls"]))
    best = max(bowls, key=lambda b: (b["wickets"], -b["runs"]))
    return {
        "match": n, "stage": stage, "teams": list(m.teams), "winner": m.winner, "margin": m.margin,
        "result": "tie" if m.winner is None else "win",
        "scores": [{"team": i["batting"], "runs": i["runs"], "wickets": i["wickets"], "overs": i["overs"]}
                   for i in d["innings"]],
        "top_scorer": {"name": top["name"], "runs": top["runs"], "balls": top["balls"]},
        "best_bowler": {"name": best["name"], "wickets": best["wickets"], "runs": best["runs"]},
        "lineups": lineups,                     # the XIs used: {franchise: {"xi", "impact"}}
    }


def table(summaries: list[dict], teams: list[str], overs: int = 20) -> list[dict]:
    rows = {t: {"team": t, "played": 0, "won": 0, "lost": 0, "tied": 0, "points": 0,
                "for_runs": 0, "for_balls": 0, "against_runs": 0, "against_balls": 0} for t in teams}
    for s in summaries:
        if s["stage"] != "League":
            continue
        for i, sc in enumerate(s["scores"]):
            bat, bowl = rows[sc["team"]], rows[s["scores"][1 - i]["team"]]
            balls = overs * 6 if sc["wickets"] >= 10 else _balls(sc["overs"])
            bat["for_runs"] += sc["runs"]
            bat["for_balls"] += balls
            bowl["against_runs"] += sc["runs"]
            bowl["against_balls"] += balls
        for t in s["teams"]:
            r = rows[t]
            r["played"] += 1
            if s["winner"] is None:
                r["tied"] += 1
                r["points"] += 1
            elif s["winner"] == t:
                r["won"] += 1
                r["points"] += 2
            else:
                r["lost"] += 1
    for r in rows.values():
        f = 6 * r["for_runs"] / r["for_balls"] if r["for_balls"] else 0
        a = 6 * r["against_runs"] / r["against_balls"] if r["against_balls"] else 0
        r["nrr"] = round(f - a, 3)
    return sorted(rows.values(), key=lambda r: (-r["points"], -r["nrr"], r["team"]))


def start(teams: dict[str, str], seed: int) -> dict:
    """A new season for ``teams`` (franchise id -> name): fixtures drawn, nothing played."""
    ids = list(teams)
    return {
        "teams": [{"id": f, "name": n} for f, n in teams.items()],
        "seed": seed,
        "fixtures": [{"stage": "League", "home": a, "away": b} for a, b in league(ids, seed)],
        "matches": [],
        "playoffs": {},                          # stage -> {"winner", "loser"} (franchise ids)
        "tally": {"runs": {}, "wickets": {}},    # player id -> running totals
        "table": table([], list(teams.values())),
        "champion": None,
        "runner_up": None,
        "caps": {"orange": [], "purple": []},
        "format": "IPL (two groups, 14 matches each)" if len(ids) == 10 else "Double round robin",
    }


def _ids(state: dict) -> dict[str, str]:
    return {t["name"]: t["id"] for t in state["teams"]}


def next_fixture(state: dict) -> dict | None:
    """The next match to play (drawing playoff fixtures once the league is done)."""
    n = len(state["matches"])
    league_left = [f for f in state["fixtures"] if f["stage"] == "League"]
    if n < len(league_left):
        return state["fixtures"][n]
    if state["champion"]:
        return None
    seeds = {i + 1: _ids(state)[r["team"]] for i, r in enumerate(state["table"])}
    for stage, x, y in playoff_plan(len(state["teams"])):
        if stage in state["playoffs"]:
            continue
        def pick(ref):
            kind, key = ref
            if kind == "seed":
                return seeds[key]
            done = state["playoffs"].get(key)
            return done and done["winner" if kind == "winner" else "loser"]
        a, b = pick(x), pick(y)
        if a and b:
            return {"stage": stage, "home": a, "away": b}
    return None


def _caps(state: dict) -> dict:
    t = state["tally"]
    orange = sorted(({"id": k, **v} for k, v in t["runs"].items()), key=lambda r: (-r["runs"], r["balls"]))[:5]
    purple = sorted(({"id": k, **v} for k, v in t["wickets"].items()), key=lambda r: (-r["wickets"], r["runs"]))[:5]
    return {"orange": orange, "purple": purple}


def play_next(state: dict, teams: dict[str, Team], lineups: dict[str, dict], env: Env) -> dict | None:
    """Simulate the next fixture with the given Teams (franchise id -> Team, as they
    are now). Updates ``state``; returns the full match, or None if it's over."""
    fx = next_fixture(state)
    if fx is None:
        return None
    n = len(state["matches"]) + 1
    a, b = fx["home"], fx["away"]
    m = simulate_match(teams[a], teams[b], env, seed=state["seed"] * 1000 + n)
    full = m.to_dict()
    s = _summary(n, fx["stage"], m, {a: lineups[a], b: lineups[b]})
    state["matches"].append(s)
    name = {t["id"]: t["name"] for t in state["teams"]}
    for inn in full["innings"]:
        for bt in inn["batting_card"]:
            if bt["how_out"]:
                r = state["tally"]["runs"].setdefault(bt["id"], {"name": bt["name"], "team": inn["batting"], "runs": 0, "balls": 0})
                r["runs"] += bt["runs"]
                r["balls"] += bt["balls"]
        for bw in inn["bowling_card"]:
            w = state["tally"]["wickets"].setdefault(bw["id"], {"name": bw["name"], "team": inn["bowling"], "wickets": 0, "runs": 0})
            w["wickets"] += bw["wickets"]
            w["runs"] += bw["runs"]
    if fx["stage"] == "League":
        state["table"] = table(state["matches"], [t["name"] for t in state["teams"]])
    else:
        rank = {_ids(state)[r["team"]]: i for i, r in enumerate(state["table"])}
        if s["winner"] is None:
            win = min((a, b), key=lambda f: rank[f])
            s["margin"] = f"tied; {name[win]} go through on league position"
        else:
            win = _ids(state)[s["winner"]]
        state["playoffs"][fx["stage"]] = {"winner": win, "loser": b if win == a else a}
        if fx["stage"] == "Final":
            state["champion"] = {"id": win, "name": name[win]}
            lose = state["playoffs"]["Final"]["loser"]
            state["runner_up"] = {"id": lose, "name": name[lose]}
    state["caps"] = _caps(state)
    return full


def total_matches(state: dict) -> int:
    return len([f for f in state["fixtures"] if f["stage"] == "League"]) + len(playoff_plan(len(state["teams"])))
