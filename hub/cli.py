"""Command line entry point.

Deterministic only (D21). Anything needing a model belongs in a Claude Code
skill, not here.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from hub import config, render


def cmd_render(args: argparse.Namespace) -> int:
    cfg = config.load()
    tailoring = Path(args.tailoring) if args.tailoring else None
    out = Path(args.out) if args.out else None

    if args.app:
        folder = cfg.applications / args.app
        if not folder.is_dir():
            print(f"no such application: {folder}", file=sys.stderr)
            return 1
        tailoring = tailoring or folder / "tailoring.yaml"
        out = out or folder / "cv.tex"

    out = out or config.ROOT / "output" / "cv.tex"
    return render.build(out, tailoring=tailoring, compile_pdf=not args.no_pdf)


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
    r.add_argument("--out", help="output .tex path")
    r.add_argument("--no-pdf", action="store_true")
    r.set_defaults(func=cmd_render)

    c = sub.add_parser("config", help="show resolved configuration")
    c.set_defaults(func=cmd_config)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
