"""The season after an auction: look at it, set your XI, play it, open a match."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..db import get_conn
from . import service as S

router = APIRouter(prefix="/rooms/{code}/season", tags=["season"])


class Lineup(BaseModel):
    token: str
    xi: list[str] = Field(min_length=11, max_length=11)
    impact: str | None = None


class Play(BaseModel):
    token: str | None = None


def _room(conn, code: str) -> dict:
    try:
        return S.load_room(conn, code)
    except LookupError as e:
        raise HTTPException(404, str(e)) from e


@router.get("")
def season(code: str, token: str | None = None, conn=Depends(get_conn)) -> dict[str, Any]:
    """Before it's played: every squad with its current XI (picked by a person or
    the engine). Afterwards: the whole season. ``you`` is the caller's franchise."""
    room = _room(conn, code)
    conn.commit()
    you = S.seat_of(room, token)
    out: dict[str, Any] = {"code": room["code"], "mode": room["mode"], "you": you,
                           "host": S.is_host(room, token), "played": room["season"] is not None}
    if room["season"]:
        return {**out, "season": room["season"]}
    teams = []
    for fid, team in S.squads(conn, room).items():
        xi_ids, impact, picked = S.lineup_for(team, room["lineups"].get(fid))
        teams.append({"id": fid, "name": team["name"], "bot": team["bot"], "owner": team["owner"],
                      "players": list(team["players"].values()), "xi": xi_ids, "impact": impact, "picked": picked})
    return {**out, "teams": teams}


@router.put("/lineup")
def set_lineup(code: str, req: Lineup, conn=Depends(get_conn)) -> dict[str, Any]:
    room = _room(conn, code)
    fid = S.seat_of(room, req.token)
    if fid is None:
        raise HTTPException(403, "You didn't run a franchise in this auction.")
    try:
        S.save_lineup(conn, room, fid, req.xi, req.impact)
    except S.SeasonError as e:
        raise HTTPException(422, str(e)) from e
    conn.commit()
    return {"ok": True, "franchise": fid}


@router.post("/play")
def play(code: str, req: Play, conn=Depends(get_conn)) -> dict[str, Any]:
    """Simulate the whole season (about five seconds for ten teams) and save it."""
    room = _room(conn, code)
    if not room["season"] and not S.is_host(room, req.token):
        raise HTTPException(403, "Only the host can start the season.")
    result = S.play_season(conn, room)
    conn.commit()
    return {"played": True, "season": result}


@router.get("/match/{n}")
def match(code: str, n: int, conn=Depends(get_conn)) -> dict[str, Any]:
    row = conn.execute("SELECT match_json FROM sim_results WHERE context = 'season' AND ref = %s AND match_no = %s",
                       (code.upper(), n)).fetchone()
    if row is None:
        raise HTTPException(404, "No such match.")
    return row["match_json"]
