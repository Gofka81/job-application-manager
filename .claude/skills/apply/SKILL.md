---
name: apply
description: Fill a job application form in the browser from the answer bank, stopping before Submit. Use after the CV is ready, or when asked to apply to a vacancy, fill an application form, or submit an application in this repository.
---

# Fill the form

The CV exists in `data/applications/<app_id>/` and the vacancy has a posting
URL in `application.json`. You fill what is known, ask about what is not, and
**stop**. The human uploads the CV and presses Submit.

Load the `claude-in-chrome` skill first; this needs the browser tools.

## The line you do not cross

**Never press Submit.** Not to "test the flow", not because the form looks
complete, not if asked in passing. The human is the only Submit point, and
that is the whole shape of the system rather than a preference.

**Never upload the CV file either.** The human attaches it. A file dialog is
where an automated fill quietly sends the wrong document.

**Never invent an answer.** If the bank has no answer and the human is not
here to give one, leave the field empty and say so at STOP. A plausible wrong
answer in a submitted application is invisible until an employer reads it.

## Steps

### 1. Open the posting

`source_url` from `application.json`. If it needs a login, say so and stop —
the human signs in, then you continue.

### 2. Per page, not per field

Read every question on the page first, then ask the bank once:

```
jam ask "Years of experience with SQL" "Do you require sponsorship?" --type integer
```

It answers with what it knows and lists what it does not:

```json
{
  "answered": {"Years of experience with SQL": {"slot": "sql_years", "value": "5"}},
  "unknown": ["Do you require sponsorship?"]
}
```

Use `--type` to match the field: `integer`, `number`, `text`, or `range` for
a dropdown. One stored answer serves every shape, so never reword a value
yourself — ask for the shape you need.

### 3. Ask about the rest in one batch

Put every unknown question to the human at once. Interrupting per field makes
this unbearable by the third application.

Record each answer so it is never asked again:

```
jam learn "Do you require sponsorship?" "No"
jam learn "Describe your experience with Databricks" "..." --reuse always
```

`--reuse never` for anything company-specific — "why do you want to work
here" must never be reused, or a paragraph about one employer eventually
reaches another.

If the question is a known one worded differently, attach it rather than
creating a slot:

```
jam learn "How many years of SQL?" "5" --slot sql_years
```

### 4. Fill, conservatively

A confident match fills the field. **Any doubt asks.** An extra question
costs ten seconds; a wrong answer costs the vacancy.

For anything the bank cannot answer and the human has not supplied, leave it
empty. Never guess a salary, a date, a visa status or a notice period.

### 5. STOP

Do not submit. Show the human, in this order:

1. **Every field you filled, with its value.** Not "the form is complete" —
   the actual values.
2. **Which ones you inferred rather than read from the bank**, marked. These
   are the ones worth reading; the rest they have seen before. Five marked
   fields get read even on the fiftieth application, a whole form does not.
3. **What is still empty**, and why.
4. **What they must do**: attach `data/applications/<app_id>/cv.pdf`, review,
   press Submit.

### 6. After they submit

Only once they confirm it went through:

```
jam submit <app_id>
```

That writes the journal entry that starts the aging clock, marks the vacancy
applied in job-radar, and pings the watchdog. Nothing else records a
submission, so an unrecorded one is invisible to every later count.

If they did not submit — closed the tab, changed their mind — record nothing.
A form that was filled is not an application that happened.
