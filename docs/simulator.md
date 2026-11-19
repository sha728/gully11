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

## Data files (regenerate after a data refresh)

| File | Made by | Contents |
| --- | --- | --- |
| `sim/data/base_rates.json` | `gully-pipeline simbase` | Environment outcome counts, extras, wicket kinds, first-innings score distribution, remaining-runs table for win probability, role priors |
| `sim/data/calibration.json` | `scripts/validate_sim.py --fit` | Per-phase outcome multipliers and the conditions spread, fitted by replaying real matches |

## Validation (IPL, fit on 2024–25, tested on 2026)

`uv run python scripts/validate_sim.py --fit 2024 2025 --years 2026 2026`

The replay uses the real XIs, batting orders, bowlers and toss outcome,
20 simulations per match. Results on 72 matches the calibration never saw:

| Metric | Real | Sim | Diff |
| --- | --- | --- | --- |
| First-innings total, mean | 195.1 | 190.3 | −2.5% (pass, target ±5%) |
| First-innings total, sd | 36.8 | 37.4 | +1.6% |
| Boundaries per legal ball | 0.225 | 0.219 | −2.8% (pass) |
| Wickets per legal ball | 0.053 | 0.053 | +0.5% (pass) |
| Extras per innings | 8.9 | 9.3 | +4.7% |
| Chasing side wins | 62.5% | 52.2% | 2024–25 real was ~51%; one season is noisy |

Without calibration the simulator already landed within 1.5% on mean score,
but 4–8% high on boundaries and wickets. League-average players reproduce the
environment exactly (unit-tested), so the excess comes from the player ratings.
Careers built partly in weaker competitions make strong players look a bit
stronger with bat and ball.

## Known gaps / next steps

- **Team strength signal is weak.** Simulated vs. real win % per team-season
  correlates at about 0 (n = 30, noisy). Ratings are career-long. Recency
  weighting, and ratings adjusted for opposition strength across competitions,
  are the next improvements.
- Calibration is per environment. Only `IPL_recent` is fitted; other
  environments run uncalibrated until fitted on their own matches.
- Free hits, super overs (ties stand as ties), DLS and Test matches are not
  modelled yet.

## Design choices (not from any source)

log5 combination, shrinkage strengths, chase-intent exponents, conditions
factor, the calibration step, and keeping death bowlers' last overs.
