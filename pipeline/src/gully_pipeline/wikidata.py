"""Full names and Wikipedia article titles for players, via Wikidata.

Cricsheet names players by initials ("RG Sharma"), so fans searching "Rohit
Sharma" need the full name. One SPARQL query maps every ESPNcricinfo player ID
(Wikidata property P2697) to its English label and English Wikipedia article.
The article titles are also the input for reading batting/bowling styles from
Wikipedia infoboxes later. Wikidata content is CC0.
"""

from __future__ import annotations

import csv
from pathlib import Path

import httpx

from .legends import REF_DIR, wiki_user_agent

NAMES_CSV = REF_DIR / "wikidata_players.csv"
ENDPOINT = "https://query.wikidata.org/sparql"
QUERY = """SELECT ?cricinfo ?label ?article WHERE {
  ?p wdt:P2697 ?cricinfo .
  OPTIONAL { ?p rdfs:label ?label FILTER(lang(?label) = "en") }
  OPTIONAL { ?article schema:about ?p ; schema:isPartOf <https://en.wikipedia.org/> }
}"""
WIKI_PREFIX = "https://en.wikipedia.org/wiki/"


def fetch_names(out: Path = NAMES_CSV) -> int:
    r = httpx.post(ENDPOINT, data={"query": QUERY, "format": "json"}, timeout=300,
                   headers={"User-Agent": wiki_user_agent(),
                            "Accept": "application/sparql-results+json"})
    r.raise_for_status()
    rows: dict[str, tuple[str, str]] = {}
    for b in r.json()["results"]["bindings"]:
        cid = b["cricinfo"]["value"].strip()
        label = b.get("label", {}).get("value", "")
        article = b.get("article", {}).get("value", "")
        title = httpx.URL(article).path.removeprefix("/wiki/").replace("_", " ") if article else ""
        # Keep the row with the most information if an ID appears twice.
        if cid not in rows or (title and not rows[cid][1]):
            rows[cid] = (label, title)
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["cricinfo_id", "name_en", "wikipedia_title"])
        for cid in sorted(rows, key=lambda x: (len(x), x)):
            w.writerow([cid, *rows[cid]])
    return len(rows)
