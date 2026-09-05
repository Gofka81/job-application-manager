# Data model

Files are the truth. Derived state is never stored. DuckDB reads this
directly; there is no ingest step.

## Layout

```yaml
experience:
  - id: northwind
    company: Northwind Systems
    title: Senior Software Engineer
    from: 2023-04
    bullets: [...]
skills:
  python: {since: 2018-09}
legal:  {work_authorization: ..., notice_period: ...}
comp:   {expected: ...}
```
data/                             # NEVER in git
├── master-profile.yaml           # asset: THE single truth -- experience,
│                                 #   skills, dates, awkward form fields
├── templates/
│   ├── cv.typ                    # render template
│   ├── nudge.md                  # asset: follow-up templates
│   └── final.md
├── answer-bank.yaml              # asset: answers to form questions
├── story-bank.md                 # asset: stories, structured for retrieval
├── question-bank.md              # asset: questions that actually get asked
├── weak-spots.md                 # asset: recurring failures
├── decision-journal.md           # asset: decision + reason + date
├── contacts.tsv                  # asset: who to send follow-ups to
├── applications/
│   └── 2026-09-04--northwind--senior-swe/
│       ├── application.json      # facts about the application
│       ├── jd.md                 # JD snapshot at submission time
│       ├── cv.pdf                # what actually went out
│       ├── cover.pdf
│       └── prep-round-2.md       # prep sheet, on demand
└── logs/
    ├── status.jsonl              # status transitions
    ├── rounds.jsonl              # interview stages
    ├── follow-up.jsonl           # touches sent
    └── changes.jsonl             # LinkedIn, profile, channel, filter changes
```yaml
experience:
  - id: northwind
    company: Northwind Systems
    title: Senior Software Engineer
    from: 2023-04
    bullets: [...]
skills:
  python: {since: 2018-09}
legal:  {work_authorization: ..., notice_period: ...}
comp:   {expected: ...}
```

## Join key

`app_id` = the application folder name:
`YYYY-MM-DD--company-slug--role-slug`.

Assigned once at creation and **never changed** — it is the join key across
all four logs. The date in the key is the submission date, not the posting
date.

---

## `application.json`

| field | example | why |
|---|---|---|
| `app_id` | `2026-09-04--northwind--senior-swe` | key |
| `company`, `title` | `Northwind Systems`, `Senior Software Engineer` | grouping |
| `source_url` | the link | getting back to the original |
| `channel` | `linkedin` / `career_site` / `greenhouse` / `referral` | **where** you applied |
| `discovery` | `radar` / `self` | **how** you found it |
| `role_archetype` | `platform` / `analytics` / `generalist` | CV versions are only compared within an archetype |
| `cv_version` | hash of `tailoring.yaml` | **provenance only**, not a dimension |
| `radar_score` | `8` | controls the composition of the sample |
| `score_source` | `radar` / `hub` | what produced the score |
| `jd_hash` | hash of the JD | link to the repost detector |
| `submitted_at` | ISO-8601 with timezone | start of the aging clock |

**Current status is deliberately absent.** Status is a fold of
`status.jsonl`. Storing it would create a second truth that needs syncing.

`channel` and `discovery` are different dimensions. The first says which
portal you applied through; the second says whether the radar found it or
you did. The second is interesting on its own: it shows whether WF1 brings
quality, or only volume.

---

## `coverage.yaml`

What the vacancy asked for and what the master could answer. Structured, not
prose: a `changes.md` paragraph cannot be joined to an outcome later.

```yaml
experience:
  - id: northwind
    company: Northwind Systems
    title: Senior Software Engineer
    from: 2023-04
    bullets: [...]
skills:
  python: {since: 2018-09}
legal:  {work_authorization: ..., notice_period: ...}
comp:   {expected: ...}
```yaml
requirements:
  - text: "5+ years Python"
    weight: required          # required | preferred
    status: covered           # covered | partial | missing
    evidence: [northwind.2, skills.python]
  - text: "dbt"
    weight: required
    status: missing
    evidence: []
```yaml
experience:
  - id: northwind
    company: Northwind Systems
    title: Senior Software Engineer
    from: 2023-04
    bullets: [...]
skills:
  python: {since: 2018-09}
legal:  {work_authorization: ..., notice_period: ...}
comp:   {expected: ...}
```

`evidence` points at master ids, so a claim of coverage is checkable rather
than asserted.

### What this makes answerable, and at what strength

The unit of observation decides everything here.

| question | unit | n | verdict |
|---|---|---|---|
| does a higher share of covered requirements yield more interviews | application | 29-150 | weak — one predictor against ~15 events, only a large effect shows |
| which specific missing requirement precedes rejection | **requirement** | hundreds | **strong** — "dbt required and missing in 14 applications, 14 rejected" is rule-of-three territory |
| what does the market want that the master lacks | **requirement** | hundreds | **strongest — needs no outcomes at all** |

The third is the reason to collect this from day one: aggregating `missing`
across applications answers what to learn, and it works from the first
application, with no statuses, dates or replies.

### Joining gaps to rejection latency

A missing visa, location or years-of-experience is a knockout filter and
rejects within a day. A missing technology is a human judgement and rejects
over weeks. Splitting rejections by latency separates the two — and different
gaps need different remedies.

### The confounder to state up front

You apply where you partly match, so "X was missing → rejected" can simply
mean "harder roles reject more often". Controlled the same way as everywhere
else: `radar_score` alongside, and comparisons within similar roles.

---

## Logs

One line = one event. Files are **append-only**.
Shared fields: `ts` (ISO-8601 with timezone), `app_id`.

| file | specific fields |
|---|---|
| `status.jsonl` | `from`, `to`, `source`, `note` |
| `rounds.jsonl` | `round_no`, `kind` (`screen`/`tech`/`system-design`/`final`), `outcome`, `prediction`, `debrief` |
| `follow-up.jsonl` | `contact`, `template`, `sent_via`, `delivered`, `note` |
| `changes.jsonl` | `area`, `what`, `why`, `filter_version` — **no `app_id`**, these are profile changes |

`area` values in `changes.jsonl`: `linkedin`, `master_profile`,
`cv_template`, `channel_mix`, `radar_filter`, `thresholds`.

### The `source` vocabulary and retraction

| `source` | what it is | counts toward timing metrics |
|---|---|---|
| `email` | classified from an email | yes |
| `portal` | status seen in the ATS portal | yes |
| `manual` | human confirmed it in a session | yes |
| `correction` | replaces an earlier record with the same `(app_id, to)` | yes |
| `backfill` | entered after the fact | **no** |

- `from: null` — the previous state is unknown.
- `to: null` — a **retraction**: it withdraws the application's latest
  observation. Nothing is deleted; a new line is appended.

**Backfilled records take no part in latency computation.** A date written
after the fact is not an observation of time; counting it would corrupt both
time-to-response and transition velocity.

---

## Statuses

| status | meaning | who writes it |
|---|---|---|
| `submitted` | submission confirmed | intake, automatically |
| `acknowledged` | automated ATS confirmation | email, automatic |
| `in_process` | a **human** replied: screening, call, take-home | confirmed in a session |
| `offer` | offer | confirmed in a session |
| `rejected` | rejection | email, automatic |
| `withdrawn` | you pulled out | manual only |

`stale` and `ghosted` are not on the list — they are **computed** from
`submitted_at`, the log and the thresholds. That is what makes a threshold a
query parameter rather than a fact in history: change your mind, recompute
the whole history, no migration.

Interview stages are not statuses but `rounds.jsonl`. A status holds only the
latest value, while the funnel is built on the sequence.

---

## Answer bank

```yaml
experience:
  - id: northwind
    company: Northwind Systems
    title: Senior Software Engineer
    from: 2023-04
    bullets: [...]
skills:
  python: {since: 2018-09}
legal:  {work_authorization: ..., notice_period: ...}
comp:   {expected: ...}
```yaml
- slot: sql_years
  question: "Years of experience with SQL"
  aliases: ["SQL (years)", "How many years of SQL"]
  type: number
  stated: "6 years"          # what the human said
  stated_at: 2026-09-04
  since: 2020-09             # computed backwards, month precision
  granularity: 0.5
  reuse: always

- slot: work_authorization
  type: enum
  value: {ref: master-profile.legal.work_authorization}
  reuse: always
```yaml
experience:
  - id: northwind
    company: Northwind Systems
    title: Senior Software Engineer
    from: 2023-04
    bullets: [...]
skills:
  python: {since: 2018-09}
legal:  {work_authorization: ..., notice_period: ...}
comp:   {expected: ...}
```

Where possible `value` references `master-profile.yaml` instead of copying
it. The fact lives in one place; the bank stores **how to phrase it as an
answer to a specific question**.

**Tenure is stored as a date and entered as a number.** Rounded to 0.5, and
**never rounded up by more than half a year**. Gaps in experience need no
modelling — the human's own estimate already accounts for them, and the
back-computed date preserves it.

**One value, many field types:** from the same `since` the agent produces
`5.5` for a decimal field, `5` for an integer, `5-10` for a range dropdown,
`5+ years` for free text. The human is never asked twice.

| `reuse` | examples |
|---|---|
| `always` | education, work authorization, years per technology, location |
| `per_archetype` | salary expectation, work format |
| `never` | "why our company" — regenerated per JD every time |

---

## `master-profile.yaml`

The single truth. Prose, dates, skills and awkward form fields in one file.
There is no second master.

```yaml
experience:
  - id: northwind
    company: Northwind Systems
    title: Senior Software Engineer
    from: 2023-04
    bullets: [...]
skills:
  python: {since: 2018-09}
legal:  {work_authorization: ..., notice_period: ...}
comp:   {expected: ...}
```yaml
experience:
  - id: northwind
    company: Northwind Systems
    title: Data Engineer
    from: 2023-04
    bullets: [...]
skills:
  sql: {since: 2020-09}
legal:  {work_authorization: ..., notice_period: ...}
comp:   {expected: ...}
```yaml
experience:
  - id: northwind
    company: Northwind Systems
    title: Senior Software Engineer
    from: 2023-04
    bullets: [...]
skills:
  python: {since: 2018-09}
legal:  {work_authorization: ..., notice_period: ...}
comp:   {expected: ...}
```

The CV is **rendered** from it through a LaTeX template (D42). There is no
fixed set of versions (D43): every application is tailored from the bare
master, and the plan lives beside that application:

```yaml
experience:
  - id: northwind
    company: Northwind Systems
    title: Senior Software Engineer
    from: 2023-04
    bullets: [...]
skills:
  python: {since: 2018-09}
legal:  {work_authorization: ..., notice_period: ...}
comp:   {expected: ...}
```yaml
# data/applications/<app_id>/tailoring.yaml
max_pages: 1
drop: [contoso.1, fabrikam.2, kotlin, scala]     # section, id, <id>.<index>, skill
emphasis: [databricks, pyspark, aws]       # reorders only, never adds
bullets:
  northwind.1:
    from: [northwind.1]                     # what the gate checks against
    text: "…"
```yaml
experience:
  - id: northwind
    company: Northwind Systems
    title: Senior Software Engineer
    from: 2023-04
    bullets: [...]
skills:
  python: {since: 2018-09}
legal:  {work_authorization: ..., notice_period: ...}
comp:   {expected: ...}
```

Omit the file and the bare master renders — useful for review, not for
sending. There is deliberately **no shared default set of drops**: it would
quietly become the fixed version set D43 removed.

---

## Thresholds

Both provisional, both in one place in the config.

| parameter | provisional | consumer |
|---|---|---|
| `stale_days` | 21 | follow-up trigger in WF6, not terminal |
| `ghosted_days` | 45 | terminal status in the funnel |

The numbers from English-language trackers (stale 14 / ghosted 21-30) do not
transfer: replies on the UK market come noticeably later.

**Recalibration:** once 30+ observed times-to-first-response accumulate, set
`ghosted_days` to the p90 of that distribution and record the change in
`changes.jsonl`.

---

## Rules

1. Logs are never rewritten. A mistake is fixed by a compensating event
   (`source: correction`) or a retraction (`to: null`), never by editing a
   line.
2. Derived state is not stored. Current status, aging, the funnel — all
   computed by query when needed.
3. Only assets are hand-edited. Everything under `logs/` and
   `applications/*/application.json` is written by code.
4. Machine logs are JSONL, not YAML. YAML would need converting before every
   query — exactly the ingest step that was removed.
5. `data/` never enters git. The repo keeps only `data/README.md` and
   `.gitkeep`.
