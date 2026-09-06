"""Recover coverage records from `tailor-cv`'s prose logs.

Every `changes.md` opens with a table of what the vacancy asked for and what
answered it, and closes with an honest gaps section. That is the same content
`coverage.yaml` holds, written for a human.

What does NOT survive the conversion is `evidence`. The prose says "Scytale
b1", not an id in the master, and guessing the mapping would put unverifiable
claims into a file whose whole point is that coverage is checkable. So a
recovered record is marked `source: backfill` and carries no evidence; the
validator allows that for backfill and demands it for anything written fresh.

This costs nothing that matters. `jam gaps` reads `missing`, and a missing
requirement has no evidence by definition.
"""
from __future__ import annotations

import re
from pathlib import Path

ROW = re.compile(r"^\|(?!\s*[-: ]+\|)(.+?)\|(.+?)\|\s*$")
WEIGHT = re.compile(r"\((req|required|resp|pref|preferred)[^)]*\)", re.I)
PREFIX = re.compile(r"^\s*\*?(Pref|Preferred|Req|Required)\s*:\*?\s*", re.I)


def clean(cell: str) -> str:
    text = re.sub(r"`([^`]*)`", r"\1", cell)
    text = re.sub(r"\*\*?([^*]*)\*\*?", r"\1", text)
    return " ".join(text.split()).strip()


def weight_of(raw: str) -> str:
    """`(pref)` and `(resp/pref)` mean preferred; everything else required.

    Only 10 of 29 logs carry markers at all, so most rows fall to the default.
    The table is headed "JD requirement", which makes required the honest
    guess, but it does inflate the required count.
    """
    m = WEIGHT.search(raw) or PREFIX.match(raw)
    if not m:
        return "required"
    return "preferred" if m.group(1).lower().startswith("pref") else "required"


def status_of(coverage: str) -> str:
    if "⚠️" not in coverage and "partial" not in coverage.lower():
        return "covered"
    if re.search(r"nothing\b", coverage, re.I):
        return "missing"
    return "partial"


def parse(changes: str) -> list[dict]:
    """Rows of the requirement table, until the first section after it."""
    out, in_table = [], False
    for line in changes.splitlines():
        m = ROW.match(line)
        if not m:
            if in_table and line.startswith("#"):
                break
            continue
        left, right = m.group(1), m.group(2)
        if re.search(r"JD requirement|Requirement", left, re.I):
            in_table = True
            continue
        if not in_table:
            continue
        text = clean(PREFIX.sub("", WEIGHT.sub("", left)))
        if not text:
            continue
        out.append({"text": text, "weight": weight_of(left),
                    "status": status_of(right), "evidence": []})
    return out


GAP_ITEM = re.compile(r"^\s*(?:\d+[.)]|[-*])\s+(.*)$")
NOT_REQUIRED = re.compile(
    r"not a requirement|emerging|nice[- ]to[- ]have|optional|bonus|"
    r"desirable|preferred|not claimed, per your call", re.I)


def parse_gaps(changes: str) -> list[dict]:
    """The `## Honest gaps` list.

    Most gaps live here rather than in the table: 21 of 29 logs have no gap
    marked in the table at all while every one of them has this section. Reading
    only the table threw away almost everything the exercise is for.
    """
    out = []
    section = re.split(r"^##+\s*Honest gaps\s*$", changes, flags=re.M | re.I)
    if len(section) < 2:
        return out
    body = re.split(r"^##+\s", section[1], flags=re.M)[0]
    for line in body.splitlines():
        m = GAP_ITEM.match(line)
        if not m:
            continue
        item = m.group(1)
        lead = re.match(r"\*\*(.+?)\.?\*\*", item)
        text = clean(lead.group(1) if lead else item.split(".")[0])
        if not text or len(text) > 90:
            continue
        out.append({"text": text,
                    "weight": "preferred" if NOT_REQUIRED.search(item) else "required",
                    "status": "missing", "evidence": []})
    return out


def convert(folder: Path) -> dict | None:
    changes = folder / "changes.md"
    if not changes.exists():
        return None
    text = changes.read_text()
    requirements = parse(text)
    seen = {r["text"].lower() for r in requirements}
    for gap in parse_gaps(text):
        # A gap can appear in both places; the table row already says missing.
        if gap["text"].lower() not in seen:
            requirements.append(gap)
            seen.add(gap["text"].lower())
    if not requirements:
        return None
    return {"source": "backfill", "requirements": requirements}
