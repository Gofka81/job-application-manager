"""Fact gate tests.

The edge cases here are career-ops' (MIT), carried over deliberately: each one
was a real bug found in review there, and D51 says the tests are worth more
than the code.
"""
from __future__ import annotations

from hub import factgate as g

SOURCE = (
    "Migrated 70+ batch workflows to AWS using EMR, Glue, S3 and Delta Lake. "
    "Reduced storage costs by 12% annually. "
    "Ensured data accuracy for 100,000+ customers."
)


class TestNumbers:
    def test_thousands_separator_is_normalised(self):
        assert "100000" in g.numbers("100,000 customers")

    def test_magnitude_suffix_is_expanded_not_dropped(self):
        # "50k users" once normalised to "50 users", so a CV claiming 50k
        # matched a source saying 50 — a 1000x inflation passing the gate
        # while a smaller "900 users" was correctly caught.
        assert "50000" in g.numbers("50k users")
        assert "50" not in g.numbers("50k users")

    def test_units_are_kept_with_the_number(self):
        assert g.numbers("5TB of data") == {"5tb"}
        assert g.numbers("12% annually") == {"12%"}

    def test_non_ascii_digits_still_produce_claims(self):
        # A CV written in Arabic-Indic or Devanagari digits produced ZERO
        # claims, so the gate reported a pass having checked nothing.
        assert g.numbers("١٨% growth") == {"18%"}
        assert g.numbers("९००० users") == {"9000"}


class TestNames:
    def test_products_and_acronyms_are_caught(self):
        found = g.names("using EMR, Glue, S3 and PySpark")
        assert {"emr", "glue", "s3", "pyspark"} <= found

    def test_sentence_opening_word_is_not_a_proper_noun(self):
        assert "migrated" not in g.names("Migrated 70 workflows")
        assert "delivered" not in g.names("Delivered a pipeline")

    def test_case_of_the_trigger_does_not_hide_a_name(self):
        # Patterns keyed to "Worked at" missed "worked at" — i.e. exactly the
        # spelling CVs are written in was invisible.
        assert "initech" in g.names("Worked at Initech as an engineer")
        assert "initech" in g.names("he worked at Initech as an engineer")

    def test_extraction_is_symmetric(self):
        text = "Delivered 12% savings on AWS"
        assert g.names(text) == g.names(text)
        assert g.numbers(text) == g.numbers(text)


class TestVerify:
    def test_passes_a_faithful_rewrite(self):
        r = g.verify("Cut storage costs 12% by moving workloads onto S3", SOURCE)
        assert r.ok, r.report()

    def test_catches_an_invented_client_name(self):
        # The one real fabrication found across 29 tailored applications.
        r = g.verify("Migrated 70+ workflows for Contoso", SOURCE)
        assert not r.ok and r.invented_names == {"contoso"}

    def test_catches_an_invented_number(self):
        r = g.verify("Reduced storage costs by 40% annually", SOURCE)
        assert r.invented_numbers == {"40%"}

    def test_catches_a_technology_the_source_lacks(self):
        r = g.verify("Ran the pipelines on Kubernetes", SOURCE)
        assert r.invented_names == {"kubernetes"}

    def test_framing_language_passes_on_purpose(self):
        # The gate's deliberate blind spot: a characterisation layered onto a
        # real fact is what anyone writing their own CV does (D40).
        r = g.verify(
            "Migrated 70+ batch workflows to AWS, ensuring trusted, reliable "
            "data delivery in a strict compliance environment",
            SOURCE,
        )
        assert r.ok, r.report()

    def test_allow_list_admits_a_known_exception(self):
        assert g.verify("Ran on Kubernetes", SOURCE, allow={"Kubernetes"}).ok

    def test_scoped_source_stops_a_metric_migrating(self):
        """D40a: an override is checked against its declared origin only."""
        northwind = "Reduced storage costs by 12% annually."
        fabrikam = "Cut downtime by 50% across CRM pipelines."
        assert g.verify("Cut downtime by 50%", fabrikam).ok
        # The same sentence attached to the other employer's bullet is not.
        assert g.verify("Cut downtime by 50%", northwind).invented_numbers == {"50%"}

    def test_report_names_the_remedy(self):
        r = g.verify("Worked for Contoso", SOURCE)
        assert "contoso" in r.report() and "master-profile.yaml" in r.report()
