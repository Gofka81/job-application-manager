"""Checking a finished CV, whatever produced it.

The dictionary is injected rather than read from the system, so these tests
behave the same everywhere.
"""
from __future__ import annotations

from pathlib import Path

from hub import check

DICT = frozenset({"testing", "design", "monitoring", "kingdom", "contribute",
                  "source", "extract", "consult", "monitor", "advance"})


def ordinary(token, text=""):
    return check.is_ordinary(token, text, DICT)


class TestNoise:
    def test_a_capitalised_ordinary_word_is_filtered(self):
        """Every word in a skills line is capitalised, so without this the
        handful that matter are buried."""
        assert ordinary("testing") and ordinary("design")

    def test_an_inflected_form_is_filtered_too(self):
        # The dictionary holds base forms; "contributed" would otherwise read
        # as a proper noun.
        assert ordinary("contributed") and ordinary("sourced")
        assert ordinary("extracts") and ordinary("monitoring")

    def test_a_short_stem_is_not_stretched_to_a_match(self):
        assert not ordinary("ing")


class TestSignal:
    def test_a_technology_that_is_also_a_word_survives(self):
        """Hiding Kafka or Snowflake is the one failure this cannot have."""
        for tech in ("kafka", "snowflake", "etl", "elt", "spark", "delta"):
            assert not ordinary(tech), tech

    def test_an_acronym_survives_even_if_it_spells_a_word(self):
        assert not ordinary("iam", "IAM policies and roles")

    def test_a_token_with_a_digit_survives(self):
        assert not ordinary("s3") and not ordinary("spark3")

    def test_an_unknown_word_survives(self):
        assert not ordinary("dataops") and not ordinary("pyspark")

    def test_without_a_dictionary_nothing_is_filtered(self):
        """Noisy but safe: a missing word list must not hide claims."""
        assert not check.is_ordinary("testing", "", frozenset())


class TestReport:
    def make(self, **kw):
        return check.Report(path=Path("cv.pdf"), chars=100, pages=1, **kw)

    def test_a_clean_report_passes(self):
        assert self.make().ok

    def test_no_extracted_text_fails(self):
        r = check.Report(path=Path("cv.pdf"), chars=0)
        assert not r.ok and "not selectable" in r.report()

    def test_a_ligature_fails(self):
        r = self.make(ligatures={"ﬂ"})
        assert not r.ok and "unsearchable" in r.report()

    def test_missing_contact_fails(self):
        r = self.make(missing_contact=["ada@example.com"])
        assert not r.ok and "contact details missing" in r.report()

    def test_over_the_page_budget_fails(self):
        r = check.Report(path=Path("cv.pdf"), chars=100, pages=2, max_pages=1)
        assert not r.ok and "budget is 1" in r.report()

    def test_the_budget_is_optional(self):
        assert check.Report(path=Path("cv.pdf"), chars=100, pages=3).ok
