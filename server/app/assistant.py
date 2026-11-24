"""The assistant ("Ask" → "Answer").

  question + language
    → 1. ROUTE    which kind of question? ("now", "text" or "past")
    → 2. RETRIEVE the stored frames that can answer it (or decide "I'm not sure")
    → 3. GENERATE a short answer from those frames only (Gemini, fallback Ollama)
    → 4. CHECK    remove any "safe" claim (in code, not only in the prompt)
    → 5. LOG      save it in qa_log
"""
import base64
import logging
import re
import sys
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait

import cv2
import httpx
import requests

from app import config, db, embeddings, vision
from app.ingest import capture_live_frame, resize_to_max_width
from app.languages import (LANGUAGE_NAMES, NOT_SURE, ROUTE_KEYWORDS, SAFE_PATTERNS, STOPWORDS,
                           normalize_language, not_sure)

log = logging.getLogger("assistant")

last_model_used = "none"  # shown by GET /status
_gemini_client = None
_gemini_pool = ThreadPoolExecutor(max_workers=6, thread_name_prefix="gemini")  # parallel copies

SYSTEM_PROMPT = """You help a blind or visually impaired person.
Answer ONLY from the provided images, OCR text and detected objects. Do not guess.
Maximum 2 short sentences. Reply in {language_name}.
Never say that anything is safe, and never judge whether something is safe or dangerous.
If the evidence is unclear or missing, reply exactly: "{not_sure}"
Do not identify or describe who a person is (no names, no faces, no identity)."""


# ---------- 1. Route ----------

def _is_arabic(text):
    """True if the text contains Arabic letters (Unicode block U+0600-U+06FF)."""
    return any("؀" <= ch <= "ۿ" for ch in text)


def _contains_keyword(question, keyword):
    """Whole-word match for English/French (so "now" doesn't match "know").
    Plain match for Arabic, where small words are glued to the next word (e.g. "و" = "and")."""
    if _is_arabic(keyword):
        return keyword in question
    return re.search(rf"(?<!\w){re.escape(keyword)}(?!\w)", question) is not None


def route_question(question, language):
    """Decide what kind of question this is: "text" (a sign), "now" (in front of me) or "past"."""
    q = question.lower()
    for route in ("text", "now"):
        words = ROUTE_KEYWORDS[route][language] + ROUTE_KEYWORDS[route]["en"]
        if any(_contains_keyword(q, w) for w in words):
            return route
    return "past"  # "just passed", "earlier", or anything else: search recent frames by meaning


def keywords_for_ocr(question, language):
    """Meaningful words of the question, to look for inside OCR text (e.g. "pharmacy", "exit")."""
    words = re.findall(r"[\w'-]+", question.lower())
    stop = STOPWORDS[language] | STOPWORDS["en"]
    min_len = 3 if language == "ar" else 4
    return [w for w in words if len(w) >= min_len and w not in stop]


# ---------- 2. Retrieve ----------
# Each function returns (frames, confidence, reason). reason is None when the evidence is good
# enough to answer, or a key of NOT_SURE_REASONS when we must say "I'm not sure".

def retrieve_now():
    """The current LIVE picture (stored right now, so it is a normal frame with an id).
    If the stream gives none, the newest stored frame, and only if it is fresh."""
    frame = capture_live_frame()
    if frame is not None:
        frame["analyzed"] = False  # stored a moment ago: OCR/YOLO have not run on it yet
    else:
        frame = db.newest_frame()
    if frame is None or frame["age_seconds"] > config.NOW_MAX_AGE_SECONDS:
        return [], 0.1, "no_recent"
    return [frame], 0.8, None


def retrieve_past(question):
    """Recent frames closest in meaning to the question."""
    frames = db.search_similar(embeddings.embed_text(question), config.SEARCH_WINDOW_SECONDS,
                               config.TOP_K_FRAMES)
    if not frames:
        return [], 0.0, "no_match"
    best = frames[0]["similarity"]
    if best < config.MIN_SIMILARITY:
        return frames, best, "no_match"
    return frames, best, None


def retrieve_text(question, language):
    """Signs/text: first frames whose OCR contains a word of the question, else recent frames
    with any text, most similar first."""
    words = keywords_for_ocr(question, language)
    if words:
        frames = db.search_ocr_keywords(words, config.SEARCH_WINDOW_SECONDS, config.TOP_K_FRAMES)
        if frames:
            return frames, 0.85, None
    frames = db.search_frames_with_text(embeddings.embed_text(question),
                                        config.SEARCH_WINDOW_SECONDS, config.TOP_K_FRAMES)
    if not frames:
        return [], 0.0, "no_text"
    return frames, 0.6, None


def retrieve(route, question, language):
    """Call the retrieval function that matches the route."""
    if route == "now":
        return retrieve_now()
    if route == "text":
        return retrieve_text(question, language)
    return retrieve_past(question)


# ---------- 3. Generate ----------

def describe_frames(frames):
    """Text evidence for the model: when each frame was seen, its OCR text and objects.
    Only the first MAX_IMAGES_PER_QUESTION frames are sent as images; the others as text only."""
    lines = []
    for i, f in enumerate(frames):
        has_image = "image attached" if i < config.MAX_IMAGES_PER_QUESTION else "text only, no image"
        start = f'Frame {f["id"]} ({has_image}, seen {f["age_seconds"]:.0f} seconds ago): '
        # A live frame was stored a moment ago: its ocr_text/caption are still '' because
        # vision has not run yet, which does NOT mean "nothing there". Let the model look.
        if f.get("analyzed") is False:
            lines.append(start + "not analyzed yet, use the image itself.")
            continue
        text = f'"{f["ocr_text"]}"' if f["ocr_text"] else "none"
        objects = f["caption"] or "none"
        lines.append(start + f"text read: {text}; objects detected: {objects}.")
    return "\n".join(lines)


def load_jpeg(image_path, max_width):
    """Read a stored frame as JPEG bytes, made at most `max_width` pixels wide.
    Smaller uploads = faster answers, and fewer requests lost on a weak connection."""
    image = resize_to_max_width(cv2.imread(str(config.SERVER_DIR / image_path)), max_width)
    return cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, config.MODEL_JPEG_QUALITY])[1].tobytes()


def get_gemini_client():
    """Create the Gemini client once.
    - max_keepalive_connections=0: a NEW connection for every request. Reused connections
      were silently dropped by the network and the request never got an answer.
    - no automatic SDK retries: ask_gemini_first_answer() decides when to send again."""
    global _gemini_client
    if _gemini_client is None:
        from google import genai
        from google.genai import types
        _gemini_client = genai.Client(
            api_key=config.GEMINI_API_KEY,
            http_options=types.HttpOptions(
                timeout=config.GEMINI_REQUEST_TIMEOUT_SECONDS * 1000,
                retry_options=types.HttpRetryOptions(attempts=1),
                client_args={"limits": httpx.Limits(max_keepalive_connections=0)},
            ),
        )
    return _gemini_client


def ask_gemini(system_prompt, user_text, images):
    """Send the images + evidence to Gemini and return its answer text."""
    from google.genai import types
    parts = [types.Part.from_bytes(data=img, mime_type="image/jpeg") for img in images]
    thinking = (types.ThinkingConfig(thinking_level=config.GEMINI_THINKING_LEVEL)
                if config.GEMINI_THINKING_LEVEL else None)
    response = get_gemini_client().models.generate_content(
        model=config.GEMINI_MODEL,
        contents=parts + [user_text],
        config=types.GenerateContentConfig(system_instruction=system_prompt, temperature=0.2,
                                           max_output_tokens=config.ANSWER_MAX_TOKENS,
                                           thinking_config=thinking),
    )
    return response.text


def ask_gemini_first_answer(system_prompt, user_text, images, stop_at):
    """Send the request; if no answer after GEMINI_RESEND_AFTER_SECONDS, send a copy (up to
    GEMINI_MAX_COPIES) and return the FIRST good answer. Some requests get lost and never
    answer, and waiting for them would make the phone time out. Returns None if nothing
    arrived before `stop_at`. Requests still running finish on their own in the background."""
    waiting = set()
    for copy in range(1, config.GEMINI_MAX_COPIES + 1):
        waiting.add(_gemini_pool.submit(ask_gemini, system_prompt, user_text, images))
        is_last = copy == config.GEMINI_MAX_COPIES
        wait_until = stop_at if is_last else min(stop_at, time.monotonic() + config.GEMINI_RESEND_AFTER_SECONDS)
        while waiting and time.monotonic() < wait_until:
            done, waiting = wait(waiting, timeout=wait_until - time.monotonic(), return_when=FIRST_COMPLETED)
            for request in done:
                try:
                    answer = request.result()
                except Exception as error:  # e.g. 429 rate limit: this copy failed
                    log.warning("Gemini request %d failed (%s)", copy, str(error)[:200])
                    continue
                if answer and answer.strip():
                    if copy > 1:
                        log.info("Gemini answered after sending %d copies", copy)
                    return answer.strip()
        if time.monotonic() >= stop_at:
            break
        if not is_last:
            log.info("No answer from Gemini yet, sending copy %d", copy + 1)
    return None


def ask_ollama(system_prompt, user_text, images, timeout):
    """Fallback: local Ollama vision model, ONE small image (CPU is slow)."""
    response = requests.post(
        f"{config.OLLAMA_URL}/api/chat",
        json={
            "model": config.OLLAMA_MODEL,
            "stream": False,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text,
                 "images": [base64.b64encode(img).decode("ascii") for img in images[:1]]},
            ],
            "options": {"temperature": 0.2, "num_predict": 120},
        },
        timeout=(config.OLLAMA_CONNECT_TIMEOUT_SECONDS, timeout),  # (connect, read)
    )
    response.raise_for_status()
    return response.json()["message"]["content"]


def generate_answer(question, language, frames, deadline):
    """Ask Gemini; if it fails (error, 429 rate limit, timeout) ask Ollama with the time left.
    Returns (answer text, model name), or (None, "none") if both failed."""
    global last_model_used
    system_prompt = SYSTEM_PROMPT.format(language_name=LANGUAGE_NAMES[language],
                                         not_sure=NOT_SURE[language])
    user_text = (f"Evidence from the camera:\n{describe_frames(frames)}\n\n"
                 f"Question (answer in {LANGUAGE_NAMES[language]}): {question}")

    if config.GEMINI_API_KEY:
        images = [load_jpeg(f["image_path"], config.GEMINI_IMAGE_WIDTH)
                  for f in frames[:config.MAX_IMAGES_PER_QUESTION]]  # most relevant first
        stop_at = min(deadline, time.monotonic() + config.GEMINI_BUDGET_SECONDS)
        answer = ask_gemini_first_answer(system_prompt, user_text, images, stop_at)
        if answer:
            last_model_used = config.GEMINI_MODEL
            return answer, config.GEMINI_MODEL
        log.warning("Gemini did not answer, trying Ollama")
    else:
        log.warning("GEMINI_API_KEY is not set, trying Ollama")

    time_left = deadline - time.monotonic()
    if time_left < 2:
        log.warning("No time left for Ollama (%.1f s)", time_left)
        return None, "none"
    try:
        images = [load_jpeg(f["image_path"], config.OLLAMA_IMAGE_WIDTH) for f in frames[:1]]
        answer = ask_ollama(system_prompt, user_text, images, timeout=time_left)
        last_model_used = config.OLLAMA_MODEL
        return answer.strip(), config.OLLAMA_MODEL
    except Exception as error:
        log.warning("Ollama failed too (%s)", str(error)[:200])
        return None, "none"


# ---------- 4. Check: never "safe" ----------

def remove_safe_claims(answer):
    """Drop every sentence that says something is safe. Returns the cleaned text (may be empty)."""
    sentences = re.split(r"(?<=[.!?؟])\s+", answer.strip())
    kept = [s for s in sentences
            if not any(re.search(p, s, flags=re.IGNORECASE) for p in SAFE_PATTERNS)]
    if len(kept) < len(sentences):
        log.warning("Removed a 'safe' claim from the answer: %r", answer)
    return " ".join(kept).strip()


# ---------- The whole flow ----------

def answer_question(question, language):
    """Answer one question. Returns {"answer", "confidence", "frame_ids"} (the /ask response)."""
    started = time.monotonic()
    deadline = started + config.ANSWER_DEADLINE_SECONDS
    language = normalize_language(language)
    vision.set_active_language(language)  # new frames use the OCR reader of this language

    route = route_question(question, language)
    frames, confidence, reason = retrieve(route, question, language)
    model = "none"

    if reason:  # weak evidence: don't even ask the model
        answer = not_sure(language, reason)
        confidence = min(confidence, 0.2)
    else:
        answer, model = generate_answer(question, language, frames, deadline)
        answer = remove_safe_claims(answer) if answer else ""
        if not answer:
            answer, confidence = not_sure(language, "no_model" if model == "none" else None), 0.2
        elif NOT_SURE[language].rstrip(".") in answer:  # the model itself said "I'm not sure"
            confidence = min(confidence, 0.3)

    confidence = round(float(confidence), 2)
    frame_ids = [f["id"] for f in frames]
    latency_ms = int((time.monotonic() - started) * 1000)
    try:
        db.insert_qa(language, question, answer, frame_ids, confidence, latency_ms)
    except Exception:
        log.exception("Could not save the question in qa_log")  # still answer the user
    log.info("Answered in %d ms via %s (route=%s, frames=%s, confidence=%.2f): %r",
             latency_ms, model, route, frame_ids, confidence, answer)
    return {"answer": answer, "confidence": confidence, "frame_ids": frame_ids}


def warm_up():
    """Do the slow first-time work at server start, not during the user's first question
    (importing the Gemini SDK, the first embedding)."""
    if config.GEMINI_API_KEY:
        get_gemini_client()
    embeddings.embed_text("warm up")
    log.info("Assistant ready (answer model: %s, fallback: %s)", config.GEMINI_MODEL, config.OLLAMA_MODEL)


# ---------- Helper command ----------

def list_gemini_models():
    """Print the Gemini models your API key can use to answer (generateContent)."""
    for model in get_gemini_client().models.list():
        if "generateContent" in (model.supported_actions or []):
            print(model.name.removeprefix("models/"))


if __name__ == "__main__":
    if "--list-models" in sys.argv:
        list_gemini_models()
