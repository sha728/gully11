-- Player stats tables. Rebuilt from scratch on every `gully-pipeline load`.
-- Source: pipeline/src/gully_pipeline/aggregate.py (DuckDB). Keep columns in sync.

CREATE EXTENSION IF NOT EXISTS pg_trgm;

DROP TABLE IF EXISTS player_phase_stats, player_season_stats, player_format_stats, players;

CREATE TABLE players (
    id                  text PRIMARY KEY,          -- Cricsheet register identifier
    cricsheet_id        text NOT NULL,
    name                text NOT NULL,
    unique_name         text,
    cricinfo_id         text,
    country             text,
    role                text NOT NULL CHECK (role IN ('BAT', 'BOWL', 'AR', 'WK')),
    batting_hand        text,
    bowling_style       text,
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
    PRIMARY KEY (player_id, format, phase, role)
);

CREATE INDEX players_name_trgm ON players USING gin (name gin_trgm_ops);
CREATE INDEX players_unique_name_trgm ON players USING gin (unique_name gin_trgm_ops);
CREATE INDEX players_country ON players (country);
CREATE INDEX players_role ON players (role);
CREATE INDEX player_format_stats_format ON player_format_stats (format, player_id);
