"""Auction rooms over REST (create, join, look) and a WebSocket per room (bid,
pass, start, live state)."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, WebSocket
from pydantic import BaseModel, Field

from ..db import connection, get_conn
from .live import ROOMS, save_room
from .mini import build_mini
from .pool import RULES, build_pool
from .room import AuctionError, Room, room_code

router = APIRouter(tags=["auction"])


class NewRoom(BaseModel):
    nickname: str = Field(min_length=1, max_length=24)
    teams: int = Field(default=10, ge=2, le=10)
    humans: int = Field(default=1, ge=1, le=10)
    speed: Literal["normal", "fast"] = "normal"
    mode: Literal["mega", "mini"] = "mega"


class Join(BaseModel):
    nickname: str = Field(min_length=1, max_length=24)
    franchise: str | None = None         # one of the room's franchises; else the next free seat


@router.post("/rooms")
def create_room(req: NewRoom, conn=Depends(get_conn)) -> dict[str, Any]:
    """Host a room: you get the first franchise; the rest wait for friends (``humans``)
    or are bots."""
    teams = 10 if req.mode == "mini" else req.teams       # mini: the real ten franchises
    if req.humans > teams:
        raise HTTPException(422, "More people than franchises.")
    replay = build_mini(conn) if req.mode == "mini" else None
    pool = [] if replay else build_pool(conn, req.mode, teams)
    code = room_code()
    while ROOMS.get(code):
        code = room_code()
    try:
        room = Room(code, req.mode, RULES[req.mode], pool, teams, req.humans, req.speed, host=req.nickname,
                    replay=replay)
    except AuctionError as e:
        raise HTTPException(422, str(e)) from e
    ROOMS.add(room, save_room(connection))
    me = room.by_token(room.host_token)
    return {"code": code, "token": room.host_token, "franchise": me.id}


@router.post("/rooms/{code}/join")
async def join_room(code: str, req: Join) -> dict[str, Any]:
    live = ROOMS.get(code)
    if live is None:
        raise HTTPException(404, "No room with that code. Check it, or it may have ended.")
    if live.room.phase != "lobby":
        raise HTTPException(409, "This auction has already started.")
    async with live.lock:
        try:
            f = live.room.claim(req.nickname, req.franchise)
        except AuctionError as e:
            raise HTTPException(409, str(e)) from e
    await live.broadcast()
    return {"code": live.room.code, "token": f.token, "franchise": f.id}


@router.get("/rooms/{code}")
def get_room(code: str, conn=Depends(get_conn)) -> dict[str, Any]:
    """A live room's state, or a finished auction's result."""
    live = ROOMS.get(code)
    if live is not None:
        return {"live": True, **live.room.view(),
                **({"result": live.room.summary()} if live.room.phase == "ended" else {})}
    row = conn.execute("SELECT code, mode, teams, result, ended_at FROM auction_rooms WHERE code = %s",
                       (code.upper(),)).fetchone()
    if row is None:
        raise HTTPException(404, "No room with that code.")
    return {"live": False, "code": row["code"], "mode": row["mode"], "phase": "ended", "result": row["result"]}


@router.websocket("/ws/rooms/{code}")
async def room_socket(ws: WebSocket, code: str, token: str | None = None) -> None:
    live = ROOMS.get(code)
    if live is None:
        await ws.accept()
        await ws.close(code=4404, reason="No room with that code.")
        return
    await ROOMS.connect(live, ws, token)
