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
SHARPNESS_MIN = 100.0       # Laplacian variance; below this the frame is too blurry → drop
HASH_MIN = 10               # pHash distance to the last kept frame; below this = same scene → drop
DARK_MAX = 60.0             # mean brightness (0-255) below which a frame counts as "dark"

# ---------- Storage ----------
FRAMES_DIR = SERVER_DIR / "frames"  # JPEG files of kept frames
FRAME_MAX_WIDTH = 960       # resize wider frames before saving (smaller files, faster OCR later)
JPEG_QUALITY = 85           # 0-100, JPEG compression quality

# ---------- Database ----------
DATABASE_URL = os.getenv("DATABASE_URL", "")  # secret (contains the password): set it in .env
DB_POOL_SIZE = 5            # max connections shared by ingest, retention and web requests
DB_TIMEOUT_SECONDS = 5      # wait at most this long for a free connection

# ---------- Retention (privacy: keep only what is needed) ----------
# Can be overridden from the environment for testing, e.g.  $env:RETENTION_MINUTES = "1"
RETENTION_MINUTES = float(os.getenv("RETENTION_MINUTES", "30"))  # frames older than this are deleted
RETENTION_CHECK_SECONDS = 60  # how often the cleanup runs

# ---------- Languages ----------
LANGUAGES = ("en", "fr", "ar")
DEFAULT_LANGUAGE = "en"     # used until the first question tells us the user's language

# ---------- AI model files ----------
MODELS_DIR = SERVER_DIR / "models"   # YOLO-World, CLIP and EasyOCR weights (downloaded, not in Git)
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

# ---------- Embeddings ----------
# 384 dimensions (matches vector(384)). Loaded from MODELS_DIR/<name>/ if present, else from Hugging Face.
EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

# ---------- Vision worker ----------
VISION_QUEUE_MAX = 5        # frames waiting for OCR/YOLO; when full, the OLDEST waiting one is skipped

# ---------- Assistant: retrieval ("which frames answer the question?") ----------
NOW_MAX_AGE_SECONDS = 5     # "what is in front of me": newest frame older than this → "I'm not sure"
SEARCH_WINDOW_SECONDS = 180  # "just passed" / "what did the sign say": look back this far
TOP_K_FRAMES = 3            # max frames sent to the answer model
# Best cosine similarity below this → "I'm not sure". Measured in step 3: real matches scored
# 0.25-0.53, unrelated frames 0.04-0.05. Tune on real footage.
MIN_SIMILARITY = 0.20

# ---------- Assistant: answer model ----------
# The phone gives up after 15 s, so the whole answer must be ready before that.
ANSWER_DEADLINE_SECONDS = 12
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")  # secret: set it in .env
# Check which models YOUR key can use with:  python -m app.assistant --list-models
# Tested 2026-11-20: flash-lite answers in 1.4-3 s; 3.5-flash and 3.8-flash took > 10 s (too slow).
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
GEMINI_THINKING_LEVEL = "minimal"  # least "thinking" = fastest answer (not supported by gemini-3.8-flash)
# Measured 2026-11-20: requests sent on a REUSED connection got lost (the network silently
# closes idle connections), so each request opens a new connection (answer in ~2-3 s).
# A few requests still get lost: if no answer after GEMINI_RESEND_AFTER_SECONDS we send the
# same request again and keep whichever answer arrives first.
GEMINI_REQUEST_TIMEOUT_SECONDS = 10  # one request; Google rejects deadlines under 10 s
GEMINI_RESEND_AFTER_SECONDS = 4
GEMINI_MAX_COPIES = 2       # each copy counts against the free-tier rate limit
GEMINI_BUDGET_SECONDS = 9   # stop waiting for Gemini after this (then Ollama gets the time left)
# 127.0.0.1, not "localhost": on Windows "localhost" tries IPv6 first, which doubles the wait
# when Ollama is not running.
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
OLLAMA_CONNECT_TIMEOUT_SECONDS = 1  # Ollama runs on this PC: if it doesn't connect in 1 s, it's off
OLLAMA_MODEL = "qwen2.5vl:3b"  # small vision model, runs on CPU
OLLAMA_IMAGE_WIDTH = 512    # Ollama on CPU is slow: send ONE small image only
ANSWER_MAX_TOKENS = 300

# ---------- Web API ----------
CORS_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]  # the React dashboard (Vite)
