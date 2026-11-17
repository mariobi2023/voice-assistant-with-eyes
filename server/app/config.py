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
