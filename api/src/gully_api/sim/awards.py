"""Player of the match and player of the series.

Every player in a match gets an impact score from their own figures, judged
against how that match went, so the same rule works for a T20 and a Test:

* batting: runs, plus a share of the runs scored above (or below) the match's
  own scoring rate for the balls they faced;
* bowling: each wicket is worth the match's runs per wicket, plus a share of the
  runs saved against the match's scoring rate for the balls they bowled.

The share is 1 in limited overs and 0.5 in Tests, where scoring rate matters less.
Players on the losing side count at 0.8, so the award usually goes to the winners
but an outstanding performance in defeat can still take it, as in real cricket.
A series award adds up the impact over all its matches.

These weights are design choices, not taken from any source.
"""

from __future__ import annotations

LOSER_WEIGHT = 0.8


def _balls(overs: str) -> int:
    o, _, b = str(overs).partition(".")
    return int(o) * 6 + int(b or 0)


def impact(match: dict, is_test: bool) -> dict[str, dict]:
    """player id -> {"id", "name", "team", "score", runs/balls/out and wickets/conceded/balls bowled}
    for one match record (``MatchResult.to_dict()``). Super overs don't count."""
    inns = match["innings"]
    runs = sum(i["runs"] for i in inns)
    balls = sum(_balls(i["overs"]) for i in inns)
    wkts = sum(i["wickets"] for i in inns)
    par = runs / balls if balls else 0.0                       # runs per ball in this match
    per_wicket = max(runs / wkts, 15.0) if wkts else 30.0      # what a wicket was worth here
    share = 0.5 if is_test else 1.0

    out: dict[str, dict] = {}

    def player(pid: str, name: str, team: str) -> dict:
        return out.setdefault(pid, {"id": pid, "name": name, "team": team, "score": 0.0,
                                    "runs": 0, "balls": 0, "innings": 0, "not_out": 0,
                                    "wickets": 0, "conceded": 0, "bowled": 0})

    for inn in inns:
        for b in inn["batting_card"]:
            if not b["how_out"]:
                continue                                       # did not bat
            p = player(b["id"], b["name"], inn["batting"])
            p["runs"] += b["runs"]
            p["balls"] += b["balls"]
            p["innings"] += 1
            p["not_out"] += b["how_out"] == "not out"
            p["score"] += b["runs"] + share * (b["runs"] - par * b["balls"])
        for b in inn["bowling_card"]:
            p = player(b["id"], b["name"], inn["bowling"])
            bowled = _balls(b["overs"])
            p["wickets"] += b["wickets"]
            p["conceded"] += b["runs"]
            p["bowled"] += bowled
            p["score"] += b["wickets"] * per_wicket + share * (par * bowled - b["runs"])

    winner = match.get("winner")
    if winner:
        for p in out.values():
            if p["team"] != winner:
                p["score"] *= LOSER_WEIGHT
    for p in out.values():
        p["score"] = round(p["score"], 1)
    return out


def figures(p: dict) -> str:
    """'87* (52) and 2/24', '5/31', '112 (240)'."""
    parts = []
    if p["innings"]:
        star = "*" if p["innings"] == p["not_out"] else ""
        parts.append(f"{p['runs']}{star} ({p['balls']})")
    if p["wickets"] or (p["bowled"] and not parts):
        parts.append(f"{p['wickets']}/{p['conceded']}")
    return " and ".join(parts) or "–"


def _award(p: dict) -> dict:
    return {"id": p["id"], "name": p["name"], "team": p["team"], "score": p["score"], "figures": figures(p)}


def player_of_match(match: dict, is_test: bool) -> dict | None:
    """The top impact score; ties go to the winners, then to more runs plus wickets."""
    scores = impact(match, is_test)
    if not scores:
        return None
    best = max(scores.values(), key=lambda p: (p["score"], p["team"] == match.get("winner"),
                                               p["runs"] + 20 * p["wickets"], p["id"]))
    return _award(best)


def player_of_series(matches: list[dict], is_test: bool) -> dict | None:
    """The most impact summed over every match of a series."""
    total: dict[str, dict] = {}
    for m in matches:
        for pid, p in impact(m, is_test).items():
            t = total.setdefault(pid, {**p, "score": 0.0, "runs": 0, "balls": 0, "innings": 0, "not_out": 0,
                                       "wickets": 0, "conceded": 0, "bowled": 0, "matches": 0})
            for k in ("score", "runs", "balls", "innings", "not_out", "wickets", "conceded", "bowled"):
                t[k] += p[k]
            t["matches"] += 1
    if not total:
        return None
    best = max(total.values(), key=lambda p: (p["score"], p["runs"] + 20 * p["wickets"], p["id"]))
    runs = f"{best['runs']} runs" if best["innings"] else ""
    wkts = f"{best['wickets']} wickets" if best["wickets"] else ""
    return {"id": best["id"], "name": best["name"], "team": best["team"], "score": round(best["score"], 1),
            "matches": best["matches"], "runs": best["runs"], "wickets": best["wickets"],
            "figures": " and ".join(x for x in (runs, wkts) if x) or "–"}


def with_award(match: dict) -> dict:
    """A saved match record with its player of the match filled in (records saved
    before awards existed don't have one)."""
    if "player_of_match" not in match:
        from .rates import load_env
        match["player_of_match"] = player_of_match(match, load_env(match["env"]).is_test)
    return match
