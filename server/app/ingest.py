"""Ingest pipeline ("Remember").

Reads the camera stream from MediaMTX (RTSP), checks about SAMPLE_FPS frames per second,
and keeps only frames that are:
  1. sharp enough  (Laplacian variance >= SHARPNESS_MIN), and
  2. a new scene   (pHash distance to the last kept frame >= HASH_MIN).
Kept frames are saved as JPEG in server/frames/ and as a row in the frames table.
A second thread (VisionWorker) then adds OCR text, objects, caption and embedding to the row.

Everything runs in background threads, so the web server (/ask) is never blocked.
Test on its own:   python -m app.ingest   (ingest + vision + database + retention)
"""
import logging
import os
import queue
import socket
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import cv2
import imagehash
from PIL import Image

from app import config, db, embeddings, retention, vision
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


def find_video_codec(url):
    """Ask the RTSP server which video codec the stream uses (RTSP "DESCRIBE" request).
    Returns e.g. "H264", "VP8", "AV1", or None if there is no stream. Only used to explain
    WHY OpenCV could not open the stream in the log."""
    try:
        host_port = url.split("//", 1)[1].split("/", 1)[0]
        host, _, port = host_port.partition(":")
        with socket.create_connection((host, int(port or 554)), timeout=3) as sock:
            sock.sendall(f"DESCRIBE {url} RTSP/1.0\r\nCSeq: 1\r\nAccept: application/sdp\r\n\r\n".encode())
            reply = sock.recv(8192).decode(errors="replace")
    except OSError:
        return None
    in_video = False
    for line in reply.splitlines():  # SDP: "m=video ..." then "a=rtpmap:96 AV1/90000"
        if line.startswith("m="):
            in_video = line.startswith("m=video")
        elif in_video and line.startswith("a=rtpmap:"):
            return line.split()[1].split("/")[0].upper()
    return None


def explain_open_failure(url):
    """Log the real reason the stream could not be opened."""
    codec = find_video_codec(url)
    if codec is None:
        log.warning("No stream at %s (is the phone/browser publishing?), retrying in %.0f s",
                    url, config.RECONNECT_SECONDS)
    elif codec not in config.SUPPORTED_CODECS:
        log.warning("Stream found but its video codec is %s, which OpenCV cannot read. "
                    "Publish with %s instead. Retrying in %.0f s",
                    codec, " or ".join(config.SUPPORTED_CODECS), config.RECONNECT_SECONDS)
    else:
        log.warning("Stream found (%s) but OpenCV could not open it yet, retrying in %.0f s",
                    codec, config.RECONNECT_SECONDS)


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
                explain_open_failure(config.RTSP_URL)
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


# ---------- The vision worker (OCR + YOLO + embedding) ----------

class VisionWorker:
    """Second background thread: analyzes stored frames one by one.

    OCR takes 1-3 s per frame on a CPU. Doing it here, not in the Ingestor thread,
    means slow OCR never makes us fall behind the live stream, and never blocks /ask.
    """

    def __init__(self):
        self._queue = queue.Queue(maxsize=config.VISION_QUEUE_MAX)  # (frame_id, frame) waiting
        self._stop_event = threading.Event()
        self._thread = None

    def start(self):
        """Load the models, then start the analysis thread."""
        vision.load_models()
        embeddings.get_model()
        self._thread = threading.Thread(target=self._run, name="vision", daemon=True)
        self._thread.start()

    def stop(self):
        """Ask the thread to finish (it checks every second)."""
        self._stop_event.set()

    def submit(self, frame_id, frame):
        """Queue a frame for analysis. If the queue is full, skip the OLDEST waiting frame:
        fresh frames matter most for 'what is in front of me'."""
        try:
            self._queue.put_nowait((frame_id, frame))
        except queue.Full:
            skipped_id, _ = self._queue.get_nowait()
            log.info("Vision busy: frame %d skipped analysis (kept without OCR/objects)", skipped_id)
            self._queue.put_nowait((frame_id, frame))

    def _run(self):
        """Take frames from the queue and analyze them until stopped."""
        while not self._stop_event.is_set():
            try:
                frame_id, frame = self._queue.get(timeout=1)
            except queue.Empty:
                continue
            try:
                self.analyze_and_store(frame_id, frame)
            except Exception:
                log.exception("Vision failed for frame %d", frame_id)  # keep the thread alive

    def analyze_and_store(self, frame_id, frame):
        """OCR + objects + caption + embedding for one frame, saved into its database row."""
        started = time.monotonic()
        analysis = vision.analyze_frame(frame)
        text = embeddings.build_frame_text(analysis["ocr_text"], analysis["caption"])
        embedding = embeddings.embed_text(text)  # None if nothing was read or seen
        if not db.update_frame_vision(frame_id, analysis, embedding):
            log.info("Frame %d was deleted before analysis finished", frame_id)
            return
        log.info("Frame %d analyzed in %.1f s: text=%r objects=[%s]", frame_id,
                 time.monotonic() - started, analysis["ocr_text"], analysis["caption"])


# ---------- Starting everything together ----------

def start_pipeline():
    """Start ingest + vision + retention threads. Returns a function that stops them all.
    Used by `python -m app.ingest` now and by main.py (the web server) from step 4."""
    apply_migrations()  # make sure the tables exist
    stop_event = threading.Event()
    retention.start_retention_thread(stop_event)

    vision_worker = VisionWorker()
    vision_worker.start()  # loads the models (can take ~30 s the first time: downloads)

    def store_and_queue(frame, info):
        """on_frame_kept: save the row right away (fast), then queue the frame for analysis."""
        info["id"] = db.insert_frame(info)
        log.info("Frame stored in database with id %d", info["id"])
        vision_worker.submit(info["id"], frame)

    ingestor = Ingestor(on_frame_kept=store_and_queue)
    ingestor.start()

    def stop_pipeline():
        stop_event.set()
        vision_worker.stop()
        ingestor.stop()
        db.close_pool()

    return ingestor, stop_pipeline


def setup_logging():
    """Log to the console in UTF-8: the Windows console default (cp1252) cannot print
    Arabic OCR text and would show logging errors instead."""
    sys.stderr.reconfigure(encoding="utf-8")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def main():
    """Run the whole pipeline without the web server (test). Stop with Ctrl+C."""
    setup_logging()
    _ingestor, stop_pipeline = start_pipeline()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        log.info("Stopping...")
        stop_pipeline()


if __name__ == "__main__":
    main()
