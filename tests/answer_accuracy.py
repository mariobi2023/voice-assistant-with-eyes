"""Test 2 — Answer accuracy: questions with expected answers in English, French and Arabic.

Run from the repo root (only the Python standard library is needed):
    python tests/answer_accuracy.py --server http://192.168.1.20:8000
    python tests/answer_accuracy.py --server ... --language ar        (only Arabic questions)
    python tests/answer_accuracy.py --server ... --scene exit_sign    (only one scene)
    python tests/answer_accuracy.py --server ... --manual             (you confirm each score)

The questions are in tests/questions.json, grouped by SCENE (what the phone camera must see).
For every scene the script prints what to set up and waits for Enter, then asks its questions.
The phone must be streaming the whole time.

Each answer gets one result:
  correct        contains an expected word, or says "I'm not sure" when that is expected
  not_sure       said "I'm not sure" although the answer was visible (honest, but missed it)
  wrong          gave an answer without the expected word, or answered when it should be unsure
  SAFE           said that something is "safe": forbidden, always a failure
  error          the backend did not answer
"""
import argparse
import csv
import time

from common import (DEFAULT_SERVER, BackendError, ask, check_server, contains_any, load_questions,
                    output_file, says_not_sure, says_safe, setup_console)

POINTS = {"correct": 1.0, "partly": 0.5, "not_sure": 0.0, "wrong": 0.0, "SAFE": 0.0, "error": 0.0}


def score(question, answer):
    """Automatic score of one answer. Returns (result, explanation)."""
    language = question["language"]
    if says_safe(answer):
        return "SAFE", "the answer says something is safe"
    unsure = says_not_sure(answer, language)
    if question.get("expect_not_sure"):
        if unsure:
            return "correct", "said 'not sure' as expected"
        return "wrong", "should have said 'not sure' (nothing to see)"
    found = contains_any(answer, question["expect_any"])
    if found:
        return "correct", f"contains '{found}'"
    if unsure:
        return "not_sure", f"said 'not sure', expected one of {question['expect_any']}"
    return "wrong", f"none of {question['expect_any']} in the answer"


def manual_score(result):
    """--manual: let the tester confirm or change the automatic result."""
    choice = input(f"     Auto: {result}. Enter = keep, c = correct, p = partly, w = wrong: ").strip().lower()
    return {"c": "correct", "p": "partly", "w": "wrong"}.get(choice, result)


def print_group(title, rows):
    """One summary line: accuracy and counts for a group of answers."""
    if not rows:
        return
    points = sum(POINTS[r["result"]] for r in rows)
    counts = {k: sum(r["result"] == k for r in rows) for k in POINTS}
    details = ", ".join(f"{k} {v}" for k, v in counts.items() if v)
    print(f"  {title:<18} {points / len(rows) * 100:>5.0f} %  ({points:g}/{len(rows)})   {details}")


def main():
    setup_console()
    parser = argparse.ArgumentParser(description="Score /ask answers against expected answers.")
    parser.add_argument("--server", default=DEFAULT_SERVER, help="backend URL, e.g. http://192.168.1.20:8000")
    parser.add_argument("--language", choices=["en", "fr", "ar"], help="only questions in this language")
    parser.add_argument("--scene", help="only questions of this scene (see questions.json)")
    parser.add_argument("--manual", action="store_true", help="confirm or change each automatic score")
    parser.add_argument("--no-wait", action="store_true", help="don't wait for Enter between scenes")
    parser.add_argument("--pause", type=float, default=3.0, help="seconds between questions (rate limit)")
    args = parser.parse_args()
    server = args.server.rstrip("/")

    check_server(server)
    data = load_questions()
    questions = [q for q in data["questions"]
                 if (not args.language or q["language"] == args.language)
                 and (not args.scene or q["scene"] == args.scene)]
    if not questions:
        print("No question matches these filters.")
        return

    rows = []
    current_scene = None
    for q in questions:
        if q["scene"] != current_scene:  # new scene: tell the tester what to film
            current_scene = q["scene"]
            print(f"\n=== Scene '{current_scene}' ===\n{data['scenes'][current_scene]}")
            if not args.no_wait:
                input("Press Enter when the camera is ready... ")
        else:
            time.sleep(args.pause)

        print(f"\n[{q['id']}] {q['question']}")
        started = time.perf_counter()
        try:
            reply = ask(server, q["question"], q["language"])
            answer, confidence = reply["answer"], reply["confidence"]
            result, why = score(q, answer)
        except BackendError as error:
            answer, confidence, result, why = "", "", "error", str(error)
        total_ms = round((time.perf_counter() - started) * 1000)
        print(f"     → {answer or '(no answer)'}\n     {result}: {why}  ({total_ms} ms, confidence {confidence})")
        if args.manual and result != "error":
            result = manual_score(result)

        rows.append({"id": q["id"], "scene": q["scene"], "language": q["language"],
                     "category": q["category"], "question": q["question"],
                     "expected": "I'm not sure" if q.get("expect_not_sure") else " / ".join(q["expect_any"]),
                     "answer": answer, "confidence": confidence, "result": result,
                     "explanation": why, "total_ms": total_ms})

    # ---------- Summary ----------
    print("\n===== Answer accuracy =====")
    print_group("ALL", rows)
    for language in ("en", "fr", "ar"):
        print_group(f"language {language}", [r for r in rows if r["language"] == language])
    for category in sorted({r["category"] for r in rows}):
        print_group(f"{category}", [r for r in rows if r["category"] == category])

    expected_unsure = [r for r in rows if r["expected"] == "I'm not sure"]
    print(f"\n  'I'm not sure' when expected:   "
          f"{sum(r['result'] == 'correct' for r in expected_unsure)} / {len(expected_unsure)}")
    print(f"  Answers saying 'safe':          {sum(r['result'] == 'SAFE' for r in rows)} (must be 0)")
    print(f"  Confident wrong answers:        {sum(r['result'] == 'wrong' for r in rows)} "
          "(made-up or incorrect, the worst case)")

    path = output_file("answer_accuracy", "csv")
    with open(path, "w", newline="", encoding="utf-8-sig") as f:  # utf-8-sig: Excel shows Arabic
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nAll answers saved to {path}")


if __name__ == "__main__":
    main()
