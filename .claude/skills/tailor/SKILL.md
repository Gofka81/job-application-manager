---
name: tailor
description: Tailor the CV to a specific vacancy in this repo. Reads the JD, records what it asks for against the master profile, writes the tailoring plan, and renders through the gates. Use when applying to a job, tailoring a CV to a job description, or preparing application materials.
---

# Tailor an application

You supply the judgement. The repository supplies the enforcement.

Your output is **decisions written to files**: `coverage.yaml`,
`tailoring.yaml`, `changes.md`. Never a PDF, and never an edit to the master. `jam` renders and
checks; if a check fails, fix the decision, not the check.

## What you must never do

- **Never edit `data/master-profile.yaml`.** If the vacancy wants something true
  that the master lacks, say so in `changes.md` and ask. Adding it yourself
  turns a gap into a claim nobody verified.
- **Never write `cv.tex` or `cv.pdf`.** `jam render` does that.
- **Never invent.** No employer, title, date, technology or number may appear
  that the master does not hold. The fact gate enforces this, but arriving at
  the gate with a fabrication already means the reasoning went wrong.
- **Never weaken a check to make it pass.** Not `factgate.allow` in
  `config.yaml`, not the gate code. A failing gate is information.

## Steps

### 1. Locate the application

The folder is `data/applications/<app_id>/`, where `app_id` is
`YYYY-MM-DD--company-slug--role-slug` using the **submission** date. It should
hold `jd.md`. If the JD is missing, ask for the full posting text and save it
there verbatim first. A snippet is not enough to judge coverage.

### 2. Read the JD and record coverage

Extract every requirement, separating what the posting **requires** from what
it **prefers**. Write `coverage.yaml`:

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

`evidence` holds ids from the master: `<entry id>.<bullet index>` (0-based),
`skills.<key>`, `education.<id>`, `certifications.<index>`. A `covered` or
`partial` requirement **must** cite evidence; a `missing` one must not.

Be honest about `missing`. Aggregated across applications this is the one
analysis in the project that works at low volume, because its unit is a
requirement rather than an application, and it answers what to learn next. A
`partial` marked `covered` corrupts that permanently.

Check it: `jam coverage --app <app_id>`.

### 3. Write the tailoring plan

`tailoring.yaml` in the same folder:

```yaml
max_pages: 1
drop: [contoso.1, fabrikam.2, kotlin, scala]
emphasis: [databricks, pyspark, aws]
bullets:
  northwind.1:
    from: [northwind.1]
    text: "Developed proactive data quality and reconciliation controls…"
  northwind.merged:
    from: [northwind.0, northwind.2]
    text: "…"
```

- `drop` takes a section name, an entry id, a single bullet as
  `<id>.<index>`, or a skill key.
- `emphasis` reorders skills only; it cannot introduce one.
- `bullets` are rewordings and merges. **`from` is mandatory and is what the
  gate checks against.** An override is verified against those bullets alone,
  never the whole master, so a metric belonging to one employer cannot appear
  in another's. A merge lists several sources, takes the position of the
  earliest, and the rest drop out. Sources must belong to the same entry.

Reword to use the vacancy's vocabulary where it is truthful. Framing language
layered onto a real fact is fine. "Ensuring reliable delivery" on top of real
data-quality work is what anyone writing their own CV does. A new noun or
number is not.

For a skill the market spells several ways, prefer declaring `aliases` in the
master over rewording per application. The renderer then prints whichever
form the JD uses, for every future application at once. Ask before adding
them; that is a master edit.

### 4. Render

```
jam render --app <app_id>
```

It resolves aliases against `jd.md`, applies the plan, and runs three checks
before the PDF exists.

| exit | meaning | what to do |
|---|---|---|
| 0 | done | review the PDF |
| 1 | malformed input | usually an override missing `from`, or evidence naming an id that is not in the master |
| 2 | over the page budget | cut content via `drop`; do not shrink margins, the design is fixed |
| 3 | fact gate | a claim is not in its source. Remove it, or ask whether it is true and belongs in the master |
| 4 | extraction | a term did not survive `pdftotext`, so a recruiter's keyword search would not find it |

### 5. Write `changes.md`

For the human, not for the machine:

- **Requirement → coverage**, mirroring `coverage.yaml` in prose.
- **Changes made**, honestly: what was dropped, reordered, merged, reworded.
- **Honest gaps**: what the vacancy wants that the master genuinely lacks.
  Never soften this. It is the most useful thing in the file.
- **Judgement**: anything the numbers do not show. A posting that reads as a
  different role than its title, an unusual emphasis.

## Rules

`references/tailoring-principles.md`. Read it before writing anything.
