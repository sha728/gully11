"""Captaincy ratings from real captaincy records (data/captains.csv, built by
``gully-pipeline captains`` from Wikipedia's captain lists).

A captain's tactical rating (0..1) for a format is

    experience * (0.6 + 0.8 * (win rate - 0.5))

* experience = m / (m + 30), m = matches captained (in this format, plus half the
  matches in the closest related one: IPL and T20Is count for each other, ODIs and
  Tests too), so a few games in charge count for little;
* win rate = (won + half the ties + 10) / (decided games + 20): the record pulled
  toward 50% so a short winning streak isn't greatness.

Never captained: 0. MS Dhoni in the IPL (235 matches, 58% won) rates about 0.6;
one season in charge with an average record, about 0.25.

The rating decides how well the captain calls the toss and makes bowling
changes (see engine.py); it never changes anyone's batting or bowling.
"""

from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).parent / "data" / "captains.csv"

# Records that inform each simulated format: (its own, a related one at half weight).
RELATED = {"IPL": ("IPL", "T20I"), "T20I": ("T20I", "IPL"), "ODI": ("ODI", "Test"), "Test": ("Test", "ODI")}
EXPERIENCE_HALF = 30         # matches in charge for half the experience credit
PRIOR_GAMES = 20             # games of a 50% record the win rate is pulled toward


@lru_cache(maxsize=1)
def _records() -> dict[tuple[str, str], dict]:
    """(player or legend id, format) -> record."""
    out: dict[tuple[str, str], dict] = {}
    if not DATA.exists():
        return out
    with DATA.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rec = {k: int(r[k]) for k in ("matches", "won", "lost", "tied", "drawn", "nr")}
            rec["name"] = r["name"]
            for pid in (r["player_id"], r["legend_id"]):
                if pid:
                    out[(pid, r["format"])] = rec
    return out


def record(pid: str, fmt: str) -> dict | None:
    """The captaincy record in exactly this format, if any."""
    return _records().get((pid, fmt))


def rating(pid: str, fmt: str) -> float:
    own, near = RELATED.get(fmt, (fmt, fmt))
    m = won = tied = decided = 0.0
    for f, w in ((own, 1.0), (near, 0.5)):
        r = record(pid, f)
        if r:
            m += w * r["matches"]
            won += w * r["won"]
            tied += w * r["tied"]
            decided += w * (r["won"] + r["lost"] + r["tied"])
    if m == 0:
        return 0.0
    experience = m / (m + EXPERIENCE_HALF)
    rate = (won + 0.5 * tied + PRIOR_GAMES / 2) / (decided + PRIOR_GAMES)
    return round(max(0.0, min(1.0, experience * (0.6 + 0.8 * (rate - 0.5)))), 3)


def summary(pid: str, fmt: str) -> dict | None:
    """What the UI shows: the record in this format (or the related one) and the rating."""
    own, near = RELATED.get(fmt, (fmt, fmt))
    r, f = record(pid, own), own
    if r is None:
        r, f = record(pid, near), near
    if r is None:
        return None
    decided = r["won"] + r["lost"] + r["tied"]
    return {"format": f, "matches": r["matches"], "won": r["won"], "lost": r["lost"],
            "win_pct": round(100 * (r["won"] + 0.5 * r["tied"]) / decided, 1) if decided else None,
            "rating": rating(pid, fmt)}


def best(ids: list[str], fmt: str) -> str | None:
    """The best-rated captain among these players (None if nobody has captained)."""
    scored = [(rating(i, fmt), i) for i in ids]
    top = max(scored, default=(0.0, None))
    return top[1] if top[0] > 0 else None
