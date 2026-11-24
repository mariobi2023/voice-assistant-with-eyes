"""Retention: automatically delete old frames — database rows AND image files.

Every RETENTION_CHECK_SECONDS a background thread:
  1. deletes frame rows older than RETENTION_MINUTES and their JPEG files;
  2. sweeps frames/ for leftover JPEGs older than that (e.g. a file saved while the DB was down),
     so no image is ever kept longer than allowed.
"""
import logging
import threading
import time

from app import config, db

log = logging.getLogger("retention")


def delete_file(relative_path):
    """Delete one frame file (path relative to server/). Returns True if a file was removed."""
    full_path = (config.SERVER_DIR / relative_path).resolve()
    if config.FRAMES_DIR.resolve() not in full_path.parents:
        log.warning("Refusing to delete a file outside frames/: %s", relative_path)
        return False
    try:
        full_path.unlink()
        return True
    except FileNotFoundError:
        return False  # already gone: nothing to do


def sweep_old_files(max_age_seconds):
    """Delete JPEGs in frames/ whose file time is older than max_age_seconds. Returns how many."""
    if not config.FRAMES_DIR.exists():
        return 0
    cutoff = time.time() - max_age_seconds
    removed = 0
    for path in config.FRAMES_DIR.glob("*.jpg"):
        if path.stat().st_mtime < cutoff:
            path.unlink(missing_ok=True)
            removed += 1
    return removed


def run_retention_once():
    """One cleanup pass. Returns (rows deleted, files deleted)."""
    paths = db.delete_frames_older_than(config.RETENTION_MINUTES)  # rows first...
    files = sum(delete_file(p) for p in paths)                      # ...then their files
    files += sweep_old_files(config.RETENTION_MINUTES * 60)         # ...then any leftovers
    if paths or files:
        log.info("Retention: deleted %d rows and %d files older than %s min",
                 len(paths), files, config.RETENTION_MINUTES)
    return len(paths), files


def _retention_loop(stop_event):
    """Run a cleanup pass now and then every RETENTION_CHECK_SECONDS until stopped."""
    while not stop_event.is_set():
        try:
            run_retention_once()
        except Exception:
            log.exception("Retention pass failed, will retry")  # e.g. DB briefly down: keep the thread alive
        stop_event.wait(config.RETENTION_CHECK_SECONDS)


def start_retention_thread(stop_event):
    """Start the cleanup loop in a background (daemon) thread."""
    thread = threading.Thread(target=_retention_loop, args=(stop_event,), name="retention", daemon=True)
    thread.start()
    log.info("Retention started: keeping frames for %s min, checking every %s s",
             config.RETENTION_MINUTES, config.RETENTION_CHECK_SECONDS)
    return thread
