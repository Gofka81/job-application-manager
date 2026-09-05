# Tailoring principles

Binding rules for producing a job-tailored CV. Read before writing anything.

## Honesty (non-negotiable)

- **Only real content.** Every employer, title, date, degree, certification,
  metric and skill in the output must exist in the master profile. Never add
  one to fit the JD.
- **Rephrase, don't invent.** You may reword a real bullet in the JD's
  vocabulary, split or merge real bullets, and change emphasis. The
  underlying fact must stay true.
- **No metric inflation.** Don't add numbers the master lacks, and don't
  enlarge the ones it has. `70+` is not `100+`.
- **Surface gaps, don't paper over them.** If the vacancy requires something
  the candidate lacks, record it as `missing` and write it in `changes.md`.
  That is signal, not failure.
- **Ask when unsure** whether a claim is real, rather than guessing.

## Voice

- **No em dashes.** Use a comma, a full stop, or restructure the sentence.
  They read as machine-written, and a CV that reads as machine-written invites
  the reader to discount everything in it. This applies to anything you write:
  reworded bullets, `changes.md`, cover letters.
- **No em dashes in the master either.** If one is already there, leave the
  master alone and ask, because it is not yours to edit, but do not carry the
  style into new wording.
- Plain declarative sentences. No "leveraged", "spearheaded", "passionate
  about", "proven track record". They say nothing and cost a line.
- Lead a bullet with the verb and the object, not with a framing clause.

## Relevance and emphasis

- Lead with what this vacancy prioritises. Reorder bullets and skills so the
  most relevant appear first.
- **Mirror the vacancy's exact terms where truthful.** A recruiter's search
  matches exact strings and does not expand synonyms: a search for `ETL` will
  not return a CV that says "Data Pipelines". Prefer declaring the alternative
  spelling as an `alias` in the master, which fixes it for every future
  application at once, over rewording this one.
- Cut genuinely irrelevant detail to make room, but keep enough breadth that
  the CV reads as a whole professional rather than a single-vacancy stunt.

## What the ATS actually does

Worth knowing, because the folklore is wrong and it changes what to optimise.

Applicant tracking systems do **not** generally auto-reject on keywords. The
"75% never reach a human" figure traces to a vendor's 2012 sales pitch, and
Greenhouse does not rank resumes algorithmically at all. What actually happens
is volume: hundreds of applicants, and a recruiter running keyword searches
over the database and reading the top of the results.

So the thing that matters is **retrieval, not density**. A term must be
present and must survive text extraction. Stuffing it repeatedly buys nothing;
missing it entirely makes the CV invisible.

## Format

- Single-column, selectable text. The repository's renderer already enforces
  this; do not try to change the template.
- Respect the page budget in `tailoring.yaml`. If it fails, cut content;
  never shrink margins or spacing. The design is fixed on purpose, so that
  every application looks like the same person sent it.
