"""Captaincy records from Wikipedia, for the simulator's tactical captains.

Sources (English Wikipedia, CC BY-SA 4.0): "List of Indian Premier League
captains" and each Test nation's "List of … captains" page (men's Test, ODI and
T20I sections). Output: ``captains.csv`` with one row per captain per format:
matches captained, won, lost, tied, drawn, no result, the page revision, and our
player id (Cricsheet players) or legend id (pre-2001 greats) where they match.

Tables differ between pages (column order, a "Total" row per captain in Test
tables, tooltips in headers), so columns are found by their headings, and a
table with "Total" rows is read from those rows only.
"""

from __future__ import annotations

import csv
import re
from urllib.parse import unquote
from pathlib import Path

import duckdb
import mwparserfromhell as mwp

from .legends import fetch_wikitext
from .paths import DB_PATH, PIPELINE_ROOT

OUT = PIPELINE_ROOT.parent / "api" / "src" / "gully_api" / "sim" / "data" / "captains.csv"
LEGENDS_CSV = PIPELINE_ROOT / "reference" / "legends.csv"

IPL_PAGE = "List of Indian Premier League captains"
NATION_PAGES = [f"List of {c} national cricket captains" for c in
                ("India", "Australia", "South Africa", "New Zealand", "Pakistan", "Sri Lanka",
                 "Bangladesh", "Zimbabwe", "Afghanistan")] + \
               ["List of England cricket captains", "List of West Indies cricket captains"]

# Links in captain tables that aren't people: teams, tours, series, seasons.
NOT_A_PERSON = re.compile(r"\b(cricket team|cricket(?!er)|in \w+ in|tour|series|season|trophy|cup|history|test|list of|"
                          r"world xi|league|championship|tournament|ground|stadium)\b", re.I)

# Plain links to countries (an opposition written as [[New Zealand]]).
PLACES = {"England", "Australia", "India", "Pakistan", "South Africa", "New Zealand", "West Indies",
          "Sri Lanka", "Bangladesh", "Zimbabwe", "Afghanistan", "Ireland", "Kenya", "Scotland",
          "Netherlands", "United Arab Emirates", "Canada", "Namibia", "Nepal", "Oman", "United States",
          "Hong Kong", "Wales", "Jamaica", "Barbados", "Trinidad and Tobago", "Guyana"}

COLUMN = {
    "played": "matches", "matches": "matches", "mat": "matches", "p": "matches", "m": "matches",
    "tests": "matches", "odis": "matches", "t20is": "matches", "games": "matches",
    "won": "won", "w": "won", "wins": "won",
    "lost": "lost", "l": "lost", "losses": "lost",
    "tied": "tied", "t": "tied", "tie": "tied", "ties": "tied",
    "drawn": "drawn", "d": "drawn", "draw": "drawn", "drawn/tied": "drawn", "draws": "drawn", "d/t": "drawn",
    "nr": "nr", "no result": "nr", "n/r": "nr", "noresult": "nr",
}


def _format_of(heading: str) -> str | None:
    h = heading.lower()
    if any(w in h for w in ("women", "youth", "vice", "u19", "under-19", "tournament")):
        return None
    if "test" in h:
        return "Test"
    if "twenty20" in h or "t20" in h:
        return "T20I"
    if "one day" in h or "one-day" in h or "odi" in h:
        return "ODI"
    return None


def _sections(wikitext: str) -> list[tuple[str, str]]:
    """(format, body) for each men's Test/ODI/T20I section, first occurrence only
    (pages repeat the headings for women's and youth cricket further down)."""
    parts = re.split(r"^(={2,4}[^=\n].*?={2,4})\s*$", wikitext, flags=re.M)
    out, seen, in_women = [], set(), False
    for i in range(1, len(parts), 2):
        heading = parts[i].strip("= ").strip()
        level = len(parts[i]) - len(parts[i].lstrip("="))
        if level == 2:
            in_women = "women" in heading.lower() or "youth" in heading.lower()
        fmt = _format_of(heading)
        if fmt and not in_women and fmt not in seen:
            seen.add(fmt)
            out.append((fmt, parts[i + 1]))
    return out


def _header_label(cell: str) -> str:
    code = mwp.parse(cell)
    for t in code.filter_templates():
        if t.name.strip().lower() in ("tooltip", "abbr", "abbreviation"):
            return str(t.get(1).value).strip().lower()
    text = code.strip_code()
    text = re.sub(r"<br\s*/?>", " ", text)
    return re.sub(r"\s+", " ", text).strip().lower()


def _split(line: str) -> list[str]:
    # "|| a || b" continues a row: drop both leading bars.
    body = line[2:] if line.startswith(("||", "!!")) else line[1:]
    parts = re.split(r"\|\||!!", body)
    cells = []
    for p in parts:
        span = re.match(r'^\s*(?:[a-z]+="?[^|]*?"?\s*)+\|(?!\|)', p)
        if span and "[[" not in span.group(0):
            p = p[span.end():]
        cells.append(p.strip())
    return cells


def _clean(cell: str) -> mwp.wikicode.Wikicode:
    """A cell without footnotes: names inside <ref>s and {{refn}}s ("Smith stood
    in for Cummins") aren't the captain of the row."""
    code = mwp.parse(cell)
    for tag in code.filter_tags(recursive=False):
        if str(tag.tag).lower() == "ref":
            code.remove(tag)
    for t in code.filter_templates(recursive=False):
        if t.name.strip().lower() in ("refn", "efn", "sfn", "ref label", "note", "notetag", "#tag:ref"):
            code.remove(t)
    return code


def _person(cell: str) -> tuple[str, str] | None:
    """(article title, display name) of the first player in a cell: a
    {{sortname|First|Last|...}} template or a plain link."""
    code = _clean(cell)
    for t in code.filter_templates():
        if t.name.strip().lower() == "sortname" and t.has(1) and t.has(2):
            name = f"{str(t.get(1).value).strip()} {str(t.get(2).value).strip()}".strip()
            if t.has(3) and str(t.get(3).value).strip():
                return str(t.get(3).value).strip(), name
            if t.has("dab"):
                return f"{name} ({str(t.get('dab').value).strip()})", name
            return name, name
    for link in code.filter_wikilinks():
        target = str(link.title).strip()
        if ":" in target or NOT_A_PERSON.search(target) or target in PLACES:
            continue
        name = str(link.text).strip() if link.text else target.split(" (")[0]
        return target.replace("_", " "), re.sub(r"\s+", " ", mwp.parse(name).strip_code())
    return None


def _int(cell: str) -> int | None:
    s = mwp.parse(cell).strip_code().replace("'''", "").replace("*", "").strip()
    return int(s) if re.fullmatch(r"\d{1,3}", s) else None


def _table_rows(table: str) -> tuple[list[str], list[list[str]]]:
    rows = re.split(r"\n\|-[^\n]*", table)
    header: list[str] = []
    body: list[list[str]] = []
    for row in rows:
        lines = [ln.strip() for ln in row.strip().splitlines() if ln.strip().startswith(("|", "!"))
                 and not ln.strip().startswith(("|+", "|}", "{|"))]
        cells: list[str] = []
        is_header = bool(lines) and all(ln.startswith("!") for ln in lines)
        for ln in lines:
            cells += _split(ln)
        if not cells:
            continue
        if is_header and not header:
            labels = [_header_label(c) for c in cells]
            if any(COLUMN.get(lb) for lb in labels):
                header = labels
                continue
        body.append(cells)
    return header, body


def parse_section(body: str) -> dict[str, dict]:
    """{article: record} for one format section."""
    out: dict[str, dict] = {}
    for m in re.finditer(r"\{\|(.*?)\n\|\}", body, flags=re.S):
        header, rows = _table_rows(m.group(1))
        stats = [COLUMN.get(h) for h in header]
        numeric = [s for s in stats if s]
        if "matches" not in numeric:
            continue
        # Test tables have a "Total" row per captain (series rows above it); a
        # single "Total" at the bottom of an ODI/T20I table is the team's, skipped.
        totals = sum(any("total" in mwp.parse(c).strip_code().lower() for c in r[:4]) for r in rows)
        has_totals = totals >= 3
        current = None
        for r in rows:
            who = next((p for p in (_person(c) for c in r) if p), None)
            if who:
                current = who
            labels = [mwp.parse(c).strip_code().lower() for c in r[:4]]
            if any("grand total" in lb for lb in labels):
                continue                  # the whole team, not a captain
            is_total = any("total" in lb for lb in labels)
            if has_totals != is_total:
                continue
            if current is None:
                continue                  # e.g. a grand total for the whole team
            # Numbers after the name (or after "Total") map onto the stat columns in order.
            start = 0
            for i, c in enumerate(r):
                if (who and _person(c) == who) or "total" in mwp.parse(c).strip_code().lower():
                    start = i + 1
                    break
            nums = [n for n in (_int(c) for c in r[start:]) if n is not None]
            if len(nums) < 2:
                continue
            rec = dict(zip(numeric, nums))
            title, name = current
            agg = out.setdefault(title, {"name": name, "matches": 0, "won": 0, "lost": 0, "tied": 0, "drawn": 0, "nr": 0})
            for k in ("matches", "won", "lost", "tied", "drawn", "nr"):
                agg[k] += rec.get(k, 0)
            current = None                # each total (or row) belongs to one captain
    return {t: r for t, r in out.items() if r["matches"] > 0}


def parse_ipl(wikitext: str) -> dict[str, dict]:
    """The IPL page: one table, a row per captain with a career total."""
    for m in re.finditer(r"\{\|(.*?)\n\|\}", wikitext, flags=re.S):
        header, rows = _table_rows(m.group(1))
        if "matches" not in [COLUMN.get(h) for h in header]:
            continue
        out = {}
        stats = [COLUMN.get(h) for h in header]
        for r in rows:
            who = _person(r[0]) if r else None
            if not who:
                continue
            # Cells line up with the header here: read each stat by its column.
            rec = {"name": who[1], "matches": 0, "won": 0, "lost": 0, "tied": 0, "drawn": 0, "nr": 0}
            for s, c in zip(stats, r):
                if s and (n := _int(c)) is not None:
                    rec[s] = n
            if rec["matches"]:
                out[who[0]] = rec
        if out:
            return out
    return {}


def legend_id(name: str) -> str:
    """Same id the pipeline gives legends (aggregate.py): 'L-' + slugged name."""
    return "L-" + re.sub(r"(^-|-$)", "", re.sub(r"[^a-z0-9]+", "-", name.lower()))


def resolve_redirects(titles: list[str]) -> dict[str, str]:
    """Wikipedia's canonical title for each (``Mahendra Singh Dhoni`` -> ``MS Dhoni``),
    50 per API call, no page content."""
    import httpx
    from .legends import API, wiki_user_agent
    out = {t: t for t in titles}
    with httpx.Client(headers={"User-Agent": wiki_user_agent()}, timeout=60) as client:
        for i in range(0, len(titles), 50):
            batch = titles[i:i + 50]
            q = client.get(API, params={"action": "query", "titles": "|".join(batch), "redirects": 1,
                                        "format": "json", "formatversion": 2}).raise_for_status().json()["query"]
            step = {m["from"]: m["to"] for m in q.get("normalized", [])}
            hop = {m["from"]: m["to"] for m in q.get("redirects", [])}
            for t in batch:
                n = step.get(t, t)
                out[t] = hop.get(n, n)
    return out


def _match(rows: list[dict], db_path: Path = DB_PATH) -> None:
    with duckdb.connect(str(db_path), read_only=True) as con:
        players = con.execute("SELECT id, wikipedia_title, full_name FROM players").fetchall()
    by_title = {t: pid for pid, t, _ in players if t}
    by_name: dict[str, set] = {}
    for pid, _, full in players:
        if full:
            by_name.setdefault(full.lower(), set()).add(pid)
    legends = {}
    if LEGENDS_CSV.exists():
        with LEGENDS_CSV.open(encoding="utf-8") as f:
            for r in csv.DictReader(f):
                lid = legend_id(r["name"])
                title = unquote(r.get("source_url", "").rsplit("/wiki/", 1)[-1].split("?")[0]).replace("_", " ")
                if title:
                    legends[title] = lid
                legends.setdefault(r["name"], lid)
    canonical = resolve_redirects(sorted({r["article"] for r in rows}))
    for r in rows:
        r["article"] = canonical.get(r["article"], r["article"])
        pid = by_title.get(r["article"])
        if pid is None:
            options = by_name.get(r["name"].lower(), set())
            pid = next(iter(options)) if len(options) == 1 else None
        r["player_id"] = pid or ""
        r["legend_id"] = legends.get(r["article"]) or legends.get(r["name"]) or ""


def build() -> dict:
    pages = fetch_wikitext([IPL_PAGE] + NATION_PAGES)
    rows: list[dict] = []
    for title, page in pages.items():
        src = f"https://en.wikipedia.org/w/index.php?oldid={page['revid']}"
        if title == IPL_PAGE:
            found = {"IPL": parse_ipl(page["wikitext"])}
        else:
            found = {fmt: parse_section(body) for fmt, body in _sections(page["wikitext"])}
        for fmt, recs in found.items():
            for article, rec in recs.items():
                rows.append({"format": fmt, "article": article, **rec, "source": src})
    # A player who captained more than one nation (rare) or appears twice: add up.
    merged: dict[tuple, dict] = {}
    for r in rows:
        key = (r["format"], r["article"])
        if key in merged:
            for k in ("matches", "won", "lost", "tied", "drawn", "nr"):
                merged[key][k] += r[k]
        else:
            merged[key] = dict(r)
    rows = sorted(merged.values(), key=lambda r: (r["format"], -r["matches"]))
    _match(rows)
    # Only captains we can place in a game: a Cricsheet player or a legend.
    rows = [r for r in rows if r["player_id"] or r["legend_id"]]
    # Results can't add up to more than the matches: such a row was misread. (Ties
    # are left out: a T20 tie settled by a super over is also counted as a win.)
    bad = [r for r in rows if r["won"] + r["lost"] + r["drawn"] + r["nr"] > r["matches"]]
    rows = [r for r in rows if r not in bad]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    cols = ["format", "article", "name", "matches", "won", "lost", "tied", "drawn", "nr", "player_id", "legend_id", "source"]
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    return {"rows": rows, "dropped": bad}
