"""FastAPI web server: the API used by the phone app and the dashboard.

Run (from server/):   uvicorn app.main:app --host 0.0.0.0 --port 8000
Try it in a browser:  http://localhost:8000/docs

At startup it also starts the background pipeline: ingest → vision → database, + retention.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app import assistant, config
from app.ingest import setup_logging, start_pipeline

setup_logging()  # our INFO logs (frame kept/dropped, answer time) in the uvicorn console
pipeline = {}    # the running ingestor and the function that stops everything


@asynccontextmanager
async def lifespan(app):
    """Start the background threads when the server starts, stop them when it stops."""
    pipeline["ingestor"], pipeline["stop"] = start_pipeline()  # loads the AI models (~45 s)
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


# ---------- Endpoints ----------

@app.post("/ask", response_model=AskResponse)
def ask(request: AskRequest):
    """Answer a spoken question from the stored frames only.
    A plain `def` (not async): FastAPI runs it in a worker thread, so a slow model
    call does not block other requests."""
    return assistant.answer_question(request.question, request.language)
