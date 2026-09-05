#!/usr/bin/env python3
"""Render a CV from data/master-profile.yaml.

Deterministic core (D21): no model is involved. The master profile is the
single source of truth (D41); tailoring is per application, declared in that
application's tailoring.yaml (D43).

Usage:
    jam render                       # the bare master, for review
    jam render --app 2026-09-05--acme--senior-data-engineer
    jam render --tailoring path/to/tailoring.yaml --out somewhere/cv.tex
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

from hub import atscheck, config, factgate, overrides as ov

MONTHS = {1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "May", 6: "Jun",
          7: "Jul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec"}

# A SINGLE pass, not sequential replaces. Sequential ones re-process their own
# output: "\\" -> "\\textbackslash{}" and then the "{" rule escaped the braces
# that replacement had just introduced, producing "\\textbackslash\\{\\}".
_ESCAPES = {
    "\\": r"\textbackslash{}",
    "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#",
    "_": r"\_", "{": r"\{", "}": r"\}",
    # In CV prose "~18%" means "about 18%", so $\sim$ rather than a raised mark.
    "~": r"$\sim$",
    "^": r"\textasciicircum{}",
}
_ESCAPE_RE = re.compile("|".join(re.escape(k) for k in _ESCAPES))


def tex(text) -> str:
    """Escape a plain string for LaTeX and collapse YAML's folded newlines."""
    s = " ".join(str(text).split())
    return _ESCAPE_RE.sub(lambda m: _ESCAPES[m.group()], s)


def month(value) -> str:
    """2024-08 -> 'Aug 2024'. A null end date means the role is current."""
    if value is None:
        return "Present"
    s = str(value)
    m = re.match(r"^(\d{4})-(\d{1,2})", s)
    if not m:
        return tex(s)
    return f"{MONTHS[int(m.group(2))]} {m.group(1)}"


def flatten_master(node) -> str:
    """Every string the master holds, as one blob for the gate to check against.

    Values only, never keys: a key like `work_authorization` matching a token
    would make the gate MORE permissive, and permissiveness is the wrong
    direction for a check.
    """
    if isinstance(node, dict):
        return " ".join(flatten_master(v) for v in node.values())
    if isinstance(node, list):
        return " ".join(flatten_master(v) for v in node)
    return "" if node is None else f"{node} "


def source_text(master: dict) -> str:
    """What the gate checks a rendered CV against.

    Values alone are not enough: a skill's identity lives in its KEY
    (`spark_sql`), and the renderer prints the display form (`Spark SQL`).
    Both are added, so a real skill is not reported as invented.
    """
    return " ".join([
        flatten_master(master),
        " ".join(flatten_skills(master.get("skills", {}), drop=set())),
        " ".join(k for group in master.get("skills", {}).values() for k in group),
    ])


# Commands whose ARGUMENT is layout, not content. Dropping the command alone
# leaves "0.4in" and "-1.25em" behind, and the gate then reports 0.4 and 1.25
# as invented numbers.
# An ALLOWLIST, so a layout command not named here leaks its argument into the
# checked text as a claim — `\pagestyle{empty}` reported "empty" as a term lost
# in extraction. Add to it when the template gains a command.
_LAYOUT_CMD = re.compile(
    r"\\(?:vspace|hspace|itemsep|documentclass|usepackage|geometry|pagestyle"
    r"|setlength|renewcommand|newcommand|hfill|linespread)\*?"
    r"(?:\[[^\]]*\])?(?:\{[^}]*\})?"
)
_DIMENSION = re.compile(r"-?\d+(?:\.\d+)?\s*(?:in|em|ex|pt|cm|mm)\b")
_ESCAPED = {r"\%": "%", r"\&": "&", r"\$": "$", r"\#": "#", r"\_": "_"}


def strip_tex(tex: str) -> str:
    """Rendered .tex back to prose, so the template is not read as claims."""
    out = re.sub(r"\\href\{[^}]*\}\{([^}]*)\}", r"\1", tex)
    out = _LAYOUT_CMD.sub(" ", out)
    out = re.sub(r"\\begin\{[^}]*\}|\\end\{[^}]*\}", " ", out)
    for a, b in _ESCAPED.items():          # "12\%" would otherwise yield "12"
        out = out.replace(a, b)
    out = re.sub(r"\\[a-zA-Z]+\*?", " ", out)
    out = out.replace("{", " ").replace("}", " ").replace("$", " ")
    return _DIMENSION.sub(" ", out)


# Words the RENDERER emits: section headings, month names, link furniture.
# They are the template's vocabulary, not claims about the candidate, so they
# are exempt. Nothing here is a skill, an employer or a number.
TEMPLATE_WORDS = frozenset(
    {"skills", "work", "experience", "projects", "education", "certifications",
     "present", "link", "gpa", "sim", "github"} | set(MONTHS.values())
)


def link_label(url: str) -> str:
    """Display text for a link: the URL without scheme, www or trailing slash.

    Derived rather than hardcoded — the label must follow the profile, not sit
    in the renderer where changing the profile would leave it stale.
    """
    return re.sub(r"^https?://(www\.)?", "", url).rstrip("/")


def alias_form(label: str, aliases: list[str], jd: str) -> str:
    """Pick the spelling the vacancy itself uses, if it declares one.

    A recruiter's boolean search matches exact strings and does not expand
    synonyms: `AND "ETL"` will not return a CV that says "Data Pipelines".
    Only forms declared in the master are candidates, so this can change how
    a fact is spelled but never what is claimed — the fact gate is satisfied
    by construction.
    """
    if not jd:
        return label
    for form in aliases:
        if re.search(rf"(?<!\w){re.escape(form)}(?!\w)", jd, re.I):
            return form
    return label


def skill_labels(skills: dict, drop: set, jd: str = "") -> list[tuple[str, str]]:
    """(key, printed label) for every skill that survives `drop`."""
    special = {
        "sql": "SQL", "aws": "AWS", "emr": "EMR", "s3": "S3", "hdfs": "HDFS",
        "nosql": "NoSQL", "ci_cd": "CI/CD", "rest_apis": "REST APIs",
        "duckdb": "DuckDB", "postgresql": "PostgreSQL", "fastapi": "FastAPI",
        "pyspark": "PySpark", "numpy": "NumPy", "pytest": "pytest",
        "spark_sql": "Spark SQL", "github_actions": "GitHub Actions",
        "anthropic_api": "Anthropic API", "llama_3_3": "Llama 3.3",
        "relational_db": "Relational DB", "nosql": "NoSQL",
        "event_driven_architectures": "Event-Driven Architectures",
        "azure_data_factory": "Azure Data Factory", "ci_cd": "CI/CD",
    }
    out = []
    for group, entries in skills.items():
        for key, meta in entries.items():
            if key in drop or f"{group}.{key}" in drop:
                continue
            meta = meta or {}
            label = meta.get("display") or special.get(key) or key.replace("_", " ").title()
            label = alias_form(label, meta.get("aliases") or [], jd)
            detail = meta.get("detail")
            out.append((key, f"{label} ({detail})" if detail else label))
    return out


def flatten_skills(skills: dict, drop: set, jd: str = "") -> list[str]:
    return [label for _, label in skill_labels(skills, drop, jd)]


def render(master: dict, profile: dict, jd: str = "") -> str:
    sections = profile.get("sections") or []
    drop = set(profile.get("drop") or [])
    emphasis = [e.lower() for e in (profile.get("emphasis") or [])]
    ident = master["identity"]
    L = []

    L.append(r"\documentclass{resume}")
    L.append(r"\usepackage[left=0.4in,top=0.4in,right=0.4in,bottom=0.4in]{geometry}")
    L.append(rf"\name{{{tex(ident['name'])}}}")
    L.append(rf"\address{{{tex(ident['phone'])} \\ {tex(ident['location'])}}}")
    L.append(
        rf"\address{{\href{{mailto:{ident['email']}}}{{{tex(ident['email'])}}} \\ "
        rf"\href{{{ident['linkedin']}}}{{{tex(link_label(ident['linkedin']))}}} \\ "
        rf"\href{{{ident['github']}}}{{{tex(link_label(ident['github']))}}}}}"
    )
    L.append(r"\begin{document}")

    if "skills" in sections:
        names = flatten_skills(master["skills"], drop, jd)
        # Emphasis only reorders: a skill cannot be introduced here that the
        # master does not hold, so the fact gate stays satisfiable (D44).
        if emphasis:
            names.sort(key=lambda n: 0 if n.lower() in emphasis else 1)
        body = ", ".join(tex(n) for n in names)
        if names:
            body = r"\textbf{" + tex(names[0]) + "}, " + ", ".join(tex(n) for n in names[1:])
        L += [r"\begin{rSection}{SKILLS}", body, r"\end{rSection}", ""]

    if "experience" in sections:
        L.append(r"\begin{rSection}{WORK EXPERIENCE}")
        for job in master["experience"]:
            if job["id"] in drop:
                continue
            span = f"{month(job['from'])} - {month(job.get('to'))}"
            bullets = ov.resolve(job, profile.get("bullets", {}), drop)
            if not bullets:
                continue
            L.append(rf"\textbf{{{tex(job['company'])}}} - {tex(job['title'])} \hfill {span}")
            L.append(r"\begin{itemize}")
            L.append(r"\itemsep -3pt {}")
            for b in bullets:
                L.append(rf"  \item {tex(b)}")
            L += [r"\end{itemize}", ""]
        L += [r"\end{rSection}", ""]

    if "projects" in sections and master.get("projects"):
        L.append(r"\begin{rSection}{PROJECTS}")
        for p in master["projects"]:
            if p["id"] in drop:
                continue
            L.append(
                rf"\textbf{{{tex(p['name'])}}} - {tex(p['tagline'])} "
                rf"\hfill \href{{{p['url']}}}{{GitHub}}"
            )
            L.append(r"\begin{itemize}")
            L.append(r"\itemsep -3pt {}")
            for b in ov.resolve(p, profile.get("bullets", {}), drop):
                L.append(rf"  \item {tex(b)}")
            L += [r"\end{itemize}", ""]
        L += [r"\end{rSection}", ""]

    if "education" in sections:
        L.append(r"\begin{rSection}{Education}")
        rows = []
        for e in master["education"]:
            if e["id"] in drop:
                continue
            right = ", ".join(
                x for x in (e.get("result"), f"GPA {e['gpa']}" if e.get("gpa") else None) if x
            )
            rows.append(
                rf"{{\bf {tex(e['degree'])}}}, {tex(e['institution'])} \hfill {tex(right)}"
            )
        L += ["\\\\\n".join(rows), r"\end{rSection}", ""]

    if "certifications" in sections and master.get("certifications"):
        L.append(r"\begin{rSection}{CERTIFICATIONS}")
        L.append(r"\vspace{-1.25em}")
        for c in master["certifications"]:
            L.append(
                rf"\item{{$\bullet$ {tex(c['name'])}}} "
                rf"{{\href{{{c['url']}}}{{Link!}}\hfill {{{month(c['date'])}}}}}"
            )
        L += [r"\end{rSection}", ""]

    L.append(r"\end{document}")
    return "\n".join(L) + "\n"


def page_count(pdf: Path) -> int | None:
    """Pages in a PDF. poppler if present, otherwise a scan of the raw bytes."""
    try:
        out = subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True)
        for line in out.stdout.splitlines():
            if line.startswith("Pages:"):
                return int(line.split()[1])
    except FileNotFoundError:
        pass
    blob = pdf.read_bytes()
    n = blob.count(b"/Type /Page") - blob.count(b"/Type /Pages")
    return n or None



def drop_set(spec: dict) -> set[str]:
    return set(spec.get("drop") or [])


def alias_swaps(master: dict, spec: dict, jd: str) -> list[str]:
    """Report which skills were printed in the vacancy's own spelling."""
    if not jd:
        return []
    skills, drop = master.get("skills", {}), drop_set(spec)
    plain = dict(skill_labels(skills, drop))
    swapped = [(k, v) for k, v in skill_labels(skills, drop, jd) if v != plain[k]]
    return ([f"aliases -> " + ", ".join(f"{plain[k]} as {v}" for k, v in swapped)]
            if swapped else [])


def default_tailoring() -> dict:
    """Everything the master holds, nothing dropped, no page limit.

    Deliberately NOT a stored profile: a shared default would quietly become
    the fixed version set that D43 removed.
    """
    return {
        "name": "master",
        "sections": ["skills", "experience", "projects", "education",
                     "certifications"],
        "emphasis": [],
        "drop": [],
        "max_pages": None,
    }


def load_tailoring(path: Path | None) -> dict:
    spec = default_tailoring()
    if path is not None:
        declared = yaml.safe_load(path.read_text()) or {}
        # The default carries name="master", so setdefault would never fire —
        # the name has to come from the file, or failing that its folder.
        spec["name"] = declared.get("name") or path.parent.name
        spec.update({k: v for k, v in declared.items() if k != "name"})
    return spec


def build(out: Path, tailoring: Path | None = None, jd: Path | None = None,
          compile_pdf: bool = True) -> int:
    """Render to .tex and optionally to PDF.

    Exit codes: 0 success, 1 missing or malformed input, 2 page limit,
    3 fact gate, 4 ATS extraction, otherwise latexmk's own code.
    """
    cfg = config.load()
    if not cfg.master_profile.exists():
        print(f"no master profile: {cfg.master_profile}", file=sys.stderr)
        return 1
    if tailoring is not None and not tailoring.exists():
        print(f"no tailoring file: {tailoring}", file=sys.stderr)
        return 1

    master = yaml.safe_load(cfg.master_profile.read_text())
    spec = load_tailoring(tailoring)
    allow = TEMPLATE_WORDS | set(cfg.factgate_allow)

    # Overrides are checked FIRST, against their declared sources alone
    # (D40a). The document-level gate below then treats a verified override
    # as legitimate source — its new wording is by definition absent from the
    # master, so it would otherwise fail there.
    try:
        ov.validate(master, spec.get("bullets", {}))
    except ov.OverrideError as exc:
        print(f"tailoring: {exc}", file=sys.stderr)
        return 1
    violations = ov.verify(master, spec.get("bullets", {}), allow=allow)
    for v in violations:
        print(v.result.report(f"override {v.key}"), file=sys.stderr)
    if violations:
        return 3

    jd_text = jd.read_text() if jd and jd.exists() else ""
    for line in alias_swaps(master, spec, jd_text):
        print(line)

    out.parent.mkdir(parents=True, exist_ok=True)
    document = render(master, spec, jd_text)
    out.write_text(document)
    shutil.copy(cfg.templates / "resume.cls", out.parent / "resume.cls")
    print(f"tex  -> {out}")

    # The gate runs BEFORE compilation, so no PDF exists that has not passed
    # it (D36). Human approval comes after the gate, never instead of it.
    verified = " ".join(b["text"] for b in spec.get("bullets", {}).values())
    result = factgate.verify(
        strip_tex(document), source_text(master) + " " + verified, allow=allow
    )
    print(result.report(spec["name"]))
    if not result.ok:
        return 3

    if not compile_pdf:
        return 0

    r = subprocess.run(
        ["latexmk", "-pdf", "-interaction=nonstopmode", "-halt-on-error",
         f"-outdir={out.parent}", out.name],
        cwd=out.parent, capture_output=True, text=True,
    )
    if r.returncode != 0:
        sys.stderr.write(r.stdout[-3000:])
        return r.returncode

    pdf = out.with_suffix(".pdf")

    # A term that does not extract is invisible to the keyword search a
    # recruiter actually runs, however prominent it looks on the page.
    try:
        ats = atscheck.check(
            strip_tex(document), atscheck.extract(pdf),
            [master["identity"].get("email"), master["identity"].get("phone")],
        )
        print(ats.report())
        if not ats.ok:
            return 4
    except atscheck.ExtractorMissing as exc:
        print(f"ats check: skipped — {exc}", file=sys.stderr)

    pages = page_count(pdf)
    print(f"pdf  -> {pdf} ({pages} page{'s' if pages != 1 else ''})")

    # A page limit is a property of the application, not of the author's
    # restraint. Without a fixed version set this and the fact gate are the
    # only structural limits left.
    limit = spec.get("max_pages")
    if limit and pages and pages > limit:
        print(
            f"\nFAIL: tailoring '{spec['name']}' allows {limit} page(s), "
            f"got {pages}.\nTrim via `drop` — a section, a job or project id, "
            f"or a single bullet as `<id>.<index>` (0-based).",
            file=sys.stderr,
        )
        return 2
    return 0

