"""Full names and Wikipedia article titles for players, via Wikidata.

Cricsheet names players by initials ("RG Sharma"), so fans searching "Rohit
Sharma" need the full name. One SPARQL query maps every ESPNcricinfo player ID
(Wikidata property P2697) to its English label and English Wikipedia article.
The article titles are also the input for reading batting/bowling styles from
Wikipedia infoboxes later. Wikidata content is CC0.

It also gives a cricket nationality for players the ball-by-ball data can't:
Cricsheet's country is the side a player appeared for in internationals, so
uncapped players (county pros, IPL uncapped Indians) and nations Cricsheet has
no matches for (Afghanistan) have none. Wikidata's "country for sport" (P1532)
is used first, then country of citizenship (P27), translated to Cricsheet's
team names (United Kingdom -> England, Jamaica -> West Indies, ...). Only ever a
fallback: a player's own international record wins.
"""

from __future__ import annotations

import csv
from pathlib import Path

import httpx

from .legends import REF_DIR, wiki_user_agent

__all__ = ["NAMES_CSV", "fetch_names", "fetch_countries", "team_for"]

NAMES_CSV = REF_DIR / "wikidata_players.csv"
ENDPOINT = "https://query.wikidata.org/sparql"
QUERY = """SELECT ?cricinfo ?label ?article WHERE {
  ?p wdt:P2697 ?cricinfo .
  OPTIONAL { ?p rdfs:label ?label FILTER(lang(?label) = "en") }
  OPTIONAL { ?article schema:about ?p ; schema:isPartOf <https://en.wikipedia.org/> }
}"""
WIKI_PREFIX = "https://en.wikipedia.org/wiki/"
# Item ids only: asking for labels in the same query times out on ~35k players.
COUNTRY_QUERY = """SELECT ?cricinfo ?sport ?cit WHERE {
  ?p wdt:P2697 ?cricinfo .
  OPTIONAL { ?p wdt:P1532 ?sport }
  OPTIONAL { ?p wdt:P27 ?cit }
}"""

# Wikidata country labels that aren't Cricsheet team names. Caribbean nations play
# as West Indies; the home nations other than Scotland and Ireland as England.
TEAM_OF = {
    "United Kingdom": "England", "United Kingdom of Great Britain and Ireland": "England",
    "Wales": "England", "Great Britain": "England",
    "Kingdom of the Netherlands": "Netherlands", "Kingdom of Denmark": "Denmark",
    "United States": "United States of America", "People's Republic of China": "China",
    "Republic of Ireland": "Ireland", "State of Palestine": None,
    **{c: "West Indies" for c in (
        "Jamaica", "Barbados", "Guyana", "Trinidad and Tobago", "Antigua and Barbuda", "Saint Lucia",
        "Saint Vincent and the Grenadines", "Saint Kitts and Nevis", "Grenada", "Dominica", "Montserrat",
        "Anguilla", "British Virgin Islands", "United States Virgin Islands", "Sint Maarten",
        "West Indies Federation")},
}
# Colonial-era states: not a cricket nationality for a modern player.
NOT_A_TEAM = {"British Raj", "Dominion of India", "Dominion of Pakistan", "Dominion of Ceylon",
              "Union of South Africa", "Federation of Rhodesia and Nyasaland", "Rhodesia",
              "Southern Rhodesia", "Colony of Natal", "Cape Colony", "British Ceylon"}


def team_for(sport: list[str], citizenship: list[str]) -> str | None:
    """A cricket nationality from Wikidata country labels: the sporting country
    if it names one team, else citizenship if that does. Two different teams at
    the same level (a dual citizen with no sporting country) gives None rather
    than a guess."""
    def teams(labels: list[str]) -> set[str]:
        out = set()
        for label in labels:
            if label in NOT_A_TEAM:
                continue
            team = TEAM_OF.get(label, label)
            if team:
                out.add(team)
        return out

    for group in (teams(sport), teams(citizenship)):
        if len(group) == 1:
            return group.pop()
        if len(group) > 1:
            return None
    return None


def _sparql(query: str) -> list[dict]:
    r = httpx.post(ENDPOINT, data={"query": query, "format": "json"}, timeout=300,
                   headers={"User-Agent": wiki_user_agent(),
                            "Accept": "application/sparql-results+json"})
    r.raise_for_status()
    return r.json()["results"]["bindings"]


def fetch_countries() -> dict[str, str]:
    """ESPNcricinfo id -> cricket nationality (Cricsheet team name), where Wikidata has one."""
    qid = lambda uri: uri.rsplit("/", 1)[-1]   # noqa: E731
    sport: dict[str, list[str]] = {}
    cit: dict[str, list[str]] = {}
    for b in _sparql(COUNTRY_QUERY):
        cid = b["cricinfo"]["value"].strip()
        for key, store in (("sport", sport), ("cit", cit)):
            if key in b:
                q = qid(b[key]["value"])
                if q not in store.setdefault(cid, []):
                    store[cid].append(q)
    items = {q for store in (sport, cit) for qs in store.values() for q in qs}
    labels: dict[str, str] = {}
    items_list = sorted(items)
    for i in range(0, len(items_list), 400):
        values = " ".join(f"wd:{q}" for q in items_list[i:i + 400])
        for b in _sparql(f'SELECT ?c ?l WHERE {{ VALUES ?c {{ {values} }} '
                         f'?c rdfs:label ?l FILTER(lang(?l) = "en") }}'):
            labels[qid(b["c"]["value"])] = b["l"]["value"]
    out = {}
    for cid in set(sport) | set(cit):
        team = team_for([labels.get(q, "") for q in sport.get(cid, [])],
                        [labels.get(q, "") for q in cit.get(cid, [])])
        if team:
            out[cid] = team
    return out


def fetch_names(out: Path = NAMES_CSV) -> int:
    rows: dict[str, tuple[str, str]] = {}
    for b in _sparql(QUERY):
        cid = b["cricinfo"]["value"].strip()
        label = b.get("label", {}).get("value", "")
        article = b.get("article", {}).get("value", "")
        title = httpx.URL(article).path.removeprefix("/wiki/").replace("_", " ") if article else ""
        # Keep the row with the most information if an ID appears twice.
        if cid not in rows or (title and not rows[cid][1]):
            rows[cid] = (label, title)
    countries = fetch_countries()
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["cricinfo_id", "name_en", "wikipedia_title", "country"])
        for cid in sorted(set(rows) | set(countries), key=lambda x: (len(x), x)):
            w.writerow([cid, *rows.get(cid, ("", "")), countries.get(cid, "")])
    return len(rows)
