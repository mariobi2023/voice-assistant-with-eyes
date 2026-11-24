-- Migration 0001: the two tables of the multimedia database (docs/ARCHITECTURE.md, section 7).
-- Never edit a migration that was already applied: add a new numbered file instead.

-- pgvector is enabled by setup_database.sql (superuser). IF NOT EXISTS makes this a no-op then.
CREATE EXTENSION IF NOT EXISTS vector;

-- One row per kept camera frame. The JPEG itself is on disk at image_path.
CREATE TABLE frames (
    id           SERIAL PRIMARY KEY,
    captured_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    image_path   TEXT NOT NULL,                -- "frames/20261116_153012_123.jpg" (relative to server/)
    ocr_text     TEXT NOT NULL DEFAULT '',     -- '' until OCR has run / when no text was found
    ocr_conf     REAL,                         -- NULL when there is no text
    objects      JSONB NOT NULL DEFAULT '[]',  -- [{"label":"door","conf":0.91,"box":[x,y,w,h]}], never NULL
    caption      TEXT NOT NULL DEFAULT '',     -- built from the object labels
    sharpness    REAL,
    brightness   REAL,
    enhanced     BOOLEAN NOT NULL DEFAULT FALSE,
    embedding    vector(384)                   -- multilingual MiniLM embedding, filled in step 3
);
CREATE INDEX frames_captured_at_idx ON frames (captured_at);                          -- time window search + retention
CREATE INDEX frames_embedding_idx ON frames USING hnsw (embedding vector_cosine_ops); -- similarity search

-- One row per question asked, for the dashboard history and the tests.
CREATE TABLE qa_log (
    id           SERIAL PRIMARY KEY,
    asked_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    language     TEXT NOT NULL,                -- "en", "fr" or "ar"
    question     TEXT NOT NULL,
    answer       TEXT NOT NULL,
    frame_ids    INT[] NOT NULL DEFAULT '{}',  -- frames used for the answer, never NULL
    confidence   REAL NOT NULL DEFAULT 0,      -- 0..1
    latency_ms   INT NOT NULL DEFAULT 0
);
CREATE INDEX qa_log_asked_at_idx ON qa_log (asked_at);
