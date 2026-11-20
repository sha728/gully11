"""Live auction rooms: one ``Room`` per code, held in this process, a clock task
per room, and every connected browser on a WebSocket.

The server owns the clock: lots close when *its* time says so, and clients only
draw a countdown from ``ends_at`` (with ``server_now`` sent alongside, so a
browser with a wrong clock still counts down correctly). Every change bumps the
room's version and the new state goes to everyone in the room.

Rooms live in memory (an API restart ends them); a finished auction is saved to
Postgres. Running more than one API process would need the room state in Redis
instead, as the plan describes.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import logging
import time

from fastapi import WebSocket
from psycopg.types.json import Jsonb

from .room import AuctionError, Room

log = logging.getLogger(__name__)

TICK = 0.2                 # seconds between clock checks
IDLE_LIMIT = 6 * 3600      # forget rooms nobody has touched for this long


class LiveRoom:
    def __init__(self, room: Room, save):
        self.room = room
        self.lock = asyncio.Lock()
        self.sockets: dict[WebSocket, str | None] = {}     # socket -> franchise id (None = watcher)
        self.task: asyncio.Task | None = None
        self.sent = -1
        self.touched = time.time()
        self.saved = False
        self._save = save

    def refresh_online(self) -> None:
        """Tell the room which franchises have someone connected: a friend who has
        closed the tab doesn't hold up every lot."""
        self.room.online = {fid for fid in self.sockets.values() if fid}

    def state(self) -> dict:
        return {"type": "state", "server_now": time.time(), **self.room.view()}

    async def broadcast(self) -> None:
        if self.room.version == self.sent:
            return
        self.sent = self.room.version
        msg = json.dumps(self.state(), default=str)
        dead = []
        for ws in list(self.sockets):
            try:
                await ws.send_text(msg)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.sockets.pop(ws, None)

    async def run(self) -> None:
        """The room's clock: tick, broadcast, save once it's over."""
        while True:
            async with self.lock:
                self.room.tick(time.time())
                ended = self.room.phase == "ended"
            await self.broadcast()
            if ended:
                if not self.saved:
                    self.saved = True
                    with contextlib.suppress(Exception):
                        await asyncio.to_thread(self._save, self.room)
                return
            await asyncio.sleep(TICK)

    async def act(self, fn) -> None:
        async with self.lock:
            fn()
            self.touched = time.time()
        await self.broadcast()


class Rooms:
    def __init__(self):
        self.rooms: dict[str, LiveRoom] = {}

    def add(self, room: Room, save) -> LiveRoom:
        self._sweep()
        live = LiveRoom(room, save)
        self.rooms[room.code] = live
        return live

    def get(self, code: str) -> LiveRoom | None:
        return self.rooms.get(code.upper())

    def _sweep(self) -> None:
        now = time.time()
        for code, live in list(self.rooms.items()):
            if now - live.touched > IDLE_LIMIT and not live.sockets:
                if live.task:
                    live.task.cancel()
                self.rooms.pop(code, None)

    async def start(self, live: LiveRoom, token: str | None) -> None:
        await live.act(lambda: live.room.start(time.time(), token))
        live.task = asyncio.create_task(live.run())

    async def connect(self, live: LiveRoom, ws: WebSocket, token: str | None) -> None:
        """Serve one browser until it disconnects."""
        await ws.accept()
        franchise = live.room.by_token(token)
        live.sockets[ws] = franchise.id if franchise else None
        live.refresh_online()
        await ws.send_text(json.dumps({**live.state(), "you": franchise.id if franchise else None,
                                       "host": token is not None and token == live.room.host_token},
                                      default=str))
        try:
            while True:
                msg = json.loads(await ws.receive_text())
                await self._handle(live, ws, franchise, token, msg)
        except Exception as e:                       # disconnect or bad frame
            if not _is_disconnect(e):
                log.debug("auction socket closed: %s", e)
        finally:
            live.sockets.pop(ws, None)
            live.refresh_online()

    async def _handle(self, live: LiveRoom, ws: WebSocket, franchise, token, msg: dict) -> None:
        kind = msg.get("type")
        franchise = live.room.by_token(token)        # fresh: picking a team moves the seat
        try:
            if kind == "start":
                await self.start(live, token)
            elif franchise is None:
                raise AuctionError("You're watching this room: join to bid.")
            elif kind == "bid":
                await live.act(lambda: live.room.bid(franchise.id, int(msg["amount"]), time.time()))
            elif kind == "pass":
                await live.act(lambda: live.room.pass_(franchise.id))
            elif kind == "choose":
                await live.act(lambda: live.room.choose(franchise, str(msg["franchise"])))
                # Now running another franchise: re-point this socket and tell the browser.
                franchise = live.room.by_token(token)
                live.sockets[ws] = franchise.id
                live.refresh_online()
                await ws.send_text(json.dumps({"type": "you", "you": franchise.id}))
            elif kind == "ping":
                await ws.send_text(json.dumps({"type": "pong", "server_now": time.time()}))
        except (AuctionError, KeyError, ValueError, TypeError) as e:
            await ws.send_text(json.dumps({"type": "error", "message": str(e)}))


def _is_disconnect(e: Exception) -> bool:
    return type(e).__name__ in ("WebSocketDisconnect", "ConnectionClosed", "ConnectionClosedOK")


ROOMS = Rooms()


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def seats(room: Room) -> dict:
    """Who ran which franchise, as token hashes (the tokens themselves aren't kept)."""
    host = room.by_token(room.host_token)
    return {"host": host.id if host else None,
            "franchises": {f.id: token_hash(f.token) for f in room.franchises.values() if f.token}}


def save_room(pool_factory):
    """A saver bound to the DB pool: writes the finished auction."""
    def save(room: Room) -> None:
        with pool_factory() as conn:
            conn.execute(
                "INSERT INTO auction_rooms (code, mode, teams, result, seats, ended_at) "
                "VALUES (%s, %s, %s, %s, %s, now()) "
                "ON CONFLICT (code) DO UPDATE SET result = EXCLUDED.result, seats = EXCLUDED.seats, ended_at = now()",
                (room.code, room.mode, len(room.franchises), Jsonb(room.summary()), Jsonb(seats(room))))
            conn.commit()
    return save
