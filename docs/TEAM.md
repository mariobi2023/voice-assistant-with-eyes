# Team responsibilities

Who built what in *Voice Assistant With Eyes*, based on the Git history of this repository.
Each member leads their own area; integration and testing are shared.

| Member | Name | Area | Folders |
|---|---|---|---|
| A | Samer El Murr | Mobile app, streaming, dashboard, proactive warnings, integration, tests, documentation | `mobile/`, `mediamtx/`, `dashboard/`, `docs/` |
| B | Mario Bouissa | Backend: ingest, image processing, multimedia database, AI assistant, API | `server/` |

## Member A: Samer El Murr

| Date | Work | Branch / PR |
|---|---|---|
| 2026-11-10 | Project documentation: `docs/ARCHITECTURE.md`, `CLAUDE.md` (rules, stack, conventions) | `setup/project-docs` (#1) |
| 2026-11-13 | MediaMTX configuration (WHIP in, RTSP + WHEP out) and stream test | `feature/mobile-stream-test` (#2) |
| 2026-11-13 | React + Vite dashboard: WHEP live video, status, frame timeline, Q&A history (mock data first) | `feature/dashboard` (#3) |
| 2026-11-13 | Flutter app: WHIP streaming of the back camera, settings screen (server IP, language) | `feature/mobile-app-stream` (#4) |
| 2026-11-13 | Voice in the app: big Ask button, `speech_to_text`, `flutter_tts`, mock answers in EN/FR/AR | `feature/mobile-voice` (#5) |
| 2026-11-24 | **Bonus: proactive warnings**: WebSocket `/ws` client, strong vibration, speech queue (a warning waits for the answer), "safe" filter, auto-reconnect, mock warnings | `feature/mobile-warnings` (#7) |
| 2026-11-24 | Flutter unit tests (settings, mock answers, warning parsing, "safe" filter) | `feature/mobile-warnings` (#7) |
| 2026-11-24 | Integration with the real backend: dashboard `.env` (backend + WHEP URLs), real frame images, API mismatch fixes, clear "server not reachable" errors in both front ends, mock mode off by default | `feature/integration` (PR pending) |
| 2026-11-24 | Documentation deliverables: root README, this file, architecture update, presentation outline | `docs/readme-team` (PR pending) |

## Member B: Mario Bouissa

| Date | Work | Commit |
|---|---|---|
| 2026-11-04 | Created the repository | `bb054f1` |
| 2026-11-16 | **Step 1, ingest**: read the RTSP stream with OpenCV, keep only sharp (Laplacian) and new (pHash) frames as JPEG | `a367c9e` |
| 2026-11-16 | **Step 2, database**: PostgreSQL + pgvector, migration runner, automatic retention (rows and files) | `6b75e62` |
| 2026-11-17 | **Step 3, vision**: EasyOCR (EN/FR + AR readers), YOLO-World with custom classes, multilingual embeddings | `083180a` |
| 2026-11-17 | **Step 4, assistant**: question routing (now/text/past), retrieval, "I'm not sure" logic, `POST /ask` | `a88f93c` |
| 2026-11-20 | Gemini tuning: `gemini-3.5-flash-lite`, fresh connection per request, resend if no answer | `b9800ff` |
| 2026-11-21 | Ingest robustness: explain why a stream cannot be opened (codec), reconnect when the video freezes | `fa89248`, `8824422` |
| 2026-11-21 | **Step 5**: dashboard endpoints (`/status`, `/frames`, `/frames/{id}/image`, `/qa`), live frame for "what is in front of me", **face blurring** (YuNet), smaller uploads | `de3a224` |
| 2026-11-21 | Threshold tuning (`SHARPNESS_MIN`) and clean-up of requirements / `.gitignore` | `6061fe5`, `dc7147d` (#6) |

## Shared / still to do

| Task | Owner |
|---|---|
| Backend `WS /ws` endpoint that sends warnings (and live updates to the dashboard) | B (app side done by A) |
| Bonus: dark / blurry image enhancement before analysis (`enhanced` column is ready) | B |
| Test results: speed (latency), search quality, answer accuracy, user feedback | A, with B |
| Tuning thresholds on real footage (`SHARPNESS_MIN`, `HASH_MIN`, `MIN_SIMILARITY`) | B |
| Live demo rehearsal (phone + laptop on the same Wi-Fi) | A and B |
