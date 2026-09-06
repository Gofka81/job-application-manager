"""Reading the radar's INBOX."""
from __future__ import annotations

from datetime import date, timedelta

from hub import inbox


def row(**over):
    base = {"job_id": "a" * 16, "company": "Northwind", "title": "Data Engineer",
            "url": "https://example.com/1", "source": "linkedin",
            "location": "London", "status": "new", "score": 8.0}
    return {**base, **over}


class TestWhere:
    """Remote is a column of its own in the radar, so it does not have to be
    read out of a location string."""

    def test_a_remote_job_says_so_beside_the_place(self):
        job = inbox.Job.from_row(row(remote=True, location="United Kingdom"))
        assert job.where == "remote · United Kingdom"

    def test_a_remote_job_with_no_place_still_says_remote(self):
        assert inbox.Job.from_row(row(remote=True, location="")).where == "remote"

    def test_an_unknown_remote_flag_is_not_treated_as_false(self):
        """Most rows are null rather than false; calling that office-based
        would be inventing a fact."""
        job = inbox.Job.from_row(row(remote=None))
        assert job.remote is None and job.where == "London"


class TestSalary:
    def test_a_range_is_shown_in_thousands(self):
        job = inbox.Job.from_row(row(salary_min=75000, salary_max=85000,
                                     currency="£"))
        assert job.salary == "£75-85k"

    def test_one_end_is_enough(self):
        assert inbox.Job.from_row(row(salary_min=70000, currency="£")).salary == "£70k"

    def test_no_figures_means_no_column(self):
        assert inbox.Job.from_row(row()).salary == ""


class TestAge:
    def test_it_counts_from_the_posting_date(self):
        when = (date.today() - timedelta(days=3)).isoformat()
        assert inbox.Job.from_row(row(posted_at=when)).age_days == 3

    def test_it_falls_back_to_when_the_radar_first_saw_it(self):
        """Which is every posting in practice: none carry a date."""
        when = (date.today() - timedelta(days=5)).isoformat()
        assert inbox.Job.from_row(row(first_seen=when)).age_days == 5

    def test_neither_means_unknown_rather_than_zero(self):
        assert inbox.Job.from_row(row()).age_days is None


class TestShortlist:
    def make(self, *scores):
        return [inbox.Job.from_row(row(score=s, job_id=f"id{i}"))
                for i, s in enumerate(scores)]

    def test_the_best_fit_comes_first(self):
        got = inbox.shortlist(self.make(5.0, 9.0, 7.0))
        assert [j.score for j in got] == [9.0, 7.0, 5.0]

    def test_unscored_rows_go_last_not_first(self):
        """Sorting a missing score as missing put them at the top, where they
        look like the best matches."""
        got = inbox.shortlist(self.make(5.0, None, 9.0))
        assert [j.score for j in got] == [9.0, 5.0, None]

    def test_a_minimum_score_drops_the_rest(self):
        assert len(inbox.shortlist(self.make(5.0, 9.0), min_score=8.0)) == 1

    def test_only_new_by_default(self):
        jobs = [inbox.Job.from_row(row(status=s)) for s in ("new", "applied")]
        assert len(inbox.shortlist(jobs)) == 1

    def test_asking_for_no_status_shows_everything(self):
        jobs = [inbox.Job.from_row(row(status=s)) for s in ("new", "applied")]
        assert len(inbox.shortlist(jobs, statuses=())) == 2


class TestSlug:
    def test_it_is_a_date_a_company_and_a_role(self):
        job = inbox.Job.from_row(row(company="Data Idols",
                                     title="Senior Data Engineer"))
        assert job.slug().endswith("--data-idols--senior-data-engineer")




class TestPriorityTier:
    """The radar's own default sort, and the reason for it is in its own
    comment: scarce roles would otherwise be buried under London's volume.
    Somewhere with three postings a month never outbids somewhere with three
    hundred on score alone."""

    CITIES = ("edinburgh", "glasgow")

    def test_a_priority_city_is_the_top_tier(self):
        assert inbox.Job.from_row(row(location="Glasgow G2")).tier(self.CITIES) == 0

    def test_the_canonical_locations_are_used_when_present(self):
        job = inbox.Job.from_row(row(location="somewhere",
                                     locations=["Edinburgh"]))
        assert job.tier(self.CITIES) == 0

    def test_case_does_not_matter(self):
        assert inbox.Job.from_row(
            row(location="GLASGOW, LANARKSHIRE")).tier(self.CITIES) == 0

    def test_remote_is_the_second_tier(self):
        assert inbox.Job.from_row(row(remote=True)).tier(self.CITIES) == 1

    def test_remote_in_the_text_counts_even_without_the_flag(self):
        """Boards label a remote role with the employer's city, so the flag is
        often missing where the words are not."""
        assert inbox.Job.from_row(
            row(location="Remote (UK)")).tier(self.CITIES) == 1

    def test_everything_else_is_the_last_tier(self):
        assert inbox.Job.from_row(row(location="London")).tier(self.CITIES) == 2

    def test_a_priority_city_outranks_a_better_scored_london_role(self):
        jobs = [inbox.Job.from_row(row(location="London", score=9.0)),
                inbox.Job.from_row(row(location="Glasgow", score=6.0))]
        best = sorted(jobs, key=lambda j: (j.tier(self.CITIES), -(j.score or -1)))
        assert best[0].location == "Glasgow"

    def test_score_still_decides_inside_a_tier(self):
        jobs = [inbox.Job.from_row(row(location="Glasgow", score=6.0)),
                inbox.Job.from_row(row(location="Edinburgh", score=9.0))]
        best = sorted(jobs, key=lambda j: (j.tier(self.CITIES), -(j.score or -1)))
        assert best[0].score == 9.0

    def test_no_cities_configured_leaves_two_tiers(self):
        assert inbox.Job.from_row(row(location="Glasgow")).tier(()) == 2
