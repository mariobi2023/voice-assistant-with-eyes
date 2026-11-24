// All dashboard settings in one place.
// The URLs come from dashboard/.env (see .env.example), so you can point the dashboard at
// another laptop without changing code. Vite only exposes variables starting with VITE_.
const env = import.meta.env

// FastAPI backend (server/). Trailing "/" removed so we can add "/status" etc.
export const API_BASE = (env.VITE_BACKEND_URL || 'http://localhost:8000').replace(/\/+$/, '')

// MediaMTX WHEP endpoint for the "cam" stream (see mediamtx/mediamtx.yml).
export const WHEP_URL = env.VITE_WHEP_URL || 'http://localhost:8889/cam/whep'

// false (default) = call the real backend at API_BASE
// true            = fake data from mockData.js (set VITE_USE_MOCK=true in .env)
export const USE_MOCK = env.VITE_USE_MOCK === 'true'

// How often the panels refresh, in milliseconds.
export const REFRESH_MS = 5000

// Give up on a backend request after this long and show "did not answer".
export const REQUEST_TIMEOUT_MS = 4000

// How many of the newest frames the timeline shows (GET /frames?limit=...).
export const FRAMES_LIMIT = 50
