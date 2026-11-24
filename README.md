# Voice Assistant With Eyes

**An AI that describes the world out loud**: a university project for *Multimedia Database &
Image Processing* (Fall 2026/2027), for blind and visually impaired users.

A phone camera streams live video to a server. The user asks a question out loud ("What's in
front of me?", "What did that sign say?", "What was written on the door I just passed?") and
hears a short spoken answer. The server **remembers** recent frames in a multimedia database
(image + OCR text + detected objects + time + embedding), so it can also answer questions about
what the camera saw a moment ago.

**Stream → Remember → Ask → Answer**

> This is a helper, **not** a replacement for a white cane or a guide dog.
> The assistant never says that something is "safe", says "I'm not sure" when the evidence is
> weak, answers only from what the camera saw, and never recognizes or identifies people
> (faces are blurred before anything is stored). Old frames are deleted automatically.

## Architecture

```
┌──────────────────────┐  video: WebRTC (WHIP) :8889  ┌──────────────────┐
│ MOBILE APP (Flutter) │ ───────────────────────────► │ MediaMTX         │
│ camera, Ask button,  │                              │ streaming server │
│ speech, TTS, warnings│                              └───┬──────────┬───┘
└───────┬──────▲───────┘                   RTSP :8554     │          │  WebRTC (WHEP) :8889
        │      │                                          ▼          ▼
        │      │  answer text / warnings     ┌──────────────────┐   ┌─────────────────────┐
        │      └──────────────────────────── │ BACKEND FastAPI  │   │ DASHBOARD           │
        │   POST /ask {question, language}   │ :8000            │◄──│ React + Vite :5173  │
        └──────────────────────────────────► │ ingest → vision  │   │ live video, status, │
                                             │ → database; /ask │   │ timeline, Q&A       │
                                             └────────┬─────────┘   └─────────────────────┘
                                                      ▼             GET /status /frames /qa
                                        PostgreSQL + pgvector
                                        + server/frames/*.jpg (faces blurred,
                                          deleted after 30 min)
                                                      │
                                        Answer model: Gemini API → fallback Ollama (local)
```

Warnings reach the phone over `WS /ws` (`{"type":"warning",...}`). The app side is done; the
backend endpoint is still to do.

Full details (pipeline, database schema, answer flow, API): [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Tech stack

| Part | Technology |
|---|---|
| Mobile app (`mobile/`) | Flutter (Android): `flutter_webrtc` (WHIP), `speech_to_text`, `flutter_tts` |
| Streaming (`mediamtx/`) | MediaMTX: WHIP in, RTSP + WHEP out |
| Backend (`server/`) | Python 3.12, FastAPI, Uvicorn, OpenCV, `imagehash` |
| Privacy | OpenCV YuNet face **detection** + blur (no recognition) |
| OCR | EasyOCR (English/French and Arabic readers) |
| Objects | Ultralytics YOLO-World (`yolov8s-worldv2`) with our own classes ("door", "stairs", "exit sign"…) |
| Embeddings | sentence-transformers `paraphrase-multilingual-MiniLM-L12-v2` (384 dims) |
| Database | PostgreSQL + pgvector (HNSW index, cosine similarity) |
| Answer model | Gemini `gemini-3.5-flash-lite`, fallback Ollama `qwen2.5vl:3b` |
| Dashboard (`dashboard/`) | React 18 + Vite 5 |
| Languages | English, French, Arabic |

## How to run (Windows)

All parts can run on one laptop. The phone must be on the **same Wi-Fi** (or the laptop on the
phone's hotspot). Find the laptop's IP with `ipconfig` → "IPv4 Address" of the Wi-Fi adapter.

Windows Firewall must let the phone reach the laptop on **TCP 8000** (backend),
**TCP 8889** and **UDP 8189** (MediaMTX). Allow them when Windows asks, or add inbound rules.

### 1. MediaMTX (streaming server)

1. Download the Windows build of [MediaMTX](https://github.com/bluenviron/mediamtx/releases)
   and put `mediamtx.exe` in the `mediamtx\` folder (it is git-ignored).
2. From the repo root:
   ```powershell
   .\mediamtx\mediamtx.exe .\mediamtx\mediamtx.yml
   ```
3. Quick test without the phone: open http://localhost:8889/cam/publish in Chrome and publish
   with the **H264** or **VP8** codec (not AV1, which OpenCV cannot read), then watch it at
   http://localhost:8889/cam.

### 2. Backend (`server/`)

Needs Python 3.12, PostgreSQL with the [pgvector](https://github.com/pgvector/pgvector)
extension, and a free [Gemini API key](https://aistudio.google.com/apikey).

```powershell
cd server
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1

# Dependencies, in this order (details at the top of requirements.txt):
pip install torch==2.10.0 torchvision==0.25.0 --index-url https://download.pytorch.org/whl/cpu
pip install git+https://github.com/ultralytics/CLIP.git
pip install -r requirements.txt

# One-time database setup (choose a password):
& "C:\Program Files\PostgreSQL\18\bin\psql.exe" -U postgres -v db_password=YOUR_PASSWORD -f setup_database.sql

# Settings: put the same password and your Gemini key in .env
copy .env.example .env
notepad .env

# Start (tables are created automatically; first start downloads the AI models)
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Check it at http://localhost:8000/docs. Optional offline fallback:
install [Ollama](https://ollama.com) and run `ollama pull qwen2.5vl:3b`.

### 3. Dashboard (`dashboard/`)

Needs Node.js.

```powershell
cd dashboard
npm install
copy .env.example .env     # then set the backend and MediaMTX IPs in .env
npm run dev
```

Open **http://localhost:5173** (the backend only accepts the dashboard from this address).

| `.env` variable | Default |
|---|---|
| `VITE_BACKEND_URL` | `http://localhost:8000` |
| `VITE_WHEP_URL` | `http://localhost:8889/cam/whep` |
| `VITE_USE_MOCK` | `false` (`true` = fake data, no backend needed) |

### 4. Flutter app (`mobile/`)

Needs the Flutter SDK, the Android SDK + NDK, and an Android phone with USB debugging on.

```powershell
cd mobile
flutter pub get
flutter run
```

In the app: **Settings** (gear) → the laptop's IP (used for both MediaMTX :8889 and the
backend :8000), language (English / Français / العربية), mock mode (off = real backend) →
**Save**. Then **Start streaming** and tap **Ask**.

Tests: `flutter test` (mobile), `npm run build` (dashboard).

> The dashboard `.env` settings, mock mode **off** by default and the clear
> "server not reachable" messages come from the `feature/integration` branch. Until it is
> merged into `dev`, the dashboard uses `USE_MOCK` in `src/config.js` and the app starts in
> mock mode.

## Documentation

| Document | Contents |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Architecture, pipeline, database schema, answer flow, API (source of truth) |
| [docs/TEAM.md](docs/TEAM.md) | Team responsibilities: who built what |
| [docs/PRESENTATION.md](docs/PRESENTATION.md) | Slide-by-slide presentation outline |
| [docs/project-brief.pdf](docs/project-brief.pdf) | The original project brief |
| [mobile/README.md](mobile/README.md) | Flutter app files and how to run it |
| [dashboard/README.md](dashboard/README.md) | Dashboard files and settings |
| [server/requirements.txt](server/requirements.txt) | Backend install steps and dependencies |
