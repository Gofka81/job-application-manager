"""Turning a vacancy into an application folder.

The one place the two systems meet in the other direction: the hub tells the
radar a vacancy has been taken, so it leaves the INBOX and cannot be applied
to twice.

`saved` is set here and `applied` only once a submission is confirmed (D9).
The distinction matters: a folder that exists is not an application that
happened, and counting the first as the second inflates every funnel built on
top.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
from datetime import date, datetime
from pathlib import Path

# Where the posting lives, which is not the same as where you found it (D25).
CHANNEL_BY_SOURCE = {
    "greenhouse": "greenhouse", "lever": "lever", "ashby": "ashby",
    "workday": "workday", "linkedin": "linkedin", "indeed": "indeed",
    "reed": "reed", "adzuna": "adzuna",
}


def slugify(text: str, limit: int = 40) -> str:
    out = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return out[:limit].strip("-") or "unknown"


def app_id(company: str, title: str, when: date | None = None) -> str:
    """The join key, and the folder name. Assigned once and never changed."""
    return f"{when or date.today()}--{slugify(company, 24)}--{slugify(title)}"


def already_applied(root: Path, company: str, title: str) -> list[str]:
    """Existing applications to the same company and role.

    The same vacancy resurfaces months later from another source, and by then
    nobody remembers (D27). This does not block; it tells you.
    """
    want_company, want_title = slugify(company, 24), slugify(title)
    out = []
    for folder in sorted(root.glob("*/application.json")):
        try:
            record = json.loads(folder.read_text())
        except (OSError, ValueError):
            continue
        if (slugify(record.get("company", ""), 24) == want_company
                and slugify(record.get("title", "")) == want_title):
            out.append(folder.parent.name)
    return out


def record(job: dict, when: date | None = None,
           discovery: str = "radar") -> dict:
    """`application.json` for a vacancy being taken.

    `submitted_at` stays null until a submission is confirmed, and there is no
    status field at all: status is a fold of the log, and a second copy here
    would be a second truth to keep in step.

    `discovery` is how it was found — "radar" or "link". The radar's own
    fields stay empty on a link, rather than taking a default: a score
    invented here would be indistinguishable later from one the radar gave,
    which is what `score_source` exists to keep answerable.
    """
    description = job.get("description") or ""
    return {
        "app_id": app_id(job.get("company", ""), job.get("title", ""), when),
        "company": job.get("company"),
        "title": job.get("title"),
        "source_url": job.get("url"),
        "channel": CHANNEL_BY_SOURCE.get(job.get("source", ""), job.get("source")),
        "discovery": discovery,
        "role_archetype": None,
        "cv_version": None,
        "radar_score": job.get("score"),
        "score_source": "radar" if job.get("score") is not None else None,
        "radar_job_id": job.get("job_id"),
        "jd_hash": hashlib.sha1(description.encode()).hexdigest() if description else None,
        "jd_full": bool(job.get("jd_full", True)),
        "posted_at": job.get("posted_at"),
        "submitted_at": None,
    }


def create(root: Path, job: dict, when: date | None = None,
           discovery: str = "radar") -> tuple[Path, dict]:
    """Write the folder. Returns where it went and what was written."""
    data = record(job, when, discovery)
    folder = root / data["app_id"]
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "application.json").write_text(json.dumps(data, indent=2) + "\n")

    description = job.get("description") or ""
    header = (f"# {job.get('title')} — {job.get('company')}\n\n"
              f"{job.get('url')}\n\n")
    if not description:
        header += ("_The radar holds no text for this posting. Read it from the "
                   "page and paste it here._\n")
    (folder / "jd.md").write_text(header + description + "\n")
    return folder, data


def discard(folder: Path, trash: Path) -> Path:
    """Take an application out of the working set.

    Moved rather than deleted. A folder holds a tailored CV, a coverage
    record and the notes behind both, which is an hour of work and a
    keystroke away from gone; a wrong `y` should be recoverable. The list
    reads `applications/*/application.json`, so anything under `trash` is
    already invisible to every screen without deleting a byte.

    The status log is left alone. It is append-only by design: a submission
    that happened still happened, whatever became of the folder.
    """
    if not folder.is_dir():
        raise FileNotFoundError(folder)
    trash.mkdir(parents=True, exist_ok=True)
    target = trash / folder.name
    if target.exists():
        stamp = datetime.now().strftime("%H%M%S")
        target = trash / f"{folder.name}--{stamp}"
    return Path(shutil.move(str(folder), str(target)))
