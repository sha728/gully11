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
from .run import play

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
    return {**row, "lineups": season["lineups"] or {}, "season": season["result"]}


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
    if room["season"]:
        raise SeasonError("This season has already been played.")
    team = squads(conn, room)[fid]
    if len(team["players"]) < 11:
        raise SeasonError("Your squad has fewer than eleven players: the engine picks for you.")
    try:
        lineup.check(team["players"], xi_ids, impact)
    except lineup.LineupError as e:
        raise SeasonError(str(e)) from e
    conn.execute("UPDATE seasons SET lineups = lineups || %s WHERE code = %s",
                 (Jsonb({fid: {"xi": xi_ids, "impact": impact}}), room["code"]))


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


def play_season(conn, room: dict) -> dict:
    if room["season"]:
        return room["season"]
    env = load_env(xi.FORMATS[FORMAT].env)
    sq = squads(conn, room)
    teams, lineups = {}, {}
    for fid, team in sq.items():
        xi_ids, impact, picked = lineup_for(team, room["lineups"].get(fid))
        teams[fid] = _team(fid, team, xi_ids, impact, env)
        lineups[fid] = {"xi": xi_ids, "impact": impact, "picked": picked}
    seed = zlib.crc32(room["code"].encode())
    result, full = play(teams, env, seed)
    result["lineups"] = lineups
    result["format"] = "IPL (two groups, 14 matches each)" if len(teams) == 10 else "Double round robin"
    for i, m in enumerate(full, start=1):
        conn.execute("INSERT INTO sim_results (context, ref, match_no, match_json) VALUES ('season', %s, %s, %s) "
                     "ON CONFLICT (context, ref, match_no) DO NOTHING", (room["code"], i, Jsonb(m)))
    conn.execute("UPDATE seasons SET result = %s, played_at = now() WHERE code = %s", (Jsonb(result), room["code"]))
    return result
