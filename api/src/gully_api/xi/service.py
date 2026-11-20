"""XI Builder: spin for an era and a nation (or IPL franchise), draft an XI under
role rules, play a seeded 5-match series against a fixed XI of greats.

Everything is deterministic from (format, seed, picks): the same inputs give the
same spins, the same candidate lists and the same series, which is what makes
shareable challenges and the daily challenge work.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import random
import zlib
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from ..settings import settings
from ..sim import captaincy
from ..sim import Profile, Team, from_legend, from_phase_rows, load_env, simulate_match, simulate_test

FULL_MEMBERS = ["India", "Australia", "England", "South Africa", "New Zealand", "Pakistan",
                "Sri Lanka", "West Indies", "Bangladesh", "Zimbabwe", "Afghanistan", "Ireland"]

# Franchises renamed over the years are merged under today's name.
IPL_ALIASES = {
    "Delhi Daredevils": "Delhi Capitals",
    "Kings XI Punjab": "Punjab Kings",
    "Royal Challengers Bangalore": "Royal Challengers Bengaluru",
    "Rising Pune Supergiants": "Rising Pune Supergiant",
}
# Cricsheet labels some IPL seasons by the turn of the year.
IPL_SEASON_YEAR = {"2007/08": 2008, "2009/10": 2010, "2020/21": 2020}


@dataclass(frozen=True)
class FormatSpec:
    env: str              # simulator environment
    stats: str            # which phase stats rate the players (format family)
    eras: dict[str, tuple[int, int]]
    unit: str             # "nation" or "franchise"
    min_matches: int      # in the era, to be draftable
    wicket_value: int     # runs a wicket is worth in the candidate ordering


def _decades(*starts: int) -> dict[str, tuple[int, int]]:
    return {f"{s}s": (s, s + 9) for s in starts}


FORMATS: dict[str, FormatSpec] = {
    "Test": FormatSpec("Test", "Test", _decades(1970, 1980, 1990, 2000, 2010, 2020), "nation", 5, 25),
    "ODI": FormatSpec("ODI", "ODI", _decades(1980, 1990, 2000, 2010, 2020), "nation", 10, 25),
    "T20I": FormatSpec("T20I", "T20", _decades(2000, 2010, 2020), "nation", 8, 20),
    "IPL": FormatSpec("IPL", "T20", {"2008–12": (2008, 2012), "2013–17": (2013, 2017),
                                     "2018–22": (2018, 2022), "2023–26": (2023, 2026)}, "franchise", 10, 20),
}
LEGEND_ERA_END = 2000      # legends fill eras before Cricsheet's ball-by-ball coverage
MIN_CANDIDATES = 4         # an era/side combination must offer at least this many
LIST_SIZE = 15             # candidates shown per spin
SERIES_MATCHES = 5
MAX_OVERSEAS_IPL = 4
OPENER_MIN_INNINGS = 5     # innings opened in the format...
OPENER_MIN_SHARE = 0.4     # ...and this share of their innings, to count as an opener
SPIN_TYPES = ("spin", "orthodox", "break", "unorthodox")   # legends' Wikipedia bowling types

# Batting positions. Each candidate carries the slots it may fill; the keeper must
# bat in the top six, so slot 6 is the keeper's unless one already bats higher.
SLOTS = [
    {"slot": 1, "label": "Opener", "short": "OPEN"},
    {"slot": 2, "label": "Opener", "short": "OPEN"},
    {"slot": 3, "label": "No. 3", "short": "TOP"},
    {"slot": 4, "label": "No. 4", "short": "MID"},
    {"slot": 5, "label": "No. 5", "short": "MID"},
    {"slot": 6, "label": "Keeper", "short": "WK"},
    {"slot": 7, "label": "All-rounder or spinner", "short": "AR/SPIN"},
    {"slot": 8, "label": "All-rounder or spinner", "short": "AR/SPIN"},
    {"slot": 9, "label": "Bowler", "short": "BOWL"},
    {"slot": 10, "label": "Bowler", "short": "BOWL"},
    {"slot": 11, "label": "Bowler", "short": "BOWL"},
]
KEEPER_SLOT = 6

WORLD_XI = json.loads((Path(__file__).parent / "world_xi.json").read_text())


class DraftError(ValueError):
    """The submitted XI breaks a draft rule (message says which)."""


# ------------------------------------------------------------------ candidates

def _season_year(fmt: str, season: str) -> int:
    if fmt == "IPL" and season in IPL_SEASON_YEAR:
        return IPL_SEASON_YEAR[season]
    return int(season[:4])


def _units(conn, fmt: str) -> list[str]:
    if FORMATS[fmt].unit == "nation":
        return FULL_MEMBERS
    teams = [r["team"] for r in conn.execute(
        "SELECT DISTINCT team FROM player_teams WHERE format = 'IPL'").fetchall()]
    return sorted({IPL_ALIASES.get(t, t) for t in teams})


def candidates(conn, fmt: str, era: str, unit: str) -> list[dict]:
    """Draftable players for one spin, best first. Modern players from ball-by-ball
    season stats inside the era; for eras before 2001 (Tests/ODIs), legends."""
    spec = FORMATS[fmt]
    y0, y1 = spec.eras[era]
    out: list[dict] = []

    if y0 <= LEGEND_ERA_END and fmt in ("Test", "ODI"):
        for r in conn.execute(
            "SELECT * FROM legends WHERE format = %s AND country = %s "
            "AND format_start <= %s AND format_end >= %s", (fmt, unit, y1, y0)).fetchall():
            out.append({
                "id": r["id"], "person": r["cricsheet_id"] or r["id"], "name": r["name"], "kind": "legend",
                "role": r["role"], "country": r["country"], "matches": r["matches"], "runs": r["runs"],
                "bat_avg": r["bat_avg"], "bat_sr": r["bat_sr"], "wickets": r["wickets"],
                "bowl_econ": r["bowl_econ"], "years": f"{r['format_start']}–{r['format_end']}",
                "opener": bool(r["opener"]),
                "spinner": any(t in (r["bowling_type"] or "") for t in SPIN_TYPES),
            })

    if y1 > LEGEND_ERA_END:
        # Seasons inside the era, then the player's totals across them.
        if spec.unit == "franchise":
            names = [t for t in _all_ipl_names(conn) if IPL_ALIASES.get(t, t) == unit]
            pool = conn.execute(
                "SELECT DISTINCT player_id, season FROM player_teams WHERE format = 'IPL' AND team = ANY(%s)",
                (names,)).fetchall()
        else:
            pool = conn.execute(
                "SELECT s.player_id, s.season FROM player_season_stats s JOIN players p ON p.id = s.player_id "
                "WHERE s.format = %s AND p.country = %s", (fmt, unit)).fetchall()
        keep = {(r["player_id"], r["season"]) for r in pool if y0 <= _season_year(fmt, r["season"]) <= y1}
        if keep:
            rows = conn.execute(
                """SELECT s.player_id, s.season, s.matches, s.bat_innings, s.not_outs, s.runs, s.balls_faced,
                          s.wickets, s.balls_bowled, s.runs_conceded,
                          p.name, p.full_name, p.role, p.country, p.era_start, p.era_end, p.bowling_style,
                          coalesce(o.opened, 0) AS opened, coalesce(o.innings, 0) AS innings
                   FROM player_season_stats s JOIN players p ON p.id = s.player_id
                   LEFT JOIN player_opening o ON o.player_id = s.player_id AND o.format = s.format
                   WHERE s.format = %s AND s.player_id = ANY(%s)""",
                (fmt, list({k[0] for k in keep}))).fetchall()
            agg: dict[str, dict] = {}
            for r in rows:
                if (r["player_id"], r["season"]) not in keep:
                    continue
                a = agg.setdefault(r["player_id"], {**r, "matches": 0, "bat_innings": 0, "not_outs": 0, "runs": 0,
                                                    "balls_faced": 0, "wickets": 0, "balls_bowled": 0,
                                                    "runs_conceded": 0, "y0": 9999, "y1": 0})
                for k in ("matches", "bat_innings", "not_outs", "runs", "balls_faced", "wickets",
                          "balls_bowled", "runs_conceded"):
                    a[k] += r[k]
                yr = _season_year(fmt, r["season"])
                a["y0"], a["y1"] = min(a["y0"], yr), max(a["y1"], yr)
            for pid, a in agg.items():
                if a["matches"] < spec.min_matches:
                    continue
                outs = a["bat_innings"] - a["not_outs"]
                out.append({
                    "id": pid, "person": pid, "name": a["full_name"] or a["name"], "kind": "modern",
                    "role": a["role"], "country": a["country"], "matches": a["matches"], "runs": a["runs"],
                    "bat_avg": round(a["runs"] / outs, 2) if outs else None,
                    "bat_sr": round(100 * a["runs"] / a["balls_faced"], 2) if a["balls_faced"] else None,
                    "wickets": a["wickets"],
                    "bowl_econ": round(6 * a["runs_conceded"] / a["balls_bowled"], 2) if a["balls_bowled"] else None,
                    "years": f"{a['y0']}–{a['y1']}" if a["y0"] != a["y1"] else str(a["y0"]),
                    "opener": a["opened"] >= OPENER_MIN_INNINGS and a["opened"] >= OPENER_MIN_SHARE * a["innings"],
                    "spinner": a["bowling_style"] == "spin",
                })

    for c in out:
        # Captaincy record in this format (legends by their legend id, else their Cricsheet id).
        c["captaincy"] = captaincy.summary(c["id"], fmt) or captaincy.summary(c["person"], fmt)
        c["value"] = (c["runs"] or 0) + spec.wicket_value * (c["wickets"] or 0)
        c["spinner"] = c["spinner"] and c["role"] in ("BOWL", "AR")
        c["slots"] = eligible_slots(c)
    # One entry per person (a legend who is also in Cricsheet appears once).
    best: dict[str, dict] = {}
    for c in sorted(out, key=lambda c: -c["value"]):
        best.setdefault(c["person"], c)
    return list(best.values())[:LIST_SIZE]


def eligible_slots(c: dict) -> list[int]:
    """Batting positions a player may take: openers at 1-2 (and wherever their role
    allows); batters, keepers and all-rounders 3-6; all-rounders and spinners 7-8;
    bowlers and all-rounders 9-11. Slot 6 is also subject to the keeper rule."""
    role = c["role"]
    out = [1, 2] if c.get("opener") else []
    if role in ("BAT", "WK", "AR"):
        out += [3, 4, 5, 6]
    if role == "AR" or (role == "BOWL" and c.get("spinner")):
        out += [7, 8]
    if role in ("BOWL", "AR"):
        out += [9, 10, 11]
    return out


def _all_ipl_names(conn) -> list[str]:
    return [r["team"] for r in conn.execute(
        "SELECT DISTINCT team FROM player_teams WHERE format = 'IPL'").fetchall()]


_POOL_CACHE: dict[str, list[tuple[str, str]]] = {}


def viable_combos(conn, fmt: str) -> list[tuple[str, str]]:
    """Era/side combinations with enough draftable players (cached per process)."""
    if fmt not in _POOL_CACHE:
        combos = []
        for era in FORMATS[fmt].eras:
            for unit in _units(conn, fmt):
                if len(candidates(conn, fmt, era, unit)) >= MIN_CANDIDATES:
                    combos.append((era, unit))
        _POOL_CACHE[fmt] = combos
    return _POOL_CACHE[fmt]


# ------------------------------------------------------------------ spins

def _rng(*parts) -> random.Random:
    """Spin RNG keyed with a server secret: the seed in a share link names a draw,
    but without the secret nobody can work out its spins from the (open) code."""
    key = settings.xi_secret.encode()
    digest = hmac.new(key, ":".join(map(str, parts)).encode(), hashlib.sha256).digest()
    return random.Random(int.from_bytes(digest, "big"))


def _fills(c: dict) -> set[int]:
    """Slots a candidate can fill with the keeper at 6 (the strict reading)."""
    s = set(c["slots"])
    return s if c["role"] == "WK" else s - {KEEPER_SLOT}


def _feasible(lists: list[list[dict]]) -> bool:
    """Can all eleven slots be filled, one player per spin? Bipartite matching of
    spins to slots, with the keeper at 6 so the keeper rule holds as well."""
    options = [set().union(*(_fills(c) for c in cands)) for cands in lists]
    spin_in: dict[int, int] = {}          # slot -> spin

    def place(i: int, seen: set[int]) -> bool:
        for slot in sorted(options[i]):
            if slot not in seen:
                seen.add(slot)
                if slot not in spin_in or place(spin_in[slot], seen):
                    spin_in[slot] = i
                    return True
        return False

    return all(place(i, set()) for i in range(len(lists)))


_SPIN_CACHE: dict[tuple[str, int], list[dict]] = {}
SPIN_CACHE_SIZE = 512


def spins(conn, fmt: str, seed: int) -> list[dict]:
    """Eleven seeded spins, each an (era, side) with its candidate list (cached:
    every pick and move in a draft re-checks against them)."""
    key = (fmt, seed)
    if key not in _SPIN_CACHE:
        if len(_SPIN_CACHE) >= SPIN_CACHE_SIZE:
            _SPIN_CACHE.pop(next(iter(_SPIN_CACHE)))
        _SPIN_CACHE[key] = _draw(conn, fmt, seed)
    return _SPIN_CACHE[key]


def _draw(conn, fmt: str, seed: int) -> list[dict]:
    """Re-draws deterministically until every batting slot can be filled."""
    if fmt not in FORMATS:
        raise DraftError(f"Unknown format {fmt!r}")
    combos = viable_combos(conn, fmt)
    for attempt in range(50):
        rng = _rng(fmt, seed, attempt)
        picks = [rng.choice(combos) for _ in range(11)]
        lists = [candidates(conn, fmt, era, unit) for era, unit in picks]
        if _feasible(lists):
            return [{"spin": i + 1, "era": era, "side": unit, "candidates": c}
                    for i, ((era, unit), c) in enumerate(zip(picks, lists))]
    raise RuntimeError("no feasible spin set found")  # practically unreachable


def daily_seed(fmt: str, day: date) -> int:
    return zlib.crc32(f"daily:{fmt}:{day.isoformat()}".encode())


# ------------------------------------------------------------------ the XI

def validate(conn, fmt: str, seed: int, picks: list[str], slots: list[int]) -> list[dict]:
    """Check a draft against its spins. ``picks`` are in spin order and ``slots``
    gives each pick's batting position. Returns the rows in batting order."""
    if len(picks) != 11 or len(slots) != 11:
        raise DraftError("Pick exactly 11 players, one per spin.")
    if sorted(slots) != list(range(1, 12)):
        raise DraftError("Each batting position from 1 to 11 must be filled once.")
    rows = []
    for spin, pid, slot in zip(spins(conn, fmt, seed), picks, slots):
        match = next((c for c in spin["candidates"] if c["id"] == pid), None)
        if match is None:
            raise DraftError(f"Spin {spin['spin']}: {pid} isn't on the {spin['era']} {spin['side']} list.")
        if slot not in match["slots"]:
            raise DraftError(f"{match['name']} can't bat at {slot} ({SLOTS[slot - 1]['label'].lower()}).")
        rows.append({**match, "slot": slot})
    rows.sort(key=lambda r: r["slot"])
    check_rules(fmt, rows)
    return rows


def check_rules(fmt: str, rows: list[dict]) -> None:
    people = [r["person"] for r in rows]
    if len(set(people)) != len(people):
        raise DraftError("The same player can't be picked twice.")
    if not any(r["role"] == "WK" for r in rows):
        raise DraftError("Your XI needs a wicketkeeper.")
    if all("slot" in r for r in rows) and not any(
            r["role"] == "WK" and r["slot"] <= KEEPER_SLOT for r in rows):
        raise DraftError("Your keeper has to bat in the top six.")
    if sum(r["role"] in ("BOWL", "AR") for r in rows) < 5:
        raise DraftError("Your XI needs at least five bowling options (bowlers or all-rounders).")
    if fmt == "IPL":
        overseas = sum(1 for r in rows if r.get("country") and r["country"] != "India")
        if overseas > MAX_OVERSEAS_IPL:
            raise DraftError(f"IPL sides can field at most {MAX_OVERSEAS_IPL} overseas players.")


def profiles(conn, fmt: str, ids: list[str]) -> dict[str, Profile]:
    """Simulator profiles: career phase stats for modern players (league-adjusted),
    career figures for legends."""
    spec = FORMATS[fmt]
    env = load_env(spec.env)
    out: dict[str, Profile] = {}
    legend_ids = [i for i in ids if i.startswith("L-")]
    modern_ids = [i for i in ids if not i.startswith("L-")]
    if legend_ids:
        for r in conn.execute("SELECT * FROM legends WHERE format = %s AND id = ANY(%s)",
                              (fmt if fmt in ("Test", "ODI") else "ODI", legend_ids)).fetchall():
            out[r["id"]] = from_legend(r, env)
    if modern_ids:
        players = {r["id"]: r for r in conn.execute(
            "SELECT id, coalesce(full_name, name) AS name, role FROM players WHERE id = ANY(%s)",
            (modern_ids,)).fetchall()}
        rows: dict[str, list] = {i: [] for i in modern_ids}
        for r in conn.execute("SELECT * FROM player_phase_stats WHERE format = %s AND player_id = ANY(%s)",
                              (spec.stats, modern_ids)).fetchall():
            rows[r["player_id"]].append(r)
        # Phase stats cover the format family (all T20s for the IPL); a part-timer's
        # wickets come from this format alone.
        wickets = {r["player_id"]: r["wickets"] for r in conn.execute(
            "SELECT player_id, wickets FROM player_format_stats WHERE format = %s AND player_id = ANY(%s)",
            (fmt, modern_ids)).fetchall()}
        for pid, p in players.items():
            out[pid] = from_phase_rows(p, rows[pid], env)
            out[pid].wickets = wickets.get(pid) or 0
    missing = set(ids) - set(out)
    if missing:
        raise DraftError(f"Unknown players: {sorted(missing)}")
    return out


def world_xi(conn, fmt: str) -> Team:
    cfg = WORLD_XI[fmt]
    prof = profiles(conn, fmt, cfg["players"])
    cap = cfg.get("captain") or captaincy.best(cfg["players"], fmt)
    return Team(cfg["name"], [prof[i] for i in cfg["players"]], keeper=cfg["keeper"],
                captain=cap, captaincy=captaincy.rating(cap, fmt) if cap else 0.0)


def challenge_slug(fmt: str, seed: int, picks: list[str], slots: list[int], captain: str | None = None) -> str:
    key = f"{fmt}:{seed}:{','.join(picks)}:{','.join(map(str, slots))}"
    if captain:
        key += f":c={captain}"        # same XI, different captain: a different challenge
    return hashlib.blake2b(key.encode(), digest_size=6).hexdigest()


def play_series(conn, fmt: str, seed: int, picks: list[str], slots: list[int],
                name: str = "Your XI", captain: str | None = None) -> dict:
    """Validate, then play five seeded matches against the Greats, batting in the
    chosen order, led by ``captain`` (one of the XI; default: the best-rated
    captain in it). Returns a summary plus the full match records."""
    ordered = validate(conn, fmt, seed, picks, slots)
    prof = profiles(conn, fmt, [r["id"] for r in ordered])
    keeper = next(r["id"] for r in ordered if r["role"] == "WK")
    if captain not in picks:
        captain = captaincy.best(picks, fmt) or ordered[0]["id"]
    mine = Team(name, [prof[r["id"]] for r in ordered], keeper=keeper,
                captain=captain, captaincy=captaincy.rating(captain, fmt))
    them = world_xi(conn, fmt)
    env = load_env(FORMATS[fmt].env)
    sim = simulate_test if env.is_test else simulate_match

    matches, tally = [], {"won": 0, "lost": 0, "drawn": 0, "tied": 0}
    for i in range(SERIES_MATCHES):
        m = sim(mine, them, env, zlib.crc32(f"xi:{fmt}:{seed}:{i}".encode()))
        if m.result == "draw":
            tally["drawn"] += 1
        elif m.winner is None:
            tally["tied"] += 1
        elif m.winner == mine.name:
            tally["won"] += 1
        else:
            tally["lost"] += 1
        matches.append(m)

    w, l = tally["won"], tally["lost"]
    verdict = ("Series won" if w > l else "Series lost" if l > w else "Series drawn") + f" {w}–{l}"
    def lead(team: Team) -> dict:
        p = next(x for x in team.players if x.id == team.captain) if team.captain else None
        return {"id": team.captain, "name": p.name if p else None, "rating": team.captaincy,
                "record": captaincy.summary(team.captain, fmt) if team.captain else None}

    return {
        "slug": challenge_slug(fmt, seed, picks, slots, captain),
        "format": fmt, "seed": seed, "picks": picks, "slots": slots, "opponent": them.name,
        "captains": {"mine": lead(mine), "them": lead(them)},
        "xi": [{**r, "order": r["slot"]} for r in ordered],
        "result": {**tally, "verdict": verdict},
        "matches": [_summary(m, i + 1) for i, m in enumerate(matches)],
        "_full": [m.to_dict() for m in matches],
    }


def _summary(m, n: int) -> dict:
    d = m.to_dict()
    top = max((b for inn in d["innings"] for b in inn["batting_card"]), key=lambda b: b["runs"])
    best = max((b for inn in d["innings"] for b in inn["bowling_card"]),
               key=lambda b: (b["wickets"], -b["runs"]))
    return {
        "match": n, "winner": d["winner"], "result": d["result"], "margin": d["margin"],
        "scores": [{"team": i["batting"], "runs": i["runs"], "wickets": i["wickets"], "overs": i["overs"],
                    "declared": i.get("declared", False)} for i in d["innings"]],
        "top_scorer": {"name": top["name"], "runs": top["runs"], "balls": top["balls"]},
        "best_bowler": {"name": best["name"], "wickets": best["wickets"], "runs": best["runs"]},
    }
