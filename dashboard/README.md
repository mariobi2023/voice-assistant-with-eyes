# Dashboard (React + Vite)

Live camera view (WHEP from MediaMTX), frame timeline, Q&A history and status.

## Run

```powershell
cd dashboard
npm install                 # first time only
copy .env.example .env      # first time only, then edit the IPs in .env
npm run dev                 # opens on http://localhost:5173
```

`.env` settings (restart `npm run dev` after changing them):

| Variable | Default | What it is |
|---|---|---|
| `VITE_BACKEND_URL` | `http://localhost:8000` | FastAPI backend (`server/`) |
| `VITE_WHEP_URL` | `http://localhost:8889/cam/whep` | MediaMTX live video |
| `VITE_USE_MOCK` | `false` | `true` = fake data, no backend needed |

To use a teammate's laptop, put its IP in both URLs, e.g. `http://192.168.1.20:8000`.
Open the dashboard at **http://localhost:5173**: the backend only accepts requests from
`localhost:5173` / `127.0.0.1:5173` (CORS in `server/app/config.py`).

For live video, MediaMTX must be running (`mediamtx mediamtx\mediamtx.yml` from the
repo root) and a camera must be publishing to `cam`
(e.g. http://localhost:8889/cam/publish).

## Files

| File | What it does |
|---|---|
| `.env.example` | Template for `.env`: backend URL, WHEP URL, mock switch |
| `src/config.js` | Reads `.env`; refresh interval, request timeout, frames shown |
| `src/mockData.js` | Fake `/status`, `/frames`, `/qa` data (same shape as the API) |
| `src/api.js` | `getStatus()`, `getFrames()`, `getQa()`: real backend (or mock), clear error messages |
| `src/whep.js` | Minimal WHEP client (WebRTC playback from MediaMTX) |
| `src/App.jsx` | Loads data every 5 s and lays out the panels |
| `src/components/` | `LiveVideo`, `StatusPanel`, `QaHistory`, `FrameTimeline` |
