"""What a vacancy asked for, and what the master could answer.

Structured rather than prose (D70): a paragraph in `changes.md` cannot be
joined to an outcome later, and counting it means writing regexes over
someone's writing.

    requirements:
      - text: "5+ years Python"
        weight: required          # required | preferred
        status: covered           # covered | partial | missing
        evidence: [northwind.2, skills.python]

`evidence` points at master ids, so a claim of coverage is checkable rather
than asserted — an id that does not resolve is an error, not a typo to
ignore.

The reason to collect this from the first application is the analysis that
needs no outcomes at all: aggregate `missing` and you have what the market
asks for that the master lacks. Its unit of observation is a requirement, and
there are hundreds of those, which is why it works at a volume where almost
nothing else in WF7 does.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import yaml

from hub import overrides

WEIGHTS = ("required", "preferred")
STATUSES = ("covered", "partial", "missing")


class CoverageError(ValueError):
    pass


def valid_ids(master: dict) -> set[str]:
    ids = set(overrides.bullet_index(master))
    for group in (master.get("skills") or {}).values():
        ids.update(f"skills.{k}" for k in group)
    for e in master.get("education") or []:
        ids.add(f"education.{e['id']}")
    for i, _ in enumerate(master.get("certifications") or []):
        ids.add(f"certifications.{i}")
    return ids


def validate(master: dict, doc: dict) -> None:
    backfilled = (doc or {}).get("source") == "backfill"
    reqs = (doc or {}).get("requirements")
    if not reqs:
        raise CoverageError("coverage file has no `requirements`")
    known = valid_ids(master)
    for i, r in enumerate(reqs):
        where = f"requirement {i} ({str(r.get('text'))[:40]!r})"
        if not r.get("text"):
            raise CoverageError(f"{where}: needs `text`")
        if r.get("weight") not in WEIGHTS:
            raise CoverageError(f"{where}: `weight` must be one of {WEIGHTS}")
        if r.get("status") not in STATUSES:
            raise CoverageError(f"{where}: `status` must be one of {STATUSES}")
        evidence = r.get("evidence") or []
        if r["status"] != "missing" and not evidence and not backfilled:
            raise CoverageError(
                f"{where}: status {r['status']!r} but no evidence — "
                f"a claim of coverage has to point at something"
            )
        if r["status"] == "missing" and evidence:
            raise CoverageError(f"{where}: status 'missing' cannot cite evidence")
        for e in evidence:
            if e not in known:
                raise CoverageError(
                    f"{where}: evidence {e!r} is not an id in the master"
                )


@dataclass
class Summary:
    required: int = 0
    required_covered: int = 0
    preferred: int = 0
    preferred_covered: int = 0
    missing_required: list[str] = None
    missing_preferred: list[str] = None

    @property
    def share(self) -> float | None:
        """Covered share of required. `partial` counts as half."""
        return self.required_covered / self.required if self.required else None

    def report(self) -> str:
        pct = f"{self.share:.0%}" if self.share is not None else "n/a"
        lines = [f"required  {self.required_covered:.1f}/{self.required} ({pct})",
                 f"preferred {self.preferred_covered:.1f}/{self.preferred}"]
        if self.missing_required:
            lines.append("missing, required:  " + "; ".join(self.missing_required))
        if self.missing_preferred:
            lines.append("missing, preferred: " + "; ".join(self.missing_preferred))
        return "\n".join(lines)


def summarize(doc: dict) -> Summary:
    s = Summary(missing_required=[], missing_preferred=[])
    for r in doc["requirements"]:
        weight = r["weight"]
        score = {"covered": 1.0, "partial": 0.5, "missing": 0.0}[r["status"]]
        if weight == "required":
            s.required += 1
            s.required_covered += score
        else:
            s.preferred += 1
            s.preferred_covered += score
        if r["status"] == "missing":
            (s.missing_required if weight == "required"
             else s.missing_preferred).append(r["text"])
    return s


def load(path: Path) -> dict:
    return yaml.safe_load(path.read_text()) or {}


# The logs' own vocabulary for describing a gap, rather than the thing missing.
# "Azure breadth" and "Databricks recency" are two ways of naming Azure and
# Databricks, and counting the qualifier tells you nothing.
SCAFFOLDING = frozenset({
    "and", "or", "the", "a", "an", "of", "in", "on", "for", "to", "with", "at",
    "by", "no", "not", "none", "any", "some", "own", "per", "its",
    "experience", "breadth", "recency", "depth", "exposure", "gap", "gaps",
    "framing", "thin", "only", "side", "specifically", "specific", "named",
    "formal", "direct", "real", "hands", "scale", "core", "stack", "tools",
    "tooling", "platform", "platforms", "data", "work", "role", "claimed",
})


def terms(folder: Path, min_count: int = 2) -> Counter:
    """Count the terms inside gap texts, not the whole phrases.

    Exact phrases undercount: "Microsoft Fabric" and "Fabric" are the same
    gap written twice. Ordinary English is kept here, unlike the CV check —
    "streaming", "mentoring" and "financial services" are the signal, not
    noise, so only the logs' own scaffolding words are dropped.
    """
    counts = Counter()
    for f in sorted(folder.glob("*/coverage.yaml")):
        doc = load(f)
        for r in doc.get("requirements") or []:
            if r.get("status") != "missing":
                continue
            for word in re.findall(r"[A-Za-z][A-Za-z0-9+#./-]+", str(r["text"])):
                word = word.strip("./-").lower()
                if len(word) > 2 and word not in SCAFFOLDING:
                    counts[word] += 1
    return Counter({t: n for t, n in counts.items() if n >= min_count})


def aggregate(folder: Path) -> tuple[Counter, Counter, int]:
    """Count what was missing across every application that recorded coverage.

    Needs no outcomes, so it pays off from the first application.
    """
    required, preferred, seen = Counter(), Counter(), 0
    for f in sorted(folder.glob("*/coverage.yaml")):
        doc = load(f)
        if not doc.get("requirements"):
            continue
        seen += 1
        for r in doc["requirements"]:
            if r.get("status") == "missing":
                key = " ".join(str(r["text"]).split()).lower()
                (required if r.get("weight") == "required" else preferred)[key] += 1
    return required, preferred, seen
