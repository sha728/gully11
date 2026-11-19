import logging
from collections.abc import Iterator
from pathlib import Path

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from .settings import settings

# Created on app startup and closed on shutdown. A closed psycopg pool cannot be
# reopened, so each startup (e.g. each test client) gets a fresh one.
_pool: ConnectionPool | None = None


def _configure(conn) -> None:
    # Default word-similarity threshold (0.6) misses one-letter-swap typos such as
    # "bumrha" -> "JJ Bumrah" (0.57); 0.4 keeps those while dropping most noise.
    conn.execute("SET pg_trgm.word_similarity_threshold = 0.4")
    conn.commit()


def open_pool() -> None:
    global _pool
    _pool = ConnectionPool(
        settings.database_url,
        open=True,
        min_size=1,
        max_size=10,
        configure=_configure,
        kwargs={"row_factory": dict_row},
    )


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


def get_conn() -> Iterator:
    """FastAPI dependency: borrow a pooled connection for one request."""
    if _pool is None:
        raise RuntimeError("database pool not open (app startup did not run)")
    with _pool.connection() as conn:
        yield conn


APP_SCHEMA = Path(__file__).resolve().parents[2] / "db" / "schema" / "app.sql"


def apply_app_schema() -> None:
    """Create the API's own tables (xi_challenges, sim_results) if missing. Safe to
    run on every start; a database that isn't up yet is logged, not fatal."""
    if _pool is None:
        return
    try:
        with _pool.connection(timeout=5) as conn:
            conn.execute(APP_SCHEMA.read_text())
    except Exception as e:  # pragma: no cover - startup without a database
        logging.getLogger(__name__).warning("app schema not applied: %s", e)


def connection():
    """A pooled connection outside a request (background tasks)."""
    if _pool is None:
        raise RuntimeError("database pool not open (app startup did not run)")
    return _pool.connection()
