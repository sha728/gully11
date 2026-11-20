"""Play a season: league, table, playoffs, caps. Pure: takes the teams, returns
the result and every full match.

Points: 2 for a win, 1 each for a tie (the engine has no super over). The table
is sorted by points, then net run rate, IPL style: runs per over scored minus
conceded, a side bowled out counted as having faced its full 20 overs. A tied
playoff goes to the team higher in the table.
"""

from __future__ import annotations

from collections import defaultdict

from ..sim.engine import Team, simulate_match
from ..sim.rates import Env
from .schedule import league, playoff_plan


def _balls(overs: str) -> int:
    o, _, b = overs.partition(".")
    return int(o) * 6 + int(b or 0)


def _summary(n: int, stage: str, m) -> dict:
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


def caps(matches: list[dict]) -> dict:
    """Orange Cap (runs) and Purple Cap (wickets), top five each."""
    runs: dict[str, dict] = defaultdict(lambda: {"runs": 0, "balls": 0, "innings": 0})
    wkts: dict[str, dict] = defaultdict(lambda: {"wickets": 0, "runs": 0, "balls": 0})
    team_of: dict[str, str] = {}
    for m in matches:
        for inn in m["innings"]:
            for b in inn["batting_card"]:
                if b["how_out"]:
                    r = runs[b["id"]]
                    r["name"], r["runs"], r["balls"], r["innings"] = b["name"], r["runs"] + b["runs"], r["balls"] + b["balls"], r["innings"] + 1
                    team_of[b["id"]] = inn["batting"]
            for b in inn["bowling_card"]:
                w = wkts[b["id"]]
                w["name"], w["wickets"], w["runs"] = b["name"], w["wickets"] + b["wickets"], w["runs"] + b["runs"]
                w["balls"] += _balls(str(b["overs"]))
                team_of[b["id"]] = inn["bowling"]
    orange = sorted(({"id": k, "team": team_of[k], **v} for k, v in runs.items()), key=lambda r: (-r["runs"], r["balls"]))[:5]
    purple = sorted(({"id": k, "team": team_of[k], **v} for k, v in wkts.items()), key=lambda r: (-r["wickets"], r["runs"]))[:5]
    return {"orange": orange, "purple": purple}


def play(teams: dict[str, Team], env: Env, seed: int) -> tuple[dict, list[dict]]:
    """``teams`` maps franchise id -> Team (named after the franchise). Returns the
    result and the full matches (in playing order)."""
    ids = list(teams)
    name = {fid: t.name for fid, t in teams.items()}
    fid_of = {t.name: fid for fid, t in teams.items()}
    summaries, full = [], []

    def run(a: str, b: str, stage: str) -> dict:
        n = len(full) + 1
        m = simulate_match(teams[a], teams[b], env, seed=seed * 1000 + n)
        full.append(m.to_dict())
        s = _summary(n, stage, m)
        summaries.append(s)
        return s

    for a, b in league(ids, seed):
        run(a, b, "League")
    standings = table(summaries, [name[f] for f in ids])
    seeds = {i + 1: fid_of[r["team"]] for i, r in enumerate(standings)}
    rank = {fid_of[r["team"]]: i for i, r in enumerate(standings)}

    outcome: dict[str, tuple[str, str]] = {}            # stage -> (winner, loser)
    for stage, x, y in playoff_plan(len(ids)):
        def pick(ref):
            kind, key = ref
            if kind == "seed":
                return seeds[key]
            return outcome[key][0 if kind == "winner" else 1]
        a, b = pick(x), pick(y)
        s = run(a, b, stage)
        if s["winner"] is None:                         # tie: the higher-placed team goes through
            win = min((a, b), key=lambda f: rank[f])
            s["margin"] = f"tied; {name[win]} go through on league position"
        else:
            win = fid_of[s["winner"]]
        outcome[stage] = (win, b if win == a else a)

    champion = outcome["Final"][0]
    return {
        "teams": [{"id": f, "name": name[f]} for f in ids],
        "matches": summaries,
        "table": standings,
        "champion": {"id": champion, "name": name[champion]},
        "runner_up": {"id": outcome["Final"][1], "name": name[outcome["Final"][1]]},
        "caps": caps(full),
    }, full
