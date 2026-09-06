"""Recording that an application was actually sent.

The one thing WF3 leaves behind. It runs after a human has pressed Submit, not
before: a filled form is not an application, and a folder that exists is not
one either. Counting either as a submission inflates every rate built on top.

Four things happen, in an order chosen so a failure never leaves a lie:

  1. the journal gets `submitted` — the fact, locally, first
  2. application.json gets `submitted_at`, which starts the aging clock
  3. the radar is told `applied`, so the vacancy leaves the INBOX
  4. the watchdog on the Pi is pinged, so it knows the search is alive

Only the first two are ours. The last two cross a network and are allowed to
fail: the application still happened, and both can be repeated.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from hub import log


class NotAnApplication(ValueError):
    pass


def load(folder: Path) -> dict:
    path = folder / "application.json"
    if not path.exists():
        raise NotAnApplication(f"no application.json in {folder}")
    return json.loads(path.read_text())


def ping_watchdog(url: str | None = None) -> str:
    """Tell the Pi a submission happened. Date only, fire and forget.

    Sent at Submit rather than at session start: opening a session without
    applying is not activity, and a watchdog counting sessions would stay
    quiet in exactly the case it exists for.
    """
    url = url or os.environ.get("WATCHDOG_URL")
    if not url:
        return "no WATCHDOG_URL, skipped"
    payload = json.dumps({"last_submission": datetime.now(timezone.utc)
                          .date().isoformat()}).encode()
    request = urllib.request.Request(url, data=payload, headers={
        "Content-Type": "application/json",
        "User-Agent": "job-application-hub/0.1",
        "CF-Access-Client-Id": os.environ.get("CF_ACCESS_CLIENT_ID", ""),
        "CF-Access-Client-Secret": os.environ.get("CF_ACCESS_CLIENT_SECRET", ""),
    })
    try:
        with urllib.request.urlopen(request, timeout=10):
            return "pinged"
    except (urllib.error.URLError, OSError) as exc:
        return f"not pinged: {exc}"


def record(folder: Path, logs: Path, note: str = "") -> dict:
    """Write the submission. Returns what was recorded."""
    application = load(folder)
    if application.get("submitted_at"):
        raise NotAnApplication(
            f"{application['app_id']} was already submitted on "
            f"{application['submitted_at']}")

    event = log.append(logs / "status.jsonl", log.status_event(
        application["app_id"], "submitted", source="manual", note=note))

    application["submitted_at"] = event["ts"]
    (folder / "application.json").write_text(
        json.dumps(application, indent=2) + "\n")
    return application
