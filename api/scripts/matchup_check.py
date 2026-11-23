"""Do matchups predict real balls better? Ball-level check on held-out IPL seasons.

For every legal ball in the chosen IPL seasons, the simulator's outcome
distribution for that batter, bowler and phase (players rated only on data from
before that season, like validate_sim.py) is scored against what actually
happened: log loss per ball (lower is better) with and without matchups, overall
and for balls where a matchup applies. Chase aggression and match conditions are
left out: this isolates the batter-v-bowler model.

    uv run python scripts/matchup_check.py --years 2024 2026
"""

from __future__ import annotations

import argparse
import math
from collections import defaultdict

import duckdb

from gully_api.sim import load_env
from gully_api.sim.engine import _Match

from validate_sim import DB, PQ, load_profiles, q

OUTCOME = {0: 1, 1: 2, 2: 3, 3: 4, 4: 5, 6: 6}   # runs off the bat -> OUTCOMES index (0 = wicket)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", nargs=2, type=int, default=[2024, 2026])
    ap.add_argument("--env", default="IPL_recent")
    args = ap.parse_args(argv)
    env = load_env(args.env).with_calibration(None, 0.0)   # no match conditions draw
    with duckdb.connect(str(DB), read_only=True) as con:
        balls = q(con, f"""
            SELECT year(m.start_date) AS yr, d.over, d.batter_id, d.bowler_id, d.runs_batter, d.is_wicket,
                   d.wicket_kind, d.player_out_id
            FROM read_parquet('{PQ.as_posix()}/deliveries.parquet') d
            JOIN read_parquet('{PQ.as_posix()}/matches.parquet') m USING (match_id)
            WHERE m.event_name = 'Indian Premier League' AND year(m.start_date) BETWEEN ? AND ?
              AND NOT d.is_super_over AND d.wides = 0 AND d.noballs = 0""", list(args.years))
        ids = {b["batter_id"] for b in balls} | {b["bowler_id"] for b in balls}
        years = sorted({b["yr"] for b in balls})
        with_mu = {y: load_profiles(con, ids, env, as_of=y, half_life=4) for y in years}
        without = {y: load_profiles(con, ids, env, as_of=y, half_life=4, matchups=False) for y in years}

    sims = {k: _Match(env, 0, False) for k in ("with", "without")}
    loss = defaultdict(lambda: [0.0, 0.0, 0])          # group -> [with, without, n]
    for b in balls:
        if b["is_wicket"] and b["wicket_kind"] in ("retired hurt", "retired not out", "retired out"):
            continue
        if b["is_wicket"] and b["player_out_id"] != b["batter_id"]:
            continue                                     # non-striker run out: not this matchup
        o = 0 if b["is_wicket"] else OUTCOME.get(b["runs_batter"])
        if o is None:
            continue
        y = b["yr"]
        bat_w, bowl_w = with_mu[y].get(b["batter_id"]), with_mu[y].get(b["bowler_id"])
        if not bat_w or not bowl_w:
            continue
        phase = env.phase(b["over"])
        pw = sims["with"].combined(bat_w, bowl_w, phase)[o]
        pn = sims["without"].combined(without[y][b["batter_id"]], without[y][b["bowler_id"]], phase)[o]
        groups = ["all"]
        if bowl_w.kind:
            groups.append(f"batter v {bowl_w.kind}")
        if bat_w.hand:
            groups.append(f"bowler v {'left' if bat_w.hand == 'L' else 'right'}-hander")
        for g in groups:
            loss[g][0] -= math.log(pw)
            loss[g][1] -= math.log(pn)
            loss[g][2] += 1
    print(f"IPL {args.years[0]}-{args.years[1]}: log loss per ball (lower is better)")
    print(f"{'balls':28}{'n':>8}{'without':>10}{'with':>10}{'change':>9}")
    for g, (w, n_, n) in sorted(loss.items(), key=lambda kv: -kv[1][2]):
        print(f"{g:28}{n:8,}{n_ / n:10.4f}{w / n:10.4f}{(w - n_) / n_:+9.2%}")


if __name__ == "__main__":
    main()
