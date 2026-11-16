"""Ingest pipeline ("Remember").

Reads the camera stream from MediaMTX (RTSP), checks about SAMPLE_FPS frames per second,
and keeps only frames that are:
  1. sharp enough  (Laplacian variance >= SHARPNESS_MIN), and
  2. a new scene   (pHash distance to the last kept frame >= HASH_MIN).
Kept frames are saved as JPEG in server/frames/.

Runs in a background thread, so the web server (/ask) is never blocked by it.
Test on its own:   python -m app.ingest   (also stores rows in the DB and runs retention)
"""
import logging
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import cv2
import imagehash
from PIL import Image

from app import config, db, retention
from app.migrate import apply_migrations

log = logging.getLogger("ingest")

# Ask OpenCV's FFmpeg to read RTSP over TCP: over UDP, lost packets on Wi-Fi
# give grey, broken frames. Must be set before the first VideoCapture is created.
os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp")


# ---------- Small image helpers ----------

def open_stream(url):
    """Open the RTSP stream, with timeouts so a missing stream doesn't hang forever."""
    params = [
        cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, config.OPEN_TIMEOUT_MS,
        cv2.CAP_PROP_READ_TIMEOUT_MSEC, config.READ_TIMEOUT_MS,
    ]
    return cv2.VideoCapture(url, cv2.CAP_FFMPEG, params)


def resize_to_max_width(frame, max_width):
    """Shrink a frame wider than max_width (keeps the aspect ratio). Smaller = faster later."""
    height, width = frame.shape[:2]
    if width <= max_width:
        return frame
    scale = max_width / width
    return cv2.resize(frame, (max_width, int(height * scale)), interpolation=cv2.INTER_AREA)


def measure_sharpness(gray):
    """Variance of the Laplacian (edge strength). Blurry image = few edges = low value."""
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def measure_brightness(gray):
    """Mean pixel value, 0 (black) to 255 (white)."""
    return float(gray.mean())


def compute_phash(frame):
    """Perceptual hash: similar-looking images get similar hashes, even if pixels differ a bit."""
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)  # OpenCV is BGR, Pillow expects RGB
    return imagehash.phash(Image.fromarray(rgb))


def save_jpeg(frame, captured_at):
    """Save the frame as frames/<timestamp>.jpg and return the path relative to server/."""
    config.FRAMES_DIR.mkdir(parents=True, exist_ok=True)
    filename = captured_at.strftime("%Y%m%d_%H%M%S_%f")[:-3] + ".jpg"  # e.g. 20261116_153012_123.jpg
    full_path = config.FRAMES_DIR / filename
    cv2.imwrite(str(full_path), frame, [cv2.IMWRITE_JPEG_QUALITY, config.JPEG_QUALITY])
    return full_path.relative_to(config.SERVER_DIR).as_posix()  # "frames/2026...jpg"


# ---------- The ingest worker ----------

class Ingestor:
    """Background thread: stream → frame selection → JPEG on disk."""

    def __init__(self, on_frame_kept=None):
        # Called as on_frame_kept(frame, info) for every kept frame.
        # Later steps plug the database / OCR / YOLO in here.
        self.on_frame_kept = on_frame_kept
        self.stream_connected = False  # shown by GET /status
        self.fps = 0.0                 # frames checked per second, shown by GET /status
        self._last_hash = None         # pHash of the last kept frame
        self._stop_event = threading.Event()
        self._thread = None

    def start(self):
        """Start reading the stream in a background (daemon) thread."""
        self._thread = threading.Thread(target=self._run, name="ingest", daemon=True)
        self._thread.start()

    def stop(self):
        """Ask the thread to finish and wait for it."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=config.READ_TIMEOUT_MS / 1000 + 1)

    def _run(self):
        """Outer loop: connect, read until the stream drops, wait, reconnect."""
        while not self._stop_event.is_set():
            cap = open_stream(config.RTSP_URL)
            if not cap.isOpened():
                log.warning("No stream at %s, retrying in %.0f s", config.RTSP_URL, config.RECONNECT_SECONDS)
            else:
                log.info("Connected to %s", config.RTSP_URL)
                self.stream_connected = True
                self._read_loop(cap)
                log.warning("Stream lost, reconnecting in %.0f s", config.RECONNECT_SECONDS)
            cap.release()
            self.stream_connected = False
            self.fps = 0.0
            self._stop_event.wait(config.RECONNECT_SECONDS)

    def _read_loop(self, cap):
        """Inner loop: read every frame (so we never lag behind), but only check SAMPLE_FPS per second."""
        interval = 1.0 / config.SAMPLE_FPS
        next_check = time.monotonic()
        checked, window_start = 0, time.monotonic()

        while not self._stop_event.is_set():
            # grab() takes the next frame from the stream without converting it (cheap).
            if not cap.grab():
                return  # stream ended or read timed out
            now = time.monotonic()
            if now < next_check:
                continue  # not time to check a frame yet: skip it
            next_check = now + interval

            ok, frame = cap.retrieve()  # convert the grabbed frame into an image
            if ok and frame is not None:
                self.process_frame(frame)
                checked += 1

            # Update the measured fps every 5 seconds.
            if now - window_start >= 5:
                self.fps = round(checked / (now - window_start), 1)
                checked, window_start = 0, now

    def process_frame(self, frame):
        """Run the selection checks on one frame. Returns info about the kept frame, or None if dropped."""
        captured_at = datetime.now(timezone.utc)
        frame = resize_to_max_width(frame, config.FRAME_MAX_WIDTH)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # Check 1: sharp?
        sharpness = measure_sharpness(gray)
        if sharpness < config.SHARPNESS_MIN:
            log.info("Frame dropped: blurry (sharpness %.0f < %.0f)", sharpness, config.SHARPNESS_MIN)
            return None

        # Check 2: new scene? (subtracting two hashes gives the number of different bits)
        frame_hash = compute_phash(frame)
        if self._last_hash is not None:
            distance = frame_hash - self._last_hash
            if distance < config.HASH_MIN:
                log.info("Frame dropped: same scene (hash distance %d < %d)", distance, config.HASH_MIN)
                return None

        # Kept: save it and remember its hash for the next comparison.
        brightness = measure_brightness(gray)
        image_path = save_jpeg(frame, captured_at)
        self._last_hash = frame_hash
        info = {
            "captured_at": captured_at,
            "image_path": image_path,
            "sharpness": sharpness,
            "brightness": brightness,
            "is_dark": brightness < config.DARK_MAX,  # used for enhancement in a later step
        }
        log.info("Frame kept: %s (sharpness %.0f, brightness %.0f)", image_path, sharpness, brightness)

        if self.on_frame_kept:
            try:
                self.on_frame_kept(frame, info)
            except Exception:
                # e.g. database down: log it, but keep reading the stream.
                # (The JPEG stays on disk; retention's file sweep removes it later.)
                log.exception("Could not store kept frame %s", image_path)
        return info


def save_frame_to_db(frame, info):
    """on_frame_kept callback: store the kept frame's row in the frames table."""
    info["id"] = db.insert_frame(info)
    log.info("Frame stored in database with id %d", info["id"])


def main():
    """Run ingest + database + retention without the web server (step 2 test). Stop with Ctrl+C.
    From step 4 on, main.py starts all of this together with the API."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    apply_migrations()  # make sure the tables exist
    stop_event = threading.Event()
    retention.start_retention_thread(stop_event)
    ingestor = Ingestor(on_frame_kept=save_frame_to_db)
    ingestor.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        log.info("Stopping...")
        stop_event.set()
        ingestor.stop()
        db.close_pool()


if __name__ == "__main__":
    main()
