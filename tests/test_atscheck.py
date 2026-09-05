"""ATS extraction checks.

The check functions are pure so the failure modes can be tested without
compiling anything; one integration test covers the real round trip.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from hub import atscheck, render

RENDERED = "SKILLS Python PySpark EXPERIENCE Northwind Systems workflows EDUCATION"
CONTACT = ["ada@example.com", "+44 0000 000000"]


def extracted(text: str) -> str:
    return text + " ada@example.com +44 0000 000000"


class TestCheck:
    def test_a_clean_round_trip_passes(self):
        r = atscheck.check(RENDERED, extracted(RENDERED), CONTACT)
        assert r.ok, r.report()

    def test_an_empty_extraction_is_caught(self):
        r = atscheck.check(RENDERED, "", CONTACT)
        assert not r.ok and "not selectable" in r.report()

    def test_a_ligature_is_caught_by_the_raw_scan_not_by_lost_tokens(self):
        """Why the ligature check has to stand on its own.

        Our tokeniser NFKC-normalises, so "workﬂows" compares equal to
        "workflows" and nothing registers as lost. An ATS parser may not
        normalise, and then a recruiter's search for "workflows" matches
        nothing. The raw character scan is the only thing that sees it.
        """
        r = atscheck.check(RENDERED,
                           extracted(RENDERED.replace("workflows", "workﬂows")),
                           CONTACT)
        assert "ﬂ" in r.ligatures
        assert not r.lost          # invisible to the token comparison
        assert not r.ok            # caught anyway

    def test_contact_details_that_do_not_extract_are_caught(self):
        r = atscheck.check(RENDERED, RENDERED, CONTACT)
        assert r.missing_contact == CONTACT

    def test_scrambled_reading_order_is_caught(self):
        out = "EDUCATION Python PySpark SKILLS Northwind Systems workflows"
        r = atscheck.check(RENDERED, extracted(out), CONTACT)
        assert not r.ok and "reading order" in r.report()

    def test_tokenising_matches_the_fact_gate(self):
        """Survives extraction and counts as a claim must mean the same."""
        from hub import factgate
        assert atscheck.check("AWS S3", extracted("AWS S3"), []).lost == set()
        assert factgate.tokens("AWS S3") == {"aws", "s3"}


@pytest.mark.skipif(not shutil.which("latexmk") or not shutil.which("pdftotext"),
                    reason="needs latexmk and poppler")
def test_real_pdf_round_trip(tmp_path):
    master = yaml.safe_load(Path("tests/fixtures/master-min.yaml").read_text())
    out = tmp_path / "cv.tex"
    out.write_text(render.render(master, {
        "name": "t", "sections": ["skills", "experience", "projects",
                                  "education", "certifications"],
        "emphasis": [], "drop": [],
    }))
    shutil.copy("templates/resume.cls", tmp_path / "resume.cls")
    subprocess.run(["latexmk", "-pdf", "-interaction=nonstopmode",
                    f"-outdir={tmp_path}", "cv.tex"],
                   cwd=tmp_path, capture_output=True, check=True)
    r = atscheck.check(render.strip_tex(out.read_text()),
                       atscheck.extract(tmp_path / "cv.pdf"),
                       ["ada@example.com"])
    assert r.ok, r.report()
