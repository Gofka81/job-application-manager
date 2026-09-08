"""Command line entry point.

Deterministic only (D21). Anything needing a model belongs in a Claude Code
skill, not here.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import os
import re
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import yaml

from hub import (agent, answerbank, atscheck, backfill, bootstrap, check as check_mod, config,
                 coverage, inbox as inbox_mod, latex, picker, render,
                 openurl, submit as submit_mod, take as take_mod)


def cmd_render(args: argparse.Namespace) -> int:
    cfg = config.load()
    tailoring = Path(args.tailoring) if args.tailoring else None
    out = Path(args.out) if args.out else None

    jd = Path(args.jd) if args.jd else None

    if args.app:
        folder = cfg.applications / args.app
        if not folder.is_dir():
            print(f"no such application: {folder}", file=sys.stderr)
            return 1
        tailoring = tailoring or folder / "tailoring.yaml"
        jd = jd or folder / "jd.md"
        out = out or folder / "cv.tex"

    out = out or config.ROOT / "output" / "cv.tex"
    return render.build(out, tailoring=tailoring, jd=jd,
                        compile_pdf=not args.no_pdf)


def cmd_check(args: argparse.Namespace) -> int:
    """Check finished CVs against the master, whatever produced them."""
    cfg = config.load()
    master = yaml.safe_load(cfg.master_profile.read_text())
    source = render.source_text(master)
    ident = master.get("identity", {})
    contact = [ident.get("email")] if args.contact else []
    allow = set(cfg.factgate_allow)

    targets = []
    for raw in args.paths:
        p = Path(raw)
        targets.extend(sorted(p.rglob("*.pdf")) if p.is_dir() else [p])
    if not targets:
        print("nothing to check", file=sys.stderr)
        return 1

    failed = 0
    for pdf in targets:
        try:
            report = check_mod.check(pdf, source, contact, allow, args.max_pages)
        except check_mod.atscheck.ExtractorMissing as exc:
            print(exc, file=sys.stderr)
            return 1
        print(report.report())
        failed += not report.ok
    if len(targets) > 1:
        print(f"\n{len(targets) - failed}/{len(targets)} pass")
    return 3 if failed else 0


def cmd_backfill(args: argparse.Namespace) -> int:
    """Recover coverage records from tailor-cv's prose logs."""
    cfg = config.load()
    folders = sorted(p for p in cfg.applications.iterdir() if p.is_dir())
    written = skipped = 0
    for folder in folders:
        doc = backfill.convert(folder)
        if doc is None:
            skipped += 1
            continue
        out = folder / "coverage.yaml"
        if out.exists() and not args.force:
            skipped += 1
            continue
        if args.apply:
            out.write_text(
                "# Recovered from changes.md. `evidence` is absent because the\n"
                "# prose names bullets in words, not master ids (see hub/backfill.py).\n"
                + yaml.safe_dump(doc, sort_keys=False, allow_unicode=True,
                                 width=88))
        written += 1
        n = len(doc["requirements"])
        miss = sum(r["status"] == "missing" for r in doc["requirements"])
        print(f"{folder.name}: {n} requirements, {miss} missing")
    verb = "wrote" if args.apply else "would write"
    print(f"\n{verb} {written}, skipped {skipped}")
    if not args.apply:
        print("re-run with --apply to write the files")
    return 0


def _load_env() -> None:
    """Read .env without a dependency. Real environment wins."""
    path = config.ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


#: The screen's sorts, and what each asks the radar for. Here rather than in
#: `_pick` because the first fetch happens before the bar is built and has to
#: agree with it.
_SORTS = [("priority", "priority"), ("fit", "score"),
          ("posted", "posted"), ("found", "seen")]


def _remembered_sort() -> str:
    """What the bar will open on. The default screen is `priority`."""
    try:
        saved = json.loads(_filter_state_path().read_text())
    except (OSError, ValueError):
        return "priority"
    return dict(_SORTS).get(saved.get("sort"), "priority")


def cmd_inbox(args: argparse.Namespace) -> int:
    """What job-radar has found, best fit first."""
    _load_env()
    interactive = not args.plain and picker.usable()
    # The whole table, once. Ordering and filtering happen here, so no screen
    # can be missing a row the radar holds. A pipe or an agent gets the plain
    # default order rather than whoever last used the screen.
    sort = _remembered_sort() if interactive else "score"
    try:
        jobs = inbox_mod.fetch_all(args.q)
    except inbox_mod.RadarError as exc:
        print(exc, file=sys.stderr)
        return 1
    if inbox_mod.truncated(jobs):
        print(f"the radar holds more than {inbox_mod.WHOLE_TABLE} rows; this is "
              f"the newest {len(jobs)} of them", file=sys.stderr)

    hidden = () if args.all else inbox_mod.DONE
    priority = inbox_mod.priority_locations() if sort == "priority" else ()
    shortlist = inbox_mod.shortlist(jobs, args.min_score, hidden,
                                    args.max_age, sort=sort, priority=priority)
    if not shortlist:
        print(f"nothing matches ({len(jobs)} rows fetched)")
        return 0

    # A person picks with the arrow keys; an agent, a pipe or CI gets the table.
    if interactive:
        taken: set[str] = set()
        queued: list[str] = []

        def remember(job_id: str, app_id: str) -> None:
            taken.add(job_id)
            queued.append(app_id)

        while True:
            rows = [j for j in shortlist if j.job_id not in taken]
            chosen = _pick(rows, hidden, args.min_score, args.max_age)
            if chosen is None:
                break
            _vacancy_screen(chosen.job_id, on_taken=remember)

        # Tailoring runs once the screens are closed rather than inside them:
        # it takes a minute and has plenty to say, and neither fits behind a
        # list you are still browsing.
        if args.no_tailor:
            for app_id in queued:
                print(f"taken: {app_id} — next: /tailor {app_id}")
            return 0
        code = 0
        for app_id in queued:
            code = _tailor(app_id) or code
        return code

    print(f"{len(shortlist)} of {len(jobs)} jobs\n")
    # The id, not a row number: position is not identity, and the next scan
    # reorders the list. This one can be pasted straight into `jam take`.
    print(f"{'id':<9} {'fit':>4}  {'age':>5}  {'company':<24} {'title':<42} "
          f"{'where':<18} {'pay':<10} src")
    print("-" * 123)
    for job in shortlist[:args.top]:
        fit = f"{job.score:.1f}" if job.score is not None else "  -"
        age = job.age_label
        flag = "" if job.jd_full else " *"
        print(f"{job.job_id[:8]:<9} {fit:>4}  {age:>5}  {job.company[:24]:<24} "
              f"{(job.title[:40] + flag):<42} {job.location[:18]:<18} "
              f"{job.salary:<10} {job.source}")
    print(f"\n  jam take {shortlist[0].job_id[:8]}"
          f"        or  jam take \"{shortlist[0].company.lower()}\"")

    if any(not j.jd_full for j in shortlist[:args.top]):
        print("\n* the radar holds only a snippet; the full JD is read from the "
              "posting when the application is created")
    if args.why:
        print()
        for job in shortlist[:args.top]:
            if job.reason:
                print(f"{job.job_id[:8]}  {job.reason[:104]}")
    return 0


def _filter_state_path() -> Path:
    return config.load().data / ".inbox-filters.json"


def _restore_filters(filters: list) -> None:
    """Put the bar back where it was left.

    Choosing 7d and 8+ every time you open the list is the kind of friction
    that ends with the filters going unused.
    """
    try:
        saved = json.loads(_filter_state_path().read_text())
    except (OSError, ValueError):
        return
    for f in filters:
        label = saved.get(f.name)
        for i, (option, _) in enumerate(f.options):
            if option == label:
                f.index = i
                break


def _remember_filters(filters: list) -> None:
    state = {f.name: f.label for f in filters}
    try:
        _filter_state_path().write_text(json.dumps(state, indent=2) + "\n")
    except OSError:
        pass                                  # never fail a screen over this


def _fit(job) -> str:
    return f"{job.score:.1f}" if job.score is not None else "-"


#: The radar's own bands, from its `tgfmt.dot` — "matches the dashboard's badge
#: bands" — so a 6.5 is amber in the Telegram card, amber on the dashboard and
#: amber here. Two tools disagreeing about what a good match is would make the
#: colour worth less than no colour at all.
FIT_BANDS = (7.0, 5.0)
#: The radar's `RECENT_HOURS = 48`, its dashboard's "Recent 48h" default and the
#: window its 🆕 New view uses; then `archive_after_days: 30` from its config,
#: after which a row leaves the live table altogether.
AGE_BANDS = (2, 30)


def _fit_role(job) -> str:
    """Traffic lights on the score, in the radar's bands. An unscored row is
    dim: not judged, rather than judged low."""
    return _score_role(job.score)


def _age_role(job) -> str:
    """The same three lights on the age, in the radar's windows: what it calls
    new, what is still live, and what it is about to archive."""
    days = job.age_days
    if days is None:
        return "none"
    good, fair = AGE_BANDS
    if days <= good:
        return "good"
    return "fair" if days <= fair else "poor"


def _score_role(score) -> str:
    """The radar's bands, wherever one of its scores is shown — the inbox and
    the application it became are the same number and the same verdict."""
    if score is None:
        return "none"
    good, fair = FIT_BANDS
    if score >= good:
        return "good"
    return "fair" if score >= fair else "poor"


def _stage_role(record: dict) -> str:
    """What the stage is asking for.

    Green is ready to send. Amber is unfinished — a step nobody has run yet.
    Red is a check that ran and failed, which is a different thing from work
    outstanding: the CV exists, it is just too long to send. Submitted is dim,
    like every other row on these screens that is not asking for a decision.
    """
    stage, _ = _stage(record)
    if stage == "submitted":
        return "none"
    if stage == "ready":
        return "good"
    return "poor" if stage.endswith("pages") else "fair"


def _field(label: str, value, role: str = "cell") -> list | None:
    """One labelled line: the label is a name, the value is what it is worth.

    Shared by the two detail screens so a field cannot be laid out one way on
    the vacancy and another on the application it became.
    """
    return [(f"  {label:<10}", "name"), (str(value), role)] if value else None


def _section(title: str, width: int = 58) -> list[tuple[str, str]]:
    """A rule with the name of what follows set into it, as under the list."""
    lead = "──"
    label = f" {title} "
    return [("  " + lead, "rule"), (label, "name"),
            ("─" * max(0, width - len(lead) - len(label)), "rule")]


def _where_parts(job) -> list[tuple[str, str]]:
    """`remote · London` is two facts in one cell, and only one of them is a
    place: the radar keeps remote as a column of its own. Colouring the word
    apart from the location is how a screen says that without a second column.
    """
    if not job.remote:
        return [(job.location, "cell")]
    return ([("remote", "remote")] if not job.location
            else [("remote", "remote"), (f" · {job.location}", "cell")])


def _pick(jobs: list, hidden=inbox_mod.DONE, min_score=0.0, max_age=None):
    # Age is time since the radar met the posting, which is the figure the
    # radar's own list shows; the board's publication day is a coarser and
    # often later-looking version of the same thing.
    columns = [
        picker.Column("fit", 4, _fit, right=True, role=_fit_role),
        # Five, not four: `1000d` for something a board never took down used to
        # be cut to `1000`, which reads as a number rather than a truncation.
        picker.Column("age", 5, lambda j: j.age_label, right=True,
                      role=_age_role),
        picker.Column("company", 22, lambda j: j.company),
        picker.Column("title", 38, lambda j: j.title, flex=True),
        picker.Column("where", 22, lambda j: j.where, parts=_where_parts),
        picker.Column("pay", 11, lambda j: j.salary),
        picker.Column("src", 10, lambda j: j.source),
    ]

    # "priority" is the radar's own default: it tiers by location first — a
    # priority city, then UK-remote, then the rest — and only sorts by score
    # inside a tier.
    priority = inbox_mod.priority_locations()

    def shortlist(jobs):
        return inbox_mod.shortlist(jobs, min_score, hidden, max_age,
                                   sort=sort_filter.value, priority=priority)

    def deep(query: str):
        """The radar searches the JD text server-side; the list payload never
        carries it, so `spark` cannot be found by filtering what is on screen."""
        return shortlist(inbox_mod.fetch_all(query))

    def reload(p) -> str:
        try:
            found = inbox_mod.fetch_all()
        except inbox_mod.RadarError as exc:
            return str(exc)
        p.base = shortlist(found)
        p.all = list(p.base)
        p.deep_query = ""
        return ""

    def reorder(p) -> str:
        """No round trip: the screen already holds every row the radar has, so
        changing the sort is a re-sort and not a different question. It used to
        refetch, which is how a change of sort could change which vacancies
        existed — and did, since the fit page carries no unscored rows."""
        p.all = inbox_mod.order_by(p.all, sort_filter.value, priority)
        if sort_filter.value == "priority":
            return f"{', '.join(priority).title()} first, then remote" \
                if priority else "by location tier, then fit"
        return ""

    sort_filter = picker.Filter(
        "sort", _SORTS,
        reload=reorder,
        hints={
            "priority": "your cities first, then remote, best fit inside each",
            "fit": "best triage score first, wherever it is",
            "posted": "most recently published by the employer",
            "found": "most recently met by the radar, which can differ",
        })

    filters = [
        picker.Filter("age", [("48h", 2), ("7d", 7), ("all", None)],
                      keep=lambda j, v: v is None or (j.age_days or 0) <= v,
                      hints={"48h": "published in the last two days",
                             "7d": "published in the last week",
                             "all": "everything still open  ·  age is time "
                                    "since the radar found it"}),
        sort_filter,
        # A row with no score has not been judged below the bar, it has not
        # been judged. Dropping those hid exactly the freshest rows — the
        # radar scores overnight, so this morning's arrivals have no number
        # yet — so the bar applies to them only while fit is what orders the
        # list, which is the one case where an unscored row has no place to sit.
        picker.Filter("min fit", [("any", None), ("7+", 7.0), ("8+", 8.0),
                                  ("9", 9.0)],
                      keep=lambda j, v: (v is None or (j.score or 0) >= v
                                         or (j.score is None
                                             and sort_filter.value != "score")),
                      hints={"any": "every row, scored or not",
                             "7+": "a reasonable match and above",
                             "8+": "a strong match",
                             "9": "the radar's best only  ·  not-yet-scored "
                                  "rows stay unless the sort is fit"}),
    ]
    _restore_filters(filters)
    # The caller fetched before the remembered sort was known, so the rows in
    # hand are in score order whatever the bar says. Reordering them here is
    # what makes the screen open in the order it claims; a change of sort from
    # the bar refetches, which is what picks up rows this page never held.
    jobs = inbox_mod.order_by(jobs, sort_filter.value, priority)

    def score_unrated(p) -> str:
        pending = [j.job_id for j in p.rows if j.score is None][:20]
        if not pending:
            return "everything here already has a score"
        try:
            inbox_mod.triage(pending)
        except inbox_mod.RadarError as exc:
            return str(exc)
        return (f"sent {len(pending)} to be scored now, rather than waiting "
                f"for the radar's overnight run")

    screen = picker.Picker(
        jobs, columns, title="job-radar inbox",
        search=lambda j: f"{j.company} {j.title} {j.location} {j.source}",
        deep=deep, deep_label="in JD",
        filters=filters,
        keys={20: ("^t score", score_unrated),
              18: ("^r reload", lambda p: reload(p) or "reloaded")},
        # The reason sits beside the score rather than behind a flag: a bare
        # number looks more objective than it is and cannot be argued with.
        detail=lambda j: j.reason,
        # Named the same as the section on the vacancy screen: it is the same
        # sentence from the same place, and one thing should not have two names.
        detail_label="why the radar rated it",
    )
    chosen = screen.run()
    _remember_filters(screen.filters)
    return chosen


def _vacancy_screen(job_id: str, on_taken=None) -> None:
    """The whole posting, laid out to be read rather than parsed."""
    try:
        job = inbox_mod.detail(job_id)
    except inbox_mod.RadarError as exc:
        picker.view([str(exc)], title="could not load the vacancy")
        return

    cfg = config.load()
    company, title = job.get("company") or "", job.get("title") or ""
    url = job.get("url") or ""

    # The same pieces the list is drawn from: a label is a name, a value that
    # means better or worse carries its light, and the radar's prose is the
    # radar's prose. A screen where the label and its value are the same colour
    # is a screen you read twice — once to find the fields, once to read them.
    row = inbox_mod.Job.from_row(job)
    salary = ""
    lo, hi, cur = job.get("salary_min"), job.get("salary_max"), job.get("currency") or ""
    if lo or hi:
        salary = (f"{cur}{int((lo or 0)/1000)}k–{cur}{int(hi/1000)}k" if lo and hi
                  else f"{cur}{int((lo or hi)/1000)}k")

    posted, seen = job.get("posted_at"), job.get("first_seen")
    when = seen or posted
    # The same reading of the stamp as the list column, so a row cannot be
    # "2 hours ago" on one screen and something else on the next.
    age = row.age_phrase
    if when and not age:
        age = str(when)[:10]               # a stamp we could not read at all

    seen = take_mod.already_applied(cfg.applications, company, title)

    fit = (f"{job.get('score')}/10" if job.get("score") is not None
           else "not scored yet — press s")
    lines = [line for line in [
        _field("fit", fit, _fit_role(row)),
        _field("found", age, _age_role(row)),
        # The board's day, where it gave one, sits under the age rather than
        # replacing it: it is the coarser figure and it is often the later one.
        _field("posted", str(posted)[:10] if posted else "", "option"),
        ([(f"  {'where':<10}", "name")] + _where_parts(row)
         if row.where else None),
        _field("pay", salary),
        _field("source", job.get("source"), "option"),
        _field("link", url, "option"),
    ] if line]

    if job.get("eval_reason"):
        lines += ["", _section("why the radar rated it"), ""]
        lines += [[("    " + chunk, "hint")]
                  for chunk in _chunks(job["eval_reason"], 88)]
    if seen:
        # Loud, and in the colour the screen uses for a bad number: applying
        # twice to one company is the mistake this screen exists to prevent.
        lines += ["", [("  ALREADY APPLIED: ", "poor"),
                       (", ".join(seen), "poor")]]

    body = (job.get("description") or "").strip()
    lines += ["", _section("the posting"), ""]
    if body:
        for paragraph in re.split(r"\n\s*\n", body):
            lines += _chunks(" ".join(paragraph.split()), 92) + [""]
    else:
        lines += ["The radar holds no text for this posting.",
                  "Applying writes a jd.md to paste it into."]

    def apply_now() -> str:
        folder, _ = take_mod.create(cfg.applications, job)
        try:
            inbox_mod.set_status(job_id, "saved")
        except inbox_mod.RadarError as exc:
            return f"created {folder.name}, but the radar was not told: {exc}"
        if on_taken:
            on_taken(job_id, folder.name)
        return f"created {folder.name}"

    def score_now() -> str:
        try:
            inbox_mod.triage([job_id])
        except inbox_mod.RadarError as exc:
            return str(exc)
        return "queued for scoring"

    actions = [picker.Act("a", "apply", apply_now,
                          confirm="create the application?"),
               picker.Act("o", "open", lambda: openurl.open_url(url))]
    if job.get("score") is None:
        actions.append(picker.Act("s", "score it", score_now))
    # The subtitle carries what the row is rather than what it says: the state
    # the radar has it in, and the id to paste into `jam take`.
    state = job.get("status") or "new"
    picker.Detail(f"{company} · {title}", lines, actions,
                  subtitle=f"{state}  ·  {job_id[:8]}").run()


def _resolve(query: str, jobs: list):
    """A job id prefix, or a fragment of the company or title.

    Position in a list is not an identity: the next scan reorders it, and
    `take 3` would quietly take a different vacancy.
    """
    q = query.lower()
    exact = [j for j in jobs if j.job_id.startswith(query)]
    if len(exact) == 1:
        return exact[0], []
    hits = [j for j in jobs if q in f"{j.company} {j.title}".lower()]
    return (hits[0] if len(hits) == 1 else None), hits


def _take(job_id: str, assume_yes: bool) -> int:
    cfg = config.load()
    try:
        job = inbox_mod.detail(job_id)
    except inbox_mod.RadarError as exc:
        print(exc, file=sys.stderr)
        return 1

    company, title = job.get("company"), job.get("title")
    print(f"{company} · {title}")
    print(f"  fit {job.get('score') or '-'} · {job.get('source')} · {job.get('url')}")
    if job.get("eval_reason"):
        print(f"  {job['eval_reason']}")
    jd = job.get("description") or ""
    print(f"  JD: {len(jd)} chars" + ("" if jd else "  — not held by the radar"))

    seen = take_mod.already_applied(cfg.applications, company or "", title or "")
    if seen:
        print(f"\n  already applied: {', '.join(seen)}")

    if not assume_yes:
        try:
            if input("\ncreate the application? [y/N] ").strip().lower() != "y":
                print("nothing created")
                return 0
        except (EOFError, KeyboardInterrupt):
            print()
            return 0

    folder, record = take_mod.create(cfg.applications, job)
    print(f"\ncreated {folder}")
    print(f"  application.json  channel={record['channel']} "
          f"discovery={record['discovery']} radar_score={record['radar_score']}")
    print(f"  jd.md             {len(jd)} chars")
    try:
        inbox_mod.set_status(job_id, "saved")
        print("  marked saved in job-radar")
    except inbox_mod.RadarError as exc:
        # The folder is the thing that matters; the radar can be told again.
        print(f"  could not mark it saved: {exc}", file=sys.stderr)
    print("\nnext: /tailor")
    return 0


@dataclass
class Action:
    key: str
    label: str
    hint: str
    run: object


def _menu_actions(cfg) -> list[Action]:
    """Built fresh each time so the counts are current.

    Nothing here touches the network: the menu has to appear instantly, and
    the radar is only called once the inbox is actually chosen.
    """
    applications = (sorted(p.name for p in cfg.applications.glob("*/application.json"))
                    if cfg.applications.exists() else [])
    bank = cfg.data / "answer-bank.yaml"
    answered = total = 0
    if bank.exists():
        entries = yaml.safe_load(bank.read_text()) or []
        total = len(entries)
        answered = sum(1 for e in entries
                       if e.get("value") is not None or e.get("since"))

    return [
        Action("inbox", "inbox", "vacancies from job-radar",
               lambda: main(["inbox"])),
        Action("apps", "applications",
               f"{len(applications)} in data/applications",
               lambda: _list_applications(cfg)),
        Action("gaps", "gaps", "what the market wants that you lack",
               lambda: _gaps_screen(cfg)),
        Action("answers", "answer bank",
               f"{answered}/{total} filled" if total else "not created yet",
               lambda: _answers_screen(cfg)),
        Action("config", "config", "where everything points",
               lambda: picker.view(_config_lines(cfg), title="config")),
        Action("quit", "quit", "", lambda: None),
    ]


def _applications(cfg) -> list[dict]:
    out = []
    for path in sorted(cfg.applications.glob("*/application.json"), reverse=True):
        try:
            record = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        record["_folder"] = path.parent
        out.append(record)
    return out


def _stage(record: dict) -> tuple[str, str]:
    """Where an application stands, and what moves it on.

    Worked out from the folder rather than stored: a stage field would be a
    second truth to keep in step with the files that actually exist.

    Held on the record once worked out. Two columns and the colour of one of
    them ask for this, and answering meant opening the PDF to count its pages —
    three times per row per keystroke, on every arrow key. The records are
    re-read from disk after anything that changes a folder, which is when the
    answer can change; `rebuild` drops it by hand because it changes one
    without re-reading.

    A file existing is not the same as it being usable. One application read
    "ready" on a two-page CV that the page budget rejects, which is the kind
    of quiet wrongness that only shows up when someone tries to send it — so
    the PDF is checked, not just counted.

    `jam` cannot run the next step itself — the deterministic half is not
    allowed to call a model (D21) — so it names it and you run it.
    """
    if "_stage" not in record:
        record["_stage"] = _work_out_stage(record)
    return record["_stage"]


def _work_out_stage(record: dict) -> tuple[str, str]:
    folder = record["_folder"]
    app_id = record.get("app_id")
    if record.get("submitted_at"):
        return "submitted", ""
    pdf = folder / "cv.pdf"
    if not pdf.exists():
        return "no cv", f"/tailor {app_id}"
    pages = atscheck.page_count(pdf)
    budget = config.load().thresholds.cv_max_pages
    if pages and budget and pages > budget:
        return f"{pages} pages", f"/tailor {app_id}"
    for name, missing in (("coverage.yaml", "no coverage"),
                          ("changes.md", "no notes")):
        if not (folder / name).exists():
            return missing, f"/tailor {app_id}"
    return "ready", f"/apply {app_id}"


def _application_detail(record: dict) -> list:
    folder = record["_folder"]
    files = sorted(p.name for p in folder.iterdir() if p.is_file())
    stage, action = _stage(record)
    score = record.get("radar_score")

    # What to do about it first, because that is the question this screen is
    # opened with; what it is second.
    lines = [line for line in [
        _field("stage", stage, _stage_role(record)),
        _field("next", action, "hint"),
        "",
        _field("fit", score if score is not None else "not scored",
               _score_role(score)),
        _field("found via", record.get("discovery"), "option"),
        _field("channel", record.get("channel"), "option"),
        _field("submitted", record.get("submitted_at") or "not yet",
               "cell" if record.get("submitted_at") else "option"),
        _field("posting", record.get("source_url"), "option"),
        _field("files", ", ".join(files), "option"),
    ] if line]

    lines += _detail_checks(folder)
    jd = folder / "jd.md"
    if jd.exists():
        text = " ".join(jd.read_text().split())
        # The posting itself, in the one colour on the screen that means the
        # thing rather than something said about it.
        lines += ["", _section("the posting"), ""]
        lines += _chunks(text, 96)[:14]
    return lines


def _detail_checks(folder: Path) -> list[str]:
    """What the built CV actually scores, next to the stage that summarises it.

    The list can only say one thing per row, so a CV that is both too long and
    thin on coverage shows as "2 pages". The number that got it there belongs
    here, where there is room for it, rather than in a separate command.
    """
    lines = []
    pdf = folder / "cv.pdf"
    if pdf.exists():
        pages = atscheck.page_count(pdf)
        budget = config.load().thresholds.cv_max_pages
        over = pages is not None and pages > budget
        lines.append(_field("pages", f"{pages if pages else '?'}"
                            + (f" (over {budget})" if over else ""),
                            "poor" if over else "good"))
    path = folder / "coverage.yaml"
    if path.exists():
        try:
            s = coverage.summarize(coverage.load(path))
        except (KeyError, TypeError, yaml.YAMLError):
            lines.append(_field("coverage", "unreadable", "poor"))
        else:
            pct = f"{s.share:.0%}" if s.share is not None else "n/a"
            # Green when nothing required is uncovered, rather than at some
            # percentage nobody chose: `missing` is the word the tailoring
            # skill writes and the one `jam gaps` counts, so it is the line
            # that decides. A missing requirement is work outstanding, not a
            # failed check — the CV can still be sent with it.
            lines.append(_field(
                "coverage", f"required {s.required_covered:g}/{s.required} "
                            f"({pct}) · preferred {s.preferred_covered:g}/"
                            f"{s.preferred}",
                "good" if not s.missing_required else "fair"))
            for text in (s.missing_required or [])[:6]:
                lines.append([("    missing  ", "option"),
                              (text[:80], "fair")])
    return ["", _section("checks"), *lines] if lines else []


def _chunks(text: str, width: int) -> list[str]:
    out, line = [], ""
    for word in text.split():
        if len(line) + len(word) + 1 > width:
            out.append(line)
            line = word
        else:
            line = f"{line} {word}".strip()
    if line:
        out.append(line)
    return out


def _list_applications(cfg) -> int:
    records = _applications(cfg)
    if not records:
        picker.view(["Nothing here yet.", "",
                     "Take a vacancy from the inbox and it appears."],
                    title="applications")
        return 0
    # The stage is what this screen is for, so it comes before the columns a
    # narrow terminal drops. `next` is the screen telling you what to run, and
    # is coloured as the screen talking rather than as data.
    columns = [
        picker.Column("date", 10, lambda r: str(r.get("app_id", ""))[:10],
                      role=lambda r: "option"),
        picker.Column("fit", 4, lambda r: str(r.get("radar_score") or "-"),
                      right=True, role=lambda r: _score_role(r.get("radar_score"))),
        picker.Column("stage", 12, lambda r: _stage(r)[0], role=_stage_role),
        picker.Column("company", 22, lambda r: r.get("company") or ""),
        picker.Column("title", 32, lambda r: r.get("title") or "", flex=True),
    ]
    # `next` used to be a column, and at 30 characters it was the first thing
    # dropped on any terminal narrower than 140 — so the one cell that said
    # what to run was the one nobody saw. It lives under the list now, where
    # the whole command fits and the stage that prompted it can be explained.
    def delete(screen):
        """Deleting from the list is the common case: three of four rows in a
        list are usually ones you already know you do not want."""
        row = screen.rows[screen.cursor] if screen.rows else None
        if row is None:
            return "nothing selected"

        def go():
            message = _delete_application(row, cfg)
            screen.base = [r for r in screen.base if r is not row]
            screen.all = [r for r in screen.all if r is not row]
            return message
        return picker.Ask(_delete_question(row), go)

    while True:
        chosen = picker.Picker(
            records, columns, title="applications",
            search=lambda r: (f"{r.get('company')} {r.get('title')} "
                              f"{_stage(r)[0]}"),
            keys={24: ("^x delete", delete)},
            # Under the list, the reason the stage says what it says: the page
            # count that failed, the requirement nothing covers. The column has
            # room for a verdict and none for what is behind it.
            detail=_application_note, detail_label="where it stands",
        ).run()
        if chosen is None:
            return 0
        _application_screen(chosen, cfg)
        # Re-read: the screen can have deleted the row that opened it.
        records = _applications(cfg)
        if not records:
            return 0


def _application_note(record: dict) -> str:
    """One line saying why the stage is what it is.

    The stage column can hold one verdict — `2 pages`, `no coverage` — and a
    verdict without its number sends you to another command to find out what
    it meant.
    """
    stage, action = _stage(record)
    if record.get("submitted_at"):
        via = record.get("channel") or "an unrecorded channel"
        return f"submitted {str(record['submitted_at'])[:10]} through {via}"
    bits = [f"{stage} — run {action}" if action else stage]
    path = record["_folder"] / "coverage.yaml"
    if path.exists():
        try:
            s = coverage.summarize(coverage.load(path))
        except (KeyError, TypeError, yaml.YAMLError):
            bits.append("coverage.yaml cannot be read")
        else:
            pct = f" ({s.share:.0%})" if s.share is not None else ""
            covered = f"required {s.required_covered:g}/{s.required}{pct}"
            if s.missing_required:
                covered += f", missing {'; '.join(s.missing_required[:3])}"
            bits.append(covered)
    return "  ·  ".join(bits)


def _delete_application(record: dict, cfg) -> str:
    """Take one application out of the working set.

    Moved to `.trash`, not deleted: a folder is a tailored CV, a coverage
    record and the notes behind both, and one keystroke should not be able to
    end that. The status log is left alone, being append-only by design.
    """
    try:
        gone = take_mod.discard(record["_folder"], cfg.data / ".trash")
    except OSError as exc:
        return f"could not delete it: {exc}"
    return f"deleted {gone.name} (recoverable in .trash)"


def _delete_question(record: dict) -> str:
    """Deleting a submitted application throws away the record of something
    that actually happened, which is worth saying rather than asking the same
    question for both cases."""
    who = record.get("company") or record.get("app_id", "this")
    if record.get("submitted_at"):
        return f"Delete {who}? It was submitted, and this is the only copy."
    return f"Delete {who}?"


def _application_screen(record: dict, cfg) -> None:
    """One application in full, with the two things worth doing to it.

    Rebuilding lives here rather than only on the command line because the
    reason to rebuild is almost always something read on this screen: a page
    count over budget, a claim the gate rejected.
    """
    folder = record["_folder"]
    # Named like the vacancy screen: what it is at the top, the id and where it
    # stands underneath, so the two screens are read the same way.
    detail = picker.Detail(
        f"{record.get('company')} · {record.get('title')}",
        _application_detail(record),
        subtitle=f"{record.get('app_id', '')}  ·  {_stage(record)[0]}")

    def rebuild() -> str:
        ok, lines = _rebuild(folder, cfg)
        # The stage is worked out from the folder, and the folder just changed.
        record.pop("_stage", None)
        detail.lines = (_application_detail(record)
                        + ["", _section("rebuild"), ""]
                        + [[("    " + line, "cell" if ok else "poor")]
                           for line in lines])
        detail.subtitle = f"{record.get('app_id', '')}  ·  {_stage(record)[0]}"
        return "rebuilt, passes" if ok else "rebuilt, does not pass"

    actions = [picker.Act("b", "rebuild cv", rebuild)]
    url = record.get("source_url")
    if url:
        actions.append(picker.Act("o", "open posting",
                                  lambda: openurl.open_url(url)))
    if (folder / "cv.pdf").exists():
        actions.append(picker.Act("v", "view cv",
                                  lambda: openurl.open_path(folder / "cv.pdf")))
    actions.append(picker.Act(
        "d", "delete", lambda: _delete_application(record, cfg),
        confirm=_delete_question(record), closes=True))
    detail.actions = actions
    detail.run()


def _answers_screen(cfg) -> int:
    """Browse the bank and fill an answer without opening the YAML.

    Twenty-five of the thirty-seven are things only the person knows, and
    editing them in a file is the reason they stay empty.
    """
    path = cfg.data / "answer-bank.yaml"
    if not path.exists():
        picker.view(["No answer bank yet.", "",
                     "Run `jam answers --init` to create it from the standard",
                     "set of questions forms ask."], title="answer bank")
        return 0

    def state(entry):
        if entry.get("since"):
            return f"{answerbank.years_since(entry['since']):g} years"
        value = entry.get("value")
        return "—" if value is None else str(value)

    columns = [
        picker.Column("", 1, lambda e: " " if (e.get("value") is None
                                               and not e.get("since")) else "✓"),
        picker.Column("question", 44, lambda e: e.get("question") or e["slot"],
                      flex=True),
        picker.Column("answer", 22, state),
        picker.Column("reuse", 13, lambda e: e.get("reuse", "")),
    ]
    while True:
        bank = yaml.safe_load(path.read_text()) or []
        answered = sum(1 for e in bank
                       if e.get("value") is not None or e.get("since"))
        chosen = picker.Picker(
            bank, columns, title=f"answer bank   {answered}/{len(bank)} filled",
            search=lambda e: f"{e.get('question', '')} {e['slot']}",
            detail=lambda e: _answer_hint(e),
        ).run()
        if chosen is None:
            return 0
        _fill_answer(path, bank, chosen)


def _answer_hint(entry: dict) -> str:
    hints = {
        "always": "reused on every application",
        "per_archetype": "may differ by the kind of role",
        "never": "written fresh each time — never reused",
    }
    note = hints.get(entry.get("reuse", ""), "")
    if entry.get("since"):
        note += f"   stored as a date ({entry['since']}), so it stays true"
    return note


def _fill_answer(path, bank: list, entry: dict) -> None:
    print(f"\n{entry.get('question') or entry['slot']}")
    if entry.get("value") is not None:
        print(f"currently: {entry['value']}")
    if entry.get("type") == "number":
        print('a tenure answer like "6 years" is stored as a date, so it stays true')
    try:
        answer = input("> ").strip()
    except (EOFError, KeyboardInterrupt):
        return
    if not answer:
        return

    years = re.match(r"^\s*(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)\b",
                     answer, re.I)
    if years:
        entry["since"] = answerbank.since_from_years(float(years.group(1)))
        entry["stated"] = answer
        entry["stated_at"] = str(date.today())
        entry["granularity"] = 0.5
        entry.pop("value", None)
    else:
        entry["value"] = answer
    path.write_text(bootstrap.HEADER + yaml.safe_dump(
        bank, sort_keys=False, allow_unicode=True, width=88))


def _gaps_screen(cfg) -> int:
    """What the market asked for that the master does not hold.

    A bare word count answers "so what". Choosing a term shows the vacancies
    that wanted it, in their own words, which is what makes it actionable
    rather than trivia.
    """
    counts = coverage.terms(cfg.applications, min_count=1)
    if not counts:
        picker.view(["No coverage recorded yet.", "",
                     "Each application records what the vacancy asked for and",
                     "what the master could answer. Aggregated, that says what",
                     "to learn next — and it needs no outcomes, so it works",
                     "from the first application."], title="gaps")
        return 0

    rows = [{"term": term, "n": n} for term, n in counts.most_common()]
    total = len({f.parent for f in cfg.applications.glob("*/coverage.yaml")})
    columns = [picker.Column("asked by", 8, lambda r: f"{r['n']} of {total}",
                             right=True),
               picker.Column("missing", 40, lambda r: r["term"], flex=True)]
    while True:
        chosen = picker.Picker(
            rows, columns,
            title=f"gaps across {total} applications",
            search=lambda r: r["term"],
            detail=lambda r: f"{r['n']} of {total} vacancies asked for this and "
                             f"the master could not answer",
        ).run()
        if chosen is None:
            return 0
        picker.view(_gap_detail(cfg, chosen["term"]), title=chosen["term"])


def _gap_detail(cfg, term: str) -> list[str]:
    lines = []
    for f in sorted(cfg.applications.glob("*/coverage.yaml")):
        doc = coverage.load(f)
        wanted = [r["text"] for r in doc.get("requirements") or []
                  if r.get("status") == "missing" and term in str(r["text"]).lower()]
        if wanted:
            lines.append(f.parent.name)
            lines += [f"    {w}" for w in wanted]
            lines.append("")
    return lines or [f"nothing recorded for {term}"]


def cmd_menu(args: argparse.Namespace) -> int:
    """One entry point, so nothing has to be remembered or typed."""
    _load_env()
    cfg = config.load()
    if not picker.usable():
        main(["--help"])
        return 0
    while True:
        actions = _menu_actions(cfg)
        chosen = picker.Picker(
            actions,
            [picker.Column("", 14, lambda a: a.label),
             picker.Column("", 46, lambda a: a.hint)],
            title="job application hub",
            search=lambda a: f"{a.label} {a.hint}",
            filterable=False,
        ).run()
        if chosen is None or chosen.key == "quit":
            return 0
        try:
            chosen.run()
        except KeyboardInterrupt:
            return 0


def _rebuild(folder: Path, cfg) -> tuple[bool, list[str]]:
    """Compile the folder's cv.tex and check what came out.

    Returns whether it is usable and the lines to show. Editing cv.tex by
    hand is the normal way to fix a CV that ran long, and until now the only
    way to see the result was to remember latexmk and re-run `jam check`
    separately. Doing both here means a rebuild cannot quietly leave a PDF
    that no longer passes.
    """
    try:
        built = latex.compile_tex(folder, cfg.data / "master")
    except latex.BuildError as exc:
        return False, [str(exc)]
    if not built.ok:
        return False, ["latex failed, the old cv.pdf is left untouched", "",
                       *latex.errors(built.log)]

    master = yaml.safe_load(cfg.master_profile.read_text())
    try:
        report = check_mod.check(built.pdf, render.source_text(master), [],
                                 set(cfg.factgate_allow),
                                 cfg.thresholds.cv_max_pages)
    except check_mod.atscheck.ExtractorMissing as exc:
        return True, ["built cv.pdf", f"check skipped: {exc}"]
    return report.ok, ["built cv.pdf", "", *report.report().splitlines()]


def cmd_build(args: argparse.Namespace) -> int:
    """Rebuild one application's CV from its own cv.tex."""
    cfg = config.load()
    folder = cfg.applications / args.app
    if not folder.is_dir():
        print(f"no such application: {args.app}", file=sys.stderr)
        return 1
    ok, lines = _rebuild(folder, cfg)
    print("\n".join(lines))
    if args.clean:
        print(f"cleaned {latex.clean(folder)} working file(s)")
    return 0 if ok else 3


def _tailor(app_id: str, model: str | None = None) -> int:
    """Hand the tailoring to the agent and show what it did."""
    cfg = config.load()
    if not (cfg.applications / app_id).is_dir():
        print(f"no such application: {app_id}", file=sys.stderr)
        return 1
    print(f"tailoring {app_id} — this takes a minute\n")
    try:
        result = agent.tailor(app_id, config.ROOT, model or cfg.agent_model)
    except agent.AgentMissing as exc:
        print(exc, file=sys.stderr)
        print(f"\nrun it yourself with:  /tailor {app_id}", file=sys.stderr)
        return 1
    except subprocess.TimeoutExpired:
        print("the agent ran out of time; the folder is left as it was",
              file=sys.stderr)
        return 1

    print(result.text or "(the agent said nothing)")
    if result.cost:
        print(f"\n${result.cost:.2f}")
    if not result.ok:
        return 1
    folder = cfg.applications / app_id
    made = [name for name in ("cv.pdf", "coverage.yaml", "changes.md")
            if (folder / name).exists()]
    missing = [name for name in ("cv.pdf", "coverage.yaml", "changes.md")
               if name not in made]
    print(f"\nwrote: {', '.join(made) or 'nothing'}")
    if missing:
        print(f"still missing: {', '.join(missing)}")
        return 1
    print(f"next: /apply {app_id}")
    return 0


def cmd_tailor(args: argparse.Namespace) -> int:
    return _tailor(args.app, args.model)


def cmd_submit(args: argparse.Namespace) -> int:
    """Record a submission that has already happened."""
    _load_env()
    cfg = config.load()
    folder = cfg.applications / args.app
    try:
        application = submit_mod.record(folder, cfg.logs, args.note or "")
    except submit_mod.NotAnApplication as exc:
        print(exc, file=sys.stderr)
        return 1

    print(f"{application['app_id']} submitted at {application['submitted_at']}")
    job_id = application.get("radar_job_id")
    if job_id:
        try:
            inbox_mod.set_status(job_id, "applied")
            print("  radar marked applied")
        except inbox_mod.RadarError as exc:
            print(f"  radar not updated: {exc}", file=sys.stderr)
    print(f"  watchdog {submit_mod.ping_watchdog()}")
    return 0


def cmd_triage(args: argparse.Namespace) -> int:
    """Ask the radar to score vacancies it has not scored yet."""
    _load_env()
    try:
        jobs = inbox_mod.fetch_all()
        pending = [j for j in jobs if j.score is None and j.status == "new"]
        if not pending:
            print("nothing left to score")
            return 0
        batch = [j.job_id for j in pending[: args.count]]
        inbox_mod.triage(batch)
    except inbox_mod.RadarError as exc:
        print(exc, file=sys.stderr)
        return 1
    print(f"queued {len(batch)} of {len(pending)} unscored vacancies")
    print("the radar scores them in the background; run the inbox again later")
    return 0


def _triage_screen(cfg) -> int:
    _load_env()
    try:
        jobs = inbox_mod.fetch_all()
    except inbox_mod.RadarError as exc:
        picker.view([str(exc)], title="triage")
        return 0
    pending = [j for j in jobs if j.score is None and j.status == "new"]
    if not pending:
        picker.view(["Everything new has a score."], title="triage")
        return 0

    def run() -> str:
        batch = [j.job_id for j in pending[:20]]
        try:
            inbox_mod.triage(batch)
        except inbox_mod.RadarError as exc:
            return str(exc)
        return f"queued {len(batch)} — scores appear as the radar works through them"

    lines = [f"{len(pending)} new vacancies have no fit score yet.", ""]
    lines += [f"  {j.company} · {j.title}" for j in pending[:20]]
    picker.Detail("triage", lines,
                  [picker.Act("s", "score the first 20", run,
                              confirm="queue 20 for scoring?")],
                  subtitle="scoring costs model time on the Pi").run()
    return 0


def cmd_take(args: argparse.Namespace) -> int:
    _load_env()
    if len(args.query) >= 12 and all(c in "0123456789abcdef" for c in args.query):
        return _take(args.query, args.yes)
    try:
        # By name, over everything: a vacancy found this morning has no score
        # yet, and a score-ordered page does not contain it — `jam take
        # "la fosse"` answered "no such vacancy" for exactly the rows the
        # screen was shouting about.
        jobs = inbox_mod.fetch_all()
    except inbox_mod.RadarError as exc:
        print(exc, file=sys.stderr)
        return 1
    job, hits = _resolve(args.query, jobs)
    if job is None:
        if not hits:
            print(f"nothing matches {args.query!r}", file=sys.stderr)
        else:
            print(f"{args.query!r} matches {len(hits)}:", file=sys.stderr)
            for h in hits[:10]:
                print(f"  {h.job_id[:8]}  {h.company} · {h.title}", file=sys.stderr)
        return 1
    return _take(job.job_id, args.yes)


def cmd_ask(args: argparse.Namespace) -> int:
    """Answer form questions from the bank, as JSON for an agent to read.

    One call per page rather than one per field: the agent fills what is
    known and asks the human about the rest in a single batch, because
    interrupting per field makes the system unbearable by the third
    application.
    """
    cfg = config.load()
    path = cfg.data / "answer-bank.yaml"
    bank = yaml.safe_load(path.read_text()) if path.exists() else []
    questions = args.questions or [l.strip() for l in sys.stdin if l.strip()]

    answered, unknown = {}, []
    for question in questions:
        match = answerbank.find(question, bank)
        entry = next((e for e in bank if e["slot"] == match.slot), None) \
            if match.certain else None
        value = answerbank.value_of(entry, args.type) if entry else None
        if value in (None, ""):
            unknown.append(question)
        else:
            answered[question] = {"slot": entry["slot"], "value": value,
                                  "reuse": entry.get("reuse", "always")}
    print(json.dumps({"answered": answered, "unknown": unknown}, indent=2,
                     ensure_ascii=False))
    return 0


def cmd_learn(args: argparse.Namespace) -> int:
    """Record an answer the human just gave, so it is not asked twice."""
    cfg = config.load()
    path = cfg.data / "answer-bank.yaml"
    bank = yaml.safe_load(path.read_text()) if path.exists() else []
    try:
        entry = answerbank.learn(bank, args.question, args.answer,
                                 slot=args.slot, reuse=args.reuse)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 1
    path.write_text(bootstrap.HEADER + yaml.safe_dump(
        bank, sort_keys=False, allow_unicode=True, width=88))
    print(f"{entry['slot']}: {entry.get('value') or entry.get('stated')}")
    return 0


def cmd_answers(args: argparse.Namespace) -> int:
    """Show the answer bank, or create it from the standard question set."""
    cfg = config.load()
    path = cfg.data / "answer-bank.yaml"

    if args.init:
        if path.exists() and not args.force:
            print(f"{path} exists; --force to overwrite", file=sys.stderr)
            return 1
        path.parent.mkdir(parents=True, exist_ok=True)
        entries = bootstrap.starter()
        filled = 0
        if cfg.master_profile.exists():
            master = yaml.safe_load(cfg.master_profile.read_text())
            filled = bootstrap.prefill(entries, master)
        path.write_text(bootstrap.HEADER + yaml.safe_dump(
            entries, sort_keys=False, allow_unicode=True, width=88))
        print(f"wrote {len(entries)} questions to {path}, "
              f"{filled} answered from the master profile")
        print("fill in the values you know; the rest are learned as they come up")
        return 0

    if not path.exists():
        print(f"no answer bank at {path} — run `jam answers --init`",
              file=sys.stderr)
        return 1

    bank = yaml.safe_load(path.read_text()) or []
    answered = [e for e in bank
                if e.get("value") is not None or e.get("since")]
    print(f"{len(answered)}/{len(bank)} answered")
    if args.missing:
        for e in bank:
            if e.get("value") is None and not e.get("since"):
                print(f"  [{e['reuse']:<13}] {e['question']}")
    return 0


def cmd_coverage(args: argparse.Namespace) -> int:
    cfg = config.load()
    folder = cfg.applications / args.app
    path = folder / "coverage.yaml"
    if not path.exists():
        print(f"no coverage file: {path}", file=sys.stderr)
        return 1
    master = yaml.safe_load(cfg.master_profile.read_text())
    doc = coverage.load(path)
    try:
        coverage.validate(master, doc)
    except coverage.CoverageError as exc:
        print(f"coverage: {exc}", file=sys.stderr)
        return 1
    print(coverage.summarize(doc).report())
    return 0


def cmd_gaps(args: argparse.Namespace) -> int:
    """What the market asked for that the master does not hold.

    Needs no outcomes: the unit of observation is a requirement, and there
    are hundreds of those across a search.
    """
    cfg = config.load()
    required, preferred, seen = coverage.aggregate(cfg.applications)
    if not seen:
        print("no applications have recorded coverage yet")
        return 0
    if args.terms:
        counts = coverage.terms(cfg.applications, args.min_count)
        print(f"terms recurring in gaps across {seen} application(s)\n")
        for term, n in counts.most_common():
            print(f"  {n:3}x  {term}")
        return 0
    print(f"across {seen} application(s) with recorded coverage\n")
    for label, counter in (("required", required), ("preferred", preferred)):
        rows = [(t, n) for t, n in counter.most_common() if n >= args.min_count]
        print(f"missing, {label}:" if rows
              else f"missing, {label}: nothing at or above {args.min_count}")
        for text, n in rows:
            print(f"  {n:3}x  {text}")
        print()
    return 0


def _config_lines(cfg) -> list[str]:
    bank = cfg.data / "answer-bank.yaml"
    return [
        f"data          {cfg.data}",
        f"applications  {cfg.applications}",
        f"templates     {cfg.templates}",
        "",
        f"master        {'present' if cfg.master_profile.exists() else 'MISSING'}",
        f"answer bank   {'present' if bank.exists() else 'not created'}",
        "",
        f"stale after   {cfg.thresholds.stale_days} days",
        f"ghosted after {cfg.thresholds.ghosted_days} days",
        f"follow-ups    at most {cfg.followup.max_touches_per_company} per company, "
        f"{cfg.followup.min_days_between} days apart",
        "",
        f"radar         {os.environ.get('JOB_RADAR_API_URL') or 'not configured'}",
    ]


def cmd_config(args: argparse.Namespace) -> int:
    cfg = config.load()
    print(f"data       {cfg.data}")
    print(f"templates  {cfg.templates}")
    print(f"stale      {cfg.thresholds.stale_days}d")
    print(f"ghosted    {cfg.thresholds.ghosted_days}d")
    print(f"followup   max {cfg.followup.max_touches_per_company} per company, "
          f"{cfg.followup.min_days_between}d apart")
    if not cfg.master_profile.exists():
        print(f"MISSING    {cfg.master_profile}", file=sys.stderr)
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="jam", description="Job Application Hub")
    ap.set_defaults(func=cmd_menu)
    sub = ap.add_subparsers(dest="cmd")

    r = sub.add_parser("render", help="render a CV from the master profile")
    r.add_argument("--app", help="application id; uses its tailoring.yaml")
    r.add_argument("--tailoring", help="explicit tailoring file")
    r.add_argument("--jd", help="job description, for alias resolution")
    r.add_argument("--out", help="output .tex path")
    r.add_argument("--no-pdf", action="store_true")
    r.set_defaults(func=cmd_render)

    ck = sub.add_parser("check", help="check finished CV PDFs against the master")
    ck.add_argument("paths", nargs="+", help="PDF files or directories to scan")
    ck.add_argument("--max-pages", type=int)
    ck.add_argument("--contact", action="store_true",
                    help="also require the contact email to extract")
    ck.set_defaults(func=cmd_check)

    ib = sub.add_parser("inbox", help="what job-radar has found")
    ib.add_argument("--top", type=int, default=20, help="rows to show")
    ib.add_argument("--min-score", type=float, default=0.0)
    ib.add_argument("--max-age", type=int, help="days since posted")
    ib.add_argument("--q", help="search title, company and JD text")
    ib.add_argument("--all", action="store_true",
                    help="the decided ones too: expired, applied, archived")
    ib.add_argument("--why", action="store_true", help="show the triage reason")
    ib.add_argument("--yes", "-y", action="store_true",
                    help="skip the confirmation when taking from the picker")
    ib.add_argument("--no-tailor", action="store_true",
                    help="just take it; write the CV later")
    ib.add_argument("--plain", action="store_true",
                    help="print the table instead of the picker")
    ib.set_defaults(func=cmd_inbox)

    bl = sub.add_parser("build", help="rebuild one application's CV from its cv.tex")
    bl.add_argument("app", help="application id (the folder name)")
    bl.add_argument("--clean", action="store_true",
                    help="remove latexmk's working files afterwards")
    bl.set_defaults(func=cmd_build)

    tl = sub.add_parser("tailor", help="have the agent write the CV for one application")
    tl.add_argument("app", help="application id")
    tl.add_argument("--model", help="override the model for this run")
    tl.set_defaults(func=cmd_tailor)

    sb = sub.add_parser("submit", help="record a submission that has happened")
    sb.add_argument("app", help="application id")
    sb.add_argument("--note", help="anything worth remembering")
    sb.set_defaults(func=cmd_submit)

    tr = sub.add_parser("triage", help="score vacancies the radar has not rated")
    tr.add_argument("--count", type=int, default=20)
    tr.set_defaults(func=cmd_triage)

    tk = sub.add_parser("take", help="turn a vacancy into an application")
    tk.add_argument("query", help="job id, or part of the company or title")
    tk.add_argument("--yes", "-y", action="store_true")
    tk.set_defaults(func=cmd_take)

    ak = sub.add_parser("ask", help="answer form questions from the bank (JSON)")
    ak.add_argument("questions", nargs="*", help="or one per line on stdin")
    ak.add_argument("--type", choices=("number", "integer", "text", "range"),
                    help="shape the answer for this kind of field")
    ak.set_defaults(func=cmd_ask)

    ln = sub.add_parser("learn", help="record an answer given by the human")
    ln.add_argument("question")
    ln.add_argument("answer")
    ln.add_argument("--slot", help="attach as a new wording of a known slot")
    ln.add_argument("--reuse", default="always",
                    choices=answerbank.REUSE)
    ln.set_defaults(func=cmd_learn)

    an = sub.add_parser("answers", help="the answer bank for application forms")
    an.add_argument("--init", action="store_true", help="create from the standard set")
    an.add_argument("--force", action="store_true")
    an.add_argument("--missing", action="store_true", help="list unanswered questions")
    an.set_defaults(func=cmd_answers)

    bf = sub.add_parser("backfill", help="recover coverage records from changes.md")
    bf.add_argument("--apply", action="store_true")
    bf.add_argument("--force", action="store_true", help="overwrite existing")
    bf.set_defaults(func=cmd_backfill)

    cv = sub.add_parser("coverage", help="validate and summarise an application's coverage")
    cv.add_argument("--app", required=True)
    cv.set_defaults(func=cmd_coverage)

    g = sub.add_parser("gaps", help="what the market wants that the master lacks")
    g.add_argument("--min-count", type=int, default=1)
    g.add_argument("--terms", action="store_true",
                   help="count terms inside gaps rather than whole phrases")
    g.set_defaults(func=cmd_gaps)

    c = sub.add_parser("config", help="show resolved configuration")
    c.set_defaults(func=cmd_config)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
