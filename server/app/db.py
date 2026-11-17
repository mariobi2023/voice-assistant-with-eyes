"""PostgreSQL access: every SQL query of the app lives in this file.

A connection pool is shared by the threads (ingest, retention, web requests):
each function borrows a connection, runs its query and gives it back.
`with pool.connection()` commits on success and rolls back on error.
"""
import logging
import threading

from pgvector.psycopg import register_vector
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from app import config

log = logging.getLogger("db")

_pool = None
_pool_lock = threading.Lock()  # two threads must not create two pools at the same time


def _configure_connection(conn):
    """Run on each new connection: teach psycopg the pgvector 'vector' type (numpy array <-> vector)."""
    register_vector(conn)


def get_pool():
    """Create the connection pool the first time it is needed, then reuse it."""
    global _pool
    with _pool_lock:
        if _pool is None:
            if not config.DATABASE_URL:
                raise RuntimeError("DATABASE_URL is missing: copy .env.example to .env and fill it in")
            _pool = ConnectionPool(config.DATABASE_URL, min_size=1, max_size=config.DB_POOL_SIZE,
                                   timeout=config.DB_TIMEOUT_SECONDS, configure=_configure_connection,
                                   open=True)
        return _pool


def close_pool():
    """Close all connections (on shutdown)."""
    global _pool
    with _pool_lock:
        if _pool is not None:
            _pool.close()
            _pool = None


# ---------- frames ----------

def insert_frame(info):
    """Save a kept frame (info dict from ingest) and return its new id."""
    with get_pool().connection() as conn:
        row = conn.execute(
            """INSERT INTO frames (captured_at, image_path, sharpness, brightness, enhanced)
               VALUES (%s, %s, %s, %s, %s)
               RETURNING id""",
            (info["captured_at"], info["image_path"], info["sharpness"], info["brightness"],
             info.get("enhanced", False)),
        ).fetchone()
    return row[0]


def update_frame_vision(frame_id, analysis, embedding):
    """Fill in OCR text, objects, caption and embedding of a frame (after vision ran).
    Returns False if the frame no longer exists (already deleted by retention)."""
    with get_pool().connection() as conn:
        cur = conn.execute(
            """UPDATE frames
               SET ocr_text = %s, ocr_conf = %s, objects = %s, caption = %s, embedding = %s
               WHERE id = %s""",
            (analysis["ocr_text"], analysis["ocr_conf"], Jsonb(analysis["objects"]),
             analysis["caption"], embedding, frame_id),
        )
        return cur.rowcount == 1


def count_frames():
    """How many frames are stored (shown by GET /status)."""
    with get_pool().connection() as conn:
        return conn.execute("SELECT count(*) FROM frames").fetchone()[0]


def delete_frames_older_than(minutes):
    """Delete frame rows older than `minutes` and return their image paths (to delete the files)."""
    with get_pool().connection() as conn:
        rows = conn.execute(
            """DELETE FROM frames
               WHERE captured_at < now() - %s * interval '1 minute'
               RETURNING image_path""",
            (minutes,),
        ).fetchall()
    return [row[0] for row in rows]
