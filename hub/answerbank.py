"""Answers to the questions application forms ask.

Two channels fill it, and the second matters more than it looks:

  asked      the agent hits a field it has no answer for and asks
  harvested  whatever the human typed by hand is collected at the STOP screen,
             including fields the agent never recognised as questions

Matching is deliberately asymmetric. A confident match fills the field; any
doubt asks. A needless question costs ten seconds, a wrong answer in a
submitted application costs the vacancy.

Tenure is stored as a date and entered as a number. "6 years" said today
becomes `since: 2020-09`, so the answer stays true next year without anyone
maintaining it. Gaps in experience need no modelling: the human's own estimate
already accounts for them, and the back-computed date preserves it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

REUSE = ("always", "per_archetype", "never")


def normalise(question: str) -> str:
    """Questions differ by punctuation and case across every ATS."""
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", question.lower()).split())


def since_from_years(years: float, today: date | None = None) -> str:
    """"6 years" said today -> the month it must have started."""
    today = today or date.today()
    months = int(round(years * 12))
    total = today.year * 12 + (today.month - 1) - months
    return f"{total // 12:04d}-{total % 12 + 1:02d}"


def years_since(since: str, today: date | None = None,
                granularity: float = 0.5) -> float:
    """Rounded to `granularity`, and NEVER up by more than half a step.

    Overstating tenure on a formal application is not the economy to make, so
    the rounding is deliberately asymmetric: 5.9 rounds to 5.5, not 6.0.
    """
    today = today or date.today()
    y, m = (int(p) for p in str(since).split("-")[:2])
    months = (today.year - y) * 12 + (today.month - m)
    return max(0.0, (months / 12) // granularity * granularity)


def format_years(value: float, field_type: str, options: list[str] | None = None):
    """One stored value, whatever shape the form wants."""
    if field_type == "integer":
        return str(int(value))
    if field_type == "range" and options:
        for option in options:
            nums = [float(n) for n in re.findall(r"\d+(?:\.\d+)?", option)]
            if len(nums) == 2 and nums[0] <= value <= nums[1]:
                return option
            if len(nums) == 1 and ("+" in option or "more" in option.lower()):
                if value >= nums[0]:
                    return option
        return options[-1]
    if field_type == "text":
        return f"{int(value)}+ years"
    return f"{value:g}"


@dataclass
class Match:
    slot: str
    confidence: str          # "exact" | "alias" | "none"

    @property
    def certain(self) -> bool:
        return self.confidence in ("exact", "alias")


def find(question: str, bank: list[dict]) -> Match:
    """Exact wording or a declared alias only.

    No fuzzy fallback on purpose. A near-match that fills the wrong field is
    invisible until an employer reads it, while an extra question is a
    ten-second cost the human sees immediately.
    """
    asked = normalise(question)
    for entry in bank:
        if normalise(entry.get("question", "")) == asked:
            return Match(entry["slot"], "exact")
    for entry in bank:
        if any(normalise(a) == asked for a in entry.get("aliases") or []):
            return Match(entry["slot"], "alias")
    return Match("", "none")


def value_of(entry: dict, field_type: str | None = None,
             options: list[str] | None = None, today: date | None = None):
    """The answer, in the shape the field wants."""
    field_type = field_type or entry.get("type", "text")
    if "since" in entry:
        years = years_since(entry["since"], today, entry.get("granularity", 0.5))
        return format_years(years, field_type, options)
    return entry.get("value")


def learn(bank: list[dict], question: str, answer: str, slot: str | None = None,
          reuse: str = "always", field_type: str = "text",
          today: date | None = None) -> dict:
    """Record an answer.

    The question is usually already in the bank with nothing filled in — the
    standard set is created empty — so this fills that entry rather than
    adding a second one. A question the bank has never seen becomes a new
    slot, and a new wording of a known slot becomes an alias.
    """
    if reuse not in REUSE:
        raise ValueError(f"reuse must be one of {REUSE}")

    match = find(question, bank)
    entry = next((e for e in bank if e["slot"] == match.slot), None) \
        if match.certain else None

    if entry is None and slot:
        entry = next((e for e in bank if e["slot"] == slot), None)
        if entry is not None:
            entry.setdefault("aliases", []).append(question)

    if entry is None:
        entry = {"slot": slot or normalise(question).replace(" ", "_")[:40],
                 "question": question, "type": field_type, "reuse": reuse}
        bank.append(entry)

    _apply(entry, answer, today)
    return entry


def _apply(entry: dict, answer: str, today: date | None) -> None:
    """A tenure is stored as the date it started, so it stays true next year."""
    years = re.match(r"^\s*(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)\b",
                     str(answer), re.I)
    if years:
        entry["stated"] = str(answer)
        entry["stated_at"] = str(today or date.today())
        entry["since"] = since_from_years(float(years.group(1)), today)
        entry["granularity"] = 0.5
        entry["type"] = "number"
        entry.pop("value", None)
    else:
        entry["value"] = answer
        entry.pop("since", None)


def unanswered(questions: list[str], bank: list[dict]) -> list[str]:
    """Everything to put in one batch, rather than interrupting per field."""
    return [q for q in questions if not find(q, bank).certain]
