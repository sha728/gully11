"""The mega-auction player pool, built from our own data.

Everyone who has played the IPL in the last three seasons is auctionable. Each
player gets:

* a **value**: batting and bowling from the last three seasons of T20s (all
  leagues) plus a share of the whole career, each scored against specialists in
  that skill and pulled toward an ordinary player when the sample is small, plus
  a reputation term for IPL and T20I experience;
* a **fair price**: value rank mapped onto a price curve that starts at 15 crore
  and falls so that a full set of squads is worth about 92% of the room's money
  (for ten teams: the 20th player about 11.7 crore, the 60th about 7, the 100th
  about 4.2);
* a **base price** from the slabs in the rules (uncapped players at most 50 lakh);
* a **set**: marquee first, then capped batters, all-rounders, keepers, fast
  bowlers and spinners in turn, then the uncapped sets.

This is a stats model, not one trained on past auction prices: the planned
LightGBM model can replace ``values`` once a licensed price history exists.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

RULES = json.loads((Path(__file__).parent / "rules.json").read_text())

POOL_SEASONS = ("2024", "2025", "2026")      # IPL seasons that make a player auctionable
FORM_FROM = 2024                             # T20 seasons counted for form

CATEGORY_ORDER = ("BA", "AL", "WK", "FA", "SP")
CATEGORY_LABEL = {"M": "Marquee", "BA": "Batters", "AL": "All-rounders", "WK": "Wicketkeepers",
                  "FA": "Fast bowlers", "SP": "Spinners"}

# ``{before}``: only seasons before a cutoff (season labels sort in time order:
# "2025" < "2025/26" < "2026"), so a replayed auction shows nothing from after it.
_BEFORE = "(%(before)s::text IS NULL OR season < %(before)s::text)"

_SQL = """
WITH ipl AS (
    SELECT player_id, max(season) AS last_ipl, sum(matches) AS ipl_matches
    FROM player_season_stats
    WHERE format = 'IPL' AND season = ANY(%(seasons)s) AND {before}
    GROUP BY player_id
), form AS (
    SELECT player_id, sum(matches) AS m, sum(bat_innings) AS inn, sum(runs) AS runs,
           sum(balls_faced) AS bf, sum(balls_bowled) AS bb, sum(runs_conceded) AS rc,
           sum(wickets) AS w
    FROM player_season_stats
    WHERE format = 'T20' AND left(season, 4)::int >= %(form_from)s AND {before}
    GROUP BY player_id
), career AS (
    SELECT player_id, sum(matches) AS m, sum(bat_innings) AS inn, sum(runs) AS runs,
           sum(balls_faced) AS bf, sum(balls_bowled) AS bb, sum(runs_conceded) AS rc,
           sum(wickets) AS w
    FROM player_season_stats WHERE format = 'T20' AND {before}
    GROUP BY player_id
), caps AS (
    SELECT player_id,
           sum(matches) FILTER (WHERE format = 'IPL') AS ipl_career,
           sum(matches) FILTER (WHERE format = 'T20I') AS t20i_career
    FROM player_season_stats WHERE format IN ('IPL', 'T20I') AND {before}
    GROUP BY player_id
), team AS (
    SELECT DISTINCT ON (player_id) player_id, team
    FROM player_teams WHERE format = 'IPL' AND {before}
    ORDER BY player_id, season DESC, matches DESC
)
SELECT p.id, coalesce(p.full_name, p.name) AS name, p.name AS short_name, p.role, p.country,
       p.capped, p.is_overseas_for_ipl, p.bowling_style,
       ipl.last_ipl, ipl.ipl_matches, team.team AS last_team,
       f.m, f.inn, f.runs, f.bf, f.bb, f.rc, f.w,
       coalesce(caps.ipl_career, 0) AS ipl_career, coalesce(caps.t20i_career, 0) AS t20i_career,
       c.m AS c_m, c.inn AS c_inn, c.runs AS c_runs, c.bf AS c_bf, c.bb AS c_bb, c.rc AS c_rc, c.w AS c_w
FROM players p
LEFT JOIN ipl ON ipl.player_id = p.id
LEFT JOIN form f ON f.player_id = p.id
LEFT JOIN career c ON c.player_id = p.id
LEFT JOIN caps ON caps.player_id = p.id
LEFT JOIN team ON team.player_id = p.id
WHERE ipl.player_id IS NOT NULL OR p.id = ANY(%(extra)s)
""".replace("{before}", _BEFORE)

REPUTATION_WEIGHT = 0.45  # IPL and T20I experience, next to form
CAREER_WEIGHT = 0.35      # career T20 numbers count this much next to the last three seasons


def _overrides() -> dict[str, dict]:
    """Hand-filled nationalities for players Cricsheet can't place (see nationality.csv)."""
    rows = (Path(__file__).parent / "nationality.csv").read_text(encoding="utf-8").splitlines()[1:]
    out = {}
    for line in rows:
        pid, _name, country, capped, *_ = line.split(",")
        out[pid] = {"country": country, "capped": capped == "true"}
    return out


def overseas(row: dict) -> bool:
    """Cricsheet has no country for some players (Afghanistan's internationals, most
    uncapped Indians). A capped player with no country played international cricket
    for someone, and India's internationals always have one, so they're overseas;
    an uncapped one with no country is almost always a domestic Indian player."""
    if row["is_overseas_for_ipl"] is not None:
        return bool(row["is_overseas_for_ipl"])
    return bool(row["capped"])


def _blend(row: dict, key: str) -> float:
    return (row[key] or 0) + CAREER_WEIGHT * (row[f"c_{key}"] or 0)


def skills(row: dict) -> tuple[float, float]:
    """(batting, bowling): the last three seasons of T20s plus a share of the whole
    career, pulled toward an ordinary player for the role when the sample is small,
    so a few months of big hitting don't outweigh years of it.

    Batting is runs per innings plus the extra runs a strike rate above 130 adds
    over the balls faced per innings."""
    inn, runs, bf = (_blend(row, k) for k in ("inn", "runs", "bf"))
    bb, rc, w = (_blend(row, k) for k in ("bb", "rc", "w"))
    batter = row["role"] in ("BAT", "WK", "AR")
    rpi = (runs + (18 if batter else 6) * 8) / (inn + 8)
    sr = 100 * (runs + 1.25 * 150) / (bf + 150)
    bpi = 100 * rpi / sr
    bat = rpi + (sr - 130) / 100 * bpi
    k = 240
    per24 = (w + k / 24 * 0.9) / ((bb + k) / 24)          # wickets per four overs
    econ = 6 * (rc + 8.8 / 6 * k) / (bb + k)
    bowl = per24 * (8.8 / econ) ** 2
    return bat, bowl


def _z(xs: list[float]) -> tuple[float, float]:
    m = sum(xs) / len(xs)
    sd = (sum((x - m) ** 2 for x in xs) / len(xs)) ** 0.5 or 1.0
    return m, sd


def values(rows: list[dict]) -> list[float]:
    """Each skill scored against the specialists in it (batting against batters and
    keepers, bowling against bowlers), so a top bowler is worth as much as a top
    batter. All-rounders add 60% of their weaker skill when it's above average.
    Scaled by sample size and by how recently they played the IPL."""
    raw = [skills(r) for r in rows]
    bm, bs = _z([b for (b, _), r in zip(raw, rows) if r["role"] in ("BAT", "WK")] or [0.0])
    wm, ws = _z([w for (_, w), r in zip(raw, rows) if r["role"] == "BOWL"] or [0.0])
    out = []
    for (bat, bowl), r in zip(raw, rows):
        zb, zw = (bat - bm) / bs, (bowl - wm) / ws
        role = r["role"]
        if role in ("BAT", "WK"):
            v = zb + 0.3 * max(0.0, zw)
        elif role == "BOWL":
            v = zw + 0.3 * max(0.0, zb)
        else:
            v = max(zb, zw) + 0.6 * max(0.0, min(zb, zw) + 0.5)
        v += 0.3 if role == "WK" else 0.0
        m = (r["m"] or 0) + CAREER_WEIGHT * (r["c_m"] or 0)
        v *= m / (m + 20)                                     # proven, not a few good weeks
        v *= {"2026": 1.0, "2025": 0.92}.get(r["last_ipl"], 0.85)
        out.append(v)
    # Reputation: franchises pay for proven names, not only this year's numbers.
    rep = [math.log1p(r["ipl_career"]) + 0.5 * math.log1p(r["t20i_career"]) for r in rows]
    rm, rs = _z(rep)
    return [v + REPUTATION_WEIGHT * (x - rm) / rs for v, x in zip(out, rep)]


def _round_to_grid(lakh: float, increments: list) -> int:
    """Down to a price a bid could actually reach."""
    for limit, step in increments:
        if limit is None or lakh < limit:
            return int(lakh // step * step)
    return int(lakh)


TOP_PRICE = 1500          # lakh: the best player's fair price (sales run above it when bots compete)
FLOOR_PRICE = 30
MARKET_SHARE = 0.92       # share of all purses the fair prices of a full set of squads add up to
SQUAD_TARGET = 21         # players per squad the market is priced for


def decay_for(teams: int, purse: int) -> float:
    """Steepness of the price curve so that the fair prices of the best
    ``teams * SQUAD_TARGET`` players add up to ``MARKET_SHARE`` of all purses: the
    room's money, not a fixed table, sets what a mid-ranked player is worth."""
    return _decay(teams * SQUAD_TARGET, MARKET_SHARE * teams * purse)


def _decay(n: int, budget: float) -> float:
    """Curve steepness at which the best ``n`` fair prices add up to ``budget``."""
    def total(tau: float) -> float:
        return sum(price_curve(i, tau) for i in range(n))

    lo, hi = 1.0, 500.0
    for _ in range(60):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if total(mid) < budget else (lo, mid)
    return lo


def price_curve(rank: int, tau: float) -> float:
    """Fair price in lakh for the player ranked ``rank`` (0 = best)."""
    return FLOOR_PRICE + (TOP_PRICE - FLOOR_PRICE) * math.exp(-rank / tau)


def base_price(fair: int, capped: bool, rules: dict) -> int:
    slabs = rules["base_prices"]
    allowed = [b for b in slabs if (b >= rules["capped_min_base"] if capped else b <= rules["uncapped_max_base"])]
    fit = [b for b in allowed if b <= fair * 0.3]
    return max(fit) if fit else min(allowed)


def pool_size(teams: int) -> int:
    """Enough players for every squad to reach the maximum, plus a few spare."""
    return teams * RULES["mega"]["squad_max"] + 20


def _rated(conn, extra: list[str] = (), before: str | None = None) -> list[dict]:
    """Every player from the last three IPL seasons (plus ``extra`` ids), with
    nationality fixes and a value, best first. Values are scored across this whole
    population, so a player's rating doesn't depend on who else is in a room.
    ``before``: count only seasons before this label (a replayed auction)."""
    rows = conn.execute(_SQL, {"seasons": list(POOL_SEASONS), "form_from": FORM_FROM,
                               "extra": list(extra), "before": before}).fetchall()
    fixes = _overrides()
    rows = [{**r, **({**fixes[r["id"]], "is_overseas_for_ipl": fixes[r["id"]]["country"] != "India"}
                     if r["id"] in fixes else {})} for r in rows]
    players = [{**r, "overseas": overseas(r), "value": v} for r, v in zip(rows, values(rows))]
    players.sort(key=lambda p: (-p["value"], p["id"]))
    return players


def _entry(p: dict, rank: int, fair: int, base: int) -> dict:
    bowl_type = "SP" if p["bowling_style"] == "spin" else "FA"
    cat = {"BAT": "BA", "AR": "AL", "WK": "WK", "BOWL": bowl_type}[p["role"]]
    inn, bb = p["inn"] or 0, p["bb"] or 0
    return {
        "id": p["id"], "name": p["name"], "short_name": p["short_name"], "role": p["role"],
        "country": p["country"], "overseas": p["overseas"], "capped": p["capped"],
        "spinner": p["bowling_style"] == "spin" and p["role"] in ("BOWL", "AR"),
        "last_team": p["last_team"], "last_ipl": p["last_ipl"], "ipl_matches": p["ipl_career"],
        "category": cat, "fair": fair, "base": base, "rank": rank, "record": True,
        "form": {
            "matches": p["m"] or 0, "runs": p["runs"] or 0,
            "bat_avg": round(p["runs"] / inn, 1) if inn else None,
            "bat_sr": round(100 * p["runs"] / p["bf"], 1) if p["bf"] else None,
            "wickets": p["w"] or 0,
            "econ": round(6 * p["rc"] / bb, 2) if bb >= 60 else None,
        },
    }


def build_pool(conn, mode: str = "mega", teams: int = 10) -> list[dict]:
    """Mega-auction lots for a room of ``teams`` franchises, best first (sets and
    the per-room shuffle come later)."""
    rules = RULES[mode]
    tau = decay_for(teams, rules["purse_lakh"])
    out = []
    for rank, p in enumerate(_rated(conn)[: pool_size(teams)]):
        fair = max(_round_to_grid(price_curve(rank, tau), rules["increments"]), FLOOR_PRICE)
        base = base_price(fair, p["capped"], rules)
        out.append(_entry(p, rank, max(fair, base), base))
    return out


def make_sets(pool: list[dict], rules: dict) -> list[tuple[str, list[dict]]]:
    """Marquee sets, then capped categories in turn, then uncapped, each in sets of
    ``set_size`` (best first). Returns [(set code, players)]."""
    by_fair = sorted(pool, key=lambda p: -p["fair"])
    marquee = by_fair[: rules["marquee"]]
    rest = by_fair[rules["marquee"]:]
    sets: list[tuple[str, list[dict]]] = []
    half = math.ceil(len(marquee) / 2)
    for i, chunk in enumerate((marquee[:half], marquee[half:]), start=1):
        if chunk:
            sets.append((f"M{i}", chunk))
    size = rules["set_size"]
    for capped in (True, False):
        queues = {c: [p for p in rest if p["capped"] == capped and p["category"] == c] for c in CATEGORY_ORDER}
        n = 1
        while any(queues.values()):
            for c in CATEGORY_ORDER:
                if queues[c]:
                    chunk, queues[c] = queues[c][:size], queues[c][size:]
                    sets.append((f"{'' if capped else 'U'}{c}{n}", chunk))
            n += 1
    return sets


def set_label(code: str) -> str:
    uncapped = code.startswith("U")
    core = code[1:] if uncapped else code
    cat = "M" if core.startswith("M") else core[:2]
    return f"{'Uncapped ' if uncapped else ''}{CATEGORY_LABEL[cat].lower() if uncapped else CATEGORY_LABEL[cat]} · set {core[len(cat):]}"
