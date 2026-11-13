// Fake data shaped exactly like the backend API (docs/ARCHITECTURE.md, section 9).
// Stop using it (USE_MOCK = false in config.js) once the backend is running.

// Helper: an ISO timestamp "seconds ago" from now.
const ago = (seconds) => new Date(Date.now() - seconds * 1000).toISOString()

// GET /status
export const mockStatus = {
  stream_connected: true,
  fps: 2.0,
  frames_stored: 5,
  model: 'gemini-flash',
}

// GET /frames — same columns as the "frames" table (without the embedding). Oldest first.
export const mockFrames = [
  {
    id: 101, captured_at: ago(150), image_path: 'frames/101.jpg',
    ocr_text: 'EXIT', ocr_conf: 0.94,
    objects: [{ label: 'person', conf: 0.88, box: [120, 40, 80, 200] }],
    caption: 'A hallway with an exit sign above a door.',
    sharpness: 182.4, brightness: 110.2, enhanced: false,
  },
  {
    id: 102, captured_at: ago(120), image_path: 'frames/102.jpg',
    ocr_text: 'Pharmacie — Ouvert 9h-19h', ocr_conf: 0.81,
    objects: [],
    caption: 'A shop front with a green pharmacy sign.',
    sharpness: 140.0, brightness: 95.7, enhanced: false,
  },
  {
    id: 103, captured_at: ago(90), image_path: 'frames/103.jpg',
    ocr_text: '', ocr_conf: null,
    objects: [
      { label: 'chair', conf: 0.76, box: [30, 90, 60, 70] },
      { label: 'dining table', conf: 0.71, box: [100, 100, 150, 80] },
    ],
    caption: 'A dim room with a table and a chair.',
    sharpness: 105.3, brightness: 48.1, enhanced: true,
  },
  {
    id: 104, captured_at: ago(45), image_path: 'frames/104.jpg',
    ocr_text: 'مخرج الطوارئ', ocr_conf: 0.67,
    objects: [],
    caption: 'A sign with Arabic text on a wall.',
    sharpness: 160.9, brightness: 120.4, enhanced: false,
  },
  {
    id: 105, captured_at: ago(10), image_path: 'frames/105.jpg',
    ocr_text: 'Room 2.14', ocr_conf: 0.9,
    objects: [{ label: 'person', conf: 0.65, box: [200, 50, 70, 190] }],
    caption: 'A door with a room number plate.',
    sharpness: 199.2, brightness: 132.0, enhanced: false,
  },
]

// GET /qa — same columns as the "qa_log" table. Newest first.
export const mockQa = [
  {
    id: 4, asked_at: ago(8), language: 'en',
    question: 'What was written on the door I just passed?',
    answer: 'The door plate says "Room 2.14".',
    frame_ids: [105], confidence: 0.82, latency_ms: 1840,
  },
  {
    id: 3, asked_at: ago(40), language: 'ar',
    question: 'ماذا تقول اللافتة؟',
    answer: 'اللافتة تقول "مخرج الطوارئ".',
    frame_ids: [104], confidence: 0.61, latency_ms: 2210,
  },
  {
    id: 2, asked_at: ago(85), language: 'fr',
    question: "Qu'est-ce qu'il y a devant moi ?",
    answer: "Je ne suis pas sûr. L'image est trop sombre.",
    frame_ids: [103], confidence: 0.28, latency_ms: 950,
  },
  {
    id: 1, asked_at: ago(115), language: 'fr',
    question: 'Quels sont les horaires de la pharmacie ?',
    answer: 'Le panneau indique ouvert de 9h à 19h.',
    frame_ids: [102], confidence: 0.77, latency_ms: 2030,
  },
]
