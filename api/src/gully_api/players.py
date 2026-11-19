"""Player search and profile endpoints (read-only, pre-aggregated tables)."""

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from .db import get_conn

router = APIRouter(prefix="/players", tags=["players"])

Format = Literal["Test", "ODI", "T20I", "IPL", "T20"]
Role = Literal["BAT", "BOWL", "AR", "WK"]


class PlayerSummary(BaseModel):
    id: str
    name: str                  # Cricsheet name (initials)
    full_name: str | None      # from Wikidata, when known
    unique_name: str | None
    country: str | None
    role: Role
    capped: bool
    era_start: int | None
    era_end: int | None
    matches: int
    # Headline numbers for the requested format (null when no format filter).
    format_matches: int | None = None
    runs: int | None = None
    bat_avg: float | None = None
    bat_sr: float | None = None
    wickets: int | None = None
    bowl_econ: float | None = None


class SearchResult(BaseModel):
    total: int
    items: list[PlayerSummary]


class Player(BaseModel):
    id: str
    name: str
    full_name: str | None
    wikipedia_title: str | None
    unique_name: str | None
    cricinfo_id: str | None
    country: str | None
    role: Role
    batting_hand: str | None
    bowling_style: str | None
    is_overseas_for_ipl: bool | None
    capped: bool
    era_start: int | None
    era_end: int | None
    matches: int
    source: str


class PlayerProfile(BaseModel):
    player: Player
    formats: list[dict[str, Any]]
    seasons: list[dict[str, Any]]
    phases: list[dict[str, Any]]
    dismissals: list[dict[str, Any]]
    venues: list[dict[str, Any]]


@router.get("", response_model=SearchResult)
def search_players(
    conn=Depends(get_conn),
    q: Annotated[str | None, Query(min_length=2, max_length=60)] = None,
    country: str | None = None,
    role: Role | None = None,
    format: Format | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    sort: Literal["matches", "runs", "wickets"] = "matches",
    offset: Annotated[int, Query(ge=0)] = 0,
) -> SearchResult:
    """Fuzzy name search (pg_trgm word similarity) with optional filters.

    Without ``q``, players are ordered by ``sort`` (matches by default; runs and
    wickets apply when a format is given).
    """
    where: list[str] = []
    params: dict[str, Any] = {"limit": limit, "offset": offset, "q": q, "format": format}

    if q:
        # word_similarity lets "kohli" match "V Kohli"; ILIKE catches short exact substrings.
        where.append("(%(q)s <%% p.name OR %(q)s <%% p.unique_name OR %(q)s <%% p.full_name "
                     "OR p.name ILIKE '%%' || %(q)s || '%%' OR p.full_name ILIKE '%%' || %(q)s || '%%')")
        # Ties (e.g. two players called Rohit Sharma) fall back to matches played.
        score = ("greatest(word_similarity(%(q)s, p.name), "
                 "word_similarity(%(q)s, coalesce(p.unique_name, '')), "
                 "word_similarity(%(q)s, coalesce(p.full_name, ''))) DESC, ")
    else:
        score = ""
    if country:
        where.append("p.country ILIKE %(country)s")
        params["country"] = country
    if role:
        where.append("p.role = %(role)s")
        params["role"] = role

    if format:
        join = "JOIN player_format_stats s ON s.player_id = p.id AND s.format = %(format)s"
        stat_cols = ("s.matches AS format_matches, s.runs, s.bat_avg, s.bat_sr, "
                     "s.wickets, s.bowl_econ")
        order_matches = f"s.{sort}"
    else:
        join = ""
        stat_cols = "NULL::int AS format_matches"
        order_matches = "p.matches"  # runs/wickets need a format

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    sql = f"""
        SELECT p.id, p.name, p.full_name, p.unique_name, p.country, p.role, p.capped,
               p.era_start, p.era_end, p.matches, {stat_cols},
               count(*) OVER () AS total
        FROM players p {join}
        {where_sql}
        ORDER BY {score}{order_matches} DESC, p.name
        LIMIT %(limit)s OFFSET %(offset)s
    """
    rows = conn.execute(sql, params).fetchall()
    total = rows[0]["total"] if rows else 0
    return SearchResult(total=total, items=[PlayerSummary(**r) for r in rows])


@router.get("/{player_id}", response_model=PlayerProfile)
def get_player(
    player_id: str,
    conn=Depends(get_conn),
    format: Format | None = None,
) -> PlayerProfile:
    """Profile: identity plus career stats by format, by season, and by phase.

    ``format`` narrows the season and phase lists (career-by-format is always full).
    """
    player = conn.execute(
        "SELECT id, name, full_name, wikipedia_title, unique_name, cricinfo_id, country, role, batting_hand, "
        "bowling_style, is_overseas_for_ipl, capped, era_start, era_end, matches, source "
        "FROM players WHERE id = %s",
        (player_id,),
    ).fetchone()
    if player is None:
        raise HTTPException(status_code=404, detail="Player not found")

    fmt_filter = "AND format = %(format)s" if format else ""
    params = {"id": player_id, "format": format}

    formats = conn.execute(
        "SELECT * FROM player_format_stats WHERE player_id = %(id)s "
        "ORDER BY array_position(ARRAY['Test','ODI','T20I','IPL','T20'], format)",
        params,
    ).fetchall()
    seasons = conn.execute(
        f"SELECT * FROM player_season_stats WHERE player_id = %(id)s {fmt_filter} "
        "ORDER BY format, season",
        params,
    ).fetchall()
    phases = conn.execute(
        f"SELECT {PHASE_COLS} FROM player_phase_stats WHERE player_id = %(id)s {fmt_filter} "
        "ORDER BY format, role, array_position(ARRAY['PP','middle','death'], phase)",
        params,
    ).fetchall()
    dismissals = conn.execute(
        f"SELECT format, kind, n FROM player_dismissals WHERE player_id = %(id)s {fmt_filter} "
        "ORDER BY format, n DESC",
        params,
    ).fetchall()
    # Venues with a meaningful sample: 3+ innings or 10+ overs bowled.
    venues = conn.execute(
        f"SELECT s.*, v.name AS venue_name, v.city FROM player_venue_stats s "
        f"JOIN venues v ON v.id = s.venue_id WHERE s.player_id = %(id)s "
        f"{'AND s.format = %(format)s' if format else ''} "
        "AND (s.bat_innings >= 3 OR s.balls_bowled >= 60) ORDER BY s.format, s.runs DESC",
        params,
    ).fetchall()

    strip = lambda rows: [{k: v for k, v in r.items() if k != "player_id"} for r in rows]  # noqa: E731
    return PlayerProfile(
        player=Player(**player),
        formats=strip(formats),
        seasons=strip(seasons),
        phases=strip(phases),
        dismissals=dismissals,
        venues=strip(venues),
    )


# Phase columns shown to users (the exp_*/lexp_* columns are simulator inputs).
PHASE_COLS = ", ".join([
    "format", "phase", "role", "balls", "runs", "wickets", "dots", "ones", "twos", "threes",
    "fours", "sixes", "wide_balls", "noball_balls", "dismissal_rate", "dot_pct", "single_pct",
    "four_pct", "six_pct", "wide_rate", "noball_rate", "strike_rate", "economy",
])
