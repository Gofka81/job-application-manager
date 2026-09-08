# Settled decisions

75 decisions (D0-D73, plus D40a). The numbers are stable — other documents reference
them. Ordered by theme, not chronologically.

---

## Boundaries and submission

**D0. WF3 boundaries.** WF3 is purely the submission mechanism: it starts
once WF2 has produced the files and ends at a confirmed Submit. Writing the
application record is already WF4. Positioning, focus and CV version do not
belong to WF3.

**D6. Form filling is done by an agent in the browser**, not by scripted
automation over selectors. There is no brittleness against markup — the agent
looks at the page and acts on context.

**D7. STOP shows a list of fields with values, agent-inferred ones
highlighted.** The residual risk after D6 is different: non-determinism
produces a plausible but wrong answer. "Check the form" becomes a
click-through by the fiftieth application; five highlighted fields stay
readable.

**D8. Awkward fields sit in the profile in advance** — salary, location, work
authorization, notice period. So the agent takes them rather than inferring
them.

**D9. `application.json` is created after Submit is confirmed**, never
before. Otherwise abandoned submissions corrupt the funnel denominator.

---

## Sampling

**D1. `role_archetype` in `application.json`.** Originally this existed so CV
versions could be compared within an archetype. With per-application tailoring
(D43) there are no versions to compare, but the field stays: it is a property
of the *vacancy*, not of the CV — the market assigns it, not you — so it
accumulates faster and still answers "do I convert worse on analytics roles".

**D2. A guard metric alongside conversion:** median `radar_score` and
seniority level. Conversion is trivially gamed by lowering ambition;
conversion up while quality drops is a regression.

**D3. `filter_version` in `changes.jsonl`.** job-radar filters do not change
inside a measurement block, otherwise the sample shifts mid-measurement.

**D4. Positioning is not A/B tested.** A block of at least 30 submissions
with fixed positioning, evaluated **only for catastrophe**. An experiment on
difference will not finish before the search ends.

**D5. Range restriction is not treated.** Triage is validated only within the
score range actually applied to.

---

## Follow-up

**D10. Hard caps on touches:** no more than 2 per company, at least 10 days
apart, a full stop after an explicit rejection. Aging makes reminders cheap;
the cap is a property of the engine, not self-discipline.

---

## Interviews

**D11. The debrief is three questions plus a prediction**, the same day:
worst answer; what surprised me; which story landed; prediction in one word.
Three is the threshold at which a debrief still gets written while exhausted.
The prediction gives calibration: the unit of observation is a round, so it
is measurable at small volumes.

**D12. A weak spot from one interview is a hypothesis.** Only what repeats
twice reaches the file. Otherwise preparation gets rewritten around noise.

**D13. Capture cheap, curate later.** The debrief is written raw on the day
of the interview; promotion into the story bank is a separate unhurried act
once a week. Same pattern as `draft` in the answer bank: deliberately one
mechanism serving two assets.

**D64. The main WF5 artifact is the prep sheet**, one page before a round.
The constraint matters more than the contents: mini-research is a classic
rabbit hole.

**D65. The prep sheet is generated on demand**, not automatically —
provisionally. Automatic generation would produce a pile of documents nobody
opens. To be revisited at design time.

**D66. The story bank is structured for retrieval, not for storage.**
Competency, technologies, scale, raw text. The value is not in what is
recorded but in it surfacing at the right moment.

**D67. The question bank is a separate asset.** Interview questions repeat
across companies just like form questions do. Measurable at small volumes:
dozens of questions per season.

**D68. `rounds.jsonl` steers preparation focus.** Analytics does not report
here, it steers: once the round type where applications die is visible, the
prep sheet weights toward it.

**D69. Not doing:** calendar and round scheduling, mock interviews.

---

## Silence and thresholds

**D14. `ghosted` is not written to the log — it is computed.** Once
submissions are recorded automatically the denominator is complete, so
silence is fully derivable. Consequence: **a threshold is a query parameter,
not a fact in history** — change your mind, recompute the whole history, no
migration.

**D15. Two different thresholds, both provisional, both in one config
location:** `stale_days` 21 (follow-up trigger, not terminal),
`ghosted_days` 45 (terminal in the funnel). The numbers from English-language
trackers (14 / 21-30) do not transfer: replies on the UK market come later.

**D16. Recalibration rule.** Once 30+ observed times-to-first-response
accumulate, set `ghosted_days` to their p90 and record it in `changes.jsonl`.

**D17. Ghost rate and rejection rate are separate metrics.** "40% rejected"
and "40% silent" are different diagnoses: the first is about the CV and
profile, the second about the channel — or about the application never
arriving.

---

## Email

**D18. Emails are matched against the closed list of applications.** Not
open-world extraction of a company from the email body, which is what vendors
do (they have to — they do not know where you applied). Plus a time window
from `submitted_at`. A fundamentally easier problem that needs none of their
data volume.

**D19. Classification is allowed to say `unclear`.** A model without that
option will guess — and will guess wrong exactly on borderline phrasings like
"we'll keep your CV on file".

---

## Runtime

**D20. There is no scheduled daemon.** Everything derived is computed at
query time.

**D21. The system splits in two by the right to call a model.** The
deterministic core (queries, reports, digest, validation, fact gate) is
Python + DuckDB with no model. The agentic edges (generation, browser,
classification) run in a Claude Code session. This operationalizes "LLM calls
are bounded": the boundary runs through code.

**D22. A session opens with the digest.** Email is checked on demand at
session start — a day of latency changes nothing. The nudge rides on an
action the human already wants to take.

**D23. The "you disappeared" watchdog lives on the Pi, not the Mac.** A
reminder about absence cannot live in the system the person has vanished
from. The ping is sent **at Submit**, not at session start: a session without
submissions is not activity. The Pi stores one number, not a log; analytics
never reads it.

**D28. Two ways to switch the watchdog off.** `snooze` with an expiry (the
radar keeps running) or stopping the container (the search is over). Snooze
always carries an expiry, is visible in the digest, its reason goes into
`changes.jsonl`, and **its delivery is confirmed** — unlike the ping, an
undelivered snooze means being nagged on holiday.

---

## Intake

**D24. One intake, two branches, one dossier.** From INBOX the JD and score
already exist. For an arbitrary link the agent reads the page itself.
Downstream, the code does not know which branch it came from.

**D25. `discovery` is separate from `channel`.** Where you found it and where
you applied are different dimensions. `discovery` shows whether WF1 brings
quality or only volume.

**D26. Off-radar JDs run through the same bounded triage**, so `radar_score`
stays comparable. `score_source` records its provenance.

**D27. Dedup against already-submitted applications.** The same vacancy can
resurface a month later from a new source. The hub checks only its own
records; it never reaches into the Pi. Plus company context shown at intake —
also needed for the D10 cap.

---

## Statuses

**D29. Six values:** `submitted`, `acknowledged`, `in_process`, `offer`,
`rejected`, `withdrawn`. Every extra status is a decision that has to be made
at recording time.

**D30. `acknowledged` separate from `in_process`** — the difference between a
bot and a human. The first proves the application arrived; the second is the
first real reply, from which the main timing metric runs.

**D31. Who writes what, by asymmetry.** Automation writes what a human would
forget (acknowledgements, rejections). It asks about what the human would
notice anyway (a human reply, an offer).

**D32. Interview stages are not statuses but `rounds.jsonl`.** Round counts
and types vary; a status holds only the latest value, while the funnel is
built on the sequence.

**D33. `rejected` is terminal.** A reopened role is a new application with a
new `app_id`.

---

## CV anti-fabrication

**D34. `tailor-cv` is kept for its judgement, not its mechanics.** Its shape
was right for a *standalone tool*; as a *system component* the division of
labour is different — a deterministic skeleton with the agent at the edges.

What survives: reading the JD, the requirement-to-coverage table, the honest
gaps section, bounded reframing, the cover letter, and
`references/tailoring-principles.md`.

What is taken away: it no longer edits `.tex`, no longer controls margins or
layout, no longer decides what to cut, no longer compiles. Its output is
`overrides.yaml` plus `changes.md`, not a CV.

The skill therefore **moves into the repo** (`.claude/skills/`), because it is
now bound to a contract — the `overrides.yaml` schema, profile names, gate
behaviour — and a global skill would drift from it on the first renderer
change. Reviewed after analysing 29 real tailored applications on 2026-09-05;
see `research.md`.

**D35. Its `Never fabricate` is an instruction to a model, not a check.** A
deterministic fact gate modelled on career-ops' `verify-cv-facts.mjs` is
added: claims of type `employer`, `title`, `tool` and metrics, checked
against the master.

**D36. The gate is wired into the PDF build**, not a separate step. No PDF
exists without passing it. Human approval comes after the gate, not instead
of it.

**D37. The extractor is symmetric.** The same code runs over the document and
over the source, so widening a pattern can only add claims on both sides — it
cannot hide a fabrication by construction.

**D38. No model inside the gate.** An LLM entailment check was rejected: a
deterministic check does not rubber-stamp its own output.

**D39. Atomizing the profile is NOT required.** The gate compares text to
text, so per-bullet `ref` links into the profile are unnecessary.

**D40. The gate is a boundary, not a ban.** Earlier this said "wire the gate
into `tailor-cv`", which no longer describes anything: the renderer is ours
and the gate lives in it.

The rule is not "do not rewrite" but **"rewrite freely, and no new employer,
title, technology or number will appear"** — enforced mechanically rather than
promised. Inside that envelope the agent may reword a bullet, merge two, or
append the JD's own framing to an existing fact.

This replaces an earlier, stricter proposal to forbid bullet rewriting
outright. That proposal answered a misdiagnosis: a first pass suggested the
skill was rewriting most bullets and inventing skills, but it had compared
against a master profile that had itself changed in the meantime. The skill's
own contemporaneous logs show prose rewriting in 9 of 29 applications, with
selection, ordering and layout dominating — and an explicit self-audit that no
employer, title, date, metric or technology was added.

**D40a. Reframed bullets are checked against their declared source, not the
whole master.** An override names the bullets it derives from; its claims must
be a subset of theirs. Checking against the whole master would let a metric
from one employer migrate into another employer's bullet. This is stricter
than career-ops' whole-document comparison, and right for this use.

**D70. Two artifacts per application: what changed, and what was missing.**
`tailoring.yaml` records the first, `coverage.yaml` the second — both
structured, because prose in `changes.md` cannot be joined to an outcome
later.

`coverage.yaml` lists each JD requirement with `weight` (required/preferred),
`status` (covered/partial/missing) and `evidence` pointing at master ids, so
a claim of coverage is checkable rather than asserted.

**The reason to record it from day one is the analysis that needs no
outcomes:** aggregating `missing` across applications answers "what does the
market want that I do not have", the unit of observation is a requirement
rather than an application, and it therefore works at this volume — unlike
almost everything else in WF7.

Two further uses, in descending strength: which specific missing requirement
precedes rejection (unit = requirement, hundreds of observations); and whether
a higher covered share yields more interviews (unit = application, one
predictor against ~15 events — only a large effect would show).

**Join gaps to rejection latency, not just to the fact of rejection.** A
missing visa, location or years-of-experience is a knockout filter and rejects
within a day; a missing technology is a human judgement and rejects over
weeks. Different gaps, different remedies.

**Confounder, stated up front:** you apply where you partly match, so
"X missing -> rejected" can simply mean "harder roles reject more". Controlled
with `radar_score` and comparisons within similar roles.

**D72. The PDF must survive being read back.** After compiling, the text is
extracted with `pdftotext` and compared against what was rendered: every
token must reappear, no ligature glyphs, contact details present, section
order unchanged. Failure blocks the PDF (exit 4).

The mechanism this protects is retrieval. Recruiters do not read every
application — they run keyword searches and read the top of the results, and
boolean search matches exact strings. A term that does not extract is
invisible however prominent it looks on the page, and nothing errors.

**The ligature scan is raw, not inferred from lost tokens.** Our tokeniser
NFKC-normalises, so "workﬂows" compares equal to "workflows" and nothing
registers as lost — while an ATS parser that does not normalise leaves the
term unsearchable. A check that reports success in exactly the failing case
is worse than no check.

**A real ATS was considered and rejected.** Greenhouse and Workday parse with
their own engines and expose no candidate-facing API; the only way to observe
their parsing is to submit test applications to real employers, which
pollutes their pipelines and burns companies worth applying to. Passing this
check is necessary, not sufficient — `pdftotext` is not their parser.

It passes today on the current LaTeX toolchain, which makes it a regression
guard rather than a fix: it earns its place the day a font, template or engine
changes.

**D73. The minimum viable WF2 is a check over `tailor-cv`, not a replacement
for it.** Decided 2026-09-05, reversing the direction of the block.

`tailor-cv` works and is in use. Rebuilding what it does — a renderer, a
structured master, per-application overrides, aliases, section handling — is
most of the complexity in WF2, and its unique value is reproducibility and a
design that does not drift. Both matter on a long search; neither is worth
waiting for on a short one.

The checks, however, do not need any of it. They take a finished PDF and the
master profile, so nothing has to know what produced the document.

`jam check <pdf|dir>` answers three questions: does it claim anything the
master does not hold, does its text come back out, is it the length it should
be. Everything it flags is a question rather than a verdict — the answer is
usually "true, so put it in the master" or "not true, so take it out".

**Reading the PDF rather than the source removes a whole class of defect.**
The three false-positive classes hit during implementation — skill names
living in master keys, layout parameters read as content, template words read
as claims — all came from turning YAML into LaTeX and back. A PDF holds
exactly what a person and a parser see.

**Noise is the thing that decides whether a check is used.** Run over 29 real
applications it first reported around fifteen findings each, most of them
ordinary words capitalised in a skills line. A check nobody reads is worse
than none, so ordinary English words are filtered by the system word list —
while acronyms, mixed-case names, anything with a digit, and a list of
technology names that collide with English words (kafka, snowflake, spark,
delta, etl) always survive. Hiding a real technology is the one failure this
cannot have.

The renderer stays in the tree, tested and working, for whenever the search
turns out to be long.

**D74. `jam apply <app_id>` is the join between the two halves, and it is a
command rather than a printed string.** Decided 2026-09-08.

The deterministic half ended by printing `/apply <app_id>` for someone to
retype in a Claude session, and the skill began by assuming a CV existed.
Nothing checked that it did. A tailoring that failed, a `cv.tex` edited after
the last build, a two-page PDF — all of them reached a form, and the human
attached a CV that had never passed.

`jam apply` does the checking and then hands over the terminal: it tailors
what is missing, recompiles what is there, refuses to go on unless the stage
reads `ready`, and only then `execvp`s into the session that fills the form.
One command reaches every stage, so the screens name it whatever an
application is short of.

What it does not do is fill the form. `jam` has no browser, and the human is
the only Submit point (D9); adding browser tools to the headless agent would
put both halves of that on one side of the line.

**D75. A tailoring is not finished until all three files exist.** A `cv.tex`
with no `coverage.yaml` beside it recompiles to a clean pass, and a clean
pass is exactly what it must not report: the honest-gaps record is the half
of an application that survives it, and `jam gaps` is built on the assumption
that a missing record means an application nobody made, not one whose agent
died halfway.

So `cv.tex`, `coverage.yaml` and `changes.md` are checked together, and any
of them absent re-runs the tailoring rather than the compiler.

**D76. Anything that runs for minutes streams.** The agent was invoked with
`--output-format json` and captured whole, so a tailoring was five minutes of
silence followed by one paragraph. When it failed, that paragraph was all
there was, and the failure had to be reproduced to be read.

`stream-json` with a line per tool use costs nothing and makes the run
legible while it happens. On the command line it goes to the terminal; from a
screen it goes to `.tailor.log` (D77). Either way what the run was doing is
readable while it is doing it, which a spinner never is.

**D80. One agent per application, three in total.** Added 2026-09-08 after
checking, and finding neither.

Two agents writing one `cv.tex` is a CV neither of them wrote. The screens
guarded it and `jam tailor` did not, which mattered because `jam tailor` is
the command the background job itself runs. The marker names that job's own
pid, so the check is "a run exists whose pid is not mine" rather than "a run
exists" — otherwise the background job refuses itself.

The total is capped at three because taking eight vacancies out of the inbox
in one sitting is ordinary, and each is a Claude run and a LaTeX compile.
Starting eight is a machine nobody can use and a bill nobody chose. What is
held back is not lost: it is a folder with no CV yet, which is a stage the
screens already show and one key already fixes. A crashed agent does not hold
a place, because the count reaps as it reads (D77).

**D79. What the screens are allowed to say and do.** Settled 2026-09-08,
after a first attempt broke most of them.

Six rules, each of which came from getting it wrong:

**One command per stage.** Every screen names `jam apply <id>`, whatever the
application is short of — it tailors what is missing, rebuilds what is stale,
and only then opens the form. Naming a different command per stage made the
reader work out which half of the system they were in.

**One key does whatever is needed.** `b` writes the CV when there is none and
recompiles when there is. A second key for "start over" only differed from it
on a folder that was already finished, which is not a difference anyone can
read off a label; the rare case is a flag on the command line, where it costs
nothing.

**A label is true in every case it can happen, not the common one.**
"rebuild cv" was a lie in exactly the case that sends you looking for it.

**The same thing gets the same word everywhere.** `open posting`, `build cv`.
Two screens using two words for one action is two things to learn.

**Nothing takes the terminal from a screen.** An action runs between two
redraws, so it may not write to the terminal or take longer than a keystroke
should. Anything that does goes to the background and the screen reports on
it (D77).

**A screen rebuilds from the folder, never from what an action returned.**
The folder is the truth, and a background job changes it without going
through the screen at all.

**D78. `--allowed-tools` approves; it does not restrict.** Found 2026-09-08
while building link intake.

The intake agent is given a URL from the internet and asked what is on it, so
it was invoked with `--allowed-tools WebFetch` and documented as having that
and nothing else. It fetched the page with `Bash curl`. Denying `Bash` moved
it to another tool that runs commands.

What refuses is a `deny` rule passed through `--settings`, so
`agent.NO_SIDE_EFFECTS` names the tools that execute, write or reach other
systems, and any job that must not act is run with it.

It is a list of names, so it is only as good as the list — it narrows, it is
not a wall. The guarantee underneath it is structural: the intake agent's
whole output is one JSON object that is parsed in `hub/intake.py`, and
nothing it says reaches a file. The fact gate remains what a posting has to
get past to reach a PDF.

**D77. A tailoring runs in the background; a rebuild runs in place.**
Decided 2026-09-08, replacing a first attempt that ran both in the
foreground.

One key on the application screen does whatever the folder is short of, and
the two things it can do cost three orders of magnitude apart. Recompiling is
seconds and writes nothing to the terminal — latexmk and `pdftotext` both
capture their own output — so it happens between two redraws like any other
action. Writing a CV is minutes of an agent, and waiting for it meant the
screen went away for the whole of it: the one thing you could not do while an
application was being tailored was look at any of the others, which is the
reason to be on that screen at all.

So it is started and let go of. Two files in the application folder carry it:
`.tailoring` (pid and start time) and `.tailor.log` (everything it printed).
The stage reads `tailoring…` while it runs and the screens redraw on a timer,
so a row stops saying what was true when it opened.

Three things this has to get right, each of which is a way of being stuck:

- **The marker is reaped by whoever reads it, not by the child.** A process
  that crashed is exactly the one that will not have tidied up.
- **The worker is orphaned, not merely detached.** A child of the screen
  becomes a zombie when it exits, and a zombie answers `os.kill(pid, 0)` — a
  run that finished in a second read `tailoring…` until the marker went
  stale. It is backgrounded inside a shell that then exits, so it reparents
  onto init and its pid stops existing when it does.
- **An old marker is dead however alive its pid looks**, because pids are
  recycled. Thirty minutes, against an agent timeout of fifteen.

The background job is `jam tailor <app_id>` — the command anyone would type,
not a second code path that can behave differently from the one used by hand.
`jam apply` still runs it in the foreground, because a command line is where
waiting is the right behaviour.

---

## Master and CV versions

**D41. One master, structured** — `master-profile.yaml`. Prose, dates, skills
with start dates, awkward form fields. There is no second master.

**D42. The CV is rendered through a template — LaTeX, not Typst.** Revised
2026-09-04 at implementation: Typst is not installed, `latexmk` is, and the
existing `resume.cls` already carries a design that was approved. Rebuilding
typography for a different engine buys nothing — the requirement was
"rendered from structured data", not a particular engine.

Consequence: `templates/` lives in the **repo**, not under `data/`. The
earlier layout put it in `data/`, which is never versioned (D56) — losing the
CV template to our own privacy rule would be absurd.

**D43. No fixed CV versions. Tailoring is per application.** Reversed on
2026-09-05.

A fixed set of 3-5 render profiles existed to keep `cv_version` usable as an
analytics dimension. But a verdict on a version needs 30 submissions *per
version*, and at 60-150 applications no more than one would ever get there —
the same arithmetic that killed A/B testing on positioning (D4). The dimension
being defended could only ever have reported "not enough data".

What diagnoses the CV instead is the funnel wall, which needs no versions at
all: "12 of 19 died before a first reply" is a signal about the CV and the
positioning however many variants produced them.

So `versions/` is gone. Each application carries its own
`tailoring.yaml` — sections, `drop`, `emphasis`, `max_pages`, aliases, bullet
overrides — self-contained, starting from the bare master every time. No
shared default set of drops: a default would quietly become the fixed version
set this decision removes.

`cv_version` survives only as **provenance** — a pointer to or hash of that
file, answering "what exactly went out" without posing as a grouping.

Consequence: **the gate matters more, not less.** Structure used to be
constrained by the profile; now nothing constrains it except the fact gate and
`max_pages`.

The detector loses its "dead CV version" check.

**D44. The fact gate checks rendered text against the master** flattened to
plain text. Rephrasing for a JD does not change the claims.

**D45. Rejected:** keeping `.tex` as the master with YAML only for forms.
Dates and companies would then live in two places and need a sync check.

---

## Logs

**D46. The `source` vocabulary and retraction.** `email`, `portal`, `manual`,
`correction` (replaces an earlier record with the same `(app_id, to)`),
`backfill`. `from: null` means the prior state is unknown; `to: null` is a
retraction and nothing is deleted.

**D47. Backfilled records take no part in latency computation.** A date
written after the fact is not an observation of time.

**D48. Sample floors in the detector's report.** No comparative claims below
~20 submitted; no median for a transition with fewer than 3 completed
measurements; medians report right censoring — otherwise, with high ghosting,
they are systematically optimistic.

---

## Relationship to career-ops

**D49. We write our own; career-ops is a reference.** Forking was rejected:
the project is not built for the UK market. We take algorithms and edge cases,
not the codebase. MIT, so porting is allowed with attribution.

**D50. Port to Python, do not embed Node.** The core is already Python +
DuckDB.

**D51. Tests are ported along with the logic — and they matter more.** The
edge cases there are encoded in `--self-test` and `*.test.mjs`.

**D52. Parity is proven with golden fixtures.** The original scripts still
run: execute them, capture the outputs, keep them as fixtures.

**D53. Read the implementation, not the header.** `set-status.mjs` does not
contain the correction logic even though the format is documented in
`funnel-velocity.mjs`'s header.

**D54. A regex trap when porting.** The patterns use `\p{L}` and `\p{N}` with
the `u` flag; Python's `re` does not support that — the `regex` package is
required. A bug of exactly this class already happened there.

**D55. Attribution in the ported file's docstring:** source, commit, MIT.

**D71. Documentation uses a fictional persona, never the real profile.**
The repository is public; the data it drives is not. Examples use an invented
US software engineer — Jordan Reyes, Austin TX — at the standard fictional
companies `Northwind Systems`, `Contoso` and `Fabrikam`, with ids
`northwind`, `contoso`, `fabrikam`.

This is not only about privacy. Real employers in a general-purpose project's
schemas read as though the tool were built for one person, and an example that
happens to be true invites copying a fact instead of the shape.

The same applies to code: identity belongs in `master-profile.yaml`, never in
a renderer or a test fixture.

---

## Privacy

**D56. `data/` never enters git.** The repo keeps only the skeleton. The rule
is made mechanical: a pre-commit hook rejects anything under `data/` in
staged, so `git add -f` will not work. Accepted consequence: there is no
history or rollback for the data; backups are the OS's job.

**D57. Secrets in `.env`**, `.env` in `.gitignore`, `.env.example` in the
repo.

**D58. Bounded also applies to how much data leaves the machine.** What goes
to the model is not a mailbox but a single candidate: sender, subject, first
N characters. The Gmail query is narrow, access is read-only.

**D59. `contacts.tsv` is other people's personal data.** Do not publish, do
not sync, delete once the search is over. The rest of the history stays.

**D60. Telegram gets numbers only.** No company names: it is someone else's
server and a chat history on a phone. Vacancies that job-radar pushes to
INBOX are existing practice and do not change; this is about submissions.

**D61. `jd.md` is someone else's text.** Fine to keep privately, not to
publish.

**D62. Mac→Pi channel: Cloudflare Tunnel, Access service token.** An
unauthenticated request never reaches the Pi — it is cut off at the edge. No
authentication logic appears on the Pi, and the token can be revoked without
a redeploy. The endpoint accepts a date and nothing else.

**D63. A silent watchdog failure is worse than no watchdog** — because it is
relied upon. So the digest shows "last ping accepted by the Pi: 04.09".
