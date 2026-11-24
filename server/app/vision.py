"""Vision: read text (OCR) and find objects in a kept frame.

- OCR:     EasyOCR. Two readers, because one reader cannot mix Arabic with French:
             ["en", "fr"] for English/French users, ["ar", "en"] for Arabic users.
           Only the reader of the ACTIVE language (the user's last question) is used.
- Objects: Ultralytics YOLO-World with our own class list (normal YOLO has no "door" or "stairs").
- Caption: a short text built from the object labels (no AI call per frame).

NO face recognition: "person" is only a box with a label, never who the person is.
Models are loaded once (first use) because loading takes several seconds.
"""
import hashlib
import logging
import threading
from collections import Counter

from app import config

log = logging.getLogger("vision")

_ocr_readers = {}             # reader key ("latin" / "arabic") -> easyocr.Reader
_yolo_model = None
_load_lock = threading.Lock()  # load each model only once, even if two threads ask
_active_language = config.DEFAULT_LANGUAGE


# ---------- Active language (decides which OCR reader runs) ----------

def set_active_language(language):
    """Remember the user's language (called by /ask) so new frames use the matching OCR reader."""
    global _active_language
    if language in config.OCR_READERS and language != _active_language:
        log.info("OCR language switched to %s", language)
        _active_language = language


# ---------- Model loading ----------

def _reader_key(language):
    """Readers are shared: en and fr use the same ["en","fr"] reader."""
    return "arabic" if language == "ar" else "latin"


def get_ocr_reader(language):
    """Return the EasyOCR reader for this language, loading it the first time (CPU only)."""
    key = _reader_key(language)
    with _load_lock:
        if key not in _ocr_readers:
            import easyocr  # imported here: it is slow to import and only needed once
            langs = config.OCR_READERS[language]
            log.info("Loading EasyOCR reader %s (downloads the model if missing)...", langs)
            config.EASYOCR_DIR.mkdir(parents=True, exist_ok=True)
            _ocr_readers[key] = easyocr.Reader(langs, gpu=False, verbose=False,
                                               model_storage_directory=str(config.EASYOCR_DIR))
        return _ocr_readers[key]


def _custom_yolo_path():
    """File for YOLO-World with OUR classes. The name contains a hash of the class list,
    so editing YOLO_CLASSES in config.py automatically builds a new file."""
    key = hashlib.md5("|".join(config.YOLO_CLASSES).encode("utf-8")).hexdigest()[:8]
    return config.MODELS_DIR / f"yolo-world-custom-{key}.pt"


def _build_custom_yolo(path):
    """One-time: YOLO-World uses CLIP to turn our class words into vectors, then we save
    the result. Later starts load the saved file directly: no CLIP needed (faster, less RAM)."""
    from ultralytics import YOLOWorld
    import ultralytics.nn.text_model as text_model
    text_model.WEIGHTS_DIR = config.MODELS_DIR  # keep the CLIP download in server/models/clip/
    log.info("Building %s from %s with %d classes (one time, needs CLIP)...",
             path.name, config.YOLO_MODEL, len(config.YOLO_CLASSES))
    model = YOLOWorld(str(config.MODELS_DIR / config.YOLO_MODEL))  # downloads the base model if missing
    model.set_classes(config.YOLO_CLASSES)  # tell YOLO-World which words to look for
    model.save(str(path))


def get_yolo_model():
    """Return YOLO-World with our custom class list, loading it the first time."""
    global _yolo_model
    with _load_lock:
        if _yolo_model is None:
            from ultralytics import YOLO
            config.MODELS_DIR.mkdir(parents=True, exist_ok=True)
            path = _custom_yolo_path()
            if not path.exists():
                _build_custom_yolo(path)
            log.info("Loading %s", path.name)
            _yolo_model = YOLO(str(path))
        return _yolo_model


def load_models():
    """Load everything at startup, so the first frame is not slow."""
    get_ocr_reader(_active_language)
    get_yolo_model()


# ---------- OCR ----------

def run_ocr(frame, language=None):
    """Read the text in the frame. Returns (text, mean confidence), or ("", None) if none."""
    reader = get_ocr_reader(language or _active_language)
    results = reader.readtext(frame)  # list of (box, text, confidence)
    kept = [(text.strip(), conf) for _box, text, conf in results
            if conf >= config.OCR_MIN_CONF and text.strip()]
    if not kept:
        return "", None
    text = " ".join(t for t, _ in kept)
    mean_conf = sum(c for _, c in kept) / len(kept)
    return text, round(float(mean_conf), 3)


# ---------- Object detection ----------

def detect_objects(frame):
    """Find our custom classes. Returns [{"label", "conf", "box": [x, y, w, h]}], best first."""
    result = get_yolo_model().predict(frame, conf=config.YOLO_MIN_CONF,
                                      imgsz=config.YOLO_IMAGE_SIZE, verbose=False)[0]
    objects = []
    for box in result.boxes:
        x1, y1, x2, y2 = (int(v) for v in box.xyxy[0].tolist())
        objects.append({
            "label": result.names[int(box.cls)],
            "conf": round(float(box.conf), 3),
            "box": [x1, y1, x2 - x1, y2 - y1],  # top-left corner + width/height, as in the schema
        })
    objects.sort(key=lambda o: o["conf"], reverse=True)
    return objects


def build_caption(objects):
    """Short text from the labels, e.g. "door, 2 chairs, exit sign" ("" if nothing found)."""
    counts = Counter(o["label"] for o in objects)  # keeps the order of first appearance (best first)
    parts = [label if n == 1 else f"{n} {label}s" for label, n in counts.items()]
    return ", ".join(parts)


# ---------- Everything for one frame ----------

def analyze_frame(frame):
    """Run OCR + object detection on one frame and return the results as a dict."""
    ocr_text, ocr_conf = run_ocr(frame)
    objects = detect_objects(frame)
    return {
        "ocr_text": ocr_text,
        "ocr_conf": ocr_conf,
        "objects": objects,
        "caption": build_caption(objects),
    }
