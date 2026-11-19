"""Generate the simulator's base-rate file from the parsed deliveries.

Writes ``api/src/gully_api/sim/data/base_rates.json`` (committed; regenerate when
the data refreshes). For each *environment* (a format, optionally limited to
recent years) and phase it stores raw outcome counts - the simulator turns
them into probabilities - plus extras, wicket kinds, first-innings score
distributions and a "remaining runs" table used for win probability.

Count definitions match ``player_phase_stats`` exactly, so the league baseline
and individual players are measured the same way:

* bat:  balls = deliveries faced (wides excluded); wickets = any dismissal on
        the delivery (incl. run outs, excl. retirements); dots include wicket balls
* bowl: balls = legal deliveries; wickets = credited to the bowler;
        dots = legal balls conceding nothing
"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb

from .aggregate import TEST_PHASE
from .paths import PIPELINE_ROOT

OUT_PATH = PIPELINE_ROOT.parent / "api" / "src" / "gully_api" / "sim" / "data" / "base_rates.json"

# name -> (format, first year, last year, overs)
ENVS = {
    "T20": ("T20", None, None, 20),
    "T20I": ("T20I", None, None, 20),
    "IPL": ("IPL", None, None, 20),
    "IPL_recent": ("IPL", 2024, 2026, 20),
    "ODI": ("ODI", None, None, 50),
    "ODI_recent": ("ODI", 2023, 2026, 50),
    "Test": ("Test", None, None, 0),     # overs 0 = no limit (two innings each)
}
# Resource (remaining-runs) tables are built on the large all-time format sets
# and rescaled per environment by its average first-innings total.
RESOURCE_BASE = {20: "T20", 50: "ODI"}

RETIRED = "('retired hurt', 'retired not out', 'retired out')"
MIN_CELL = 40  # min innings-states per resource cell before smoothing kicks in


def _env_view(con, fmt: str, y0: int | None, y1: int | None) -> None:
    yr = f"AND year(start_date) BETWEEN {y0} AND {y1}" if y0 else ""
    con.execute(f"""
        CREATE OR REPLACE TEMP VIEW e AS
        SELECT d.* EXCLUDE (phase), {TEST_PHASE.format(table='d')} AS phase
        FROM d JOIN match_formats f USING (match_id)
        WHERE f.format = '{fmt}' {yr}
    """)


def _phase_counts(con) -> dict:
    out: dict = {}
    bat = con.execute(f"""
        SELECT phase,
               count(*) FILTER (WHERE wides = 0) AS balls,
               count(*) FILTER (WHERE wides = 0 AND is_wicket
                                AND wicket_kind NOT IN {RETIRED}) AS wickets,
               count(*) FILTER (WHERE wides = 0 AND runs_batter = 0) AS dots,
               count(*) FILTER (WHERE wides = 0 AND runs_batter = 1) AS ones,
               count(*) FILTER (WHERE wides = 0 AND runs_batter = 2) AS twos,
               count(*) FILTER (WHERE wides = 0 AND runs_batter = 3) AS threes,
               count(*) FILTER (WHERE is_four) AS fours,
               count(*) FILTER (WHERE is_six) AS sixes
        FROM e WHERE phase IS NOT NULL GROUP BY phase
    """).fetchall()
    bowl = con.execute("""
        SELECT phase,
               count(*) FILTER (WHERE is_legal) AS balls,
               count(*) FILTER (WHERE bowler_credited) AS wickets,
               count(*) FILTER (WHERE is_legal AND runs_batter + wides + noballs = 0) AS dots,
               count(*) FILTER (WHERE is_legal AND runs_batter = 1) AS ones,
               count(*) FILTER (WHERE is_legal AND runs_batter = 2) AS twos,
               count(*) FILTER (WHERE is_legal AND runs_batter = 3) AS threes,
               count(*) FILTER (WHERE is_legal AND is_four) AS fours,
               count(*) FILTER (WHERE is_legal AND is_six) AS sixes,
               count(*) FILTER (WHERE wides > 0) AS wide_balls,
               count(*) FILTER (WHERE noballs > 0) AS noball_balls
        FROM e WHERE phase IS NOT NULL GROUP BY phase
    """).fetchall()
    cols_bat = ["balls", "wickets", "dots", "ones", "twos", "threes", "fours", "sixes"]
    cols_bowl = cols_bat + ["wide_balls", "noball_balls"]
    for row in bat:
        out.setdefault(row[0], {})["bat"] = dict(zip(cols_bat, row[1:]))
    for row in bowl:
        out.setdefault(row[0], {})["bowl"] = dict(zip(cols_bowl, row[1:]))
    return out


def _dist(con, sql: str) -> dict[str, int]:
    return {str(k): v for k, v in con.execute(sql).fetchall()}


def _extras(con) -> dict:
    legal = con.execute("SELECT count(*) FILTER (WHERE is_legal) FROM e").fetchone()[0]
    clean_dot = con.execute(
        "SELECT count(*) FROM e WHERE is_legal AND runs_batter = 0 AND NOT is_wicket"
    ).fetchone()[0]
    return {
        "legal_balls": legal,
        "wide_runs": _dist(con, "SELECT wides, count(*) FROM e WHERE wides > 0 GROUP BY 1"),
        # byes/leg-byes only modelled on otherwise-dot legal balls
        "clean_dots": clean_dot,
        "bye_runs": _dist(con, """SELECT byes + legbyes, count(*) FROM e
                                  WHERE is_legal AND runs_batter = 0 AND NOT is_wicket
                                    AND byes + legbyes > 0 GROUP BY 1"""),
        "wicket_kinds": _dist(con, f"""SELECT wicket_kind, count(*) FROM e
                                       WHERE is_wicket AND wicket_kind NOT IN {RETIRED}
                                       GROUP BY 1"""),
    }


def _full_first_innings(con, overs: int) -> str:
    """SQL for first innings that ran their natural course (all out or full overs,
    no rain rule, no reduced-overs match)."""
    return f"""
        WITH inn AS (
            SELECT match_id, sum(runs_total) AS total,
                   sum(wicket_count) FILTER (WHERE wicket_kind NOT IN {RETIRED}
                                              OR wicket_kind IS NULL) AS wkts,
                   count(*) FILTER (WHERE is_legal) AS legal
            FROM e WHERE innings = 1 GROUP BY 1
        )
        SELECT inn.* FROM inn JOIN m USING (match_id)
        WHERE {"m.result IS NOT NULL" if overs == 0 else
               f"m.overs = {overs} AND m.method IS NULL AND (inn.wkts >= 10 OR inn.legal >= {overs * 6})"}
    """


def _score_dist(con, overs: int) -> dict:
    r = con.execute(f"""
        SELECT count(*), avg(total), stddev_samp(total),
               quantile_cont(total, 0.1), quantile_cont(total, 0.5), quantile_cont(total, 0.9),
               avg(wkts)
        FROM ({_full_first_innings(con, overs)})
    """).fetchone()
    keys = ["innings", "mean", "sd", "p10", "p50", "p90", "mean_wickets"]
    return {k: (round(v, 2) if isinstance(v, float) else v) for k, v in zip(keys, r)}


def _test_shape(con) -> dict:
    """How real Tests unfold, for validating the Test engine: per-innings averages
    (runs, overs, wickets, share not all out) and the draw rate."""
    rows = con.execute(f"""
        WITH i AS (
            SELECT match_id, innings, sum(runs_total) AS r, count(*) FILTER (WHERE is_legal) AS b,
                   count(*) FILTER (WHERE is_wicket AND wicket_kind NOT IN {RETIRED}) AS w
            FROM e GROUP BY ALL
        )
        SELECT innings, count(*), avg(r), avg(b) / 6.0, avg(w), avg((w < 10)::INT),
               6.0 * sum(r) / sum(b), sum(w) / sum(b)
        FROM i WHERE innings <= 4 GROUP BY 1 ORDER BY 1
    """).fetchall()
    draws = con.execute("""
        SELECT avg((result = 'draw')::INT) FROM m
        WHERE match_id IN (SELECT DISTINCT match_id FROM e) AND result IS NOT NULL
    """).fetchone()[0]
    # run_rate / wicket_rate per innings drive the engine's pitch-wear factors.
    keys = ["innings", "n", "runs", "overs", "wickets", "not_all_out", "run_rate", "wicket_rate"]
    return {"innings": [{k: (round(v, 5) if isinstance(v, float) else v) for k, v in zip(keys, r)} for r in rows],
            "draw_rate": round(draws, 3)}


def _resources(con, overs: int) -> dict:
    """mean/sd of runs still to come in a full first innings, by (legal balls
    bowled, wickets down) at the start of a delivery."""
    rows = con.execute(f"""
        WITH full_inn AS ({_full_first_innings(con, overs)}),
        x AS (
            SELECT e.match_id, e.is_legal, e.runs_total,
                   sum(CASE WHEN e.is_legal THEN 1 ELSE 0 END) OVER w_before AS balls_before,
                   coalesce(sum(CASE WHEN e.is_wicket AND e.wicket_kind NOT IN {RETIRED}
                                     THEN e.wicket_count ELSE 0 END) OVER w_before, 0) AS wkts_before,
                   sum(e.runs_total) OVER w_after AS runs_after
            FROM e JOIN full_inn USING (match_id)
            WHERE e.innings = 1
            WINDOW w_before AS (PARTITION BY e.match_id ORDER BY e.over, e.ball_in_over
                                ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING),
                   w_after AS (PARTITION BY e.match_id ORDER BY e.over, e.ball_in_over
                               ROWS BETWEEN CURRENT ROW AND UNBOUNDED FOLLOWING)
        )
        SELECT coalesce(balls_before, 0) AS b, least(wkts_before, 9) AS w,
               count(*), avg(runs_after), stddev_samp(runs_after)
        FROM x WHERE is_legal GROUP BY ALL
    """).fetchall()
    n_balls = overs * 6
    mean = [[None] * 10 for _ in range(n_balls)]
    sd = [[None] * 10 for _ in range(n_balls)]
    for b, w, n, mu, s in rows:
        if b < n_balls and n >= MIN_CELL:
            mean[b][w], sd[b][w] = mu, s
    # Fill sparse cells: more wickets down -> fewer runs to come. Walk wickets up,
    # then down, copying the neighbour scaled by 0.85 / 1/0.85.
    for b in range(n_balls):
        for w in range(1, 10):
            if mean[b][w] is None and mean[b][w - 1] is not None:
                mean[b][w], sd[b][w] = mean[b][w - 1] * 0.85, sd[b][w - 1] * 0.9
        for w in range(8, -1, -1):
            if mean[b][w] is None and mean[b][w + 1] is not None:
                mean[b][w], sd[b][w] = mean[b][w + 1] / 0.85, sd[b][w + 1] / 0.9
    # Any still-empty ball index (only if a whole row lacked data): copy previous ball.
    for b in range(n_balls):
        for w in range(10):
            if mean[b][w] is None:
                mean[b][w], sd[b][w] = mean[b - 1][w], sd[b - 1][w]
    r = lambda grid: [[round(v, 2) for v in row] for row in grid]  # noqa: E731
    return {"overs": overs, "mean": r(mean), "sd": r(sd)}


# Shrinkage priors: observed / context-expected outcome ratios for groups of
# players with little data. "Unproven" = career sample below these thresholds.
PRIOR_BAT_BALLS = 150
PRIOR_BOWL_BALLS = 300
CATS = ["wickets", "dots", "ones", "twos", "threes", "fours", "sixes"]


def _priors(con, fmt: str) -> dict[str, list[float]]:
    """Ratio vectors (in sim OUTCOMES order: W, 0, 1, 2, 3, 4, 6) for each prior group.
    Dots exclude wicket balls, matching the simulator's outcome definition."""
    groups = {
        "tail_bat": ("bat", "p.role = 'BOWL'", f"< {PRIOR_BAT_BALLS}"),
        "unproven_bat": ("bat", "p.role <> 'BOWL'", f"< {PRIOR_BAT_BALLS}"),
        "part_timer_bowl": ("bowl", "p.role IN ('BAT', 'WK')", f"< {PRIOR_BOWL_BALLS}"),
        "unproven_bowl": ("bowl", "p.role IN ('BOWL', 'AR')", f"< {PRIOR_BOWL_BALLS}"),
    }
    out = {}
    for name, (role, role_sql, balls_sql) in groups.items():
        sums = ", ".join(f"sum({c}), sum(exp_{c})" for c in CATS)
        r = con.execute(f"""
            SELECT {sums} FROM player_phase_stats s JOIN players p ON p.id = s.player_id
            WHERE s.format = '{fmt}' AND s.role = '{role}' AND {role_sql}
              AND s.player_id IN (SELECT player_id FROM player_phase_stats
                                  WHERE format = '{fmt}' AND role = '{role}'
                                  GROUP BY 1 HAVING sum(balls) {balls_sql})
        """).fetchone()
        obs = dict(zip(CATS, r[0::2]))
        exp = dict(zip(CATS, r[1::2]))
        vec_obs = [obs["wickets"], obs["dots"] - obs["wickets"]] + [obs[c] for c in CATS[2:]]
        vec_exp = [exp["wickets"], exp["dots"] - exp["wickets"]] + [exp[c] for c in CATS[2:]]
        out[name] = [round(o / e, 3) for o, e in zip(vec_obs, vec_exp)]
    return out


def build_simbase(parquet_dir: Path, db_path: Path, out: Path = OUT_PATH) -> dict:
    pq = parquet_dir.as_posix()
    result: dict = {"envs": {}, "resources": {}, "phases": {
        "20": [[0, "PP"], [6, "middle"], [15, "death"]],
        "50": [[0, "PP"], [10, "middle"], [40, "death"]],
        "0": [[0, "PP"], [15, "middle"], [80, "death"]],   # Tests: new / middle / old ball
    }}
    with duckdb.connect(str(db_path), read_only=True) as con:
        con.execute(f"""
            CREATE TEMP VIEW d AS SELECT * FROM read_parquet('{pq}/deliveries.parquet')
                                  WHERE NOT is_super_over;
            CREATE TEMP VIEW m AS SELECT * FROM read_parquet('{pq}/matches.parquet');
        """)
        for name, (fmt, y0, y1, overs) in ENVS.items():
            _env_view(con, fmt, y0, y1)
            family = {"Test": "Test", "ODI": "ODI"}.get(fmt, "T20")
            result["envs"][name] = {
                "format": fmt, "family": family, "years": [y0, y1] if y0 else None, "overs": overs,
                "phases": _phase_counts(con),
                "extras": _extras(con),
                "first_innings": _score_dist(con, overs),
                **({"test_shape": _test_shape(con)} if overs == 0 else {}),
            }
        for overs, env in RESOURCE_BASE.items():
            fmt, y0, y1, _ = ENVS[env]
            _env_view(con, fmt, y0, y1)
            result["resources"][str(overs)] = {"env": env, **_resources(con, overs)}
        result["priors"] = {fmt: _priors(con, fmt) for fmt in ("T20", "ODI", "Test")}
        result["prior_thresholds"] = {"bat_balls": PRIOR_BAT_BALLS, "bowl_balls": PRIOR_BOWL_BALLS}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, separators=(",", ":")))
    return result
