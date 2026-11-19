"""Load player tables from DuckDB into Postgres.

Drops and recreates the player tables (api/db/schema/players.sql) and bulk
copies every row in one transaction, so the API never sees a half-loaded state.
"""

from __future__ import annotations

import os
from pathlib import Path

import duckdb
import psycopg

from .aggregate import DEFAULT_HALF_LIFE
from .paths import PIPELINE_ROOT

REPO_ROOT = PIPELINE_ROOT.parent
SCHEMA_SQL = REPO_ROOT / "api" / "db" / "schema" / "players.sql"

# Parents before children (foreign keys). Postgres gets only the current form
# ratings (latest as_of, default half-life); the full grid stays in DuckDB.
TABLES = {
    "players": "SELECT * FROM players",
    "player_format_stats": "SELECT * FROM player_format_stats",
    "player_season_stats": "SELECT * FROM player_season_stats",
    "player_phase_stats": "SELECT * FROM player_phase_stats",
    "player_phase_form": f"""
        SELECT * EXCLUDE (pid), pid AS player_id FROM player_phase_form
        WHERE as_of = (SELECT max(as_of) FROM player_phase_form)
          AND half_life = {DEFAULT_HALF_LIFE}""",
    "venues": "SELECT * FROM venues",
    "venue_format_stats": "SELECT * FROM venue_format_stats",
    "player_dismissals": "SELECT * FROM player_dismissals",
    "player_venue_stats": "SELECT * FROM player_venue_stats",
}


def database_url() -> str:
    if url := os.environ.get("DATABASE_URL"):
        return url
    env = REPO_ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            key, _, value = line.partition("=")
            if key.strip() == "DATABASE_URL":
                return value.strip()
    raise SystemExit("DATABASE_URL not set (copy .env.example to .env)")


def load(db_path: Path, url: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    with duckdb.connect(str(db_path), read_only=True) as duck, psycopg.connect(url) as pg:
        with pg.cursor() as cur:
            cur.execute(SCHEMA_SQL.read_text())
            for table, query in TABLES.items():
                rel = duck.execute(query)
                cols = [c[0] for c in rel.description]
                col_list = ", ".join(cols)
                n = 0
                with cur.copy(f"COPY {table} ({col_list}) FROM STDIN") as copy:
                    while batch := rel.fetchmany(50_000):
                        for row in batch:
                            copy.write_row(row)
                        n += len(batch)
                counts[table] = n
            cur.execute("ANALYZE")
        pg.commit()
    return counts
