"""Does the PDF survive being read back?

Recruiters do not read every application — they run keyword searches over the
database and read the top of the results, and boolean search matches exact
strings. A term that does not extract from the PDF is therefore invisible, no
matter how prominent it looks on the page.

This is the classic silent failure: the CV looks perfect, nothing errors, and
the term simply is not there. What it catches:

  - ligature glyphs with no ToUnicode mapping, so "workflows" extracts as
    "work ows" and no search for it will ever match
  - text rendered as outlines or images, extracting as nothing at all
  - column or table layouts that scramble reading order
  - font subsetting that loses the character mapping

NOT a substitute for a real ATS. Greenhouse and Workday use their own
parsers, and there is no candidate-facing API to test against — submitting
test applications to real employers to find out is not an option. Passing here
is necessary, not sufficient.
"""
from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from hub import factgate

# Scanned raw, not inferred from lost tokens: the fact gate's tokeniser
# NFKC-normalises, so "workﬂows" compares equal to "workflows" and nothing
# looks lost. An ATS parser may not normalise, and then the term is
# unsearchable while every check we own reports success.
LIGATURES = {chr(c) for c in range(0xFB00, 0xFB07)}
SECTIONS = ("SKILLS", "EXPERIENCE", "PROJECTS", "EDUCATION", "CERTIFICATIONS")


class ExtractorMissing(RuntimeError):
    pass


def page_count(pdf: Path) -> int | None:
    """Pages in a PDF, via poppler with a fallback scan of the raw bytes."""
    if shutil.which("pdfinfo"):
        r = subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True)
        for line in r.stdout.splitlines():
            if line.startswith("Pages:"):
                return int(line.split()[1])
    blob = pdf.read_bytes()
    return (blob.count(b"/Type /Page") - blob.count(b"/Type /Pages")) or None


def extract(pdf: Path) -> str:
    if not shutil.which("pdftotext"):
        raise ExtractorMissing(
            "pdftotext not found — install poppler (brew install poppler)"
        )
    r = subprocess.run(["pdftotext", str(pdf), "-"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip() or "pdftotext failed")
    return r.stdout


@dataclass
class Result:
    lost: set[str] = field(default_factory=set)
    ligatures: set[str] = field(default_factory=set)
    missing_contact: list[str] = field(default_factory=list)
    section_order: list[str] = field(default_factory=list)
    expected_order: list[str] = field(default_factory=list)
    chars: int = 0

    @property
    def ok(self) -> bool:
        return not (self.lost or self.ligatures or self.missing_contact
                    or self.section_order != self.expected_order)

    def report(self) -> str:
        if self.ok:
            return f"ats check: pass — {self.chars} chars, all terms survive"
        lines = ["ats check: FAIL"]
        if not self.chars:
            lines.append("  nothing extracted — the text is not selectable")
        if self.ligatures:
            lines.append("  ligature glyphs, unsearchable: "
                         + " ".join(sorted(self.ligatures)))
        if self.missing_contact:
            lines.append("  contact details did not extract: "
                         + ", ".join(self.missing_contact))
        if self.lost:
            sample = sorted(self.lost)[:12]
            lines.append(f"  {len(self.lost)} term(s) lost in extraction: "
                         + ", ".join(sample))
        if self.section_order != self.expected_order:
            lines.append(f"  reading order scrambled: {self.section_order} "
                         f"!= {self.expected_order}")
        return "\n".join(lines)


def check(rendered_text: str, extracted: str, contact: list[str]) -> Result:
    """Compare what was rendered against what a parser can read back.

    Token comparison reuses the fact gate's tokeniser, so "survives
    extraction" and "counts as a claim" mean the same thing by construction.
    """
    order = [s for s in SECTIONS if s in extracted.upper()]
    return Result(
        lost=factgate.tokens(rendered_text) - factgate.tokens(extracted),
        ligatures={c for c in set(extracted) if c in LIGATURES},
        missing_contact=[c for c in contact if c and c not in extracted],
        section_order=order,
        expected_order=[s for s in SECTIONS if s in rendered_text.upper()],
        chars=len(extracted.strip()),
    )
