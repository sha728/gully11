-- Player stats tables. Rebuilt from scratch on every `gully-pipeline load`.
-- Source: pipeline/src/gully_pipeline/aggregate.py (DuckDB). Keep columns in sync.

CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Children before parents (foreign keys).
DROP TABLE IF EXISTS player_matchups, player_opening, legends, player_teams,
    player_venue_stats, player_dismissals, venue_format_stats, venues,
    player_phase_form, player_phase_stats, player_season_stats, player_format_stats, players;

CREATE TABLE players (
    id                  text PRIMARY KEY,          -- Cricsheet register identifier
    cricsheet_id        text NOT NULL,
    name                text NOT NULL,
    unique_name         text,
    cricinfo_id         text,
    full_name           text,              -- Wikidata English label
    wikipedia_title     text,
    country             text,
    role                text NOT NULL CHECK (role IN ('BAT', 'BOWL', 'AR', 'WK')),
    batting_hand        text,              -- 'L' / 'R', from Wikipedia's infobox
    bowling_style       text,              -- 'spin' / 'pace': Wikipedia, else from stumpings off their bowling
    bowling_arm         text,              -- 'L' / 'R'
    bowling_type        text,              -- fast / fast-medium / medium / off-spin / leg-spin / left-arm orthodox / left-arm wrist-spin
    is_overseas_for_ipl boolean,
    capped              boolean NOT NULL,
    era_start           integer,
    era_end             integer,
    matches             integer NOT NULL,
    bat_share           double precision,
    bowl_share          double precision,
    source              text NOT NULL
);

CREATE TABLE player_format_stats (
    player_id     text NOT NULL REFERENCES players (id),
    format        text NOT NULL,
    matches       integer NOT NULL,
    bat_innings   integer NOT NULL,
    runs          integer NOT NULL,
    balls_faced   integer NOT NULL,
    not_outs      integer NOT NULL,
    highest       integer,
    fifties       integer NOT NULL,
    hundreds      integer NOT NULL,
    fours         integer NOT NULL,
    sixes         integer NOT NULL,
    bat_avg       double precision,
    bat_sr        double precision,
    bowl_innings  integer NOT NULL,
    balls_bowled  integer NOT NULL,
    runs_conceded integer NOT NULL,
    wickets       integer NOT NULL,
    best_bowling  text,
    five_wkts     integer NOT NULL,
    bowl_econ     double precision,
    bowl_avg      double precision,
    bowl_sr       double precision,
    bowl_dot_pct  double precision,
    catches       integer NOT NULL,
    stumpings     integer NOT NULL,
    PRIMARY KEY (player_id, format)
);

CREATE TABLE player_season_stats (
    LIKE player_format_stats,
    season text NOT NULL,
    PRIMARY KEY (player_id, format, season)
);

CREATE TABLE player_phase_stats (
    player_id      text NOT NULL REFERENCES players (id),
    format         text NOT NULL,
    phase          text NOT NULL CHECK (phase IN ('PP', 'middle', 'death')),
    role           text NOT NULL CHECK (role IN ('bat', 'bowl')),
    balls          integer NOT NULL,
    runs           integer NOT NULL,
    wickets        integer NOT NULL,
    dots           integer NOT NULL,
    ones           integer NOT NULL,
    twos           integer NOT NULL,
    threes         integer NOT NULL,
    fours          integer NOT NULL,
    sixes          integer NOT NULL,
    wide_balls     integer,
    noball_balls   integer,
    dismissal_rate double precision,
    dot_pct        double precision,
    single_pct     double precision,
    two_pct        double precision,
    three_pct      double precision,
    four_pct       double precision,
    six_pct        double precision,
    wide_rate      double precision,
    noball_rate    double precision,
    strike_rate    double precision,
    economy        double precision,
    -- Expected counts had an average player faced/bowled the same balls in the
    -- same competitions, years and phases (context-adjusted baseline).
    exp_wickets      double precision,
    exp_dots         double precision,
    exp_ones         double precision,
    exp_twos         double precision,
    exp_threes       double precision,
    exp_fours        double precision,
    exp_sixes        double precision,
    exp_wide_balls   double precision,
    exp_noball_balls double precision,
    -- League-adjusted expectations: exp_* x competition strength (league_strength),
    -- so ratings from different leagues share one scale (T20: IPL = 1).
    lexp_wickets        double precision,
    lexp_dots           double precision,
    lexp_ones           double precision,
    lexp_twos           double precision,
    lexp_threes         double precision,
    lexp_fours          double precision,
    lexp_sixes          double precision,
    PRIMARY KEY (player_id, format, phase, role)
);

-- Simulator ratings input: recency-weighted phase counts (fractional), current
-- as of `as_of` (first year NOT included) with `half_life` years of decay.
-- Same count columns as player_phase_stats, so the simulator reads either.
CREATE TABLE player_phase_form (
    player_id        text NOT NULL REFERENCES players (id),
    format           text NOT NULL,
    phase            text NOT NULL,
    role             text NOT NULL,
    as_of            integer NOT NULL,
    half_life        integer NOT NULL,
    balls            double precision NOT NULL,
    wickets          double precision NOT NULL,
    dots             double precision NOT NULL,
    ones             double precision NOT NULL,
    twos             double precision NOT NULL,
    threes           double precision NOT NULL,
    fours            double precision NOT NULL,
    sixes            double precision NOT NULL,
    wide_balls       double precision,
    noball_balls     double precision,
    exp_wickets      double precision,
    exp_dots         double precision,
    exp_ones         double precision,
    exp_twos         double precision,
    exp_threes       double precision,
    exp_fours        double precision,
    exp_sixes        double precision,
    exp_wide_balls   double precision,
    exp_noball_balls double precision,
    -- League-adjusted expectations: exp_* x competition strength (league_strength),
    -- so ratings from different leagues share one scale (T20: IPL = 1).
    lexp_wickets        double precision,
    lexp_dots           double precision,
    lexp_ones           double precision,
    lexp_twos           double precision,
    lexp_threes         double precision,
    lexp_fours          double precision,
    lexp_sixes          double precision,
    PRIMARY KEY (player_id, format, phase, role)
);

-- Matchups: a batter against pace / spin (split = bowling_style), a bowler against
-- left- / right-handers (split = batting_hand). o_* observed, x_* what an average
-- player got in the same matchup and context; o/x > 1 = above average. All data
-- (the per-season cut-offs used in validation stay in DuckDB).
CREATE TABLE player_matchups (
    player_id   text NOT NULL REFERENCES players (id),
    role        text NOT NULL,              -- 'bat' / 'bowl'
    fam         text NOT NULL,              -- 'T20' / 'ODI' / 'Test'
    split       text NOT NULL,              -- 'pace' / 'spin' (bat), 'L' / 'R' (bowl)
    balls       double precision NOT NULL,
    o_wickets double precision, o_dots double precision, o_ones double precision, o_twos double precision,
    o_threes double precision, o_fours double precision, o_sixes double precision,
    x_wickets double precision, x_dots double precision, x_ones double precision, x_twos double precision,
    x_threes double precision, x_fours double precision, x_sixes double precision,
    PRIMARY KEY (player_id, role, fam, split)
);

CREATE INDEX players_name_trgm ON players USING gin (name gin_trgm_ops);
CREATE INDEX players_unique_name_trgm ON players USING gin (unique_name gin_trgm_ops);
CREATE INDEX players_full_name_trgm ON players USING gin (full_name gin_trgm_ops);
CREATE INDEX players_country ON players (country);
CREATE INDEX players_role ON players (role);
CREATE INDEX player_format_stats_format ON player_format_stats (format, player_id);

-- Venues -------------------------------------------------------------------
CREATE TABLE venues (
    id          text PRIMARY KEY,           -- slug of the ground name
    name        text NOT NULL,
    city        text,
    matches     integer NOT NULL,
    first_match date,
    last_match  date
);

CREATE TABLE venue_format_stats (
    venue_id                     text NOT NULL REFERENCES venues (id),
    format                       text NOT NULL,
    matches                      integer NOT NULL,
    first_year                   integer,
    last_year                    integer,
    avg_first_innings            double precision,   -- uninterrupted matches only
    avg_first_innings_recent     double precision,   -- last 3 years in the data
    matches_recent               integer,
    avg_first_innings_wickets    double precision,
    chasing_win_pct              double precision,   -- limited overs only
    toss_winner_wins_pct         double precision,
    toss_choose_field_pct        double precision,
    highest_total                integer,
    lowest_all_out_first_innings integer,
    PRIMARY KEY (venue_id, format)
);

CREATE TABLE player_dismissals (
    player_id text NOT NULL REFERENCES players (id),
    format    text NOT NULL,
    kind      text NOT NULL,
    n         integer NOT NULL,
    PRIMARY KEY (player_id, format, kind)
);

CREATE TABLE player_venue_stats (
    player_id     text NOT NULL REFERENCES players (id),
    format        text NOT NULL,
    venue_id      text NOT NULL REFERENCES venues (id),
    bat_innings   integer NOT NULL,
    runs          integer NOT NULL,
    balls_faced   integer NOT NULL,
    highest       integer,
    bat_avg       double precision,
    bat_sr        double precision,
    balls_bowled  integer NOT NULL,
    runs_conceded integer NOT NULL,
    wickets       integer NOT NULL,
    bowl_econ     double precision,
    PRIMARY KEY (player_id, format, venue_id)
);

CREATE INDEX venues_name_trgm ON venues USING gin (name gin_trgm_ops);
CREATE INDEX player_venue_stats_venue ON player_venue_stats (venue_id, format);

-- Pre-2001 greats (Wikipedia infobox career figures), one row per format -------
CREATE TABLE legends (
    id           text NOT NULL,             -- 'L-<name slug>'
    cricsheet_id text REFERENCES players (id), -- same person in the ball-by-ball data
    name         text NOT NULL,
    country      text NOT NULL,
    format       text NOT NULL,             -- Test / ODI
    matches      integer,
    runs         integer,
    bat_avg      double precision,
    bat_sr       double precision,          -- usually unknown for this era
    hundreds     integer,
    fifties      integer,
    highest      integer,
    balls_bowled integer,
    wickets      integer,
    bowl_avg     double precision,
    bowl_econ    double precision,
    bowl_sr      double precision,
    best_bowling text,
    catches      integer,
    stumpings    integer,
    role         text NOT NULL,
    batting_hand text,
    bowling_arm  text,
    bowling_type text,
    opener       boolean NOT NULL DEFAULT false,
    format_start integer,
    format_end   integer,
    era_start    integer,
    era_end      integer,
    source_url   text,
    PRIMARY KEY (id, format)
);

-- Sides each player appeared for, per format and season ---------------------
CREATE TABLE player_teams (
    player_id text NOT NULL REFERENCES players (id),
    format    text NOT NULL,
    season    text NOT NULL,
    team      text NOT NULL,
    matches   integer NOT NULL,
    PRIMARY KEY (player_id, format, season, team)
);
CREATE INDEX player_teams_lookup ON player_teams (format, team, season);

-- Openers: innings batted and innings opened, per format ---------------------
CREATE TABLE player_opening (
    player_id text NOT NULL REFERENCES players (id),
    format    text NOT NULL,
    innings   integer NOT NULL,
    opened    integer NOT NULL,
    PRIMARY KEY (player_id, format)
);
