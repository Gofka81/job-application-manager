"""The answer bank: matching, tenure, and what shape a value takes."""
from __future__ import annotations

from datetime import date

import pytest

from hub import answerbank as ab

TODAY = date(2026, 9, 6)

BANK = [
    {"slot": "sql_years", "question": "Years of experience with SQL",
     "aliases": ["SQL (years)", "How many years of SQL?"],
     "type": "number", "since": "2020-09", "granularity": 0.5,
     "reuse": "always"},
    {"slot": "work_auth", "question": "Do you require sponsorship?",
     "type": "enum", "value": "No", "reuse": "always"},
]


class TestTenure:
    def test_a_stated_number_becomes_a_date(self):
        assert ab.since_from_years(6, TODAY) == "2020-09"

    def test_the_date_reads_back_as_the_same_number(self):
        assert ab.years_since("2020-09", TODAY) == 6.0

    def test_rounding_never_goes_up(self):
        """Overstating tenure on a formal application is not the economy to
        make, so 5.9 is 5.5 rather than 6."""
        since = ab.since_from_years(5.9, TODAY)
        assert ab.years_since(since, TODAY) == 5.5

    def test_it_stays_true_as_time_passes(self):
        """The point of storing a date: nobody maintains the number."""
        assert ab.years_since("2020-09", date(2027, 9, 6)) == 7.0

    def test_a_future_start_is_not_negative(self):
        assert ab.years_since("2030-01", TODAY) == 0.0


class TestShape:
    def test_one_value_serves_every_field_type(self):
        assert ab.format_years(5.5, "number") == "5.5"
        assert ab.format_years(5.5, "integer") == "5"
        assert ab.format_years(5.5, "text") == "5+ years"

    def test_a_range_dropdown_picks_the_bucket(self):
        options = ["1-3", "3-5", "5-10", "10+"]
        assert ab.format_years(5.5, "range", options) == "5-10"
        assert ab.format_years(2, "range", options) == "1-3"

    def test_an_open_ended_bucket_is_matched(self):
        assert ab.format_years(12, "range", ["1-3", "10+"]) == "10+"

    def test_a_value_above_every_bucket_takes_the_last(self):
        assert ab.format_years(99, "range", ["1-3", "3-5"]) == "3-5"


class TestMatching:
    def test_exact_wording_matches(self):
        assert ab.find("Years of experience with SQL", BANK).slot == "sql_years"

    def test_punctuation_and_case_do_not_matter(self):
        assert ab.find("YEARS OF EXPERIENCE WITH SQL?", BANK).certain

    def test_a_declared_alias_matches(self):
        m = ab.find("SQL (years)", BANK)
        assert m.slot == "sql_years" and m.confidence == "alias"

    def test_a_near_miss_does_not_match(self):
        """No fuzzy fallback: a wrong field is invisible until an employer
        reads it, while an extra question costs ten seconds."""
        assert not ab.find("Years of experience with NoSQL", BANK).certain
        assert not ab.find("Rate your SQL skill", BANK).certain


class TestValue:
    def test_tenure_is_computed_not_stored(self):
        assert ab.value_of(BANK[0], "integer", today=TODAY) == "6"

    def test_a_plain_value_is_returned_as_is(self):
        assert ab.value_of(BANK[1]) == "No"


class TestLearning:
    def test_a_new_question_becomes_a_slot(self):
        bank = []
        entry = ab.learn(bank, "Notice period?", "1 month", today=TODAY)
        assert entry["value"] == "1 month" and len(bank) == 1

    def test_a_stated_tenure_is_stored_as_a_date(self):
        bank = []
        entry = ab.learn(bank, "Years of Python?", "6 years", today=TODAY)
        assert entry["since"] == "2020-09" and entry["stated"] == "6 years"
        assert ab.value_of(entry, "number", today=TODAY) == "6"

    def test_a_new_wording_attaches_to_a_known_slot(self):
        bank = [dict(BANK[0])]
        ab.learn(bank, "Total SQL experience", "6 years", slot="sql_years")
        assert len(bank) == 1
        assert "Total SQL experience" in bank[0]["aliases"]

    def test_a_question_already_known_is_not_duplicated(self):
        bank = [dict(BANK[0])]
        ab.learn(bank, "SQL (years)", "6 years")
        assert len(bank) == 1

    def test_an_unknown_reuse_scope_is_rejected(self):
        with pytest.raises(ValueError):
            ab.learn([], "Q", "A", reuse="sometimes")


class TestBatching:
    def test_only_the_unknown_questions_are_asked(self):
        """Asked in one batch per page; interrupting per field makes the
        system unbearable by the third application."""
        asked = ab.unanswered(
            ["Years of experience with SQL", "Do you require sponsorship?",
             "Describe a conflict you resolved"], BANK)
        assert asked == ["Describe a conflict you resolved"]


class TestPrefill:
    """What the master already knows should not be asked again."""

    MASTER = {
        "identity": {"location": "Austin, TX",
                     "linkedin": "https://linkedin.com/in/example",
                     "github": "https://github.com/example"},
        "experience": [
            {"id": "northwind", "company": "Northwind Systems",
             "title": "Senior Software Engineer", "from": "2024-08", "to": None},
            {"id": "contoso", "company": "Contoso", "title": "Engineer",
             "from": "2022-01", "to": "2024-07"},
        ],
        "education": [{"id": "uni", "institution": "University of Example",
                       "degree": "Bachelor of Computer Science"}],
        "skills": {"languages": {"python": {"since": "2020-09"}}},
        "career_start": "2022-01",
    }

    def entries(self):
        from hub import bootstrap
        e = bootstrap.starter()
        bootstrap.prefill(e, self.MASTER)
        return {x["slot"]: x for x in e}

    def test_identity_fields_are_answered(self):
        e = self.entries()
        assert e["location"]["value"] == "Austin, TX"
        assert "github.com/example" in e["portfolio"]["value"]

    def test_the_current_role_is_the_one_without_an_end_date(self):
        e = self.entries()
        assert e["current_employer"]["value"] == "Northwind Systems"
        assert e["current_title"]["value"] == "Senior Software Engineer"

    def test_skill_tenure_becomes_a_date_not_a_number(self):
        """So the answer is still true next year."""
        e = self.entries()
        assert e["python_years"]["since"] == "2020-09"
        assert e["python_years"].get("value") is None

    def test_total_experience_comes_from_career_start(self):
        assert self.entries()["total_years"]["since"] == "2022-01"

    def test_what_the_master_cannot_know_is_left_open(self):
        """Salary, notice period and work authorisation are exactly the D8
        awkward fields: a form asks them and a CV never states them."""
        e = self.entries()
        for slot in ("salary_expectation", "notice_period", "work_authorization"):
            assert e[slot]["value"] is None, slot

    def test_an_empty_master_prefills_nothing_and_does_not_fail(self):
        from hub import bootstrap
        entries = bootstrap.starter()
        assert bootstrap.prefill(entries, {}) == 0
