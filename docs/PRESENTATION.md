# Presentation outline — Voice Assistant With Eyes

Short presentation (about 10–12 minutes + live demo). One section = one slide.
**Speaker** says who presents it. Keep slides visual: one diagram or a few words each,
details go in what the speaker says.

---

## Slide 1 — Title

- **Voice Assistant With Eyes: an AI that describes the world out loud**
- Multimedia Database & Image Processing, Fall 2026/2027
- Samer El Murr · Mario Bouissa

**Speaker:** Samer

---

## Slide 2 — The problem

- Walking into an unknown building: you can't read the signs, find the door, or remember
  what you just passed.
- Daily reality for blind and visually impaired people.
- Our goal: point the phone, **ask out loud, hear a short honest answer**, including about
  things seen a moment ago ("What was written on the door I just passed?").
- A helper, **not** a replacement for a white cane or a guide dog.

**Speaker:** Samer

---

## Slide 3 — Ground rules we built in

- Never says something is "safe" (removed in code, not only in the prompt).
- Says "I'm not sure" when the evidence is weak.
- Answers only from what the camera saw.
- No face recognition: faces are blurred before anything is stored.
- Old frames deleted automatically after 30 minutes.
- English, French and Arabic.

**Speaker:** Samer

---

## Slide 4 — Architecture

- Show the diagram from the README: Phone → MediaMTX → Backend → PostgreSQL + pgvector,
  Dashboard, Gemini / Ollama.
- The 4 steps: **Stream → Remember → Ask → Answer**.

**Speaker:** Samer (overview), Mario (backend boxes)

---

## Slide 5 — Technology stack

| Part | Technology |
|---|---|
| App | Flutter, WebRTC (WHIP), phone speech-to-text and text-to-speech |
| Streaming | MediaMTX |
| Backend | Python, FastAPI, OpenCV |
| Vision | EasyOCR, YOLO-World, YuNet face blur |
| Database | PostgreSQL + pgvector, multilingual embeddings |
| AI answer | Gemini flash-lite, Ollama fallback |
| Dashboard | React + Vite |

Why: free tools, run on a normal laptop CPU, multilingual.

**Speaker:** Samer (app, streaming, dashboard), Mario (backend, AI)

---

## Slide 6 — Stream: mobile app and streaming

- Back camera → WebRTC (WHIP) → MediaMTX → RTSP for the backend, WHEP for the dashboard.
- Accessible app: black/white/yellow, huge buttons, TalkBack labels, vibration feedback.
- One tap on **Ask**: vibrate → listen → vibrate → send → speak the answer.
- One server IP in Settings for everything; clear spoken errors ("Server not reachable,
  check the IP and Wi-Fi").

**Speaker:** Samer

---

## Slide 7 — Remember: image processing and multimedia database

- Keep only useful frames: **sharp** (Laplacian variance) and **new** (perceptual hash).
- Blur faces **before** saving (detection only, no identity).
- OCR (EasyOCR, EN/FR + AR) and objects (YOLO-World with our own words: door, stairs,
  exit sign…). Normal YOLO has no "door".
- Each frame = image + text + objects + time + 384-number embedding, in PostgreSQL + pgvector.
- Search by **time and meaning**: an Arabic question finds an English sign.

**Speaker:** Mario

---

## Slide 8 — Ask and Answer: the AI assistant

- 3 question types: **now** (live picture), **text** (signs, OCR keyword search),
  **past** (meaning search in the last 3 minutes).
- Weak evidence → "I'm not sure" without calling the model.
- Gemini gets the 2 best frames + OCR + objects; answer in max 2 sentences, in the user's
  language. Ollama on the laptop if Gemini fails.
- Whole answer in under 12 s (the phone waits 15 s).

**Speaker:** Mario

---

## Slide 9 — Dashboard and bonus: warnings

- Dashboard: live video, status (stream, fps, frames, model), frame timeline with images,
  Q&A history with confidence and latency.
- Bonus: **warnings without being asked** ("Warning: stairs ahead"): strong vibration, spoken
  right after the current answer, never during listening, never "safe".

**Speaker:** Samer

---

## Slide 10 — Live demo flow

1. Show the laptop: MediaMTX, backend and dashboard running (status: backend connected).
2. Phone: **Start streaming** → live video appears on the dashboard.
3. Point at a sign → ask **"What does the sign say?"** → spoken answer; the Q&A appears on the
   dashboard.
4. Point ahead → ask **"What is in front of me?"** (English).
5. Walk past a door with a label → ask **"What was written on the door I just passed?"**
   (memory of past frames).
6. Switch language → ask in **French** or **Arabic**.
7. Ask about something never seen → **"I'm not sure"**.
8. Show the timeline: faces blurred, frames older than 30 min are gone.
9. Warning: point at stairs or a door (backend `/events`), or use mock mode: phone vibrates and speaks it.

Backup plan: mock mode in the app and `VITE_USE_MOCK=true` on the dashboard if the network fails.

**Speaker:** both (Samer holds the phone, Mario explains the backend logs)

---

## Slide 11 — Results

Already measured during development (from `server/app/config.py`):

- Gemini flash-lite answers in **1.4–3 s**; bigger models took more than 10 s (too slow).
- Image upload is the bottleneck: 134 KB → 9.9 s, 43 KB (384 px) → **3.4–5.5 s**, same answer.
- Search: matching frames scored **0.25–0.53** similarity, unrelated frames **0.04–0.05**.
- Face detector: real faces scored **0.90–0.94**, a false alarm 0.61 (threshold 0.7).

To fill in after the test sessions:

| Test | Method | Result |
|---|---|---|
| Speed | Latency of `/ask` (`qa_log.latency_ms`) over N questions per type | _TBD_ |
| Search quality | Is the right frame in the top 3? (N labelled questions) | _TBD_ |
| Answer accuracy | Correct / partly correct / wrong / "not sure", per language | _TBD_ |
| User feedback | Short questionnaire, only with people who agree | _TBD_ |

**Speaker:** both

---

## Slide 12 — What we learned

- Network is the real bottleneck: smaller images and resending lost requests mattered more than
  a bigger model.
- Normal object detectors miss what blind users need most (doors, stairs) → YOLO-World.
- Safety rules must be enforced **in code**, not trusted to the prompt.
- Background threads keep the stream and the questions responsive while OCR is slow.
- Mock modes let the app and dashboard be built before the backend existed.
- Accessibility first: voice, vibration and big contrast, not small text.

**Speaker:** both

---

## Slide 13 — Who did what

| Samer El Murr (Member A) | Mario Bouissa (Member B) |
|---|---|
| Flutter app: streaming, voice, settings | Ingest: frame selection, freeze/codec handling |
| MediaMTX setup | Face blurring (privacy) |
| Dashboard | OCR, YOLO-World, embeddings |
| Proactive warnings (app) | PostgreSQL + pgvector, retention |
| Integration with the backend, tests | AI assistant and API (`/ask`, dashboard endpoints) |
| Documentation | Gemini / Ollama tuning |

Details: [TEAM.md](TEAM.md).

**Speaker:** both

---

## Slide 14 — Next steps and questions

- Merge the backend warnings (`/events`) and image enhancement, full test results.
- Questions.

**Speaker:** both
