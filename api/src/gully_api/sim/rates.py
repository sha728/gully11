"""League/environment base rates for the simulator (from data/base_rates.json).

Outcome vectors are always ordered as ``OUTCOMES``: wicket, then runs off the
bat. Extras (wides, no-balls, byes) are modelled separately per delivery.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import cache
from pathlib import Path

OUTCOMES = ("W", "0", "1", "2", "3", "4", "6")
RUNS = (0, 0, 1, 2, 3, 4, 6)  # runs off the bat for each outcome
W, DOT = 0, 1
PHASES = ("PP", "middle", "death")

DATA_PATH = Path(__file__).parent / "data" / "base_rates.json"
CALIBRATION_PATH = Path(__file__).parent / "data" / "calibration.json"

# Each environment belongs to a family (T20, ODI or Test): the all-time environment
# whose baseline player ratings in that family are measured against.


def counts_to_vector(c: dict) -> list[float]:
    """Raw counts (as in player_phase_stats / base_rates.json) -> outcome counts.

    ``dots`` include wicket balls, so the wicket count is moved out of the dot
    bucket. Returned values are counts, not yet normalised.
    """
    wk = c["wickets"]
    return [wk, max(c["dots"] - wk, 0), c["ones"], c["twos"], c["threes"], c["fours"], c["sixes"]]


def normalise(v: list[float]) -> list[float]:
    s = sum(v)
    return [x / s for x in v]


def _dist(d: dict[str, int]) -> tuple[tuple, tuple]:
    keys = tuple(d)
    total = sum(d.values())
    return keys, tuple(d[k] / total for k in keys)


@dataclass(frozen=True)
class Env:
    """Everything the engine needs about where/when a match is played."""
    name: str
    overs: int
    phase_starts: tuple[tuple[int, str], ...]
    bat_env: dict[str, list[float]]     # E: target outcome rates (batter view)
    bat_base: dict[str, list[float]]    # L: baseline player batting rates are measured against
    bowl_base: dict[str, list[float]]   # L for bowling rates
    wide_rate: dict[str, float]         # per legal ball
    noball_rate: dict[str, float]
    wide_runs: tuple[tuple, tuple]      # (values, probs)
    bye_prob: float                     # P(byes | otherwise clean dot ball)
    bye_runs: tuple[tuple, tuple]
    wicket_kinds: tuple[tuple, tuple]
    first_innings: dict
    res_mean: list[list[float]]         # remaining runs, [legal balls bowled][wickets down]
    res_sd: list[list[float]]
    priors: dict[str, tuple]            # shrinkage targets for low-sample players
    prior_bat_balls: int
    prior_bowl_balls: int
    # Per-phase outcome multipliers fitted by replaying real matches in this
    # environment (scripts/validate_sim.py --fit). 1.0 everywhere if not fitted.
    calibration: dict[str, tuple] = None  # type: ignore[assignment]
    # Spread (log scale) of the per-match conditions factor on boundary rates.
    conditions_sd: float = 0.0
    family: str = "T20"                 # T20 / ODI / Test: which player stats apply
    test_shape: dict | None = None      # real per-innings averages (Tests only)
    # Tests: (probability a match loses time, most overs it can lose); fitted.
    test_weather: tuple[float, float] = (0.0, 0.0)

    def with_weather(self, p: float, max_lost: float) -> "Env":
        from dataclasses import replace
        return replace(self, test_weather=(p, max_lost))

    @property
    def is_test(self) -> bool:
        """Tests have no over limit (overs == 0): two innings each, declarations."""
        return self.overs == 0

    def __post_init__(self):
        if self.calibration is None:
            object.__setattr__(self, "calibration", {p: (1.0,) * 7 for p in PHASES})

    def with_calibration(self, calibration: dict[str, tuple] | None,
                         conditions_sd: float | None = None) -> "Env":
        from dataclasses import replace
        return replace(self, calibration=calibration or {p: (1.0,) * 7 for p in PHASES},
                       conditions_sd=self.conditions_sd if conditions_sd is None else conditions_sd)

    @property
    def max_overs_per_bowler(self) -> int:
        return self.overs // 5

    def phase(self, over: int) -> str:
        name = self.phase_starts[0][1]
        for start, label in self.phase_starts:
            if over >= start:
                name = label
        return name

    def remaining(self, balls: int, wickets: int) -> tuple[float, float]:
        """(mean, sd) runs still to come in an uninterrupted innings."""
        if balls >= self.overs * 6 or wickets >= 10:
            return 0.0, 0.0
        return self.res_mean[balls][wickets], self.res_sd[balls][wickets]


@cache
def _raw() -> dict:
    return json.loads(DATA_PATH.read_text())


def env_names() -> list[str]:
    return list(_raw()["envs"])


@cache
def load_env(name: str) -> Env:
    raw = _raw()
    if name not in raw["envs"]:
        raise ValueError(f"Unknown environment {name!r}; choose from {env_names()}")
    e = raw["envs"][name]
    overs = e["overs"]
    family = e.get("family") or {20: "T20", 50: "ODI"}[overs]
    base = raw["envs"][family]
    # Remaining-runs tables (win probability, chase intent) exist for limited overs only.
    res = raw["resources"].get(str(overs), {"env": family, "mean": [], "sd": []})
    # Rescale the all-time remaining-runs table to this environment's scoring level.
    scale = e["first_innings"]["mean"] / raw["envs"][res["env"]]["first_innings"]["mean"]

    def vecs(env, role):
        return {p: normalise(counts_to_vector(env["phases"][p][role])) for p in PHASES}

    bowl = {p: e["phases"][p]["bowl"] for p in PHASES}
    x = e["extras"]
    return Env(
        name=name,
        overs=overs,
        phase_starts=tuple((s, lbl) for s, lbl in raw["phases"][str(overs)]),
        bat_env=vecs(e, "bat"),
        bat_base=vecs(base, "bat"),
        bowl_base=vecs(base, "bowl"),
        wide_rate={p: bowl[p]["wide_balls"] / bowl[p]["balls"] for p in PHASES},
        noball_rate={p: bowl[p]["noball_balls"] / bowl[p]["balls"] for p in PHASES},
        wide_runs=_dist({int(k): v for k, v in x["wide_runs"].items()}),
        bye_prob=sum(x["bye_runs"].values()) / x["clean_dots"],
        bye_runs=_dist({int(k): v for k, v in x["bye_runs"].items()}),
        wicket_kinds=_dist(x["wicket_kinds"]),
        first_innings=e["first_innings"],
        res_mean=[[m * scale for m in row] for row in res["mean"]],
        res_sd=[[s * scale for s in row] for row in res["sd"]],
        priors={k: tuple(v) for k, v in raw["priors"][family].items()},
        family=family,
        test_shape=e.get("test_shape"),
        test_weather=tuple(_calibration().get(name, {}).get("weather", (0.0, 0.0))),
        prior_bat_balls=raw["prior_thresholds"]["bat_balls"],
        prior_bowl_balls=raw["prior_thresholds"]["bowl_balls"],
        calibration=_calibration().get(name, {}).get("multipliers"),
        conditions_sd=_calibration().get(name, {}).get("conditions_sd", 0.0),
    )


def _calibration() -> dict:
    if not CALIBRATION_PATH.exists():
        return {}
    data = json.loads(CALIBRATION_PATH.read_text())
    return {env: {"multipliers": {p: tuple(v) for p, v in c["multipliers"].items()},
                  "conditions_sd": c.get("conditions_sd", 0.0),
                  "weather": (c["weather"]["p"], c["weather"]["max_lost"]) if "weather" in c else (0.0, 0.0)}
            for env, c in data.items()}
