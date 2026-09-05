# WF2 — materials

The flow in full: what exists, what is planned, and what each gate is for.
Narrative and decisions live in [`workflows.md`](workflows.md) and
[`decisions.md`](decisions.md).

```mermaid
flowchart TB

subgraph IN [INPUTS]
  MASTER[(master-profile.yaml<br>the single source of truth)]
  JD[(jd.md<br>snapshot from intake)]
end

subgraph AG [AGENT -- judgement only, bounded by the gates]
  COVERAGE[1 COVERAGE<br>JD requirements vs the master<br>B1.7c -- planned]
  PLAN[2 TAILORING PLAN<br>what to drop, what to lead with<br>B1.7c -- planned]
  REFRAME[4 REFRAME<br>reword a bullet, merge two,<br>append the JD framing<br>B1.7b -- planned]
  COVERGEN[10 COVER LETTER<br>B1.7e -- planned]
end

subgraph DET [DETERMINISTIC CORE -- cannot call a model]
  ALIAS[3 ALIAS RESOLVER<br>declared synonym forms<br>matched against the JD, SKILLS only<br>B1.7a -- planned]
  RENDER[5 RENDER<br>master + plan + overrides to .tex<br>BUILT]
  MERGE[bullet merging in the render path<br>B1.7d -- planned]
end

subgraph GATES [GATES -- each one blocks the PDF]
  FACT{{6 FACT GATE<br>no new employer, technology or number<br>checked against the declared source<br>BUILT -- exit 3}}
  ATS{{7 ATS CHECK<br>every term survives extraction<br>no ligatures, order intact<br>BUILT -- exit 4}}
  PAGES{{8 MAX PAGES<br>BUILT -- exit 2}}
  HUMAN{{9 HUMAN APPROVAL<br>after the gates, never instead}}
end

subgraph ART [ARTIFACTS -- one folder per application]
  COVYAML[(coverage.yaml<br>requirement, weight, status, evidence)]
  TAILYAML[(tailoring.yaml<br>drop, emphasis, max_pages)]
  OVERYAML[(overrides.yaml<br>reworded bullets + from provenance)]
  CHANGES[(changes.md<br>coverage table + honest gaps)]
  CV[(cv.pdf)]
  COVERPDF[(cover.pdf)]
end

OUT1[WF3 -- submission]
OUT2[WF7 -- what the market wants<br>that the master lacks<br>jam gaps, B1.7g]

MASTER --> COVERAGE
JD --> COVERAGE
COVERAGE -->|what is covered, what is missing| COVYAML
COVERAGE -->|prose table + honest gaps| CHANGES
COVERAGE --> PLAN
PLAN --> TAILYAML
PLAN --> REFRAME
REFRAME -->|text + declared origin bullets| OVERYAML

JD --> ALIAS
MASTER --> ALIAS
ALIAS -->|JD wording for skills terms| RENDER
TAILYAML --> RENDER
OVERYAML --> RENDER
MASTER --> RENDER
MERGE --> RENDER

RENDER -->|.tex| FACT
MASTER -.->|source of allowed claims| FACT
OVERYAML -.->|per-override source scope| FACT
FACT -->|passes| ATS
ATS -->|passes| PAGES
PAGES -->|passes| HUMAN
HUMAN -->|approved| CV

MASTER --> COVERGEN
JD --> COVERGEN
COVERGEN --> FACT
COVERGEN --> COVERPDF

CV --> OUT1
COVERPDF --> OUT1
COVYAML --> OUT2

classDef built fill:#dcfce7,stroke:#15803d,stroke-width:2px,color:#0f172a
classDef planned fill:#fef3c7,stroke:#a16207,color:#0f172a
classDef gate fill:#ffedd5,stroke:#c2410c,stroke-width:2px,color:#0f172a
classDef data fill:#e5e7eb,stroke:#4b5563,color:#0f172a
classDef ext fill:#dbeafe,stroke:#1d4ed8,color:#0f172a

class RENDER built
class COVERAGE,PLAN,REFRAME,COVERGEN,ALIAS,MERGE planned
class FACT,ATS,PAGES,HUMAN gate
class MASTER,JD,COVYAML,TAILYAML,OVERYAML,CHANGES,CV,COVERPDF data
class OUT1,OUT2 ext
```

## Legend

| | |
|---|---|
| green | built and running today |
| amber | planned, with its roadmap task id |
| orange hexagon | a gate; each one blocks the PDF and has its own exit code |
| grey cylinder | an artifact written to the application folder |
| dashed arrow | a source the gate checks against, not an input to the render |

## What is built and what it costs

Three gates stand and the render works. Everything that fills the frame is
still to be written.

The gates are enforcement, not throughput: the fact gate would have caught one
fabrication in 29 real applications, and the ATS check passes on the current
toolchain, so it guards against a future font or template change rather than
fixing anything today.

## The cheap version

The most valuable single artifact is `coverage.yaml`, and it needs none of the
pipeline. Aggregated across applications it answers "what does the market ask
for that the master lacks" — the unit of observation is a requirement rather
than an application, so it works from the first submission, with no outcomes,
no gates and no renderer.

A minimum WF2 is therefore not the conveyor but making the tailoring skill
emit `coverage.yaml` and `tailoring.yaml` as a by-product of what it already
does.
