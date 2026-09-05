# Workflows

For each WF: what it does, what is settled, what is still open.
Decision numbers link to [`decisions.md`](decisions.md).

---

## WF1 · job-radar

**Where:** Raspberry Pi, Docker, public through a Cloudflare Tunnel.
**Status: implemented and running**, the vacancy flow is sufficient.

10 sources through official APIs (vacancy plus `posted_at`) → normalize,
dedup, filter by freshness and criteria → bounded LLM triage `fit 0-10` with
a reason → SQL job-radar → INBOX.

The **watchdog** lives here too (D23) — a separate thing from the radar,
holding a single number: the date of the last submission.

**Open:** no review has been done. Checklist for when it comes up — silent
source degradation (zero results read as "a quiet market"), invisible false
negatives from filters, uncalibrated triage. The repost detector is in
[`todo.md`](../todo.md).

---

## WF2 · materials

**In:** the dossier from intake (`app_id`, `jd.md`, company, role).
**Out:** `cv.pdf`, `cover.pdf`, `changes.md`, `tailoring.yaml` (what changed)
and `coverage.yaml` (what was missing) in the application folder.

### The flow

```
1. COVERAGE          agent    JD requirements -> what the master covers
                              -> coverage.yaml (structured) + changes.md
2. TAILORING PLAN    agent    what to drop, what to lead with, page budget
                              -> tailoring.yaml, from the bare master
3. ALIASES           det.     SKILLS terms swapped to the JD's wording
                              (ETL vs Data Pipelines) — dictionary, no model
4. REFRAME           agent    may reword a bullet, merge two, append the JD's
                     BOUNDED  framing -> overrides.yaml
5. RENDER            det.     master + profile + aliases + overrides -> .tex
6. FACT GATE         det.     BLOCKS the PDF -- no invented fact
7. ATS CHECK         det.     BLOCKS the PDF -- every term survives extraction
8. MAX_PAGES         det.     BLOCKS the PDF
9. APPROVAL          human
10. COVER LETTER     agent    -> the same gates
```

Steps 5, 6, 7 and 8 exist today (`jam render --app <id>`). Steps 1, 3, 4
and 10 are not built.

### Where reframing lives

The master is never edited, so per-application wording needs its own file:

```yaml
# data/applications/<app_id>/tailoring.yaml
max_pages: 1
drop: [contoso.1, fabrikam.2, kotlin, scala]
emphasis: [databricks, pyspark, aws]
bullets:
  northwind.1:
    from: [northwind.1]
    text: "Developed proactive data quality and reconciliation controls…"
  northwind.merged:
    from: [northwind.0, northwind.2]     # two bullets merged into one
    text: "…"
```

`from` is not documentation — it is what the gate checks against (D40a).

### What each gate is for

| gate | catches | does not catch |
|---|---|---|
| fact gate | a new employer, title, technology or number | framing language — deliberately |
| ats check | terms lost in extraction, ligatures, scrambled reading order | whether a real ATS parses it well |
| max_pages | layout | — |
| human | sense and tone | anything they have stopped reading by the 50th application |

The framing is deliberate: not "do not rewrite" but **"rewrite, and no new
fact will appear"** (D40).

### Aliases apply to SKILLS only

Bullets come verbatim from the master or from `overrides`. Substituting
synonyms into agent-written prose would corrupt it, and the boolean-search
benefit lives in the skills line anyway — recruiter search matches exact
strings and does not expand synonyms.

### There are no CV versions

Every application is tailored from the bare master (D43). `cv_version` is
kept only as provenance — a pointer to that application's `tailoring.yaml`.

The detector therefore has no "dead CV version" check. What diagnoses the CV
is the funnel wall: where applications die, not which variant produced them.

### What `tailor-cv` becomes

It stops producing the CV and starts producing the decisions the deterministic
renderer consumes: `overrides.yaml` plus `changes.md`. It moves into the repo
because it is now bound to a contract (D34).

## WF3 · submission

**Boundaries (D0):** starts once WF2 has produced the files, ends at a
confirmed Submit. Writing the application record is already WF4. Positioning
and version choice do not belong here.

The agent fills the form in the browser (D6) → STOP → the human clicks Submit.

**Settled:** filling is done by an agent, not scripted automation over
selectors, so there is no brittleness against markup changes. The residual
risk is a different one — non-determinism: a plausible but wrong answer. So
STOP shows a **list of fields with values, with agent-inferred ones
highlighted** (D7), and awkward fields sit in the profile in advance (D8).
`application.json` is created after Submit is confirmed, never before (D9).

The **answer bank** is consumed by WF3 but not owned by it — it is an asset.
Questions are asked in a batch per page, not field by field. Matching is
asymmetric: a confident match fills, any doubt asks.

---

## WF4 · tracking

**Two halves, very different in difficulty.**

**Writing the submission** is automatic, a side effect of intake. Forgetting
it is impossible.

**Capturing the outcome** is three layers, each covering the previous one's
gap:

1. **Gmail** — the main stream. Matching runs against the **closed list** of
   your own applications (D18), not open-world extraction from the email
   body. Classification is allowed to say `unclear` (D19). Write asymmetry
   (D31): automation writes what a human would forget — acknowledgements and
   rejections; it asks about what the human would notice anyway — a human
   reply and an offer.
2. **A weekly sweep** of open applications — whatever bypassed email:
   portals, phone calls, LinkedIn.
3. **Aging** — `ghosted` is computed (D14), never written. This guarantees no
   application is left without an ending.

Status is a fold of `status.jsonl`, not a field. The vocabulary is six
values (D29).

---

## WF5 · interviews

**The main artifact is the prep sheet** (D64): one page before a round.
5 facts about the company, 5 stories matched to this JD and round type, the
weak spots that fire on this round type specifically, your questions for
them, and where the application stands.

The constraint matters more than the contents: one page. Mini-research is a
classic rabbit hole. Generated on demand (D65, provisional).

**The debrief** (D11) — three questions plus a prediction, the same day:

1. Which answer was my worst?
2. What surprised me, what was I not ready for?
3. Which story landed?
4. Prediction in one word: pass / fail / no idea

The prediction provides **calibration** — one of only two things in the
system measurable at small volumes, because the unit of observation here is
a round, not an application.

**The story bank is structured for retrieval** (D66): competency,
technologies, scale, raw text. The **question bank** (D67) is a separate
asset, filled by weekly curation. A weak spot from a single interview is a
hypothesis; only what repeats twice reaches the file (D12).

`rounds.jsonl` steers preparation focus (D68): once it shows which round type
applications die on, the prep sheet weights toward it.

**Not doing** (D69): calendar and round scheduling, mock interviews.

---

## WF6 · follow-up

Aging sees anything `stale` beyond `stale_days` → queue → the human sends
manually.

**Hard caps** (D10): no more than 2 touches per company, at least 10 days
apart, a full stop after an explicit rejection. Aging makes reminders cheap,
and without caps that slides into pestering. **The cap is a property of the
engine, not self-discipline.**

What gets recorded is **delivery**, not sending: guessed addresses produce
bounces that would otherwise look like sent emails in the log.

**Open:** the actual thresholds. `stale_days` 21 is a provisional number.

---

## WF7 · analytics

**A catastrophe detector, not an optimizer.** An optimizer asks "which is
better?" and needs ~400 applications. A detector asks "is anything definitely
broken?" — and by the rule of three, 30 is enough.

**What it catches:** a dead channel (0 replies over 30+), a dead CV version,
a wall in the funnel (*where* applications die is more informative than how
many), a rotting denominator, volume, sample drift, time to response.

**What will never be available:** "version B is 15% better". The right
response is not to gather more data but to stop asking the question.

**Three rules:** thresholds are set in advance; the output is a verdict, not
a dashboard; rates are never shown without n.

**`not enough data` is a first-class output**, not an empty result. Sample
floors (D48): no comparative claims below ~20 submitted; no median for a
transition with fewer than 3 completed measurements; medians report right
censoring.

Ghost rate and rejection rate are separate metrics (D17): "40% rejected" and
"40% silent" are different diagnoses.

**Sampling** (D1-D5): `role_archetype`, a guard metric alongside conversion,
`filter_version`, positioning is not A/B tested, range restriction is not
treated.
