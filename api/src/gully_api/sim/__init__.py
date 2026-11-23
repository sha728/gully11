"""Shared match simulator: used by the XI series and the post-auction season."""

from .engine import MatchResult, Team, simulate_match, simulate_test
from .profiles import Profile, attach_matchups, from_career, from_legend, from_phase_rows
from .rates import Env, env_names, load_env

__all__ = ["MatchResult", "Team", "simulate_match", "simulate_test", "Profile", "from_career",
           "from_legend", "from_phase_rows", "attach_matchups", "Env", "env_names", "load_env"]
