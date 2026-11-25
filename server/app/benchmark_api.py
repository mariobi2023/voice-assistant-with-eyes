"""/benchmark/* endpoints: upload test images in Swagger (http://localhost:8000/docs) and compare
Gemini models, the image enhancement, retrieval and frame selection. Logic: benchmark.py.

Every POST takes the images as multipart files and `?format=json` (default) or `?format=xlsx`
(downloads a formatted Excel file). Nothing is stored. One benchmark runs at a time (409 otherwise).
"""
import json
import threading
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response

from app import benchmark, benchmark_excel, config
from app.languages import normalize_language

router = APIRouter(prefix="/benchmark", tags=["benchmark"])
_busy = threading.Lock()  # a benchmark uses the CPU models and the API keys: one at a time

# Shared parameter types (shown in Swagger with these descriptions).
Files = Annotated[list[UploadFile], File(description=f"1 to {config.BENCHMARK_MAX_IMAGES} JPEG/PNG images")]
Language = Annotated[str, Form(description="en, fr or ar (OCR reader + answer language)")]
Format = Annotated[Literal["json", "xlsx"], Query(description="json = see it here, xlsx = Excel file")]
Question = Annotated[str, Form(min_length=1, max_length=500, description="Asked about every image")]
Models = Annotated[str, Form(description="Comma-separated Gemini models (empty = default list)")]
Expected = Annotated[str, Form(description="Optional comma-separated words: an answer containing "
                                           "one of them counts as correct (e.g. exit,sortie)")]
Mode = Annotated[Literal["auto", "force"], Form(description="auto = pipeline rules (only dark / "
                                                            "slightly blurry images), force = always")]


@router.get("/config")
def benchmark_config():
    """Default settings of the benchmarks. Shows how many API keys are set, never the keys."""
    return {
        "default_models": config.BENCHMARK_MODELS,
        "api_keys_configured": len(config.GEMINI_API_KEYS),
        "max_images": config.BENCHMARK_MAX_IMAGES,
        "max_upload_mb": config.BENCHMARK_MAX_UPLOAD_MB,
        "gemini_timeout_seconds": config.BENCHMARK_GEMINI_TIMEOUT_SECONDS,
        "call_delay_seconds": config.BENCHMARK_CALL_DELAY_SECONDS,
        "overload_retry_seconds": config.BENCHMARK_OVERLOAD_RETRY_SECONDS,
    }


@router.post("/enhancement")
def enhancement(files: Files, language: Language = "en", mode: Mode = "auto",
                format: Format = "json"):
    """OCR text and detected objects on each image BEFORE vs AFTER enhancement
    (brightness, sharpness, words read, OCR confidence, objects gained/lost, time)."""
    images = _load_images(files)
    return _run(format, benchmark.run_enhancement, images, normalize_language(language), mode)


@router.post("/models")
def models(files: Files, question: Question, language: Language = "en", models: Models = "",
           expected: Expected = "", enhance: Annotated[bool, Form(description="Enhance images "
                                                                  "first, like the pipeline")] = True,
           format: Format = "json"):
    """Every Gemini model answers the same question on every image: answer, latency,
    'I'm not sure', 'safe' sentences removed, correct (if `expected` is given). Summary per model."""
    images = _load_images(files)
    return _run(format, benchmark.run_models, images, question, normalize_language(language),
                _parse_models(models), _split(expected), enhance)


@router.post("/full")
def full(files: Files, question: Question, language: Language = "en", models: Models = "",
         expected: Expected = "", mode: Mode = "auto", format: Format = "json"):
    """Everything at once: OCR/objects before vs after enhancement, and every model answering
    on the original AND the enhanced image (does enhancement change the answer?)."""
    images = _load_images(files)
    return _run(format, benchmark.run_full, images, question, normalize_language(language),
                _parse_models(models), _split(expected), mode)


@router.post("/retrieval")
def retrieval(files: Files,
              questions: Annotated[str, Form(description='JSON list, e.g. [{"question": "What did '
                                             'the sign say?", "expected": "exit.jpg"}] ("expected" '
                                             '= file name of the image that answers it)')],
              language: Language = "en", format: Format = "json"):
    """Embedding search quality: similarity of every question to every image, the image ranked
    first, and whether it is the expected one (top-1 accuracy)."""
    parsed = _parse_questions(questions)
    images = _load_images(files)
    return _run(format, benchmark.run_retrieval, images, parsed, normalize_language(language))


@router.post("/frame-selection")
def frame_selection(files: Files, format: Format = "json"):
    """Would the ingest pipeline keep or drop each image (in upload order, like a stream)?
    Brightness, sharpness, enhancement, distance to the last kept image, decision + reason."""
    images = _load_images(files, blur=False)  # numbers only: the image is never shown to a model
    return _run(format, benchmark.run_frame_selection, images)


# ---------- Helpers ----------

def _load_images(files, blur=True):
    """Check the uploads (count, size) and decode them (faces blurred). 422 if invalid."""
    if not 1 <= len(files) <= config.BENCHMARK_MAX_IMAGES:
        raise HTTPException(422, f"Send between 1 and {config.BENCHMARK_MAX_IMAGES} images")
    max_bytes = int(config.BENCHMARK_MAX_UPLOAD_MB * 1024 * 1024)
    images, seen = [], {}
    for upload in files:
        data = upload.file.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise HTTPException(422, f"{upload.filename}: larger than {config.BENCHMARK_MAX_UPLOAD_MB} MB")
        name = upload.filename or "image"
        seen[name] = seen.get(name, 0) + 1
        if seen[name] > 1:  # two files with the same name: keep the rows apart
            name = f"{name} #{seen[name]}"
        images.append(benchmark.decode_image(name, data, blur=blur))
    return images


def _split(text):
    """'a, b,,c' → ['a', 'b', 'c']"""
    return [part.strip() for part in text.split(",") if part.strip()]


def _parse_models(text):
    """The models to compare: the given list, or the default one from config.py."""
    models = _split(text) or config.BENCHMARK_MODELS
    if len(models) > 5:
        raise HTTPException(422, "At most 5 models per benchmark (free-tier rate limits)")
    return list(dict.fromkeys(models))  # no duplicates


def _parse_questions(text):
    """The retrieval questions: a JSON list of {"question", "expected"} objects."""
    try:
        items = json.loads(text)
    except json.JSONDecodeError as error:
        raise HTTPException(422, f"questions is not valid JSON: {error}")
    if (not isinstance(items, list) or not items
            or not all(isinstance(i, dict) and str(i.get("question", "")).strip() for i in items)):
        raise HTTPException(422, 'questions must be a non-empty list of {"question": ..., "expected": ...}')
    return [{"question": str(i["question"]).strip(), "expected": str(i.get("expected") or "")}
            for i in items]


def _run(output_format, function, *args):
    """Run one benchmark (only one at a time) and return it as JSON or as an Excel download."""
    if not _busy.acquire(blocking=False):
        raise HTTPException(409, "A benchmark is already running, try again when it is finished")
    try:
        result = function(*args)
    finally:
        _busy.release()
    if output_format == "json":
        return result
    filename = f"benchmark_{result['info']['benchmark']}_{datetime.now():%Y%m%d_%H%M%S}.xlsx"
    return Response(
        benchmark_excel.build_workbook(result),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
