# CLAUDE.md

University project: "Voice Assistant With Eyes" — an AI that describes the world out loud
for blind and visually impaired users (Multimedia Database & Image Processing, Fall 2026/2027).

**Before doing any work, read `docs/ARCHITECTURE.md`.** It is the source of truth for
the architecture, stack, database schema, API and folder structure. The original brief
is `docs/project-brief.pdf`.

## Non-negotiable rules

- NO face recognition or person identification — never add such libraries or features.
- The assistant must NEVER tell the user that something is "safe".
- The assistant must say "I'm not sure" (in the user's language) when evidence is weak.
- Answers must come ONLY from stored frames, OCR text and detected objects.
- Support at least English, French and Arabic.
- Old frames must be deleted automatically (DB rows and image files).

## Stack summary

- `mobile/` — Flutter (flutter_webrtc, speech_to_text, flutter_tts)
- `mediamtx/` — MediaMTX streaming server (WHIP in, RTSP/WHEP out)
- `server/` — Python 3.11+, FastAPI, OpenCV, EasyOCR, Ultralytics YOLO,
  sentence-transformers, PostgreSQL + pgvector, Gemini API (fallback: Ollama)
- `dashboard/` — React + Vite

## Conventions

- Work on a feature branch (`feature/<area>-<short-name>`), never commit directly to `main`.
- Secrets (API keys, DB password) go in `server/.env`, never in code. Keep `.env.example` updated.
- Tunable values (thresholds, retention time, model names) live in `server/app/config.py`.
- Keep functions small and commented — every team member must be able to explain the code in the demo.
- When adding a dependency, add it to `server/requirements.txt` or the relevant package file.
- Explain changes step by step when finishing a task.
