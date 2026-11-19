"""Spot-check aggregate tables against a recount from the raw Cricsheet JSON.

The recount below deliberately shares no code with parse.py / aggregate.py:
it walks the original match files in the zip with plain Python and tallies a
handful of players directly, then compares with ``player_format_stats``.
"""

from __future__ import annotations

import json
import zipfile
from collections import defaultdict
from pathlib import Path

import duckdb

# A spread of roles, eras and formats: batters, pace, spin, keepers, all-rounders,
# a T20-league specialist, and an IPL-era uncapped-then-capped player.
DEFAULT_PLAYERS = [
    "V Kohli", "JJ Bumrah", "JM Anderson", "MS Dhoni", "JE Root",
    "SP Narine", "BA Stokes", "AB de Villiers", "RA Jadeja", "RK Singh",
]

FIELDS = ["matches", "runs", "balls_faced", "dismissals", "balls_bowled",
          "runs_conceded", "wickets", "catches", "stumpings"]

NOT_BOWLER = {"run out", "retired hurt", "retired out", "retired not out",
              "obstructing the field", "handled the ball", "timed out"}
NOT_OUT = {"retired hurt", "retired not out"}


def formats_of(info: dict) -> list[str]:
    mt, tt = info.get("match_type"), info.get("team_type")
    ev = info.get("event")
    ev = ev.get("name") if isinstance(ev, dict) else ev
    out = []
    if mt == "Test":
        out.append("Test")
    if mt == "ODI":
        out.append("ODI")
    if mt == "T20" and tt == "international":
        out.append("T20I")
    if ev == "Indian Premier League":
        out.append("IPL")
    if mt in ("T20", "IT20"):
        out.append("T20")
    return out


def recount(zip_path: Path, player_ids: set[str]) -> dict[tuple[str, str], dict[str, int]]:
    tally: dict[tuple[str, str], dict[str, int]] = defaultdict(lambda: dict.fromkeys(FIELDS, 0))
    with zipfile.ZipFile(zip_path) as zf:
        for name in zf.namelist():
            if not name.endswith(".json") or "/" in name:
                continue
            doc = json.loads(zf.read(name))
            info = doc["info"]
            if info.get("gender") != "male":
                continue
            fmts = formats_of(info)
            if not fmts:
                continue
            reg = info.get("registry", {}).get("people", {})
            ours = {n: reg[n] for n in reg if reg[n] in player_ids}
            if not ours:
                continue

            local: dict[str, dict[str, int]] = defaultdict(lambda: dict.fromkeys(FIELDS, 0))
            for names in info.get("players", {}).values():
                for n in names:
                    if n in ours:
                        local[ours[n]]["matches"] = 1

            for inn in doc.get("innings", []):
                if inn.get("super_over"):
                    continue
                for over in inn["overs"]:
                    for d in over["deliveries"]:
                        ex = d.get("extras", {})
                        wide, nb = ex.get("wides", 0), ex.get("noballs", 0)
                        bat, bowl = d["batter"], d["bowler"]
                        if bat in ours:
                            t = local[ours[bat]]
                            t["runs"] += d["runs"]["batter"]
                            if not wide:
                                t["balls_faced"] += 1
                        if bowl in ours:
                            t = local[ours[bowl]]
                            t["runs_conceded"] += d["runs"]["batter"] + wide + nb
                            if not wide and not nb:
                                t["balls_bowled"] += 1
                        for w in d.get("wickets", []):
                            kind = w["kind"]
                            if w["player_out"] in ours and kind not in NOT_OUT:
                                local[ours[w["player_out"]]]["dismissals"] += 1
                            if bowl in ours and kind not in NOT_BOWLER:
                                local[ours[bowl]]["wickets"] += 1
                            if kind == "caught and bowled" and bowl in ours:
                                local[ours[bowl]]["catches"] += 1
                            for f in w.get("fielders", []):
                                fn = f.get("name")
                                if fn in ours and not f.get("substitute"):
                                    if kind == "caught":
                                        local[ours[fn]]["catches"] += 1
                                    elif kind == "stumped":
                                        local[ours[fn]]["stumpings"] += 1

            for pid, t in local.items():
                for fmt in fmts:
                    agg = tally[(pid, fmt)]
                    for k, v in t.items():
                        agg[k] += v
    return tally


def run(zip_path: Path, db_path: Path, names: list[str] = DEFAULT_PLAYERS) -> list[dict]:
    """Return one row per (player, format, field) with table value vs recount."""
    with duckdb.connect(str(db_path), read_only=True) as con:
        ids = dict(con.execute(
            "SELECT unique_name, id FROM players WHERE unique_name IN (SELECT unnest(?))",
            [names],
        ).fetchall())
        missing = set(names) - set(ids)
        if missing:
            raise SystemExit(f"Not in players table: {sorted(missing)}")
        table = {
            (r[0], r[1]): dict(zip(FIELDS, r[2:]))
            for r in con.execute(
                f"""SELECT player_id, format, matches, runs, balls_faced,
                           bat_innings - not_outs, balls_bowled, runs_conceded,
                           wickets, catches, stumpings
                    FROM player_format_stats WHERE player_id IN (SELECT unnest(?))""",
                [list(ids.values())],
            ).fetchall()
        }

    raw = recount(zip_path, set(ids.values()))
    by_id = {v: k for k, v in ids.items()}
    rows = []
    for key in sorted(set(table) | set(raw)):
        t, r = table.get(key, {}), raw.get(key, {})
        for f in FIELDS:
            rows.append({"player": by_id[key[0]], "format": key[1], "field": f,
                         "table": t.get(f), "raw": r.get(f)})
    return rows
