"""Shared helpers for the test scripts: HTTP calls to the backend and answer checks.

Only the Python standard library is used (no pip install needed).
The backend is reached over HTTP only, so the tests can run from any laptop on the
same Wi-Fi as the server:   --server http://192.168.1.20:8000
"""
import json
import re
import socket
import sys
import unicodedata
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = TESTS_DIR / "output"  # raw results (git-ignored)
DEFAULT_SERVER = "http://localhost:8000"
ASK_TIMEOUT_SECONDS = 20  # the phone gives up after 15 s; we wait a bit longer to measure


class BackendError(Exception):
    """The backend could not be reached or answered with an error. The message is readable."""


def setup_console():
    """Print Arabic and French accents correctly in the Windows console."""
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


def _request(method, url, body=None, timeout=10):
    """Send one HTTP request and return the decoded JSON reply."""
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(url, data=data, method=method,
                                     headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:  # the server answered, with an error code
        detail = error.read().decode("utf-8", errors="replace")[:300]
        raise BackendError(f"Server error on {url} (HTTP {error.code}): {detail}") from None
    except (socket.timeout, TimeoutError):
        raise BackendError(f"Server did not answer within {timeout} s ({url})") from None
    except urllib.error.URLError as error:
        if isinstance(error.reason, (socket.timeout, TimeoutError)):
            raise BackendError(f"Server did not answer within {timeout} s ({url})") from None
        raise BackendError(f"Server not reachable at {url} ({error.reason}). "
                           "Check the IP, the Wi-Fi and that the backend is running.") from None


def ask(server, question, language):
    """POST /ask → {"answer", "confidence", "frame_ids"}."""
    return _request("POST", f"{server}/ask", {"question": question, "language": language},
                    timeout=ASK_TIMEOUT_SECONDS)


def get_status(server):
    """GET /status → {"stream_connected", "fps", "frames_stored", "model"}."""
    return _request("GET", f"{server}/status")


def get_qa(server, limit):
    """GET /qa → past questions and answers, newest first (includes server latency_ms)."""
    return _request("GET", f"{server}/qa?limit={limit}")


def check_server(server):
    """Print the backend status before a test. Returns the status dict (exits if unreachable)."""
    try:
        status = get_status(server)
    except BackendError as error:
        print(f"ERROR: {error}")
        sys.exit(1)
    print(f"Backend {server}: stream connected={status['stream_connected']}, "
          f"fps={status['fps']}, frames stored={status['frames_stored']}, model={status['model']}")
    if not status["stream_connected"]:
        print("WARNING: the backend is not reading the camera stream: answers will be 'not sure'.")
    return status


def load_questions():
    """Questions and expected answers from tests/questions.json."""
    with open(TESTS_DIR / "questions.json", encoding="utf-8") as f:
        return json.load(f)


def output_file(name, extension):
    """tests/output/<date>_<time>_<name>.<extension> (folder created if needed)."""
    OUTPUT_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return OUTPUT_DIR / f"{stamp}_{name}.{extension}"


# ---------- Answer checks ----------

# Same "safe" patterns as the backend (server/app/languages.py). An answer must NEVER match.
# "pas sûr" (= not sure) is allowed.
SAFE_PATTERNS = [
    r"\bsafe(ly|ty)?\b", r"\bunsafe\b", r"\bno danger\b", r"\bdanger[- ]free\b",
    r"\bhazard[- ]free\b", r"\bsans danger\b", r"\bsans risque\b", r"\ben sécurité\b",
    r"\bsécuritaire\b", r"\bsécurisée?s?\b", r"(?<!pas )\bsûre?s?\b",
    r"آمن", r"أمان", r"مأمون", r"لا خطر", r"بدون خطر",
]

# Ways of saying "I'm not sure" (the backend uses the first one of each language).
# Checked on normalized text (lowercase, no accents, simple Arabic letters).
NOT_SURE_PATTERNS = {
    "en": [r"not sure", r"\bi don'?t know\b", r"\bcan'?t tell\b", r"\bcannot tell\b", r"\bunsure\b"],
    "fr": [r"pas sure?", r"ne sais pas", r"incertaine?"],
    "ar": [r"لست متاكد", r"غير متاكد", r"لا اعرف", r"لا ادري"],
}


def says_safe(answer):
    """True if the answer says something is safe (forbidden by the project rules)."""
    return any(re.search(p, answer, flags=re.IGNORECASE) for p in SAFE_PATTERNS)


def normalize(text):
    """Lowercase, remove accents (é → e) and Arabic short vowels, unify Arabic letter forms,
    so "Sûr", "sur" and "SUR" compare equal, and "أ"/"إ"/"آ" all become "ا"."""
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))  # accents + Arabic harakat
    text = re.sub("[أإآ]", "ا", text)
    text = text.replace("ى", "ي").replace("ة", "ه")
    # Arabic-Indic digits → 0-9, so "٢٠٤" matches "204"
    return text.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789"))


def says_not_sure(answer, language):
    """True if the answer admits it is not sure (in that language, or in English)."""
    text = normalize(answer)
    patterns = NOT_SURE_PATTERNS.get(language, []) + NOT_SURE_PATTERNS["en"]
    return any(re.search(normalize(p), text) for p in patterns)


def contains_any(answer, keywords):
    """The first expected keyword found in the answer, or None."""
    text = normalize(answer)
    for keyword in keywords:
        if normalize(keyword) in text:
            return keyword
    return None
