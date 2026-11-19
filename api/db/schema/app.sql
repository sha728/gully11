-- Tables the API itself writes (user-created state). Applied at API startup and
-- never dropped by `gully-pipeline load`, unlike the stats tables in players.sql.

CREATE TABLE IF NOT EXISTS xi_challenges (
    slug        text PRIMARY KEY,           -- hash of (format, seed, picks): same XI, same link
    format      text NOT NULL,
    seed        bigint NOT NULL,
    daily       date,                       -- set when played as the daily challenge
    picks       jsonb NOT NULL,             -- {"ids": spin order, "slots": batting position of each}
    xi          jsonb NOT NULL,             -- the XI as drafted, in batting order
    opponent    text NOT NULL,
    result      jsonb NOT NULL,             -- won / lost / drawn / tied + verdict
    matches     jsonb NOT NULL,             -- per-match summaries
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS xi_challenges_daily ON xi_challenges (format, daily);

CREATE TABLE IF NOT EXISTS sim_results (
    id          bigserial PRIMARY KEY,
    context     text NOT NULL,              -- 'xi' now; 'season' later
    ref         text NOT NULL,              -- challenge slug (or season id)
    match_no    integer NOT NULL,
    match_json  jsonb NOT NULL,             -- full match: innings, cards, commentary
    created_at  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (context, ref, match_no)
);

-- A draft in progress. Spins are revealed one at a time and every pick and move is
-- checked here, so the browser never holds spins it hasn't revealed.
CREATE TABLE IF NOT EXISTS xi_drafts (
    id          text PRIMARY KEY,           -- random token; whoever holds it drafts
    format      text NOT NULL,
    seed        bigint NOT NULL,
    daily       date,
    rival       text,                       -- challenge slug being chased, if any
    revealed    integer NOT NULL DEFAULT 0,
    picks       jsonb NOT NULL,             -- 11 entries: null or {"id", "slot"}
    challenge   text,                       -- slug once played
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);
