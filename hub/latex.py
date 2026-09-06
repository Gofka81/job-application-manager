"""Rebuild an application's CV from the .tex sitting next to it.

`jam render` builds from the master profile through the tailoring spec. This
is the other half: an application folder holds its own `cv.tex`, edited by
hand or by the agent, and after any edit the PDF beside it is stale. Without
this the only way to refresh it was to remember the latexmk invocation and
run it in the right directory, which is exactly the kind of thing that gets
skipped and leaves a folder claiming a CV it no longer has.

Compiling is separate from checking on purpose: a build that fails LaTeX and
a build that fails the page budget are different problems, and collapsing
them into one boolean loses which one happened.
"""
from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

ARTIFACTS = (".aux", ".fdb_latexmk", ".fls", ".log", ".out", ".synctex.gz")


class BuildError(RuntimeError):
    """The folder is not in a state that can be built."""


@dataclass
class Built:
    pdf: Path
    log: str

    @property
    def ok(self) -> bool:
        return self.pdf.exists()


def compile_tex(folder: Path, master: Path | None = None) -> Built:
    """Run latexmk over `folder/cv.tex`, returning the PDF and the log tail.

    `resume.cls` is copied from the master when the folder lacks it. The class
    file is deliberately not tailored per application (every application has
    to look like it came from the same person), so a missing one is an
    oversight rather than a decision.
    """
    tex = folder / "cv.tex"
    if not tex.exists():
        raise BuildError(f"no cv.tex in {folder.name}")

    cls = folder / "resume.cls"
    if not cls.exists():
        if master is None or not (master / "resume.cls").exists():
            raise BuildError("no resume.cls, and none in the master to copy")
        shutil.copy(master / "resume.cls", cls)

    if not shutil.which("latexmk"):
        raise BuildError("latexmk not found — install a TeX distribution")

    r = subprocess.run(
        ["latexmk", "-pdf", "-interaction=nonstopmode", "-halt-on-error",
         tex.name],
        cwd=folder, capture_output=True, text=True,
    )
    log = (r.stdout + r.stderr)[-3000:]
    pdf = folder / "cv.pdf"
    if r.returncode != 0:
        # latexmk leaves the previous PDF in place on failure, so its
        # existence proves nothing about this run.
        return Built(pdf=Path(folder / "cv.pdf.__failed__"), log=log)
    return Built(pdf=pdf, log=log)


def errors(log: str, limit: int = 12) -> list[str]:
    """The lines of a LaTeX log worth showing a human.

    A failed run prints hundreds of lines of package chatter around the two
    that say what broke.
    """
    out = []
    for line in log.splitlines():
        if line.startswith("!") or line.startswith("l.") or "Error" in line:
            out.append(line.strip())
        if len(out) >= limit:
            break
    return out or [line.strip() for line in log.splitlines()[-limit:] if line.strip()]


def clean(folder: Path) -> int:
    """Drop latexmk's working files. Returns how many went."""
    gone = 0
    for suffix in ARTIFACTS:
        path = folder / f"cv{suffix}"
        if path.exists():
            path.unlink()
            gone += 1
    return gone
