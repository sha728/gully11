"""Which ratings predict real balls best? Ball-level check on IPL seasons.

Scores every legal IPL ball in the chosen years against the batter-v-bowler
outcome distribution (log loss per ball, lower is better) under different
ratings, all built from data before the ball:

* start of season - form ratings as of the season's first day (half-life 4y)
* in-season xW    - the same plus each player's T20 balls from earlier that year,
                    weighted W (see validate_sim.py --in-season)

Also reports, for batters with 150+ balls in a season, how well the expected
strike rate tracks the real one. Match conditions and chase intent are left out.

    uv run python scripts/rating_check.py --years 2024 2026
"""

from __future__ import annotations

import argparse
import math
import statistics
from collections import defaultdict

import duckdb

from gully_api.sim import load_env
from gully_api.sim.engine import _Match
from gully_api.sim.rates import RUNS

from validate_sim import DB, PQ, in_season_profiles, load_profiles, q

OUTCOME = {0: 1, 1: 2, 2: 3, 3: 4, 4: 5, 6: 6}


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", nargs=2, type=int, default=[2024, 2026])
    ap.add_argument("--weights", nargs="*", type=float, default=[1.0, 2.0, 3.0])
    args = ap.parse_args(argv)
    env = load_env("IPL_recent")
    with duckdb.connect(str(DB), read_only=True) as con:
        con.execute(f"""
            CREATE TEMP VIEW d AS SELECT * FROM read_parquet('{PQ.as_posix()}/deliveries.parquet') WHERE NOT is_super_over;
            CREATE TEMP VIEW m AS SELECT * FROM read_parquet('{PQ.as_posix()}/matches.parquet');""")
        balls = q(con, """
            SELECT d.match_id, m.start_date, year(m.start_date) AS yr, d.over, d.batter_id, d.bowler_id,
                   d.runs_batter, d.is_wicket, d.wicket_kind, d.player_out_id
            FROM d JOIN m USING (match_id)
            WHERE m.event_name = 'Indian Premier League' AND year(m.start_date) BETWEEN ? AND ?
              AND d.wides = 0 AND d.noballs = 0""", list(args.years))
        players = defaultdict(set)
        dates = {}
        for b in balls:
            players[b["match_id"]] |= {b["batter_id"], b["bowler_id"]}
            dates[b["match_id"]] = b["start_date"]
        matches = [{"match_id": mid, "start_date": dates[mid], "season": str(dates[mid].year),
                    "teams": {"all": {"xi": sorted(ps), "impact": []}}} for mid, ps in players.items()]
        ids = set().union(*players.values())
        years = sorted({b["yr"] for b in balls})
        ratings = {"start of season": {y: load_profiles(con, ids, env, as_of=y, half_life=4) for y in years}}
        for w in args.weights:
            ratings[f"in-season x{w:g}"] = in_season_profiles(con, matches, env, 4, w)

    sim = _Match(env, 0, False)
    sim.conditions = 1.0
    results = {}
    for label, profs in ratings.items():
        sim._combo.clear()
        loss, n = 0.0, 0
        per_bat = defaultdict(lambda: [0, 0.0, 0])       # (batter, year) -> balls, expected runs, real runs
        for b in balls:
            if b["is_wicket"] and (b["wicket_kind"] in ("retired hurt", "retired not out", "retired out")
                                   or b["player_out_id"] != b["batter_id"]):
                continue
            o = 0 if b["is_wicket"] else OUTCOME.get(b["runs_batter"])
            if o is None:
                continue
            p = profs.get(b["match_id"]) or profs.get(b["yr"]) or {}
            bat, bowl = p.get(b["batter_id"]), p.get(b["bowler_id"])
            if not bat or not bowl:
                continue
            sim._combo.clear() if label != "start of season" else None
            v = sim.combined(bat, bowl, env.phase(b["over"]))
            loss -= math.log(v[o])
            n += 1
            s = per_bat[(b["batter_id"], b["yr"])]
            s[0] += 1
            s[1] += sum(x * r for x, r in zip(v, RUNS))
            s[2] += b["runs_batter"]
        big = [s for s in per_bat.values() if s[0] >= 150]
        corr = statistics.correlation([s[2] / s[0] for s in big], [s[1] / s[0] for s in big])
        err = statistics.mean(abs(100 * (s[1] - s[2]) / s[0]) for s in big)
        results[label] = (loss / n, n, corr, err, len(big))
    base = results["start of season"][0]
    print(f"IPL {args.years[0]}-{args.years[1]}, legal balls scored against each rating")
    print(f"{'rating':18}{'balls':>8}{'log loss':>10}{'vs start':>10}{'batter SR corr':>16}{'mean SR miss':>14}")
    for label, (ll, n, corr, err, nb) in results.items():
        print(f"{label:18}{n:8,}{ll:10.4f}{(ll - base) / base:+10.2%}{corr:16.2f}{err:14.1f}   ({nb} batter-seasons)")


if __name__ == "__main__":
    main()
