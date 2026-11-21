"""Privacy: blur faces BEFORE a frame is saved to disk / the database.

We only DETECT where faces are (a box), then blur that box. We never recognize or identify
who a person is (no face recognition: project rule). Nothing about the face is stored.

Detector: YuNet, a small face detector built into OpenCV (cv2.FaceDetectorYN).
Its model file (~230 KB) is downloaded once into server/models/.

Test on one image:   python -m app.privacy <input.jpg> <output.jpg>
"""
import logging
import sys
import threading
import urllib.request

import cv2
import numpy as np

from app import config

log = logging.getLogger("privacy")

_detector = None
_load_lock = threading.Lock()  # load the model only once, even if two threads ask


# ---------- Model loading ----------

def _download_model(path):
    """Download the YuNet model file the first time."""
    config.MODELS_DIR.mkdir(parents=True, exist_ok=True)
    log.info("Downloading face detector model %s ...", path.name)
    tmp = path.with_suffix(".part")  # don't leave a half-written file if the download fails
    urllib.request.urlretrieve(config.FACE_MODEL_URL, tmp)
    tmp.replace(path)


def get_face_detector():
    """Return the YuNet face detector, loading (and downloading) it the first time."""
    global _detector
    with _load_lock:
        if _detector is None:
            path = config.MODELS_DIR / config.FACE_MODEL_FILE
            if not path.exists():
                _download_model(path)
            _detector = cv2.FaceDetectorYN.create(
                str(path), "", (320, 320),            # input size is set per frame below
                score_threshold=config.FACE_MIN_CONF,
                nms_threshold=0.3,
                top_k=50,
            )
        return _detector


# ---------- Detection + blurring ----------

def detect_faces(frame):
    """Find faces. Returns a list of boxes [x, y, w, h] (location only, no identity)."""
    height, width = frame.shape[:2]
    detector = get_face_detector()
    with _load_lock:  # one detector object shared by threads: use it one at a time
        detector.setInputSize((width, height))
        _ok, faces = detector.detect(frame)
    if faces is None:
        return []
    # Each row: x, y, w, h, 5 landmark points (10 values), score. We keep only the box.
    return [[int(v) for v in face[:4]] for face in faces]


def _expand_box(box, frame_shape):
    """Make the box a bit bigger (hair, chin, ears) and keep it inside the image."""
    x, y, w, h = box
    margin_x, margin_y = int(w * config.FACE_BLUR_MARGIN), int(h * config.FACE_BLUR_MARGIN)
    height, width = frame_shape[:2]
    x1, y1 = max(0, x - margin_x), max(0, y - margin_y)
    x2, y2 = min(width, x + w + margin_x), min(height, y + h + margin_y)
    return x1, y1, x2, y2


def blur_region(frame, x1, y1, x2, y2):
    """Blur an OVAL (face shape) inside this rectangle, IN PLACE, with soft edges.
    The background around the face stays sharp."""
    region = frame[y1:y2, x1:x2]
    if region.size == 0:
        return
    h, w = region.shape[:2]
    # 1) Remove all details: shrink to a few blocks, enlarge back, then blur strongly.
    #    (Shrinking first means the face cannot be recovered from the blur.)
    blocks = config.FACE_PIXEL_BLOCKS
    small = cv2.resize(region, (max(1, w * blocks // max(w, h)), max(1, h * blocks // max(w, h))),
                       interpolation=cv2.INTER_AREA)
    blurred = cv2.resize(small, (w, h), interpolation=cv2.INTER_LINEAR)
    kernel = max(3, (min(w, h) // 3) | 1)  # odd number, grows with the face size
    blurred = cv2.GaussianBlur(blurred, (kernel, kernel), 0)

    # 2) Oval mask: 1.0 inside the face oval, 0.0 outside, with a soft (feathered) edge.
    mask = np.zeros((h, w), dtype=np.float32)
    cv2.ellipse(mask, (w // 2, h // 2), (w // 2, h // 2), 0, 0, 360, 1.0, thickness=-1)
    feather = max(3, (min(w, h) // 6) | 1)
    mask = cv2.GaussianBlur(mask, (feather, feather), 0)[:, :, None]

    # 3) Mix: blurred pixels inside the oval, original pixels outside.
    frame[y1:y2, x1:x2] = (blurred * mask + region * (1 - mask)).astype(np.uint8)


def blur_faces(frame):
    """Blur every detected face. Changes `frame` in place and returns the number of faces."""
    if not config.BLUR_FACES:
        return 0
    boxes = detect_faces(frame)
    for box in boxes:
        blur_region(frame, *_expand_box(box, frame.shape))
    return len(boxes)


# ---------- Manual test ----------

def main():
    """python -m app.privacy in.jpg out.jpg  → saves a copy with faces blurred."""
    logging.basicConfig(level=logging.INFO)
    if len(sys.argv) != 3:
        print("Usage: python -m app.privacy <input.jpg> <output.jpg>")
        return
    frame = cv2.imread(sys.argv[1])
    if frame is None:
        print("Could not read", sys.argv[1])
        return
    count = blur_faces(frame)
    cv2.imwrite(sys.argv[2], frame)
    print(f"{count} face(s) blurred -> {sys.argv[2]}")


if __name__ == "__main__":
    main()
