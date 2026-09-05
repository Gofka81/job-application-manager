# Existing solutions

State as of 2026-09-04. Sources are web search plus a local reading of
career-ops. This is a map of what exists, not an audit.

---

## Email parsing for application tracking

The problem class is solved many times over. The shape is the same
everywhere: keyword/regex prefilter → classification → statuses
Applied / Interview / Rejected / Offer.

### Open source

| project | what is inside |
|---|---|
| [CareerSync](https://github.com/Tomiwajin/CareerSync) | Gmail read-only, regex patterns over phrases like "thank you for applying", "not selected". Claims to be stateless with no data storage. How the check is triggered is not documented in the README |
| [ApplyPotato](https://github.com/coolbrother/apply-potato) | Detects submission confirmations, OAs, interviews, offers, rejections. Runs locally |
| [adamrangwala/Job-Application-Tracker](https://github.com/adamrangwala/Job-Application-Tracker) | Google Apps Script over Gmail, funnel visualization, drafts replies to rejections |
| [job-application-tracker topic](https://github.com/topics/job-application-tracker) | the rest of the ecosystem |

### Commercial

| product | notes |
|---|---|
| [Jobtrakr](https://www.jobtrakr.in/) | auto-detects confirmations, invitations, rejections from the inbox |
| [G-Track](https://jobtrack-ai.com/gmail-job-tracker) | matching against known company domains plus keywords — heuristics, not semantics |
| [JobShinobi parser](https://www.jobshinobi.com/tools/job-application-email-parser-tool) | extracts company, position, status |
| [JobShifu](https://jobshifu.com/job-tracker) | **reports ghosting and rejection as separate metrics** |
| [GotResumeBuilder](https://www.gotresumebuilder.com/job-application-tracker) | thresholds: stale 14 days / ghosted 30 days |

## Form autofill

| product | notes |
|---|---|
| [Simplify](https://www.jobshinobi.com/compare/teal-job-tracker-vs-huntr) | autofills 100+ portals: Workday, Greenhouse, iCIMS |
| Huntr, Teal (extensions) | capture a vacancy from the page; Huntr is lighter, Teal pulls more metadata but is slower |

**A fork in the road, not a recommendation.** Simplify covers ~80% of
standard ATS portals with an off-the-shelf extension. The downside: it does
not learn from your answers, so it never fills the answer bank. A browser
agent is slower on standard forms but covers the non-standard ones and grows
the asset.

---

## career-ops — the closest analogue, half of it already written

[github.com/santifer/career-ops](https://github.com/santifer/career-ops),
MIT, local copy at `~/Developer/DataEng/career-ops`.
Node/`.mjs`, dozens of utilities, covers almost the whole of our domain.

Read: `ARCHITECTURE.md`, `verify-cv-facts.mjs`, `funnel-velocity.mjs`
(header plus the log fold), and the headers of `reply-watch`,
`reply-matcher`, `application-answers`, `followup-cadence`,
`detect-reposts`, `rejection-latency`, `analyze-patterns`, `intake`.
Everything else is by filename only.

### The doctrine matches ours almost word for word

- **"Files are canonical — databases are derived"**, declared settled
  doctrine: SQLite exists only as a derived index and will "never become a
  primary store — not even opt-in". We arrived at the same thing
  independently.
- **Human-in-the-loop**: "It never submits applications on your behalf".
- **Local-first**, no server and no account.
- **Deterministic/agentic split** — exactly our D21: `intake.mjs` does
  "enumeration, text extraction, idempotency bookkeeping — everything
  deterministic", while semantic mapping lives in `modes/intake.md`; the
  script **never** writes `cv.md` or `profile.yml` — the agent does, after
  explicit human confirmation.

### What we took from `verify-cv-facts.mjs`

A deterministic gate **with no model**. It extracts four claim types
(`employer`, `title`, `tool`, metrics) from the finished document and checks
them against the source text; allow-list for exceptions, list of forbidden
phrases. Wired into PDF generation, so it cannot be an optional step.

**A symmetric extractor** — the same code over the document and over the
source. Widening a pattern can only add claims on both sides; it cannot hide
a fabrication by construction. That property is worth keeping in any
implementation of our own.

**Edge cases documented in the code** (each one a real bug from review):

- a CV written in non-ASCII digits (ar, hi, ja, zh) produced zero claims —
  the gate "passed" having checked nothing;
- `Worked at` capitalized did not match while `worked at` did: i.e. the exact
  spelling CVs are written in was invisible;
- `50k users` normalized to `50 users` — a 1000x inflation passed while a
  smaller `900 users` was correctly caught;
- the modifier window between a number and its noun: too narrow broke the
  gate in both directions.

### Correction: they DO account for small samples

An earlier version of this file claimed no tool asks whether there is enough
data. **Not true** — `funnel-velocity.mjs` carries a section titled
"Statistical honesty rules (council-reviewed, non-negotiable)":

- `CLAIM_MIN_N = 20` — no comparative claims below 20 applied; there is even
  a test named `'tone: no multiplier claim under n=20'`;
- `HOP_MIN_N = 3` — fewer than three completed measurements →
  `insufficientData`, no median at all;
- medians **report right censoring** ("n still waiting, excluded"), because
  "with 61% ghosting, completed-only medians are survivorship-biased";
- 0-day transitions (same-day catch-up entries) are excluded from medians but
  counted separately.

`analyze-patterns.mjs` has `--min-threshold` and `--min-vendor-n` — the same
sample floors.

So our "catastrophe detector" is not unique in spirit. What is not stated
there as explicitly is the framing: output is a verdict — ok / catastrophe /
not enough data — rather than a dashboard.

### The append-only correction protocol — a ready answer

They keep `data/status-log.tsv`, append-only:

```
{tracker#}\t{YYYY-MM-DD}\t{from}\t{to}\t{source}\t{note}
```

- `from` = `-` — the prior state is unknown;
- `to` = `-` — a **retraction**: it withdraws the row's latest observation;
- `source: correction` — replaces an earlier record with the same `(num, to)`;
- `VALID_SOURCES`: `set-status`, `web`, `correction`, `backfill`, `manual`;
- **`DAY_MATH_SOURCES` is narrower** — `set-status`, `web`, `correction`.
  `backfill` and `manual` do not enter latency computation: a date written
  after the fact is not an observation of time.

We had not anticipated that last point, and it matters: without it
retroactive entries corrupt every timing metric.

### What we are NOT taking

The LLM entailment check (a bullet can reference a real fact and still
exaggerate it). career-ops does not have one, and that is probably right: a
deterministic check does not rubber-stamp its own output.

---

## What `tailor-cv` actually did — 29 real applications

Analysed 2026-09-05 against `~/Developer/DataEng/cv-tailor/applications`:
29 folders, each with `jd.md`, `cv.tex`, `cv.pdf` and `changes.md`.

### A metric that had to be retracted

The first pass diffed each tailored `cv.tex` against the *current*
`master/cv.tex` and reported that 78% of bullets were substantively rewritten
and that all 29 applications claimed skills absent from the master, one of
them appearing in 11 of the 29.

**That measurement is unsound.** The master itself moved: the most frequent
of those skills had been in the master when those CVs were generated and was
edited out afterwards. There is no git history for the source repository, so
the master cannot be reconstructed as of each application date, and drift
cannot be separated from tailoring.

Keep the lesson rather than the number: **a moving baseline makes a diff
meaningless.** It is also the argument for the master living under version
control in this project.

### What holds up

`changes.md` is written at the time of each edit and describes changes against
the master as it then stood, so it does not suffer from drift. Counting the
edit types it reports:

| operation | mentions | applications |
|---|---|---|
| cut / dropped | 94 | 28/29 |
| added | 81 | 27/29 |
| layout, one page | 72 | 17/29 |
| reordered | 49 | 26/29 |
| merged | 41 | 21/29 |
| JD wording | 35 | 19/29 |
| reframed | 31 | 20/29 |
| **rewritten prose** | **9** | **9/29** |

Selection, ordering and layout dominate. Prose rewriting is the rarest
operation, not the common one.

### What "added" actually means

Sampling the 76 lines that mention adding: it is overwhelmingly **framing
language appended to an existing fact** — "validation" and "ensuring trusted,
reliable data delivery" onto a data-quality bullet; "applying security and
governance practices" onto RBAC work; "in a strict security and compliance
environment" onto a compliance bullet.

The skill audits itself explicitly: *"No employer, title, date, metric, or
technology was added that isn't in the master."* One exception it flagged
itself: a client name that the master does not hold.

**The consequence for the gate.** A career-ops-style gate checks employers,
titles, tools and numbers — so it would have passed nearly everything the
skill actually did, and would have caught the one client name. The gate's
blind spot is adjectival framing, and that is acceptable: framing layered onto
a real fact is what anyone writing their own CV does. This is why D40 became
"a boundary, not a ban".

### Assessment

Strong as an **authoring assistant**, weak as a **system component**.

The judgement is real: it reads a JD closely enough to note that one
"Data Engineer" posting was a data-governance role wearing a Data Engineer
title, and its gaps sections say plainly where the CV has nothing.

What it lacks is enforcement and reproducibility: the discipline rests on its
own word (the client name was noticed and recorded, but nothing stopped it), the same
input yields different output, and one page was achieved by shrinking margins
each time — so the 29 PDFs are not visually one family.

Hence the split in D34: keep the judgement, add the enforcement.

### An unused dataset

The 29 `changes.md` files contain 29 honest gaps sections — what employers
asked for that the CV does not have. Unlike conversion, this **is** measurable
at this volume: the unit of observation is a requirement, and there are
hundreds of them. Worth aggregating to see what recurs.

---

## What to read from career-ops before writing each block

| our block | read first |
|---|---|
| intake | `intake.mjs`, `jd-capture.mjs`, `browser-extract.mjs`, `dedup-tracker.mjs` |
| WF2 fact gate | `verify-cv-facts.mjs` + `config/cv-facts.example.json` |
| WF4 email | `reply-matcher.mjs` (550 lines of deterministic matching), `reply-watch.mjs` |
| WF4 log | the `status-log.tsv` format, the fold and correction protocol in `funnel-velocity.mjs` |
| WF6 | `followup-cadence.mjs` (`DEFAULT_CADENCE`, touch caps) |
| WF7 | `funnel-velocity.mjs`, `rejection-latency.mjs`, `analyze-patterns.mjs`, `stats.mjs` |
| repost detector | `detect-reposts.mjs` + `role-matcher.mjs` |
| WF1 (review) | `scan.mjs` + `providers/` — Greenhouse, Ashby, Lever, BambooHR, Teamtailor, Workday, Breezy |

`reply-matcher.mjs` deserves separate attention: it documents real matching
failures — a placeholder `?` in the company field matched almost every email
and scored `high confidence`; the short name `HP` matched inside the word
`PHP`. That is a price not worth paying twice.

## What career-ops does not have (stays ours)

- **An answer bank that learns.** `application-answers.mjs` records answers
  within an application; reuse across applications was not visible (the code
  mentions that previously one had to grep old reports).
- **Calibration of predictions in the debrief.**
- **An agent filling the form in the browser.** There the human fills it —
  a deliberate project boundary.
- **DuckDB over files with no persistent index.** They run a SQLite index
  under the same doctrine.

---

## What we took overall

**Thresholds as a starting point.** stale 14 / ghosted 21-30 is the norm
among English-language trackers. **Not transferable directly**: replies on
the UK market come later. We took the idea of two distinct thresholds; the
numbers are our own (D15-D16).

**Ghost rate separate from rejection rate.** JobShifu's approach. Confirms
that silence is an outcome, not missing data (D17).

**Capture at submission time, not parsing after the fact.**
[Stated by a vendor](https://www.autoapplymax.com/blog/job-application-tracker-chrome-extension):
data is taken from the application itself, "not after" — no forgotten
entries, no typos in company names, no wrong dates. Empirically confirms the
intake design. Consequence: **email is needed only for outcomes, not for
recording the application.**

## Where we are better positioned than the vendors

The industry's known pain point is matching an email to an application,
because recruiters write from `no-reply@ats-domain`. One vendor
[tests against 2.5M emails from 50k domains](https://curriculo.me/email-inbox/) —
solving it with data volume.

They have to: they do not know where you applied, so for them it is
open-world extraction. For us it is **matching against a closed list** of our
own applications with dates and companies, plus a time window from
`submitted_at`. A fundamentally easier problem that needs none of their data
(D18).
