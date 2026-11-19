"""Head-to-head comparison of two players in one format, optionally a year range.

Each radar metric is also given as a percentile (0-100, higher = better) against
qualified players in that format: 500+ balls faced for batting metrics, 500+
balls bowled for bowling metrics. Percentiles use career numbers for the pool,
so a year-range figure is placed on the same career scale.
"""

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from .db import get_conn
from .players import Format

router = APIRouter(tags=["compare"])

MIN_BALLS = 500
# A player's own figure is only ranked once they have this many balls on that side;
# 29 overs of part-time bowling shouldn't 'win' economy against specialists.
MIN_SAMPLE = 300

# key -> (label, side, higher_is_better, SQL over aggregated columns)
METRICS: dict[str, tuple[str, Literal["bat", "bowl"], bool, str]] = {
    "bat_avg": ("Batting average", "bat", True, "runs::float / nullif(bat_innings - not_outs, 0)"),
    "bat_sr": ("Strike rate", "bat", True, "100.0 * runs / nullif(balls_faced, 0)"),
    "boundary_pct": ("Boundary %", "bat", True, "100.0 * (fours + sixes) / nullif(balls_faced, 0)"),
    "balls_per_dismissal": ("Balls per dismissal", "bat", True,
                            "balls_faced::float / nullif(bat_innings - not_outs, 0)"),
    "bowl_econ": ("Economy", "bowl", False, "6.0 * runs_conceded / nullif(balls_bowled, 0)"),
    "bowl_sr": ("Balls per wicket", "bowl", False, "balls_bowled::float / nullif(wickets, 0)"),
    "wickets_per_match": ("Wickets per match", "bowl", True, "wickets::float / nullif(matches, 0)"),
}

AGG_COLS = ("matches", "bat_innings", "not_outs", "runs", "balls_faced", "fours", "sixes",
            "balls_bowled", "runs_conceded", "wickets", "fifties", "hundreds", "five_wkts",
            "catches", "stumpings")


class Metric(BaseModel):
    key: str
    label: str
    side: Literal["bat", "bowl"]
    higher_is_better: bool
    value: float | None
    percentile: float | None
    qualified: bool            # enough balls to be ranked (MIN_SAMPLE)


class ComparedPlayer(BaseModel):
    id: str
    name: str
    full_name: str | None
    country: str | None
    role: str
    totals: dict[str, Any]
    metrics: list[Metric]


class Comparison(BaseModel):
    format: str
    from_year: int | None
    to_year: int | None
    min_balls_for_percentiles: int
    min_sample_to_rank: int
    players: list[ComparedPlayer]


def _totals(conn, pid: str, fmt: str, y0: int | None, y1: int | None) -> dict | None:
    cols = ", ".join(f"sum({c})::int AS {c}" for c in AGG_COLS)
    if y0 is None and y1 is None:
        return conn.execute(f"SELECT {cols} FROM player_format_stats WHERE player_id = %s "
                            "AND format = %s HAVING count(*) > 0", (pid, fmt)).fetchone()
    return conn.execute(
        f"SELECT {cols} FROM player_season_stats WHERE player_id = %s AND format = %s "
        "AND left(season, 4)::int BETWEEN %s AND %s HAVING count(*) > 0",
        (pid, fmt, y0 or 0, y1 or 9999)).fetchone()


def _metrics(conn, totals: dict, fmt: str) -> list[Metric]:
    out = []
    for key, (label, side, higher, expr) in METRICS.items():
        value = conn.execute(
            f"SELECT {expr} AS v FROM (SELECT {', '.join(f'%({c})s::float AS {c}' for c in AGG_COLS)}) t",
            {c: totals[c] or 0 for c in AGG_COLS}).fetchone()["v"]
        pct = None
        balls = "balls_faced" if side == "bat" else "balls_bowled"
        qualified = (totals[balls] or 0) >= MIN_SAMPLE
        if value is not None and qualified:
            better = "<" if higher else ">"
            pct = conn.execute(
                f"SELECT round((100.0 * count(*) FILTER (WHERE v {better} %(x)s) / nullif(count(*), 0))::numeric, 1)"
                f"::float AS p FROM (SELECT {expr} AS v FROM player_format_stats "
                f"WHERE format = %(f)s AND {balls} >= {MIN_BALLS}) pool WHERE v IS NOT NULL",
                {"x": value, "f": fmt}).fetchone()["p"]
        out.append(Metric(key=key, label=label, side=side, higher_is_better=higher,
                          value=round(value, 2) if value is not None else None, percentile=pct,
                          qualified=qualified))
    return out


@router.get("/compare", response_model=Comparison)
def compare(
    a: str,
    b: str,
    format: Format,
    conn=Depends(get_conn),
    from_year: Annotated[int | None, Query(ge=1900, le=2100)] = None,
    to_year: Annotated[int | None, Query(ge=1900, le=2100)] = None,
) -> Comparison:
    if from_year and to_year and from_year > to_year:
        raise HTTPException(422, "from_year is after to_year")
    players = []
    for pid in (a, b):
        p = conn.execute("SELECT id, name, full_name, country, role FROM players WHERE id = %s", (pid,)).fetchone()
        if p is None:
            raise HTTPException(404, f"Player not found: {pid}")
        totals = _totals(conn, pid, format, from_year, to_year) or dict.fromkeys(AGG_COLS, 0)
        players.append(ComparedPlayer(**p, totals=totals, metrics=_metrics(conn, totals, format)))
    return Comparison(format=format, from_year=from_year, to_year=to_year,
                      min_balls_for_percentiles=MIN_BALLS, min_sample_to_rank=MIN_SAMPLE, players=players)
