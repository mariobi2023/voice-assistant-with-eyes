"""Unprompted warnings ("Stairs ahead.", "Door ahead.") without the user asking.

When YOLO-World finds stairs or a door with good confidence (ALERT_MIN_CONF) in a NEW frame,
an alert is created. The phone receives it in one of two ways and speaks it:
- GET /events (preferred): one open connection, the server pushes each alert (Server-Sent Events).
- GET /alerts (fallback): the phone asks every second or so for the new ones.

Rules:
- No repeats: the same alert type at most once every ALERT_COOLDOWN_SECONDS.
- Only fresh alerts are returned (ALERT_MAX_AGE_SECONDS): an old warning is worse than none.
- The text only says what was SEEN ("Stairs ahead."), never that anything is "safe".
- Kept in memory only (not in the database): an alert is useless after a few seconds.
"""
import itertools
import json
import logging
import threading
import time
from collections import deque
from datetime import datetime, timezone

from app import config
from app.languages import ALERT_TEXTS

log = logging.getLogger("alerts")

_alerts = deque(maxlen=config.ALERT_HISTORY_MAX)  # newest at the right; old ones fall off the left
_last_alert_time = {}           # alert type ("stairs") -> time.monotonic() of its last alert
# Alert ids start from the current Unix time (in seconds) and go up by 1 each time.
# The phone remembers the last id it spoke, so ids must keep going up even after a server
# restart: the new start time is always higher than the old ids, because the cooldown keeps
# alerts far below one per second (at most one per type every ALERT_COOLDOWN_SECONDS).
_next_id = itertools.count(int(time.time()))
_lock = threading.Lock()        # the vision thread writes, web requests read


def check_objects(frame_id, objects, captured_at):
    """Called by the vision worker with the objects found in a new frame.
    Creates at most one alert per type, respecting the cooldown. Returns the new alerts."""
    age = (datetime.now(timezone.utc) - captured_at).total_seconds()
    if age > config.ALERT_MAX_AGE_SECONDS:
        return []  # vision was busy: the frame is too old to warn about what is ahead NOW

    created = []
    for alert_type, label in config.ALERT_LABELS.items():
        best = _best_confidence(objects, label)
        if best >= config.ALERT_MIN_CONF:
            alert = _create_if_not_recent(alert_type, best, frame_id, captured_at)
            if alert:
                created.append(alert)
    return created


def _best_confidence(objects, label):
    """Highest confidence of this label in the frame (0 if it was not detected)."""
    return max((o["conf"] for o in objects if o["label"] == label), default=0.0)


def _create_if_not_recent(alert_type, conf, frame_id, captured_at):
    """Add an alert unless the same type was already given less than ALERT_COOLDOWN_SECONDS ago."""
    now = time.monotonic()
    with _lock:
        last = _last_alert_time.get(alert_type)
        if last is not None and now - last < config.ALERT_COOLDOWN_SECONDS:
            return None  # said a moment ago: don't repeat it
        _last_alert_time[alert_type] = now
        alert = {
            "id": next(_next_id),
            "type": alert_type,
            "conf": conf,
            "frame_id": frame_id,
            "created_at": captured_at,  # when the camera saw it
        }
        _alerts.append(alert)
    log.info("Alert %d: %s (conf %.2f, frame %d)", alert["id"], alert_type, conf, frame_id)
    return alert


def recent_alerts(after_id, language):
    """Fresh alerts with id > after_id, oldest first, with the text in the user's language."""
    now = datetime.now(timezone.utc)
    with _lock:
        alerts = list(_alerts)
    return [
        {**a, "text": ALERT_TEXTS[a["type"]][language]}
        for a in alerts
        if a["id"] > after_id
        and (now - a["created_at"]).total_seconds() <= config.ALERT_MAX_AGE_SECONDS
    ]


def to_sse(alert):
    """Format one alert as a Server-Sent Events message:

        id: 1795000012
        event: alert
        data: {"id": 1795000012, "type": "stairs", "text": "Stairs ahead.", ...}
        (empty line = end of message)

    The phone remembers the id; if the connection drops it sends it back as Last-Event-ID."""
    data = {**alert, "created_at": alert["created_at"].isoformat()}
    payload = json.dumps(data, ensure_ascii=False)  # one line; keeps Arabic text readable
    return f"id: {alert['id']}\nevent: alert\ndata: {payload}\n\n"
