"""Playing XIs for the season: a team's best legal XI from its squad, and checks
for the XI a person picks.

Rules (IPL): eleven players, at most four overseas on the field (an overseas
Impact sub only if the XI has three or fewer), a wicketkeeper, and at least five
bowling options (bowlers and all-rounders, the Impact sub included); the last two
only as far as the squad allows. The Impact sub
is a bench bowler who bowls but doesn't bat.

``players`` maps id -> {"id", "name", "role", "overseas", "fair", "opener", "bat",
"bowl"}: ``bat`` and ``bowl`` are simulator-based strengths (see ``strengths``).
"""

from __future__ import annotations

from ..sim.profiles import Profile, expected

MAX_OVERSEAS = 4
MIN_BOWLING = 5
WICKET_ROLES = ("BOWL", "AR")


class LineupError(ValueError):
    """An XI the rules don't allow (message says why)."""


def strengths(p: Profile) -> tuple[float, float]:
    """(batting, bowling) from the simulator's profile: batting is runs per
    dismissal times strike rate (middle overs), bowling the engine's own measure
    (wickets are worth 20 runs) across all three phases."""
    rpb, w = expected(p.bat["middle"])
    bat = (rpb / max(w, 1e-3)) * rpb
    bowl = sum(20 * expected(p.bowl[ph])[1] - expected(p.bowl[ph])[0] for ph in p.bowl) / len(p.bowl)
    return bat, bowl


def quality(p: dict) -> float:
    """How much a player is worth a place: his best skill, by role."""
    if p["role"] in ("BAT", "WK"):
        return p["bat_rank"]
    if p["role"] == "BOWL":
        return p["bowl_rank"]
    return max(p["bat_rank"], p["bowl_rank"]) + 0.3 * min(p["bat_rank"], p["bowl_rank"])


def _normalise(players: dict[str, dict]) -> None:
    """Put batting and bowling on one scale (rank within the squad), so the XI picker
    can compare a batter with a bowler."""
    for key, out in (("bat", "bat_rank"), ("bowl", "bowl_rank")):
        order = sorted(players.values(), key=lambda p: p[key])
        for i, p in enumerate(order):
            p[out] = i / max(1, len(order) - 1)


def check(players: dict[str, dict], xi: list[str], impact: str | None) -> None:
    if len(xi) != 11 or len(set(xi)) != 11:
        raise LineupError("Pick exactly eleven different players.")
    unknown = [i for i in xi + ([impact] if impact else []) if i not in players]
    if unknown:
        raise LineupError("Those players aren't in your squad.")
    if impact in xi:
        raise LineupError("The Impact sub has to come from the bench.")
    team = [players[i] for i in xi]
    os_xi = sum(p["overseas"] for p in team)
    if os_xi > MAX_OVERSEAS:
        raise LineupError(f"At most {MAX_OVERSEAS} overseas players in the XI.")
    if impact and players[impact]["overseas"] and os_xi >= MAX_OVERSEAS:
        raise LineupError("With four overseas players in the XI, the Impact sub must be Indian.")
    # A squad without a keeper (or five bowlers) can't be held to that rule: the
    # engine then gives the gloves to a batter.
    has_wk = any(p["role"] == "WK" for p in players.values())
    if has_wk and not any(p["role"] == "WK" for p in team):
        raise LineupError("Your XI needs a wicketkeeper.")
    bowling = sum(p["role"] in WICKET_ROLES for p in team) + bool(impact and players[impact]["role"] in WICKET_ROLES)
    available = sum(p["role"] in WICKET_ROLES for p in players.values())
    if bowling < min(MIN_BOWLING, available):
        raise LineupError(f"You need at least {MIN_BOWLING} bowling options (bowlers and all-rounders, the Impact sub included).")


def batting_order(players: dict[str, dict], xi: list[str]) -> list[str]:
    """Openers (tagged openers first, best batting; a bowler who opens, like Sunil
    Narine, counts), then batters and keepers, then all-rounders, then bowlers,
    each by batting strength."""
    team = [players[i] for i in xi]
    by_bat = lambda p: -p["bat"]                                            # noqa: E731
    batters = [p for p in team if p["role"] in ("BAT", "WK", "AR") or p["opener"]]
    openers = sorted(batters, key=lambda p: (not p["opener"], by_bat(p)))[:2]
    rest = [p for p in team if p not in openers]
    tier = {"BAT": 0, "WK": 0, "AR": 1, "BOWL": 2}
    rest.sort(key=lambda p: (tier[p["role"]], by_bat(p)))
    return [p["id"] for p in openers + rest]


def auto(players: dict[str, dict]) -> tuple[list[str], str | None]:
    """The best legal XI (in batting order) and Impact sub this squad can field.
    Greedy by quality, never taking a player who would leave the XI unable to meet
    a requirement. Squads too thin for a legal XI field what they can."""
    _normalise(players)
    ranked = sorted(players.values(), key=lambda p: (-quality(p), p["id"]))
    xi: list[dict] = []

    def unmet(team: list[dict]) -> int:
        wk = 0 if any(p["role"] == "WK" for p in team) else 1
        bowl = max(0, MIN_BOWLING - 1 - sum(p["role"] in WICKET_ROLES for p in team))   # the sub is the 5th
        return wk + bowl

    for p in ranked:
        if len(xi) == 11:
            break
        if p["overseas"] and sum(q["overseas"] for q in xi) >= MAX_OVERSEAS:
            continue
        trial = xi + [p]
        if unmet(trial) <= 11 - len(trial) or unmet(trial) < unmet(xi):
            xi = trial
    for p in ranked:                                       # thin squad: fill however we can
        if len(xi) == 11:
            break
        if p not in xi:
            xi.append(p)
    ids = [p["id"] for p in xi]
    os_xi = sum(p["overseas"] for p in xi)
    bench = [p for p in sorted(players.values(), key=lambda p: -p["bowl_rank"])
             if p["id"] not in ids and p["role"] in WICKET_ROLES and not (p["overseas"] and os_xi >= MAX_OVERSEAS)]
    impact = bench[0]["id"] if bench else None
    return batting_order(players, ids), impact
