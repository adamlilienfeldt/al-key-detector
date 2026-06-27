"""Simpel JSONL event-log til dataanalyse. Hver linje = ét event m. ts + felter."""
import json
import os
import time

LOG_PATH = os.path.expanduser("~/Library/Logs/AL_KEY_DETECTOR_web.jsonl")


def log_event(event_type, path=None, **fields):
    rec = {"ts": time.time(), "type": event_type, **fields}
    p = path or LOG_PATH
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "a") as f:
        f.write(json.dumps(rec) + "\n")
    return rec
