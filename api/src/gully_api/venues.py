"""Venue search and venue pages."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from .db import get_conn
from .players import Format

router = APIRouter(prefix="/venues", tags=["venues"])


class VenueSummary(BaseModel):
    id: str
    name: str
    city: str | None
    matches: int


class VenuePage(BaseModel):
    venue: dict[str, Any]
    formats: list[dict[str, Any]]
    top_batters: list[dict[str, Any]]
    top_bowlers: list[dict[str, Any]]


@router.get("", response_model=list[VenueSummary])
def search_venues(
    conn=Depends(get_conn),
    q: Annotated[str | None, Query(min_length=2, max_length=60)] = None,
    format: Format | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[VenueSummary]:
    """Venues by fuzzy name/city match, else most-played first."""
    params: dict[str, Any] = {"q": q, "format": format, "limit": limit}
    where = []
    if q:
        # Stricter than player search: ground names are long, so a loose fuzzy match
        # ("rashid" ~ "Shahid") is mostly noise. Substring, or a strong fuzzy hit.
        where.append("(v.name ILIKE '%%' || %(q)s || '%%' OR v.city ILIKE '%%' || %(q)s || '%%' "
                     "OR word_similarity(%(q)s, v.name) >= 0.6)")
    if format:
        where.append("EXISTS (SELECT 1 FROM venue_format_stats s WHERE s.venue_id = v.id "
                     "AND s.format = %(format)s)")
    order = "word_similarity(%(q)s, v.name) DESC, " if q else ""
    rows = conn.execute(
        f"SELECT id, name, city, matches FROM venues v "
        f"{'WHERE ' + ' AND '.join(where) if where else ''} "
        f"ORDER BY {order}matches DESC LIMIT %(limit)s",
        params,
    ).fetchall()
    return [VenueSummary(**r) for r in rows]


@router.get("/{venue_id}", response_model=VenuePage)
def get_venue(
    venue_id: str,
    conn=Depends(get_conn),
    format: Format | None = None,
    top: Annotated[int, Query(ge=1, le=50)] = 10,
) -> VenuePage:
    """Venue summary per format plus leading run scorers and wicket takers there.
    The leader lists use ``format`` if given, else the venue's most-played specific
    format (all-T20 only if nothing else)."""
    venue = conn.execute("SELECT * FROM venues WHERE id = %s", (venue_id,)).fetchone()
    if venue is None:
        raise HTTPException(404, "Venue not found")
    formats = conn.execute(
        "SELECT * FROM venue_format_stats WHERE venue_id = %s "
        "ORDER BY array_position(ARRAY['Test','ODI','T20I','IPL','T20'], format)",
        (venue_id,),
    ).fetchall()
    # Default: the busiest specific format (the all-T20 total always wins on count).
    specific = [f for f in formats if f["format"] != "T20"] or formats
    fmt = format or (max(specific, key=lambda f: f["matches"])["format"] if specific else None)
    params = {"v": venue_id, "f": fmt, "top": top}
    top_batters = conn.execute(
        "SELECT p.id, p.name, p.full_name, p.country, s.format, s.bat_innings, s.runs, s.highest, s.bat_avg, s.bat_sr "
        "FROM player_venue_stats s JOIN players p ON p.id = s.player_id "
        "WHERE s.venue_id = %(v)s AND s.format = %(f)s AND s.runs > 0 "
        "ORDER BY s.runs DESC LIMIT %(top)s", params).fetchall()
    top_bowlers = conn.execute(
        "SELECT p.id, p.name, p.full_name, p.country, s.format, s.balls_bowled, s.wickets, s.runs_conceded, s.bowl_econ "
        "FROM player_venue_stats s JOIN players p ON p.id = s.player_id "
        "WHERE s.venue_id = %(v)s AND s.format = %(f)s AND s.wickets > 0 "
        "ORDER BY s.wickets DESC, s.bowl_econ LIMIT %(top)s", params).fetchall()
    for f in formats:
        f.pop("venue_id", None)
    return VenuePage(venue=venue, formats=formats, top_batters=top_batters, top_bowlers=top_bowlers)
