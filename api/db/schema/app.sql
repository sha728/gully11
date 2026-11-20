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

-- A finished auction (live rooms are held in the API process while they run).
CREATE TABLE IF NOT EXISTS auction_rooms (
    code        text PRIMARY KEY,
    mode        text NOT NULL,              -- 'mega' (later 'mini')
    teams       integer NOT NULL,
    result      jsonb NOT NULL,             -- squads, spend, best-value buys
    created_at  timestamptz NOT NULL DEFAULT now(),
    ended_at    timestamptz
);
-- Who held which franchise (sha256 of each person's seat token) and the host's
-- franchise, so the season after an auction knows whose squad is whose.
ALTER TABLE auction_rooms ADD COLUMN IF NOT EXISTS seats jsonb;

-- The season a finished auction's squads play: lineups while it's being set up,
-- then the result (table, playoffs, caps, match summaries). Full matches live in
-- sim_results with context 'season' and ref = room code.
CREATE TABLE IF NOT EXISTS seasons (
    code        text PRIMARY KEY REFERENCES auction_rooms(code),
    lineups     jsonb NOT NULL DEFAULT '{}'::jsonb,   -- {franchise: {"xi": [ids, batting order], "impact": id}}
    result      jsonb,                                -- set once played
    created_at  timestamptz NOT NULL DEFAULT now(),
    played_at   timestamptz
);

-- The captain the person picked for their XI (null: the best-rated captain in it).
ALTER TABLE xi_drafts ADD COLUMN IF NOT EXISTS captain text;

-- Daily challenge leaderboard: one entry per daily draft played (the draft id is
-- the only "account": whoever holds it can name the entry). Ranked by points
-- (win 2, tie or draw 1), then run difference across the five matches.
CREATE TABLE IF NOT EXISTS xi_daily_entries (
    draft_id    text PRIMARY KEY REFERENCES xi_drafts(id),
    format      text NOT NULL,
    day         date NOT NULL,
    slug        text NOT NULL REFERENCES xi_challenges(slug),
    name        text,                       -- nickname; null shows as "Anonymous"
    won         integer NOT NULL,
    lost        integer NOT NULL,
    tied        integer NOT NULL,
    drawn       integer NOT NULL,
    points      integer NOT NULL,
    run_diff    integer NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS xi_daily_entries_board ON xi_daily_entries (format, day, points DESC, run_diff DESC, created_at);
