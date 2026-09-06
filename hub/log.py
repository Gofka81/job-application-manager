"""Append-only journals.

A line is one event and files are never rewritten. A mistake is corrected by
another event — `source: correction` replaces an earlier record of the same
transition, and a `to` of null retracts one — because editing a line in place
loses the fact that the earlier belief existed.

Current status is not stored anywhere. It is a fold of this file, so there is
one truth about where an application stands rather than two that have to be
kept in step.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

STATUSES = ("submitted", "acknowledged", "in_process", "offer", "rejected",
            "withdrawn")

# Where a record came from. `backfill` and `manual` are excluded from latency
# maths: a date written after the fact is not an observation of time.
SOURCES = ("email", "portal", "manual", "correction", "backfill")
DAY_MATH_SOURCES = ("email", "portal", "manual", "correction")


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def append(path: Path, event: dict) -> dict:
    event = {"ts": now(), **event}
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")
    return event


def read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except ValueError:
            continue          # a damaged line is skipped, never fatal
    return out


def status_event(app_id: str, to: str | None, source: str = "manual",
                 previous: str | None = None, note: str = "") -> dict:
    if to is not None and to not in STATUSES:
        raise ValueError(f"status must be one of {STATUSES}")
    if source not in SOURCES:
        raise ValueError(f"source must be one of {SOURCES}")
    return {"app_id": app_id, "from": previous, "to": to,
            "source": source, "note": note}


def fold(events: list[dict], app_id: str | None = None) -> dict[str, str]:
    """Current status per application, latest observation wins.

    A `to` of null retracts the row's latest observation rather than deleting
    a line, and a `correction` replaces the earlier record of the same
    transition.
    """
    timeline: dict[str, list[dict]] = {}
    for event in sorted(events, key=lambda e: e.get("ts", "")):
        key = event.get("app_id")
        if not key or (app_id and key != app_id):
            continue
        seen = timeline.setdefault(key, [])
        if event.get("to") is None:
            if seen:
                seen.pop()
            continue
        if event.get("source") == "correction":
            for i, earlier in enumerate(seen):
                if earlier.get("to") == event.get("to"):
                    seen[i] = event
                    break
            else:
                seen.append(event)
            continue
        seen.append(event)
    return {key: events[-1]["to"] for key, events in timeline.items() if events}
