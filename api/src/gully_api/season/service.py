"""From a finished auction to a season: squads, lineups, simulation, storage."""

from __future__ import annotations

import hashlib
import zlib

from psycopg.types.json import Jsonb

from ..sim.engine import Team
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
    if state and any("balls" not in w for w in state["tally"]["wickets"].values()):
        # Tallies from before balls bowled were counted: rebuild them from the matches.
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
    prof = xi.profiles(conn, FORMAT, sorted(known)) if known else {}
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
                "bat": bat, "bowl": bowl,
            }
            profiles[pid] = pr
        out[f["id"]] = {"id": f["id"], "name": f["name"], "bot": f["bot"], "owner": f.get("owner"),
                        "players": players, "profiles": profiles}
    return out


def lineup_for(team: dict, saved: dict | None) -> tuple[list[str], str | None, bool]:
    """(xi in batting order, impact sub, picked by a person?)."""
    if saved:
        try:
            lineup.check(team["players"], saved["xi"], saved.get("impact"))
            return saved["xi"], saved.get("impact"), True
        except lineup.LineupError:
            pass                                    # squad changed or rules did: fall back to auto
    xi_ids, impact = lineup.auto(team["players"])
    return xi_ids, impact, False


def save_lineup(conn, room: dict, fid: str, xi_ids: list[str], impact: str | None) -> None:
    """Set a franchise's XI for its coming matches (before or during the season)."""
    state = room["season"]
    if state and state.get("champion"):
        raise SeasonError("The season is over.")
    team = squads(conn, room)[fid]
    if len(team["players"]) < 11:
        raise SeasonError("Your squad has fewer than eleven players: the engine picks for you.")
    try:
        lineup.check(team["players"], xi_ids, impact)
    except lineup.LineupError as e:
        raise SeasonError(str(e)) from e
    conn.execute("UPDATE seasons SET lineups = lineups || %s WHERE code = %s",
                 (Jsonb({fid: {"xi": xi_ids, "impact": impact}}), room["code"]))
    room["lineups"][fid] = {"xi": xi_ids, "impact": impact}


def _team(fid: str, team: dict, xi_ids: list[str], impact: str | None, env) -> Team:
    profs = [team["profiles"][i] for i in xi_ids]
    # A squad short of eleven (an auction can end that way) fields replacement players.
    n = 0
    while len(profs) < 11:
        n += 1
        role = "BOWL" if n % 2 else "BAT"
        profs.append(from_phase_rows({"id": f"{fid}-rep{n}", "name": f"Replacement {n}", "role": role}, [], env))
    keeper = next((p.id for p in profs if p.role == "WK"), None)
    return Team(team["name"], profs, keeper=keeper, impact=[team["profiles"][impact]] if impact else [])


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
    sq = squads(conn, room)
    teams, used = {}, {}
    for fid, team in sq.items():
        xi_ids, impact, picked = lineup_for(team, room["lineups"].get(fid))
        teams[fid] = _team(fid, team, xi_ids, impact, env)
        used[fid] = {"xi": xi_ids, "impact": impact, "picked": picked}
    played = 0
    while True:
        fx = run.next_fixture(state)
        if fx is None:
            break
        if how == "mine" and you in (fx["home"], fx["away"]):
            break                                  # your match is next
        full = run.play_next(state, teams, used, env)
        played += 1
        conn.execute("INSERT INTO sim_results (context, ref, match_no, match_json) VALUES ('season', %s, %s, %s) "
                     "ON CONFLICT (context, ref, match_no) DO UPDATE SET match_json = EXCLUDED.match_json",
                     (room["code"], len(state["matches"]), Jsonb(full)))
        if how == "next" or (how == "mine" and you is None):
            break
    conn.execute("UPDATE seasons SET result = %s, played_at = CASE WHEN %s THEN now() ELSE played_at END "
                 "WHERE code = %s", (Jsonb(state), bool(state["champion"]), room["code"]))
    return state


def view(conn, room: dict, token: str | None) -> dict:
    """Everything the season page needs: each team's squad and current XI (so XIs
    can change mid-season), and the season so far."""
    you = seat_of(room, token)
    teams = []
    for fid, team in squads(conn, room).items():
        xi_ids, impact, picked = lineup_for(team, room["lineups"].get(fid))
        teams.append({"id": fid, "name": team["name"], "bot": team["bot"], "owner": team["owner"],
                      "players": list(team["players"].values()), "xi": xi_ids, "impact": impact, "picked": picked})
    state = room["season"]
    nxt = run.next_fixture(state) if state else None
    return {"code": room["code"], "mode": room["mode"], "you": you, "host": is_host(room, token),
            "next": nxt and {**nxt, "match": len(state["matches"]) + 1},
            "started": state is not None, "finished": bool(state and state["champion"]),
            "total": run.total_matches(state) if state else None, "teams": teams, "season": state}
