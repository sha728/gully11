"""League fixtures and the playoff bracket.

Ten teams play the IPL's format since 2022: two groups of five (drawn by the
seed). A team plays the other four in its group twice, its counterpart in the
other group twice and the remaining four once: 14 matches each, 70 in all.
Smaller rooms play a double round robin. Matches are ordered so nobody plays two
in a row when it can be avoided.

Playoffs (four or more teams): Qualifier 1 (1st v 2nd), Eliminator (3rd v 4th),
Qualifier 2 (loser of Q1 v winner of the Eliminator), Final. Two or three teams:
a final between the top two.
"""

from __future__ import annotations

import itertools
import random


def league(teams: list[str], seed: int) -> list[tuple[str, str]]:
    rng = random.Random(seed)
    if len(teams) == 10:
        order = teams[:]
        rng.shuffle(order)
        a, b = order[:5], order[5:]
        games = []
        for group in (a, b):
            for x, y in itertools.combinations(group, 2):
                games += [(x, y), (y, x)]
        for i, x in enumerate(a):
            for j, y in enumerate(b):
                games += [(x, y), (y, x)] if i == j else [(x, y) if rng.random() < 0.5 else (y, x)]
    else:
        games = [(x, y) for x, y in itertools.permutations(teams, 2)]
    rng.shuffle(games)
    return _spread(games)


def _spread(games: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Order matches so teams get rest: each next match is the one whose teams have
    waited longest since they last played (ties keep the shuffled order)."""
    out: list[tuple[str, str]] = []
    left = games[:]
    last: dict[str, int] = {}
    while left:
        n = len(out)
        best = max(range(len(left)), key=lambda i: (min(n - last.get(t, -99) for t in left[i]), -i))
        game = left.pop(best)
        for t in game:
            last[t] = n
        out.append(game)
    return out


PLAYOFFS = [
    ("Qualifier 1", ("seed", 1), ("seed", 2)),
    ("Eliminator", ("seed", 3), ("seed", 4)),
    ("Qualifier 2", ("loser", "Qualifier 1"), ("winner", "Eliminator")),
    ("Final", ("winner", "Qualifier 1"), ("winner", "Qualifier 2")),
]


def playoff_plan(n_teams: int) -> list[tuple]:
    if n_teams >= 4:
        return PLAYOFFS
    return [("Final", ("seed", 1), ("seed", 2))]
