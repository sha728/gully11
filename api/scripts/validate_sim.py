"""Validate (and optionally calibrate) the simulator against real IPL matches.

Replays completed, uninterrupted IPL matches with the real squads (batting order
and bowlers chosen from pre-match information) and toss outcome, K times each, and compares
simulated vs real:

* first-innings total: mean, sd, p10/p50/p90       (plan target: mean within 5%)
* boundary rate and wicket rate per legal ball     (plan target: within 5%)
* extras per innings, chasing win %
* team strength: correlation of simulated vs real win % per team-season

Calibration (``--fit Y0 Y1``): fit per-phase outcome multipliers on the fit years
so simulated outcome rates match reality, save them to sim/data/calibration.json,
then validate on ``--years`` (use years outside the fit range for an honest test).

Ratings: ``--ratings form`` (default) rates players as of each season using only
earlier data, recency-weighted (``--half-life``); ``career`` uses all data (in-sample).

    uv run python scripts/validate_sim.py --fit 2024 2025 --years 2026 2026
    uv run python scripts/validate_sim.py --years 2024 2026
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
import zlib
from collections import defaultdict
from pathlib import Path

import duckdb

from gully_api.sim import Team, from_phase_rows, load_env, simulate_match
from gully_api.sim.rates import CALIBRATION_PATH, PHASES

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "pipeline" / "data" / "gully.duckdb"
PQ = ROOT / "pipeline" / "data" / "parquet" / "all"
RETIRED = "('retired hurt','retired not out','retired out')"


def q(con, sql, params=None):
    cur = con.execute(sql, params or [])
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def load_matches(con, y0: int, y1: int) -> list[dict]:
    matches = q(con, f"""
        SELECT match_id, season, team1, team2, winner, result FROM m
        WHERE event_name = 'Indian Premier League' AND overs = 20 AND method IS NULL
          AND result IN ('win', 'tie') AND year(start_date) BETWEEN {y0} AND {y1}
          AND match_id IN (SELECT match_id FROM d GROUP BY 1 HAVING max(innings) = 2)
        ORDER BY start_date, match_id
    """)
    ids = [m["match_id"] for m in matches]
    p = [ids]
    inns = q(con, f"""
        SELECT match_id, innings, batting_team,
               sum(runs_total) AS runs, count(*) FILTER (WHERE is_legal) AS legal,
               count(*) FILTER (WHERE is_wicket AND wicket_kind NOT IN {RETIRED}) AS wkts,
               count(*) FILTER (WHERE is_four) AS fours, count(*) FILTER (WHERE is_six) AS sixes,
               sum(wides + noballs + byes + legbyes + penalty) AS extras
        FROM d WHERE match_id IN (SELECT unnest(?)) GROUP BY ALL
    """, p)
    outcomes = q(con, f"""
        SELECT match_id, phase,
               count(*) FILTER (WHERE wides = 0 AND is_wicket AND wicket_kind NOT IN {RETIRED}) AS w,
               count(*) FILTER (WHERE wides = 0 AND runs_batter = 0 AND NOT
                                (is_wicket AND wicket_kind NOT IN {RETIRED})) AS o0,
               count(*) FILTER (WHERE wides = 0 AND runs_batter = 1 AND NOT is_wicket) AS o1,
               count(*) FILTER (WHERE wides = 0 AND runs_batter = 2 AND NOT is_wicket) AS o2,
               count(*) FILTER (WHERE wides = 0 AND runs_batter = 3 AND NOT is_wicket) AS o3,
               count(*) FILTER (WHERE wides = 0 AND is_four) AS o4,
               count(*) FILTER (WHERE wides = 0 AND is_six) AS o6
        FROM d WHERE match_id IN (SELECT unnest(?)) GROUP BY ALL
    """, p)
    listed = q(con, "SELECT match_id, team, player_id AS pid FROM mp WHERE match_id IN (SELECT unnest(?))", p)

    by = defaultdict(dict)
    for r in inns:
        by[r["match_id"]][r["innings"]] = r
    outc = defaultdict(dict)
    for r in outcomes:
        outc[r["match_id"]][r["phase"]] = [r["w"], r["o0"], r["o1"], r["o2"], r["o3"], r["o4"], r["o6"]]
    squad = defaultdict(list)
    for r in listed:
        squad[(r["match_id"], r["team"])].append(r["pid"])
    # Line-ups use pre-match information only. Deriving them from the scorecard
    # (who batted, who bowled) leaks the result: a side that chased easily has few
    # batters listed, so its tail would be promoted above its unused middle order.
    bat_share = dict(con.execute(
        "SELECT id, coalesce(bat_share, 0) FROM players WHERE id IN (SELECT unnest(?))",
        [[r["pid"] for r in listed]]).fetchall())

    out = []
    for mt in matches:
        mid = mt["match_id"]
        if 1 not in by[mid] or 2 not in by[mid]:
            continue
        teams = {}
        for team in (mt["team1"], mt["team2"]):
            ranked = sorted(dict.fromkeys(squad[(mid, team)]), key=lambda p: -bat_share.get(p, 0))
            # 11 who bat, in order of career share of team balls faced; any extra
            # listed players (IPL Impact Player) join as bowling-only options.
            teams[team] = {"xi": ranked[:11], "impact": ranked[11:]}
        out.append({**mt, "inns": by[mid], "teams": teams, "outcomes": outc[mid],
                    "bat_first": by[mid][1]["batting_team"]})
    return out


def load_profiles(con, ids: set[str], env, fmt: str = "T20",
                  as_of: int | None = None, half_life: int = 0) -> dict:
    """Career ratings (player_phase_stats, all data) or, with ``as_of``, point-in-time
    form ratings from player_phase_form: only data before ``as_of``, recency-weighted."""
    players = {r["id"]: r for r in q(con, "SELECT id, name, role FROM players WHERE id IN (SELECT unnest(?))",
                                     [list(ids)])}
    rows = defaultdict(list)
    if as_of is None:
        sql = "SELECT *, player_id AS pid FROM player_phase_stats WHERE format = ? AND player_id IN (SELECT unnest(?))"
        params = [fmt, list(ids)]
    else:
        sql = ("SELECT * FROM player_phase_form WHERE format = ? AND pid IN (SELECT unnest(?)) "
               "AND as_of = ? AND half_life = ?")
        params = [fmt, list(ids), as_of, half_life]
    for r in q(con, sql, params):
        rows[r["pid"]].append(r)
    return {pid: from_phase_rows(players[pid], rows[pid], env) for pid in ids if pid in players}


def season_year(mt: dict) -> int:
    return int(str(mt["season"])[:4])


def build_teams(mt: dict, prof: dict) -> dict[str, Team]:
    teams = {}
    for name, t in mt["teams"].items():
        teams[name] = Team(name, [prof[p] for p in t["xi"]], impact=[prof[p] for p in t["impact"]])
    return teams


def replay(matches: list[dict], profs: dict[int, dict], env, runs: int) -> dict:
    """Simulate every match ``runs`` times; return aggregates mirroring ``real_stats``."""
    s = defaultdict(list)
    s["outcomes"] = {p: [0] * 7 for p in PHASES}
    s["team"] = defaultdict(lambda: [0, 0])
    for mt in matches:
        teams = build_teams(mt, profs[season_year(mt)])
        first = mt["bat_first"]
        second = next(n for n in teams if n != first)
        first_wins = 0.0
        for k in range(runs):
            seed = zlib.crc32(f"{mt['match_id']}:{k}".encode())
            r = simulate_match(teams[first], teams[second], env, seed, bat_first=0, commentary=False)
            s1, s2 = r.innings
            s["first"].append(s1.runs)
            s["wkts1"].append(s1.wickets)
            for inn in (s1, s2):
                s["legal"].append(inn.legal_balls)
                s["bound"].append(sum(b.fours + b.sixes for b in inn.bat.values()))
                s["wk"].append(inn.wickets)
                s["extras"].append(sum(inn.extras.values()))
                for p in PHASES:
                    s["outcomes"][p] = [a + b for a, b in zip(s["outcomes"][p], inn.outcomes[p])]
            s["chase_won"].append(r.winner == second)
            first_wins += 1.0 if r.winner == first else 0.5 if r.winner is None else 0.0
            for team in (first, second):
                s["team"][(mt["season"], team)][1] += 1
                s["team"][(mt["season"], team)][0] += r.winner == team
        s["p_first"].append(first_wins / runs)
    return s


def real_stats(matches: list[dict]) -> dict:
    s = defaultdict(list)
    s["outcomes"] = {p: [0] * 7 for p in PHASES}
    s["team"] = defaultdict(lambda: [0, 0])
    for mt in matches:
        first = mt["bat_first"]
        second = next(n for n in mt["teams"] if n != first)
        i1, i2 = mt["inns"][1], mt["inns"][2]
        s["first"].append(i1["runs"])
        s["wkts1"].append(i1["wkts"])
        for inn in (i1, i2):
            s["legal"].append(inn["legal"])
            s["bound"].append(inn["fours"] + inn["sixes"])
            s["wk"].append(inn["wkts"])
            s["extras"].append(inn["extras"])
        for p, v in mt["outcomes"].items():
            s["outcomes"][p] = [a + b for a, b in zip(s["outcomes"][p], v)]
        s["chase_won"].append(mt["winner"] == second)
        s["first_won"].append(1.0 if mt["winner"] == first else 0.5 if mt["winner"] is None else 0.0)
        for team in (first, second):
            s["team"][(mt["season"], team)][1] += 1
            s["team"][(mt["season"], team)][0] += mt["winner"] == team
    return s


def rates(counts: dict[str, list[int]]) -> dict[str, list[float]]:
    return {p: [c / sum(v) for c in v] for p, v in counts.items()}


CONDITION_GRID = (0.0, 0.06, 0.10, 0.14, 0.18, 0.22, 0.26)


def fit(matches, profs, env, runs: int, iterations: int = 4) -> tuple[dict[str, tuple], float]:
    """1. pick the match-conditions spread whose first-innings sd best matches reality;
    2. multiplicative fixed point: scale each phase/outcome by real/sim rate."""
    real_all = real_stats(matches)
    real_sd = statistics.stdev(real_all["first"])
    best = min(CONDITION_GRID, key=lambda sd: abs(
        statistics.stdev(replay(matches, profs, env.with_calibration(None, sd), runs)["first"]) - real_sd))
    print(f"  conditions spread: {best} (real first-innings sd {real_sd:.1f})")

    real = rates(real_all["outcomes"])
    cal = {p: [1.0] * 7 for p in PHASES}
    main = (0, 1, 2, 5, 6)  # W, dot, 1, 4, 6: the outcomes with enough balls to judge
    for it in range(iterations):
        sim = rates(replay(matches, profs, env.with_calibration(cal, best), runs)["outcomes"])
        # damped update (power 0.7) so rare outcomes (2s, 3s) don't oscillate on noise
        cal = {p: [c * (r / s) ** 0.7 for c, r, s in zip(cal[p], real[p], sim[p])] for p in PHASES}
        worst = max(abs(real[p][i] / sim[p][i] - 1) for p in PHASES for i in main)
        print(f"  fit iteration {it + 1}: largest gap (W/0/1/4/6 by phase) before update {worst:.1%}")
    return {p: tuple(round(x, 4) for x in v) for p, v in cal.items()}, best


def pct(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(p * len(xs)))]


def report(real: dict, sim: dict, tolerance: float) -> bool:
    rows = []

    def add(label, rv, sv, check=False):
        diff = (sv - rv) / rv if rv else 0.0
        rows.append((label, rv, sv, diff, (abs(diff) <= tolerance) if check else None))

    add("1st-inns total: mean", statistics.mean(real["first"]), statistics.mean(sim["first"]), True)
    add("1st-inns total: sd", statistics.stdev(real["first"]), statistics.stdev(sim["first"]))
    for p in (0.1, 0.5, 0.9):
        add(f"1st-inns total: p{int(p * 100)}", pct(real["first"], p), pct(sim["first"], p))
    add("boundaries per legal ball", sum(real["bound"]) / sum(real["legal"]),
        sum(sim["bound"]) / sum(sim["legal"]), True)
    add("wickets per legal ball", sum(real["wk"]) / sum(real["legal"]),
        sum(sim["wk"]) / sum(sim["legal"]), True)
    add("1st-inns wickets", statistics.mean(real["wkts1"]), statistics.mean(sim["wkts1"]))
    add("extras per innings", statistics.mean(real["extras"]), statistics.mean(sim["extras"]))
    add("chasing side wins", statistics.mean(real["chase_won"]), statistics.mean(sim["chase_won"]))

    keys = [k for k in real["team"] if real["team"][k][1] >= 5]
    rw = [real["team"][k][0] / real["team"][k][1] for k in keys]
    sw = [sim["team"][k][0] / sim["team"][k][1] for k in keys]
    corr = statistics.correlation(rw, sw) if len(keys) > 2 else float("nan")

    print(f"{'metric':28}{'real':>10}{'sim':>10}{'diff':>9}  check")
    for label, rv, sv, diff, ok in rows:
        mark = "" if ok is None else ("PASS" if ok else "FAIL")
        print(f"{label:28}{rv:10.3f}{sv:10.3f}{diff:+9.1%}  {mark}")
    print(f"team-season win%: real sd {statistics.pstdev(rw):.3f}, sim sd {statistics.pstdev(sw):.3f}, "
          f"correlation {corr:.2f} (n={len(keys)})")
    # Match-level accuracy: Brier score of the simulated win chance vs the result.
    # 0.25 = coin flip; lower is better. Clip to avoid 0/1 from finite runs.
    ps = [min(max(p, 0.02), 0.98) for p in sim["p_first"]]
    brier = statistics.mean((p - y) ** 2 for p, y in zip(ps, real["first_won"]))
    hits = statistics.mean((p > 0.5) == (y == 1.0) for p, y in zip(ps, real["first_won"]) if p != 0.5)
    print(f"match prediction: Brier {brier:.4f} (coin flip 0.2500), picks winner {hits:.1%}")
    return all(ok is not False for *_, ok in rows)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", nargs=2, type=int, default=[2024, 2026])
    ap.add_argument("--fit", nargs=2, type=int, help="fit calibration on these years first")
    ap.add_argument("--runs", type=int, default=20)
    ap.add_argument("--env", default="IPL_recent")
    ap.add_argument("--tolerance", type=float, default=0.05)
    ap.add_argument("--ratings", choices=["form", "career"], default="form",
                    help="form: point-in-time, recency-weighted (no look-ahead); career: all data")
    ap.add_argument("--half-life", type=int, default=4, help="years; 0 = no decay (form ratings)")
    args = ap.parse_args(argv)

    t0 = time.perf_counter()
    env = load_env(args.env)
    with duckdb.connect(str(DB), read_only=True) as con:
        con.execute(f"""
            CREATE TEMP VIEW d AS SELECT * FROM read_parquet('{PQ.as_posix()}/deliveries.parquet')
                                  WHERE NOT is_super_over;
            CREATE TEMP VIEW m AS SELECT * FROM read_parquet('{PQ.as_posix()}/matches.parquet');
            CREATE TEMP VIEW mp AS SELECT * FROM read_parquet('{PQ.as_posix()}/match_players.parquet');
        """)
        test = load_matches(con, *args.years)
        fit_set = load_matches(con, *args.fit) if args.fit else []
        ids = {p for m in test + fit_set for t in m["teams"].values() for p in t["xi"] + t["impact"]}
        years = {season_year(m) for m in test + fit_set}
        if args.ratings == "career":
            career = load_profiles(con, ids, env)
            profs = {y: career for y in years}
        else:
            profs = {y: load_profiles(con, ids, env, as_of=y, half_life=args.half_life) for y in years}

    if args.fit:
        print(f"Fitting calibration on {len(fit_set)} matches ({args.fit[0]}-{args.fit[1]})")
        cal, cond_sd = fit(fit_set, profs, env, max(5, args.runs // 2))
        data = json.loads(CALIBRATION_PATH.read_text()) if CALIBRATION_PATH.exists() else {}
        data[args.env] = {"fit_years": args.fit, "matches": len(fit_set), "ratings": args.ratings,
                          "half_life": args.half_life, "conditions_sd": cond_sd, "multipliers": cal}
        CALIBRATION_PATH.write_text(json.dumps(data, indent=1))
        env = env.with_calibration(cal, cond_sd)
        print(f"  saved -> {CALIBRATION_PATH}")

    real = real_stats(test)
    sim = replay(test, profs, env, args.runs)
    calibrated = any(v != (1.0,) * 7 for v in env.calibration.values())
    print(f"\nValidation on {len(test)} real matches {args.years[0]}-{args.years[1]}, "
          f"{len(test) * args.runs:,} simulated, env={args.env}, "
          f"{'calibrated' if calibrated else 'uncalibrated'}, ratings={args.ratings}"
          f"{f' (half-life {args.half_life}y)' if args.ratings == 'form' else ''}, {time.perf_counter() - t0:.0f}s")
    return 0 if report(real, sim, args.tolerance) else 1


if __name__ == "__main__":
    sys.exit(main())
