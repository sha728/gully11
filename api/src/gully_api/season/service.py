"""From a finished auction to a season: squads, lineups, simulation, storage."""

from __future__ import annotations

import hashlib
import zlib

from psycopg.types.json import Jsonb

from ..sim import captaincy
from ..sim.engine import BowlerNeeded, Team
from ..sim.profiles import from_phase_rows
from ..sim.rates import load_env
from ..xi import service as xi
from . import lineup
from . import run

FORMAT = "IPL"


class SeasonError(ValueError):
    """Something about the season request isn't allowed (message says why)."""


def load_room(conn, code: str) -> dict:
    row = conn.execute("SELECT code, mode, result, seats FROM auction_rooms WHERE code = %s",
                       (code.upper(),)).fetchone()
    if row is None:
        raise LookupError("No finished auction with that code.")
    season = conn.execute("SELECT lineups, result FROM seasons WHERE code = %s", (row["code"],)).fetchone()
    if season is None:
        conn.execute("INSERT INTO seasons (code) VALUES (%s) ON CONFLICT DO NOTHING", (row["code"],))
        season = {"lineups": {}, "result": None}
    elif season["result"] and "fixtures" not in season["result"]:
        # A season saved by the first, all-at-once version: start it again.
        conn.execute("UPDATE seasons SET result = NULL WHERE code = %s", (row["code"],))
        conn.execute("DELETE FROM sim_results WHERE context = 'season' AND ref = %s", (row["code"],))
        season = {**season, "result": None}
    state = season["result"]
    if state and (any("balls" not in w for w in state["tally"]["wickets"].values())
                  or "impact" not in state["tally"]):
        # Tallies from before balls bowled (or player impact) were counted: rebuild them.
        state["tally"] = {"runs": {}, "wickets": {}}
        for r in conn.execute("SELECT match_json FROM sim_results WHERE context = 'season' AND ref = %s "
                              "ORDER BY match_no", (row["code"],)).fetchall():
            run.add_to_tally(state, r["match_json"])
        run.refresh_caps(state)
        conn.execute("UPDATE seasons SET result = %s WHERE code = %s", (Jsonb(state), row["code"]))
    return {**row, "lineups": season["lineups"] or {}, "season": state}


def seat_of(room: dict, token: str | None) -> str | None:
    """The franchise this token ran in the auction, if any."""
    if not token or not room["seats"]:
        return None
    h = hashlib.sha256(token.encode()).hexdigest()
    return next((fid for fid, th in room["seats"]["franchises"].items() if th == h), None)


def is_host(room: dict, token: str | None) -> bool:
    """The host starts the season. Auctions saved before seats were kept have no
    host on record: anyone may start those."""
    if not room["seats"] or not room["seats"].get("host"):
        return True
    return seat_of(room, token) == room["seats"]["host"]


def squads(conn, room: dict) -> dict[str, dict]:
    """Per franchise: its players with what the lineup picker needs, and their
    simulator profiles."""
    env = load_env(xi.FORMATS[FORMAT].env)
    all_ids = [s["id"] for f in room["result"]["franchises"] for s in f["squad"]]
    known = {r["id"] for r in conn.execute("SELECT id FROM players WHERE id = ANY(%s)", (all_ids,)).fetchall()}
    prof = xi.profiles(conn, FORMAT, sorted(known), recent=True) if known else {}
    opened = {r["player_id"]: r for r in conn.execute(
        "SELECT player_id, innings, opened FROM player_opening WHERE format = 'T20' AND player_id = ANY(%s)",
        (sorted(known),)).fetchall()}
    out = {}
    for f in room["result"]["franchises"]:
        players, profiles = {}, {}
        for s in f["squad"]:
            p = s["player"]
            pid = s["id"]
            pr = prof.get(pid) or from_phase_rows({"id": pid, "name": p["name"], "role": p["role"]}, [], env)
            o = opened.get(pid)
            bat, bowl = lineup.strengths(pr)
            players[pid] = {
                "id": pid, "name": p["name"], "role": p["role"], "overseas": p["overseas"],
                "fair": p.get("fair", 0), "price": s.get("paid", s["price"]), "retained": bool(s.get("retained")),
                "opener": bool(o and o["opened"] >= xi.OPENER_MIN_INNINGS and o["opened"] >= xi.OPENER_MIN_SHARE * o["innings"]),
                "captaincy": captaincy.summary(pid, FORMAT),
                "bat": bat, "bowl": bowl,
            }
            profiles[pid] = pr
        out[f["id"]] = {"id": f["id"], "name": f["name"], "bot": f["bot"], "owner": f.get("owner"),
                        "players": players, "profiles": profiles}
    return out


def lineup_for(team: dict, saved: dict | None) -> tuple[list[str], str | None, bool, str | None, list[str]]:
    """(xi in batting order, Impact Player chosen (None: the engine picks), picked by
    a person?, captain, named substitutes). The captain is the one chosen if they're
    in the XI, else the best-rated captain in it. Lineups saved before substitutes
    were named have one sub: the Impact Player."""
    xi_ids, impact, picked, subs = None, None, False, []
    if saved and saved.get("xi"):
        subs = saved.get("subs") or ([saved["impact"]] if saved.get("impact") else [])
        try:
            lineup.check(team["players"], saved["xi"], saved.get("impact"), subs=subs)
            xi_ids, impact, picked = saved["xi"], saved.get("impact"), True
        except lineup.LineupError:
            subs = []                               # squad changed or rules did: fall back to auto
    if xi_ids is None:
        xi_ids, _ = lineup.auto(team["players"])
        subs = lineup.auto_subs(team["players"], xi_ids)
    chosen = (saved or {}).get("captain")
    cap = chosen if chosen in xi_ids else (captaincy.best(xi_ids, FORMAT) or xi_ids[0] if xi_ids else None)
    return xi_ids, impact, picked, cap, subs


def save_lineup(conn, room: dict, fid: str, xi_ids: list[str], impact: str | None,
                captain: str | None = None, impact_out: str | None = None, impact_when: str = "auto",
                subs: list[str] | None = None) -> None:
    """Set a franchise's XI for its coming matches (before or during the season)."""
    state = room["season"]
    if state and state.get("champion"):
        raise SeasonError("The season is over.")
    team = squads(conn, room)[fid]
    if len(team["players"]) < 11:
        raise SeasonError("Your squad has fewer than eleven players: the engine picks for you.")
    try:
        subs = list(subs) if subs is not None else ([impact] if impact else [])
        lineup.check(team["players"], xi_ids, impact, impact_out, impact_when, subs=subs)
    except lineup.LineupError as e:
        raise SeasonError(str(e)) from e
    if captain is not None and captain not in xi_ids:
        raise SeasonError("Your captain has to be in your XI.")
    saved = {**room["lineups"].get(fid, {}), "xi": xi_ids, "impact": impact, "captain": captain, "subs": subs,
             "impact_out": impact_out if subs else None, "impact_when": impact_when if subs else "auto"}
    conn.execute("UPDATE seasons SET lineups = lineups || %s WHERE code = %s",
                 (Jsonb({fid: saved}), room["code"]))
    room["lineups"][fid] = saved


def _team(fid: str, team: dict, xi_ids: list[str], impact: str | None, env, captain: str | None = None,
          impact_out: str | None = None, impact_when: str = "auto", subs: list[str] | None = None) -> Team:
    profs = [team["profiles"][i] for i in xi_ids]
    # A squad short of eleven (an auction can end that way) fields replacement players.
    n = 0
    while len(profs) < 11:
        n += 1
        role = "BOWL" if n % 2 else "BAT"
        profs.append(from_phase_rows({"id": f"{fid}-rep{n}", "name": f"Replacement {n}", "role": role}, [], env))
    keeper = next((p.id for p in profs if p.role == "WK"), None)
    subs = list(subs) if subs is not None else ([impact] if impact else [])
    # With four overseas players in the XI the Impact Player must be Indian: the
    # engine only picks among the subs it may use.
    if sum(team["players"][i]["overseas"] for i in xi_ids if i in team["players"]) >= lineup.MAX_OVERSEAS:
        subs = [s for s in subs if s == impact or not team["players"][s]["overseas"]]
    return Team(team["name"], profs, keeper=keeper, impact=[team["profiles"][s] for s in subs],
                captain=captain, captaincy=captaincy.rating(captain, FORMAT) if captain else 0.0,
                impact_pick=impact, impact_out=impact_out if impact_out in xi_ids else None,
                impact_when=impact_when)


def impact_choice(saved: dict | None, xi_ids: list[str], impact: str | None, picked: bool) -> tuple[str | None, str]:
    """(who the Impact Player replaces, when he comes on) as the franchise set them;
    the engine decides both for bots."""
    if not (picked and saved):
        return None, "auto"
    out = saved.get("impact_out")
    return (out if out in xi_ids else None), saved.get("impact_when") or "auto"


def start_season(conn, room: dict) -> dict:
    """Draw the fixtures; nothing is played until the season is moved on."""
    if room["season"]:
        return room["season"]
    names = {f["id"]: f["name"] for f in room["result"]["franchises"]}
    state = run.start(names, zlib.crc32(room["code"].encode()))
    conn.execute("UPDATE seasons SET result = %s WHERE code = %s", (Jsonb(state), room["code"]))
    room["season"] = state
    return state


ADVANCE = ("next", "mine", "end")


def set_choose(conn, room: dict, fid: str, on: bool) -> None:
    """Whether this franchise's person chooses their bowler every over (their
    matches then wait for them at each over they bowl)."""
    state = room["season"]
    if state and state.get("champion"):
        raise SeasonError("The season is over.")
    saved = {**room["lineups"].get(fid, {}), "choose": bool(on)}
    conn.execute("UPDATE seasons SET lineups = lineups || %s WHERE code = %s", (Jsonb({fid: saved}), room["code"]))
    room["lineups"][fid] = saved


def _captains(room: dict, state: dict) -> dict[str, bool]:
    """Franchises whose person picks their bowlers -> True once they've let the
    engine finish the current match for them."""
    n = str(len(state["matches"]) + 1)
    chosen = state.get("bowling", {}).get(n, {})
    owners = {f["id"]: f for f in room["result"]["franchises"]}
    return {fid: chosen.get(f"rest:{fid}") == "auto" for fid, saved in room["lineups"].items()
            if saved.get("choose") and not owners.get(fid, {}).get("bot", True)}


def _teams(conn, room: dict, env) -> tuple[dict, dict]:
    teams, used = {}, {}
    for fid, team in squads(conn, room).items():
        saved = room["lineups"].get(fid)
        xi_ids, impact, picked, cap, subs = lineup_for(team, saved)
        out, when = impact_choice(saved, xi_ids, impact, picked)
        teams[fid] = _team(fid, team, xi_ids, impact, env, cap, out, when, subs)
        used[fid] = {"xi": xi_ids, "impact": impact, "subs": subs, "picked": picked, "captain": cap}
    return teams, used


def _fid_of(teams: dict, name: str) -> str | None:
    return next((f for f, t in teams.items() if t.name == name), None)


def advance(conn, room: dict, how: str, you: str | None) -> dict:
    """Play on: ``next`` (one match), ``mine`` (every match before your team's next
    one, so it's up next: change your XI, then play it), or ``end``. Each match
    uses the XIs set at the moment it's played."""
    state = room["season"]
    if not state:
        raise SeasonError("The season hasn't started.")
    if how not in ADVANCE:
        raise SeasonError("Unknown step.")
    env = load_env(xi.FORMATS[FORMAT].env)
    teams, used = _teams(conn, room, env)
    played = 0
    while True:
        fx = run.next_fixture(state)
        if fx is None:
            break
        if how == "mine" and you in (fx["home"], fx["away"]):
            break                                  # your match is next
        try:
            full = run.play_next(state, teams, used, env, _captains(room, state))
        except BowlerNeeded as e:
            # A captain's over: the season waits here until they choose (see bowl).
            bowling = e.partial["innings"][e.innings_no - 1]["bowling"]
            state["live"] = {"match": len(state["matches"]) + 1, "home": fx["home"], "away": fx["away"],
                             "stage": fx["stage"], "key": e.key, "over": e.over + 1,
                             "waiting": _fid_of(teams, bowling)}
            break
        state.pop("live", None)
        played += 1
        conn.execute("INSERT INTO sim_results (context, ref, match_no, match_json) VALUES ('season', %s, %s, %s) "
                     "ON CONFLICT (context, ref, match_no) DO UPDATE SET match_json = EXCLUDED.match_json",
                     (room["code"], len(state["matches"]), Jsonb(full)))
        if how == "next" or (how == "mine" and you is None):
            break
    conn.execute("UPDATE seasons SET result = %s, played_at = CASE WHEN %s THEN now() ELSE played_at END "
                 "WHERE code = %s", (Jsonb(state), bool(state["champion"]), room["code"]))
    return state


def live(conn, room: dict, token: str | None) -> dict:
    """The match the season is waiting on, as far as it has got: everyone can watch;
    the franchise whose over it is gets who may bowl it."""
    state = room["season"]
    if not state or not state.get("live"):
        raise SeasonError("No match is waiting for a bowler.")
    env = load_env(xi.FORMATS[FORMAT].env)
    teams, _ = _teams(conn, room, env)
    you = seat_of(room, token)
    try:
        m = run.simulate_next(state, teams, env, _captains(room, state))
    except BowlerNeeded as e:
        out = {**state["live"], "match_json": e.partial, "yours": you == state["live"]["waiting"]}
        if out["yours"]:
            out.update(options=e.options, suggested=e.suggested, innings=e.innings_no)
        return out
    return {**state["live"], "match_json": m.to_dict(), "yours": False}


def bowl(conn, room: dict, token: str | None, key: str, bowler: str) -> dict:
    """Choose who bowls the over the season is waiting on (``auto``: the engine's
    pick; ``rest``: the engine bowls the rest of this match for you). The host may
    send ``rest`` for a franchise that has gone quiet. Then the season plays on to
    the next such over, or finishes the match."""
    state = room["season"]
    wait = (state or {}).get("live")
    if not wait:
        raise SeasonError("No match is waiting for a bowler.")
    you = seat_of(room, token)
    if you != wait["waiting"] and not (bowler == "rest" and is_host(room, token)):
        raise SeasonError("It's not your over to choose.")
    if key != wait["key"]:
        raise SeasonError("That over has already been decided.")
    if bowler not in ("auto", "rest"):
        ids = {o["id"] for o in live(conn, room, token).get("options", [])}
        if bowler not in ids:
            raise SeasonError("That player can't bowl this over.")
    n = str(wait["match"])
    chosen = state.setdefault("bowling", {}).setdefault(n, {})
    if bowler == "rest":
        chosen[f"rest:{wait['waiting']}"] = "auto"
    else:
        chosen[key] = bowler
    state.pop("live", None)
    return advance(conn, room, "next", you)


def view(conn, room: dict, token: str | None) -> dict:
    """Everything the season page needs: each team's squad and current XI (so XIs
    can change mid-season), and the season so far."""
    you = seat_of(room, token)
    teams = []
    for fid, team in squads(conn, room).items():
        saved = room["lineups"].get(fid)
        xi_ids, impact, picked, cap, subs = lineup_for(team, saved)
        out, when = impact_choice(saved, xi_ids, impact, picked)
        teams.append({"id": fid, "name": team["name"], "bot": team["bot"], "owner": team["owner"],
                      "impact_out": out, "impact_when": when, "subs": subs,
                      "players": list(team["players"].values()), "xi": xi_ids, "impact": impact, "picked": picked,
                      "captain": cap, "choose": bool(room["lineups"].get(fid, {}).get("choose"))})
    state = room["season"]
    nxt = run.next_fixture(state) if state else None
    return {"code": room["code"], "mode": room["mode"], "you": you, "host": is_host(room, token),
            "next": nxt and {**nxt, "match": len(state["matches"]) + 1},
            "started": state is not None, "finished": bool(state and state["champion"]),
            "total": run.total_matches(state) if state else None, "teams": teams, "season": state}
