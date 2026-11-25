"""All tunable settings in one place.

- Secrets and machine-specific values come from server/.env (see .env.example).
- Thresholds are starting values: tune them on real footage and change them HERE only.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

# Folder paths. SERVER_DIR is the "server/" folder, whatever the current directory is.
SERVER_DIR = Path(__file__).resolve().parent.parent
load_dotenv(SERVER_DIR / ".env")  # read server/.env into environment variables

# ---------- Stream ----------
RTSP_URL = os.getenv("RTSP_URL", "rtsp://localhost:8554/cam")  # MediaMTX output
SAMPLE_FPS = 2.0            # how many frames per second we check (the rest are skipped)
RECONNECT_SECONDS = 3.0     # wait before retrying when the stream is missing or drops
OPEN_TIMEOUT_MS = 5000      # give up opening the stream after 5 s (then retry)
READ_TIMEOUT_MS = 5000      # a read that hangs longer than 5 s = stream lost
FREEZE_SECONDS = 2.0        # picture 100% identical this long = decoder stuck → reconnect
# Video codecs OpenCV's built-in FFmpeg can read over RTSP. NOT AV1 (Chrome's browser test
# page may choose it: pick H264 or VP8 there).
SUPPORTED_CODECS = ("H264", "VP8", "VP9")

# ---------- Frame selection ----------
SHARPNESS_MIN = 10.0        # Laplacian variance; below this the frame is too blurry → drop
HASH_MIN = 5                # pHash distance to the last kept frame; below this = same scene → drop
DARK_MAX = 60.0             # mean brightness (0-255) below which a frame counts as "dark"

# ---------- Image enhancement (enhance.py), before OCR and YOLO ----------
# Dark frames (brightness < DARK_MAX) are brightened BEFORE the sharpness check:
# dark images have weak edges, so without this they were dropped as "blurry".
CLAHE_CLIP_LIMIT = 2.0      # CLAHE contrast limit; higher = stronger boost, but more noise
CLAHE_TILE_GRID = 8         # CLAHE works on an 8x8 grid of tiles (local contrast)
GAMMA_TARGET_BRIGHTNESS = 110.0  # gamma correction aims for about this mean brightness
GAMMA_MIN = 0.4             # strongest brightening allowed (lower gamma = brighter)
# Frames with SHARPNESS_MIN <= sharpness < SLIGHTLY_BLURRY_MAX get a mild unsharp mask.
SLIGHTLY_BLURRY_MAX = 100.0
UNSHARP_SIGMA = 2.0         # size of the blur subtracted by the unsharp mask (pixels)
UNSHARP_AMOUNT = 0.6        # sharpening strength; ~0.5-1.0 is "mild", more gives halos

# ---------- Storage ----------
FRAMES_DIR = SERVER_DIR / "frames"  # JPEG files of kept frames
FRAME_MAX_WIDTH = 960       # resize wider frames before saving (smaller files, faster OCR later)
JPEG_QUALITY = 85           # 0-100, JPEG compression quality

# ---------- Privacy: blur faces before saving (detection only, NO recognition) ----------
BLUR_FACES = True           # blur every detected face before the JPEG is written
FACE_MODEL_FILE = "face_detection_yunet_2023mar.onnx"  # OpenCV's YuNet detector, saved in MODELS_DIR
FACE_MODEL_URL = ("https://github.com/opencv/opencv_zoo/raw/main/models/"
                  "face_detection_yunet/face_detection_yunet_2023mar.onnx")
# Lower = blurs more faces but also random patches (which could hide sign text from OCR).
# Tested on sample photos: real faces scored 0.90-0.94, a false alarm 0.61.
FACE_MIN_CONF = 0.7
FACE_BLUR_MARGIN = 0.08     # enlarge each face box by 8% on every side (just enough for the chin)
FACE_PIXEL_BLOCKS = 6       # face is shrunk to ~6 pixels across before blurring (no details left)

# ---------- Database ----------
DATABASE_URL = os.getenv("DATABASE_URL", "")  # secret (contains the password): set it in .env
DB_POOL_SIZE = 5            # max connections shared by ingest, retention and web requests
DB_TIMEOUT_SECONDS = 5      # wait at most this long for a free connection

# ---------- Retention (privacy: keep only what is needed) ----------
# Can be overridden from the environment for testing, e.g.  $env:RETENTION_MINUTES = "1"
RETENTION_MINUTES = float(os.getenv("RETENTION_MINUTES", "30"))  # frames older than this are deleted
RETENTION_CHECK_SECONDS = 60  # how often the cleanup runs

# ---------- Languages (texts in languages.py) ----------
DEFAULT_LANGUAGE = "en"     # used until the first question tells us the user's language

# ---------- AI model files ----------
# YOLO-World, CLIP, EasyOCR, MiniLM and face-detector weights (downloaded, not in Git).
MODELS_DIR = SERVER_DIR / "models"
EASYOCR_DIR = MODELS_DIR / "easyocr"

# ---------- OCR (EasyOCR, CPU) ----------
# One reader per language. en and fr share a reader; Arabic needs its own (EasyOCR can't mix them).
OCR_READERS = {"en": ["en", "fr"], "fr": ["en", "fr"], "ar": ["ar", "en"]}
OCR_MIN_CONF = 0.3          # ignore text pieces EasyOCR is less sure about

# ---------- Object detection (YOLO-World, CPU) ----------
YOLO_MODEL = "yolov8s-worldv2.pt"  # base model, downloaded into MODELS_DIR the first time
YOLO_MIN_CONF = 0.25        # ignore weaker detections (YOLO-World scores are lower than normal YOLO)
YOLO_IMAGE_SIZE = 640       # input size; smaller = faster, less accurate
# Our own vocabulary (normal COCO YOLO has no "door" or "stairs"). No face recognition: labels only.
YOLO_CLASSES = [
    "door", "stairs", "person", "chair", "table", "exit sign", "elevator", "car",
    "bicycle", "bus", "traffic light", "stop sign", "bench", "trash can", "window",
    "sign", "pole", "escalator", "toilet", "sink", "laptop", "bottle", "cup", "bag",
]

# ---------- Unprompted alerts: "Stairs ahead." / "Door ahead." (alerts.py) ----------
ALERT_LABELS = {"stairs": "stairs", "door": "door"}  # alert type -> YOLO class (in YOLO_CLASSES)
ALERT_MIN_CONF = 0.40       # "good confidence": higher than YOLO_MIN_CONF so weak guesses don't alert. Tune.
ALERT_COOLDOWN_SECONDS = 10  # the same alert type at most once every 10 s (no repeats)
ALERT_MAX_AGE_SECONDS = 8   # older alerts are not given any more: "ahead" would no longer be true
ALERT_HISTORY_MAX = 50      # alerts kept in memory for GET /alerts and GET /events

# GET /events (Server-Sent Events): the phone keeps one connection open, alerts are pushed to it.
EVENTS_CHECK_SECONDS = 0.25     # how often each open connection looks for new alerts (max extra delay)
EVENTS_KEEPALIVE_SECONDS = 15   # send a small "ping" comment when quiet, so proxies/phones don't cut the line
EVENTS_RETRY_MS = 2000          # tells the phone: if the connection drops, reconnect after 2 s

# ---------- Embeddings ----------
# 384 dimensions (matches vector(384)). Loaded from MODELS_DIR/<name>/ if present, else from Hugging Face.
EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

# ---------- Vision worker ----------
VISION_QUEUE_MAX = 5        # frames waiting for OCR/YOLO; when full, the OLDEST waiting one is skipped

# ---------- Assistant: retrieval ("which frames answer the question?") ----------
NOW_MAX_AGE_SECONDS = 5     # "what is in front of me": newest frame older than this → "I'm not sure"
# "What is in front of me" uses the LIVE frame (last one read from the stream, stored on demand),
# so it works even when the camera is still and no new frame was kept. Last read older than
# this = stream stopped → fall back to the newest stored frame.
LIVE_FRAME_MAX_AGE_SECONDS = 2
SEARCH_WINDOW_SECONDS = 180  # "just passed" / "what did the sign say": look back this far
TOP_K_FRAMES = 3            # max frames sent to the answer model
# Best cosine similarity below this → "I'm not sure". Measured on test frames: real matches
# scored 0.25-0.53, unrelated frames 0.04-0.05. Tune on real footage.
MIN_SIMILARITY = 0.20

# ---------- Assistant: answer model ----------
# The phone gives up after 15 s, so the whole answer must be ready before that.
ANSWER_DEADLINE_SECONDS = 12
# Secrets: set them in .env. Free tier = low rate limit per key, so several keys can be given
# (GEMINI_API_KEYS=key1,key2,key3): requests rotate between them. GEMINI_API_KEY alone still works.
GEMINI_API_KEYS = [k.strip() for k in os.getenv("GEMINI_API_KEYS", "").split(",") if k.strip()] \
    or ([os.getenv("GEMINI_API_KEY", "").strip()] if os.getenv("GEMINI_API_KEY", "").strip() else [])
GEMINI_API_KEY = GEMINI_API_KEYS[0] if GEMINI_API_KEYS else ""  # "" = no key configured
# Check which models YOUR key can use with:  python -m app.assistant --list-models
# Tested 2026-11-20: flash-lite answers in 1.4-3 s; 3.5-flash and 3.8-flash took > 10 s (too slow).
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
GEMINI_THINKING_LEVEL = "minimal"  # least "thinking" = fastest answer (not supported by gemini-3.8-flash)
# Measured 2026-11-20: requests sent on a REUSED connection got lost (the network silently
# closes idle connections), so each request opens a new connection (answer in ~2-3 s).
# A few requests still get lost: if no answer after GEMINI_RESEND_AFTER_SECONDS we send the
# same request again and keep whichever answer arrives first.
GEMINI_REQUEST_TIMEOUT_SECONDS = 10  # one request; Google rejects deadlines under 10 s
GEMINI_RESEND_AFTER_SECONDS = 5  # not sooner: on a slow upload a 2nd copy slows the 1st one down
GEMINI_MAX_COPIES = 2       # each copy counts against the free-tier rate limit
GEMINI_BUDGET_SECONDS = 9   # stop waiting for Gemini after this (then Ollama gets the time left)
# The upload speed is the bottleneck. Measured with the same photo: 134 KB → 9.9 s,
# 73 KB → 6-24 s, 43 KB (384 px) → 3.4-5.5 s, with the same correct answer. So images are
# shrunk to 384 px and only the most relevant ones are sent (others go as text: OCR + objects).
GEMINI_IMAGE_WIDTH = 384
MODEL_JPEG_QUALITY = 70     # JPEG quality of images sent to Gemini/Ollama
MAX_IMAGES_PER_QUESTION = 2
# 127.0.0.1, not "localhost": on Windows "localhost" tries IPv6 first, which doubles the wait
# when Ollama is not running.
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
OLLAMA_CONNECT_TIMEOUT_SECONDS = 1  # Ollama runs on this PC: if it doesn't connect in 1 s, it's off
OLLAMA_MODEL = "qwen2.5vl:3b"  # small vision model, runs on CPU
OLLAMA_IMAGE_WIDTH = 512    # Ollama on CPU is slow: send ONE small image only
ANSWER_MAX_TOKENS = 300

# ---------- Benchmark endpoints (/benchmark/*, tests only: nothing is stored) ----------
BENCHMARK_MODELS = ["gemini-3.5-flash-lite", "gemini-3.5-flash", "gemini-3.8-flash"]  # compared by default
BENCHMARK_MAX_IMAGES = 10          # images per request (each one = several model calls)
BENCHMARK_MAX_UPLOAD_MB = 10       # max size of ONE uploaded image
BENCHMARK_GEMINI_TIMEOUT_SECONDS = 30  # no phone waiting here: give slow models time to answer
BENCHMARK_CALL_DELAY_SECONDS = 0.0  # pause between model calls (raise it if the free tier says 429)
BENCHMARK_OVERLOAD_RETRY_SECONDS = 3.0  # model "overloaded" (HTTP 503): wait this long, try once more

# ---------- Web API ----------
CORS_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]  # the React dashboard (Vite)
