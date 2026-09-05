# Project risks

Assessed per WF. Ordered by expected damage, not by execution order.

---

# 0. Meta-risk: the system competes with the job search

The goal is to find a job faster. But seven workflows are several weeks of
work, and those weeks are subtracted from submissions. The system pays off at
high volume; at low volume manual work wins.

**Symptom.** A week with no applications sent but with commits in the repo.

**What to do.** Order by data dependencies, not by WF number. WF1 already
works and feeds enough, so the count starts at submission.

**Block 1 — intake.** WF2 + WF3 + writing the record from WF4, together. Not
three stages but one path: link → dossier → agent fills → STOP → confirmed
Submit → record. Plus bootstrapping the answer bank before the first
submission. Splitting it makes no sense — value appears only when the path is
whole. It is also what produces the volume everything else needs.

**Block 2 — capturing outcomes.** The second half of WF4: reply-watch through
Gmail, a weekly sweep of open applications. Without outcomes in the log there
is no funnel, only a list of submissions.

**Block 3 — WF7, the detector.** Building it earlier is pointless: the first
verdict needs ~30 submissions, and before that the detector has nothing to
say.

**Block 4 — WF6.** Follow-up thresholds come from the distribution of
time-to-response, which does not exist before block 2.

**Block 5 — WF5.** Becomes relevant once interviews start.

The reverse order used to stand here, with WF3 last, on the assumption that
form filling meant scripted automation over selectors — expensive and
brittle. Since an agent fills the form in the browser, there is no
markup brittleness, and WF3 moved into the first block.

---

# 1. WF7 · analytics will not catch the signal

The main risk of the project. Analytics is what makes it valuable, and
analytics is what will most likely fail — not through bugs but through
statistics.

## How much data is actually needed

To reliably distinguish a 10% conversion from 20% (i.e. a CV twice as good)
takes **about 200 applications per group, 400 in total**. To distinguish 10%
from 30% — about 62 per group, 124 total.

A realistic search is 60-150 applications over three months. Which means:

- **A difference smaller than 2x will never be visible.** It physically
  drowns in noise.
- Splitting by channel × CV version gives 12 cells with 1-2 interviews each.
  That is not analytics, it is divination.

## The consequence that is worse than having no signal

At small n you will **always find a pattern**. It will be noise but will look
like insight. You will change the CV, the baseline resets, you accumulate
another 20 applications, find fresh noise, and go round again. Analytics
becomes not useless but **harmful**: it manufactures confidence without
information.

## What to do about it

**1. Few large changes instead of many small ones.** Budget: one change per
~30 applications. Small wording tweaks are unmeasurable by construction —
either make them without measuring, or do not make them.

**2. Measure higher up the funnel.** Interviews over three months will be
5-15 — not enough to compute even a rate. Replies of any kind, rejections
included, will be 30-60. A reply rate has a confidence interval of ±12pp at
n=60 — crude, but measurable. Interviews as a metric are unavailable; replies
are borderline.

**3. Time-to-first-response as the primary metric.** A continuous quantity
carries more information per observation than a binary one. A median shifting
from 12 days to 6 is visible on a sample where a rate shift is not.

**4. The decision rule is written BEFORE the change.** In
`decision-journal.md`, before changing anything: "I will consider this worked
if over the next 30 applications the reply rate is above X". Without it you
are fitting the story to the result.

**5. Ghosting is an outcome, not missing data.** The most common ending is
silence. If silence is not in the log, the funnel denominator keeps only
those who replied, and conversion is systematically inflated.

**6. Confounders that will ruin the before-after slice.** The market,
seasonality, your own improvement at interviewing, and above all **a change
in the vacancy sample**. If after a new CV you start applying to better
vacancies, conversion rises for the wrong reason. That is why `radar_score`
sits in `application.json` — to control the composition of the sample.

## The honest conclusion

At these volumes analytics is **a catastrophe detector, not an optimizer**.
It will reliably say "channel X produced zero replies across 40 applications"
and will never say "CV version B is 15% better". Design for the first
question.

---

# 2. WF4 · the status log will fall apart

Second in importance. All analytics rests on `status.jsonl` being complete,
and filling in statuses is manual work with no immediate payoff.

**The main risk is bias, not gaps.** You will always record an interview
invitation. A rejection, often. Silence, never. The data is skewed exactly
toward success, and conversion inside it is inflated.

**What to do.** Ghosting is computed by the aging engine, not recorded by
hand. Reply-watch through the Gmail API rather than pasting — pasting is a
daily manual act, and it will die within two weeks. The email classifier must
have an `unclear` status and must not guess.

---

# 3. WF2 · the CV generator

**Invented facts.** The most expensive mistake in the project: the model adds
something to the CV that never happened, and it goes to an employer. The
generator must only reorder and rephrase from `master-profile.yaml`, never
introduce new facts. A check is required: every claim in the CV maps to an
entry in the profile. Human approval is not a substitute — by the fiftieth
application nobody is really looking.

**CV version proliferation.** If the generator produces a unique CV per JD,
`cv_version` has cardinality equal to the number of applications and is dead
as an analytics dimension. A **fixed small set — 3-5 versions** — is needed,
with fine tailoring inside them. This is a constraint on WF2, not on
analytics.

**The ATS will not parse the PDF.** A silent failure: you will never find
out. Check by extracting the text from the finished PDF and reading it.

---

# 4. WF3 · the copilot and Submit

**Brittleness.** Workday, Greenhouse, Lever, Taleo are all different, and
Workday especially painful. Automation breaks on every redesign. The risk is
not that it will not work but that it will eat more time than it saves.

*(Largely resolved: an agent looking at the page does not break on markup —
see D6. What remains is non-determinism.)*

**Phantom applications.** The form is filled, the human never clicks Submit,
and `application.json` already exists. Such records corrupt the funnel
denominator. **The record must be created after submission is confirmed, not
before.**

**Habituation to the gate.** STOP before Submit works only while it is being
read. By the thirtieth application it becomes a click-through — and then it
is no longer a safeguard. The gate must show something that changes: the
specific fields and the file going out.

---

# 5. WF6 · follow-up

**Reputational.** The aging engine makes reminders cheap, and it is easy to
slide into pestering. Hard limits are needed: no more than two touches per
company, at least 10 days apart, a full stop after an explicit rejection.

**Contacts.** Real recruiter addresses are hard to obtain; guessed addresses
produce bounces that will look like sent emails in the log. Record delivery,
not sending.

**The effect is unmeasurable.** Same statistics as WF7. Follow-up will have
to rest on judgement rather than data.

---

# 6. WF5 · interviews

**A debrief is written immediately or never.** There is no energy after an
interview. Keep it to three questions, written the same day.

**The story bank overgrows.** In six months it becomes an unsearchable wall
of text. It needs a cap and periodic pruning.

**Weak spots from two interviews are not a pattern.** The same small-n trap,
only qualitative. Mark them as hypotheses, confirm by repetition.

---

# 7. WF1 · job-radar

> **Status: implemented and running**, the vacancy flow is sufficient.
> The feasibility risk below is empirically resolved. The remaining points
> stay as a review checklist for when it comes up.

**Public APIs barely exist.** LinkedIn offers no jobs API, Indeed closed
theirs. "10 sources through APIs" may in practice collapse to two or three,
with the rest being scraping, blocks and breakage. This is a feasibility
risk and should be checked before any code: how many sources genuinely have
access.

**Silent degradation.** A source stops returning results — the pipeline
reports zero new vacancies, and you read that as "a quiet market". Per-source
counters and an alert on zero are needed.

**Invisible false negatives.** Filters discard vacancies silently, so there
is no way to learn that they are too strict. Once a week, show a random
sample of what was discarded.

**Uncalibrated triage.** `fit 0-10` is anchored to nothing and will drift
between runs and model versions. Since `radar_score` lands in
`application.json`, the correlation between score and actual outcome can be
checked — the only way to learn whether triage is worth anything at all.

---

# 8. Cross-cutting

**Personal data in git.** `contacts.tsv` holds other people's names and
addresses; `jd.md` and the materials hold yours. Settled by D56: `data/`
never enters git.

**Fading once it succeeds.** You find a job and the system is abandoned
half-built. That is fine, even good — but it makes the implementation order
in section 0 critical: the first steps must pay off on their own.
