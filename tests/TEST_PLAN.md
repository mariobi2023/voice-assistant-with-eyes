# Test plan — Voice Assistant With Eyes

Required deliverable: **test results for speed, search quality, answer accuracy and feedback**.
This plan says what we measure, how, and what counts as a pass. Results go in
[results.md](results.md).

## Setup

- **Server laptop** (Member B): MediaMTX + backend running (`uvicorn app.main:app --host 0.0.0.0 --port 8000`).
- **Test laptop** (Member A, can be the same laptop): Python 3 only. The scripts use the
  **standard library only** and talk to the backend **over HTTP**, so nothing else is installed.
- **Phone**: the Flutter app streaming (Start streaming), same Wi-Fi as both laptops.
- Find the server IP with `ipconfig` on the server laptop. Check it from the test laptop:
  open `http://<server-ip>:8000/docs` in a browser.
- Run every script **from the repo root**. Raw results are saved in `tests/output/` (not committed).

| Script | Measures | Command |
|---|---|---|
| `ask_latency.py` | `/ask` response time over 20 questions | `python tests/ask_latency.py --server http://<server-ip>:8000` |
| `answer_accuracy.py` | Answer accuracy EN/FR/AR, "not sure", never "safe" | `python tests/answer_accuracy.py --server http://<server-ip>:8000` |
| `stream_latency.py` | Video delay phone → dashboard | `python tests/stream_latency.py --stopwatch`, then `python tests/stream_latency.py` |

Before each script runs, it prints `GET /status` (stream connected, fps, frames stored, model)
and warns if the backend is not reading the stream.

## Test materials (print before the session)

| Scene | What to prepare |
|---|---|
| `exit_sign` | A4 sheet with **EXIT** in big black letters, taped on a wall at eye level |
| `chair_table` | A chair and a table about 2 m away, nothing written, no people |
| `door_label` | A door with **ROOM 204** taped on it |
| `arabic_sign` | A4 sheet with **صيدلية** (pharmacy) in big letters |
| `nothing` | A plain wall or floor |

Exact instructions per scene are in [questions.json](questions.json) (`scenes`); the accuracy
script prints them and waits for Enter before each scene.

## 1. Speed: `/ask` response time

**What:** time from sending the question to receiving the full answer, over **20 questions**
(all three languages, all question types, taken from `questions.json`).

**How:** `ask_latency.py` sends the questions one by one (3 s pause to respect the Gemini
free-tier rate limit) and reports min / avg / median / max of:

- **total**: what the phone feels (network included),
- **server**: `latency_ms` saved by the backend in `qa_log` (read back from `GET /qa`),
- **network + overhead** = total − server,
- total per category (sign / now / memory / not_sure / safety).

It also counts failed requests, answers slower than 15 s (the phone gives up then) and
answers saying "safe".

**Pass:** average total < 5 s, max < 12 s (server deadline), 0 answers over 15 s, 0 failures.

Run it at least twice: once with the server on the same laptop (no Wi-Fi), once over Wi-Fi.

## 2. Answer accuracy (and search quality)

**What:** 16 questions in [questions.json](questions.json): sign reading, "what is in front of
me", memory ("the door I just passed"), nothing-to-see questions, and "is it safe" questions,
in English, French and Arabic.

**How:** `answer_accuracy.py` goes scene by scene, asks each question and scores the answer
automatically (`--manual` lets the tester confirm or change each score):

| Result | Meaning |
|---|---|
| `correct` | contains an expected word (case/accents/Arabic letter forms ignored), or says "I'm not sure" when that is expected |
| `not_sure` | said "I'm not sure" although the answer was visible: honest, but a miss |
| `wrong` | answered without the expected word, or answered when it should have been unsure |
| `SAFE` | said something is "safe": forbidden, always a failure |
| `error` | no answer from the backend |

Reported: accuracy overall, per language and per category; "I'm not sure" when expected
(x / 6); answers saying "safe" (must be 0); confident wrong answers.

**Search quality:** the `sign` and `memory` questions only succeed if retrieval found the right
frame (the model only sees the retrieved frames), so their accuracy measures search quality.
For a closer look, open the dashboard Q&A history: each answer lists its `frame_ids`; check in
the timeline that the frame with the sign/label is among them, and note it in results.md.

**Pass:** ≥ 70 % overall, ≥ 60 % in each language, "not sure" when expected ≥ 5/6,
**0 "safe"**, as few confident wrong answers as possible.

## 3. Stream latency: phone → dashboard

**What:** how late the live video on the dashboard is compared with reality.

**How ("film a clock"):**
1. `python tests/stream_latency.py --stopwatch` opens a big millisecond stopwatch window.
2. Put the dashboard next to it on the same screen; point the phone camera at the stopwatch.
3. Screenshot both at once (**Win + Shift + S**). Latency = stopwatch − stopwatch seen in the video.
4. Repeat ~10 times, a few seconds apart.
5. `python tests/stream_latency.py`, type each pair (`437.812 436.990`) → min / avg / max.

Accuracy about ±30 ms (screen refresh + camera exposure).

**Pass:** average < 1 s on the same Wi-Fi.

## 4. User feedback

**Who:** only people who agree and sign the consent form
([CONSENT_AND_FEEDBACK.md](CONSENT_AND_FEEDBACK.md)). Ideally a few people, including at least
one visually impaired person if one volunteers; sighted testers can wear a blindfold.
Always with a team member next to them; indoors, no stairs or streets.

**How:** 10–15 minutes each: the tester asks 5–10 questions of their own in their language,
then fills in the short feedback form (1–5 scores + comments). Average the scores in results.md.

## Privacy during tests

- Faces are blurred by the backend before storage; frames are deleted after 30 minutes.
- Do not film people who did not agree. Do not keep screenshots with faces.
- The `tests/output/` CSV files contain only questions and answers; they are not committed.
