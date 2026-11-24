// Functions the panels use to get data from the FastAPI backend (server/app/main.py).
// While USE_MOCK is true they return fake data instead.
// Every failure becomes an Error with a clear message the page can show as it is.
import { API_BASE, FRAMES_LIMIT, REQUEST_TIMEOUT_MS, USE_MOCK } from './config.js'
import { mockStatus, mockFrames, mockQa } from './mockData.js'

// FastAPI errors look like {"detail": "text"} or, for bad parameters (422),
// {"detail": [{...}, ...]}. Return a short readable text.
async function readDetail(response) {
  try {
    const body = await response.json()
    return typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
  } catch {
    return response.statusText
  }
}

// Small helper: GET a JSON endpoint from the backend, with a timeout.
async function getJson(path) {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS)
  let response
  try {
    response = await fetch(API_BASE + path, { signal: controller.signal })
  } catch (err) {
    if (err.name === 'AbortError') {
      throw new Error(`Server did not answer within ${REQUEST_TIMEOUT_MS / 1000} s (${API_BASE}). ` +
        'Check that the backend is running and the Wi-Fi.')
    }
    // fetch fails like this when nothing answers at that address (wrong IP, other Wi-Fi,
    // backend stopped) AND when the backend refuses our origin (CORS).
    throw new Error(`Server not reachable at ${API_BASE}. Check the IP in dashboard/.env and the Wi-Fi. ` +
      'Open the dashboard at http://localhost:5173 (the backend only accepts that address).')
  } finally {
    clearTimeout(timer)
  }
  if (!response.ok) {
    throw new Error(`Server error on ${path} (HTTP ${response.status}): ${await readDetail(response)}`)
  }
  return response.json()
}

// GET /status → { stream_connected, fps, frames_stored, model }
export function getStatus() {
  return USE_MOCK ? Promise.resolve(mockStatus) : getJson('/status')
}

// GET /frames → the newest FRAMES_LIMIT stored frames, oldest first
export function getFrames() {
  return USE_MOCK ? Promise.resolve(mockFrames) : getJson(`/frames?limit=${FRAMES_LIMIT}`)
}

// GET /qa → list of past questions and answers, newest first
export function getQa() {
  return USE_MOCK ? Promise.resolve(mockQa) : getJson('/qa')
}

// URL of a frame's image: GET /frames/{id}/image (404 once retention deleted it)
export function frameImageUrl(id) {
  return `${API_BASE}/frames/${id}/image`
}
