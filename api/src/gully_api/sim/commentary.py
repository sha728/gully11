"""Template commentary lines (no LLM). Variant choice is keyed on the ball's
position, not the match RNG, so turning commentary on or off never changes a result."""

from __future__ import annotations

TEMPLATES = {
    "dot": ["no run", "defended back to the bowler", "beaten outside off", "straight to the fielder"],
    1: ["1 run", "worked into the gap for a single", "pushed to long-on for one", "quick single"],
    2: ["2 runs", "driven into the deep, they come back for two", "placed well, two runs"],
    3: ["3 runs", "chased down just inside the rope, three taken"],
    4: ["FOUR", "FOUR, cracking drive through the covers", "FOUR, pulled away to the fence",
        "FOUR, edged past the slip"],
    6: ["SIX", "SIX, launched over long-on", "SIX, straight down the ground", "SIX, slog-swept into the stands"],
}


def describe(e: dict, n: int) -> str:
    head = f"{e['ball']} {e['bowler']} to {e['batter']}, "
    kind = e["kind"]
    if kind == "wide":
        extra = "" if e["runs"] == 1 else f" ({e['runs']} runs)"
        return head + "wide" + extra
    if kind == "noball":
        r = e["bat_runs"]
        return head + "no ball" + (f", {r} off the bat" if r else "")
    if kind == "wicket":
        return head + f"OUT! {e['out']} {e['how']}"
    r = e["bat_runs"]
    if r == 0 and e.get("byes"):
        return head + f"{e['byes']} {'bye' if e['byes'] == 1 else 'byes'}"
    options = TEMPLATES["dot" if r == 0 else r]
    return head + options[n % len(options)]
