"""Per-application bullet overrides: rewording and merging.

The master is never edited. An application that needs a bullet phrased for its
vacancy declares the new text in its own tailoring file, together with the
bullets it derives from:

    bullets:
      northwind.1:
        from: [northwind.1]
        text: "Developed proactive data quality controls…"
      northwind.merged:
        from: [northwind.0, northwind.2]
        text: "…"

`from` is not documentation. The fact gate checks an override against those
bullets ALONE (D40a), never against the whole master — otherwise a metric
belonging to one employer could migrate into another employer's bullet and
still pass, because the number exists "somewhere".

A merged override takes the position of its earliest source, and the other
sources drop out.
"""
from __future__ import annotations

from dataclasses import dataclass

from hub import factgate


class OverrideError(ValueError):
    pass


def bullet_index(master: dict) -> dict[str, str]:
    """Every bullet in the master, addressable as `<entry id>.<index>`."""
    out: dict[str, str] = {}
    for section in ("experience", "projects"):
        for entry in master.get(section) or []:
            for i, text in enumerate(entry.get("bullets") or []):
                out[f"{entry['id']}.{i}"] = " ".join(str(text).split())
    return out


def validate(master: dict, overrides: dict) -> None:
    """Fail loudly on an override that cannot be checked.

    An override with no `from`, or one naming a bullet that does not exist,
    would otherwise be checked against nothing and pass by default — the
    quiet failure this whole gate exists to prevent.
    """
    index = bullet_index(master)
    for key, spec in (overrides or {}).items():
        if not isinstance(spec, dict) or "text" not in spec:
            raise OverrideError(f"override {key!r}: needs a `text`")
        sources = spec.get("from")
        if not sources:
            raise OverrideError(
                f"override {key!r}: needs `from` listing the bullets it derives "
                f"from — without it there is nothing to check it against"
            )
        for src in sources:
            if src not in index:
                raise OverrideError(
                    f"override {key!r}: `from` names {src!r}, which is not a "
                    f"bullet in the master"
                )
        entry_id = key.split(".")[0]
        for src in sources:
            if src.split(".")[0] != entry_id:
                raise OverrideError(
                    f"override {key!r}: derives from {src!r}, a different "
                    f"entry. Merging across employers is not a rewording."
                )


def resolve(entry: dict, overrides: dict, drop: set[str]) -> list[str]:
    """Final bullet texts for one entry, after drops, rewording and merges."""
    entry_id = entry["id"]
    mine = {k: v for k, v in (overrides or {}).items()
            if k.split(".")[0] == entry_id}

    # A source consumed by a merge disappears unless it is the anchor.
    consumed: set[str] = set()
    anchors: dict[str, str] = {}
    for key, spec in mine.items():
        sources = list(spec["from"])
        anchor = min(sources, key=lambda s: int(s.split(".")[1]))
        anchors[anchor] = key
        consumed.update(s for s in sources if s != anchor)

    out = []
    for i, text in enumerate(entry.get("bullets") or []):
        bid = f"{entry_id}.{i}"
        if bid in drop or bid in consumed:
            continue
        key = anchors.get(bid)
        out.append(mine[key]["text"] if key else text)
    return [" ".join(str(t).split()) for t in out]


@dataclass
class Violation:
    key: str
    result: factgate.Result


def verify(master: dict, overrides: dict, allow: set[str] | None = None
           ) -> list[Violation]:
    """Check each override against its declared sources only (D40a)."""
    index = bullet_index(master)
    out = []
    for key, spec in (overrides or {}).items():
        source = " ".join(index[s] for s in spec["from"])
        result = factgate.verify(spec["text"], source, allow=allow)
        if not result.ok:
            out.append(Violation(key, result))
    return out
