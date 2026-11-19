"""XI Builder endpoints."""

from __future__ import annotations

import random
from datetime import date, datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field

from ..db import get_conn
from . import service
from .service import FORMATS, DraftError

router = APIRouter(prefix="/xi", tags=["xi"])

XIFormat = Literal["Test", "ODI", "T20I", "IPL"]


class SpinRequest(BaseModel):
    format: XIFormat
    seed: int | None = Field(None, ge=0, lt=2**32, description="omit for a random draw")


class SeriesRequest(BaseModel):
    format: XIFormat
    seed: int = Field(ge=0, lt=2**32)
    picks: list[str] = Field(min_length=11, max_length=11, description="one id per spin, in slot order")
    daily: bool = False


def _today() -> date:
    return datetime.now(timezone.utc).date()


@router.get("/formats")
def formats() -> dict[str, Any]:
    """Formats with their eras, what a spin draws (nation or franchise) and the opponent."""
    return {f: {"eras": list(s.eras), "unit": s.unit, "opponent": service.WORLD_XI[f]["name"],
                "rules": {"keeper": "at least 1", "bowling_options": "at least 5",
                          **({"overseas": f"at most {service.MAX_OVERSEAS_IPL}"} if f == "IPL" else {})}}
            for f, s in FORMATS.items()}


@router.post("/spin")
def spin(req: SpinRequest, conn=Depends(get_conn)) -> dict[str, Any]:
    """Eleven seeded spins with their candidate lists."""
    seed = req.seed if req.seed is not None else random.randrange(2**32)
    return {"format": req.format, "seed": seed, "spins": service.spins(conn, req.format, seed)}


@router.get("/daily/{format}")
def daily(format: XIFormat, conn=Depends(get_conn)) -> dict[str, Any]:
    """Today's challenge: the same spins for everyone (UTC day)."""
    day = _today()
    seed = service.daily_seed(format, day)
    return {"format": format, "seed": seed, "date": day.isoformat(),
            "spins": service.spins(conn, format, seed)}


@router.post("/series")
def series(req: SeriesRequest, conn=Depends(get_conn)) -> dict[str, Any]:
    """Validate the draft, play 5 seeded matches against the World XI, save the
    result under a share slug. Re-submitting the same XI returns the same slug."""
    if req.daily and req.seed != service.daily_seed(req.format, _today()):
        raise HTTPException(422, "That seed isn't today's daily challenge.")
    try:
        out = service.play_series(conn, req.format, req.seed, req.picks)
    except DraftError as e:
        raise HTTPException(422, str(e)) from e
    full = out.pop("_full")
    conn.execute(
        """INSERT INTO xi_challenges (slug, format, seed, daily, picks, xi, opponent, result, matches)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (slug) DO NOTHING""",
        (out["slug"], req.format, req.seed, _today() if req.daily else None, Jsonb(req.picks),
         Jsonb(out["xi"]), out["opponent"], Jsonb(out["result"]), Jsonb(out["matches"])))
    for i, m in enumerate(full, start=1):
        conn.execute(
            "INSERT INTO sim_results (context, ref, match_no, match_json) VALUES ('xi', %s, %s, %s) "
            "ON CONFLICT (context, ref, match_no) DO NOTHING", (out["slug"], i, Jsonb(m)))
    return out


@router.get("/challenge/{slug}")
def challenge(slug: str, conn=Depends(get_conn)) -> dict[str, Any]:
    """A saved series, plus its spins so a friend can draft from the same draw."""
    row = conn.execute("SELECT * FROM xi_challenges WHERE slug = %s", (slug,)).fetchone()
    if row is None:
        raise HTTPException(404, "Challenge not found")
    row["spins"] = service.spins(conn, row["format"], row["seed"])
    row["daily"] = row["daily"].isoformat() if row["daily"] else None
    return row


@router.get("/challenge/{slug}/match/{n}")
def challenge_match(slug: str, n: int, conn=Depends(get_conn)) -> dict[str, Any]:
    """One match in full: scorecards and ball-by-ball commentary."""
    row = conn.execute("SELECT match_json FROM sim_results WHERE context = 'xi' AND ref = %s AND match_no = %s",
                       (slug, n)).fetchone()
    if row is None:
        raise HTTPException(404, "Match not found")
    return row["match_json"]
