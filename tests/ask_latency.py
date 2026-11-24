"""Test 1 — Speed: response time of POST /ask over 20 questions (min / avg / max).

Run from the repo root (only the Python standard library is needed):
    python tests/ask_latency.py --server http://192.168.1.20:8000
    python tests/ask_latency.py --server http://192.168.1.20:8000 --count 20 --pause 4

What it measures, for every question:
  - total time  = what the phone feels: send the question → full answer received (network included)
  - server time = time the backend spent (latency_ms saved in qa_log, read back from GET /qa)
  - network     = total − server
The questions come from tests/questions.json (all languages, all categories, repeated if needed).
Keep the phone streaming during the test, pointed at anything, so the backend has frames.
"""
import argparse
import csv
import statistics
import time

from common import (DEFAULT_SERVER, BackendError, ask, check_server, get_qa, load_questions,
                    output_file, says_safe, setup_console)

PHONE_TIMEOUT_SECONDS = 15  # the app gives up after this: slower answers count as "too slow"


def summary(values):
    """(min, average, median, max) of a list of numbers, or None if empty."""
    if not values:
        return None
    return min(values), statistics.mean(values), statistics.median(values), max(values)


def print_line(label, values, unit="ms"):
    s = summary(values)
    if s is None:
        print(f"  {label:<22} no data")
    else:
        print(f"  {label:<22} min {s[0]:>6.0f} {unit} | avg {s[1]:>6.0f} {unit} | "
              f"median {s[2]:>6.0f} {unit} | max {s[3]:>6.0f} {unit}  (n={len(values)})")


def server_latencies(server, rows):
    """Match our questions with GET /qa (same question text, newest first) to get latency_ms."""
    try:
        history = get_qa(server, limit=len(rows) * 2 + 10)
    except BackendError as error:
        print(f"Could not read GET /qa for server times: {error}")
        return
    for row in reversed(rows):  # our newest question ↔ newest matching qa_log entry
        for i, item in enumerate(history):
            if item["question"] == row["question"]:
                row["server_ms"] = item["latency_ms"]
                row["network_ms"] = max(0, row["total_ms"] - item["latency_ms"])
                del history[i]
                break


def main():
    setup_console()
    parser = argparse.ArgumentParser(description="Measure /ask response time.")
    parser.add_argument("--server", default=DEFAULT_SERVER, help="backend URL, e.g. http://192.168.1.20:8000")
    parser.add_argument("--count", type=int, default=20, help="number of questions (default 20)")
    parser.add_argument("--pause", type=float, default=3.0,
                        help="seconds between questions, to stay under the Gemini free-tier rate limit")
    args = parser.parse_args()
    server = args.server.rstrip("/")

    check_server(server)
    questions = load_questions()["questions"]
    rows = []
    print(f"\nAsking {args.count} questions...\n")

    for n in range(args.count):
        q = questions[n % len(questions)]
        started = time.perf_counter()
        try:
            reply = ask(server, q["question"], q["language"])
            error = ""
        except BackendError as e:
            reply, error = None, str(e)
        total_ms = (time.perf_counter() - started) * 1000

        row = {
            "n": n + 1, "id": q["id"], "language": q["language"], "category": q["category"],
            "question": q["question"], "total_ms": round(total_ms),
            "server_ms": "", "network_ms": "",
            "answer": reply["answer"] if reply else "", "confidence": reply["confidence"] if reply else "",
            "error": error,
        }
        rows.append(row)
        if reply:
            safe_flag = "  <-- SAYS 'SAFE'!" if says_safe(reply["answer"]) else ""
            print(f"{n + 1:>2}. {total_ms:>6.0f} ms  [{q['language']}] {q['question']}\n"
                  f"     → {reply['answer']}{safe_flag}")
        else:
            print(f"{n + 1:>2}. FAILED after {total_ms:.0f} ms  [{q['language']}] {q['question']}\n     {error}")
        if n + 1 < args.count:
            time.sleep(args.pause)

    ok_rows = [r for r in rows if not r["error"]]
    server_latencies(server, ok_rows)

    # ---------- Summary ----------
    print("\n===== /ask response time =====")
    print_line("Total (phone feels)", [r["total_ms"] for r in ok_rows])
    print_line("Server (qa_log)", [r["server_ms"] for r in ok_rows if r["server_ms"] != ""])
    print_line("Network + overhead", [r["network_ms"] for r in ok_rows if r["network_ms"] != ""])
    for category in sorted({r["category"] for r in ok_rows}):
        print_line(f"  category '{category}'", [r["total_ms"] for r in ok_rows if r["category"] == category])
    slow = sum(r["total_ms"] > PHONE_TIMEOUT_SECONDS * 1000 for r in ok_rows)
    safe = sum(says_safe(r["answer"]) for r in ok_rows)
    print(f"  Failed requests:      {len(rows) - len(ok_rows)} / {len(rows)}")
    print(f"  Slower than {PHONE_TIMEOUT_SECONDS} s:     {slow} (the phone would have given up)")
    print(f"  Answers saying 'safe': {safe} (must be 0)")

    path = output_file("ask_latency", "csv")
    with open(path, "w", newline="", encoding="utf-8-sig") as f:  # utf-8-sig: Excel shows Arabic
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nAll measurements saved to {path}")


if __name__ == "__main__":
    main()
