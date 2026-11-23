# Match simulator (Milestone 2)

Code: `api/src/gully_api/sim/`. Shared by the XI series and the post-auction season.

## How a ball is decided

1. **Extras**: wide or no-ball from the bowler's own rates (shrunk toward the league).
2. **Outcome** from {W, 0, 1, 2, 3, 4, 6} by the log5 / odds-ratio method:
   `p_i ∝ (bat_i / L_bat_i) × (bowl_i / L_bowl_i) × E_i × calibration_i`.
   `L` are the baselines player rates are measured against; `E` is the environment
   being simulated (for example IPL 2024–26 scoring levels).
3. **Chase intent**: required runs vs. par for the resources left. Behind: more
   boundaries and some extra risk. Ahead: protect wickets, rotate strike.
4. **Byes** on otherwise-dot balls; wicket kind and fielder; strike rotation.
5. **Match conditions**: one seeded draw per match scales boundary rates
   (pitch, ground size, dew).

The bowling plan picks each over from the designated bowlers by phase quality.
It respects the quota (4 overs in T20, 10 in ODI), never gives a bowler two
overs in a row, and keeps the two best death bowlers' last overs for the death.

## Player ratings

- **Context-adjusted.** Each player's outcome counts are compared with what an
  average player would have produced in the same competitions, years and
  phases (`exp_*` columns in `player_phase_stats`).
- **Two-level shrinkage.** The overall ratio is pulled toward a role prior over
  250 batting / 300 bowling balls. Each phase is then pulled toward the
  overall ratio over 150 balls.
- **Role priors are measured, not guessed.** They are the observed/expected
  ratios of low-sample players by role. Examples: tail-enders' wicket rate is
  1.4× average, and other unproven batters 1.27×. See `priors` in
  `sim/data/base_rates.json`.
- **Legends** (no ball-by-ball data) are estimated from career average and
  strike rate by tilting the league distribution, and are marked `estimated`.
- **League strength.** A rating against a league's own average isn't
  comparable across leagues, because beating the BPL average is easier than
  beating the IPL's. The pipeline models each player's outcomes in
  competition c as rating × strength[c] × league-average expectation, per
  role and outcome. It fits both by alternating updates: players who appear in
  several competitions link them, and priors are 300 balls per player and
  2,000 per competition. Strength is anchored at 1 for the IPL (T20) and for
  full-member internationals (ODI). Internationals are split into full,
  mixed and associate contexts. The `lexp_*` columns hold these adjusted
  expectations, which the simulator uses by default. The factors are in the
  DuckDB table `league_strength`. For example, an average Blast batter rates
  about 20% below an average IPL batter for six-hitting and gets out more.
  Strength is per competition, not per year, and is fitted on all data, which
  leaks slightly into the point-in-time validation.
- **Recent form.** `player_phase_form` holds recency-weighted counts. Each
  year before `as_of` is weighted 0.5^((as_of − 1 − year) / half_life). The
  pipeline builds a grid of as_of years (2024 to the current year) and half-lives
  (0 = none, 1, 2, 4), so validation can rate players as they stood before each
  season. Postgres gets only the current ratings, with the 4-year half-life.

## Data files (regenerate after a data refresh)

| File | Made by | Contents |
| --- | --- | --- |
| `sim/data/base_rates.json` | `gully-pipeline simbase` | Environment outcome counts, extras, wicket kinds, first-innings score distribution, remaining-runs table for win probability, role priors |
| `sim/data/calibration.json` | `scripts/validate_sim.py --fit` | Per-phase outcome multipliers and the conditions spread, fitted by replaying real matches |

## Validation (IPL, fit on 2024–25, tested on 2026)

`uv run python scripts/validate_sim.py --fit 2024 2025 --years 2026 2026`

The replay uses the real squads and toss outcome. Batting order and bowlers
come from pre-match information only, and players are rated as they stood
before each season (form ratings, 4-year half-life). 20 simulations per
match. Results on 72 matches neither the ratings nor the calibration had seen:

| Metric | Real | Sim | Diff |
| --- | --- | --- | --- |
| First-innings total, mean | 195.1 | 190.5 | −2.4% (pass, target ±5%) |
| First-innings total, sd | 36.8 | 37.6 | +1.9% |
| Boundaries per legal ball | 0.225 | 0.219 | −2.6% (pass) |
| Wickets per legal ball | 0.053 | 0.052 | −1.1% (pass) |
| Extras per innings | 8.9 | 9.1 | +2.8% |
| Chasing side wins | 62.5% | 51.7% | 2024–25 real was ~51%; one season is noisy |

### Does it pick winners? (2024–26, 213 matches, 40 sims each)

| Ratings | Brier (coin flip 0.25) | Picks winner |
| --- | --- | --- |
| Career, includes the replayed matches | 0.260 | 53.2% |
| Form as of season, no decay | 0.279 | 49.0% |
| Form, half-life 1 / 2 / 4 years | 0.280 / 0.286 / 0.287 | 49.3% / 48.5% / 48.3% |
| Form, IPL-only data, half-life 0 / 4 | 0.270 / 0.263 | 55.8% / 55.5% |
| **Form 4y, league-adjusted (default)** | **0.268** | **52.0%** (54.5% in a second run) |
| Form 4y, same calibration, no league adjustment | 0.277 | 46.8% (49.8%) |

What this shows:

- **Recency weighting doesn't measurably help.** All half-lives are within
  noise of each other. The 4-year default is a judgment call for face
  validity, since old form shouldn't count fully, not a measured gain.
- **Ratings mixed across leagues carried no predictive signal** until the
  league-strength adjustment. Same-league (IPL-only) ratings pick about 56%.
  The adjustment recovers most of that (52–55%) and improves Brier while
  keeping every player rated, including those with little or no IPL data.
- **Rating damping (not enabled).** Raising player ratios to a power below 1
  pulls Brier toward 0.25 (α = 0.4: 0.257), but the pick rate moves within
  noise. Tuning it on these 213 matches would be in-sample, and the game needs
  strong squads to look strong, so it stays off.
- **The simulator is overconfident.** Player ratings spread the per-match win
  chance with an sd of 0.144, while role structure alone gives 0.022. Brier
  stays above 0.25 because that spread isn't backed by enough signal.
- **An earlier version of this check leaked the result in reverse.** It built
  line-ups from the scorecard, so teams that chased easily had their unused
  middle order placed below the tail. That produced a −0.25 correlation with
  real results. Line-ups now use pre-match information only.

Without calibration the simulator already landed within 1.5% on mean score,
but 4–8% high on boundaries and wickets. League-average players reproduce the
environment exactly (unit-tested), so the excess comes from the player ratings.
Careers built partly in weaker competitions make strong players look a bit
stronger with bat and ball.

## Tests (beta)

`simulate_test` plays two innings each inside 450 overs, on the same ball-by-ball
model:

- **Phases:** the three labels mean the age of the ball in Tests: new (overs 0–14),
  middle (15–79) and old (80+). Players get Test phase ratings like any other format.
- **Pitch wear:** per-innings wicket and scoring factors are measured from real
  Tests. Balls per wicket fall from 65 to 61, 55 and 53 across the four innings.
- **Declarations (design choices):**
  - first innings at 600, or 500 after 140 overs
  - second innings once 250 ahead with 450+ on the board
  - third innings when the target needs about 3.6 an over in the time left, or the
    lead passes 450
- **Follow-on:** enforced at a 200-run lead when 150+ overs remain.
- **Fourth-innings intent:** chasers go for gettable targets and block for the draw
  when the rate passes 5 an over, or 4 with six wickets down.
- **Weather (design choice):** with probability p a match loses up to 200 overs. p is
  fitted to the real draw rate.
- **Calibration:** per-phase outcome multipliers, fitted like the IPL's.
  `scripts/validate_test_sim.py --fit 2023 2024 --years 2025 2026`

Holdout, 63 Tests from 2025–26:

| Innings | Runs | Overs |
| --- | --- | --- |
| 1st | +6% | +6% |
| 2nd | −2% | +2% |
| 3rd | −11% | −8% |
| 4th | +2% | +2% |

The draw rate came out at 14% against a real 8%. The fit seasons had 9.6% draws,
and two seasons of 60–80 Tests make that noisy. The weather probability also sat
at the top of the fitted grid (0.6). Treat the draw rate as approximate.

## Legends

`from_legend` builds a profile from career figures (`legends` table, Wikipedia). Most
pre-2001 strike rates were never recorded, so a missing one is estimated: the format's
league-average rate, nudged by batting average. Bradman comes out at about 59. Such
players are marked `estimated` and `sr_estimated`. Bowling reproduces career average
and economy (McGrath 21.6 at 2.49).

## Known gaps / next steps

- **Still overconfident.** Brier is about 0.27 against a coin flip's 0.25:
  the per-match win chances spread wider than the real signal supports.
  Opponent adjustment within a competition (a full member playing an
  associate) and better links for associate players, who rarely play
  elsewhere, are the next levers. Rating damping is the quick fix if needed.
- Calibration is per environment. Only `IPL_recent` is fitted; other
  environments run uncalibrated until fitted on their own matches.
- Free hits and DLS are not modelled yet.

## Matchups (pace / spin, batting hand)

Batting hand and bowling style come from each player's Wikipedia infobox
(`gully-pipeline styles`, CC BY-SA): known for 99% of IPL balls since 2015 and 89%
of all T20 balls. The pipeline's `player_matchups` table holds, per player, how a
batter did against pace and against spin, and a bowler against left- and
right-handers: observed counts next to what an average player got in the same
matchup, competition, year and phase.

Each ball multiplies the outcome odds by two factors (both 1 when unknown): the
batter's record against this kind of bowling relative to their record overall,
and the bowler's against this batting hand relative to theirs. A split is pulled
toward the player's overall record with 1,500 balls of prior, so only big samples
move: Kohli's record off spin (half the usual dismissal rate over 7,500 balls)
counts; a 60-ball split doesn't.

What it buys: realism in the individual battles more than better results. On
2024–26 IPL balls the batter-v-bowler model, rated only on earlier data, predicts
the actual outcome slightly better with matchups (log loss -0.04% overall, -0.15%
on balls against spin, no kind of ball worse; `scripts/matchup_check.py`). With
weaker shrinkage (100–400 balls) it was slightly worse: splits are noisy.
Match-level prediction is unchanged (`validate_sim.py`, Brier within noise).

## Calibration by phase and bowling kind; in-season form

**Calibration** multiplies outcome odds so simulated IPL matches reproduce real
ones. It is now fitted per phase *and* bowling kind ("death:pace", "middle:spin",
...) where a cell has 1,000+ real balls, falling back to per phase. Per phase
alone left pace at the death 6% too expensive (1.83 runs a ball v 1.73 real,
2024-26) and spin at the death taking too many wickets, because one death
multiplier had to serve both. Fitted on 2024-25 and tested on 2026 (unseen),
death-over pace moved from 1.84 to 1.78 runs a ball (2026 real: 1.68); the rest
of that gap is 2026 itself, a lower-scoring death and higher-scoring powerplay
than the years it was fitted on. `validate_sim.py` prints the table by phase and kind.

**In-season form.** Ratings as of a season's start miss breakouts and slumps
during it. `validate_sim.py --in-season W` rates each match on form before the
season plus every T20 ball the player played earlier that year (weight W, judged
against the previous year's league averages: no look-ahead). Scored ball by ball
on IPL 2024-26 (`scripts/rating_check.py`):

| ratings | log loss / ball | batter SR correlation | mean SR miss |
|---|---|---|---|
| start of season | 1.4950 | 0.52 | 13.6 |
| + season so far, x1 | **1.4945** | **0.66** | **12.2** |
| + season so far, x2 | 1.4959 | 0.71 | 11.4 |
| + season so far, x3 | 1.4982 | 0.74 | 10.9 |

Weight 1 improves both; heavier weights track batters' strike rates better but
predict individual balls worse (they overreact to small samples). Match-level
Brier can't tell these apart: 213 results are too noisy, and the engine is still
no better than a coin flip at naming winners (see below).

**In the app:** auction seasons now rate players on current form
(`player_phase_form`: recency-weighted, half-life 4 years, this year at full
weight) instead of their whole career, which tracked breakouts worst of all. The
XI Builder keeps career ratings: it drafts by era, and form would fade a 2010
great toward average.

## Super over

A tied T20 (IPL, T20I) goes to a super over; ODI ties stand (pass
`super_over=True/False` to `simulate_match` to override). ICC playing conditions:

- The side that batted second bats first. One over, two wickets (three batters).
- Each captain sends in three batters, picked from their death-overs hitting
  (runs per ball minus twice the dismissal rate), and one bowler, picked by the
  same value used for bowling changes. A better captain picks closer to the best
  option (the bowling-change temperature).
- Batters swing hard: aggression 1.9 setting a total; chasing, scaled by the
  rate needed (2 a ball is par). With average sides that gives about 12 runs per
  super over, a little under the IPL's real average, where teams send in their best.
- A tied super over is played again with the other side batting first; batters
  dismissed and bowlers used in an earlier one sit out. After four tied super
  overs (never seen in practice) the side with more boundaries in the match wins.
- Super-over balls are in the commentary as innings 3, 4, ... and their cards in
  `super_overs`; they have no win-probability line and don't count toward season caps.


## Design choices (not from any source)

log5 combination, shrinkage strengths, chase-intent exponents, conditions
factor, the calibration step, and keeping death bowlers' last overs.

## Captaincy

`gully-pipeline captains` reads Wikipedia captain lists (IPL + each Test nation, CC BY-SA) into `api/src/gully_api/sim/data/captains.csv`. A captain's rating (0..1) = experience x shrunk win rate (`sim/captaincy.py`); it drives the toss call and bowling changes only, never batting or bowling skill. Measured edge of a 0.9 captain over none: T20 +1.5 pts, ODI +4.4, Test ~+2.
