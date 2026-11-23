"""Batting hand and bowling style for every player with a Wikipedia article.

Cricsheet's ball-by-ball data says who bowled each ball but not how: no batting
hand, no bowling style. English Wikipedia's "Infobox cricketer" has both
("batting = Left-handed", "bowling = Slow left-arm orthodox"). Only the lead
section is fetched (where the infobox lives), 50 articles per request, and the
result is cached in reference/player_styles.csv (Wikipedia text is CC BY-SA 4.0;
the app credits it). The build joins it on the ESPNcricinfo id.
"""

from __future__ import annotations

import csv
import time
from pathlib import Path

import duckdb
import httpx

from .legends import API, REF_DIR, batting_hand, bowling, infobox, plain, wiki_user_agent

STYLES_CSV = REF_DIR / "player_styles.csv"
COLUMNS = ["cricinfo_id", "wikipedia_title", "batting_hand", "bowling_arm", "bowling_type", "bowling_raw", "revid"]
SPIN_TYPES = ("off-spin", "leg-spin", "left-arm orthodox", "left-arm wrist-spin")


def _lead_sections(client: httpx.Client, titles: list[str]) -> dict[str, tuple[int, str]]:
    """{requested title: (revid, lead wikitext)} for up to 50 titles; missing pages are skipped."""
    r = client.get(API, params={
        "action": "query", "prop": "revisions", "rvprop": "content|ids", "rvslots": "main",
        "rvsection": 0, "titles": "|".join(titles), "redirects": 1, "format": "json", "formatversion": 2,
    })
    r.raise_for_status()
    q = r.json()["query"]
    alias = {t: t for t in titles}
    for step in ("normalized", "redirects"):
        for m in q.get(step, []):
            for req, cur in alias.items():
                if cur == m["from"]:
                    alias[req] = m["to"]
    pages = {p["title"]: p for p in q["pages"] if "revisions" in p}
    out = {}
    for req, final in alias.items():
        p = pages.get(final)
        if p:
            rev = p["revisions"][0]
            out[req] = (rev["revid"], rev["slots"]["main"]["content"])
    return out


def parse_styles(wikitext: str) -> dict | None:
    """Batting hand (L/R), bowling arm (L/R) and type from an article's infobox."""
    try:
        box = infobox(wikitext)
    except ValueError:
        return None
    bat = plain(box.get("batting"))
    bowl = plain(box.get("bowling"))
    arm, kind = bowling(bowl) if bowl else (None, None)
    if arm is None and kind in ("leg-spin", "off-spin"):
        arm = "R"     # the left-arm versions have their own names (orthodox, wrist-spin)
    return {"batting_hand": batting_hand(bat) if bat else None, "bowling_arm": arm,
            "bowling_type": kind, "bowling_raw": bowl.split(";")[0].strip() or None}


def fetch_styles(db_path: Path, out: Path = STYLES_CSV, pause: float = 0.5) -> dict[str, int]:
    """Fetch styles for every player in the built DuckDB with a Wikipedia title."""
    con = duckdb.connect(str(db_path), read_only=True)
    rows = con.execute("SELECT cricinfo_id, wikipedia_title FROM players "
                       "WHERE wikipedia_title IS NOT NULL AND cricinfo_id IS NOT NULL").fetchall()
    con.close()
    by_title: dict[str, list[str]] = {}
    for cid, title in rows:
        by_title.setdefault(title, []).append(cid)
    titles = sorted(by_title)
    found: list[dict] = []
    with httpx.Client(headers={"User-Agent": wiki_user_agent()}, timeout=60) as client:
        for i in range(0, len(titles), 50):
            batch = titles[i:i + 50]
            for attempt in range(3):
                try:
                    pages = _lead_sections(client, batch)
                    break
                except httpx.HTTPError:
                    if attempt == 2:
                        raise
                    time.sleep(5 * (attempt + 1))
            for title, (revid, text) in pages.items():
                s = parse_styles(text)
                if s and (s["batting_hand"] or s["bowling_type"]):
                    for cid in by_title[title]:
                        found.append({"cricinfo_id": cid, "wikipedia_title": title, **s, "revid": revid})
            time.sleep(pause)
    found.sort(key=lambda r: (len(r["cricinfo_id"]), r["cricinfo_id"]))
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, COLUMNS, lineterminator="\n")
        w.writeheader()
        w.writerows(found)
    return {"articles": len(titles), "with_styles": len(found),
            "batting_hand": sum(bool(r["batting_hand"]) for r in found),
            "bowling_type": sum(bool(r["bowling_type"]) for r in found)}
