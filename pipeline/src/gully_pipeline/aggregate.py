"""Build player tables in DuckDB from the parsed Parquet files.

Tables produced (all keyed by Cricsheet register id, ``player_id``):

* ``players``             - identity, country, heuristic role, career span
* ``player_format_stats`` - career batting/bowling/fielding per format
* ``player_season_stats`` - same metrics per format and season
* ``player_phase_stats``  - per-ball outcome counts and rates by phase
                            (PP / middle / death), for the simulator

Formats are overlapping views of the same deliveries:

* Test, ODI, T20I - men's internationals (unofficial "IT20" games excluded)
* IPL             - Indian Premier League
* T20             - every men's T20 in the data (internationals + leagues)

Super-over deliveries are excluded everywhere.
"""

from __future__ import annotations

from pathlib import Path

import duckdb

FORMATS_SQL = """
CREATE OR REPLACE TABLE match_formats AS
    SELECT match_id, season, 'Test' AS format FROM m WHERE match_type = 'Test'
    UNION ALL SELECT match_id, season, 'ODI'  FROM m WHERE match_type = 'ODI'
    UNION ALL SELECT match_id, season, 'T20I' FROM m
        WHERE match_type = 'T20' AND team_type = 'international'
    UNION ALL SELECT match_id, season, 'IPL'  FROM m WHERE event_name = 'Indian Premier League'
    UNION ALL SELECT match_id, season, 'T20'  FROM m WHERE match_type IN ('T20', 'IT20');

CREATE OR REPLACE TEMP VIEW fd AS
    SELECT f.format, d.* FROM d JOIN match_formats f USING (match_id);

CREATE OR REPLACE TEMP TABLE squad AS
    SELECT DISTINCT f.format, f.season, mp.match_id, mp.player_id AS pid
    FROM mp JOIN match_formats f USING (match_id)
    WHERE mp.player_id IS NOT NULL;
"""

# Dismissals that do not end an innings for averages.
NOT_OUT_KINDS = "('retired hurt', 'retired not out')"

INNINGS_SQL = f"""
-- One row per player per batting innings.
CREATE OR REPLACE TEMP TABLE bat_inn AS
WITH appear AS (
    SELECT format, season, match_id, innings, batter_id AS pid FROM fd
    UNION
    SELECT format, season, match_id, innings, non_striker_id FROM fd
),
faced AS (
    SELECT format, match_id, innings, batter_id AS pid,
           sum(runs_batter) AS runs,
           count(*) FILTER (WHERE wides = 0) AS balls,
           count(*) FILTER (WHERE is_four) AS fours,
           count(*) FILTER (WHERE is_six) AS sixes
    FROM fd GROUP BY ALL
),
outs AS (
    SELECT format, match_id, innings, player_out_id AS pid, count(*) AS n
    FROM fd WHERE is_wicket AND wicket_kind NOT IN {NOT_OUT_KINDS}
    GROUP BY ALL
)
SELECT a.format, a.season, a.match_id, a.innings, a.pid,
       coalesce(f.runs, 0) AS runs, coalesce(f.balls, 0) AS balls,
       coalesce(f.fours, 0) AS fours, coalesce(f.sixes, 0) AS sixes,
       coalesce(o.n, 0) > 0 AS is_out
FROM appear a
LEFT JOIN faced f USING (format, match_id, innings, pid)
LEFT JOIN outs o USING (format, match_id, innings, pid)
WHERE a.pid IS NOT NULL;

-- One row per bowler per innings. Byes and leg-byes are not charged to the bowler.
CREATE OR REPLACE TEMP TABLE bowl_inn AS
SELECT format, season, match_id, innings, bowler_id AS pid,
       count(*) FILTER (WHERE is_legal) AS balls,
       sum(runs_batter + wides + noballs) AS runs,
       count(*) FILTER (WHERE bowler_credited) AS wkts,
       count(*) FILTER (WHERE is_legal AND runs_batter + wides + noballs = 0) AS dots
FROM fd WHERE bowler_id IS NOT NULL
GROUP BY ALL;

-- Catches (incl. caught & bowled) and stumpings, substitutes excluded.
CREATE OR REPLACE TEMP TABLE field_inn AS
SELECT format, season, match_id, pid,
       count(*) FILTER (WHERE kind IN ('caught', 'caught and bowled')) AS catches,
       count(*) FILTER (WHERE kind = 'stumped') AS stumpings
FROM (
    SELECT format, season, match_id, wicket_kind AS kind,
           CASE WHEN wicket_kind = 'caught and bowled' THEN bowler_id ELSE fielder_id END AS pid
    FROM fd
    WHERE is_wicket AND NOT coalesce(fielder_is_sub, false)
)
WHERE pid IS NOT NULL
GROUP BY ALL;
"""


def stats_sql(table: str, keys: list[str]) -> str:
    """Career-style stats grouped by player + ``keys`` (e.g. format, season)."""
    k = ", ".join(keys)
    return f"""
CREATE OR REPLACE TABLE {table} AS
WITH s AS (
    SELECT pid, {k}, count(DISTINCT match_id) AS matches FROM squad GROUP BY ALL
),
b AS (
    SELECT pid, {k},
           count(*) AS innings,
           sum(runs) AS runs,
           sum(balls) AS balls_faced,
           count(*) FILTER (WHERE NOT is_out) AS not_outs,
           count(*) FILTER (WHERE is_out) AS dismissals,
           max(runs) AS highest,
           count(*) FILTER (WHERE runs >= 50 AND runs < 100) AS fifties,
           count(*) FILTER (WHERE runs >= 100) AS hundreds,
           sum(fours) AS fours,
           sum(sixes) AS sixes
    FROM bat_inn GROUP BY ALL
),
w AS (
    SELECT pid, {k},
           count(*) FILTER (WHERE balls > 0) AS bowl_innings,
           sum(balls) AS balls_bowled,
           sum(runs) AS runs_conceded,
           sum(wkts) AS wickets,
           sum(dots) AS dot_balls,
           count(*) FILTER (WHERE wkts >= 5) AS five_wkts,
           arg_max(wkts || '/' || runs, wkts * 10000 - runs) AS best_bowling
    FROM bowl_inn GROUP BY ALL
),
fl AS (
    SELECT pid, {k}, sum(catches) AS catches, sum(stumpings) AS stumpings
    FROM field_inn GROUP BY ALL
)
SELECT pid AS player_id, {k},
       matches::INTEGER AS matches,
       coalesce(innings, 0)::INTEGER AS bat_innings,
       coalesce(runs, 0)::INTEGER AS runs,
       coalesce(balls_faced, 0)::INTEGER AS balls_faced,
       coalesce(not_outs, 0)::INTEGER AS not_outs,
       highest::INTEGER AS highest,
       coalesce(fifties, 0)::INTEGER AS fifties,
       coalesce(hundreds, 0)::INTEGER AS hundreds,
       coalesce(fours, 0)::INTEGER AS fours,
       coalesce(sixes, 0)::INTEGER AS sixes,
       round(runs / nullif(dismissals, 0), 2) AS bat_avg,
       round(100.0 * runs / nullif(balls_faced, 0), 2) AS bat_sr,
       coalesce(bowl_innings, 0)::INTEGER AS bowl_innings,
       coalesce(balls_bowled, 0)::INTEGER AS balls_bowled,
       coalesce(runs_conceded, 0)::INTEGER AS runs_conceded,
       coalesce(wickets, 0)::INTEGER AS wickets,
       CASE WHEN balls_bowled > 0 THEN best_bowling END AS best_bowling,
       coalesce(five_wkts, 0)::INTEGER AS five_wkts,
       round(6.0 * runs_conceded / nullif(balls_bowled, 0), 2) AS bowl_econ,
       round(runs_conceded / nullif(wickets, 0), 2) AS bowl_avg,
       round(balls_bowled / nullif(wickets, 0), 2) AS bowl_sr,
       round(100.0 * dot_balls / nullif(balls_bowled, 0), 2) AS bowl_dot_pct,
       coalesce(catches, 0)::INTEGER AS catches,
       coalesce(stumpings, 0)::INTEGER AS stumpings
FROM s
LEFT JOIN b USING (pid, {k})
LEFT JOIN w USING (pid, {k})
LEFT JOIN fl USING (pid, {k})
ORDER BY player_id, {k};
"""


CONTEXT_SQL = f"""
-- Context baselines: league-average rates per (format, competition, year, phase).
-- A player's expected counts = their balls in each context x that context's rate,
-- so ratings compare a player with the cricket they actually played in
-- (an IPL batter against IPL scoring, not against all T20 everywhere).
CREATE OR REPLACE TEMP VIEW fdc AS
SELECT *, CASE WHEN team_type = 'international' THEN 'intl'
               ELSE coalesce(event_name, 'other') END AS ctx,
       year(start_date) AS yr
FROM fd WHERE phase IS NOT NULL;

CREATE OR REPLACE TEMP TABLE ctx_bat AS
SELECT format, ctx, yr, phase,
       count(*) FILTER (WHERE wides = 0) AS balls,
       count(*) FILTER (WHERE wides = 0 AND is_wicket AND wicket_kind NOT IN {NOT_OUT_KINDS}) AS wickets,
       count(*) FILTER (WHERE wides = 0 AND runs_batter = 0) AS dots,
       count(*) FILTER (WHERE wides = 0 AND runs_batter = 1) AS ones,
       count(*) FILTER (WHERE wides = 0 AND runs_batter = 2) AS twos,
       count(*) FILTER (WHERE wides = 0 AND runs_batter = 3) AS threes,
       count(*) FILTER (WHERE is_four) AS fours,
       count(*) FILTER (WHERE is_six) AS sixes
FROM fdc GROUP BY ALL;

CREATE OR REPLACE TEMP TABLE ctx_bowl AS
SELECT format, ctx, yr, phase,
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
FROM fdc GROUP BY ALL;

CREATE OR REPLACE TEMP TABLE phase_exp AS
WITH pb AS (
    SELECT batter_id AS pid, format, ctx, yr, phase,
           count(*) FILTER (WHERE wides = 0) AS n
    FROM fdc WHERE batter_id IS NOT NULL GROUP BY ALL
),
pw AS (
    SELECT bowler_id AS pid, format, ctx, yr, phase,
           count(*) FILTER (WHERE is_legal) AS n
    FROM fdc WHERE bowler_id IS NOT NULL GROUP BY ALL
)
SELECT 'bat' AS role, pid, format, phase,
       sum(n * c.wickets / c.balls) AS exp_wickets, sum(n * c.dots / c.balls) AS exp_dots,
       sum(n * c.ones / c.balls) AS exp_ones, sum(n * c.twos / c.balls) AS exp_twos,
       sum(n * c.threes / c.balls) AS exp_threes, sum(n * c.fours / c.balls) AS exp_fours,
       sum(n * c.sixes / c.balls) AS exp_sixes,
       NULL::DOUBLE AS exp_wide_balls, NULL::DOUBLE AS exp_noball_balls
FROM pb JOIN ctx_bat c USING (format, ctx, yr, phase) WHERE c.balls > 0 GROUP BY ALL
UNION ALL
SELECT 'bowl', pid, format, phase,
       sum(n * c.wickets / c.balls), sum(n * c.dots / c.balls),
       sum(n * c.ones / c.balls), sum(n * c.twos / c.balls),
       sum(n * c.threes / c.balls), sum(n * c.fours / c.balls),
       sum(n * c.sixes / c.balls),
       sum(n * c.wide_balls / c.balls), sum(n * c.noball_balls / c.balls)
FROM pw JOIN ctx_bowl c USING (format, ctx, yr, phase) WHERE c.balls > 0 GROUP BY ALL;
"""

EXP_COLS = ["exp_wickets", "exp_dots", "exp_ones", "exp_twos", "exp_threes", "exp_fours",
            "exp_sixes", "exp_wide_balls", "exp_noball_balls"]

PHASE_SQL = f"""
-- Outcome counts per ball by phase. Raw counts are kept alongside rates so the
-- simulator can apply shrinkage toward league base rates.
-- Batting: denominator = balls faced (wides excluded, no-balls included).
-- Bowling: denominator = legal balls; wides/no-balls given as rates per legal ball.
CREATE OR REPLACE TABLE player_phase_stats AS
WITH bat AS (
    SELECT batter_id AS pid, format, phase,
           count(*) FILTER (WHERE wides = 0) AS balls,
           sum(runs_batter) AS runs,
           count(*) FILTER (WHERE wides = 0 AND runs_batter = 0) AS dots,
           count(*) FILTER (WHERE wides = 0 AND runs_batter = 1) AS ones,
           count(*) FILTER (WHERE wides = 0 AND runs_batter = 2) AS twos,
           count(*) FILTER (WHERE wides = 0 AND runs_batter = 3) AS threes,
           count(*) FILTER (WHERE is_four) AS fours,
           count(*) FILTER (WHERE is_six) AS sixes
    FROM fd WHERE phase IS NOT NULL AND batter_id IS NOT NULL
    GROUP BY ALL
),
bat_out AS (
    SELECT player_out_id AS pid, format, phase, count(*) AS wickets
    FROM fd
    WHERE phase IS NOT NULL AND is_wicket AND wicket_kind NOT IN {NOT_OUT_KINDS}
    GROUP BY ALL
),
bowl AS (
    SELECT bowler_id AS pid, format, phase,
           count(*) FILTER (WHERE is_legal) AS balls,
           sum(runs_batter + wides + noballs) AS runs,
           count(*) FILTER (WHERE is_legal AND runs_batter + wides + noballs = 0) AS dots,
           count(*) FILTER (WHERE is_legal AND runs_batter = 1) AS ones,
           count(*) FILTER (WHERE is_legal AND runs_batter = 2) AS twos,
           count(*) FILTER (WHERE is_legal AND runs_batter = 3) AS threes,
           count(*) FILTER (WHERE is_legal AND is_four) AS fours,
           count(*) FILTER (WHERE is_legal AND is_six) AS sixes,
           count(*) FILTER (WHERE bowler_credited) AS wickets,
           count(*) FILTER (WHERE wides > 0) AS wide_balls,
           count(*) FILTER (WHERE noballs > 0) AS noball_balls
    FROM fd WHERE phase IS NOT NULL AND bowler_id IS NOT NULL
    GROUP BY ALL
),
u AS (
    SELECT 'bat' AS role, pid, format, phase, balls, runs, dots, ones, twos, threes,
           fours, sixes, coalesce(o.wickets, 0) AS wickets,
           NULL::BIGINT AS wide_balls, NULL::BIGINT AS noball_balls
    FROM bat LEFT JOIN bat_out o USING (pid, format, phase)
    UNION ALL
    SELECT 'bowl', pid, format, phase, balls, runs, dots, ones, twos, threes,
           fours, sixes, wickets, wide_balls, noball_balls
    FROM bowl
)
SELECT pid AS player_id, format, phase, role,
       balls::INTEGER AS balls, runs::INTEGER AS runs, wickets::INTEGER AS wickets,
       dots::INTEGER AS dots, ones::INTEGER AS ones, twos::INTEGER AS twos,
       threes::INTEGER AS threes, fours::INTEGER AS fours, sixes::INTEGER AS sixes,
       wide_balls::INTEGER AS wide_balls, noball_balls::INTEGER AS noball_balls,
       round(wickets / nullif(balls, 0), 5) AS dismissal_rate,
       round(dots / nullif(balls, 0), 5) AS dot_pct,
       round(ones / nullif(balls, 0), 5) AS single_pct,
       round(twos / nullif(balls, 0), 5) AS two_pct,
       round(threes / nullif(balls, 0), 5) AS three_pct,
       round(fours / nullif(balls, 0), 5) AS four_pct,
       round(sixes / nullif(balls, 0), 5) AS six_pct,
       round(wide_balls / nullif(balls, 0), 5) AS wide_rate,
       round(noball_balls / nullif(balls, 0), 5) AS noball_rate,
       round(100.0 * runs / nullif(balls, 0), 2) AS strike_rate,
       round(6.0 * runs / nullif(balls, 0), 2) AS economy,
       {", ".join(f"round(x.{c}, 3) AS {c}" for c in EXP_COLS)}
FROM u
LEFT JOIN phase_exp x USING (role, pid, format, phase)
WHERE balls > 0
ORDER BY player_id, format, phase, role;
"""

# Role thresholds (heuristic, tune against known players):
# share of team balls bowled / faced across every match the player appears in.
BOWL_SHARE_MIN = 0.08
BAT_SHARE_AR_MIN = 0.07

PLAYERS_SQL = f"""
CREATE OR REPLACE TABLE players AS
WITH team_faced AS (
    SELECT match_id, batting_team AS team, count(*) FILTER (WHERE wides = 0) AS n
    FROM d GROUP BY ALL
),
team_bowled AS (
    SELECT match_id, bowling_team AS team, count(*) FILTER (WHERE is_legal) AS n
    FROM d GROUP BY ALL
),
p_faced AS (
    SELECT match_id, batter_id AS pid, count(*) FILTER (WHERE wides = 0) AS n
    FROM d GROUP BY ALL
),
p_bowled AS (
    SELECT match_id, bowler_id AS pid, count(*) FILTER (WHERE is_legal) AS n
    FROM d GROUP BY ALL
),
share AS (
    SELECT mp.player_id AS pid,
           count(DISTINCT mp.match_id) AS matches,
           sum(coalesce(pf.n, 0)) / nullif(sum(coalesce(tf.n, 0)), 0) AS bat_share,
           sum(coalesce(pb.n, 0)) / nullif(sum(coalesce(tb.n, 0)), 0) AS bowl_share,
           min(year(m.start_date)) AS era_start,
           max(year(m.start_date)) AS era_end
    FROM mp
    JOIN m USING (match_id)
    LEFT JOIN team_faced tf ON tf.match_id = mp.match_id AND tf.team = mp.team
    LEFT JOIN team_bowled tb ON tb.match_id = mp.match_id AND tb.team = mp.team
    LEFT JOIN p_faced pf ON pf.match_id = mp.match_id AND pf.pid = mp.player_id
    LEFT JOIN p_bowled pb ON pb.match_id = mp.match_id AND pb.pid = mp.player_id
    WHERE mp.player_id IS NOT NULL
    GROUP BY 1
),
stumps AS (
    SELECT fielder_id AS pid, count(*) AS n FROM d
    WHERE wicket_kind = 'stumped' AND NOT coalesce(fielder_is_sub, false)
    GROUP BY 1
),
intl AS (
    SELECT mp.player_id AS pid, mode(mp.team) AS country, count(*) AS intl_matches
    FROM mp JOIN match_formats f USING (match_id)
    WHERE f.format IN ('Test', 'ODI', 'T20I') AND mp.player_id IS NOT NULL
      AND mp.team NOT LIKE '% XI'   -- composite sides (ICC World XI, Asia XI, ...)
    GROUP BY 1
),
capped AS (
    SELECT DISTINCT mp.player_id AS pid
    FROM mp JOIN match_formats f USING (match_id)
    WHERE f.format IN ('Test', 'ODI', 'T20I')
)
SELECT s.pid AS id,
       s.pid AS cricsheet_id,
       p.name,
       p.unique_name,
       p.key_cricinfo AS cricinfo_id,
       i.country,
       CASE
           WHEN coalesce(st.n, 0) >= 2 OR (st.n = 1 AND s.matches < 15) THEN 'WK'
           WHEN s.bowl_share >= {BOWL_SHARE_MIN} AND s.bat_share >= {BAT_SHARE_AR_MIN} THEN 'AR'
           WHEN s.bowl_share >= {BOWL_SHARE_MIN} THEN 'BOWL'
           ELSE 'BAT'
       END AS role,
       NULL::VARCHAR AS batting_hand,
       NULL::VARCHAR AS bowling_style,
       CASE WHEN i.country IS NULL THEN NULL ELSE i.country <> 'India' END AS is_overseas_for_ipl,
       c.pid IS NOT NULL AS capped,
       s.era_start::INTEGER AS era_start,
       s.era_end::INTEGER AS era_end,
       s.matches::INTEGER AS matches,
       round(s.bat_share, 4) AS bat_share,
       round(s.bowl_share, 4) AS bowl_share,
       'cricsheet' AS source
FROM share s
LEFT JOIN people p ON p.identifier = s.pid
LEFT JOIN stumps st ON st.pid = s.pid
LEFT JOIN intl i ON i.pid = s.pid
LEFT JOIN capped c ON c.pid = s.pid
ORDER BY s.pid;
"""


def build(parquet_dir: Path, people_csv: Path, db_path: Path) -> dict[str, int]:
    """Build all player tables into ``db_path``. Returns row counts per table."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    pq = parquet_dir.as_posix()
    with duckdb.connect(str(db_path)) as con:
        con.execute(f"""
            CREATE OR REPLACE TEMP VIEW d AS
                SELECT * FROM read_parquet('{pq}/deliveries.parquet') WHERE NOT is_super_over;
            CREATE OR REPLACE TEMP VIEW m AS SELECT * FROM read_parquet('{pq}/matches.parquet');
            CREATE OR REPLACE TEMP VIEW mp AS SELECT * FROM read_parquet('{pq}/match_players.parquet');
            CREATE OR REPLACE TEMP TABLE people AS
                SELECT * FROM read_csv('{people_csv.as_posix()}', header = true, all_varchar = true);
        """)
        con.execute(FORMATS_SQL)
        con.execute(INNINGS_SQL)
        con.execute(stats_sql("player_format_stats", ["format"]))
        con.execute(stats_sql("player_season_stats", ["format", "season"]))
        con.execute(CONTEXT_SQL)
        con.execute(PHASE_SQL)
        con.execute(PLAYERS_SQL)
        tables = ["players", "player_format_stats", "player_season_stats", "player_phase_stats"]
        return {t: con.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in tables}
