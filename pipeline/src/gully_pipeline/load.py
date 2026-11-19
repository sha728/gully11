"""Load player tables from DuckDB into Postgres.

Drops and recreates the player tables (api/db/schema/players.sql) and bulk
copies every row in one transaction, so the API never sees a half-loaded state.
"""

from __future__ import annotations

import os
from pathlib import Path

import duckdb
import psycopg

from .paths import PIPELINE_ROOT

REPO_ROOT = PIPELINE_ROOT.parent
SCHEMA_SQL = REPO_ROOT / "api" / "db" / "schema" / "players.sql"

# Parents before children (foreign keys).
TABLES = ["players", "player_format_stats", "player_season_stats", "player_phase_stats"]


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
            for table in TABLES:
                rel = duck.execute(f"SELECT * FROM {table}")
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
