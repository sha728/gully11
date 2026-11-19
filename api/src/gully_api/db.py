from collections.abc import Iterator

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from .settings import settings

def _configure(conn) -> None:
    # Default word-similarity threshold (0.6) misses one-letter-swap typos such as
    # "bumrha" -> "JJ Bumrah" (0.57); 0.4 keeps those while dropping most noise.
    conn.execute("SET pg_trgm.word_similarity_threshold = 0.4")
    conn.commit()


pool = ConnectionPool(
    settings.database_url,
    min_size=1,
    max_size=10,
    open=False,
    configure=_configure,
    kwargs={"row_factory": dict_row},
)


def get_conn() -> Iterator:
    """FastAPI dependency: borrow a pooled connection for one request."""
    with pool.connection() as conn:
        yield conn
