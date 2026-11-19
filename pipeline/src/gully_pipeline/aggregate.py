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

# Tests have no powerplay or death overs, so Cricsheet phases are null. Reuse the same
# three labels for the age of the ball: new ball (overs 0-14 of an innings), middle
# (15-79) and old ball (80+, around the second new ball). Real Tests since 2001: runs
# per over 3.2 / 3.3 / 3.5, balls per wicket 58 / 63 / 52 across those spans.
TEST_PHASE = ("CASE WHEN {table}.phase IS NULL AND {table}.match_type = 'Test' THEN "
              "CASE WHEN {table}.over < 15 THEN 'PP' WHEN {table}.over < 80 THEN 'middle' "
              "ELSE 'death' END ELSE {table}.phase END")

FORMATS_SQL = f"""
CREATE OR REPLACE TABLE match_formats AS
    SELECT match_id, season, 'Test' AS format FROM m WHERE match_type = 'Test'
    UNION ALL SELECT match_id, season, 'ODI'  FROM m WHERE match_type = 'ODI'
    UNION ALL SELECT match_id, season, 'T20I' FROM m
        WHERE match_type = 'T20' AND team_type = 'international'
    UNION ALL SELECT match_id, season, 'IPL'  FROM m WHERE event_name = 'Indian Premier League'
    UNION ALL SELECT match_id, season, 'T20'  FROM m WHERE match_type IN ('T20', 'IT20');

CREATE OR REPLACE TEMP VIEW fd AS
    SELECT f.format, d.* EXCLUDE (phase), {TEST_PHASE.format(table='d')} AS phase
    FROM d JOIN match_formats f USING (match_id);

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


FULL_MEMBERS = ("('India', 'Australia', 'England', 'South Africa', 'New Zealand', 'Pakistan', "
                "'Sri Lanka', 'West Indies', 'Bangladesh', 'Zimbabwe', 'Afghanistan', 'Ireland')")

CONTEXT_SQL = f"""
-- Context baselines: league-average rates per (format, competition, year, phase).
-- A player's expected counts = their balls in each context x that context's rate,
-- so ratings compare a player with the cricket they actually played in
-- (an IPL batter against IPL scoring, not against all T20 everywhere).
-- Internationals are split by tier: India v Australia and Nepal v Oman are not the
-- same competition. ICC Full Members (all 12 treated as full for every year).
CREATE OR REPLACE TEMP VIEW fdc AS
SELECT *,
       CASE WHEN team_type = 'international' THEN
                CASE WHEN batting_team IN {FULL_MEMBERS} AND bowling_team IN {FULL_MEMBERS} THEN 'intl-full'
                     WHEN batting_team IN {FULL_MEMBERS} OR bowling_team IN {FULL_MEMBERS} THEN 'intl-mixed'
                     ELSE 'intl-assoc' END
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
"""

# --------------------------------------------------------------- recent form
# Recency-weighted phase stats for the simulator. Each year of data before
# ``as_of`` is weighted 0.5 ** ((as_of - 1 - year) / half_life), so the last
# completed year counts fully; half_life 0 means no decay (career).
# Several (as_of, half_life) combinations are built so validation can rate
# players "as of" each season using only earlier data (no look-ahead).
FORM_HALF_LIVES = (0, 1, 2, 4)
DEFAULT_HALF_LIFE = 4
FORM_FIRST_AS_OF = 2024

FORM_BASE_SQL = f"""
CREATE OR REPLACE TEMP TABLE pc_bat AS
WITH faced AS (
    SELECT batter_id AS pid, format, ctx, yr, phase,
           count(*) FILTER (WHERE wides = 0) AS balls,
           count(*) FILTER (WHERE wides = 0 AND runs_batter = 0) AS dots,
           count(*) FILTER (WHERE wides = 0 AND runs_batter = 1) AS ones,
           count(*) FILTER (WHERE wides = 0 AND runs_batter = 2) AS twos,
           count(*) FILTER (WHERE wides = 0 AND runs_batter = 3) AS threes,
           count(*) FILTER (WHERE is_four) AS fours,
           count(*) FILTER (WHERE is_six) AS sixes
    FROM fdc WHERE batter_id IS NOT NULL GROUP BY ALL
),
outs AS (
    SELECT player_out_id AS pid, format, ctx, yr, phase, count(*) AS wickets
    FROM fdc WHERE is_wicket AND wicket_kind NOT IN {NOT_OUT_KINDS} GROUP BY ALL
)
SELECT f.*, coalesce(o.wickets, 0) AS wickets
FROM faced f LEFT JOIN outs o USING (pid, format, ctx, yr, phase);

CREATE OR REPLACE TEMP TABLE pc_bowl AS
SELECT bowler_id AS pid, format, ctx, yr, phase,
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
FROM fdc WHERE bowler_id IS NOT NULL GROUP BY ALL;
"""

_FORM_CATS = ["wickets", "dots", "ones", "twos", "threes", "fours", "sixes"]

# --------------------------------------------------------- league strength
# Context baselines make a rating "vs the average of the league you played in",
# which is not comparable across leagues: beating the BPL or associate average is
# easier than beating the IPL's. Model each player's outcomes in competition c as
#     observed ≈ rating[player] × strength[c] × context_expected
# per role and outcome, and fit both by alternating updates. Players who appear in
# several competitions link them. Strength is anchored at 1 for the reference
# competition, so league-adjusted ratings read as "vs the IPL average" (T20) or
# "vs full-member internationals" (ODI). Strength is per competition, not per
# year (more stable; ageing would otherwise leak into year factors).
LEAGUE_REF = {"T20": "Indian Premier League", "ODI": "intl-full", "Test": "intl-full"}
LEAGUE_ITERATIONS = 60
K_LEAGUE_PLAYER = 300    # balls of prior pulling a player's rating toward 1 in the fit
K_LEAGUE_CTX = 2000      # balls of prior pulling a competition's factor toward 1


def _fam(col: str) -> str:
    return f"CASE {col} WHEN 'ODI' THEN 'ODI' WHEN 'Test' THEN 'Test' ELSE 'T20' END"


def league_strength(con) -> dict:
    """Fit competition strength factors; leaves temp table ``ls_wide`` for joins and
    writes ``league_strength`` (one row per role, family, competition, outcome)."""
    cats = "[" + ", ".join(f"'{c}'" for c in _FORM_CATS) + "]"
    parts = []
    for role, pc, ctx in (("bat", "pc_bat", "ctx_bat"), ("bowl", "pc_bowl", "ctx_bowl")):
        obs = "[" + ", ".join(f"p.{c}::DOUBLE" for c in _FORM_CATS) + "]"
        exp = "[" + ", ".join(f"p.balls * c.{c} / c.balls" for c in _FORM_CATS) + "]"
        parts.append(f"""
            SELECT '{role}' AS role, {_fam('p.format')} AS fam, p.pid, p.ctx,
                   unnest({cats}) AS cat, unnest({obs}) AS o, unnest({exp}) AS x, p.balls
            FROM {pc} p JOIN {ctx} c USING (format, ctx, yr, phase)
            WHERE p.format IN ('T20', 'ODI', 'Test') AND c.balls > 0""")
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE ls_obs AS
        SELECT role, fam, pid, ctx, cat, sum(o) AS o, sum(x) AS x, sum(balls) AS balls
        FROM ({' UNION ALL '.join(parts)}) GROUP BY ALL;
        CREATE OR REPLACE TEMP TABLE ls_rate AS
        SELECT role, fam, cat, sum(x) / sum(balls) AS rate FROM ls_obs GROUP BY ALL;
        CREATE OR REPLACE TEMP TABLE ls_s AS
        SELECT DISTINCT role, fam, ctx, cat, 1.0::DOUBLE AS s FROM ls_obs;
    """)
    # Ratings must start from the data (observed / expected with every league at 1):
    # starting them all at 1 makes the first strength update return 1 everywhere,
    # which looks converged on step one.
    r_update = f"""
        CREATE OR REPLACE TEMP TABLE ls_r AS
        SELECT o.role, o.fam, o.pid, o.cat,
               coalesce((sum(o.o) + {K_LEAGUE_PLAYER} * q.rate)
                        / nullif(sum(s.s * o.x) + {K_LEAGUE_PLAYER} * q.rate, 0), 1) AS r
        FROM ls_obs o JOIN ls_s s USING (role, fam, ctx, cat) JOIN ls_rate q USING (role, fam, cat)
        GROUP BY o.role, o.fam, o.pid, o.cat, q.rate;
    """
    con.execute(r_update)
    ref = f"CASE s.fam WHEN 'T20' THEN '{LEAGUE_REF['T20']}' ELSE '{LEAGUE_REF['ODI']}' END"
    change = float("inf")
    it = 0
    for it in range(1, LEAGUE_ITERATIONS + 1):
        con.execute(f"""
            CREATE OR REPLACE TEMP TABLE ls_s_raw AS
            SELECT o.role, o.fam, o.ctx, o.cat,
                   coalesce((sum(o.o) + {K_LEAGUE_CTX} * q.rate)
                            / nullif(sum(r.r * o.x) + {K_LEAGUE_CTX} * q.rate, 0), 1) AS s,
                   sum(o.balls) AS balls, count(DISTINCT o.pid) AS players
            FROM ls_obs o JOIN ls_r r USING (role, fam, pid, cat) JOIN ls_rate q USING (role, fam, cat)
            GROUP BY o.role, o.fam, o.ctx, o.cat, q.rate;
            CREATE OR REPLACE TEMP TABLE ls_s_new AS
            SELECT s.role, s.fam, s.ctx, s.cat, s.s / coalesce(rf.s, 1) AS s, s.balls, s.players
            FROM ls_s_raw s LEFT JOIN ls_s_raw rf
              ON rf.role = s.role AND rf.fam = s.fam AND rf.cat = s.cat AND rf.ctx = {ref};
        """)
        change = con.execute("""
            SELECT coalesce(max(abs(ln(n.s / o.s))), 0) FROM ls_s_new n
            JOIN ls_s o USING (role, fam, ctx, cat)
            -- judge convergence on the big competitions (or the biggest, in small data)
            WHERE n.balls >= least(20000, (SELECT max(balls) FROM ls_s_new))
        """).fetchone()[0]
        con.execute("CREATE OR REPLACE TEMP TABLE ls_s AS SELECT * FROM ls_s_new")
        con.execute(r_update)
        if it >= 3 and change < 1e-4:
            break
    pivot = ", ".join(f"max(s) FILTER (WHERE cat = '{c}') AS s_{c}" for c in _FORM_CATS)
    con.execute(f"""
        CREATE OR REPLACE TABLE league_strength AS
        SELECT role, fam, ctx, cat, round(s, 4) AS strength, balls, players FROM ls_s
        ORDER BY role, fam, cat, balls DESC;
        CREATE OR REPLACE TEMP TABLE ls_wide AS
        SELECT role, fam, ctx, {pivot} FROM ls_s GROUP BY ALL;
    """)
    return {"iterations": it, "last_change": change}


def phase_exp_sql() -> str:
    """Per player/format/phase expected counts: plain context baseline (exp_*) and
    league-adjusted (lexp_* = exp_* x competition strength)."""

    def side(role: str, pc: str, ctx: str, extra: list[str]) -> str:
        exp = ", ".join(f"sum(p.balls * c.{c} / c.balls) AS exp_{c}" for c in _FORM_CATS + extra)
        lexp = ", ".join(f"sum(p.balls * c.{c} / c.balls * coalesce(l.s_{c}, 1)) AS lexp_{c}"
                         for c in _FORM_CATS)
        null_exp = "" if extra else ", NULL::DOUBLE AS exp_wide_balls, NULL::DOUBLE AS exp_noball_balls"
        return f"""
        SELECT '{role}' AS role, p.pid, p.format, p.phase, {exp}{null_exp}, {lexp}
        FROM {pc} p JOIN {ctx} c USING (format, ctx, yr, phase)
        LEFT JOIN ls_wide l ON l.role = '{role}' AND l.fam = {_fam('p.format')} AND l.ctx = p.ctx
        WHERE c.balls > 0 GROUP BY ALL"""

    return f"""
CREATE OR REPLACE TEMP TABLE phase_exp AS
{side('bat', 'pc_bat', 'ctx_bat', [])}
UNION ALL BY NAME
{side('bowl', 'pc_bowl', 'ctx_bowl', ['wide_balls', 'noball_balls'])};
"""


def form_sql(grid: list[tuple[int, int]]) -> str:
    values = ", ".join(f"({a}, {h})" for a, h in grid)
    weight = ("CASE WHEN g.half_life = 0 THEN 1.0 "
              "ELSE pow(0.5, (g.as_of - 1 - p.yr) / g.half_life) END")

    def side(role: str, table: str, ctx: str, extra: list[str]) -> str:
        obs = ", ".join(f"sum(w * {c}) AS {c}" for c in _FORM_CATS + extra)
        exp = ", ".join(f"sum(w * balls * c_{c} / c_balls) AS exp_{c}" for c in _FORM_CATS + extra)
        lexp = ", ".join(f"sum(w * balls * c_{c} / c_balls * s_{c}) AS lexp_{c}" for c in _FORM_CATS)
        null_extra = "" if extra else ", NULL::DOUBLE AS wide_balls, NULL::DOUBLE AS noball_balls"
        null_exp = "" if extra else ", NULL::DOUBLE AS exp_wide_balls, NULL::DOUBLE AS exp_noball_balls"
        cols = ", ".join(f"p.{c}" for c in _FORM_CATS + extra)
        ccols = ", ".join(f"c.{c} AS c_{c}" for c in _FORM_CATS + extra)
        scols = ", ".join(f"coalesce(l.s_{c}, 1) AS s_{c}" for c in _FORM_CATS)
        return f"""
        SELECT as_of, half_life, '{role}' AS role, pid, format, phase,
               sum(w * balls) AS balls, {obs}{null_extra}, {exp}{null_exp}, {lexp}
        FROM (
            SELECT g.as_of, g.half_life, p.pid, p.format, p.phase, p.balls, {cols},
                   c.balls AS c_balls, {ccols}, {scols}, {weight} AS w
            FROM {table} p
            JOIN {ctx} c USING (format, ctx, yr, phase)
            LEFT JOIN ls_wide l ON l.role = '{role}' AND l.fam = {_fam('p.format')} AND l.ctx = p.ctx
            CROSS JOIN grid g
            WHERE p.yr < g.as_of AND c.balls > 0
        ) GROUP BY ALL"""

    return f"""
CREATE OR REPLACE TABLE player_phase_form AS
WITH grid AS (SELECT * FROM (VALUES {values}) g(as_of, half_life))
SELECT * FROM (
    {side('bat', 'pc_bat', 'ctx_bat', [])}
    UNION ALL BY NAME
    {side('bowl', 'pc_bowl', 'ctx_bowl', ['wide_balls', 'noball_balls'])}
) WHERE balls > 0
ORDER BY as_of, half_life, pid, format, phase, role;
"""


EXP_COLS = ["exp_wickets", "exp_dots", "exp_ones", "exp_twos", "exp_threes", "exp_fours",
            "exp_sixes", "exp_wide_balls", "exp_noball_balls"] + [f"lexp_{c}" for c in _FORM_CATS]

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
       coalesce(nullif(wd.name_en, ''),
                nullif(regexp_replace(wd.wikipedia_title, ' \\(.*\\)$', ''), '')) AS full_name,
       nullif(wd.wikipedia_title, '') AS wikipedia_title,
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
LEFT JOIN wd ON wd.cricinfo_id = p.key_cricinfo
LEFT JOIN stumps st ON st.pid = s.pid
LEFT JOIN intl i ON i.pid = s.pid
LEFT JOIN capped c ON c.pid = s.pid
ORDER BY s.pid;
"""


# ------------------------------------------------------------------- venues
# Cricsheet writes the same ground several ways ("M Chinnaswamy Stadium" with and
# without ", Bengaluru"/", Bangalore"); the part before the first comma is the
# ground. Grounds that were renamed are merged under their current name.
VENUE_ALIASES = {
    "Feroz Shah Kotla": "Arun Jaitley Stadium",
    "Sardar Patel Stadium": "Narendra Modi Stadium",
    "Punjab Cricket Association Stadium": "Punjab Cricket Association IS Bindra Stadium",
    "Subrata Roy Sahara Stadium": "Maharashtra Cricket Association Stadium",
}


# Generic ground names used by several different grounds: these keep the city in
# the venue name. (Most names that appear with two cities are one ground labelled
# two ways, e.g. "Kensington Oval" with Barbados / Bridgetown, so this is a list.)
SHARED_GROUND_NAMES = ("County Ground", "The County Ground", "National Stadium", "Nehru Stadium",
                       "Queen's Park", "Gymkhana Club Ground")
# Different labels for the same city, so shared-name grounds aren't split further.
CITY_ALIASES = {"Bangalore": "Bengaluru", "Bombay": "Mumbai", "Madras": "Chennai",
                "Calcutta": "Kolkata", "Hove": "Brighton"}


def venues_sql() -> str:
    alias = " ".join(f"WHEN '{a}' THEN '{b}'" for a, b in VENUE_ALIASES.items())
    calias = " ".join(f"WHEN '{a}' THEN '{b}'" for a, b in CITY_ALIASES.items())
    ground = "trim(regexp_replace(split_part(venue, ',', 1), '\\s+', ' ', 'g'))"
    city = ("coalesce(nullif(trim(city), ''), "
            "nullif(trim(regexp_replace(venue, '^[^,]*,?', '')), ''))")
    shared = "(" + ", ".join("'" + g.replace("'", "''") + "'" for g in SHARED_GROUND_NAMES) + ")"
    return f"""
CREATE OR REPLACE TEMP VIEW mv AS
WITH b AS (
    SELECT *, CASE {ground} {alias} ELSE {ground} END AS ground,
           CASE {city} {calias} ELSE {city} END AS city_n
    FROM m WHERE venue IS NOT NULL
),
named AS (
    SELECT b.*, CASE WHEN b.ground IN {shared} AND b.city_n IS NOT NULL
                     THEN b.ground || ', ' || b.city_n ELSE b.ground END AS vname
    FROM b
)
SELECT *, regexp_replace(regexp_replace(lower(vname), '[^a-z0-9]+', '-', 'g'), '(^-|-$)', '', 'g')
          AS venue_id
FROM named;

CREATE OR REPLACE TABLE venues AS
SELECT venue_id AS id, mode(vname) AS name, mode(city_n) AS city,
       count(*)::INTEGER AS matches, min(start_date) AS first_match, max(start_date) AS last_match
FROM mv GROUP BY venue_id ORDER BY matches DESC;

-- Per venue and format. Limited-overs figures use uninterrupted matches only
-- (no rain rule); "recent" = the last three calendar years in the data.
CREATE OR REPLACE TABLE venue_format_stats AS
WITH inn AS (
    SELECT match_id, innings, any_value(batting_team) AS team, sum(runs_total) AS runs,
           sum(wicket_count) FILTER (WHERE wicket_kind NOT IN {NOT_OUT_KINDS} OR wicket_kind IS NULL)
               AS wkts
    FROM d GROUP BY ALL
),
x AS (
    SELECT f.format, mv.venue_id, mv.match_id, year(mv.start_date) AS yr, mv.winner, mv.result,
           mv.method, mv.toss_winner, mv.toss_decision,
           i1.runs AS r1, i1.wkts AS w1, i1.team AS t1, i2.runs AS r2, i2.team AS t2,
           (mv.overs = CASE f.format WHEN 'ODI' THEN 50 ELSE 20 END AND mv.method IS NULL) AS clean
    FROM mv JOIN match_formats f USING (match_id)
    LEFT JOIN inn i1 ON i1.match_id = mv.match_id AND i1.innings = 1
    LEFT JOIN inn i2 ON i2.match_id = mv.match_id AND i2.innings = 2
),
last AS (SELECT max(yr) AS y FROM x)
SELECT venue_id, format,
       count(*)::INTEGER AS matches,
       min(yr)::INTEGER AS first_year, max(yr)::INTEGER AS last_year,
       round(avg(r1) FILTER (WHERE clean OR format = 'Test'), 1) AS avg_first_innings,
       round(avg(r1) FILTER (WHERE (clean OR format = 'Test') AND yr > (SELECT y FROM last) - 3), 1)
           AS avg_first_innings_recent,
       count(*) FILTER (WHERE (clean OR format = 'Test') AND yr > (SELECT y FROM last) - 3)::INTEGER
           AS matches_recent,
       round(avg(w1) FILTER (WHERE clean OR format = 'Test'), 2) AS avg_first_innings_wickets,
       CASE WHEN format <> 'Test' THEN round(100.0 * count(*) FILTER (WHERE clean AND winner = t2)
            / nullif(count(*) FILTER (WHERE clean AND result = 'win'), 0), 1) END AS chasing_win_pct,
       round(100.0 * count(*) FILTER (WHERE winner = toss_winner)
             / nullif(count(*) FILTER (WHERE result = 'win'), 0), 1) AS toss_winner_wins_pct,
       round(100.0 * count(*) FILTER (WHERE toss_decision = 'field')
             / nullif(count(*) FILTER (WHERE toss_decision IS NOT NULL), 0), 1) AS toss_choose_field_pct,
       max(greatest(r1, coalesce(r2, 0)))::INTEGER AS highest_total,
       min(r1) FILTER (WHERE w1 >= 10)::INTEGER AS lowest_all_out_first_innings
FROM x GROUP BY venue_id, format
ORDER BY venue_id, format;

-- How each player gets out, per format (retirements excluded).
CREATE OR REPLACE TABLE player_dismissals AS
SELECT player_out_id AS player_id, f.format, wicket_kind AS kind, count(*)::INTEGER AS n
FROM d JOIN match_formats f USING (match_id)
WHERE is_wicket AND player_out_id IS NOT NULL AND wicket_kind NOT IN {NOT_OUT_KINDS}
GROUP BY ALL ORDER BY player_id, format, n DESC;

-- Player record at each venue, per format (batting + bowling).
CREATE OR REPLACE TABLE player_venue_stats AS
WITH b AS (
    SELECT bi.pid, bi.format, mv.venue_id, count(DISTINCT bi.match_id) AS bat_matches,
           count(*) AS innings, sum(bi.runs) AS runs, sum(bi.balls) AS balls,
           count(*) FILTER (WHERE bi.is_out) AS outs, max(bi.runs) AS highest
    FROM bat_inn bi JOIN mv USING (match_id) GROUP BY ALL
),
w AS (
    SELECT wi.pid, wi.format, mv.venue_id, sum(wi.balls) AS balls_bowled,
           sum(wi.runs) AS runs_conceded, sum(wi.wkts) AS wickets
    FROM bowl_inn wi JOIN mv USING (match_id) GROUP BY ALL
)
SELECT pid AS player_id, format, venue_id,
       coalesce(innings, 0)::INTEGER AS bat_innings, coalesce(runs, 0)::INTEGER AS runs,
       coalesce(balls, 0)::INTEGER AS balls_faced, highest::INTEGER AS highest,
       round(runs / nullif(outs, 0), 2) AS bat_avg, round(100.0 * runs / nullif(balls, 0), 2) AS bat_sr,
       coalesce(balls_bowled, 0)::INTEGER AS balls_bowled,
       coalesce(runs_conceded, 0)::INTEGER AS runs_conceded,
       coalesce(wickets, 0)::INTEGER AS wickets,
       round(6.0 * runs_conceded / nullif(balls_bowled, 0), 2) AS bowl_econ
FROM b FULL OUTER JOIN w USING (pid, format, venue_id)
WHERE pid IS NOT NULL
ORDER BY player_id, format, runs DESC;
"""


def legends_sql(csv_path: Path) -> str:
    """Pre-2001 greats from reference/legends.csv (Wikipedia infoboxes), one row per
    player and format. ``cricsheet_id`` links a legend to the same person in the
    ball-by-ball data (full name AND country must match), so an XI can't hold both."""
    return f"""
CREATE OR REPLACE TABLE legends AS
WITH l AS (
    SELECT 'L-' || regexp_replace(regexp_replace(lower(name), '[^a-z0-9]+', '-', 'g'), '(^-|-$)', '', 'g') AS id, *
    FROM read_csv('{csv_path.as_posix()}', header = true)
)
SELECT l.id, (SELECT p.id FROM players p WHERE p.full_name = l.name AND p.country = l.country LIMIT 1) AS cricsheet_id,
       l.name, l.country, l.format, l.matches::INTEGER AS matches, l.runs::INTEGER AS runs, l.bat_avg,
       l.bat_sr, l.hundreds::INTEGER AS hundreds, l.fifties::INTEGER AS fifties, l.highest::INTEGER AS highest,
       l.balls_bowled::INTEGER AS balls_bowled, l.wickets::INTEGER AS wickets, l.bowl_avg, l.bowl_econ,
       l.bowl_sr, l.best_bowling, l.catches::INTEGER AS catches, l.stumpings::INTEGER AS stumpings,
       l.role, l.batting_hand, l.bowling_arm, l.bowling_type,
       l.format_start::INTEGER AS format_start, l.format_end::INTEGER AS format_end,
       l.era_start::INTEGER AS era_start, l.era_end::INTEGER AS era_end, l.source_url
FROM l ORDER BY l.name, l.format;
"""


PLAYER_TEAMS_SQL = """
-- Who played for which side, per format and season (country for internationals,
-- franchise for leagues). Drives IPL drafting and nationality hints.
CREATE OR REPLACE TABLE player_teams AS
SELECT mp.player_id, f.format, f.season, mp.team, count(DISTINCT mp.match_id)::INTEGER AS matches
FROM mp JOIN match_formats f USING (match_id)
WHERE mp.player_id IS NOT NULL
GROUP BY ALL ORDER BY player_id, format, season;
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
        # Full names + Wikipedia titles from Wikidata (`gully-pipeline names`); optional.
        names = Path(__file__).resolve().parents[2] / "reference" / "wikidata_players.csv"
        if names.exists():
            con.execute(f"CREATE OR REPLACE TEMP TABLE wd AS SELECT * FROM read_csv("
                        f"'{names.as_posix()}', header = true, all_varchar = true)")
        else:
            con.execute("CREATE OR REPLACE TEMP TABLE wd "
                        "(cricinfo_id VARCHAR, name_en VARCHAR, wikipedia_title VARCHAR)")
        con.execute(FORMATS_SQL)
        con.execute(INNINGS_SQL)
        con.execute(stats_sql("player_format_stats", ["format"]))
        con.execute(stats_sql("player_season_stats", ["format", "season"]))
        con.execute(CONTEXT_SQL)
        con.execute(FORM_BASE_SQL)
        fit = league_strength(con)
        print(f"league strength fit: {fit['iterations']} iterations, last change {fit['last_change']:.2e}")
        con.execute(phase_exp_sql())
        con.execute(PHASE_SQL)
        last_year = con.execute("SELECT max(yr) FROM fdc").fetchone()[0]
        as_ofs = sorted({min(FORM_FIRST_AS_OF, last_year + 1), *range(FORM_FIRST_AS_OF, last_year + 2)})
        con.execute(form_sql([(a, h) for a in as_ofs for h in FORM_HALF_LIVES]))
        con.execute(PLAYERS_SQL)
        con.execute(venues_sql())
        con.execute(legends_sql(Path(__file__).resolve().parents[2] / "reference" / "legends.csv"))
        con.execute(PLAYER_TEAMS_SQL)
        tables = ["players", "player_format_stats", "player_season_stats", "player_phase_stats",
                  "player_phase_form", "league_strength", "venues", "venue_format_stats",
                  "player_dismissals", "player_venue_stats", "legends", "player_teams"]
        return {t: con.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in tables}
