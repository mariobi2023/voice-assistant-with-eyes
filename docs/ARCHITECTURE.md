# Architecture — Voice Assistant With Eyes

Multimedia Database & Image Processing — Project Fall 2026/2027
"An AI That Describes the World Out Loud"

## 1. Goal

A phone camera streams live video to a server. The user asks a question by voice
("What's in front of me?", "What did that sign say?", "What was written on the door
I just passed?") and hears a short spoken answer. The server remembers recent frames
in a multimedia database (image + OCR text + objects + time + embedding).

Workflow: **Stream → Remember → Ask → Answer**

## 2. Hard rules (from the project brief)

- **No face recognition.** Do not add any face identification/recognition library or feature.
- The assistant must **never say something is "safe"**. It is a helper, not a replacement for a white cane or guide dog.
- The assistant must **say "I'm not sure"** when evidence is weak.
- Answer **only from what the camera saw** (retrieved frames + OCR + detected objects). No guessing.
- Support **at least two languages** (English, French, Arabic).
- Keep only what is needed: **delete old frames** (DB rows and image files) automatically.
- Test only with people who agree.

## 3. System diagram

```
┌──────────────────────┐   WebRTC (WHIP)   ┌───────────────────┐
│ MOBILE APP (Flutter) │ ────────────────► │ MediaMTX          │
│ camera, mic, TTS     │                   │ streaming server  │
└─────────┬────────────┘                   └──┬─────────────┬──┘
          │ HTTP POST /ask                    │ RTSP        │ WebRTC (WHEP)
          │ (question text + lang)            ▼             ▼
          │                        ┌──────────────────┐  ┌────────────────┐
          └──────────────────────► │ BACKEND FastAPI  │◄─┤ DASHBOARD      │
             answer text ◄──────── │ ingest pipeline  │WS│ React + Vite   │
                                   │ retrieval + VLM  │  └────────────────┘
                                   └────────┬─────────┘
                                            ▼
                               PostgreSQL + pgvector
                               + frames/*.jpg on disk
                                            │
                               VLM: Gemini API (main)
                                    Ollama local (fallback)
```

## 4. Tech stack

| Layer | Choice | Fallback |
|---|---|---|
| Mobile app | Flutter + `flutter_webrtc`, `speech_to_text`, `flutter_tts` | Phone browser page (getUserMedia + WHIP) |
| Streaming | MediaMTX (WHIP in, RTSP/WHEP out) | — |
| Backend | Python 3.11+, FastAPI, Uvicorn | — |
| Frame selection / enhancement | OpenCV, `imagehash` | — |
| OCR (EN/FR/AR) | EasyOCR | PaddleOCR, Tesseract |
| Object detection | Ultralytics YOLO (COCO) | YOLO-World for custom classes ("door", "stairs") |
| Embeddings | `sentence-transformers` multilingual model (e.g. paraphrase-multilingual-MiniLM-L12-v2, 384 dims) | CLIP / SigLIP |
| Database | PostgreSQL + pgvector | SQLite + ChromaDB |
| Vision-language model | Gemini Flash API (Google AI Studio) | Ollama + `qwen2.5vl:7b` |
| Speech-to-text | Phone built-in STT | Groq Whisper API |
| Text-to-speech | Phone built-in TTS | — |
| Dashboard | React + Vite, WebSocket to backend, WHEP player for live video | Plain HTML/JS |

Note: COCO (standard YOLO) has **no "door" class**. Use YOLO-World or the VLM for door/stairs warnings.

## 5. Streaming

```
Phone ──WHIP──► http://<server-ip>:8889/cam/whip       (publish)
MediaMTX ─────► rtsp://localhost:8554/cam               (backend reads with OpenCV)
MediaMTX ─────► http://<server-ip>:8889/cam             (dashboard live view / WHEP)
```

- Ports: 8554 (RTSP), 8889 (WebRTC HTTP: WHIP/WHEP), 8189/udp (WebRTC media).
- Demo setup: phone and laptop on the same Wi-Fi / phone hotspot.
- Quick test without the app: open `http://localhost:8889/cam/publish` in a browser.

## 6. Ingest pipeline ("Remember")

Backend samples the RTSP stream at ~2 fps and runs each frame through:

```
1. Sharp?   Laplacian variance > SHARPNESS_MIN            else drop
2. New?     pHash distance to last kept frame > HASH_MIN  else drop
3. Dark?    mean brightness < DARK_MAX → CLAHE / gamma    (bonus: enhancement)
4. Blurry?  mild blur → unsharp mask / denoise            (bonus: enhancement)
5. OCR      EasyOCR → text + confidence
6. Objects  YOLO → labels + confidence + boxes
7. Embed    embedding of (OCR text + object labels + short caption)
8. Save     image to frames/<id>.jpg, row to DB
```

Thresholds are starting values in config and must be tuned on real footage:
`SHARPNESS_MIN ≈ 100`, `HASH_MIN ≈ 10`, `DARK_MAX ≈ 60`.

Retention job (every minute): delete rows and files older than `RETENTION_MINUTES` (e.g. 30).

## 7. Database schema

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE frames (
    id           SERIAL PRIMARY KEY,
    captured_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    image_path   TEXT NOT NULL,
    ocr_text     TEXT,
    ocr_conf     REAL,
    objects      JSONB,          -- [{"label":"person","conf":0.91,"box":[x,y,w,h]}]
    caption      TEXT,
    sharpness    REAL,
    brightness   REAL,
    enhanced     BOOLEAN DEFAULT FALSE,
    embedding    vector(384)
);
CREATE INDEX ON frames (captured_at);
CREATE INDEX ON frames USING hnsw (embedding vector_cosine_ops);

CREATE TABLE qa_log (
    id           SERIAL PRIMARY KEY,
    asked_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    language     TEXT,
    question     TEXT,
    answer       TEXT,
    frame_ids    INT[],
    confidence   REAL,
    latency_ms   INT
);
```

Search by time **and** meaning:

```sql
SELECT id, image_path, ocr_text, objects,
       1 - (embedding <=> :qvec) AS similarity
FROM frames
WHERE captured_at > now() - interval '2 minutes'
ORDER BY embedding <=> :qvec
LIMIT 3;
```

## 8. Answer flow ("Ask" → "Answer")

```
question (AR/FR/EN) → detect language → embed
  → retrieve top-3 frames (recent + similar)
  → best similarity < MIN_SIMILARITY (≈0.35)?  → "I'm not sure" (in user's language)
  → else send images + OCR + objects to VLM with system prompt below
  → log to qa_log → return answer text → phone speaks it
```

VLM system prompt (base):

> You help a blind or visually impaired person. Answer ONLY from the provided images,
> OCR text and detected objects. Maximum 2 short sentences. Reply in the user's language.
> Never say that anything is safe. If the evidence is unclear or missing, say you are
> not sure. Do not identify or describe who a person is.

If Gemini fails or hits the rate limit (HTTP 429) → automatically retry with Ollama.

## 9. API endpoints

| Method | Path | Purpose |
|---|---|---|
| POST | `/ask` | `{question, language}` → `{answer, confidence, frame_ids}` |
| GET | `/frames?from=&to=` | Timeline of stored frames (dashboard) |
| GET | `/frames/{id}/image` | Frame image |
| GET | `/qa` | Past questions and answers |
| GET | `/status` | Stream connected, fps, frames stored, model in use |
| WS | `/ws` | Live updates to dashboard (new frame, new Q&A) |

## 10. Repository structure

```
voice-assistant-with-eyes/
├── CLAUDE.md
├── README.md
├── docs/
│   ├── ARCHITECTURE.md
│   └── project-brief.pdf
├── mobile/                 # Flutter app
├── server/
│   ├── app/
│   │   ├── main.py         # FastAPI routes
│   │   ├── config.py       # thresholds, keys from .env
│   │   ├── ingest.py       # RTSP reading + frame selection
│   │   ├── vision.py       # enhancement, OCR, YOLO
│   │   ├── embeddings.py
│   │   ├── db.py           # Postgres + pgvector
│   │   ├── assistant.py    # retrieval + VLM + "not sure" logic
│   │   └── retention.py    # delete old frames
│   ├── requirements.txt
│   └── .env.example
├── dashboard/              # React + Vite
├── mediamtx/
│   └── mediamtx.yml
└── tests/                  # speed, search quality, answer accuracy
```

## 11. Team ownership

| Area | Owner | Branch prefix |
|---|---|---|
| Mobile app + streaming | Member 1 | `feature/mobile-*` |
| Images + multimedia DB | Member 2 | `feature/vision-*`, `feature/db-*` |
| AI assistant | Member 3 | `feature/assistant-*` |
| Web dashboard + tests | Member 4 | `feature/dashboard-*` |

## 12. Build order

1. MediaMTX running; publish from a browser to `/cam`; view it.
2. `server/ingest.py` reads RTSP and saves selected frames to disk.
3. OCR + YOLO + embeddings → PostgreSQL.
4. `/ask` endpoint working (test with Postman/curl).
5. Flutter app: stream + voice question + spoken answer.
6. Dashboard: live view, timeline, Q&A history.
7. Bonuses: unprompted warnings, image enhancement.
8. Tests: latency, retrieval quality, answer accuracy, user feedback.

## 13. Deliverables checklist

- [ ] Code in Git with README
- [ ] Short presentation (design, stack, what we built and learned)
- [ ] Test results: speed, search quality, answer accuracy, feedback
- [ ] Live demo + questions for each member
- [ ] Team responsibilities (who built what)
