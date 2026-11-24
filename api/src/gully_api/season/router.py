"""The season after an auction: look at it, set your XI, play it, open a match."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..db import get_conn
from ..sim.awards import with_award
from . import service as S

router = APIRouter(prefix="/rooms/{code}/season", tags=["season"])


class Lineup(BaseModel):
    token: str
    xi: list[str] = Field(min_length=11, max_length=11)
    impact: str | None = None
    captain: str | None = None       # one of the XI; None = the best-rated captain in it
    impact_out: str | None = None    # who the Impact sub replaces; None = the engine picks
    impact_when: Literal["auto", "start", "break"] = "auto"
    subs: list[str] | None = Field(default=None, max_length=5)   # named substitutes; None: just ``impact``


class Step(BaseModel):
    token: str | None = None
    how: str = "next"            # next | mine | end


class Choose(BaseModel):
    token: str
    on: bool


class Bowl(BaseModel):
    token: str
    key: str = Field(pattern=r"^[12]:\d{1,2}$")     # "<innings>:<over>"
    bowler: str = Field(min_length=1, max_length=40)  # player id, "auto" or "rest"


def _room(conn, code: str) -> dict:
    try:
        return S.load_room(conn, code)
    except LookupError as e:
        raise HTTPException(404, str(e)) from e


@router.get("")
def season(code: str, token: str | None = None, conn=Depends(get_conn)) -> dict[str, Any]:
    """Every squad with its current XI, and the season so far. ``you`` is the
    caller's franchise; ``host`` whether they move the season on."""
    room = _room(conn, code)
    out = S.view(conn, room, token)
    conn.commit()
    return out


@router.put("/lineup")
def set_lineup(code: str, req: Lineup, conn=Depends(get_conn)) -> dict[str, Any]:
    """Your XI for your coming matches: before the season or between matches."""
    room = _room(conn, code)
    fid = S.seat_of(room, req.token)
    if fid is None:
        raise HTTPException(403, "You didn't run a franchise in this auction.")
    try:
        S.save_lineup(conn, room, fid, req.xi, req.impact, req.captain, req.impact_out, req.impact_when, req.subs)
    except S.SeasonError as e:
        raise HTTPException(422, str(e)) from e
    conn.commit()
    return {"ok": True, "franchise": fid}


@router.put("/choose")
def choose_bowlers(code: str, req: Choose, conn=Depends(get_conn)) -> dict[str, Any]:
    """Choose your bowler every over in your matches (on), or leave it to the engine."""
    room = _room(conn, code)
    fid = S.seat_of(room, req.token)
    if fid is None:
        raise HTTPException(403, "You didn't run a franchise in this auction.")
    try:
        S.set_choose(conn, room, fid, req.on)
    except S.SeasonError as e:
        raise HTTPException(422, str(e)) from e
    conn.commit()
    return S.view(conn, room, req.token)


@router.get("/live")
def live(code: str, token: str | None = None, conn=Depends(get_conn)) -> dict[str, Any]:
    """The match waiting on a captain's bowling change, as far as it has got."""
    room = _room(conn, code)
    try:
        return S.live(conn, room, token)
    except S.SeasonError as e:
        raise HTTPException(409, str(e)) from e


@router.post("/live/bowl")
def live_bowl(code: str, req: Bowl, conn=Depends(get_conn)) -> dict[str, Any]:
    """Choose the bowler for the over the season is waiting on; the season then
    plays on to the next over you bowl, or to the end of the match."""
    room = _room(conn, code)
    conn.execute("SELECT 1 FROM seasons WHERE code = %s FOR UPDATE", (room["code"],))   # one step at a time
    room = _room(conn, code)
    try:
        S.bowl(conn, room, req.token, req.key, req.bowler)
    except S.SeasonError as e:
        raise HTTPException(409 if "already" in str(e) else 422, str(e)) from e
    conn.commit()
    return S.view(conn, room, req.token)


@router.post("/start")
def start(code: str, req: Step, conn=Depends(get_conn)) -> dict[str, Any]:
    """Draw the fixtures (host)."""
    room = _room(conn, code)
    if not room["season"] and not S.is_host(room, req.token):
        raise HTTPException(403, "Only the host can start the season.")
    S.start_season(conn, room)
    conn.commit()
    return S.view(conn, room, req.token)


@router.post("/advance")
def advance(code: str, req: Step, conn=Depends(get_conn)) -> dict[str, Any]:
    """Move the season on (host): ``next`` match, to the host's next match
    (``mine``), or to the ``end``. Matches are simulated now, with today's XIs."""
    room = _room(conn, code)
    if not S.is_host(room, req.token):
        raise HTTPException(403, "Only the host moves the season on.")
    conn.execute("SELECT 1 FROM seasons WHERE code = %s FOR UPDATE", (room["code"],))   # one step at a time
    room = _room(conn, code)
    try:
        S.advance(conn, room, req.how, S.seat_of(room, req.token))
    except S.SeasonError as e:
        raise HTTPException(422, str(e)) from e
    conn.commit()
    return S.view(conn, room, req.token)


@router.get("/match/{n}")
def match(code: str, n: int, conn=Depends(get_conn)) -> dict[str, Any]:
    row = conn.execute("SELECT match_json FROM sim_results WHERE context = 'season' AND ref = %s AND match_no = %s",
                       (code.upper(), n)).fetchone()
    if row is None:
        raise HTTPException(404, "No such match.")
    return with_award(row["match_json"])
