# Dashboard (React + Vite)

Live camera view (WHEP from MediaMTX), frame timeline, Q&A history and status.

## Run

```powershell
cd dashboard
npm install        # first time only
npm run dev        # opens on http://localhost:5173
```

For live video, MediaMTX must be running (`mediamtx mediamtx\mediamtx.yml` from the
repo root) and a camera must be publishing to `cam`
(e.g. http://localhost:8889/cam/publish).

## Files

| File | What it does |
|---|---|
| `src/config.js` | URLs, `USE_MOCK` switch, refresh interval |
| `src/mockData.js` | Fake `/status`, `/frames`, `/qa` data (same shape as the API) |
| `src/api.js` | `getStatus()`, `getFrames()`, `getQa()` — mock or real backend |
| `src/whep.js` | Minimal WHEP client (WebRTC playback from MediaMTX) |
| `src/App.jsx` | Loads data every 5 s and lays out the panels |
| `src/components/` | `LiveVideo`, `StatusPanel`, `QaHistory`, `FrameTimeline` |

When the backend is ready, set `USE_MOCK = false` in `src/config.js`.
