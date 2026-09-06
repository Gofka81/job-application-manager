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


def _credentials(base: str | None, token: str | None) -> tuple[str, str]:
    base = (base or os.environ.get("JOB_RADAR_API_URL") or "").rstrip("/")
    token = token or os.environ.get("JOB_RADAR_API_TOKEN")
    if not base:
        raise RadarError("JOB_RADAR_API_URL is not set — see .env.example")
    if not token:
        raise RadarError("JOB_RADAR_API_TOKEN is not set — see .env.example")
    return base, token


def _call(path: str, base: str, token: str, payload: dict | None = None):
    # Cloudflare fronts the radar and blocks urllib's default User-Agent at the
    # edge with a 403 — which reads exactly like a bad token, while the app
    # itself answers 401 for that. Sending an ordinary one avoids a confusing
    # dead end.
    body = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(f"{base}{path}", data=body, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "User-Agent": "job-application-hub/0.1",
        **({"Content-Type": "application/json"} if body else {}),
    })
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        hint = {401: " — wrong token?",
                403: " — blocked at the edge, not by the app",
                404: " — no such job"}.get(exc.code, "")
        raise RadarError(f"radar returned {exc.code}{hint}") from exc
    except urllib.error.URLError as exc:
        raise RadarError(f"cannot reach {base}: {exc.reason}") from exc


def detail(job_id: str, base: str | None = None, token: str | None = None) -> dict:
    """One job with its `description` — the plain-text JD.

    The list endpoint leaves it out because it is kilobytes per row, so the
    text is fetched once, for the vacancy actually chosen.
    """
    return _call(f"/api/jobs/{job_id}", *_credentials(base, token))


def set_status(job_id: str, status: str, base: str | None = None,
               token: str | None = None) -> None:
    """Tell the radar a vacancy has been taken, so it leaves the INBOX.

    `saved` when the application folder is created, `applied` only once a
    submission is confirmed — the same distinction the hub makes (D9).
    """
    b, t = _credentials(base, token)
    _call("/api/status", b, t, {"job_id": job_id, "status": status})


def fetch(limit: int = 200, query: str | None = None, sort: str = "score",
          base: str | None = None, token: str | None = None) -> list[Job]:
    """Sorted server-side: once the table outgrows `limit`, ordering a
    newest-first page in the client silently drops older high-scoring rows."""
    base, token = _credentials(base, token)
    url = f"/api/jobs?limit={limit}&sort={sort}" + (f"&q={query}" if query else "")
    # Cloudflare fronts the radar and blocks urllib's default User-Agent at the
    # edge with a 403 — which reads exactly like a bad token, while the app
    # itself answers 401 for that. Sending an ordinary one avoids a confusing
    # dead end.
    return [Job.from_row(r) for r in _call(url, base, token).get("jobs", [])]


def shortlist(jobs: list[Job], min_score: float = 0.0,
              statuses: tuple[str, ...] = ("new",),
              max_age: int | None = None) -> list[Job]:
    """Highest score first, and unscored rows last rather than first."""
    out = [j for j in jobs
           if (not statuses or j.status in statuses)
           and (j.score or 0) >= min_score
           and (max_age is None or (j.age_days or 0) <= max_age)]
    return sorted(out, key=lambda j: (j.score is None, -(j.score or 0)))
