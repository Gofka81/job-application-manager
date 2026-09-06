"""Rebuilding an application's CV from the .tex sitting next to it.

The compile is shelled out, so these cover the decisions around it: what
counts as a usable build, what happens when the folder is not ready, and
which lines of a LaTeX log are worth a human's attention.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from hub import latex


class Ran:
    """A stand-in for latexmk that records how it was called."""

    def __init__(self, code=0, out="", makes=None):
        self.code, self.out, self.makes = code, out, makes
        self.calls = []

    def __call__(self, command, cwd=None, **kw):
        self.calls.append((command, cwd))
        if self.makes:
            (Path(cwd) / self.makes).write_bytes(b"%PDF-1.4")
        return subprocess.CompletedProcess(command, self.code,
                                           stdout=self.out, stderr="")


@pytest.fixture
def folder(tmp_path):
    app = tmp_path / "2026-09-06--northwind--data-engineer"
    app.mkdir()
    (app / "cv.tex").write_text("\\documentclass{resume}")
    (app / "resume.cls").write_text("class")
    return app


@pytest.fixture
def latexmk(monkeypatch):
    monkeypatch.setattr(latex.shutil, "which", lambda name: "/usr/bin/latexmk")

    def install(runner):
        monkeypatch.setattr(latex.subprocess, "run", runner)
        return runner
    return install


class TestCompile:
    def test_a_successful_run_yields_the_pdf(self, folder, latexmk):
        latexmk(Ran(makes="cv.pdf"))
        built = latex.compile_tex(folder)
        assert built.ok and built.pdf == folder / "cv.pdf"

    def test_it_builds_inside_the_application_folder(self, folder, latexmk):
        """Never in data/master/: the master template is not per-vacancy."""
        ran = latexmk(Ran(makes="cv.pdf"))
        latex.compile_tex(folder)
        assert ran.calls[0][1] == folder and "cv.tex" in ran.calls[0][0]

    def test_a_failed_run_is_not_ok_even_with_a_pdf_present(self, folder,
                                                            latexmk):
        """latexmk leaves the previous PDF in place, so its existence proves
        nothing about this run."""
        (folder / "cv.pdf").write_bytes(b"%PDF stale")
        latexmk(Ran(code=1, out="! Undefined control sequence."))
        assert latex.compile_tex(folder).ok is False

    def test_a_failed_run_leaves_the_old_pdf_alone(self, folder, latexmk):
        (folder / "cv.pdf").write_bytes(b"%PDF stale")
        latexmk(Ran(code=1))
        latex.compile_tex(folder)
        assert (folder / "cv.pdf").read_bytes() == b"%PDF stale"

    def test_no_tex_is_a_build_error_not_a_crash(self, folder, latexmk):
        latexmk(Ran(makes="cv.pdf"))
        (folder / "cv.tex").unlink()
        with pytest.raises(latex.BuildError, match="no cv.tex"):
            latex.compile_tex(folder)

    def test_a_missing_class_file_is_copied_from_the_master(self, folder,
                                                            latexmk, tmp_path):
        latexmk(Ran(makes="cv.pdf"))
        master = tmp_path / "master"
        master.mkdir()
        (master / "resume.cls").write_text("the one true class")
        (folder / "resume.cls").unlink()
        latex.compile_tex(folder, master)
        assert (folder / "resume.cls").read_text() == "the one true class"

    def test_no_class_anywhere_says_so(self, folder, latexmk, tmp_path):
        latexmk(Ran(makes="cv.pdf"))
        (folder / "resume.cls").unlink()
        with pytest.raises(latex.BuildError, match="resume.cls"):
            latex.compile_tex(folder, tmp_path / "master")

    def test_a_missing_latexmk_names_itself(self, folder, monkeypatch):
        monkeypatch.setattr(latex.shutil, "which", lambda name: None)
        with pytest.raises(latex.BuildError, match="latexmk not found"):
            latex.compile_tex(folder)


class TestErrors:
    LOG = """
This is pdfTeX, Version 3.141592653
Package hyperref Warning: something harmless
! Undefined control sequence.
l.4 \\undefinedcommandhere
!  ==> Fatal error occurred, no output PDF file produced!
"""

    def test_it_picks_the_lines_that_say_what_broke(self):
        lines = latex.errors(self.LOG)
        assert "! Undefined control sequence." in lines
        assert "l.4 \\undefinedcommandhere" in lines

    def test_it_leaves_out_the_package_chatter(self):
        assert not any("pdfTeX, Version" in line
                       for line in latex.errors(self.LOG))

    def test_it_stops_rather_than_printing_the_whole_log(self):
        assert len(latex.errors("! bad\n" * 200, limit=5)) == 5

    def test_a_log_with_no_error_lines_still_shows_something(self):
        """Silence is the least useful thing to hand back."""
        assert latex.errors("nothing\nof\nnote\n") == ["nothing", "of", "note"]


class TestClean:
    def test_it_removes_latexmk_working_files(self, folder):
        for suffix in (".aux", ".log", ".fls"):
            (folder / f"cv{suffix}").write_text("x")
        assert latex.clean(folder) == 3

    def test_it_leaves_the_things_worth_keeping(self, folder):
        (folder / "cv.pdf").write_text("x")
        (folder / "cv.aux").write_text("x")
        latex.clean(folder)
        assert (folder / "cv.pdf").exists() and (folder / "cv.tex").exists()
