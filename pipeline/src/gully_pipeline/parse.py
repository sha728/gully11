"""Parse Cricsheet JSON match files into one-row-per-delivery Parquet.

Reads match JSON straight out of the downloaded zip (nothing is extracted to
disk) and writes two tables:

* ``deliveries.parquet`` - one row per delivery, legal or not
* ``matches.parquet``    - one row per match
* ``match_players.parquet`` - one row per player in each playing XI (+ subs listed)
"""

from __future__ import annotations

import json
import zipfile
from collections.abc import Iterable, Iterator
from datetime import date
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

# Phase boundaries (0-based over index, inclusive start) per limited-overs format.
# T20: powerplay 1-6, middle 7-15, death 16-20. ODI: powerplay 1-10, middle 11-40, death 41-50.
PHASES = {
    "T20": ((0, "PP"), (6, "middle"), (15, "death")),
    "IT20": ((0, "PP"), (6, "middle"), (15, "death")),
    "ODI": ((0, "PP"), (10, "middle"), (40, "death")),
    "ODM": ((0, "PP"), (10, "middle"), (40, "death")),
}

DELIVERY_SCHEMA = pa.schema([
    ("match_id", pa.string()),
    ("match_type", pa.string()),
    ("gender", pa.string()),
    ("season", pa.string()),
    ("start_date", pa.date32()),
    ("event_name", pa.string()),
    ("team_type", pa.string()),    # international / club
    ("venue", pa.string()),
    ("city", pa.string()),
    ("innings", pa.int8()),
    ("is_super_over", pa.bool_()),
    ("batting_team", pa.string()),
    ("bowling_team", pa.string()),
    ("over", pa.int16()),          # 0-based, as in Cricsheet
    ("ball_in_over", pa.int8()),   # 1-based sequence within the over, incl. extras
    ("legal_ball_in_over", pa.int8()),  # count of legal balls so far in the over (incl. this one)
    ("phase", pa.string()),        # PP / middle / death; null for Tests
    ("batter", pa.string()),
    ("batter_id", pa.string()),
    ("bowler", pa.string()),
    ("bowler_id", pa.string()),
    ("non_striker", pa.string()),
    ("non_striker_id", pa.string()),
    ("runs_batter", pa.int8()),
    ("runs_extras", pa.int8()),
    ("runs_total", pa.int8()),
    ("is_four", pa.bool_()),       # boundary four (excludes all-run fours)
    ("is_six", pa.bool_()),
    ("wides", pa.int8()),
    ("noballs", pa.int8()),
    ("byes", pa.int8()),
    ("legbyes", pa.int8()),
    ("penalty", pa.int8()),
    ("is_legal", pa.bool_()),
    ("is_wicket", pa.bool_()),
    ("wicket_count", pa.int8()),
    ("wicket_kind", pa.string()),
    ("player_out", pa.string()),
    ("player_out_id", pa.string()),
    ("bowler_credited", pa.bool_()),  # wicket counts to the bowler
    ("fielder", pa.string()),         # first fielder named on the dismissal
    ("fielder_id", pa.string()),
    ("fielder_is_sub", pa.bool_()),
])

MATCH_PLAYER_SCHEMA = pa.schema([
    ("match_id", pa.string()),
    ("team", pa.string()),
    ("player", pa.string()),
    ("player_id", pa.string()),
])

MATCH_SCHEMA = pa.schema([
    ("match_id", pa.string()),
    ("match_type", pa.string()),
    ("gender", pa.string()),
    ("season", pa.string()),
    ("start_date", pa.date32()),
    ("event_name", pa.string()),
    ("team_type", pa.string()),
    ("venue", pa.string()),
    ("city", pa.string()),
    ("team1", pa.string()),
    ("team2", pa.string()),
    ("toss_winner", pa.string()),
    ("toss_decision", pa.string()),
    ("winner", pa.string()),
    ("result", pa.string()),       # win / tie / draw / no result
    ("method", pa.string()),       # e.g. D/L
    ("overs", pa.int16()),
    ("data_version", pa.string()),
])

# Dismissals that are not credited to the bowler.
NON_BOWLER_DISMISSALS = {
    "run out", "retired hurt", "retired out", "retired not out",
    "obstructing the field", "handled the ball", "timed out",
}


def phase_for(match_type: str, over: int) -> str | None:
    bounds = PHASES.get(match_type)
    if bounds is None:
        return None
    name = bounds[0][1]
    for start, label in bounds:
        if over >= start:
            name = label
    return name


def _event_name(info: dict) -> str | None:
    event = info.get("event")
    if isinstance(event, dict):
        return event.get("name")
    return event


def _result(outcome: dict) -> tuple[str | None, str | None]:
    if "winner" in outcome:
        return outcome["winner"], "win"
    return None, outcome.get("result")


def parse_match(match_id: str, doc: dict) -> tuple[dict, list[dict], list[dict]]:
    """Return (match_row, delivery_rows, match_player_rows) for one match document."""
    info = doc["info"]
    people = info.get("registry", {}).get("people", {})
    teams = info.get("teams", [None, None])
    match_type = info.get("match_type")
    dates = info.get("dates") or [None]
    winner, result = _result(info.get("outcome", {}))
    toss = info.get("toss", {})

    common = {
        "match_id": match_id,
        "match_type": match_type,
        "gender": info.get("gender"),
        "season": str(info.get("season")) if info.get("season") is not None else None,
        "start_date": date.fromisoformat(dates[0]) if dates[0] else None,
        "event_name": _event_name(info),
        "team_type": info.get("team_type"),
        "venue": info.get("venue"),
        "city": info.get("city"),
    }

    match_row = {
        **common,
        "team1": teams[0] if len(teams) > 0 else None,
        "team2": teams[1] if len(teams) > 1 else None,
        "toss_winner": toss.get("winner"),
        "toss_decision": toss.get("decision"),
        "winner": winner,
        "result": result,
        "method": info.get("outcome", {}).get("method"),
        "overs": info.get("overs"),
        "data_version": doc.get("meta", {}).get("data_version"),
    }

    rows: list[dict] = []
    for inn_no, inn in enumerate(doc.get("innings", []), start=1):
        batting = inn.get("team")
        bowling = next((t for t in teams if t != batting), None)
        super_over = bool(inn.get("super_over", False))
        for over in inn.get("overs", []):
            over_no = over["over"]
            phase = None if super_over else phase_for(match_type, over_no)
            legal = 0
            for seq, d in enumerate(over.get("deliveries", []), start=1):
                extras = d.get("extras", {})
                wides = extras.get("wides", 0)
                noballs = extras.get("noballs", 0)
                is_legal = not wides and not noballs
                if is_legal:
                    legal += 1
                wickets = d.get("wickets", [])
                first = wickets[0] if wickets else {}
                kind = first.get("kind")
                out = first.get("player_out")
                fielders = first.get("fielders") or [{}]
                fielder = fielders[0].get("name")
                runs = d["runs"]
                boundary = not runs.get("non_boundary", False)
                rows.append({
                    **common,
                    "innings": inn_no,
                    "is_super_over": super_over,
                    "batting_team": batting,
                    "bowling_team": bowling,
                    "over": over_no,
                    "ball_in_over": seq,
                    "legal_ball_in_over": legal,
                    "phase": phase,
                    "batter": d["batter"],
                    "batter_id": people.get(d["batter"]),
                    "bowler": d["bowler"],
                    "bowler_id": people.get(d["bowler"]),
                    "non_striker": d.get("non_striker"),
                    "non_striker_id": people.get(d.get("non_striker")),
                    "runs_batter": runs.get("batter", 0),
                    "runs_extras": runs.get("extras", 0),
                    "runs_total": runs.get("total", 0),
                    "is_four": boundary and runs.get("batter", 0) == 4,
                    "is_six": boundary and runs.get("batter", 0) == 6,
                    "wides": wides,
                    "noballs": noballs,
                    "byes": extras.get("byes", 0),
                    "legbyes": extras.get("legbyes", 0),
                    "penalty": extras.get("penalty", 0),
                    "is_legal": is_legal,
                    "is_wicket": bool(wickets),
                    "wicket_count": len(wickets),
                    "wicket_kind": kind,
                    "player_out": out,
                    "player_out_id": people.get(out) if out else None,
                    "bowler_credited": bool(wickets) and kind not in NON_BOWLER_DISMISSALS,
                    "fielder": fielder,
                    "fielder_id": people.get(fielder) if fielder else None,
                    "fielder_is_sub": bool(fielders[0].get("substitute", False)),
                })

    squad_rows = [
        {"match_id": match_id, "team": team, "player": name, "player_id": people.get(name)}
        for team, names in info.get("players", {}).items()
        for name in names
    ]
    return match_row, rows, squad_rows


def iter_zip_matches(zip_path: Path) -> Iterator[tuple[str, dict]]:
    """Yield (match_id, json_doc) for each match file in a Cricsheet zip."""
    with zipfile.ZipFile(zip_path) as zf:
        for name in sorted(zf.namelist()):
            # Only flat "<id>.json" members; ignore README and anything nested.
            if not name.endswith(".json") or "/" in name or "\\" in name:
                continue
            with zf.open(name) as f:
                yield name[:-5], json.load(f)


def write_parquet(matches: Iterable[tuple[str, dict]], out_dir: Path,
                  gender: str | None = "male", batch_rows: int = 200_000) -> tuple[int, int]:
    """Parse matches and write deliveries/matches Parquet. Returns (n_matches, n_deliveries)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    n_matches = n_rows = 0
    match_rows: list[dict] = []
    squad_rows: list[dict] = []
    buf: list[dict] = []
    with pq.ParquetWriter(out_dir / "deliveries.parquet", DELIVERY_SCHEMA,
                          compression="zstd") as writer:
        for match_id, doc in matches:
            if gender and doc["info"].get("gender") != gender:
                continue
            m, rows, squads = parse_match(match_id, doc)
            match_rows.append(m)
            squad_rows.extend(squads)
            buf.extend(rows)
            n_matches += 1
            if len(buf) >= batch_rows:
                writer.write_table(pa.Table.from_pylist(buf, schema=DELIVERY_SCHEMA))
                n_rows += len(buf)
                buf.clear()
        if buf:
            writer.write_table(pa.Table.from_pylist(buf, schema=DELIVERY_SCHEMA))
            n_rows += len(buf)
    pq.write_table(pa.Table.from_pylist(match_rows, schema=MATCH_SCHEMA),
                   out_dir / "matches.parquet", compression="zstd")
    pq.write_table(pa.Table.from_pylist(squad_rows, schema=MATCH_PLAYER_SCHEMA),
                   out_dir / "match_players.parquet", compression="zstd")
    return n_matches, n_rows
