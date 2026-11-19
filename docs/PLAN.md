# Cricket Fan App — Full Project Plan

Nov 19, 2026 · @Shahid

## Overview

One web app for cricket fans that combines three things today split across three sites: deep player stats, an all-time XI builder with simulated series, and a realistic multiplayer IPL auction. Working name: **Gully11** (placeholder, change freely).

The app wins on integration, not on any single feature. Everything runs off **one player database and one match simulator**:

- **Stats → Auction:** every player card in the auction room shows real career and recent-form stats, plus a model-estimated fair price.
- **Auction → Simulator:** after the auction ends, every franchise's squad plays a simulated league season, so the room learns who actually built the best team. None of the reference sites closes this loop.
- **XI Builder ↔ Stats:** every drafted player links to their full stats page; the simulator uses the same numbers the stats pages show.

**Goals for v1**

1. A fan can look up any modern player and compare two players in under 10 seconds.
2. A fan can draft an XI and play a simulated 5-match series against a World XI, solo or against a friend.
3. Up to 10 friends (or 1 human plus AI bots) can run a full IPL-rules auction in real time, then watch the simulated season.

**Out of scope for v1:** live scores, accounts with passwords, payments or prizes, native mobile apps, women's cricket (planned for v2; the data exists).

## Reference products

Each reference does one module well; none connects to the others. Taken from their homepages on 19 Nov 2026.

| Product | What it does | What we take | What we add |
| --- | --- | --- | --- |
| [Beat My 11](https://beatmy11.com/) | Spin for an era + nation, draft an all-time XI, play a 5-match series vs a fixed World XI. Test, ODI, T20I, IPL. Daily challenge (same spins for everyone), friend challenge, leaderboard, no accounts. | Spin-and-draft loop, daily seed, friend challenge link, no-signup play | Ball-by-ball sim you can watch, player stats on tap, sim engine shared with the auction |
| [PlayAuctionGame](https://www.playauctiongame.com/) | Real-time IPL auction rooms, up to 10 friends, IPL-style timer, 350+ player pool. Mock Auction (official list + base prices) and Mega Auction (worldwide pool, full budget). No signup. | Room codes, timer-driven bidding, mock vs mega modes | Full rule engine (overseas cap, squad limits, max-fee rule, accelerated rounds), AI bot franchises, fair-price hints, post-auction simulated season |
| [Hindsight](https://hindsightcricket.com/) | T20 analytics: player and team comparisons, venue analysis, ELO team rankings, fixtures, scorecards, yearly Wrapped. | Player profiles, head-to-head comparison, venue splits | Test and ODI too, links into auction and XI modes |

## Feature scope

v1 ships all three modules at a usable depth; v2 adds polish and breadth.

| Module | v1 (must ship) | v2 (later) |
| --- | --- | --- |
| Stats | Player search, profile (career + by format + by season), batting/bowling splits by phase (powerplay, middle, death), head-to-head compare of 2 players, venue page | Team ELO rankings, matchup stats (batter vs bowler), yearly Wrapped, women's cricket |
| XI Builder | Spin era + nation, draft XI with role rules (min bowlers, 1 keeper), 5-match series vs World XI, ball-by-ball commentary feed, shareable challenge link, daily seeded challenge | Global leaderboard, custom World XI, XI vs XI between two friends live |
| Auction | Rooms with code, 2–10 franchises, humans + AI bots, mock (mini) and mega modes, full rule engine, live purse/squad panel, accelerated rounds, auction summary | Retentions/RTM pre-phase for mega mode, trade window, auction replays |
| Season sim | Post-auction round-robin + playoffs using the shared simulator, points table, top performers | Watch any match ball by ball, awards (Orange/Purple Cap equivalents) |
| Platform | Guest play with nickname (no passwords), responsive web | Optional sign-in to save history, PWA install |

## Data sources and licensing

Cricsheet covers everything modern for free; pre-2001 legends need a hand-built table, and that is the biggest manual task in the project.

| Need | Source | Coverage | License / cost |
| --- | --- | --- | --- |
| Ball-by-ball match data | [Cricsheet downloads](https://cricsheet.org/downloads/) (JSON) | Men's Tests from Dec 2001, ODIs from Jun 2002, T20Is from Feb 2005, IPL every match since Apr 2008 (1,243 of 1,243), plus BBL, PSL, CPL, SA20, ILT20 and more ([coverage](https://cricsheet.org/coverage/)) | Free, [Open Data Commons Attribution](https://cricsheet.org/licensing/): credit Cricsheet in the footer |
| Player identity across sources | Cricsheet Register (people.csv, maps to Cricinfo/Cricbuzz IDs) | All Cricsheet players | Same ODC-BY license |
| All-time legends (pre-2001) | Hand-curated `legends.csv`: career runs, average, strike rate, wickets, economy per format | \~300 players, built once | Your own compilation of public career totals; cite where each figure came from |
| IPL auction history | Kaggle IPL auction datasets (2008 onward), cross-checked against news coverage | Varies by dataset | Check each dataset's license before use; not verified yet |
| Current auction player list + base prices | Official IPL auction list (published as PDF before each auction) | Per auction | Manual import into `auction_pool.csv` |
| Player photos | None in v1: initials avatars in team colours | — | Avoids image-rights issues; paid APIs (CricAPI, SportMonks, Roanuz) are the v2 option |

**Batting hand and bowling style** (not in Cricsheet; needed by the simulator for matchups such as left-hand batter vs off-spin):

1. Cricsheet `people.csv` gives each player's ESPNcricinfo ID.
2. One Wikidata query maps ESPNcricinfo IDs (property P2697) to English Wikipedia article titles: 30,853 of the 32,010 cricketers with that ID have an article (checked 19 Nov 2026).
3. Fetch those articles' wikitext through the Wikipedia API (50 titles per request) and read the `Infobox cricketer` fields `batting`, `bowling` and `role` with `mwparserfromhell`. Example: Rinku Singh = Left-handed, Right-arm off break, Middle-order batter.
4. Normalise the free text into fixed categories: hand (L/R); bowling arm (L/R); bowling type (fast, fast-medium, medium, off-spin, leg-spin, left-arm orthodox, left-arm wrist-spin).
5. Any auction-pool player still missing values is filled by hand and flagged `source = manual`.

Wikidata's own fields are too sparse to use directly: only 1,158 of those 32,010 players have a bowling style and 30 have a batting hand. Wikipedia text is CC BY-SA 4.0, so credit Wikipedia beside Cricsheet in the footer.

**Do not scrape ESPNcricinfo or Cricbuzz.** Their terms prohibit it, and a public portfolio project should stand on licensed data.

**Ingestion plan:** download Cricsheet JSON zips → parse with Python into Parquet (one row per delivery) → aggregate in DuckDB into player, season, phase and venue tables → load aggregates into Postgres. Re-run weekly via a scheduled GitHub Action.

## Data model

Twelve core tables in Postgres; raw deliveries stay in Parquet/DuckDB and never hit the app database.

| Table | Key columns | Used by |
| --- | --- | --- |
| `players` | id, cricsheet\_id, name, country, role (BAT/BOWL/AR/WK), batting\_hand, bowling\_style, is\_overseas\_for\_ipl, capped, era\_start, era\_end, source (cricsheet / legends) | All modules |
| `player_format_stats` | player\_id, format, matches, runs, bat\_avg, bat\_sr, balls\_faced, wickets, bowl\_econ, bowl\_avg, bowl\_sr | Stats, XI, sim |
| `player_season_stats` | player\_id, format, season, same metrics as above | Stats trends, auction form |
| `player_phase_stats` | player\_id, format, phase (PP/middle/death), dismissal\_rate, dot\_pct, four\_pct, six\_pct, single\_pct | Simulator |
| `venues` | id, name, city, country, avg\_first\_innings\_score by format | Stats, sim (v2) |
| `auction_history` | player\_id, season, team, base\_price, sold\_price, sold (bool) | Price model |
| `auction_pool` | pool\_id, player\_id, set\_code, base\_price\_lakh | Auction rooms |
| `rooms` | id, code, mode (mini/mega), rules\_json, status, created\_at | Auction |
| `franchises` | id, room\_id, name, owner (human nickname or bot), purse\_left\_lakh | Auction |
| `bids` / `sales` | room\_id, player\_id, franchise\_id, amount\_lakh, timestamp, result | Auction log, replays |
| `xi_challenges` | id, seed, format, era, nation, picks\_json, result\_json, share\_slug | XI builder |
| `sim_results` | id, context (xi / season), match\_json, scorecard\_json | XI, season |

Money is stored as an integer in **lakh** (₹1 crore = 100 lakh) to avoid float rounding.

## Match simulation engine

The simulator is the shared core: the XI series and the post-auction season both call it, so it gets built and tested before any UI.

**Approach: ball-by-ball outcome probabilities.** For each delivery, pick one outcome from {dot, 1, 2, 3, 4, 6, wide, no-ball, wicket} using a probability vector blended from the batter's and bowler's real rates.

1. **Base rates** per format and phase come from all Cricsheet deliveries (e.g. T20 death overs).
2. **Player adjustment:** each batter and bowler gets a ratio vs that base (their four%, six%, dot%, dismissal rate in that phase). Use the log5 method to combine batter and bowler: it is the standard way to merge two players' rates against a league average.
3. **Shrinkage:** players with few balls are pulled toward the base rate (Bayesian prior), so a player with 30 balls faced does not look like a superstar.
4. **Game state:** in a chase, raise aggression as the required rate climbs; cut it after quick wickets. Start with simple multipliers, tune later.
5. **Legends without ball-by-ball data:** derive approximate phase rates from career average and strike rate (e.g. dismissal rate ≈ 1 / balls-per-dismissal). Label these players "estimated" in the UI.
6. **Bowling plan:** each XI must have at least 5 bowling options; a simple scheduler assigns overs respecting per-bowler limits (4 in T20, 10 in ODI).
7. **Formats:** T20 and ODI in v1 with the same engine; Tests need declarations and follow-ons, so v1 runs Tests as 2 innings each with a simple declaration rule and marks them beta.

**Output:** full scorecard, ball-by-ball commentary lines (template text, no LLM needed), and a win-probability series per ball.

**Determinism:** every match takes a seed. The same seed and the same XIs reproduce the same match, which powers daily challenges and shareable results.

**Validation:** simulate 1,000 seasons of real IPL squads and check that average first-innings scores, boundary rates and wicket rates match the real distribution within about 5%.

## Auction engine

Every IPL rule lives in a `rules.json` per mode, never in code, so a rule change or a new league is a config edit.

**Rules to encode** (IPL 2026 cycle, from [ESPNcricinfo's auction FAQ](https://www.cricinfo.com/story/ipl-auction-2026-faqs-when-where-who-and-how-much-1515453) and the [IPL Player Regulations 2025–27](https://www.iplt20.com/news/article/ipl-governing-council-announces-tata-ipl-player-regulations-2025-27)):

| Rule | Value | Status |
| --- | --- | --- |
| Squad size | Min 18, max 25 | Confirmed |
| Overseas players | Max 8 per squad | Confirmed |
| Overseas max fee (mini auction) | Lower of the top retention slab (₹18 cr) and the previous mega auction's top price; bids can go higher but the player is paid the cap | Confirmed |
| RTM | Not available in mini auctions; mega auctions allow 6 retentions + RTMs combined (max 5 capped, max 2 uncapped) | Confirmed |
| Accelerated rounds | Start after the first 70 players are presented; franchises then nominate unsold players for further accelerated rounds | Confirmed (2026 mini auction) |
| Full purse (mega mode) | ₹120 cr per team | Verify against the regulations before coding |
| Bid increment slabs | Increment grows with price (smaller steps under ₹1 cr, larger above) | Exact slabs not verified; look up before coding |
| Base prices | Set per player in the auction list (e.g. ₹2 cr top slab) | From the official list |

**Room flow**

1. Host creates a room → gets a 6-letter code. Picks mode (mini or mega), number of franchises (2–10) and how many are bots.
2. Players join with a nickname and claim a franchise. Host starts.
3. Players are presented set by set (marquee, capped batters, capped all-rounders …), as in the real auction.
4. For each player: a timer starts (e.g. 15 s). Any eligible franchise can bid the next increment; each bid resets the timer to 10 s.
5. **Server validates every bid**: enough purse left after reserving base price × remaining minimum slots, squad not full, overseas cap not hit.
6. Timer hits zero → sold to the highest bidder, or unsold. Purse and squad panels update for everyone.
7. After the configured number of players, switch to accelerated rounds; then end the auction.
8. Summary screen: every squad, total spend, best value buys (price vs model fair value) → "Simulate season" button.

**Concurrency:** the room state lives in Redis; each bid is applied with an atomic Lua script (or a per-room lock) so two bids arriving in the same millisecond cannot both win. The server owns the clock; clients only display it.

**AI bot franchises** so one person can run a full auction:

- Each bot has a squad plan (e.g. 7 batters, 7 bowlers, 4 all-rounders, 2 keepers) and a personality (aggressive, value-hunter, balanced).
- Bot's maximum bid = model fair price × need multiplier (higher when that role is short) × personality factor, capped by purse rules.
- Bots bid after a random 1–4 s delay so they feel human.

**Fair-price model:** gradient-boosted regression (LightGBM) on `auction_history` + recent T20 stats (runs, strike rate, wickets, economy over the last 2 seasons), role, age, capped status, overseas flag. Shown as a hint on each player card and used by bots.

## XI Builder (Beat the World XI)

A seeded spin-and-draft game that runs entirely on the shared simulator.

1. Pick a format: Test, ODI, T20I or IPL.
2. **Spin:** the app draws an era (e.g. 1990s) and a nation (or an IPL franchise) from a seeded random generator. You get 11 spins, one per slot.
3. **Draft:** for each spin, choose one eligible player from a list sorted by a rating. Role rules: exactly 1 keeper, at least 5 bowling options, at most 4 overseas for IPL mode.
4. **Play:** a 5-match series against a fixed World XI for that format. Watch it ball by ball or skip to scorecards.
5. **Share:** a link with the seed and your picks; a friend gets the same spins and tries to beat your series result.
6. **Daily challenge:** one seed per day per format, same for every player, results on a daily leaderboard (nickname only).

**World XI** per format is a curated list stored in config so it can be changed without code. Legends from `legends.csv` appear only in eras before 2001; later eras use Cricsheet-derived ratings.

## Stats and analytics

The stats module is the cheapest to build and doubles as the test that the data pipeline is right.

- **Search:** fuzzy name search (Postgres `pg_trgm`), filters by country, role, format.
- **Player profile:** career table by format; season-by-season line chart of average and strike rate; phase splits (powerplay, middle, death) for batting and bowling; dismissal types; best venues.
- **Compare:** any two players side by side, same format and date range, with a radar chart of normalised metrics.
- **Venue page:** average first-innings score, chasing win %, pace vs spin wickets share.
- **Cross-links:** "Draft in XI Builder" and "Last auction price" buttons on every profile.

All pages read from pre-aggregated tables, so every request is a single indexed query and the API stays fast without caching tricks.

## Architecture and tech stack

One Python backend owns the data, the simulator and the auction rooms. Python handles the data and ML work; React runs the frontend.

&#91;embedded content: system architecture · 3 frontend modules, 4 backend services, 3 data stores\]

The simulator (highlighted) is the one component every module depends on; Redis holds only live auction state, Postgres holds everything durable.

| Layer | Choice | Why |
| --- | --- | --- |
| Frontend | Next.js (React, TypeScript), Tailwind, Recharts | Matches your React experience; SSR helps player pages get indexed |
| API | FastAPI on Uvicorn | One language for API, simulator and ML; native WebSockets |
| Realtime | FastAPI WebSockets + Redis pub/sub | Pub/sub lets rooms work across more than one API instance |
| Database | Postgres 16 with `pg_trgm` | Relational stats plus fuzzy player search |
| Pipeline | Python, DuckDB, Parquet; GitHub Actions weekly | Aggregates \~20,000 matches on a laptop |
| ML | LightGBM, scikit-learn | Fast to train on small tabular data |
| Testing | pytest, Playwright, Locust | Unit, end-to-end and auction load tests |
| Hosting | Vercel (web), Render or Fly.io (API + Redis), Neon (Postgres) | Free tiers; check WebSocket limits before choosing |

## API and realtime protocol

REST for everything read-heavy; one WebSocket per auction room for live state.

**REST (FastAPI, `/api/v1`)**

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/players?q=&country=&role=&format=` | Search |
| GET | `/players/{id}` | Profile with format, season and phase stats |
| GET | `/compare?a={id}&b={id}&format=` | Head-to-head |
| GET | `/venues/{id}` | Venue page |
| POST | `/xi/spin` | Returns seeded spins for a format |
| POST | `/xi/series` | Body: picks + seed → runs 5 matches, returns results id |
| GET | `/xi/challenge/{slug}` | Load a shared challenge |
| POST | `/rooms` | Create auction room, returns code |
| POST | `/rooms/{code}/join` | Join with nickname, claim franchise |
| POST | `/rooms/{code}/season` | Simulate season for a finished auction |

**WebSocket `/ws/rooms/{code}`**

- Client → server: `bid {player_id, amount}`, `ready`, `chat {text}`, host-only `start`, `pause`, `next_set`.
- Server → client: `state` (full snapshot on join), `player_up {player, base, fair_price}`, `bid_accepted {franchise, amount, ends_at}`, `bid_rejected {reason}`, `sold {player, franchise, amount}`, `unsold`, `phase {accelerated | ended}`.
- `ends_at` is a server timestamp; clients render the countdown from it, so a laggy client never decides the outcome.
- Reconnect: client re-joins with its franchise token and receives a fresh `state` snapshot.

## Milestones and build order

Six milestones over about 12 weeks; each ends in something you can demo. The week counts are my estimate for part-time work alongside your job, so stretch them if needed.

&#91;embedded content: build roadmap · 6 milestones, \~12 weeks part-time\]

The simulator comes before both game modes because the XI series and the post-auction season are just two different callers of it.

**Start here (Milestone 1 tasks)**

- [ ] Create repo with `/web`, `/api`, `/pipeline` folders and a docker-compose for Postgres + Redis
- [ ] Download Cricsheet JSON (all men's matches) and write the parser to one-row-per-delivery Parquet
- [ ] Build `players`, `player_format_stats`, `player_season_stats`, `player_phase_stats` in DuckDB
- [ ] Spot-check 10 players' career totals against Cricsheet's own match files
- [ ] Load aggregates into Postgres; write the first `/players` endpoint
- [ ] Start `legends.csv` with 50 pre-2001 players and a source column

## Risks, open questions and flagged assumptions

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Simulator results feel unrealistic | Undermines both XI and season modes | Build and validate it first (Milestone 2) against real score distributions |
| Legends data takes longer than planned | XI mode limited to post-2001 | Launch with modern eras; add legends in batches of 50 |
| Auction race conditions | Two franchises win one player | Atomic Redis updates, server-owned clock, load test with 10 bots + 10 humans |
| Scope: three products at once | Nothing finishes | Ship in the milestone order below; each milestone is demo-able on its own |
| Auction dataset licensing unclear | Can't publish the price model | Check Kaggle licenses; fall back to manually compiled recent seasons |

**Open questions**

- [ ] Exact IPL bid increment slabs and the mega-auction purse figure: confirm from the official player regulations.
- [ ] Which Kaggle auction dataset to use, and its license.
- [ ] App name (Gully11 is a placeholder).
- [ ] Free hosting limits for WebSockets on the chosen platform.

**Flagged as my design choices, not from any source** (so you can defend them in an interview): the log5 + shrinkage simulator design, the 15 s / 10 s timer values, bot personalities, LightGBM for the price model, money stored in lakh, the 5% validation threshold, initials avatars instead of photos.

Commands and prompts to start building with Spec Kit: Spec Kit kickoff
