"""PostgreSQL access: every SQL query of the app lives in this file.

A connection pool is shared by the threads (ingest, retention, web requests):
each function borrows a connection, runs its query and gives it back.
`with pool.connection()` commits on success and rolls back on error.
"""
import threading

from pgvector.psycopg import register_vector
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from app import config

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


def update_frame_objects(frame_id, objects, caption):
    """Fast vision lane: save the YOLO objects + caption of a frame.
    Returns the row's (ocr_text, caption) after the update, so the caller can build the
    embedding text, or None if the frame no longer exists (already deleted by retention)."""
    with get_pool().connection() as conn:
        return conn.execute(
            "UPDATE frames SET objects = %s, caption = %s WHERE id = %s RETURNING ocr_text, caption",
            (Jsonb(objects), caption, frame_id),
        ).fetchone()


def update_frame_ocr(frame_id, ocr_text, ocr_conf):
    """Slow vision lane: save the OCR text of a frame.
    Returns (ocr_text, caption) after the update, or None if the frame no longer exists."""
    with get_pool().connection() as conn:
        return conn.execute(
            "UPDATE frames SET ocr_text = %s, ocr_conf = %s WHERE id = %s RETURNING ocr_text, caption",
            (ocr_text, ocr_conf, frame_id),
        ).fetchone()


def update_frame_embedding(frame_id, embedding):
    """Save the embedding of "objects + text" (recomputed each time one of the two lanes adds data)."""
    with get_pool().connection() as conn:
        conn.execute("UPDATE frames SET embedding = %s WHERE id = %s", (embedding, frame_id))


def count_frames():
    """How many frames are stored (shown by GET /status)."""
    with get_pool().connection() as conn:
        return conn.execute("SELECT count(*) FROM frames").fetchone()[0]


# ---------- frames: retrieval for the assistant ----------
# Every search returns dicts with the same keys, plus "age_seconds" (how long ago it was seen).

_FRAME_COLUMNS = """id, captured_at, image_path, ocr_text, objects, caption,
                    EXTRACT(EPOCH FROM now() - captured_at)::float AS age_seconds"""


def _fetch_dicts(sql, params):
    """Run a SELECT and return the rows as a list of dicts (column name -> value)."""
    with get_pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            return cur.execute(sql, params).fetchall()


def newest_frame():
    """The most recent frame, or None. Fallback for 'what is in front of me?' when there is no live frame."""
    rows = _fetch_dicts(f"SELECT {_FRAME_COLUMNS} FROM frames ORDER BY captured_at DESC LIMIT 1", ())
    return rows[0] if rows else None


def get_frame(frame_id):
    """One frame by id, or None. Used for the live frame stored for 'what is in front of me?'."""
    rows = _fetch_dicts(f"SELECT {_FRAME_COLUMNS} FROM frames WHERE id = %s", (frame_id,))
    return rows[0] if rows else None


def search_similar(query_vec, seconds, limit):
    """Frames from the last `seconds`, closest in MEANING to the question (cosine similarity)."""
    return _fetch_dicts(
        f"""SELECT {_FRAME_COLUMNS}, 1 - (embedding <=> %s) AS similarity
            FROM frames
            WHERE captured_at > now() - %s * interval '1 second' AND embedding IS NOT NULL
            ORDER BY embedding <=> %s
            LIMIT %s""",
        (query_vec, seconds, query_vec, limit),
    )


def search_ocr_keywords(words, seconds, limit):
    """Frames from the last `seconds` whose OCR text contains one of `words` (any case). Newest first."""
    patterns = [f"%{w}%" for w in words]
    return _fetch_dicts(
        f"""SELECT {_FRAME_COLUMNS}
            FROM frames
            WHERE captured_at > now() - %s * interval '1 second' AND ocr_text ILIKE ANY(%s)
            ORDER BY captured_at DESC
            LIMIT %s""",
        (seconds, patterns, limit),
    )


def search_frames_with_text(query_vec, seconds, limit):
    """Frames from the last `seconds` that contain ANY text, most similar to the question first
    (frames not embedded yet come last, newest first)."""
    return _fetch_dicts(
        f"""SELECT {_FRAME_COLUMNS}, 1 - (embedding <=> %s) AS similarity
            FROM frames
            WHERE captured_at > now() - %s * interval '1 second' AND ocr_text <> ''
            ORDER BY embedding <=> %s NULLS LAST, captured_at DESC
            LIMIT %s""",
        (query_vec, seconds, query_vec, limit),
    )


# ---------- qa_log ----------

def insert_qa(language, question, answer, frame_ids, confidence, latency_ms):
    """Save one question/answer (dashboard history + tests). Returns the new id."""
    with get_pool().connection() as conn:
        row = conn.execute(
            """INSERT INTO qa_log (language, question, answer, frame_ids, confidence, latency_ms)
               VALUES (%s, %s, %s, %s, %s, %s)
               RETURNING id""",
            (language, question, answer, frame_ids, confidence, latency_ms),
        ).fetchone()
    return row[0]


# ---------- Dashboard lists ----------

def list_frames(start=None, end=None, limit=200):
    """Stored frames for the timeline, OLDEST first (all columns except the embedding).
    start/end (optional datetimes) limit the time range; `limit` keeps only the newest ones."""
    return _fetch_dicts(
        """SELECT * FROM (
               SELECT id, captured_at, image_path, ocr_text, ocr_conf, objects, caption,
                      sharpness, brightness, enhanced
               FROM frames
               WHERE (%(start)s::timestamptz IS NULL OR captured_at >= %(start)s)
                 AND (%(end)s::timestamptz IS NULL OR captured_at <= %(end)s)
               ORDER BY captured_at DESC
               LIMIT %(limit)s
           ) newest
           ORDER BY captured_at ASC""",
        {"start": start, "end": end, "limit": limit},
    )


def list_qa(limit=100):
    """Past questions and answers, NEWEST first."""
    return _fetch_dicts(
        """SELECT id, asked_at, language, question, answer, frame_ids, confidence, latency_ms
           FROM qa_log
           ORDER BY asked_at DESC
           LIMIT %s""",
        (limit,),
    )


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
