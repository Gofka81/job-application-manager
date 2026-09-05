"""Per-application overrides: rewording, merging, and the scoped check."""
from __future__ import annotations

import pytest

from hub import overrides as ov

MASTER = {
    "experience": [
        {"id": "northwind", "bullets": [
            "Cut storage costs by 12% annually",
            "Built data quality checks across pipelines",
            "Migrated 70+ workflows onto EMR",
        ]},
        {"id": "fabrikam", "bullets": ["Reduced downtime by 50% on Databricks"]},
    ],
    "projects": [{"id": "widget", "bullets": ["Shipped a thing"]}],
}


def entry(eid):
    for s in ("experience", "projects"):
        for e in MASTER[s]:
            if e["id"] == eid:
                return e


class TestIndex:
    def test_addresses_experience_and_projects(self):
        idx = ov.bullet_index(MASTER)
        assert idx["northwind.0"].startswith("Cut storage")
        assert idx["fabrikam.0"].startswith("Reduced downtime")
        assert idx["widget.0"] == "Shipped a thing"


class TestValidate:
    def test_rejects_an_override_with_no_provenance(self):
        """Without `from` there is nothing to check against, so it would pass
        by default — the quiet failure the gate exists to prevent."""
        with pytest.raises(ov.OverrideError, match="needs `from`"):
            ov.validate(MASTER, {"northwind.0": {"text": "anything"}})

    def test_rejects_a_source_that_does_not_exist(self):
        with pytest.raises(ov.OverrideError, match="not a bullet"):
            ov.validate(MASTER, {"northwind.0": {"from": ["northwind.9"],
                                                 "text": "x"}})

    def test_rejects_merging_across_employers(self):
        with pytest.raises(ov.OverrideError, match="different"):
            ov.validate(MASTER, {"northwind.m": {
                "from": ["northwind.0", "fabrikam.0"], "text": "x"}})

    def test_rejects_a_missing_text(self):
        with pytest.raises(ov.OverrideError, match="needs a `text`"):
            ov.validate(MASTER, {"northwind.0": {"from": ["northwind.0"]}})


class TestResolve:
    def test_a_reword_replaces_in_place(self):
        out = ov.resolve(entry("northwind"),
                         {"northwind.1": {"from": ["northwind.1"],
                                          "text": "Reworded"}}, set())
        assert out[1] == "Reworded" and len(out) == 3

    def test_a_merge_takes_the_earliest_position_and_consumes_the_rest(self):
        out = ov.resolve(entry("northwind"),
                         {"northwind.m": {"from": ["northwind.0", "northwind.2"],
                                          "text": "Merged"}}, set())
        assert out == ["Merged", "Built data quality checks across pipelines"]

    def test_drop_still_applies(self):
        out = ov.resolve(entry("northwind"), {}, {"northwind.1"})
        assert len(out) == 2 and "quality" not in " ".join(out)

    def test_an_entry_of_another_id_is_untouched(self):
        out = ov.resolve(entry("fabrikam"),
                         {"northwind.0": {"from": ["northwind.0"], "text": "X"}},
                         set())
        assert out == ["Reduced downtime by 50% on Databricks"]


class TestVerify:
    def test_a_faithful_reword_passes(self):
        assert not ov.verify(MASTER, {"northwind.0": {
            "from": ["northwind.0"],
            "text": "Reduced storage spend 12% year on year"}})

    def test_catches_an_invented_number_and_name(self):
        v = ov.verify(MASTER, {"northwind.1": {
            "from": ["northwind.1"],
            "text": "Built checks for Contoso, cutting incidents 90%"}})
        assert v[0].result.invented_numbers == {"90%"}
        assert "contoso" in v[0].result.invented_names

    def test_a_metric_cannot_migrate_between_employers(self):
        """D40a in one test: 50% is real, but it belongs to Fabrikam."""
        v = ov.verify(MASTER, {"northwind.0": {
            "from": ["northwind.0"],
            "text": "Cut storage costs by 50% annually"}})
        assert v and v[0].result.invented_numbers == {"50%"}

    def test_a_merge_may_use_facts_from_every_declared_source(self):
        assert not ov.verify(MASTER, {"northwind.m": {
            "from": ["northwind.0", "northwind.2"],
            "text": "Cut costs 12% while migrating 70+ workflows onto EMR"}})
