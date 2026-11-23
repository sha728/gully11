"""The IPL 2026 auction from Wikipedia, for the auction game's mini mode.

Source: "List of 2026 Indian Premier League personnel changes" on English
Wikipedia (CC BY-SA 4.0). Two tables come out, each row stamped with the page
revision it was read from:

* ``ipl2026_retained.csv``: every franchise's retained squad with salaries;
* ``ipl2026_auction.csv``: every player sold at the auction, by registration
  number (the order they came up), with set, base price, buyer and price.

Players are matched to our ids by Wikipedia article (Wikidata gives each player's
title), then by full name and country. Unmatched players are kept with an empty
id and listed by the command, so they can be checked by hand.
"""

from __future__ import annotations

import csv
import difflib
import re
from pathlib import Path

import duckdb
import mwparserfromhell as mwp

from .legends import fetch_wikitext
from .paths import DB_PATH, PIPELINE_ROOT

PAGE = "List of 2026 Indian Premier League personnel changes"
OUT_DIR = PIPELINE_ROOT.parent / "api" / "src" / "gully_api" / "auction" / "data"
RETAINED_CSV = OUT_DIR / "ipl2026_retained.csv"
AUCTION_CSV = OUT_DIR / "ipl2026_auction.csv"

TEAMS = {
    "Chennai Super Kings": "CSK", "Delhi Capitals": "DC", "Gujarat Titans": "GT",
    "Kolkata Knight Riders": "KKR", "Lucknow Super Giants": "LSG", "Mumbai Indians": "MI",
    "Punjab Kings": "PBKS", "Rajasthan Royals": "RR", "Royal Challengers Bengaluru": "RCB",
    "Sunrisers Hyderabad": "SRH",
}
COUNTRIES = {
    "IND": "India", "AUS": "Australia", "ENG": "England", "SA": "South Africa", "NZ": "New Zealand",
    "WI": "West Indies", "WIN": "West Indies", "SL": "Sri Lanka", "AFG": "Afghanistan", "BAN": "Bangladesh", "ZIM": "Zimbabwe",
    "IRE": "Ireland", "NED": "Netherlands", "SCO": "Scotland", "USA": "United States of America",
    "NEP": "Nepal", "UAE": "United Arab Emirates", "PAK": "Pakistan", "NAM": "Namibia",
}
SET_ROLE = {"BA": "BAT", "AL": "AR", "WK": "WK", "FA": "BOWL", "SP": "BOWL"}
ACC_ROLE = {"batter": "BAT", "all-rounder": "AR", "wicket-keeper": "WK", "wicketkeeper": "WK",
            "bowler": "BOWL", "fast bowler": "BOWL", "spin bowler": "BOWL", "spinner": "BOWL"}


def _cells(row: str) -> list[mwp.wikicode.Wikicode]:
    """A wikitable row's cells (``|`` and ``!`` cells, ``||`` separated)."""
    cells = []
    for line in row.strip().splitlines():
        line = line.strip()
        if not line or line[0] not in "|!" or line.startswith(("|+", "|}", "{|")):
            continue
        for part in re.split(r"\|\||!!", line[1:]):
            if re.match(r'^\s*(scope|style|rowspan|colspan|class)="?[^|]*"?\s*\|', part):
                part = part.split("|", 1)[1]
            cells.append(mwp.parse(part.strip()))
    return cells


def _person(cell) -> dict | None:
    for t in cell.filter_templates():
        if t.name.strip().lower() == "sortname":
            first, last = str(t.get(1).value).strip(), str(t.get(2).value).strip()
            name = f"{first} {last}".strip()
            article = name
            if t.has(3) and str(t.get(3).value).strip():
                article = str(t.get(3).value).strip()
            elif t.has("dab"):
                article = f"{name} ({str(t.get('dab').value).strip()})"
            return {"name": name, "article": article}
    return None


def _country(cell) -> str | None:
    for t in cell.filter_templates():
        if t.name.strip().lower() in ("cr", "crw", "cricon"):
            code = str(t.get(1).value).strip().upper()
            return COUNTRIES.get(code, code)
    return None


def _lakh(cell) -> int | None:
    """``{{INRConvert|18|c}}`` (crore) or ``|50|l`` (lakh), or a bare number in lakh."""
    for t in cell.filter_templates():
        if t.name.strip().lower() == "inrconvert":
            n = float(str(t.get(1).value).strip())
            unit = str(t.get(2).value).strip().lower() if t.has(2) else "l"
            return round(n * (100 if unit.startswith("c") else 1))
    text = cell.strip_code().replace(",", "").strip()
    return int(float(text)) if re.fullmatch(r"\d+(\.\d+)?", text) else None


def _team(cell) -> str | None:
    text = cell.strip_code().strip()
    return TEAMS.get(text)


def _tables(wikitext: str) -> list[tuple[str, str]]:
    """(caption, body) for each wikitable."""
    out = []
    for m in re.finditer(r"\{\|(.*?)\n\|\}", wikitext, flags=re.S):
        body = m.group(1)
        cap = re.search(r"^\|\+(.*)$", body, flags=re.M)
        out.append((cap.group(1).strip() if cap else "", body))
    return out


def parse(wikitext: str) -> tuple[list[dict], list[dict]]:
    retained, sold = [], []
    for caption, body in _tables(wikitext):
        rows = re.split(r"\n\|-[^\n]*", body)[1:]
        team = next((code for name, code in TEAMS.items() if f"[[{name}|" in caption), None)
        if team:                                                  # a retained squad
            for row in rows:
                c = _cells(row)
                if len(c) < 4 or not (who := _person(c[1])):
                    continue
                retained.append({"team": team, **who, "country": _country(c[2]), "salary_lakh": _lakh(c[3])})
            continue
        m = re.search(r"\(([A-Z]+)(\d+)\)", caption)
        accelerated = caption.lower().startswith("accelerated")
        with_role = bool(re.search(r"^!.*\|\s*Role\s*$", body, flags=re.M))   # marquee sets list the role
        if not (m or accelerated):
            continue
        for row in rows:
            c = _cells(row)
            if len(c) < 7 or not (who := _person(c[1])):
                continue
            no = int(re.match(r"\d+", c[0].strip_code().strip()).group())
            if accelerated or with_role:
                role_text = c[3].strip_code().strip().lower()
                capped = c[5].strip_code().strip().lower() == "capped"
                base, team, price = _lakh(c[6]), _team(c[7]), _lakh(c[8])
                prev = _team(c[9]) if len(c) > 9 else None
                set_code = "ACC" if accelerated else f"{m.group(1)}{m.group(2)}"
                role = ACC_ROLE.get(role_text)
            else:
                code = m.group(1)
                capped = not code.startswith("U")
                base, team, price = _lakh(c[4]), _team(c[5]), _lakh(c[6])
                prev = _team(c[7]) if len(c) > 7 else None
                set_code, role = f"{code}{m.group(2)}", SET_ROLE.get(code.lstrip("U"))
            sold.append({"no": no, "set": set_code, **who, "country": _country(c[2]), "role": role,
                         "capped": capped, "base_lakh": base, "team": team, "price_lakh": price,
                         "prev_team": prev})
    sold.sort(key=lambda r: r["no"])
    return retained, sold


def _link_person(cell) -> dict | None:
    """A player written as a plain wikilink: ``[[Harry Brook]]`` or ``[[A (cricketer)|A]]``."""
    links = cell.filter_wikilinks()
    if links:
        article = str(links[0].title).strip()
        text = str(links[0].text).strip() if links[0].text else article
        return {"name": re.sub(r"\s*\(.*?\)$", "", text), "article": article}
    text = cell.strip_code().strip()
    return {"name": text, "article": text} if text else None


def parse_2024(wikitext: str) -> list[dict]:
    """The 2024 auction: one wide table of everyone sold, with the set in its own column."""
    sold = []
    for _caption, body in _tables(wikitext):
        if "Auctioned Price" not in body:
            continue
        for row in re.split(r"\n\|-[^\n]*", body)[1:]:
            c = _cells(row)
            if len(c) >= 11 and _country(c[3]) and not _country(c[4]):   # accelerated round: no "set no." cell
                c = [c[0], c[0], mwp.parse("ACC"), *c[2:]]
            if len(c) < 11 or not (who := _link_person(c[3])):
                continue
            set_code = c[2].strip_code().strip()
            sold.append({"no": int(re.match(r"\d+", c[0].strip_code().strip()).group()), "set": set_code,
                         **who, "country": _country(c[4]),
                         "role": ACC_ROLE.get(c[5].strip_code().strip().lower(),
                                              "BAT" if c[5].strip_code().strip().lower() == "batsman" else None),
                         "capped": c[7].strip_code().strip().lower() == "capped",
                         "base_lakh": _lakh(c[8]), "team": _team(c[9]), "price_lakh": _lakh(c[10])})
    sold.sort(key=lambda r: r["no"])
    return sold


def match(rows: list[dict], db_path: Path = DB_PATH) -> list[str]:
    """Fill ``player_id``; returns the names that didn't match."""
    with duckdb.connect(str(db_path), read_only=True) as con:
        players = con.execute(
            "SELECT id, full_name, wikipedia_title, country, name, unique_name FROM players").fetchall()
    by_title = {t: pid for pid, _, t, *_ in players if t}
    by_name: dict[str, list[tuple[str, str | None]]] = {}
    for pid, full, _, country, short, unique in players:
        # Uncapped players often have no Wikidata entry: Cricsheet's own name is
        # then usually the full one ("Priyansh Arya").
        for n in {full, short, unique} - {None}:
            by_name.setdefault(n.lower(), []).append((pid, country))

    initials: dict[str, list[tuple[str, str, str | None]]] = {}
    for pid, _, _, country, short, _ in players:
        parts = short.split()
        if len(parts) == 2 and parts[0].isupper() and len(parts[0]) <= 3:
            initials.setdefault(parts[1].lower(), []).append((pid, parts[0].lower(), country))

    def unique_match(name: str, country: str | None) -> str | None:
        options = {p for p, c in by_name.get(name, []) if c in (None, country)}
        return options.pop() if len(options) == 1 else None

    missing = []
    for r in rows:
        name = r["name"].lower()
        pid = by_title.get(r["article"]) or unique_match(name, r["country"])
        if pid is None:
            # Spelling differences ("Abhishek" / "Abishek"): a close name sharing the surname.
            surname = name.split()[-1]
            near = difflib.get_close_matches(name, [n for n in by_name if n.split()[-1] == surname], n=2, cutoff=0.88)
            if len(near) == 1:
                pid = unique_match(near[0], r["country"])
        if pid is None:
            # Cricsheet initials ("DV Malewar" for Danish Malewar), only when exactly one fits.
            first, surname = name.split()[0], name.split()[-1]
            fits = {p for p, short, c in initials.get(surname, [])
                    if short[0] == first[0] and c in (None, r["country"])}
            pid = fits.pop() if len(fits) == 1 else None
        r["player_id"] = pid or ""
        if not pid:
            missing.append(r["name"])
    return missing


def _write(path: Path, rows: list[dict], cols: list[str], revid: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols + ["source"], extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({**r, "source": f"https://en.wikipedia.org/w/index.php?oldid={revid}"})


HISTORY_CSV = OUT_DIR / "ipl_auction_history.csv"
HISTORY_COLS = ["year", "no", "set", "name", "country", "role", "capped", "base_lakh", "team",
                "price_lakh", "player_id"]


def build_history() -> dict:
    """Everyone sold at the 2024 and 2025 auctions (the 2026 one is ``ipl2026_auction.csv``),
    for fitting the auction game's price model."""
    pages = {y: fetch_wikitext([f"List of {y} Indian Premier League personnel changes"])
             [f"List of {y} Indian Premier League personnel changes"] for y in (2024, 2025)}
    rows = []
    for year, page in pages.items():
        sold = parse_2024(page["wikitext"]) if year == 2024 else parse(page["wikitext"])[1]
        missing = match(sold)
        for r in sold:
            rows.append({**r, "year": year, "source": f"https://en.wikipedia.org/w/index.php?oldid={page['revid']}"})
    with HISTORY_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=HISTORY_COLS + ["source"], extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    return {"rows": rows, "missing": [r["name"] for r in rows if not r["player_id"]]}


def build() -> dict:
    page = fetch_wikitext([PAGE])[PAGE]
    retained, sold = parse(page["wikitext"])
    missing = match(retained) + match(sold)
    _write(RETAINED_CSV, retained, ["team", "name", "country", "salary_lakh", "player_id"], page["revid"])
    _write(AUCTION_CSV, sold, ["no", "set", "name", "country", "role", "capped", "base_lakh", "team",
                               "price_lakh", "prev_team", "player_id"], page["revid"])
    return {"retained": retained, "sold": sold, "missing": missing, "revid": page["revid"]}
