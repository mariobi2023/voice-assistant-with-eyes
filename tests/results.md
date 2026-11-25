# Test results — Voice Assistant With Eyes

Fill this in after each test session (method: [TEST_PLAN.md](TEST_PLAN.md)). Copy the summary
lines the scripts print; the raw CSV files are in `tests/output/` (not committed).
Replace every `_` with the measured value.

## Test conditions

| | |
|---|---|
| Date | _ |
| Testers | _ |
| Server laptop (CPU, RAM) | _ |
| Network | ☐ same laptop ☐ Wi-Fi ☐ phone hotspot |
| Phone | _ |
| Answer model (`/status`) | _ |
| Git commit tested (`git rev-parse --short HEAD`) | _ |
| Notes (light, distance to signs…) | _ |

## 1. Speed: `/ask` response time (20 questions)

Command: `python tests/ask_latency.py --server http://_:8000`

| Measure | Min | Avg | Median | Max |
|---|---|---|---|---|
| Total (phone feels) | _ ms | _ ms | _ ms | _ ms |
| Server (`qa_log.latency_ms`) | _ ms | _ ms | _ ms | _ ms |
| Network + overhead | _ ms | _ ms | _ ms | _ ms |

| Category | Avg total |
|---|---|
| sign | _ ms |
| now | _ ms |
| memory | _ ms |
| not_sure | _ ms |
| safety | _ ms |

| Check | Result | Target |
|---|---|---|
| Failed requests | _ / 20 | 0 |
| Slower than 15 s | _ | 0 |
| Answers saying "safe" | _ | **0** |
| Pass? | ☐ yes ☐ no | avg < 5 s, max < 12 s |

## 2. Answer accuracy (16 questions)

Command: `python tests/answer_accuracy.py --server http://_:8000` (☐ with `--manual`)

| Group | Accuracy | Correct | Not sure | Wrong | SAFE |
|---|---|---|---|---|---|
| **All** | _ % | _ | _ | _ | _ |
| English | _ % | _ | _ | _ | _ |
| French | _ % | _ | _ | _ | _ |
| Arabic | _ % | _ | _ | _ | _ |
| sign | _ % | _ | _ | _ | _ |
| now | _ % | _ | _ | _ | _ |
| memory | _ % | _ | _ | _ | _ |
| not_sure | _ % | _ | _ | _ | _ |
| safety | _ % | _ | _ | _ | _ |

| Check | Result | Target |
|---|---|---|
| "I'm not sure" when expected | _ / 6 | ≥ 5 / 6 |
| Answers saying "safe" | _ | **0** |
| Confident wrong answers | _ | as few as possible |
| Pass? | ☐ yes ☐ no | ≥ 70 % overall, ≥ 60 % per language |

### Search quality

For the `sign` and `memory` questions: was the frame with the text among the `frame_ids` of
the answer (dashboard → Q&A history / timeline)?

| Question id | Right frame retrieved? | Rank (1–3) | Notes |
|---|---|---|---|
| en-sign | ☐ yes ☐ no | _ | _ |
| fr-sign | ☐ yes ☐ no | _ | _ |
| ar-sign | ☐ yes ☐ no | _ | _ |
| en-door | ☐ yes ☐ no | _ | _ |
| fr-door | ☐ yes ☐ no | _ | _ |
| ar-door | ☐ yes ☐ no | _ | _ |
| ar-arabic-sign | ☐ yes ☐ no | _ | _ |
| **Found in top 3** | _ / 7 | | |

### Notable answers

| Question | Answer | Comment |
|---|---|---|
| _ | _ | _ |

## 3. Stream latency: phone → dashboard

Command: `python tests/stream_latency.py --stopwatch`, then `python tests/stream_latency.py`

| Readings | Min | Avg | Median | Max | Pass (avg < 1 s)? |
|---|---|---|---|---|---|
| _ | _ ms | _ ms | _ ms | _ ms | ☐ yes ☐ no |

## 4. User feedback

Testers (only with signed consent): _ · Vision: _ blind, _ low vision, _ sighted blindfolded

| # | Statement (1–5) | Average | Min | Max |
|---|---|---|---|---|
| 1 | Easy to use | _ | _ | _ |
| 2 | Vibrations clear | _ | _ | _ |
| 3 | Voice clear | _ | _ | _ |
| 4 | Fast enough | _ | _ | _ |
| 5 | Answers correct | _ | _ | _ |
| 6 | Short and useful | _ | _ | _ |
| 7 | "Not sure" when right | _ | _ | _ |
| 8 | Warnings helpful | _ | _ | _ |
| 9 | Would find it useful | _ | _ | _ |

Main comments:
- _

## 5. Vision speed: frames analyzed and alert delay

Command: `cd server` then `.venv\Scripts\python ..\tests\vision_throughput.py --seconds 180`

Reference (2026-11-25, CPU laptop, frames replayed at 60/min). "Before" = one vision thread
(YOLO then OCR, queue of 5); "after" = fast YOLO/alert lane + slow OCR lane on 640 px copies.

| Measure | Before | After | This laptop |
|---|---|---|---|
| YOLO per frame | 0.14 s | 0.16 s | _ s |
| OCR per frame (median) | 1.95 s | 1.19 s | _ s |
| Frames with objects | 18 / min | 56 / min | _ / min |
| Frames with OCR text | 18 / min | 22 / min | _ / min |
| Alert delay (median / max) | 4.7 s / 5.2 s | 0.7 s / 3.4 s | _ s / _ s |
| Alerts too old (> 8 s) | 0 % here, 100 % on a laptop with OCR ≈ 9.5 s | 0 % | _ % |

## Conclusions

- What works well: _
- What to improve: _
