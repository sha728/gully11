"""Player profiles for the simulator.

A profile holds, per phase, a batting and a bowling outcome distribution plus
wide/no-ball rates. Two ways to build one:

* ``from_phase_rows`` - from ball-by-ball phase counts (player_phase_stats),
  with two-level Bayesian shrinkage:
    1. the player's overall rate vector is pulled toward a role prior
       (league average, or a weaker "tail-ender"/"part-timer" level);
    2. each phase is pulled toward that overall vector scaled to the phase.
  A player with 30 balls therefore looks close to the prior, not like a star.
* ``from_career`` - for legends with only career average / strike rate:
  tilt the league distribution until it reproduces those numbers. Marked
  ``estimated``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .rates import OUTCOMES, PHASES, RUNS, Env, counts_to_vector, normalise

# Shrinkage strengths, in balls (design choices; tune with validation).
K_OVERALL_BAT = 250
K_OVERALL_BOWL = 300
K_PHASE = 150
# Prior ratio vectors (W, 0, 1, 2, 3, 4, 6) come from the data via env.priors:
# observed / context-expected outcomes for players with small samples, by role.
#   tail_bat        - specialist bowlers batting
#   unproven_bat    - everyone else batting (low-sample batters are below average)
#   part_timer_bowl - batters and keepers bowling
#   unproven_bowl   - bowlers and all-rounders with little bowling data
WICKET_ROLES = {"BOWL", "AR"}


def bat_prior(role: str, env: Env) -> tuple:
    return env.priors["tail_bat" if role == "BOWL" else "unproven_bat"]


def bowl_prior(role: str, env: Env) -> tuple:
    return env.priors["unproven_bowl" if role in WICKET_ROLES else "part_timer_bowl"]


@dataclass
class Profile:
    id: str
    name: str
    role: str
    bat: dict[str, list[float]]            # phase -> probabilities over OUTCOMES
    bowl: dict[str, list[float]]
    wide: dict[str, float]
    noball: dict[str, float]
    balls_bowled: int = 0                  # career sample, used to pick bowlers
    balls_faced: int = 0
    estimated: bool = False
    meta: dict = field(default_factory=dict)

    def bat_ratio(self, phase: str, env: Env) -> list[float]:
        return [p / b for p, b in zip(self.bat[phase], env.bat_base[phase])]

    def bowl_ratio(self, phase: str, env: Env) -> list[float]:
        return [p / b for p, b in zip(self.bowl[phase], env.bowl_base[phase])]


def _shrink(counts: dict[str, list[float]], exp: dict[str, list[float]],
            base: dict[str, list[float]], prior: tuple, k_overall: float) -> dict[str, list[float]]:
    """Two-level shrinkage in ratio space.

    ``counts`` are observed outcome counts per phase; ``exp`` the counts an average
    player would have produced in the same contexts. Ratio = observed / expected,
    pulled toward the role prior overall, then each phase pulled toward that
    overall ratio. Output: probabilities relative to the family baseline ``base``.
    """
    observed = [0.0] * 7
    expected = [0.0] * 7
    for p in PHASES:
        if p in counts:
            observed = [o + c for o, c in zip(observed, counts[p])]
            expected = [e + x for e, x in zip(expected, exp[p])]
    mean_base = [sum(base[p][i] for p in PHASES) / len(PHASES) for i in range(7)]
    ratio = [
        (observed[i] + k_overall * mean_base[i] * prior[i]) / (expected[i] + k_overall * mean_base[i])
        for i in range(7)
    ]
    out = {}
    for p in PHASES:
        c = counts.get(p, [0.0] * 7)
        x = exp.get(p, [0.0] * 7)
        m = [K_PHASE * base[p][i] for i in range(7)]
        phase_ratio = [(c[i] + m[i] * ratio[i]) / (x[i] + m[i]) for i in range(7)]
        out[p] = normalise([base[p][i] * phase_ratio[i] for i in range(7)])
    return out


_CATS = ("wickets", "dots", "ones", "twos", "threes", "fours", "sixes")


def _expected(r: dict, base: list[float], league_adjusted: bool = True) -> list[float]:
    """Expected counts for a phase row. Preference: league-adjusted (lexp_*: league
    average x competition strength, so ratings from different leagues share one
    scale), then plain context baseline (exp_*), then balls x family baseline."""
    for prefix in (("lexp_", "exp_") if league_adjusted else ("exp_",)):
        if r.get(f"{prefix}dots") is not None:
            return counts_to_vector({k: r[f"{prefix}{k}"] for k in _CATS})
    return [r["balls"] * b for b in base]


def from_phase_rows(player: dict, rows: list[dict], env: Env, league_adjusted: bool = True) -> Profile:
    """Build a profile from ``players`` row + its ``player_phase_stats`` rows for the
    format family matching ``env`` (T20 stats for T20 sims, ODI stats for ODIs)."""
    bat_c, bat_x, bat_n, bowl_c, bowl_x, bowl_n = {}, {}, {}, {}, {}, {}
    wides = noballs = exp_wides = exp_noballs = 0.0
    for r in rows:
        p = r["phase"]
        if p not in PHASES:
            continue
        if r["role"] == "bat":
            bat_c[p], bat_n[p] = counts_to_vector(r), r["balls"]
            bat_x[p] = _expected(r, env.bat_base[p], league_adjusted)
        else:
            bowl_c[p], bowl_n[p] = counts_to_vector(r), r["balls"]
            bowl_x[p] = _expected(r, env.bowl_base[p], league_adjusted)
            wides += r.get("wide_balls") or 0
            noballs += r.get("noball_balls") or 0
            ew, en = r.get("exp_wide_balls"), r.get("exp_noball_balls")
            exp_wides += ew if ew is not None else r["balls"] * env.wide_rate[p]
            exp_noballs += en if en is not None else r["balls"] * env.noball_rate[p]
    role = player["role"]
    faced, bowled = sum(bat_n.values()), sum(bowl_n.values())

    # Wides/no-balls: observed vs context-expected, shrunk over ~300 balls of prior.
    def extra_rate(count: float, exp_count: float, league: dict[str, float]) -> dict[str, float]:
        k = 300 * sum(league.values()) / len(league)
        ratio = (count + k) / (exp_count + k)
        return {p: league[p] * ratio for p in PHASES}

    return Profile(
        id=player["id"],
        name=player["name"],
        role=role,
        bat=_shrink(bat_c, bat_x, env.bat_base, bat_prior(role, env), K_OVERALL_BAT),
        bowl=_shrink(bowl_c, bowl_x, env.bowl_base, bowl_prior(role, env), K_OVERALL_BOWL),
        wide=extra_rate(wides, exp_wides, env.wide_rate),
        noball=extra_rate(noballs, exp_noballs, env.noball_rate),
        balls_bowled=bowled,
        balls_faced=faced,
    )


# ------------------------------------------------------------------ legends

def _tilt(base: list[float], w_rate: float, runs_per_ball: float) -> list[float]:
    """Set P(W) = w_rate and tilt the run outcomes q_k -> q_k * t**k so the
    expected runs per ball equals ``runs_per_ball``. Solved by bisection on log t."""
    q = normalise(base[1:])
    target = runs_per_ball / (1 - w_rate)  # runs per non-wicket ball
    runs = RUNS[1:]

    def mean_runs(log_t: float) -> float:
        wts = [qk * math.exp(log_t * r) for qk, r in zip(q, runs)]
        s = sum(wts)
        return sum(w * r for w, r in zip(wts, runs)) / s

    lo, hi = -5.0, 5.0
    for _ in range(80):
        mid = (lo + hi) / 2
        if mean_runs(mid) < target:
            lo = mid
        else:
            hi = mid
    wts = normalise([qk * math.exp(lo * r) for qk, r in zip(q, runs)])
    return [w_rate] + [(1 - w_rate) * x for x in wts]


def _phase_shape(env: Env, base: dict[str, list[float]], overall: list[float]) -> dict:
    """Spread an overall vector across phases using the league's phase shape."""
    mean_base = [sum(base[p][i] for p in PHASES) / len(PHASES) for i in range(7)]
    ratio = [o / m for o, m in zip(overall, mean_base)]
    return {p: normalise([base[p][i] * ratio[i] for i in range(7)]) for p in PHASES}


def from_career(id: str, name: str, role: str, env: Env, *,
                bat_avg: float | None, bat_sr: float | None,
                bowl_avg: float | None = None, bowl_econ: float | None = None) -> Profile:
    """Estimated profile for players without ball-by-ball data (pre-2001 legends).

    bat: dismissal rate = 1 / balls-per-dismissal, where balls-per-dismissal =
    avg / (sr / 100). bowl: wicket rate = econ / (6 * avg). Missing values fall
    back to the data-derived prior for the player's role.
    """
    base_bat = [sum(env.bat_base[p][i] for p in PHASES) / 3 for i in range(7)]
    base_bowl = [sum(env.bowl_base[p][i] for p in PHASES) / 3 for i in range(7)]
    league_rpb = sum(p * r for p, r in zip(base_bat, RUNS))

    if bat_avg and bat_sr:
        rpb = bat_sr / 100
        bat_overall = _tilt(base_bat, min(rpb / bat_avg, 0.5), rpb)
    else:
        bat_overall = normalise([b * m for b, m in zip(base_bat, bat_prior(role, env))])
    if bowl_avg and bowl_econ:
        rpb = bowl_econ / 6
        bowl_overall = _tilt(base_bowl, min(rpb / bowl_avg, 0.5), rpb)
    else:
        bowl_overall = normalise([b * m for b, m in zip(base_bowl, bowl_prior(role, env))])

    return Profile(
        id=id, name=name, role=role,
        bat=_phase_shape(env, env.bat_base, bat_overall),
        bowl=_phase_shape(env, env.bowl_base, bowl_overall),
        wide=dict(env.wide_rate), noball=dict(env.noball_rate),
        balls_bowled=10_000 if (bowl_avg and role in WICKET_ROLES) else 0,
        estimated=True,
        meta={"league_runs_per_ball": league_rpb},
    )


def from_legend(row: dict, env: Env) -> Profile:
    """Profile for a pre-2001 great from the ``legends`` table (career figures from
    Wikipedia). Strike rates weren't recorded for most of that era, so a missing one
    is estimated: the format's league-average strike rate, nudged by batting average
    ((avg / league avg) ** 0.25, clamped to 0.7–1.15). Marked ``estimated``."""
    base = [sum(env.bat_base[p][i] for p in PHASES) / 3 for i in range(7)]
    league_rpb, league_w = expected(base)
    bat_avg, bat_sr = row.get("bat_avg"), row.get("bat_sr")
    if bat_avg and not bat_sr:
        quality = min(max((bat_avg / (league_rpb / league_w)) ** 0.25, 0.7), 1.15)
        bat_sr = 100 * league_rpb * quality
    prof = from_career(row["id"], row["name"], row["role"], env, bat_avg=bat_avg, bat_sr=bat_sr,
                       bowl_avg=row.get("bowl_avg") if (row.get("wickets") or 0) >= 10 else None,
                       bowl_econ=row.get("bowl_econ") if (row.get("wickets") or 0) >= 10 else None)
    prof.meta.update(legend=True, sr_estimated=not row.get("bat_sr"))
    return prof


def expected(vector: list[float]) -> tuple[float, float]:
    """(runs per ball, wicket probability) for an outcome vector."""
    return sum(p * r for p, r in zip(vector, RUNS)), vector[0]


__all__ = ["Profile", "from_phase_rows", "from_career", "expected", "OUTCOMES"]
