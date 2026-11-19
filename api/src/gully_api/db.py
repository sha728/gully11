from collections.abc import Iterator

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
