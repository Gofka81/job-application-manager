# Roadmap

The queue is determined by data dependencies, not by importance. Sizes are
S / M / L — relative complexity, not hours.

---

## WF prioritization

| WF | importance | complexity | depends on | when |
|---|---|---|---|---|
| WF1 job-radar | high | — | — | **done** |
| WF2 materials | high | **L** — master, template, gate | nothing | block 1 |
| WF3 submission | high | M — the agent does the hard part | WF2 | block 1 |
| WF4 write submission | medium | **S** — a side effect of intake | WF3 | block 1 |
| WF4 capture outcome | **highest** | **L** — email matching | block 1 | block 2 |
| WF7 analytics | **highest** | M | ~30 submissions | block 3 |
| WF6 follow-up | medium | S | thresholds from block 2 | block 4 |
| WF5 interviews | high *if* it gets there | M | interviews happening | block 5 |

### Three things worth taking from this table

**WF7 is the most important and still third.** It has nothing to work on
until ~30 submissions exist. Built earlier, it answers "not enough data" to
every query. Importance does not entitle it to go first.

**WF2 is harder than WF3.** Counter-intuitively: filling forms looks scarier,
but an agent does that. Migrating the master profile, the render template and
the fact gate are three separate pieces of work — and they sit on the
critical path.

**WF4 is split in two**, and the halves live in different blocks. Writing the
submission is nearly free. Capturing the outcome is the hardest deterministic
piece in the project, and everything analytical depends on it.

---

## Block 0 · Foundation

Nothing runs without this. Done once.

- [x] **F1** `S` Repo skeleton: `.gitignore` for `data/`, `.env.example`,
      pre-commit hook against `data/` in staged, `data/README.md` with the
      layout
- [~] **F2** `L` **Master migration** — the current CV into a structured
      `master-profile.yaml`: experience with bullets, skills with `since`,
      `legal`, `comp`. Manual work with agent help. *Critical path.*
      Done: identity, experience, projects, education, certifications, skills —
      18 bullets verified verbatim against the source CV. **Outstanding: the
      17 NEEDS INPUT fields** — `legal`, `comp`, `logistics`, education years,
      and `since` dates for 18 skills. Forms ask for exactly these.
- [x] **F3** `M` LaTeX template (`templates/resume.cls`) plus `jam render`
      from the master, with an enforced `max_pages`
- [x] **F5** `S` Config: `stale_days`, `ghosted_days`, paths, detector
      thresholds

**Exit:** `jam render` produces a PDF worth sending from the bare master.

---

## Block 1 · Intake — the submission path

The main block. Until it works, nothing else has anything to stand on.

- [ ] **B1.1** `S` `app_id`, application folder, `application.json` schema,
      `jd.md` snapshot
- [ ] **B1.2** `M` Intake, branch A — link from INBOX: JD and score already
      exist
- [ ] **B1.3** `M` Intake, branch B — arbitrary link: the agent reads the
      page; fallback is pasting the text
- [ ] **B1.4** `S` Dedup against already-submitted, plus company context
- [ ] **B1.5** `S` Off-radar triage with the same bounded prompt,
      `score_source`
- [x] **B1.6** `L` **Fact gate** — port `verify-cv-facts.mjs` to Python. The
      `regex` package instead of `re`. Tests and golden fixtures from the
      original. *The riskiest piece of the block*
- [x] **B1.8a** `S` ATS extraction check wired into the build (D72)
- [ ] **B1.7** `M` Render CV for an application: `tailoring.yaml` + aliases +
      overrides, gate and page limit before the PDF
- [x] **B1.7a** `S` Alias resolver — declared synonym forms in the master,
      matched against the JD text, applied to the SKILLS line only. No model
- [x] **B1.7b** `M` `overrides.yaml`: reframed and merged bullets with a
      `from` provenance list; the gate checks each override against its
      declared sources, not against the whole master (D40a)
- [~] **B1.7c** `M` Coverage: JD requirements vs the master -> structured
      `coverage.yaml` (weight, status, evidence) plus the prose gaps section
      in `changes.md`; the tailoring plan follows from it (D70)
- [x] **B1.7g** `S` `jam gaps` — aggregate `missing` across applications.
      Needs no outcomes, so it pays off from the first application
- [x] **B1.7d** `S` Bullet merging in the render path
- [~] **B1.7e** `M` Cover letter — parked, see `todo.md`. Gate scoping is
      settled; it needs a template and a brief first
- [ ] **B1.7f** `S` Move the tailoring skill into `.claude/skills/`, carrying
      over `references/tailoring-principles.md` (D34)
- [ ] **B1.8** `M` Answer bank: schema, bootstrap over 30-40 standard
      questions, extraction from old CVs and LinkedIn
- [ ] **B1.9** `M` The agent fills the form, matches slots, asks in a batch
      per page
- [ ] **B1.10** `M` STOP screen: field list with values, agent-inferred ones
      highlighted
- [ ] **B1.11** `S` Confirmed Submit → `application.json` plus
      `status.jsonl: submitted`
- [ ] **B1.12** `S` Answer harvest at STOP: short and enum go straight to
      `always`, long free text becomes `draft`

**Exit (M1):** an application goes from link to record with no manual
copying.

**What can slip inside the block:** B1.3 (arbitrary links) — if you start by
applying only from the radar. B1.12 — the bank fills without passive harvest,
just more slowly.

---

## Block 1.5 · Watchdog

Small, standalone, allowed to slip. But it is what insures the meta-risk:
"system built, no applications sent".

- [ ] **W1** `S` Endpoint on the Pi plus a Cloudflare Access service token
- [ ] **W2** `S` Watchdog logic and the Telegram message
- [ ] **W3** `S` Ping on submission from the hub, `snooze` with delivery
      confirmation

---

## Block 2 · Capturing outcomes

The hardest deterministic piece. Without it there is no funnel — only a list
of submissions.

- [ ] **B2.1** `M` Status log: writing, folding into current state, the
      `source` vocabulary, `correction` and retraction
- [ ] **B2.2** `M` Gmail: narrow query, read-only, candidate extraction
      (sender, subject, first N characters)
- [ ] **B2.3** `L` **Matching an email against the closed list of
      applications.** Ideas from `reply-matcher.mjs`: placeholders in the
      company field, short names on a word boundary, the time window from
      `submitted_at`
- [ ] **B2.4** `M` Classification with a mandatory `unclear`; auto-write
      rejections and acknowledgements; everything else into a queue
- [ ] **B2.5** `S` Weekly sweep of open applications
- [ ] **B2.6** `M` Digest at session start

**Exit (M2):** ~20 applications, each with both a beginning and an end in
the log.

---

## Block 3 · The detector

- [ ] **B3.1** `M` DuckDB query layer over the files: views for applications,
      logs, joins
- [ ] **B3.2** `M` Derived: current status, `stale`, `ghosted`,
      time-to-first-response, stage funnel
- [ ] **B3.3** `M` Catastrophe checks with thresholds, `not enough data` as a
      first-class output, right censoring in medians
- [ ] **B3.4** `S` Weekly report: six lines of verdicts, not a dashboard

**Exit (M3):** the first report, where most lines read "not enough data" —
and that is correct.

---

## Block 4 · Follow-up

- [ ] **B4.1** `S` Aging queue by `stale_days`
- [ ] **B4.2** `S` Cap engine: 2 per company, 10 days, stop after rejection
- [ ] **B4.3** `S` Templates, `contacts.tsv`, recording **delivery**
- [ ] **B4.4** `S` Recalibrate `ghosted_days` to p90, record in
      `changes.jsonl`

---

## Block 5 · Interviews

- [ ] **B5.1** `S` `rounds.jsonl`: round record, type, outcome, prediction
- [ ] **B5.2** `S` Debrief: three questions plus prediction, same day
- [ ] **B5.3** `M` Weekly curation: raw → story bank, question bank, weak
      spots
- [ ] **B5.4** `M` Prep sheet on demand
- [ ] **B5.5** `S` Calibration: prediction against outcome

---

## Milestones

| milestone | exit criterion | what it proves |
|---|---|---|
| **M0** | `render` produces an acceptable PDF | master migrated, template works |
| **M1** | first application from link to record | the pipeline is whole |
| **M2** | 20 applications with beginnings and endings | the data is usable |
| **M3** | first detector report | the feedback loop closed |
| **M4** | first threshold recalibration | the system learns from its own data |

---

## What can run in parallel

**F2 (master migration)** is long manual work that can run in the background
while B1.1-B1.5 is being written. It is on the critical path, so start it
first rather than completing it before any code.

**B1.6 (fact gate)** is a self-contained piece with tests available from
career-ops. It does not depend on the rest of block 1 and can be done any
time before B1.7.

**Block 1.5 (watchdog)** blocks nothing but itself.

## What not to build early

**The detector before 30 submissions.** It will answer "not enough data" to
everything and create the illusion that something is working.

**Follow-up thresholds before block 2.** Taking them from English-language
trackers is wrong for the UK market, and your own distribution does not exist
yet.

**The prep sheet before the first interviews.** There is no way to know what
belongs in it until you have seen which rounds actually happen.
