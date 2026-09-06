# Job Application Hub

A system for running a job search: from finding a vacancy to understanding
what works and what doesn't.

## Two independent systems

**job-radar** — Raspberry Pi, Docker. Deterministic job discovery plus bounded
LLM triage. This is WF1, and it **already works**. Exposed to the internet
through a Cloudflare Tunnel.

**Application Hub** — MacBook, local repository, Python + DuckDB. Everything
after a vacancy is chosen: WF2-WF7.

No shared code, no shared database. The only junction is a human carrying the
link of a chosen vacancy from INBOX into the hub. Plus a one-way notification
back: a ping on submission, feeding the watchdog on the Pi.

## Principles

1. **The human is the only Submit point.** The system prepares, the human
   reviews and clicks.
2. **LLM calls are bounded.** The boundary is drawn in code: the deterministic
   core physically cannot call a model.
3. **Files are the truth.** Derived state is never stored — current status,
   `ghosted`, the funnel are computed at query time.
4. **Capture cheap, curate later.** Debriefs and form answers are captured raw
   at the moment the information exists; curation is a separate, unhurried act.
5. **Analytics is a catastrophe detector, not an optimizer.** At 60-150
   applications a difference smaller than 2x is undetectable. The system is
   designed around "is anything broken", not "which is better".

## Documents

| file | contents |
|---|---|
| [`docs/roadmap.md`](docs/roadmap.md) | work queue, tasks, milestones |
| [`docs/architecture.md`](docs/architecture.md) | diagram, the two systems, stack, runtime |
| [`docs/data-model.md`](docs/data-model.md) | `data/` layout, file schemas, logs, keys |
| [`docs/wf2.md`](docs/wf2.md) | WF2 in full: diagram, gates, what is built |
| [`docs/workflows.md`](docs/workflows.md) | WF1-WF7: what each does, what is settled, what is open |
| [`docs/decisions.md`](docs/decisions.md) | 75 settled decisions with reasoning |
| [`docs/risks.md`](docs/risks.md) | risks per WF, implementation order |
| [`docs/research.md`](docs/research.md) | existing solutions, career-ops as a reference |
| [`todo.md`](todo.md) | important, but not now |
| [`THIRD_PARTY.md`](THIRD_PARTY.md) | attribution for work this borrows from |

## Implementation order

By data dependencies, not by WF number. Details in
[`docs/roadmap.md`](docs/roadmap.md).

1. **intake** — WF2 + WF3 + writing the application record, as one path
2. **outcome capture** — email, weekly sweep
3. **WF7** — the detector (nothing to work on before this point)
4. **WF6** — thresholds come from block 2 data
5. **WF5** — once interviews start happening

## Status

Architecture settled. No code yet beyond the skeleton.

Open: a WF1 review, two items in `todo.md`, and details deliberately deferred
to the design stage of each block.

## Applying to a vacancy

Ask Claude Code to tailor an application, or invoke `/tailor`. The skill in
`.claude/skills/tailor/` reads the job description, records what it asks for
against the master profile, writes the tailoring plan, and renders through the
gates. It writes decisions; `jam` writes the PDF.

The CV itself is still produced by the standalone `tailor-cv` skill, which
works; this repository checks the result rather than replacing it (D73).

Run `jam` with no arguments for a menu; everything below is also a command
in its own right.

```sh
jam                                         # menu: arrow keys all the way down
jam inbox                                   # what job-radar found, arrow keys to pick
jam take "data idols"                       # turn a vacancy into an application
jam build <app_id>                          # rebuild that application's CV and check it
jam check ~/CV/applications --max-pages 1   # check finished PDFs against the master
jam ask "Years of SQL?" --type integer      # answer a form question from the bank
jam learn "Notice period?" "1 month"        # record one the human just gave
jam submit <app_id>                         # record a submission that happened
jam gaps                                    # what the market wants that you lack
jam coverage --app <app_id>                 # validate one coverage record
jam render --app <app_id>                   # render from the master, if you want to
```

## Setup after cloning

```sh
git config core.hooksPath .githooks   # otherwise the pre-commit hook is inert
cp .env.example .env                  # then fill it in
```

`core.hooksPath` is local config — it does not travel with the repository.
Without it the hook sits in `.githooks/` and never runs.

## Privacy

`data/` **never** enters git. Secrets live in `.env`. Details: decisions
D56-D63.
