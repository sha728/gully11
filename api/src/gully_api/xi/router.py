"""XI Builder endpoints.

A draft lives on the server (``/xi/drafts``): spins are revealed one at a time and
each pick or move is checked there, so the browser never sees a spin before it is
spun. Finished drafts become shareable challenges.
"""

from __future__ import annotations

import random
import secrets
from datetime import date, datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field

from ..db import get_conn
from ..sim import captaincy
from ..sim.awards import player_of_series, with_award
from ..sim.rates import load_env
from . import service
from .draft import Draft, reel
from .service import FORMATS, DraftError

router = APIRouter(prefix="/xi", tags=["xi"])

XIFormat = Literal["Test", "ODI", "T20I", "IPL"]


def _today() -> date:
    return datetime.now(timezone.utc).date()


@router.get("/formats")
def formats() -> dict[str, Any]:
    """Formats with their eras, what a spin draws (nation or franchise), the opponent
    and the batting positions."""
    return {f: {"eras": list(s.eras), "unit": s.unit, "opponent": service.WORLD_XI[f]["name"],
                "positions": service.SLOTS,
                "rules": {"keeper": "in the top six",
                          **({"overseas": f"at most {service.MAX_OVERSEAS_IPL}"} if f == "IPL" else {})}}
            for f, s in FORMATS.items()}


# ------------------------------------------------------------------ drafts

class NewDraft(BaseModel):
    format: XIFormat
    seed: int | None = Field(None, ge=0, lt=2**32, description="a shared draw; omit for a random one")
    daily: bool = False
    vs: str | None = Field(None, max_length=32, description="slug of a challenge to chase (same draw)")


class Pick(BaseModel):
    spin: int = Field(ge=1, le=11)
    player: str = Field(max_length=64)
    slot: int | None = Field(None, ge=1, le=11, description="omit to take the best legal slot")


class Captain(BaseModel):
    player: str | None = None        # one of your picks; None = let the engine choose


class EntryName(BaseModel):
    name: str = Field(min_length=2, max_length=20, pattern=r"^[A-Za-z0-9 _.\-]+$")


class Move(BaseModel):
    src: int = Field(ge=1, le=11, alias="from")
    dst: int = Field(ge=1, le=11, alias="to")


def _load(conn, draft_id: str, lock: bool = False) -> dict:
    row = conn.execute("SELECT * FROM xi_drafts WHERE id = %s" + (" FOR UPDATE" if lock else ""),
                       (draft_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "Draft not found")
    return row


def _draft(conn, row: dict) -> Draft:
    return Draft(row["format"], service.spins(conn, row["format"], row["seed"]), row["picks"], row["revealed"])


def _view(conn, row: dict) -> dict[str, Any]:
    picked = [p["id"] for p in row["picks"] if p]
    chosen = row.get("captain") if row.get("captain") in picked else None
    return {"id": row["id"], "format": row["format"], "seed": row["seed"],
            "daily": row["daily"].isoformat() if row["daily"] else None, "rival": row["rival"],
            "challenge": row["challenge"], "positions": service.SLOTS, "reel": reel(conn, row["format"]),
            # Captain: the one picked, else the best-rated captain so far (who leads if you don't choose).
            "captain": chosen, "captain_auto": captaincy.best(picked, row["format"]) if picked else None,
            **_draft(conn, row).view()}


# Write endpoints commit before responding: the pooled connection's own commit
# runs only after the response has gone out, so a quick follow-up request (spin
# right after creating a draft, the series page right after Play) could miss it.
def _save(conn, row: dict, **changes) -> dict:
    sets = ", ".join(f"{k} = %s" for k in changes)
    vals = [Jsonb(v) if k == "picks" else v for k, v in changes.items()]
    conn.execute(f"UPDATE xi_drafts SET {sets}, updated_at = now() WHERE id = %s", (*vals, row["id"]))
    return {**row, **changes}


def _editable(row: dict) -> None:
    if row["challenge"]:
        raise HTTPException(409, "This draft has been played. Start a new one.")


@router.post("/drafts")
def new_draft(req: NewDraft, conn=Depends(get_conn)) -> dict[str, Any]:
    """Start a draft: today's challenge, a shared draw (seed), or a random one.
    Nothing is revealed yet."""
    day = _today() if req.daily else None
    if req.daily:
        seed = service.daily_seed(req.format, day)
    else:
        seed = req.seed if req.seed is not None else random.randrange(2**32)
    rival = None
    if req.vs:
        r = conn.execute("SELECT format, seed FROM xi_challenges WHERE slug = %s", (req.vs,)).fetchone()
        if r and r["format"] == req.format and r["seed"] == seed:
            rival = req.vs
    service.spins(conn, req.format, seed)               # draw now, so the first spin is quick
    row = {"id": secrets.token_urlsafe(12), "format": req.format, "seed": seed, "daily": day,
           "rival": rival, "revealed": 0, "picks": [None] * 11, "challenge": None}
    conn.execute("INSERT INTO xi_drafts (id, format, seed, daily, rival, revealed, picks) "
                 "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                 (row["id"], req.format, seed, day, rival, 0, Jsonb(row["picks"])))
    conn.commit()
    return _view(conn, row)


@router.get("/drafts/{draft_id}")
def get_draft(draft_id: str, conn=Depends(get_conn)) -> dict[str, Any]:
    return _view(conn, _load(conn, draft_id))


@router.post("/drafts/{draft_id}/spin")
def spin(draft_id: str, conn=Depends(get_conn)) -> dict[str, Any]:
    """Reveal the next spin. Every revealed spin needs a pick first."""
    row = _load(conn, draft_id, lock=True)
    _editable(row)
    d = _draft(conn, row)
    if row["revealed"] >= len(d.spins):
        raise HTTPException(409, "All eleven spins are out.")
    if d.waiting:
        raise HTTPException(409, "Pick a player from your last spin first.")
    row = _save(conn, row, revealed=row["revealed"] + 1)
    conn.commit()
    return _view(conn, row)


def _act(conn, draft_id: str, fn) -> dict[str, Any]:
    row = _load(conn, draft_id, lock=True)
    _editable(row)
    try:
        picks = fn(_draft(conn, row))
    except DraftError as e:
        raise HTTPException(422, str(e)) from e
    row = _save(conn, row, picks=picks)
    conn.commit()
    return _view(conn, row)


@router.post("/drafts/{draft_id}/pick")
def pick(draft_id: str, req: Pick, conn=Depends(get_conn)) -> dict[str, Any]:
    """Take a player from a revealed spin (replacing any earlier pick from it)."""
    return _act(conn, draft_id, lambda d: d.pick(req.spin - 1, req.player, req.slot))


@router.delete("/drafts/{draft_id}/pick/{spin_no}")
def unpick(draft_id: str, spin_no: int, conn=Depends(get_conn)) -> dict[str, Any]:
    return _act(conn, draft_id, lambda d: d.remove(spin_no - 1))


@router.post("/drafts/{draft_id}/move")
def move(draft_id: str, req: Move, conn=Depends(get_conn)) -> dict[str, Any]:
    """Move a player to another batting position, swapping with whoever is there."""
    return _act(conn, draft_id, lambda d: d.move(req.src, req.dst))


@router.post("/drafts/{draft_id}/captain")
def set_captain(draft_id: str, req: Captain, conn=Depends(get_conn)) -> dict[str, Any]:
    """Name your captain (one of the players you've picked)."""
    row = _load(conn, draft_id, lock=True)
    _editable(row)
    if req.player and req.player not in [p["id"] for p in row["picks"] if p]:
        raise HTTPException(422, "Your captain has to be in your XI.")
    row = _save(conn, row, captain=req.player)
    conn.commit()
    return _view(conn, row)


@router.post("/drafts/{draft_id}/play")
def play(draft_id: str, conn=Depends(get_conn)) -> dict[str, Any]:
    """Play the drafted XI: five seeded matches against the Greats, saved under a
    share slug. Playing the same XI again returns the same slug."""
    row = _load(conn, draft_id, lock=True)
    if row["challenge"]:
        return {"slug": row["challenge"]}
    d = _draft(conn, row)
    if not d.status()["ready"]:
        raise HTTPException(422, "Your XI isn't complete yet.")
    picks = [p["id"] for p in row["picks"]]
    slots = [p["slot"] for p in row["picks"]]
    try:
        out = service.play_series(conn, row["format"], row["seed"], picks, slots,
                                  captain=row.get("captain") if row.get("captain") in picks else None)
    except DraftError as e:
        raise HTTPException(422, str(e)) from e
    full = out.pop("_full")
    conn.execute(
        """INSERT INTO xi_challenges (slug, format, seed, daily, picks, xi, opponent, result, matches)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (slug) DO NOTHING""",
        (out["slug"], row["format"], row["seed"], row["daily"],
         Jsonb({"ids": picks, "slots": slots, "captain": out["captains"]["mine"]["id"]}),
         Jsonb(out["xi"]), out["opponent"], Jsonb({**out["result"], "captains": out["captains"]}),
         Jsonb(out["matches"])))
    for i, m in enumerate(full, start=1):
        conn.execute(
            "INSERT INTO sim_results (context, ref, match_no, match_json) VALUES ('xi', %s, %s, %s) "
            "ON CONFLICT (context, ref, match_no) DO NOTHING", (out["slug"], i, Jsonb(m)))
    if row["daily"]:
        t = out["result"]
        conn.execute(
            """INSERT INTO xi_daily_entries (draft_id, format, day, slug, won, lost, tied, drawn, points, run_diff)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (draft_id) DO NOTHING""",
            (row["id"], row["format"], row["daily"], out["slug"], t["won"], t["lost"], t["tied"], t["drawn"],
             2 * t["won"] + t["tied"] + t["drawn"], service.run_difference(out["matches"])))
    _save(conn, row, challenge=out["slug"])
    conn.commit()
    return {"slug": out["slug"], "rival": row["rival"]}


# ------------------------------------------------------------------ challenges

@router.get("/challenge/{slug}")
def challenge(slug: str, conn=Depends(get_conn)) -> dict[str, Any]:
    """A saved series. Its spins are not included: a friend replays the draw by
    starting a draft with the same seed."""
    row = conn.execute("SELECT * FROM xi_challenges WHERE slug = %s", (slug,)).fetchone()
    if row is None:
        raise HTTPException(404, "Challenge not found")
    row["daily"] = row["daily"].isoformat() if row["daily"] else None
    if isinstance(row["picks"], dict):   # {"ids", "slots", "captain"}; early challenges stored ids only
        row["captain"] = row["picks"].get("captain")
        row["picks"], row["slots"] = row["picks"]["ids"], row["picks"]["slots"]
    row["captains"] = (row["result"] or {}).get("captains")
    if row["result"] is not None and "player_of_series" not in row["result"]:
        # Played before awards existed: work them out from the saved matches.
        full = [with_award(r["match_json"]) for r in conn.execute(
            "SELECT match_json FROM sim_results WHERE context = 'xi' AND ref = %s ORDER BY match_no", (slug,))]
        if full:
            row["result"]["player_of_series"] = player_of_series(full, load_env(full[0]["env"]).is_test)
            for m, f in zip(row["matches"] or [], full):
                m["player_of_match"] = f["player_of_match"]
    return row


@router.get("/challenge/{slug}/match/{n}")
def challenge_match(slug: str, n: int, conn=Depends(get_conn)) -> dict[str, Any]:
    """One match in full: scorecards and ball-by-ball commentary."""
    row = conn.execute("SELECT match_json FROM sim_results WHERE context = 'xi' AND ref = %s AND match_no = %s",
                       (slug, n)).fetchone()
    if row is None:
        raise HTTPException(404, "Match not found")
    return with_award(row["match_json"])


# ------------------------------------------------------------------ daily leaderboard

BOARD_SIZE = 50


@router.get("/leaderboard/{fmt}")
def daily_board(fmt: XIFormat, day: date | None = None, draft: str | None = None,
                conn=Depends(get_conn)) -> dict[str, Any]:
    """The daily challenge leaderboard for one format and day (default today):
    the top 50 by points, then run difference, then who played first. ``draft``:
    your daily draft's id, to find your own entry wherever it ranks."""
    day = day or _today()
    ranked = """SELECT draft_id, slug, name, won, lost, tied, drawn, points, run_diff, created_at,
                       RANK() OVER (ORDER BY points DESC, run_diff DESC) AS rank
                FROM xi_daily_entries WHERE format = %s AND day = %s"""
    rows = conn.execute(f"{ranked} ORDER BY rank, created_at LIMIT %s", (fmt, day, BOARD_SIZE)).fetchall()
    total = conn.execute("SELECT count(*) AS n FROM xi_daily_entries WHERE format = %s AND day = %s",
                         (fmt, day)).fetchone()["n"]
    you = None
    if draft:
        you = conn.execute(f"SELECT * FROM ({ranked}) r WHERE draft_id = %s", (fmt, day, draft)).fetchone()

    def public(r: dict) -> dict:
        return {"rank": r["rank"], "name": r["name"], "slug": r["slug"], "won": r["won"], "lost": r["lost"],
                "tied": r["tied"], "drawn": r["drawn"], "points": r["points"], "run_diff": r["run_diff"],
                "you": bool(draft) and r["draft_id"] == draft}

    return {"format": fmt, "day": day.isoformat(), "today": _today().isoformat(), "total": total,
            "rows": [public(r) for r in rows], "you": public(you) if you else None}


@router.put("/leaderboard/entries/{draft_id}/name")
def name_entry(draft_id: str, req: EntryName, conn=Depends(get_conn)) -> dict[str, Any]:
    """Put a nickname on your daily entry (whoever holds the draft id can)."""
    name = " ".join(req.name.split())
    if len(name) < 2:
        raise HTTPException(422, "Pick a name of at least 2 characters.")
    row = conn.execute("UPDATE xi_daily_entries SET name = %s WHERE draft_id = %s RETURNING draft_id",
                       (name, draft_id)).fetchone()
    if row is None:
        raise HTTPException(404, "No daily entry for that draft.")
    conn.commit()
    return {"ok": True, "name": name}
