"""Test 5: vision speed. Can this laptop keep up with the stream, and are alerts fresh?

What it does (no phone, camera or database needed):
  1. Makes test frames: Ultralytics' bus.jpg + 6 generated frames with a sign on them.
  2. Times YOLO and OCR on each frame (the same functions the server uses).
  3. Replays frames into the real VisionWorker at 1 frame per second (about what the stream
     keeps) for --seconds, with the database stubbed out, and counts:
       - frames per minute that got objects (fast lane) and OCR text (slow lane)
       - alert delay = time from capture to the alert check (must stay < ALERT_MAX_AGE_SECONDS)

Run it with the server's virtual environment:
    cd server
    .venv\\Scripts\\python ..\\tests\\vision_throughput.py --seconds 180
Copy the printed summary into results.md (section 5).
"""
import argparse
import logging
import statistics
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent.parent / "server"
sys.path.insert(0, str(SERVER_DIR))

import cv2  # noqa: E402  (after sys.path, like the server code)
import numpy as np  # noqa: E402
import ultralytics  # noqa: E402

from app import alerts, config, db, ingest, privacy, vision  # noqa: E402

SIGNS = ["EXIT", "Room 204 - Library", "SORTIE DE SECOURS", "Pharmacie ouverte 24/24",
         "Bus 12  City Center  08:45", "Push to open"]


def make_frames():
    """bus.jpg + generated 960x540 frames with a white sign, faces blurred like the live pipeline."""
    bus = cv2.imread(str(Path(ultralytics.__file__).parent / "assets" / "bus.jpg"))
    frames = [ingest.resize_to_max_width(bus, config.FRAME_MAX_WIDTH)]
    rng = np.random.default_rng(0)
    for i, text in enumerate(SIGNS):
        background = np.tile(np.linspace(60, 180, 960, dtype=np.uint8), (540, 1))
        frame = cv2.cvtColor(background, cv2.COLOR_GRAY2BGR)
        frame = cv2.add(frame, rng.integers(0, 40, frame.shape, dtype=np.uint8))  # some noise
        x, y = 80 + 40 * i, 120 + 30 * i
        cv2.rectangle(frame, (x, y), (x + 620, y + 110), (240, 240, 240), -1)
        cv2.putText(frame, text, (x + 20, y + 70), cv2.FONT_HERSHEY_SIMPLEX, 1.1, (20, 20, 20), 3)
        frames.append(frame)
    for frame in frames:
        privacy.blur_faces(frame)
    return frames


def time_models(frames):
    """Median YOLO and OCR time per frame (after one warm-up run)."""
    vision.detect_objects(frames[0])
    vision.run_ocr(frames[0])
    yolo, ocr = [], []
    for frame in frames:
        start = time.monotonic()
        vision.detect_objects(frame)
        yolo.append(time.monotonic() - start)
        start = time.monotonic()
        text, _ = vision.run_ocr(frame)
        ocr.append(time.monotonic() - start)
        print(f"  YOLO {yolo[-1]:.2f} s   OCR {ocr[-1]:.2f} s   text: {text!r}")
    return statistics.median(yolo), statistics.median(ocr)


def stub_database(counts, delays, lock):
    """Replace the database writes by counters, and record the delay of every alert check."""
    def counter(key):
        def update(*_args):
            with lock:
                counts[key] += 1
            return ("", "")  # (ocr_text, caption), like the real UPDATE ... RETURNING
        return update
    db.update_frame_objects = counter("objects")
    db.update_frame_ocr = counter("ocr")
    db.update_frame_embedding = lambda *_args: None

    real_check = alerts.check_objects

    def check_objects(frame_id, objects, captured_at):
        with lock:
            delays.append((datetime.now(timezone.utc) - captured_at).total_seconds())
        return real_check(frame_id, objects, captured_at)
    alerts.check_objects = check_objects


def replay(frames, seconds):
    """Give the VisionWorker one frame per second, like the live stream."""
    counts, delays, lock = {"objects": 0, "ocr": 0}, [], threading.Lock()
    stub_database(counts, delays, lock)
    worker = ingest.VisionWorker()
    worker.start()
    start, sent = time.monotonic(), 0
    while time.monotonic() - start < seconds:
        worker.submit(sent, frames[sent % len(frames)].copy(), datetime.now(timezone.utc))
        sent += 1
        time.sleep(max(0.0, start + sent - time.monotonic()))
    worker.stop()
    time.sleep(2)  # let the last frames finish
    return sent, counts, delays


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--seconds", type=int, default=180, help="replay length (default 180)")
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING)

    frames = make_frames()
    vision.load_models()
    print("Model times per frame:")
    yolo_s, ocr_s = time_models(frames)
    print(f"\nReplaying 1 frame/s for {args.seconds} s...")
    sent, counts, delays = replay(frames, args.seconds)

    minutes = args.seconds / 60
    too_old = sum(d > config.ALERT_MAX_AGE_SECONDS for d in delays)
    print("\n===== Summary (copy into results.md) =====")
    print(f"YOLO median            {yolo_s:.2f} s")
    print(f"OCR median             {ocr_s:.2f} s   (OCR_MAX_WIDTH = {config.OCR_MAX_WIDTH})")
    print(f"Frames sent            {sent / minutes:.0f} / min")
    print(f"Frames with objects    {counts['objects'] / minutes:.0f} / min")
    print(f"Frames with OCR        {counts['ocr'] / minutes:.0f} / min")
    if delays:
        print(f"Alert delay            median {statistics.median(delays):.2f} s, max {max(delays):.2f} s")
        print(f"Too old (> {config.ALERT_MAX_AGE_SECONDS} s)        {too_old} / {len(delays)}")


if __name__ == "__main__":
    main()
