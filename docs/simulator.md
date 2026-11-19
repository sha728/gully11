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

## Known gaps / next steps

- **Still overconfident.** Brier is about 0.27 against a coin flip's 0.25:
  the per-match win chances spread wider than the real signal supports.
  Opponent adjustment within a competition (a full member playing an
  associate) and better links for associate players, who rarely play
  elsewhere, are the next levers. Rating damping is the quick fix if needed.
- Calibration is per environment. Only `IPL_recent` is fitted; other
  environments run uncalibrated until fitted on their own matches.
- Free hits, super overs (ties stand as ties), DLS and Test matches are not
  modelled yet.

## Design choices (not from any source)

log5 combination, shrinkage strengths, chase-intent exponents, conditions
factor, the calibration step, and keeping death bowlers' last overs.
