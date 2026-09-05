"""Deterministic fact gate: nothing may be claimed that the source does not hold.

No model is involved (D38) — a deterministic check does not rubber-stamp its
own output. The gate is a boundary, not a ban (D40): prose may be rewritten
freely, but no new employer, technology or number may appear.

Two things are checked, because they are the two that get invented:

  numbers   metrics, percentages, sizes, counts
  names     proper nouns and product-like tokens (AWS, S3, PySpark, Contoso)

Framing language — "ensuring trusted, reliable data delivery" — is invisible
here on purpose. Layering a characterisation onto a real fact is what anyone
writing their own CV does; inventing a client name is not.

EXTRACTION IS SYMMETRIC: the same functions run over the candidate text and
over the source. Widening a pattern can therefore only ever surface MORE
claims on both sides — it cannot hide a fabrication by construction.

Ported in spirit from career-ops `verify-cv-facts.mjs` (MIT,
github.com/santifer/career-ops); the edge cases in the tests are theirs.
Their regexes lean on \\p{L}, which Python's `re` does not support (D54);
this implementation uses Python's native Unicode-aware casing instead, so no
`regex` dependency is needed.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

# Ordinary words that open a sentence or a bullet and are capitalised for that
# reason alone. Without this every bullet's first word reads as a proper noun.
_SENTENCE_WORDS = {
    "a", "an", "and", "the", "of", "for", "to", "in", "on", "with", "by",
    "built", "designed", "developed", "delivered", "implemented", "migrated",
    "modelled", "modeled", "diagnosed", "took", "administered", "integrated",
    "constrained", "applied", "reduced", "cut", "led", "owned", "created",
    "automated", "scheduled", "packaged", "tuned", "resolved", "profiled",
    # Ordinary CV verbs. A first-position word is now treated as a claim so a
    # fabricated employer at the start of an experience line cannot hide, and
    # the price is that a verb the master never uses would be flagged. Most
    # are covered anyway because the source contains the same prose.
    "ran", "managed", "ensured", "maintained", "wrote", "shipped", "drove",
    "grew", "scaled", "supported", "coordinated", "mentored", "refactored",
    "deployed", "orchestrated", "established", "improved", "achieved",
    "enabled", "partnered", "collaborated", "analysed", "analyzed",
    "presented", "defined", "standardised", "standardized", "hardened",
    "instrumented", "introduced", "rebuilt", "replaced", "removed",
}

# Units and suffixes that travel with a number and change its meaning.
_NUM = re.compile(
    r"(?<![\w.])"
    r"(\d[\d,]*(?:\.\d+)?)"          # 70   100,000   1.5
    r"\s*"
    r"([kKmMbB]\b|%|x\b|tb\b|gb\b|mb\b)?",  # 50k  18%  3x  5TB
    re.I,
)

_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9.+#-]*")

# Unicode decimal blocks, keyed by the code point of their zero. A CV written
# in non-ASCII digits produced ZERO number claims in career-ops, so the gate
# reported a pass having checked nothing.
_DIGIT_ZEROS = (0x0660, 0x06F0, 0x0966, 0x09E6, 0x0A66, 0x0AE6, 0x0B66,
                0x0BE6, 0x0C66, 0x0CE6, 0x0D66, 0x0E50, 0x0ED0, 0x0F20,
                0x1040, 0x17E0, 0x1810)


def fold_digits(text: str) -> str:
    """Rewrite every Unicode decimal digit as ASCII.

    Applied to candidate AND source, so it can only make more claims visible
    on both sides — never hide one.
    """
    out = unicodedata.normalize("NFKC", text)
    chars = []
    for ch in out:
        cp = ord(ch)
        if ch.isdigit() and not ("0" <= ch <= "9"):
            for zero in _DIGIT_ZEROS:
                v = cp - zero
                if 0 <= v <= 9:
                    ch = str(v)
                    break
        chars.append(ch)
    return "".join(chars)


def numbers(text: str) -> set[str]:
    """Normalised numeric claims: 100,000 -> 100000, 50k -> 50000, 18% -> 18%.

    A trailing '+' is stripped on both sides. That is deliberately lenient:
    it means "70+" and "70" compare equal, so the gate will not catch an
    inflation from 70 to 70+. Numbers themselves cannot be invented, which is
    the failure that matters.
    """
    out = set()
    for value, suffix in _NUM.findall(fold_digits(text)):
        n = value.replace(",", "")
        s = (suffix or "").lower()
        if s in ("k", "m", "b"):
            mult = {"k": 1_000, "m": 1_000_000, "b": 1_000_000_000}[s]
            try:
                n = str(int(float(n) * mult))
            except ValueError:
                pass
            s = ""
        out.add(f"{n}{s}")
    return out


def names(text: str) -> set[str]:
    """Proper-noun and product-like tokens, lowercased for comparison.

    Kept: Title-case away from a sentence opening, ALL-CAPS, and anything
    mixing letters with digits or internal capitals — AWS, S3, PySpark, EMR.
    """
    out = set()
    for sentence in re.split(r"[.;:!?]\s+|\n", fold_digits(text)):
        for i, tok in enumerate(_TOKEN.finditer(sentence)):
            w = tok.group().strip(".-+#")
            if len(w) < 2:
                continue
            interesting = (
                w.isupper()
                or any(c.isdigit() for c in w)
                or any(c.isupper() for c in w[1:])
                or w[0].isupper()
            )
            if interesting and w.lower() not in _SENTENCE_WORDS:
                out.add(w.lower())
    return out


def tokens(text: str) -> set[str]:
    """Every alphabetic token in a text, lowercased.

    The SOURCE side is read with this rather than with names(): the source is
    the authority, so anything it literally contains is by definition not
    invented. That also removes the need to exempt a token merely for opening
    a line — an exemption that hid a fabricated employer, since a company name
    is exactly what sits at the start of an experience line.
    """
    return {m.group().strip(".-+#").lower()
            for m in _TOKEN.finditer(fold_digits(text))
            if len(m.group().strip(".-+#")) >= 2}


@dataclass
class Result:
    invented_numbers: set[str] = field(default_factory=set)
    invented_names: set[str] = field(default_factory=set)

    @property
    def ok(self) -> bool:
        return not (self.invented_numbers or self.invented_names)

    def report(self, label: str = "") -> str:
        if self.ok:
            return f"fact gate: pass{' — ' + label if label else ''}"
        lines = [f"fact gate: FAIL{' — ' + label if label else ''}"]
        if self.invented_names:
            lines.append("  names not in the source: "
                         + ", ".join(sorted(self.invented_names)))
        if self.invented_numbers:
            lines.append("  numbers not in the source: "
                         + ", ".join(sorted(self.invented_numbers)))
        lines.append("  add it to master-profile.yaml if true, "
                     "or remove it from the text")
        return "\n".join(lines)


def verify(candidate: str, source: str, allow: set[str] | None = None) -> Result:
    """Check a candidate text against the source it claims to derive from.

    `source` is scoped by the caller: the whole master for a rendered CV, or
    only the declared origin bullets for an override (D40a) — checking an
    override against the whole master would let a metric migrate from one
    employer to another.
    """
    allowed = {a.lower() for a in (allow or set())}
    return Result(
        invented_numbers=numbers(candidate) - numbers(source) - allowed,
        invented_names=names(candidate) - tokens(source) - allowed,
    )
