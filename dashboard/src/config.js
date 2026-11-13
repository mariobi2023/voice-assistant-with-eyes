// All dashboard settings in one place.

// MediaMTX WHEP endpoint for the "cam" stream (see mediamtx/mediamtx.yml).
export const WHEP_URL = 'http://localhost:8889/cam/whep'

// FastAPI backend (not ready yet).
export const API_BASE = 'http://localhost:8000'

// true  = use fake data from mockData.js
// false = call the real backend at API_BASE
export const USE_MOCK = true

// How often the panels refresh, in milliseconds.
export const REFRESH_MS = 5000
