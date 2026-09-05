# todo — important, but not now

A parking lot for topics that affect the architecture but do not block work
right now. Each entry: what it is, why not now, and what should bring it back.

---

## WF1 · repost detector

**What it is.** Vacancy freshness currently comes from `posted_at` in the
API. The weak point: companies re-list the same vacancy with a new date. To
`scan/dedup` that looks like a new, fresh position — it passes the freshness
filter again and goes through triage into INBOX again.

**What to do when it comes up.** Dedup on a stable fingerprint rather than
the source's `job_id`: `company + normalized_title + hash(JD)`. Keep
`first_seen_at` separate from `posted_at` in the job-radar SQL and measure
freshness from `first_seen_at`. Mark a reappearance as a `repost` with a
counter instead of a new vacancy. Side benefit: `repost_count` is a signal in
itself — a position that hangs around for months is either a hard
requirement or a ghost posting.

**Why not now.** Volume is still low and duplicates are visible by eye. The
cost of the error is an extra row in INBOX, not a missed opportunity.

**What brings it back.** INBOX regularly showing positions already seen and
deliberately skipped. Or triage starting to burn a noticeable budget on
repeats.

**Do not start from scratch.** career-ops has `detect-reposts.mjs` (MIT,
locally at `~/Developer/DataEng/career-ops`). Not read yet, but that is where
to start. See `docs/research.md`.

---

## Positioning · how many focuses to run

**What it is.** A focus (Data Platform / Analytics / ML Data Engineer)
determines the LinkedIn headline, the CV emphasis and the set of vacancies
themselves. A LinkedIn headline can only be one thing — that is a hard
constraint, not a statistical one.

**What to decide when it comes up.** How many focuses to run at once, and
whether they are genuinely different. If the vacancy overlap is large, it is
one focus with CV variants and the arithmetic below is unnecessary.

**The arithmetic if there are several.** A "dead" verdict needs 30
submissions per focus (rule of three: 0 out of 30 → rate below 10%). Three
focuses split evenly = 90 submissions before the first conclusion, i.e. ~2.5
months at 8-10 submissions a week. One primary focus = a verdict in 3-4
weeks. Proposal: one primary, with LinkedIn tuned to it and 70-80% of
submissions; the rest opportunistic — applied to but not measured, via a
`focus_track: primary | opportunistic` field.

**Why not now.** Submitting has to become cheap first — without volume there
is nothing to measure. And the focuses are not named yet.

**What brings it back.** Once intake works and submissions start flowing. Or
when the LinkedIn headline is up for a rewrite.

---

## WF2 · lexical alignment to the JD (open, decide next)

**The instinct.** `tailor-cv` swapped wording for the exact terms used in the
vacancy, and that felt like it converted. Worth taking seriously.

**Why the mechanism is real.** Research on 2026-09-04 found the "ATS
auto-rejects on keywords" premise to be largely false — 92% of surveyed
recruiters say their systems do not auto-reject, and Greenhouse does not rank
by algorithm at all. What actually happens: 400-2000 applicants per role, and
recruiters run keyword searches over the database and read the top of the
results. **Boolean search matches exact strings and does not expand
synonyms** — so `AND "ETL"` will not return a CV that says "data pipelines".

That makes exact-term alignment a real retrieval mechanism. It is also the
safest kind of tailoring: lexical, not factual. Company, title, technology
and metrics stay identical, so the fact gate passes it by construction.

**What the research does NOT support.** Ordering within the skills line —
no mechanism, no evidence. And vendor tailoring statistics (Huntr +115%,
Teal 6x) are self-selected users of tailoring products; the same
sample-composition confounder `radar_score` exists to control.

**The one causal result found.** Wiles, Munyikwa & Horton (NBER, n=480,948):
randomized algorithmic writing assistance — grammar, style, spelling —
raised hires by +7.8%, with applicant behaviour unchanged. Effect largest for
non-native English writers. Suggests a one-off pass over the master's prose
is better evidenced than any per-application rewriting.

**The tension to resolve.** Per-application rewriting reintroduces the
`cv_version` cardinality problem (D43) and costs time against volume — which
is the actual bottleneck. Options to weigh:

1. Lexical alignment as a per-application step, with `cv_version` still
   naming the underlying profile and the swap recorded separately.
2. A coverage report only (`jam coverage <jd>`) — pick the best-covering
   profile, flag true terms the profile dropped; no mutation.
3. Alias sets in the master (`spark_sql: [Spark SQL, SparkSQL]`) so a term
   is present in several forms without per-application work.

Option 3 is worth a look: it gets the retrieval benefit once, at build time,
with no per-application cost and no cardinality damage.

**Trigger.** Next working session — this blocks the shape of WF2.

---

## WF2 · cover letter (parked — needs a template first)

**Why it stopped.** An implementation was written and removed on 2026-09-05:
building a generic letter without knowing the writer's voice or what they want
in it produces something that will be redesigned anyway. It resumes when there
is a template and a brief.

**What is already settled, so it does not get re-derived:**

The letter goes through the same gates as the CV, with one difference in
scope. A letter legitimately names the company and the role, and neither is in
the master — so the allowed source is the master **plus `company` and `title`
from `application.json`**.

**The job description is deliberately not part of that source.** Admitting it
would let the letter claim any technology the vacancy happens to mention,
which is the exact failure the gate exists to prevent.

The letterhead date is generated rather than claimed, so its tokens are
exempt.

**What is needed to restart:** a LaTeX letter template, and a brief on what
the letter should contain and in what voice.
