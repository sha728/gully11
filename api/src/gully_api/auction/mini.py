"""Mini mode: a replay of the real IPL 2026 auction (Abu Dhabi, 16 December 2025).

From ``data/ipl2026_*.csv`` (Wikipedia, CC BY-SA 4.0; rebuilt by
``gully-pipeline auction2026``):

* the ten franchises start with their real retained squads; each purse is the
  ₹125 cr cap minus those retained salaries;
* the lots are the players sold that day, in registration order, at their real
  base prices and in their real sets, with the accelerated round last;
* where each player really went, and for how much, stays on the server until the
  auction ends.

Fair prices use the same stats model as mega mode, counting only seasons before
the auction, on a curve calibrated to the money the ten teams actually had. Players Cricsheet has no record of (17 uncapped
domestic players) get their base price as the fair price.
"""

from __future__ import annotations

import csv
from pathlib import Path

from .pool import FLOOR_PRICE, RULES, _decay, _entry, _rated, _round_to_grid, price_curve
from .room import FRANCHISES

DATA = Path(__file__).parent / "data"
MARKET_SHARE = 0.85        # the real teams spent 215 of the 253 cr they had (85%)
# The auction was on 16 December 2025: stats stop before the 2025/26 season, so
# nothing played after it (IPL 2026 included) shows or counts.
BEFORE = "2025/26"


def _csv(name: str) -> list[dict]:
    with (DATA / name).open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _unrated(pid: str, row: dict, role: str, base: int) -> dict:
    """A player with no ball-by-ball record (or a retained one we can't place)."""
    return {
        "id": pid, "name": row["name"], "short_name": row["name"], "role": role,
        "country": row["country"] or None, "overseas": (row["country"] or "India") != "India",
        "capped": row.get("capped", "True") == "True", "spinner": False, "last_team": None, "last_ipl": None,
        "ipl_matches": None, "category": "", "fair": base, "base": base, "rank": 999, "record": False,
        "form": {"matches": 0, "runs": 0, "bat_avg": None, "bat_sr": None, "wickets": 0, "econ": None},
    }


def build_mini(conn) -> dict:
    rules = RULES["mini"]
    sold, retained = _csv("ipl2026_auction.csv"), _csv("ipl2026_retained.csv")
    ids = [r["player_id"] for r in sold + retained if r["player_id"]]
    rated = {p["id"]: p for p in _rated(conn, ids, before=BEFORE)}

    purse = {fid: rules["purse_lakh"] for fid, _ in FRANCHISES}
    squads: dict[str, list[dict]] = {fid: [] for fid, _ in FRANCHISES}
    players: dict[str, dict] = {}
    for i, r in enumerate(retained):
        price = int(r["salary_lakh"] or 0)
        purse[r["team"]] -= price
        pid = r["player_id"] or f"R{i}"
        p = rated.get(pid)
        players[pid] = (_entry(p, p.get("rank", 0), price, price) if p
                        else _unrated(pid, r, "BAT", price))
        squads[r["team"]].append({"id": pid, "price": price, "retained": True})

    # Fair prices: rank the lots by value (matched ones), price on a curve whose
    # total is what the room could realistically spend.
    lots = []
    for r in sold:
        pid = r["player_id"] or f"W{r['no']}"
        base = int(r["base_lakh"])
        p = rated.get(r["player_id"])
        entry = _entry(p, 0, base, base) if p else _unrated(pid, r, r["role"] or "BAT", base)
        entry.update(role=r["role"] or entry["role"], capped=r["capped"] == "True",
                     overseas=(r["country"] or "India") != "India", country=r["country"] or entry["country"])
        lots.append((r, entry, p["value"] if p else None))
    budget = MARKET_SHARE * sum(purse.values())
    ranked = sorted((e for _, e, v in lots if v is not None), key=lambda e: -rated[e["id"]]["value"])
    known = sum(e["base"] for _, e, v in lots if v is None)
    tau = _decay(len(ranked), max(budget - known, len(ranked) * FLOOR_PRICE))
    for rank, e in enumerate(ranked):
        e["rank"] = rank
        e["fair"] = max(e["base"], _round_to_grid(price_curve(rank, tau), rules["increments"]))

    return {
        "lots": [(r["set"], e) for r, e, _ in lots],
        "real": {e["id"]: {"team": r["team"], "price": int(r["price_lakh"])} for r, e, _ in lots},
        "purse": purse,
        "squads": squads,
        "players": players,
    }
