"""FastAPI web server: the API used by the phone app and the dashboard.

Run (from server/):   uvicorn app.main:app --host 0.0.0.0 --port 8000
Try it in a browser:  http://localhost:8000/docs

At startup it also starts the background pipeline: ingest → vision → database, + retention.
"""
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app import assistant, config, db
from app.ingest import setup_logging, start_pipeline

setup_logging()  # our INFO logs (frame kept/dropped, answer time) in the uvicorn console
pipeline = {}    # the running ingestor and the function that stops everything


@asynccontextmanager
async def lifespan(app):
    """Start the background threads when the server starts, stop them when it stops."""
    pipeline["ingestor"], pipeline["stop"] = start_pipeline()  # loads the AI models (~25 s)
    assistant.warm_up()
    yield
    pipeline["stop"]()


app = FastAPI(title="Voice Assistant With Eyes", lifespan=lifespan)

# Let the React dashboard (another port = another "origin") call this API from the browser.
app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS,
                   allow_methods=["*"], allow_headers=["*"])


# ---------- Request / response shapes (same field names as the phone app) ----------

class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500, examples=["What is in front of me?"])
    language: str = Field(default="en", examples=["en", "fr", "ar"])


class AskResponse(BaseModel):
    answer: str
    confidence: float  # 0..1
    frame_ids: list[int]


# Dashboard shapes: same field names as dashboard/src/mockData.js.

class StatusResponse(BaseModel):
    stream_connected: bool
    fps: float
    frames_stored: int
    model: str


class DetectedObject(BaseModel):
    label: str
    conf: float
    box: list[int]  # [x, y, w, h]


class FrameOut(BaseModel):
    id: int
    captured_at: datetime
    image_path: str
    ocr_text: str            # '' when no text (never null)
    ocr_conf: float | None
    objects: list[DetectedObject]  # [] when nothing found (never null: the dashboard reads .length)
    caption: str
    sharpness: float | None
    brightness: float | None
    enhanced: bool


class QaOut(BaseModel):
    id: int
    asked_at: datetime
    language: str
    question: str
    answer: str
    frame_ids: list[int]
    confidence: float
    latency_ms: int


# ---------- Endpoints: phone ----------

@app.post("/ask", response_model=AskResponse)
def ask(request: AskRequest):
    """Answer a spoken question from the stored frames only.
    A plain `def` (not async): FastAPI runs it in a worker thread, so a slow model
    call does not block other requests."""
    return assistant.answer_question(request.question, request.language)


# ---------- Endpoints: dashboard ----------

@app.get("/status", response_model=StatusResponse)
def status():
    """Stream connected?, frames checked per second, frames stored, answer model in use."""
    ingestor = pipeline.get("ingestor")
    model = assistant.last_model_used
    if model == "none":  # no question answered yet: show the configured model
        model = config.GEMINI_MODEL
    return {
        "stream_connected": bool(ingestor and ingestor.stream_connected),
        "fps": ingestor.fps if ingestor else 0.0,
        "frames_stored": db.count_frames(),
        "model": model,
    }


@app.get("/frames", response_model=list[FrameOut])
def frames(start: datetime | None = Query(None, alias="from"),
           end: datetime | None = Query(None, alias="to"),
           limit: int = Query(200, ge=1, le=1000)):
    """Timeline of stored frames, oldest first. Optional ?from=&to= (ISO dates).
    ("from" is a Python keyword, so the parameter is called `start` in the code.)"""
    return db.list_frames(start, end, limit)


@app.get("/frames/{frame_id}/image")
def frame_image(frame_id: int):
    """The JPEG of one frame. 404 if the frame (or its file) was already deleted by retention."""
    frame = db.get_frame(frame_id)
    if frame is None:
        raise HTTPException(status_code=404, detail="Frame not found (maybe deleted by retention)")
    path = (config.SERVER_DIR / frame["image_path"]).resolve()
    if config.FRAMES_DIR.resolve() not in path.parents or not path.is_file():
        raise HTTPException(status_code=404, detail="Image file not found")
    # A frame's image never changes, so the browser may cache it (no re-download every 5 s).
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "max-age=3600"})


@app.get("/qa", response_model=list[QaOut])
def qa(limit: int = Query(100, ge=1, le=1000)):
    """Past questions and answers, newest first."""
    return db.list_qa(limit)
