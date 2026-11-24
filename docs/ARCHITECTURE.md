# Architecture — Voice Assistant With Eyes

Multimedia Database & Image Processing — Project Fall 2026/2027
"An AI That Describes the World Out Loud"

This document describes the system **as it is implemented**. Tunable values quoted here
live in `server/app/config.py`; if they change there, update them here too.

## 1. Goal

A phone camera streams live video to a server. The user asks a question by voice
("What's in front of me?", "What did that sign say?", "What was written on the door
I just passed?") and hears a short spoken answer. The server remembers recent frames
in a multimedia database (image + OCR text + objects + time + embedding).

Workflow: **Stream → Remember → Ask → Answer**

## 2. Hard rules (from the project brief)

| Rule | How the code enforces it |
|---|---|
| **No face recognition** | No identification library. Faces are only *detected* (OpenCV YuNet) and **blurred before the frame is written** to disk or the database (`privacy.py`). If blurring fails, the frame is dropped. YOLO "person" is a label only. |
| **Never say "safe"** | The model prompt forbids it **and** `remove_safe_claims()` (server) / `removeSafeClaims()` (app) delete any sentence with a "safe" word in EN/FR/AR. |
| **Say "I'm not sure"** | Weak retrieval → "I'm not sure" + short reason in the user's language, without calling the model. The model is told to reply exactly "I'm not sure" when unsure. |
| **Answer only from the camera** | The model only receives the retrieved frames, their OCR text and detected objects. |
| **At least two languages** | English, French, Arabic everywhere (STT, TTS, OCR, prompts, messages). |
| **Delete old frames** | Retention thread deletes rows **and** JPEG files older than 30 min (`retention.py`). |
| **Test only with people who agree** | Organisational rule for the test sessions. |

## 3. System diagram

```
┌──────────────────────┐   WebRTC (WHIP)   ┌───────────────────┐
│ MOBILE APP (Flutter) │ ────────────────► │ MediaMTX          │
│ camera, mic, TTS     │                   │ streaming server  │
└──┬────────────────▲──┘                   └──┬─────────────┬──┘
   │ HTTP POST /ask │ WS /ws                  │ RTSP        │ WebRTC (WHEP)
   │ (question+lang)│ warnings (to do)        ▼             ▼
   │                │              ┌──────────────────┐  ┌────────────────┐
   └────────────────┴────────────► │ BACKEND FastAPI  │◄─┤ DASHBOARD      │
      answer text ◄─────────────── │ ingest pipeline  │  │ React + Vite   │
                                   │ retrieval + VLM  │  │ polls every 5 s│
                                   └────────┬─────────┘  └────────────────┘
                                            ▼
                               PostgreSQL + pgvector
                               + frames/*.jpg on disk (faces blurred)
                                            │
                               VLM: Gemini API (main)
                                    Ollama local (fallback)
```

## 4. Tech stack

| Layer | Implemented with | Notes |
|---|---|---|
| Mobile app | Flutter (Android) + `flutter_webrtc`, `speech_to_text`, `flutter_tts`, `http`, `shared_preferences` | WebSocket via Dart's built-in `dart:io` |
| Streaming | MediaMTX (WHIP in, RTSP/WHEP out) | |
| Backend | Python 3.12, FastAPI, Uvicorn | CPU only (no GPU needed) |
| Frame selection | OpenCV (Laplacian variance), `imagehash` (pHash) | |
| Privacy | OpenCV `FaceDetectorYN` (YuNet, 2023mar) | detection + blur only |
| OCR (EN/FR/AR) | EasyOCR | two readers: `["en","fr"]` and `["ar","en"]` |
| Object detection | Ultralytics **YOLO-World** `yolov8s-worldv2.pt` with our own class list | COCO YOLO has no "door"/"stairs" |
| Embeddings | `paraphrase-multilingual-MiniLM-L12-v2` (384 dims) | multilingual: an Arabic question matches English text |
| Database | PostgreSQL + pgvector (HNSW, cosine) | own small migration runner |
| Vision-language model | Gemini `gemini-3.5-flash-lite` | fallback: Ollama `qwen2.5vl:3b` on CPU |
| Speech-to-text / TTS | Phone built-in (`speech_to_text`, `flutter_tts`) | |
| Dashboard | React 18 + Vite 5, WHEP player | REST polling every 5 s |

## 5. Streaming

```
Phone ──WHIP──► http://<server-ip>:8889/cam/whip       (publish)
MediaMTX ─────► rtsp://localhost:8554/cam               (backend reads with OpenCV, over TCP)
MediaMTX ─────► http://<server-ip>:8889/cam/whep        (dashboard live view)
```

- Ports: 8554 (RTSP), 8889 (WebRTC HTTP: WHIP/WHEP), 8189/udp (WebRTC media), 8000 (backend).
- The phone sends **video only** (the microphone stays free for speech recognition).
- The phone uses **one server IP** (from Settings) for MediaMTX and the backend.
- OpenCV can read H264, VP8 and VP9, **not AV1**. The backend logs the real codec if it cannot open the stream.
- If the decoded picture is pixel-identical for 2 s (decoder stuck after the sender changed
  resolution), the backend reconnects.
- Quick test without the app: open `http://localhost:8889/cam/publish` in a browser.

## 6. Ingest pipeline ("Remember")

Two background threads, so slow OCR never blocks the stream or `/ask`:

```
Ingest thread (ingest.py), ~2 frames checked per second (SAMPLE_FPS = 2):
1. Resize   to at most 960 px wide
2. Sharp?   Laplacian variance >= SHARPNESS_MIN (10)            else drop
3. New?     pHash distance to last kept frame >= HASH_MIN (5)  else drop
4. Privacy  detect faces (YuNet, score >= 0.7) and blur them    if this fails → drop
5. Save     JPEG to server/frames/<timestamp>.jpg + row in "frames" (no OCR yet)
6. Queue    frame → vision worker (queue of 5; when full the OLDEST waiting frame is skipped)

Vision thread (VisionWorker):
7. OCR      EasyOCR with the reader of the user's current language (confidence >= 0.3)
8. Objects  YOLO-World, our classes, confidence >= 0.25
9. Caption  built from the labels, e.g. "door, 2 chairs, exit sign" (no AI call per frame)
10. Embed   embedding of "Objects: <caption>. Text: <ocr>" → UPDATE the row
```

YOLO-World classes: door, stairs, person, chair, table, exit sign, elevator, car, bicycle, bus,
traffic light, stop sign, bench, trash can, window, sign, pole, escalator, toilet, sink, laptop,
bottle, cup, bag.

**Live frame for "now":** when the user asks about what is in front of them, the latest frame
read from the stream (at most 2 s old) is stored on demand, even if it looks like the last kept
frame, so the answer is about the current picture.

**Retention** (`retention.py`): every 60 s, delete rows older than `RETENTION_MINUTES` (30),
then their JPEG files, then any leftover JPEG older than that in `frames/`.

**Not implemented yet (bonus):** dark/blurry image enhancement (CLAHE / unsharp mask).
Brightness is measured and `DARK_MAX` (60) is defined, but `enhanced` is always `false`.

Thresholds are starting values and must be tuned on real footage.

## 7. Database schema

Created by `server/setup_database.sql` (role, database, pgvector) and
`server/migrations/0001_create_frames_and_qa_log.sql` (tables), applied automatically at startup.

```sql
CREATE TABLE frames (
    id           SERIAL PRIMARY KEY,
    captured_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    image_path   TEXT NOT NULL,                -- "frames/20261116_153012_123.jpg"
    ocr_text     TEXT NOT NULL DEFAULT '',
    ocr_conf     REAL,
    objects      JSONB NOT NULL DEFAULT '[]',  -- [{"label":"door","conf":0.91,"box":[x,y,w,h]}]
    caption      TEXT NOT NULL DEFAULT '',
    sharpness    REAL,
    brightness   REAL,
    enhanced     BOOLEAN NOT NULL DEFAULT FALSE,
    embedding    vector(384)
);
CREATE INDEX frames_captured_at_idx ON frames (captured_at);
CREATE INDEX frames_embedding_idx ON frames USING hnsw (embedding vector_cosine_ops);

CREATE TABLE qa_log (
    id           SERIAL PRIMARY KEY,
    asked_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    language     TEXT NOT NULL,
    question     TEXT NOT NULL,
    answer       TEXT NOT NULL,
    frame_ids    INT[] NOT NULL DEFAULT '{}',
    confidence   REAL NOT NULL DEFAULT 0,
    latency_ms   INT NOT NULL DEFAULT 0
);
```

Search by time **and** meaning (`db.search_similar`):

```sql
SELECT ..., 1 - (embedding <=> :qvec) AS similarity
FROM frames
WHERE captured_at > now() - :seconds * interval '1 second' AND embedding IS NOT NULL
ORDER BY embedding <=> :qvec
LIMIT 3;
```

## 8. Answer flow ("Ask" → "Answer")

```
question + language ("en" | "fr" | "ar", sent by the phone — never guessed)
  → 1. ROUTE     keywords decide the question type: "text", else "now", else "past"
  → 2. RETRIEVE  frames for that type (or decide "I'm not sure" without calling the model)
  → 3. GENERATE  Gemini, fallback Ollama, all within a 12 s deadline
  → 4. CHECK     remove any "safe" sentence (code, not only prompt)
  → 5. LOG       save in qa_log → return {answer, confidence, frame_ids} → phone speaks it
```

### Question types

| Type | Example keywords (EN/FR/AR) | Retrieval | Not sure when |
|---|---|---|---|
| **text** | sign, say, written, read · panneau, écrit · لافتة, مكتوب | Frames from the last 180 s whose OCR contains a word of the question; else recent frames with any text, most similar first | no frame with text in the window |
| **now** | now, in front of me, what do you see · maintenant, devant moi · الآن, أمامي | The live frame (stored on demand); else the newest stored frame | no frame newer than 5 s |
| **past** | anything else ("just passed", "earlier") | Top 3 frames of the last 180 s by embedding similarity | best similarity < `MIN_SIMILARITY` (0.20) |

### Model call and timing

- Phone timeout 15 s → server deadline **`ANSWER_DEADLINE_SECONDS` = 12 s**.
- Gemini gets at most 9 s. The 2 most relevant frames go as images (384 px wide, JPEG 70),
  the others as text only (OCR + objects). Minimal "thinking", temperature 0.2.
- Each request opens a new connection. If no answer after 5 s, the same request is sent again
  (max 2 copies) and the first good answer wins.
- If Gemini fails (error, HTTP 429 rate limit, no answer) → Ollama `qwen2.5vl:3b` with the
  time left (one 512 px image, needs at least 2 s left).
- If both fail → "I'm not sure. I can't analyse the image right now."
- Confidence: 0.85 (OCR keyword match), 0.8 (now), similarity (past), 0.6 (text fallback);
  capped at 0.3 if the model says "I'm not sure", 0.2 when we answer "I'm not sure" ourselves.

System prompt:

> You help a blind or visually impaired person.
> Answer ONLY from the provided images, OCR text and detected objects. Do not guess.
> Maximum 2 short sentences. Reply in {language}.
> Never say that anything is safe, and never judge whether something is safe or dangerous.
> If the evidence is unclear or missing, reply exactly: "{I'm not sure in that language}"
> Do not identify or describe who a person is (no names, no faces, no identity).

## 9. API endpoints

| Method | Path | Purpose | Status |
|---|---|---|---|
| POST | `/ask` | `{question (1-500 chars), language}` → `{answer, confidence, frame_ids}` | done |
| GET | `/status` | `{stream_connected, fps, frames_stored, model}` | done |
| GET | `/frames?from=&to=&limit=` | Stored frames, oldest first (newest `limit`, default 200) | done |
| GET | `/frames/{id}/image` | Frame JPEG (404 once deleted by retention) | done |
| GET | `/qa?limit=` | Past questions and answers, newest first | done |
| WS | `/ws` | Proactive warnings to the phone (and live updates to the dashboard) | **to do** |

Errors use FastAPI's format `{"detail": ...}`: 422 for an invalid request (e.g. empty or too
long question), 404 for a missing frame, 500 for a server error. CORS allows the dashboard at
`http://localhost:5173` and `http://127.0.0.1:5173` only.

### Warnings (`/ws`)

Warning message, read by the phone app (other message types are ignored by it):

```json
{"type": "warning", "data": {"text": "Warning: stairs ahead.", "language": "en"}}
```

- **App side (done):** connects to `ws://<server-ip>:8000/ws`, reconnects every 3 s, vibrates
  3 times and speaks the text; a warning that arrives during an answer is spoken right after
  it; never spoken while the microphone listens. Sentences with "safe" are removed. Mock mode
  simulates a warning every 30 s. The app shows "not available on this server yet" while the
  backend has no `/ws`.
- **Server side (to do):** send a warning when a frame shows e.g. a door or stairs ahead.
  The text must never say that something is "safe".

### Front-end configuration

- Dashboard: `dashboard/.env` → `VITE_BACKEND_URL`, `VITE_WHEP_URL`, `VITE_USE_MOCK`.
- App: Settings screen → server IP, language, mock mode (off by default).

## 10. Repository structure

```
voice-assistant-with-eyes/
├── README.md               # overview + how to run on Windows
├── CLAUDE.md               # rules and conventions for the code assistant
├── docs/
│   ├── ARCHITECTURE.md     # this file
│   ├── TEAM.md             # who built what
│   ├── PRESENTATION.md     # slide outline
│   └── project-brief.pdf
├── mobile/                 # Flutter app (lib/, test/)
├── mediamtx/
│   └── mediamtx.yml
├── server/
│   ├── app/
│   │   ├── main.py         # FastAPI routes, starts the pipeline
│   │   ├── config.py       # all thresholds, model names, keys from .env
│   │   ├── ingest.py       # RTSP reading, frame selection, vision worker thread
│   │   ├── privacy.py      # face detection + blur (no recognition)
│   │   ├── vision.py       # EasyOCR + YOLO-World + caption
│   │   ├── embeddings.py   # multilingual sentence embeddings
│   │   ├── db.py           # every SQL query (Postgres + pgvector)
│   │   ├── migrate.py      # applies migrations/*.sql once each
│   │   ├── assistant.py    # route → retrieve → Gemini/Ollama → "safe" check → log
│   │   ├── languages.py    # EN/FR/AR texts, keywords, "safe" patterns
│   │   └── retention.py    # delete old frames (rows + files)
│   ├── migrations/
│   ├── setup_database.sql
│   ├── requirements.txt
│   └── .env.example
└── dashboard/              # React + Vite (src/, .env.example)
```

## 11. Team ownership

| Area | Owner | Branch prefix |
|---|---|---|
| Mobile app, streaming, dashboard, warnings (app), tests, docs | Member A — Samer El Murr | `feature/mobile-*`, `feature/dashboard-*`, `docs/*` |
| Backend: ingest, images, multimedia DB, AI assistant, API | Member B — Mario Bouissa | `backend`, `feature/vision-*`, `feature/db-*`, `feature/assistant-*` |

Details: [TEAM.md](TEAM.md).

## 12. Build order and status

1. ✅ MediaMTX running; publish from a browser/phone to `/cam`; view it.
2. ✅ `ingest.py` reads RTSP and saves selected frames (with faces blurred).
3. ✅ OCR + YOLO-World + embeddings → PostgreSQL.
4. ✅ `/ask` endpoint (routing, retrieval, Gemini + Ollama, "not sure", "safe" filter).
5. ✅ Flutter app: stream + voice question + spoken answer (EN/FR/AR).
6. ✅ Dashboard: live view, status, timeline with images, Q&A history.
7. Bonuses: ✅ warnings in the app · ⬜ `/ws` warnings on the server · ⬜ image enhancement.
8. ⬜ Tests: latency, retrieval quality, answer accuracy, user feedback.

## 13. Deliverables checklist

- [x] Code in Git with README
- [ ] Short presentation (outline in [PRESENTATION.md](PRESENTATION.md))
- [ ] Test results: speed, search quality, answer accuracy, feedback
- [ ] Live demo + questions for each member
- [x] Team responsibilities ([TEAM.md](TEAM.md))
