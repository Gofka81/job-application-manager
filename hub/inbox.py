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

import yaml
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
    remote: bool | None
    locations: list

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
            remote=row.get("remote"), locations=row.get("locations") or [],
        )

    def tier(self, priority: tuple[str, ...]) -> int:
        """0 a priority city, 1 UK-remote, 2 everything else.

        The radar's dashboard sorts by this before score, and the reason is in
        its own comment: scarce roles would otherwise be buried under London's
        volume. Somewhere with three postings a month never outbids somewhere
        with three hundred on score alone.
        """
        places = [p.lower() for p in (self.locations or [self.location]) if p]
        if any(city in place for place in places for city in priority):
            return 0
        if self.remote or any("remote" in place for place in places):
            return 1
        return 2

    @property
    def where(self) -> str:
        """Remote is a column of its own in the radar; showing it beside the
        place saves reading a location string to find out."""
        if self.remote:
            return f"remote · {self.location}" if self.location else "remote"
        return self.location

    @staticmethod
    def _stamp(value) -> tuple[datetime, bool] | None:
        """One stamp read, with whether it carries a clock and not just a day.

        The offset is kept rather than sliced off: an hour is only worth
        showing if it is the reader's hour, and a `Z` read as local time is off
        by one in Britain for half the year.
        """
        text = str(value or "").strip()
        if not text:
            return None
        try:
            return (datetime.fromisoformat(text.replace("Z", "+00:00")),
                    len(text) > 10 and text[10] in "T ")
        except ValueError:
            return None

    @property
    def moment(self) -> tuple[datetime, bool] | None:
        """When the age counts from: the moment a scan met the posting.

        Discovery, not publication, and deliberately. Boards give a bare day
        for `posted_at` — `2026-09-08` and no clock — so counting from it made
        an advert found three hours ago read as `1d` because the board called
        it yesterday's, which is the wrong answer to the only question the
        column asks: is this worth opening now. The radar's own list counts
        from discovery for the same reason, and this now agrees with it.

        `posted_at` is the fallback for the rare row with no discovery stamp.
        """
        for value in (self.first_seen, self.posted_at):
            if (stamp := self._stamp(value)) is not None:
                return stamp
        return None

    @property
    def age_days(self) -> int | None:
        """Whole days since the radar met it."""
        moment = self.moment
        if moment is None:
            return None
        return (date.today() - moment[0].date()).days

    @property
    def age_hours(self) -> float | None:
        """Hours since the radar met it, or None where the only stamp on the
        row is a bare date — an hour counted from midnight is invented."""
        moment = self.moment
        if moment is None or not moment[1]:
            return None
        when = moment[0]
        # `tzinfo` of a naive stamp is None, which asks for a naive now.
        return max(0.0, (datetime.now(when.tzinfo) - when).total_seconds() / 3600)

    @property
    def age_label(self) -> str:
        """Age in five characters: hours through the first day, then days.

        A column of whole days said `0d` for every row met since midnight,
        which is most of a morning's list and exactly the rows worth telling
        apart — a vacancy found two hours ago is worth answering before one
        from breakfast.
        """
        if self.age_days is None:
            return "-"
        hours = self.age_hours
        if hours is None or hours >= 24:
            return f"{self.age_days}d"
        return "<1h" if hours < 1 else f"{int(hours)}h"

    @property
    def age_phrase(self) -> str:
        """The same age with room to spell it out."""
        if self.age_days is None:
            return ""
        hours = self.age_hours
        if hours is not None and hours < 24:
            if hours < 1:
                return "less than an hour ago"
            whole = int(hours)
            return f"{whole} hour{'s' if whole != 1 else ''} ago"
        days = self.age_days
        return "today" if days == 0 else f"{days} day{'s' if days != 1 else ''} ago"

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


def triage(job_ids: list[str] | None = None, base: str | None = None,
           token: str | None = None) -> dict:
    """Queue on-server LLM triage. A list of ids scores those; None scores
    everything pending. The radar takes no count, so a batch of twenty is
    twenty ids."""
    b, t = _credentials(base, token)
    target = job_ids if job_ids else "all_pending"
    return _call("/api/analyze", b, t, {"mode": "triage", "target": target})


def triage_status(base: str | None = None, token: str | None = None) -> dict:
    return _call("/api/analyze", *_credentials(base, token))


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


def priority_locations(base: str | None = None,
                       token: str | None = None) -> tuple[str, ...]:
    """The cities from the radar's own config.

    Read from there rather than copied here: they are the radar's setting, and
    a second copy would drift from it the first time one is edited.

    Parsed with a YAML parser rather than by hand — the deployed config writes
    the list inline (`["Edinburgh", "Glasgow"]`) while the checked-in one uses
    block form, and a hand-rolled reader saw only the second and silently
    returned nothing.
    """
    try:
        b, t = _credentials(base, token)
        request = urllib.request.Request(f"{b}/api/config", headers={
            "Authorization": f"Bearer {t}",
            "User-Agent": "job-application-hub/0.1"})
        with urllib.request.urlopen(request, timeout=15) as response:
            config = yaml.safe_load(response.read().decode()) or {}
    except (RadarError, urllib.error.URLError, OSError, yaml.YAMLError):
        return ()
    places = config.get("priority_locations") or []
    return tuple(str(p).strip().lower() for p in places if str(p).strip())


#: `limit`, `sort` and `q` are the whole of the radar's list API: no paging,
#: no offset, no cursor, and no filter for the rows that have no score yet.
#: Asking for more rows than it holds returns all of them, so this is the whole
#: table — 937 rows, 595 KB and a third of a second today, which is the same as
#: asking for 300 because the cost is the round trip and not the rows.
WHOLE_TABLE = 5000


def fetch_all(query: str | None = None, base: str | None = None,
              token: str | None = None) -> list[Job]:
    """Every row the radar holds, ordered and filtered here afterwards.

    Fetching a page and ordering it is what loses rows, and it lost the ones
    that matter most: the radar's `sort=score` answers with scored rows only,
    so a vacancy found an hour ago and not yet scored was in no page any
    fit-ordered screen ever asked for. Widening the limit does not fix that,
    and neither does a second request — the hub has to hold the set it is
    choosing from.

    Asked for by discovery so that if the table ever does outgrow one response,
    what falls off the end is the oldest rows rather than this morning's. That
    the end was reached at all is `truncated`, which the screen says out loud
    rather than quietly showing less.
    """
    return fetch(limit=WHOLE_TABLE, query=query, sort="seen",
                 base=base, token=token)


def truncated(jobs: list[Job]) -> bool:
    """Whether the radar had more rows than one response can carry.

    It cannot happen at 937 rows. It is here because the day it does, the
    screen has to say so: a list quietly missing its tail is the failure this
    whole approach exists to prevent.
    """
    return len(jobs) >= WHOLE_TABLE


def order_by(jobs: list[Job], sort: str = "score",
             priority: tuple[str, ...] = ()) -> list[Job]:
    """Put a set already in hand into the order the screen asks for.

    The server decides *which* rows arrive — ordering a page here cannot pull
    in a row the page never contained — but it does not decide what happens to
    them afterwards. Re-sorting by score regardless of the chosen sort is what
    made `posted` and `found` do nothing at all.

    A row with no date sorts last rather than as the oldest: absent is not the
    same as old, and putting them at either end of the dates would be a claim
    the row does not make.
    """
    if sort == "priority":
        return sorted(jobs, key=lambda j: (j.tier(priority), -(j.score or -1)))
    if sort in ("posted", "seen"):
        field = "posted_at" if sort == "posted" else "first_seen"
        known = [j for j in jobs if getattr(j, field)]
        unknown = [j for j in jobs if not getattr(j, field)]
        return sorted(known, key=lambda j: str(getattr(j, field)),
                      reverse=True) + unknown
    return sorted(jobs, key=lambda j: (j.score is None, -(j.score or 0)))


#: The statuses the inbox leaves out, because each has already been decided:
#: the posting is gone, it is in the hub, or it was dismissed in the radar.
#: Everything else is open, `viewed` included — a vacancy read in the radar's
#: own dashboard is still a vacancy to answer.
#:
#: An exclusion rather than a list of what to show. Naming what to show is what
#: hid `viewed` for as long as `viewed` has existed, and it would hide the next
#: status the radar invents just as quietly; naming what to hide means a status
#: nobody here has heard of arrives on screen, which is the safe way round.
DONE = ("expired", "saved", "applied", "rejected", "archived")


def shortlist(jobs: list[Job], min_score: float = 0.0,
              hidden: tuple[str, ...] = DONE,
              max_age: int | None = None, sort: str = "score",
              priority: tuple[str, ...] = ()) -> list[Job]:
    """The rows still worth a decision, in the asked-for order.

    Highest score first by default, with unscored rows last rather than first.
    `hidden=()` keeps everything, history included.
    """
    out = [j for j in jobs
           if j.status not in hidden
           and (j.score or 0) >= min_score
           and (max_age is None or (j.age_days or 0) <= max_age)]
    return order_by(out, sort, priority)
