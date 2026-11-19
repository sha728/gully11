"""Validate the Test engine (beta) against real men's Tests.

Replays real Tests with pre-match squads (11 named players ordered by career batting
share) and players rated as they stood before each season (form ratings, Test
phase stats), K times each, and compares per-innings scoring, innings length and
the draw rate with what actually happened.

    uv run python scripts/validate_test_sim.py --fit 2023 2024 --years 2025 2026 --runs 10

``--fit`` fits per-phase outcome multipliers for the "Test" environment on those
years (as validate_sim.py does for the IPL) and saves them to calibration.json.
"""

from __future__ import annotations

import argparse
import statistics
import sys
import time
import zlib
from collections import defaultdict

import json

import duckdb

from gully_api.sim import Team, load_env, simulate_test
from gully_api.sim.rates import CALIBRATION_PATH, PHASES
from validate_sim import DB, PQ, load_profiles, q


def load_tests(con, y0: int, y1: int) -> list[dict]:
    matches = q(con, f"""
        SELECT match_id, year(start_date) AS yr, team1, team2, winner, result FROM m
        WHERE match_type = 'Test' AND result IS NOT NULL AND year(start_date) BETWEEN {y0} AND {y1}
        ORDER BY start_date
    """)
    ids = [x["match_id"] for x in matches]
    inns = q(con, """
        SELECT match_id, innings, any_value(batting_team) AS team, sum(runs_total) AS runs,
               count(*) FILTER (WHERE is_legal) AS legal
        FROM d WHERE match_id IN (SELECT unnest(?)) AND innings <= 4 GROUP BY ALL
    """, [ids])
    squads = q(con, "SELECT match_id, team, player_id FROM mp WHERE match_id IN (SELECT unnest(?))", [ids])
    retired = "('retired hurt','retired not out','retired out')"
    outcomes = q(con, f"""
        SELECT match_id, CASE WHEN over < 15 THEN 'PP' WHEN over < 80 THEN 'middle' ELSE 'death' END AS phase,
               count(*) FILTER (WHERE wides = 0 AND is_wicket AND wicket_kind NOT IN {retired}) AS w,
               count(*) FILTER (WHERE wides = 0 AND runs_batter = 0 AND NOT
                                (is_wicket AND wicket_kind NOT IN {retired})) AS o0,
               count(*) FILTER (WHERE wides = 0 AND runs_batter = 1 AND NOT is_wicket) AS o1,
               count(*) FILTER (WHERE wides = 0 AND runs_batter = 2 AND NOT is_wicket) AS o2,
               count(*) FILTER (WHERE wides = 0 AND runs_batter = 3 AND NOT is_wicket) AS o3,
               count(*) FILTER (WHERE wides = 0 AND is_four) AS o4,
               count(*) FILTER (WHERE wides = 0 AND is_six) AS o6
        FROM d WHERE match_id IN (SELECT unnest(?)) AND innings <= 4 GROUP BY ALL
    """, [ids])
    by_out = defaultdict(dict)
    for r in outcomes:
        by_out[r["match_id"]][r["phase"]] = [r["w"], r["o0"], r["o1"], r["o2"], r["o3"], r["o4"], r["o6"]]
    share = dict(con.execute("SELECT id, coalesce(bat_share, 0) FROM players").fetchall())
    by_inn, by_sq = defaultdict(dict), defaultdict(list)
    for r in inns:
        by_inn[r["match_id"]][r["innings"]] = r
    for r in squads:
        by_sq[(r["match_id"], r["team"])].append(r["player_id"])
    out = []
    for mt in matches:
        mid = mt["match_id"]
        if 1 not in by_inn[mid]:
            continue
        xis = {}
        for t in (mt["team1"], mt["team2"]):
            ranked = sorted(dict.fromkeys(p for p in by_sq[(mid, t)] if p), key=lambda p: -share.get(p, 0))
            xis[t] = ranked[:11]
        if any(len(x) < 11 for x in xis.values()):
            continue
        out.append({**mt, "inns": by_inn[mid], "xis": xis, "bat_first": by_inn[mid][1]["team"],
                    "outcomes": by_out[mid]})
    return out


def replay(tests, profs, env, runs):
    """Simulate each Test ``runs`` times; aggregates plus per-phase outcome counts."""
    sim = defaultdict(list)
    sim["outcomes"] = {p: [0] * 7 for p in PHASES}
    for t in tests:
        prof = profs[t["yr"]]
        teams = {n: Team(n, [prof[p] for p in x]) for n, x in t["xis"].items() if all(p in prof for p in x)}
        if len(teams) < 2:
            continue
        first = t["bat_first"]
        second = next(n for n in teams if n != first)
        for k in range(runs):
            r = simulate_test(teams[first], teams[second], env, zlib.crc32(f"{t['match_id']}:{k}".encode()),
                              bat_first=0, commentary=False)
            for i, inn in enumerate(r.innings, start=1):
                sim[f"runs{i}"].append(inn.runs)
                sim[f"overs{i}"].append(inn.legal_balls / 6)
                for p in PHASES:
                    sim["outcomes"][p] = [a + b for a, b in zip(sim["outcomes"][p], inn.outcomes[p])]
            sim["draw"].append(r.result == "draw")
            sim["n_inns"].append(len(r.innings))
    return sim


def real_outcomes(tests):
    tot = {p: [0] * 7 for p in PHASES}
    for t in tests:
        for p, v in t["outcomes"].items():
            tot[p] = [a + b for a, b in zip(tot[p], v)]
    return {p: [c / sum(v) for c in v] for p, v in tot.items()}


def fit(tests, profs, env, runs, iterations=4):
    real = real_outcomes(tests)
    cal = {p: [1.0] * 7 for p in PHASES}
    main_idx = (0, 1, 2, 5, 6)
    for it in range(iterations):
        o = replay(tests, profs, env.with_calibration(cal, 0.0), runs)["outcomes"]
        sim = {p: [c / sum(v) for c in v] for p, v in o.items()}
        cal = {p: [c * (r / s) ** 0.7 for c, r, s in zip(cal[p], real[p], sim[p])] for p in PHASES}
        worst = max(abs(real[p][i] / sim[p][i] - 1) for p in PHASES for i in main_idx)
        print(f"  fit iteration {it + 1}: largest gap (W/0/1/4/6 by phase) before update {worst:.1%}")
    return {p: tuple(round(x, 4) for x in v) for p, v in cal.items()}


WEATHER_MAX_LOST = 200        # overs; a wet match can lose up to ~2 days
WEATHER_GRID = (0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6)


def fit_weather(tests, profs, env, runs):
    """Probability a Test loses time, chosen so the simulated draw rate matches."""
    real = statistics.mean(t["result"] == "draw" for t in tests)
    best = min(WEATHER_GRID, key=lambda p: abs(
        statistics.mean(replay(tests, profs, env.with_weather(p, WEATHER_MAX_LOST), runs)["draw"]) - real))
    print(f"  weather: p={best} (real draw rate {real:.3f})")
    return best


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", nargs=2, type=int, default=[2023, 2026])
    ap.add_argument("--runs", type=int, default=10)
    ap.add_argument("--half-life", type=int, default=4)
    ap.add_argument("--fit", nargs=2, type=int, help="fit Test calibration on these years first")
    args = ap.parse_args(argv)
    t0 = time.perf_counter()
    env = load_env("Test")
    with duckdb.connect(str(DB), read_only=True) as con:
        con.execute(f"""
            CREATE TEMP VIEW d AS SELECT * FROM read_parquet('{PQ.as_posix()}/deliveries.parquet');
            CREATE TEMP VIEW m AS SELECT * FROM read_parquet('{PQ.as_posix()}/matches.parquet');
            CREATE TEMP VIEW mp AS SELECT * FROM read_parquet('{PQ.as_posix()}/match_players.parquet');
        """)
        tests = load_tests(con, *args.years)
        fit_set = load_tests(con, *args.fit) if args.fit else []
        ids = {p for t in tests + fit_set for x in t["xis"].values() for p in x}
        profs = {y: load_profiles(con, ids, env, fmt="Test", as_of=y, half_life=args.half_life)
                 for y in {t["yr"] for t in tests + fit_set}}

    if args.fit:
        print(f"Fitting Test calibration on {len(fit_set)} Tests ({args.fit[0]}-{args.fit[1]})")
        env = env.with_weather(0.0, 0.0)   # fit outcomes on full-length matches first
        cal = fit(fit_set, profs, env, max(4, args.runs // 2))
        env = env.with_calibration(cal, 0.0)
        p_weather = fit_weather(fit_set, profs, env, max(4, args.runs // 2))
        env = env.with_weather(p_weather, WEATHER_MAX_LOST)
        data = json.loads(CALIBRATION_PATH.read_text()) if CALIBRATION_PATH.exists() else {}
        data["Test"] = {"fit_years": args.fit, "matches": len(fit_set), "ratings": "form",
                        "half_life": args.half_life, "conditions_sd": 0.0, "multipliers": cal,
                        "weather": {"p": p_weather, "max_lost": WEATHER_MAX_LOST}}
        CALIBRATION_PATH.write_text(json.dumps(data, indent=1))
        print(f"  saved -> {CALIBRATION_PATH}")

    real = defaultdict(list)
    for t in tests:
        for i, inn in t["inns"].items():
            real[f"runs{i}"].append(inn["runs"])
            real[f"overs{i}"].append(inn["legal"] / 6)
        real["draw"].append(t["result"] == "draw")
    sim = replay(tests, profs, env, args.runs)

    n = len(real["draw"])
    print(f"{n} real Tests {args.years[0]}-{args.years[1]}, {len(sim['draw'])} simulated, "
          f"{time.perf_counter() - t0:.0f}s")
    print(f"{'metric':22}{'real':>10}{'sim':>10}{'diff':>9}")
    rows = [("draw rate", statistics.mean(real["draw"]), statistics.mean(sim["draw"]))]
    for i in range(1, 5):
        if real[f"runs{i}"] and sim[f"runs{i}"]:
            rows.append((f"innings {i} runs", statistics.mean(real[f"runs{i}"]), statistics.mean(sim[f"runs{i}"])))
            rows.append((f"innings {i} overs", statistics.mean(real[f"overs{i}"]), statistics.mean(sim[f"overs{i}"])))
    for label, rv, sv in rows:
        print(f"{label:22}{rv:10.3f}{sv:10.3f}{(sv - rv) / rv if rv else 0:+9.1%}")
    print(f"innings per match: real {sum(len(t['inns']) for t in tests) / max(1, len(tests)):.2f}, "
          f"sim {statistics.mean(sim['n_inns']):.2f}")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, __file__.rsplit("\\", 1)[0].rsplit("/", 1)[0])
    sys.exit(main())
