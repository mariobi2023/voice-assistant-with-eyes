"""Tiny migration runner (no extra framework).

Every file in server/migrations/ named NNNN_description.sql is one migration.
The table schema_migrations remembers which ones were applied, so each file runs exactly once,
in number order. Each file runs in its own transaction: it is applied completely or not at all.

Run:   python -m app.migrate        (the server also runs it at startup)
"""
import logging

import psycopg

from app import config

log = logging.getLogger("migrate")

MIGRATIONS_DIR = config.SERVER_DIR / "migrations"


def ensure_migrations_table(conn):
    """Create the bookkeeping table the first time."""
    conn.execute(
        """CREATE TABLE IF NOT EXISTS schema_migrations (
               version    TEXT PRIMARY KEY,
               applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
           )"""
    )


def applied_versions(conn):
    """Names of the migration files already applied."""
    rows = conn.execute("SELECT version FROM schema_migrations").fetchall()
    return {row[0] for row in rows}


def pending_migrations(done):
    """Migration files not applied yet, sorted by their number."""
    files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    return [f for f in files if f.name not in done]


def apply_migrations():
    """Apply every pending migration. Returns the list of file names applied."""
    applied = []
    # autocommit=True: we open one explicit transaction per migration file below.
    with psycopg.connect(config.DATABASE_URL, autocommit=True) as conn:
        ensure_migrations_table(conn)
        for path in pending_migrations(applied_versions(conn)):
            sql = path.read_text(encoding="utf-8")
            with conn.transaction():  # all of the file, or nothing
                conn.execute(sql)
                conn.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (path.name,))
            log.info("Applied migration %s", path.name)
            applied.append(path.name)
    if not applied:
        log.info("Database schema is up to date")
    return applied


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    apply_migrations()
