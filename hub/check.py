"""Check a finished CV against the master profile.

Deliberately minimal, and deliberately reading the PDF rather than its source.
Whatever produced the document, the PDF holds exactly what a person and a
parser will see, so nothing has to know about LaTeX, templates or how the file
was made. That also removes the whole class of defect where a layout parameter
was mistaken for content.

Three questions, no more:

  1. does it claim anything the master does not hold
  2. does its text come back out
  3. is it the length it should be

Everything it flags is a question, not a verdict: the answer is usually either
"true, so put it in the master" or "not true, so take it out of the CV".
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from hub import atscheck, factgate

# Words a CV template contributes rather than the candidate claiming them.
FURNITURE = frozenset({
    "skills", "work", "experience", "professional", "employment", "projects",
    "education", "certifications", "certification", "summary", "profile",
    "present", "current", "link", "links", "gpa", "github", "linkedin",
    "jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "sept",
    "oct", "nov", "dec", "january", "february", "march", "april", "june",
    "july", "august", "september", "october", "november", "december",
})


# Technology names that are also ordinary English words. Without this the
# dictionary filter below would hide exactly the claims worth seeing.
TECH_HOMONYMS = frozenset({
    "kafka", "snowflake", "spark", "delta", "iceberg", "airflow", "glue",
    "hive", "beam", "flink", "pig", "storm", "cassandra", "redshift", "lake",
    "lambda", "athena", "aurora", "fabric", "flow", "looker", "tableau",
    "elt", "etl", "dbt", "go", "rust", "swift", "julia", "processing",
})

_DICT = Path("/usr/share/dict/words")


def common_words() -> frozenset[str]:
    """Ordinary English words, so a Title-Cased skills line is not all claims.

    Every word in a skills line is capitalised, so without this filter
    "Testing", "Design" and "Monitoring" read as invented proper nouns and
    bury the handful that matter.

    Only Title-case tokens are filtered. An acronym, a mixed-case name or
    anything with a digit stays visible whatever the dictionary says, and
    TECH_HOMONYMS forces through the names that collide with real words.
    """
    if not _DICT.exists():
        return frozenset()
    return frozenset(w.strip().lower() for w in _DICT.read_text().splitlines()
                     if w.strip().isalpha()) - TECH_HOMONYMS


def is_ordinary(token: str, text: str, dictionary: frozenset[str]) -> bool:
    """True when a flagged token is just an English word, capitalised."""
    if token in TECH_HOMONYMS or not dictionary:
        return False
    if any(c.isdigit() for c in token):
        return False
    # An acronym or a mixed-case name is never ordinary, whatever it spells.
    for form in (token.upper(), token.capitalize()):
        if form == token.upper() and form in text:
            return False
    if token in dictionary:
        return True
    # The dictionary holds base forms, so "contributed" and "sourced" would
    # read as proper nouns without stripping the inflection.
    for suffix, stem in ((" ", token), ("s", token[:-1]), ("es", token[:-2]),
                         ("d", token[:-1]), ("ed", token[:-2]),
                         ("ing", token[:-3]), ("ing", token[:-3] + "e"),
                         ("ly", token[:-2])):
        if token.endswith(suffix.strip()) and len(stem) > 2 and stem in dictionary:
            return True
    return False


@dataclass
class Report:
    path: Path
    claims: factgate.Result | None = None
    ligatures: set[str] = field(default_factory=set)
    missing_contact: list[str] = field(default_factory=list)
    pages: int | None = None
    chars: int = 0
    max_pages: int | None = None

    @property
    def ok(self) -> bool:
        return (self.chars > 0 and not self.ligatures and not self.missing_contact
                and (self.claims is None or self.claims.ok)
                and not (self.max_pages and self.pages and self.pages > self.max_pages))

    def report(self) -> str:
        head = f"{self.path.name}: "
        if self.ok:
            return head + f"pass ({self.pages} page(s), {self.chars} chars)"
        lines = [head + "FAIL"]
        if not self.chars:
            lines.append("  no text extracted — the PDF is not selectable")
        if self.ligatures:
            lines.append("  ligature glyphs, unsearchable: "
                         + " ".join(sorted(self.ligatures)))
        if self.missing_contact:
            lines.append("  contact details missing: " + ", ".join(self.missing_contact))
        if self.max_pages and self.pages and self.pages > self.max_pages:
            lines.append(f"  {self.pages} pages, budget is {self.max_pages}")
        if self.claims and not self.claims.ok:
            if self.claims.invented_names:
                lines.append("  not in the master: "
                             + ", ".join(sorted(self.claims.invented_names)))
            if self.claims.invented_numbers:
                lines.append("  numbers not in the master: "
                             + ", ".join(sorted(self.claims.invented_numbers)))
        return "\n".join(lines)


def check(pdf: Path, source: str, contact: list[str], allow: set[str],
          max_pages: int | None = None) -> Report:
    text = atscheck.extract(pdf)
    dictionary = common_words()
    claims = factgate.verify(text, source, allow=FURNITURE | allow)
    claims.invented_names = {n for n in claims.invented_names
                             if not is_ordinary(n, text, dictionary)}
    return Report(
        path=pdf,
        claims=claims,
        ligatures={c for c in set(text) if c in atscheck.LIGATURES},
        missing_contact=[c for c in contact if c and c not in text],
        pages=atscheck.page_count(pdf),
        chars=len(text.strip()),
        max_pages=max_pages,
    )
