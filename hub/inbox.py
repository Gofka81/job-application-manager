"""Reading the INBOX out of job-radar.

The only place the two systems touch, and it is one-way: the hub reads, the
radar knows nothing about applications. Everything after choosing a vacancy
happens here.

`description` on a job row is the plain-text JD, and `jd_full` says whether it
is complete — the radar sets it false only while a fuller posting is still
fetchable, which is when the JD has to be read off the page instead.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime


class RadarError(RuntimeError):
    pass


@dataclass
class Job:
    job_id: str
    company: str
    title: str
    url: str
    location: str
    source: str
    score: float | None
    reason: str
    status: str
    posted_at: str | None
    first_seen: str | None
    description: str
    jd_full: bool
    salary: str

    @classmethod
    def from_row(cls, row: dict) -> "Job":
        lo, hi = row.get("salary_min"), row.get("salary_max")
        cur = row.get("currency") or ""
        if lo and hi:
            salary = f"{cur}{int(lo/1000)}-{int(hi/1000)}k"
        elif lo or hi:
            salary = f"{cur}{int((lo or hi)/1000)}k"
        else:
            salary = ""
        return cls(
            job_id=row.get("job_id", ""), company=row.get("company") or "",
            title=row.get("title") or "", url=row.get("url") or "",
            location=row.get("location") or "", source=row.get("source") or "",
            score=row.get("score"), reason=row.get("eval_reason") or "",
            status=row.get("status") or "new", posted_at=row.get("posted_at"),
            first_seen=row.get("first_seen"),
            description=row.get("description") or "",
            jd_full=bool(row.get("jd_full", True)), salary=salary,
        )

    @property
    def age_days(self) -> int | None:
        for value in (self.posted_at, self.first_seen):
            if not value:
                continue
            try:
                seen = datetime.fromisoformat(str(value)[:19]).date()
            except ValueError:
                continue
            return (date.today() - seen).days
        return None

    def slug(self) -> str:
        def part(text: str) -> str:
            out = "".join(c.lower() if c.isalnum() else "-" for c in text)
            return "-".join(w for w in out.split("-") if w)[:40]
        return f"{date.today()}--{part(self.company)}--{part(self.title)}"


def fetch(limit: int = 200, query: str | None = None,
          base: str | None = None, token: str | None = None) -> list[Job]:
    base = (base or os.environ.get("JOB_RADAR_API_URL") or "").rstrip("/")
    token = token or os.environ.get("JOB_RADAR_API_TOKEN")
    if not base:
        raise RadarError("JOB_RADAR_API_URL is not set — see .env.example")
    if not token:
        raise RadarError("JOB_RADAR_API_TOKEN is not set — see .env.example")

    url = f"{base}/api/jobs?limit={limit}" + (f"&q={query}" if query else "")
    # Cloudflare fronts the radar and blocks urllib's default User-Agent at the
    # edge with a 403 — which reads exactly like a bad token, while the app
    # itself answers 401 for that. Sending an ordinary one avoids a confusing
    # dead end.
    request = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "User-Agent": "job-application-hub/0.1",
    })
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as exc:
        hint = {401: " — wrong token?",
                403: " — blocked at the edge, not by the app"}.get(exc.code, "")
        raise RadarError(f"radar returned {exc.code}{hint}") from exc
    except urllib.error.URLError as exc:
        raise RadarError(f"cannot reach {base}: {exc.reason}") from exc
    return [Job.from_row(r) for r in payload.get("jobs", [])]


def shortlist(jobs: list[Job], min_score: float = 0.0,
              statuses: tuple[str, ...] = ("new",),
              max_age: int | None = None) -> list[Job]:
    """Highest score first, and unscored rows last rather than first."""
    out = [j for j in jobs
           if (not statuses or j.status in statuses)
           and (j.score or 0) >= min_score
           and (max_age is None or (j.age_days or 0) <= max_age)]
    return sorted(out, key=lambda j: (j.score is None, -(j.score or 0)))
