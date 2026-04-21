"""
Error Recovery
==============
Retry logic and error tracking for the Bolt pipeline.
"""

import os
import time
import shutil
import json
import urllib.request
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

DISCORD_WEBHOOK       = os.getenv("DISCORD_WEBHOOK_URL", "")
MAX_ERRORS_BEFORE_ALERT = int(os.getenv("MAX_ERRORS_BEFORE_ALERT", "3"))


def with_retry(fn, *args, retries: int = 3, label: str = "",
               reraise: bool = False, **kwargs):
    delay = 5
    last_exc = None
    for attempt in range(1, retries + 1):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            last_exc = exc
            print(f"[ErrorRecovery] {label or fn.__name__} attempt {attempt}/{retries} failed: {exc}")
            if attempt < retries:
                time.sleep(delay)
                delay *= 3
    if reraise and last_exc:
        raise last_exc
    return None


class ErrorTracker:
    def __init__(self):
        self._errors   = []
        self._counts   = {}
        self._alerted  = set()

    def record(self, stage: str, context: str, error: Exception):
        entry = {
            "stage":   stage,
            "context": context,
            "error":   str(error),
            "time":    datetime.now().isoformat(),
        }
        self._errors.append(entry)
        self._counts[stage] = self._counts.get(stage, 0) + 1
        print(f"[ErrorTracker] {stage}: {error}")
        if (self._counts[stage] >= MAX_ERRORS_BEFORE_ALERT
                and stage not in self._alerted):
            self._alerted.add(stage)
            self._alert_discord(stage, error)

    def quarantine(self, file_path: str, reason: str = ""):
        os.makedirs("quarantine", exist_ok=True)
        dest = os.path.join("quarantine", os.path.basename(file_path))
        try:
            shutil.move(file_path, dest)
            print(f"[ErrorTracker] Quarantined: {file_path} → {dest} ({reason})")
        except Exception as exc:
            print(f"[ErrorTracker] Could not quarantine {file_path}: {exc}")

    def send_summary(self):
        if not self._errors:
            print("[ErrorTracker] No errors this session.")
            return
        print(f"[ErrorTracker] Session errors: {len(self._errors)}")
        for stage, count in sorted(self._counts.items(), key=lambda x: -x[1]):
            print(f"  {stage}: {count}x")

    def _alert_discord(self, stage: str, error: Exception):
        if not DISCORD_WEBHOOK:
            return
        body = {"content": f"⚠️ **Bolt error alert** | {stage} failed {self._counts[stage]}x\nLatest: {error}"}
        try:
            req = urllib.request.Request(
                DISCORD_WEBHOOK,
                data    = json.dumps(body).encode(),
                headers = {"Content-Type": "application/json"},
                method  = "POST",
            )
            urllib.request.urlopen(req, timeout=5)
        except Exception:
            pass


_tracker = None


def get_tracker() -> ErrorTracker:
    global _tracker
    if _tracker is None:
        _tracker = ErrorTracker()
    return _tracker


def record_error(stage: str, context: str, error: Exception):
    get_tracker().record(stage, context, error)


def session_summary():
    get_tracker().send_summary()
