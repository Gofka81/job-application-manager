"""Structured coverage: validation, scoring, and cross-application aggregation."""
from __future__ import annotations

import pytest
import yaml

from hub import coverage

MASTER = {
    "experience": [{"id": "northwind", "bullets": ["a", "b"]}],
    "skills": {"languages": {"python": {}, "sql": {}}},
    "education": [{"id": "uni"}],
    "certifications": [{"name": "Example Certified"}],
}


def doc(*reqs):
    return {"requirements": list(reqs)}


def req(text="X", weight="required", status="covered", evidence=("skills.python",)):
    return {"text": text, "weight": weight, "status": status,
            "evidence": list(evidence)}


class TestValidate:
    def test_accepts_ids_from_every_part_of_the_master(self):
        coverage.validate(MASTER, doc(
            req(evidence=["northwind.1"]), req(evidence=["skills.sql"]),
            req(evidence=["education.uni"]), req(evidence=["certifications.0"])))

    def test_rejects_evidence_that_does_not_resolve(self):
        with pytest.raises(coverage.CoverageError, match="not an id"):
            coverage.validate(MASTER, doc(req(evidence=["skills.rust"])))

    def test_coverage_must_point_at_something(self):
        """Otherwise 'covered' is an assertion rather than a claim."""
        with pytest.raises(coverage.CoverageError, match="no evidence"):
            coverage.validate(MASTER, doc(req(status="partial", evidence=[])))

    def test_missing_cannot_cite_evidence(self):
        with pytest.raises(coverage.CoverageError, match="cannot cite"):
            coverage.validate(MASTER, doc(req(status="missing")))

    def test_rejects_an_unknown_weight_or_status(self):
        with pytest.raises(coverage.CoverageError, match="weight"):
            coverage.validate(MASTER, doc(req(weight="nice-to-have")))
        with pytest.raises(coverage.CoverageError, match="status"):
            coverage.validate(MASTER, doc(req(status="maybe")))

    def test_rejects_an_empty_file(self):
        with pytest.raises(coverage.CoverageError, match="no `requirements`"):
            coverage.validate(MASTER, {})


class TestSummary:
    def test_partial_counts_as_half(self):
        s = coverage.summarize(doc(req(status="covered"), req(status="partial")))
        assert s.required_covered == 1.5 and s.share == 0.75

    def test_missing_is_listed_by_weight(self):
        s = coverage.summarize(doc(
            req("dbt", status="missing", evidence=[]),
            req("Kafka", "preferred", "missing", [])))
        assert s.missing_required == ["dbt"] and s.missing_preferred == ["Kafka"]

    def test_share_is_none_when_nothing_is_required(self):
        assert coverage.summarize(doc(req(weight="preferred"))).share is None


class TestAggregate:
    def test_counts_missing_across_applications(self, tmp_path):
        for i, missing in enumerate([["dbt", "Kafka"], ["dbt"], ["dbt", "Go"]]):
            app = tmp_path / f"app{i}"
            app.mkdir()
            (app / "coverage.yaml").write_text(yaml.safe_dump(doc(
                *[req(m, status="missing", evidence=[]) for m in missing])))
        required, preferred, seen = coverage.aggregate(tmp_path)
        assert seen == 3
        assert required["dbt"] == 3 and required["kafka"] == 1

    def test_an_application_without_coverage_is_skipped(self, tmp_path):
        (tmp_path / "empty").mkdir()
        (tmp_path / "empty" / "coverage.yaml").write_text("requirements: []\n")
        assert coverage.aggregate(tmp_path)[2] == 0

    def test_wording_is_normalised_so_counts_do_not_split(self, tmp_path):
        for i, text in enumerate(["dbt  models", "DBT models"]):
            app = tmp_path / f"a{i}"
            app.mkdir()
            (app / "coverage.yaml").write_text(yaml.safe_dump(
                doc(req(text, status="missing", evidence=[]))))
        assert coverage.aggregate(tmp_path)[0]["dbt models"] == 2


class TestTerms:
    """Whole phrases undercount: "Microsoft Fabric" and "Fabric" are one gap
    written twice."""

    def write(self, tmp_path, *texts):
        for i, t in enumerate(texts):
            app = tmp_path / f"app{i}"
            app.mkdir()
            (app / "coverage.yaml").write_text(yaml.safe_dump({
                "source": "backfill",
                "requirements": [{"text": t, "weight": "required",
                                  "status": "missing", "evidence": []}]}))
        return tmp_path

    def test_a_term_is_counted_across_different_phrasings(self, tmp_path):
        counts = coverage.terms(self.write(tmp_path, "Microsoft Fabric",
                                           "Fabric and Power BI"), min_count=2)
        assert counts["fabric"] == 2

    def test_the_logs_own_qualifiers_are_dropped(self, tmp_path):
        """"Azure breadth" and "Azure recency" name Azure twice."""
        counts = coverage.terms(self.write(tmp_path, "Azure breadth",
                                           "Azure recency"), min_count=2)
        assert counts["azure"] == 2 and "breadth" not in counts

    def test_ordinary_english_is_kept_here(self, tmp_path):
        """Unlike the CV check: "streaming" and "mentoring" are the signal."""
        counts = coverage.terms(self.write(tmp_path, "Streaming at scale",
                                           "Streaming pipelines"), min_count=2)
        assert counts["streaming"] == 2

    def test_below_the_floor_is_omitted(self, tmp_path):
        assert "kafka" not in coverage.terms(self.write(tmp_path, "Kafka"), 2)

    def test_covered_requirements_are_not_counted(self, tmp_path):
        app = tmp_path / "a"
        app.mkdir()
        (app / "coverage.yaml").write_text(yaml.safe_dump({
            "requirements": [{"text": "Kafka", "weight": "required",
                              "status": "covered", "evidence": ["skills.python"]}]}))
        assert coverage.terms(tmp_path, 1) == {}


class TestBackfillValidation:
    def test_a_backfilled_record_may_omit_evidence(self):
        """The prose names bullets in words, not master ids, so guessing the
        mapping would put unverifiable claims in a file whose point is that
        coverage is checkable."""
        coverage.validate(MASTER, {"source": "backfill", "requirements": [
            {"text": "X", "weight": "required", "status": "covered",
             "evidence": []}]})

    def test_a_fresh_record_still_may_not(self):
        with pytest.raises(coverage.CoverageError, match="no evidence"):
            coverage.validate(MASTER, doc(req(status="covered", evidence=[])))
