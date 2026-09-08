---
name: tailor
description: Tailor the CV to a vacancy already taken into this repo. Reads the application's JD, records what it asks for against the master, produces the CV, and runs it through the checks. Use after `jam take`, or when asked to tailor a CV, prepare application materials, or apply to a job in this repository.
---

# Tailor an application

The vacancy is already in `data/applications/<app_id>/` with `jd.md` and
`application.json`. If it is not, start from `jam inbox`.

You supply the judgement. `jam` supplies the enforcement: a claim that is not
in the master profile does not reach a PDF.

## Never

- **Never edit `data/master-profile.yaml`.** If the vacancy wants something
  true that the master lacks, say so and ask. Adding it yourself turns a gap
  nobody verified into a claim.
- **Never invent.** No employer, title, date, technology or number that the
  master does not hold.
- **Never weaken a check to make it pass** — not `factgate.allow` in
  `config.yaml`, not the code. A failing check is information, and widening
  the allow list is the cheapest way to lose it.

## Steps

### 1. Read the vacancy

`data/applications/<app_id>/jd.md`. If it says the radar held no text, open
the posting and paste the real thing in first — coverage judged from a snippet
is guesswork.

### 2. Record coverage

Every requirement, separating what the posting **requires** from what it
**prefers**, into `coverage.yaml` beside the JD:

```yaml
requirements:
  - text: "5+ years building data pipelines"
    weight: required          # required | preferred
    status: covered           # covered | partial | missing
    evidence: [northwind.2, skills.python]
  - text: "dbt"
    weight: required
    status: missing
    evidence: []
```

`evidence` holds master ids: `<entry id>.<bullet index>` (0-based),
`skills.<key>`, `education.<id>`, `certifications.<index>`. Covered and
partial must cite evidence; missing must not.

Be honest about `missing`. Aggregated across applications this is the only
analysis in the project that works at low volume, because its unit is a
requirement rather than an application — `jam gaps` is how you find out what
to learn next. Marking a partial as covered corrupts that permanently.

Check it: `jam coverage --app <app_id>`.

### 3. Produce the CV

Work in the application folder, never in `data/master/`:

```sh
cp data/master/cv.tex data/master/resume.cls data/applications/<app_id>/
# edit data/applications/<app_id>/cv.tex
jam build <app_id>
```

`jam build` compiles the folder's own `cv.tex` and runs the checks on what
came out, so a rebuild cannot leave a PDF that no longer passes. Editing and
re-running it is the normal loop; the CV that runs to two pages gets cut and
built again until it does not.

What you may change, in the order that pays:

- **Order.** Lead with what this vacancy asks for. This costs nothing and is
  most of the effect.
- **Length.** Cut what is irrelevant to this role to make room. One page
  unless the master is longer.
- **Wording.** Reword a real bullet in the vacancy's own terms where it is
  truthful. A recruiter's search matches exact strings and does not expand
  synonyms: if the posting says `ETL` and the CV says "data pipelines", the
  search will not find it.
- **Merging.** Two real bullets can become one where the vacancy names both.

Framing language layered onto a real fact is fine — "ensuring reliable
delivery" on top of real data-quality work is what anyone writing their own CV
does. A new noun or number is not.

Do not touch margins, spacing or the class file. The design is fixed so every
application looks like it came from the same person; if it does not fit, cut
content.

### 4. Check it

`jam build` already ran this. To re-check a PDF without rebuilding:

```
jam check data/applications/<app_id>/cv.pdf --max-pages 1
```

| it says | what happened | what to do |
|---|---|---|
| not in the master | a claim has no source | remove it, or ask whether it is true and belongs in the master |
| numbers not in the master | a figure was changed or invented | put the master's figure back |
| ligature glyphs | a term will not survive a recruiter's search | fix the font or the wording |
| no text extracted | the PDF is not selectable | rebuild it |
| pages, budget is 1 | too long | cut content, never margins |

Findings are questions, not verdicts. The answer is usually either "true, so
it belongs in the master" or "not true, so it comes out of the CV".

### 5. Write `changes.md`

For the human:

- **Requirement → coverage**, mirroring `coverage.yaml` in prose.
- **Changes made** — what was dropped, reordered, merged, reworded.
- **Honest gaps** — what the vacancy wants that the master genuinely lacks.
  Never soften this. It is the most useful thing in the file.
- **Judgement** — anything the numbers do not show: a posting that reads as a
  different role than its title, an unusual emphasis.

## Then

`jam apply <app_id>` fills the form. It re-checks what you built before it
opens anything, so a CV that stopped passing after your last edit does not
reach a posting. You do not submit; the human does.

## Why the honest gaps matter more than the CV

`jam gaps` aggregates the `missing` lines from every application, and it is
the one analysis in the project that works at this volume: its unit is a
requirement, and there are hundreds of those, while there are only ever tens
of applications. It is how the next thing to learn gets decided.

That only holds if `missing` means missing. Marking a partial as covered to
make a CV look better corrupts the one number that was going to be reliable.

## Rules

`references/tailoring-principles.md`. Read it before writing anything.
