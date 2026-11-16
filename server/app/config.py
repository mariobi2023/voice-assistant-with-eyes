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
