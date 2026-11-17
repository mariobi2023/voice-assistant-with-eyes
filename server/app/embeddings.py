"""Embeddings: turn text into a vector of 384 numbers, so we can search frames by MEANING.

Model: sentence-transformers "paraphrase-multilingual-MiniLM-L12-v2". It is multilingual,
so an Arabic or French question lands close to a frame whose text/objects are in English.
Vectors are normalized (length 1), so cosine similarity = how close two meanings are (0..1).

Used twice: for each frame (OCR text + object labels) and for each question (step 4).
"""
import logging
import threading

from app import config

log = logging.getLogger("embeddings")

_model = None
_lock = threading.Lock()  # the vision thread and web requests share one model


def _model_source():
    """Use the copy in server/models/ if its weights file is there, else download by name."""
    local_dir = config.MODELS_DIR / config.EMBEDDING_MODEL.split("/")[-1]  # models/paraphrase-...-v2
    if (local_dir / "model.safetensors").exists():
        return str(local_dir)
    return config.EMBEDDING_MODEL  # downloaded from Hugging Face into its cache the first time


def get_model():
    """Load the sentence-transformers model the first time (CPU only), then reuse it."""
    global _model
    with _lock:
        if _model is None:
            from sentence_transformers import SentenceTransformer
            source = _model_source()
            log.info("Loading embedding model from %s...", source)
            _model = SentenceTransformer(source, device="cpu")
        return _model


def embed_text(text):
    """Return the normalized embedding (numpy array of 384 floats) of `text`, or None if empty."""
    if not text or not text.strip():
        return None
    model = get_model()
    with _lock:
        return model.encode(text, normalize_embeddings=True)


def build_frame_text(ocr_text, caption):
    """The text we embed for a frame: what was written + what was seen."""
    parts = []
    if caption:
        parts.append(f"Objects: {caption}.")
    if ocr_text:
        parts.append(f"Text: {ocr_text}")
    return " ".join(parts)
