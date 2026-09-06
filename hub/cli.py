"""Command line entry point.

Deterministic only (D21). Anything needing a model belongs in a Claude Code
skill, not here.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

from hub import answerbank, backfill, bootstrap, check as check_mod, config, coverage, render


def cmd_render(args: argparse.Namespace) -> int:
    cfg = config.load()
    tailoring = Path(args.tailoring) if args.tailoring else None
    out = Path(args.out) if args.out else None

    jd = Path(args.jd) if args.jd else None

    if args.app:
        folder = cfg.applications / args.app
        if not folder.is_dir():
            print(f"no such application: {folder}", file=sys.stderr)
            return 1
        tailoring = tailoring or folder / "tailoring.yaml"
        jd = jd or folder / "jd.md"
        out = out or folder / "cv.tex"

    out = out or config.ROOT / "output" / "cv.tex"
    return render.build(out, tailoring=tailoring, jd=jd,
                        compile_pdf=not args.no_pdf)


def cmd_check(args: argparse.Namespace) -> int:
    """Check finished CVs against the master, whatever produced them."""
    cfg = config.load()
    master = yaml.safe_load(cfg.master_profile.read_text())
    source = render.source_text(master)
    ident = master.get("identity", {})
    contact = [ident.get("email")] if args.contact else []
    allow = set(cfg.factgate_allow)

    targets = []
    for raw in args.paths:
        p = Path(raw)
        targets.extend(sorted(p.rglob("*.pdf")) if p.is_dir() else [p])
    if not targets:
        print("nothing to check", file=sys.stderr)
        return 1

    failed = 0
    for pdf in targets:
        try:
            report = check_mod.check(pdf, source, contact, allow, args.max_pages)
        except check_mod.atscheck.ExtractorMissing as exc:
            print(exc, file=sys.stderr)
            return 1
        print(report.report())
        failed += not report.ok
    if len(targets) > 1:
        print(f"\n{len(targets) - failed}/{len(targets)} pass")
    return 3 if failed else 0


def cmd_backfill(args: argparse.Namespace) -> int:
    """Recover coverage records from tailor-cv's prose logs."""
    cfg = config.load()
    folders = sorted(p for p in cfg.applications.iterdir() if p.is_dir())
    written = skipped = 0
    for folder in folders:
        doc = backfill.convert(folder)
        if doc is None:
            skipped += 1
            continue
        out = folder / "coverage.yaml"
        if out.exists() and not args.force:
            skipped += 1
            continue
        if args.apply:
            out.write_text(
                "# Recovered from changes.md. `evidence` is absent because the\n"
                "# prose names bullets in words, not master ids (see hub/backfill.py).\n"
                + yaml.safe_dump(doc, sort_keys=False, allow_unicode=True,
                                 width=88))
        written += 1
        n = len(doc["requirements"])
        miss = sum(r["status"] == "missing" for r in doc["requirements"])
        print(f"{folder.name}: {n} requirements, {miss} missing")
    verb = "wrote" if args.apply else "would write"
    print(f"\n{verb} {written}, skipped {skipped}")
    if not args.apply:
        print("re-run with --apply to write the files")
    return 0


def cmd_answers(args: argparse.Namespace) -> int:
    """Show the answer bank, or create it from the standard question set."""
    cfg = config.load()
    path = cfg.data / "answer-bank.yaml"

    if args.init:
        if path.exists() and not args.force:
            print(f"{path} exists; --force to overwrite", file=sys.stderr)
            return 1
        path.parent.mkdir(parents=True, exist_ok=True)
        entries = bootstrap.starter()
        filled = 0
        if cfg.master_profile.exists():
            master = yaml.safe_load(cfg.master_profile.read_text())
            filled = bootstrap.prefill(entries, master)
        path.write_text(bootstrap.HEADER + yaml.safe_dump(
            entries, sort_keys=False, allow_unicode=True, width=88))
        print(f"wrote {len(entries)} questions to {path}, "
              f"{filled} answered from the master profile")
        print("fill in the values you know; the rest are learned as they come up")
        return 0

    if not path.exists():
        print(f"no answer bank at {path} — run `jam answers --init`",
              file=sys.stderr)
        return 1

    bank = yaml.safe_load(path.read_text()) or []
    answered = [e for e in bank
                if e.get("value") is not None or e.get("since")]
    print(f"{len(answered)}/{len(bank)} answered")
    if args.missing:
        for e in bank:
            if e.get("value") is None and not e.get("since"):
                print(f"  [{e['reuse']:<13}] {e['question']}")
    return 0


def cmd_coverage(args: argparse.Namespace) -> int:
    cfg = config.load()
    folder = cfg.applications / args.app
    path = folder / "coverage.yaml"
    if not path.exists():
        print(f"no coverage file: {path}", file=sys.stderr)
        return 1
    master = yaml.safe_load(cfg.master_profile.read_text())
    doc = coverage.load(path)
    try:
        coverage.validate(master, doc)
    except coverage.CoverageError as exc:
        print(f"coverage: {exc}", file=sys.stderr)
        return 1
    print(coverage.summarize(doc).report())
    return 0


def cmd_gaps(args: argparse.Namespace) -> int:
    """What the market asked for that the master does not hold.

    Needs no outcomes: the unit of observation is a requirement, and there
    are hundreds of those across a search.
    """
    cfg = config.load()
    required, preferred, seen = coverage.aggregate(cfg.applications)
    if not seen:
        print("no applications have recorded coverage yet")
        return 0
    if args.terms:
        counts = coverage.terms(cfg.applications, args.min_count)
        print(f"terms recurring in gaps across {seen} application(s)\n")
        for term, n in counts.most_common():
            print(f"  {n:3}x  {term}")
        return 0
    print(f"across {seen} application(s) with recorded coverage\n")
    for label, counter in (("required", required), ("preferred", preferred)):
        rows = [(t, n) for t, n in counter.most_common() if n >= args.min_count]
        print(f"missing, {label}:" if rows
              else f"missing, {label}: nothing at or above {args.min_count}")
        for text, n in rows:
            print(f"  {n:3}x  {text}")
        print()
    return 0


def cmd_config(args: argparse.Namespace) -> int:
    cfg = config.load()
    print(f"data       {cfg.data}")
    print(f"templates  {cfg.templates}")
    print(f"stale      {cfg.thresholds.stale_days}d")
    print(f"ghosted    {cfg.thresholds.ghosted_days}d")
    print(f"followup   max {cfg.followup.max_touches_per_company} per company, "
          f"{cfg.followup.min_days_between}d apart")
    if not cfg.master_profile.exists():
        print(f"MISSING    {cfg.master_profile}", file=sys.stderr)
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="jam", description="Job Application Hub")
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("render", help="render a CV from the master profile")
    r.add_argument("--app", help="application id; uses its tailoring.yaml")
    r.add_argument("--tailoring", help="explicit tailoring file")
    r.add_argument("--jd", help="job description, for alias resolution")
    r.add_argument("--out", help="output .tex path")
    r.add_argument("--no-pdf", action="store_true")
    r.set_defaults(func=cmd_render)

    ck = sub.add_parser("check", help="check finished CV PDFs against the master")
    ck.add_argument("paths", nargs="+", help="PDF files or directories to scan")
    ck.add_argument("--max-pages", type=int)
    ck.add_argument("--contact", action="store_true",
                    help="also require the contact email to extract")
    ck.set_defaults(func=cmd_check)

    an = sub.add_parser("answers", help="the answer bank for application forms")
    an.add_argument("--init", action="store_true", help="create from the standard set")
    an.add_argument("--force", action="store_true")
    an.add_argument("--missing", action="store_true", help="list unanswered questions")
    an.set_defaults(func=cmd_answers)

    bf = sub.add_parser("backfill", help="recover coverage records from changes.md")
    bf.add_argument("--apply", action="store_true")
    bf.add_argument("--force", action="store_true", help="overwrite existing")
    bf.set_defaults(func=cmd_backfill)

    cv = sub.add_parser("coverage", help="validate and summarise an application's coverage")
    cv.add_argument("--app", required=True)
    cv.set_defaults(func=cmd_coverage)

    g = sub.add_parser("gaps", help="what the market wants that the master lacks")
    g.add_argument("--min-count", type=int, default=1)
    g.add_argument("--terms", action="store_true",
                   help="count terms inside gaps rather than whole phrases")
    g.set_defaults(func=cmd_gaps)

    c = sub.add_parser("config", help="show resolved configuration")
    c.set_defaults(func=cmd_config)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
