"""Build reference/legends.csv: career Test/ODI figures for pre-2001 greats.

Source: the ``Infobox cricketer`` on each player's English Wikipedia article
(CC BY-SA 4.0). Every row records the exact article revision it was read from,
so each figure can be traced and re-checked. Fetches 50 titles per API call.

Gaps (not in the infobox): batting strike rate. Bowling economy and strike rate
are derived (economy = 6 * avg * wickets / balls; SR = balls / wickets).
"""

from __future__ import annotations

import csv
import os
import re
from pathlib import Path

import httpx
import mwparserfromhell as mwp

from .paths import PIPELINE_ROOT

# Wikimedia's robot policy (https://w.wiki/4wJS) rejects API clients whose user agent
# has no contact details (403). Set WIKIMEDIA_CONTACT (a URL or email) in .env.
def wiki_user_agent() -> str:
    contact = os.environ.get("WIKIMEDIA_CONTACT") or _dotenv("WIKIMEDIA_CONTACT")
    if not contact:
        raise SystemExit("Set WIKIMEDIA_CONTACT (project URL or email) in .env; Wikimedia "
                         "requires contact details in the User-Agent: https://w.wiki/4wJS")
    return f"Gully11/0.1 (cricket stats project; {contact}) httpx"


def _dotenv(key: str) -> str | None:
    env = PIPELINE_ROOT.parent / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            k, _, v = line.partition("=")
            if k.strip() == key:
                return v.strip() or None
    return None

REF_DIR = PIPELINE_ROOT / "reference"
SEED_CSV = REF_DIR / "legends_seed.csv"
LEGENDS_CSV = REF_DIR / "legends.csv"

API = "https://en.wikipedia.org/w/api.php"
FORMATS = {"Test": "test", "ODI": "odi"}  # infobox column label -> debut/last key prefix

COLUMNS = [
    "name", "country", "format", "matches", "runs", "bat_avg", "bat_sr", "hundreds",
    "fifties", "highest", "highest_not_out", "balls_bowled", "wickets", "bowl_avg",
    "bowl_econ", "bowl_sr", "best_bowling", "catches", "stumpings", "role", "role_source",
    "batting_hand", "bowling_arm", "bowling_type", "bowling_style_raw", "role_raw", "opener",
    "format_start", "format_end", "era_start", "era_end", "stats_as_of",
    "source", "source_url", "derived_fields",
]


# ---------------------------------------------------------------- fetching

def fetch_wikitext(titles: list[str]) -> dict[str, dict]:
    """Return {requested_title: {title, revid, wikitext}} via the MediaWiki API."""
    out: dict[str, dict] = {}
    with httpx.Client(headers={"User-Agent": wiki_user_agent()}, timeout=60) as client:
        for i in range(0, len(titles), 50):
            batch = titles[i:i + 50]
            r = client.get(API, params={
                "action": "query", "prop": "revisions", "rvprop": "content|ids",
                "rvslots": "main", "titles": "|".join(batch), "redirects": 1,
                "format": "json", "formatversion": 2,
            })
            r.raise_for_status()
            q = r.json()["query"]
            alias = {t: t for t in batch}
            for step in ("normalized", "redirects"):
                for m in q.get(step, []):
                    for req, cur in alias.items():
                        if cur == m["from"]:
                            alias[req] = m["to"]
            pages = {p["title"]: p for p in q["pages"]}
            for req, final in alias.items():
                p = pages.get(final)
                if not p or "missing" in p:
                    raise SystemExit(f"Wikipedia article not found: {req!r}")
                rev = p["revisions"][0]
                out[req] = {"title": p["title"], "revid": rev["revid"],
                            "wikitext": rev["slots"]["main"]["content"]}
    return out


# ---------------------------------------------------------------- parsing

def infobox(wikitext: str) -> dict[str, str]:
    """Infobox cricketer params, keys normalised (lowercase, '_' for space and '/')."""
    for t in mwp.parse(wikitext).filter_templates():
        if t.name.strip().lower().startswith("infobox cricketer"):
            out = {}
            for p in t.params:
                key = re.sub(r"[\s/]+", "_", str(p.name).strip().lower())
                out[key] = str(p.value).strip()
            return out
    raise ValueError("no Infobox cricketer")


def plain(value: str | None) -> str:
    """Wikitext -> plain text (keeps list items separated by '; ')."""
    if not value:
        return ""
    code = mwp.parse(value)
    items = []
    for t in code.filter_templates(recursive=False):
        if t.name.strip().lower() in ("ubl", "unbulleted list", "plainlist", "flatlist"):
            items += [mwp.parse(str(p.value)).strip_code().strip() for p in t.params]
    text = "; ".join(i for i in items if i) or code.strip_code()
    return re.sub(r"\s+", " ", text).strip()


def num(value: str | None) -> float | None:
    s = plain(value).replace(",", "").replace("*", "").strip()
    if not s or s in {"–", "-", "—", "n/a"}:
        return None
    m = re.match(r"^-?\d+(\.\d+)?", s)
    return float(m.group()) if m else None


def year(value: str | None) -> int | None:
    m = re.search(r"\d{4}", plain(value))
    return int(m.group()) if m else None


def split_pair(value: str | None) -> tuple[float | None, float | None]:
    """'51/68' -> (51, 68); '115/–' -> (115, None)."""
    parts = plain(value).split("/")
    if len(parts) != 2:
        return None, None
    return num(parts[0]), num(parts[1])


def batting_hand(text: str) -> str | None:
    t = text.lower()
    return "L" if t.startswith("left") else "R" if t.startswith("right") else None


BOWLING_TYPES = [  # checked in order; first match wins
    ("left-arm wrist-spin", r"left[- ]arm (unorthodox|wrist|chinaman)|chinaman"),
    ("left-arm orthodox", r"left[- ]arm (orthodox|slow|spin)|slow left[- ]arm"),
    ("leg-spin", r"leg[- ]?(break|spin)|googly"),
    ("off-spin", r"off[- ]?(break|spin)"),
    ("fast-medium", r"fast[- ]medium|medium[- ]fast"),
    ("fast", r"\bfast\b"),
    ("medium", r"medium|seam"),
]


def bowling(text: str) -> tuple[str | None, str | None]:
    """First listed style -> (arm L/R, normalised type)."""
    first = text.split(";")[0].lower()
    arm = "L" if "left" in first else "R" if "right" in first else None
    for label, pattern in BOWLING_TYPES:
        if re.search(pattern, first):
            return arm, label
    return arm, None


def role(text: str) -> str | None:
    t = text.lower()
    if "wicket" in t or "keeper" in t:
        return "WK"
    if "all" in t and "round" in t:
        return "AR"
    if "bowl" in t:
        return "BOWL"
    if "bat" in t:
        return "BAT"
    return None


def rows_for(page: dict, country: str, role_override: str | None = None) -> list[dict]:
    box = infobox(page["wikitext"])
    hand_raw = plain(box.get("batting"))
    bowl_raw = plain(box.get("bowling"))
    arm, btype = bowling(bowl_raw)
    role_raw = plain(box.get("role"))
    player_role, role_source = role(role_raw), "wikipedia"
    if player_role is None and role_override:
        player_role, role_source = role_override, "manual"
    as_of = " ".join(x for x in (plain(box.get("date")), plain(box.get("year"))) if x)

    rows = []
    n_cols = int(num(box.get("columns")) or 4)
    for i in range(1, n_cols + 1):
        label = plain(box.get(f"column{i}"))
        label = {"Tests": "Test", "ODIs": "ODI"}.get(label, label)
        if label not in FORMATS:
            continue
        g = lambda k: box.get(f"{k}{i}")  # noqa: E731
        hundreds, fifties = split_pair(g("100s_50s"))
        catches, stumpings = split_pair(g("catches_stumpings"))
        balls, wkts, bavg = num(g("deliveries")), num(g("wickets")), num(g("bowl_avg"))
        econ = sr = None
        derived = []
        if balls and wkts and bavg:
            econ = round(6 * bavg * wkts / balls, 2)
            sr = round(balls / wkts, 1)
            derived = ["bowl_econ", "bowl_sr"]
        prefix = FORMATS[label]
        top = plain(g("top_score"))
        rows.append({
            "name": page["title"].split(" (")[0],
            "country": country,
            "format": label,
            "matches": num(g("matches")),
            "runs": num(g("runs")),
            "bat_avg": num(g("bat_avg")),
            "bat_sr": None,
            "hundreds": hundreds,
            "fifties": fifties,
            "highest": num(g("top_score")),
            "highest_not_out": "*" in top if top else None,
            "balls_bowled": balls,
            "wickets": wkts,
            "bowl_avg": bavg,
            "bowl_econ": econ,
            "bowl_sr": sr,
            "best_bowling": plain(g("best_bowling")) or None,
            "catches": catches,
            "stumpings": stumpings,
            "role": player_role,
            "role_source": role_source if player_role else None,
            "batting_hand": batting_hand(hand_raw),
            "bowling_arm": arm,
            "bowling_type": btype,
            "bowling_style_raw": bowl_raw or None,
            "role_raw": role_raw or None,
            "format_start": year(box.get(f"{prefix}_debut_year")),
            # Single-match careers often omit the "last" year: fall back to debut.
            "format_end": year(box.get(f"last_{prefix}_year"))
                          or year(box.get(f"{prefix}_debut_year")),
            "stats_as_of": as_of or None,
            "source": "wikipedia",
            "source_url": "https://en.wikipedia.org/w/index.php?oldid="
                          f"{page['revid']}",
            "derived_fields": ";".join(derived) or None,
        })
    starts = [r["format_start"] for r in rows if r["format_start"]]
    ends = [r["format_end"] for r in rows if r["format_end"]]
    for r in rows:
        r["era_start"] = min(starts) if starts else None
        r["era_end"] = max(ends) if ends else None
    return rows


def _fmt(v):
    if isinstance(v, float) and v.is_integer():
        return int(v)
    return "" if v is None else v


def build_legends(seed: Path = SEED_CSV, out: Path = LEGENDS_CSV) -> list[dict]:
    with seed.open(newline="", encoding="utf-8") as f:
        seeds = list(csv.DictReader(f))
    pages = fetch_wikitext([s["wikipedia_title"] for s in seeds])
    rows = []
    for s in seeds:
        player_rows = rows_for(pages[s["wikipedia_title"]], s["country"],
                               s.get("role_override") or None)
        if not player_rows:
            raise SystemExit(f"No Test/ODI columns in infobox: {s['wikipedia_title']}")
        # Infoboxes rarely say who opened; the seed marks it by hand.
        opener = (s.get("opener") or "").strip().lower() == "true"
        rows += [{**r, "opener": opener} for r in player_rows]
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({k: _fmt(r.get(k)) for k in COLUMNS})
    return rows
