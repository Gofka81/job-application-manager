# Architecture

Two independent systems, one manual junction, one one-way notification back.

```mermaid
flowchart TB

subgraph S1 [1 -- JOB-RADAR -- Raspberry Pi + Docker + Cloudflare Tunnel -- WF1]
  SRC[(10 sources -- official APIs<br>vacancy + posted_at freshness)]
  SCAN[normalize, dedup,<br>freshness and criteria filters]
  TRIAGE[bounded LLM triage<br>fit 0-10 + reason]
  RDB[(SQL job-radar<br>jobs, seen, scores)]
  INBOX[(INBOX<br>title, company, JD, score)]
  WDOG[watchdog -- date of last submission<br>silence longer than N days]
  TGN[Telegram<br>output only, not a remote control]
end

subgraph S2 [2 -- HUB / APPLICATION PIPELINE -- MacBook, Python]
  INTAKE[intake -- normalize a link<br>JD, score, dedup against submitted]
  GEN[WF2 render CV and cover<br>version profile + JD tailoring]
  GATE[WF2 fact gate<br>deterministic, no model]
  GCV{{human -- approve CV}}
  COPILOT[WF3 agent fills the form<br>in the browser]
  STOP{{WF3 STOP -- field list,<br>agent-inferred ones highlighted}}
  HUMAN{{human -- OTP, CAPTCHA, click}}
  TRACK[WF4 tracker<br>status = fold of status.jsonl]
  RWATCH[WF4 reply-watch<br>Gmail, closed list of applications]
  GST{{human -- confirm status}}
  PREP[WF5 prep sheet<br>one page, on demand]
  ROUND[WF5 interview round]
  DEBR[WF5 debrief -- 3 questions<br>+ prediction, same day]
  AGING[WF6 aging -- stale beyond N days<br>cap of 2 touches per company]
  GFU{{human -- sends follow-up<br>manually}}
end

subgraph S3 [3 -- HUB / KEY ASSETS -- outlive any single vacancy]
  MASTER[(master-profile.yaml<br>+ versions -- render profiles)]
  MAT[(materials -- CV, cover<br>in the application folder)]
  ANSW[(answer bank<br>answer-bank.yaml)]
  STORY[(story bank + question bank<br>+ weak spots)]
  TPL[(templates + contacts.tsv)]
  DEC[(decision journal)]
end

subgraph S4 [4 -- HUB / FACTS -- append-only, never rewritten]
  APP[(application.json<br>channel, discovery, cv_version)]
  SLOG[(status.jsonl)]
  RLOG[(rounds.jsonl)]
  FLOG[(follow-up.jsonl)]
  CHLOG[(changes.jsonl)]
end

subgraph S5 [5 -- HUB / ANALYTICS -- WF7]
  ANL[catastrophe detector on DuckDB<br>reads files directly, no ingest<br>verdict -- ok, catastrophe, not enough data]
end

MANUAL{{human -- arbitrary link<br>LinkedIn, company careers page}}

%% WF1
SRC -->|raw vacancies from APIs| SCAN
SCAN -->|unique fresh candidates| TRIAGE
SCAN -->|dedup keys, seen| RDB
RDB -->|already seen| SCAN
TRIAGE -->|score 0-10| RDB
RDB -->|top-N by score| INBOX
WDOG -.->|no submissions for N days| TGN

%% two entry points into the hub
INBOX ==>|chosen vacancy from radar, link + JD| INTAKE
MANUAL ==>|agent reads the JD off the page| INTAKE
INTAKE -->|identical dossier regardless of branch| GEN

%% WF2
MASTER -->|facts + version profile| GEN
GEN -->|rendered CV| GATE
GATE -->|claims checked against the master| GCV
GCV -->|approved| MAT

%% WF3
MAT -->|CV + cover.pdf| COPILOT
ANSW -->|known answers for form fields| COPILOT
COPILOT -->|form filled<br>+ batch of unanswered questions| STOP
STOP -->|hands over control| HUMAN
HUMAN ==>|new question + answer + alias| ANSW
HUMAN -->|Submit confirmed -- WF3/WF4 boundary| APP
APP -.->|ping -- date only, fire-and-forget| WDOG

%% WF4
APP -->|new application| TRACK
TRACK -->|transition event| SLOG
RWATCH -->|classified status or unclear| GST
GST -->|confirmed from-to| SLOG
SLOG -->|fold of the log = current state| TRACK

%% WF5
TRACK -->|status = in_process| PREP
STORY -->|5 stories for this JD and round type| PREP
PREP -->|one page| ROUND
ROUND -->|round on record| RLOG
ROUND -->|notes, same day| DEBR
DEBR ==>|weekly curation -- stories,<br>questions, weak spots| STORY

%% WF6
TRACK -->|silence beyond stale_days| AGING
AGING -->|follow-up queue| GFU
TPL -->|template + contact| GFU
GFU -->|email sent| FLOG
FLOG -->|touch on record| SLOG

%% WF7 -- DuckDB reads files, there is no ingest
APP -.->|channel, discovery, cv_version| ANL
MAT -.->|CV version metadata| ANL
SLOG -.->|status transitions| ANL
RLOG -.->|interview stages| ANL
FLOG -.->|touches| ANL
CHLOG -.->|change dates for before-after| ANL
ANL -->|verdict -- channel X is dead,<br>wall at the entrance| DEC
ANL -.->|steers preparation focus| PREP

%% feedback loops
DEC ==>|new CV version, repositioning| MASTER
DEC ==>|decision to rewrite LinkedIn -- done by hand| CHLOG
STORY ==>|recurring failures| DEC

classDef pi fill:#dbeafe,stroke:#1d4ed8,color:#0f172a
classDef hub fill:#dcfce7,stroke:#15803d,color:#0f172a
classDef human fill:#ffedd5,stroke:#c2410c,stroke-width:2px,color:#0f172a
classDef asset fill:#fef9c3,stroke:#a16207,stroke-width:3px,color:#0f172a
classDef log fill:#e5e7eb,stroke:#4b5563,color:#0f172a

class SRC,SCAN,TRIAGE,RDB,INBOX,WDOG,TGN pi
class INTAKE,GEN,GATE,COPILOT,TRACK,RWATCH,PREP,ROUND,DEBR,AGING,ANL hub
class GCV,STOP,HUMAN,GST,GFU,MANUAL human
class MASTER,MAT,ANSW,STORY,TPL,DEC asset
class APP,SLOG,RLOG,FLOG,CHLOG log
```

## Legend

| style | meaning |
|---|---|
| blue | job-radar on the Pi, WF1 |
| green | hub processes, WF2-WF7 |
| orange hexagon | human gate |
| yellow cylinder, thick border | key asset, outlives a single vacancy |
| grey cylinder | fact, append-only |
| thick arrow | feedback and learning |
| dashed | the engine reading files, or a notification — not a write |

## How to read it

**Band 2** is what happens to ONE vacancy, top to bottom.

**Band 3** is the six assets that accumulate between vacancies and make the
next application cheaper. This is what the system exists for: without them
every submission would cost as much as the first one.

**Band 4** is facts that are never rewritten.

**Band 5** reads 3 and 4, returns a verdict into the decision journal, and
that closes the loop back into `master-profile.yaml`.

The diagram holds 35 nodes. That is the readability ceiling; further detail
goes into prose, not into the picture.

---

# Stack

**Python + DuckDB. There is no persistent database.**

DuckDB here is a query engine, not a store. It reads JSONL and TSV straight
out of `data/`, so there is no ingest step — and with it, no schema to
migrate and no drift between files and a database. "Files are the truth"
holds by construction rather than by discipline.

SQLite was rejected deliberately: it is optimized for concurrent writes,
transactions and long-lived mutable state, none of which the hub has. What a
persistent `.db` would bring back is an ingest script and drift.

What DuckDB gives specifically here:

- `ASOF JOIN` — "what was this application's status at the moment the
  LinkedIn profile changed". The before-after slice becomes a single join.
- Full window functions plus `QUALIFY` for stage-by-stage funnels.
- `read_json_auto` / `read_csv_auto` — logs and `contacts.tsv` read as tables
  with no conversion.

**Cache.** If queries ever get slow — which starts around hundreds of
thousands of rows, i.e. never here — a `.duckdb` file can be materialized.
It stays in `.gitignore`, rebuilds with one command, and remains a cache
rather than a source of truth.

**When to revisit.** If a UI appears, or several processes start writing
concurrently, SQLite is the right answer — that is exactly what it is for.

---

# Runtime

## There is no scheduled daemon

Everything derived — `ghosted`, aging, the funnel, current status — is
computed at query time. Nothing needs to be computed on a schedule.

## The split is by the right to call a model

| part | what | how |
|---|---|---|
| deterministic core | queries, reports, digest, validation, fact gate | Python + DuckDB, **no model** |
| agentic edges | CV generation, form filling, email classification, question matching | Claude Code session, skills |

This is what operationalizes "LLM calls are bounded": the boundary runs
through code, not through a promise. What lives in the core physically
cannot call a model.

## A session opens with the digest

```
3 applications stale, time to nudge
1 debrief unwritten (Northwind, yesterday)
2 emails classified as unclear
Gmail: checked just now, 4 new events
last ping accepted by the Pi: 04.09
```

Email is checked **on demand** at session start: a day of latency changes
nothing for status tracking, so no daemon is needed. The nudge rides on an
action the human already wants to take.

## The watchdog lives on the Pi

A reminder about absence cannot live in the system the person has vanished
from: the Mac is off, or is being avoided, precisely when the signal matters.
The Pi is always on. This is a dead man's switch.

- The hub sends a **ping at confirmed Submit** — date only, fire-and-forget.
  Not at session start: a session without submissions is not activity, and
  that is exactly the case the watchdog must catch.
- The Pi stores **one number**, not a log. Analytics never reads it.
- Channel: Cloudflare Tunnel, authentication via an Access service token.
  An unauthenticated request never reaches the Pi at all.
- `snooze` always carries an expiry, and its delivery is confirmed. The final
  off switch is stopping the container on the Pi.

## Summary

| need | covered by |
|---|---|
| submitting, debriefs, confirming statuses | Claude Code session, skills |
| numbers, reports, validation | Python + DuckDB CLI, no model |
| checking email | on demand, at session start |
| aging, ghosted, funnel | computed at query time |
| "you disappeared" | watchdog on the Pi plus a ping on submission |
