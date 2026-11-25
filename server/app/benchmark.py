"""Benchmarks on uploaded test images (used by the /benchmark/* endpoints in benchmark_api.py).

What can be compared:
  - enhancement      OCR + YOLO on the original image vs the enhanced image (enhance.py)
  - models           several Gemini models answering the same question on the same images
  - full             both at once: every model on the original AND the enhanced image
  - retrieval        does the embedding search find the right image for each question?
  - frame selection  would the ingest pipeline keep or drop each image, and why?

Rules (same as the live system):
  - Faces are blurred right after decoding, before OCR, YOLO or any model sees the image.
  - Nothing is stored: images stay in memory, nothing goes to the database or to disk.
  - Answers use the same prompt as /ask and go through remove_safe_claims().

Every run returns {"info": {...settings...}, "tables": {"Summary": [rows], ...}}: a row is a
flat dict, so the same result can be sent as JSON or written as an Excel sheet.
"""
import logging
import statistics
import time
from datetime import datetime, timezone

import cv2
import numpy as np

from app import assistant, config, embeddings, enhance, privacy, vision
from app.ingest import check_and_enhance, compute_phash, measure_brightness, measure_sharpness, \
    resize_to_max_width
from app.languages import NOT_SURE

log = logging.getLogger("benchmark")


# ---------- Loading the uploaded images ----------

def decode_image(name, data, blur=True):
    """Bytes of an uploaded file → {"name", "frame", "faces", "error"}.
    The frame is resized like a stream frame (FRAME_MAX_WIDTH) and its faces are blurred
    (blur=False only for the frame-selection test, which never shows the image to a model)."""
    image = {"name": name, "frame": None, "faces": 0, "error": None}
    frame = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        image["error"] = "not a readable image (use JPEG or PNG)"
        return image
    frame = resize_to_max_width(frame, config.FRAME_MAX_WIDTH)
    if blur:
        try:
            image["faces"] = privacy.blur_faces(frame)  # in place; never analyze an unblurred face
        except Exception as error:
            image["error"] = f"face blurring failed ({error}), image skipped"
            return image
    image["frame"] = frame
    return image


def measure(frame):
    """(brightness, sharpness) of a frame, the same measures as the ingest pipeline."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return round(measure_brightness(gray), 1), round(measure_sharpness(gray), 1)


def enhanced_version(frame, mode):
    """The enhanced frame and the steps used.
    mode "auto":  the pipeline rules (only dark → brighten, only slightly blurry → sharpen).
    mode "force": always brighten + sharpen, to see the effect on every image."""
    if mode == "force":
        return enhance.sharpen(enhance.brighten(frame)), ["brighten", "sharpen"]
    checked = check_and_enhance(frame)
    return checked["frame"], checked["steps"]


# ---------- Vision (OCR + YOLO) on one frame ----------

def analyze(frame, language):
    """Objects + OCR on one frame, with the time each one took."""
    started = time.monotonic()
    objects = vision.detect_objects(frame)
    yolo_done = time.monotonic()
    ocr_text, ocr_conf = vision.run_ocr(frame, language)
    ocr_done = time.monotonic()
    return {
        "ocr_text": ocr_text,
        "ocr_conf": ocr_conf,
        "ocr_words": len(ocr_text.split()),
        "objects": objects,
        "caption": vision.build_caption(objects),
        "object_count": len(objects),
        "object_mean_conf": round(statistics.mean(o["conf"] for o in objects), 3) if objects else None,
        "yolo_ms": int((yolo_done - started) * 1000),
        "ocr_ms": int((ocr_done - yolo_done) * 1000),
    }


def change(before, after):
    """'better' / 'worse' / 'same' when comparing two numbers (None counts as 0)."""
    before, after = before or 0, after or 0
    if after > before:
        return "better"
    if after < before:
        return "worse"
    return "same"


def vision_row(image, original, enhanced, steps, language):
    """One row of the enhancement comparison: the same image before and after enhancement."""
    before = analyze(original, language)
    # Nothing was enhanced (auto mode, normal image): "after" is the same picture, don't run it twice.
    after = analyze(enhanced, language) if steps else before
    labels_before = {o["label"] for o in before["objects"]}
    labels_after = {o["label"] for o in after["objects"]}
    brightness_before, sharpness_before = measure(original)
    brightness_after, sharpness_after = measure(enhanced)
    # OCR is better if it reads more words; with the same number of words, if it is more confident.
    ocr_change = change(before["ocr_words"], after["ocr_words"])
    if ocr_change == "same":
        ocr_change = change(before["ocr_conf"], after["ocr_conf"])
    return {
        "image": image["name"],
        "faces_blurred": image["faces"],
        "enhancement": " + ".join(steps) or "none",
        "brightness_before": brightness_before, "brightness_after": brightness_after,
        "sharpness_before": sharpness_before, "sharpness_after": sharpness_after,
        "ocr_text_before": before["ocr_text"], "ocr_text_after": after["ocr_text"],
        "ocr_words_before": before["ocr_words"], "ocr_words_after": after["ocr_words"],
        "ocr_conf_before": before["ocr_conf"], "ocr_conf_after": after["ocr_conf"],
        "ocr_change": ocr_change,
        "objects_before": before["caption"], "objects_after": after["caption"],
        "object_count_before": before["object_count"], "object_count_after": after["object_count"],
        "object_conf_before": before["object_mean_conf"], "object_conf_after": after["object_mean_conf"],
        "objects_change": change(before["object_count"], after["object_count"]),
        "labels_gained": ", ".join(sorted(labels_after - labels_before)),
        "labels_lost": ", ".join(sorted(labels_before - labels_after)),
        "ocr_ms_before": before["ocr_ms"], "ocr_ms_after": after["ocr_ms"],
        "yolo_ms_before": before["yolo_ms"], "yolo_ms_after": after["yolo_ms"],
    }, before, after


def summarize_vision(rows):
    """Summary of the enhancement comparison: how often enhancement helped OCR / objects."""
    def count(column, value):
        return sum(1 for r in rows if r[column] == value)
    enhanced_rows = [r for r in rows if r["enhancement"] != "none"]
    return [{
        "images": len(rows),
        "images_enhanced": len(enhanced_rows),
        "ocr_better": count("ocr_change", "better"),
        "ocr_same": count("ocr_change", "same"),
        "ocr_worse": count("ocr_change", "worse"),
        "objects_better": count("objects_change", "better"),
        "objects_same": count("objects_change", "same"),
        "objects_worse": count("objects_change", "worse"),
        "avg_ocr_words_before": _mean(r["ocr_words_before"] for r in rows),
        "avg_ocr_words_after": _mean(r["ocr_words_after"] for r in rows),
        "avg_objects_before": _mean(r["object_count_before"] for r in rows),
        "avg_objects_after": _mean(r["object_count_after"] for r in rows),
    }]


# ---------- Gemini answers ----------

def call_gemini(model, system_prompt, user_text, images):
    """One benchmark call to a Gemini model. Returns (answer, error, key number, latency_ms, tries).
    - HTTP 429 (free-tier rate limit) → try again with the next API key, once per key.
    - Model refuses the "thinking" setting (e.g. gemini-3.8-flash) → try again without it.
    - HTTP 503 (model overloaded, "high demand") → wait a little and try once more."""
    keys = len(config.GEMINI_API_KEYS)
    if keys == 0:
        return None, "no Gemini API key configured (GEMINI_API_KEYS in .env)", None, None, 0
    thinking = config.GEMINI_THINKING_LEVEL
    rate_limited, tries, last_error, overload_retried = 0, 0, "", False
    while rate_limited < keys:
        if config.BENCHMARK_CALL_DELAY_SECONDS:
            time.sleep(config.BENCHMARK_CALL_DELAY_SECONDS)  # be gentle with the free tier
        key = assistant.next_key_index()
        tries += 1
        started = time.monotonic()
        try:
            answer = assistant.ask_gemini(system_prompt, user_text, images, model=model, key_index=key,
                                          thinking_level=thinking,
                                          timeout_seconds=config.BENCHMARK_GEMINI_TIMEOUT_SECONDS)
            return answer, None, key + 1, int((time.monotonic() - started) * 1000), tries
        except Exception as error:
            last_error = str(error)[:300]
            if thinking and "thinking" in last_error.lower():
                log.info("%s does not accept thinking_level, retrying without it", model)
                thinking = None
            elif "429" in last_error or "RESOURCE_EXHAUSTED" in last_error:
                log.info("%s: key %d rate limited, trying the next key", model, key + 1)
                rate_limited += 1
            elif ("503" in last_error or "UNAVAILABLE" in last_error) and not overload_retried:
                log.info("%s is overloaded (503), retrying in %.0f s", model,
                         config.BENCHMARK_OVERLOAD_RETRY_SECONDS)
                overload_retried = True
                time.sleep(config.BENCHMARK_OVERLOAD_RETRY_SECONDS)
            else:
                return None, last_error, key + 1, None, tries
    return None, f"rate limited on all {keys} key(s): {last_error}", None, None, tries


def find_expected(answer, expected):
    """The first expected word found in the answer (case ignored), or None."""
    lowered = answer.casefold()
    return next((word for word in expected if word.casefold() in lowered), None)


def answer_row(image_name, version, model, frame, analysis, question, language, expected):
    """Ask one model about one image (same prompt + 'safe' filter as /ask). Returns one table row."""
    evidence = {"id": 1, "age_seconds": 0, "ocr_text": analysis["ocr_text"], "caption": analysis["caption"]}
    system_prompt, user_text = assistant.build_prompts(question, language, [evidence])
    image = assistant.encode_jpeg(frame, config.GEMINI_IMAGE_WIDTH)
    raw, error, key, latency_ms, tries = call_gemini(model, system_prompt, user_text, [image])
    answer = assistant.remove_safe_claims(raw) if raw else ""
    row = {
        "image": image_name, "version": version, "model": model,
        "answer": answer, "latency_ms": latency_ms, "error": error or "",
        "said_not_sure": bool(answer) and NOT_SURE[language].rstrip(".") in answer,
        "safe_removed": bool(raw) and answer != raw.strip(),
        "api_key": key, "tries": tries,
    }
    if expected:
        found = find_expected(answer, expected) if answer else None
        row["expected_found"] = found or ""
        row["correct"] = found is not None
    log.info("Benchmark %s on %s (%s): %s", model, image_name, version, error or answer)
    return row


def summarize_answers(rows, by=("model",)):
    """One summary row per model (or per model + version): speed, success, accuracy."""
    groups = {}
    for row in rows:
        groups.setdefault(tuple(row[k] for k in by), []).append(row)
    summary = []
    for key, group in groups.items():
        answered = [r for r in group if not r["error"]]
        latencies = [r["latency_ms"] for r in answered if r["latency_ms"] is not None]
        item = dict(zip(by, key))
        item.update({
            "calls": len(group),
            "answered": len(answered),
            "errors": len(group) - len(answered),
            "success_pct": _pct(len(answered), len(group)),
            "avg_latency_ms": int(statistics.mean(latencies)) if latencies else None,
            "median_latency_ms": int(statistics.median(latencies)) if latencies else None,
            "max_latency_ms": max(latencies) if latencies else None,
            "said_not_sure": sum(1 for r in answered if r["said_not_sure"]),
            "safe_removed": sum(1 for r in answered if r["safe_removed"]),
        })
        if "correct" in group[0]:
            item["correct"] = sum(1 for r in group if r["correct"])
            item["accuracy_pct"] = _pct(item["correct"], len(group))
        summary.append(item)
    return summary


# ---------- The benchmarks ----------

def run_enhancement(images, language, mode):
    """OCR + objects before vs after enhancement, for every image."""
    rows, errors = [], []
    for image in images:
        if image["error"]:
            errors.append(_error_row(image))
            continue
        enhanced, steps = enhanced_version(image["frame"], mode)
        rows.append(vision_row(image, image["frame"], enhanced, steps, language)[0])
    return _result("enhancement", {"language": language, "mode": mode},
                   {"Summary": summarize_vision(rows), "Vision": rows, "Errors": errors})


def run_models(images, question, language, models, expected, use_enhancement):
    """Every model answers the same question about every image."""
    rows, errors = [], []
    for image in images:
        if image["error"]:
            errors.append(_error_row(image))
            continue
        frame, steps = (enhanced_version(image["frame"], "auto") if use_enhancement
                        else (image["frame"], []))
        version = "enhanced" if steps else "original"
        analysis = analyze(frame, language)  # OCR + objects once, shared by all models
        for model in models:
            rows.append(answer_row(image["name"], version, model, frame, analysis, question,
                                   language, expected))
    info = {"question": question, "language": language, "models": ", ".join(models),
            "expected": ", ".join(expected), "enhancement": "auto" if use_enhancement else "off"}
    return _result("models", info,
                   {"Summary": summarize_answers(rows), "Answers": rows, "Errors": errors})


def run_full(images, question, language, models, expected, mode):
    """Every model on the original AND the enhanced image, plus the vision comparison."""
    vision_rows, answers, comparison, errors = [], [], [], []
    for image in images:
        if image["error"]:
            errors.append(_error_row(image))
            continue
        enhanced, steps = enhanced_version(image["frame"], mode)
        row, before, after = vision_row(image, image["frame"], enhanced, steps, language)
        vision_rows.append(row)
        for model in models:
            a = answer_row(image["name"], "original", model, image["frame"], before, question,
                           language, expected)
            # Not enhanced: the "enhanced" answer would be the same picture, don't spend a call.
            b = (answer_row(image["name"], "enhanced", model, enhanced, after, question, language,
                            expected) if steps else {**a, "version": "enhanced"})
            answers += [a, b]
            comparison.append(_compare_answers(image["name"], model, row["enhancement"], a, b))
    info = {"question": question, "language": language, "models": ", ".join(models),
            "expected": ", ".join(expected), "mode": mode}
    return _result("full", info, {
        "Summary": summarize_answers(answers, by=("model", "version")),
        "Vision summary": summarize_vision(vision_rows),
        "Before vs after": comparison,
        "Vision": vision_rows,
        "Answers": answers,
        "Errors": errors,
    })


def run_retrieval(images, questions, language):
    """For each question: which image does the embedding search rank first? Is it the expected one?
    Images are analyzed like stored frames (pipeline enhancement, then OCR + objects)."""
    names, vectors, image_rows, errors = [], [], [], []
    for image in images:
        if image["error"]:
            errors.append(_error_row(image))
            continue
        frame, _steps = enhanced_version(image["frame"], "auto")
        analysis = analyze(frame, language)
        text = embeddings.build_frame_text(analysis["ocr_text"], analysis["caption"])
        names.append(image["name"])
        vectors.append(embeddings.embed_text(text))  # None: nothing read or seen → never found
        image_rows.append({"image": image["name"], "embedded_text": text or "(nothing read or seen)"})

    rows = []
    for item in questions:
        query = embeddings.embed_text(item["question"])
        # Vectors are normalized, so the dot product IS the cosine similarity used by pgvector.
        sims = {n: (round(float(np.dot(query, v)), 3) if v is not None else None)
                for n, v in zip(names, vectors)}
        ranked = sorted((s, n) for n, s in sims.items() if s is not None)[::-1]
        top_sim, top_name = ranked[0] if ranked else (None, "")
        expected = item.get("expected") or ""
        rank = next((i + 1 for i, (_s, n) in enumerate(ranked) if n == expected), None)
        row = {
            "question": item["question"],
            "route": assistant.route_question(item["question"], language),
            "expected": expected,
            "top1": top_name,
            "top1_similarity": top_sim,
            "expected_similarity": sims.get(expected),
            "expected_rank": rank,
            "correct": bool(expected) and top_name == expected,
            "above_min_similarity": top_sim is not None and top_sim >= config.MIN_SIMILARITY,
        }
        row.update({f"sim: {n}": s for n, s in sims.items()})
        rows.append(row)

    with_expected = [r for r in rows if r["expected"]]
    right = [r["expected_similarity"] for r in with_expected if r["expected_similarity"] is not None]
    wrong = [s for r in with_expected for n, s in _sim_columns(r) if n != r["expected"] and s is not None]
    summary = [{
        "questions": len(rows),
        "images": len(names),
        "top1_correct": sum(1 for r in with_expected if r["correct"]),
        "top1_accuracy_pct": _pct(sum(1 for r in with_expected if r["correct"]), len(with_expected)),
        "would_say_not_sure": sum(1 for r in rows if not r["above_min_similarity"]),
        "min_similarity": config.MIN_SIMILARITY,
        "avg_similarity_expected_image": _mean(right, 3),
        "avg_similarity_other_images": _mean(wrong, 3),
    }]
    info = {"language": language, "note": "Embedding search only (route 'past'). The 'text' route "
            "first tries an OCR keyword match, which this test does not include."}
    return _result("retrieval", info, {"Summary": summary, "Questions": rows,
                                       "Images": image_rows, "Errors": errors})


def run_frame_selection(images):
    """Would the ingest pipeline keep each image? Images are checked in upload order, like a
    stream: the 'same scene' check compares with the last KEPT image."""
    rows, errors, last_hash = [], [], None
    for image in images:
        if image["error"]:
            errors.append(_error_row(image))
            continue
        frame = image["frame"]
        checked = check_and_enhance(frame)  # exactly the ingest decision
        height, width = frame.shape[:2]
        row = {
            "image": image["name"], "size": f"{width}x{height}",
            "brightness": round(checked["brightness"], 1),
            "dark": enhance.is_dark(checked["brightness"]),
            "sharpness": round(checked["sharpness"], 1),
            "slightly_blurry": enhance.is_slightly_blurry(checked["sharpness"]),
            "enhancement": " + ".join(checked["steps"]) or "none",
            "hash_distance": None, "faces": 0,
        }
        reason = checked["drop_reason"]
        if not reason:
            frame_hash = compute_phash(checked["frame"])
            if last_hash is not None:
                row["hash_distance"] = int(frame_hash - last_hash)  # number of different bits
                if row["hash_distance"] < config.HASH_MIN:
                    reason = f"same scene (hash distance {row['hash_distance']} < {config.HASH_MIN})"
        if not reason:
            try:  # ingest blurs faces at this point (only kept frames)
                row["faces"] = privacy.blur_faces(checked["frame"].copy())
            except Exception:
                reason = "face blurring failed"
        if not reason:
            last_hash = frame_hash  # the next image is compared with this one
        row["decision"] = "dropped" if reason else "kept"
        row["reason"] = reason or ""
        rows.append(row)
    summary = [{
        "images": len(rows),
        "kept": sum(1 for r in rows if r["decision"] == "kept"),
        "dropped_blurry": sum(1 for r in rows if r["reason"].startswith("blurry")),
        "dropped_same_scene": sum(1 for r in rows if r["reason"].startswith("same scene")),
        "enhanced": sum(1 for r in rows if r["enhancement"] != "none"),
        "sharpness_min": config.SHARPNESS_MIN, "hash_min": config.HASH_MIN,
        "dark_max": config.DARK_MAX, "slightly_blurry_max": config.SLIGHTLY_BLURRY_MAX,
    }]
    return _result("frame-selection", {}, {"Summary": summary, "Frames": rows, "Errors": errors})


# ---------- Small helpers ----------

def _compare_answers(image_name, model, enhancement, a, b):
    """One row: the same model's answer on the original vs the enhanced image."""
    row = {"image": image_name, "model": model, "enhancement": enhancement,
           "answer_original": a["answer"] or a["error"], "answer_enhanced": b["answer"] or b["error"],
           "same_answer": a["answer"] == b["answer"],
           "latency_ms_original": a["latency_ms"], "latency_ms_enhanced": b["latency_ms"]}
    if "correct" in a:
        row["correct_original"], row["correct_enhanced"] = a["correct"], b["correct"]
        row["result"] = change(int(a["correct"]), int(b["correct"]))
    return row


def _sim_columns(row):
    """(image name, similarity) pairs from the 'sim: <image>' columns of a retrieval row."""
    return [(k[5:], v) for k, v in row.items() if k.startswith("sim: ")]


def _error_row(image):
    return {"image": image["name"], "error": image["error"]}


def _mean(values, digits=1):
    values = list(values)
    return round(statistics.mean(values), digits) if values else None


def _pct(part, total):
    return round(100 * part / total, 1) if total else None


def _result(kind, info, tables):
    """The common result shape. Empty tables (e.g. no errors) are left out."""
    info = {"benchmark": kind, "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            **info}
    return {"info": info, "tables": {name: rows for name, rows in tables.items() if rows}}
