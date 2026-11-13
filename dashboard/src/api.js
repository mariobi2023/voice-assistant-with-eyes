// Functions the panels use to get data.
// While USE_MOCK is true they return fake data; later they call the FastAPI backend.
import { API_BASE, USE_MOCK } from './config.js'
import { mockStatus, mockFrames, mockQa } from './mockData.js'

// Small helper: GET a JSON endpoint from the backend.
async function getJson(path) {
  const response = await fetch(API_BASE + path)
  if (!response.ok) throw new Error(`${path} failed: ${response.status}`)
  return response.json()
}

// GET /status → { stream_connected, fps, frames_stored, model }
export function getStatus() {
  return USE_MOCK ? Promise.resolve(mockStatus) : getJson('/status')
}

// GET /frames → list of stored frames, oldest first
export function getFrames() {
  return USE_MOCK ? Promise.resolve(mockFrames) : getJson('/frames')
}

// GET /qa → list of past questions and answers, newest first
export function getQa() {
  return USE_MOCK ? Promise.resolve(mockQa) : getJson('/qa')
}

// URL of a frame's image: GET /frames/{id}/image
export function frameImageUrl(id) {
  return `${API_BASE}/frames/${id}/image`
}
