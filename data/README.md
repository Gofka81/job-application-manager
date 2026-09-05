# data/

**Nothing in this directory is ever committed** (decision D56). Only this file
and `.gitkeep` stay in git. Backups are the OS's job, not git's.

Full schemas: [`../docs/data-model.md`](../docs/data-model.md).

```
data/
├── master-profile.yaml           # THE single truth: experience, skills,
│                                 #   dates, awkward form fields
├── versions/                     # CV render profiles, 3-5 of them
├── templates/                    # cv.typ, follow-up templates
├── answer-bank.yaml              # answers to application-form questions
├── story-bank.md                 # stories, structured for retrieval
├── question-bank.md              # questions that actually get asked
├── weak-spots.md                 # recurring failures
├── decision-journal.md           # decision + reason + date
├── contacts.tsv                  # who to send follow-ups to
├── applications/
│   └── YYYY-MM-DD--company--role/
│       ├── application.json
│       ├── jd.md
│       ├── cv.pdf
│       ├── cover.pdf
│       └── prep-round-N.md
└── logs/
    ├── status.jsonl
    ├── rounds.jsonl
    ├── follow-up.jsonl
    └── changes.jsonl
```
