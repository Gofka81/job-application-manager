"""Reading the radar's INBOX."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

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

    def test_what_has_been_decided_is_left_out(self):
        jobs = [inbox.Job.from_row(row(status=s)) for s in ("new", "applied")]
        assert [j.status for j in inbox.shortlist(jobs)] == ["new"]

    def test_a_vacancy_read_in_the_radar_is_still_a_vacancy(self):
        """`viewed` is what the radar sets when its own dashboard shows a job.
        Listing what to show meant opening one there deleted it from here."""
        jobs = [inbox.Job.from_row(row(status="viewed"))]
        assert len(inbox.shortlist(jobs)) == 1

    def test_a_status_nobody_here_has_heard_of_is_shown_not_hidden(self):
        """The safe way round: a radar that invents a status gets it seen and
        questioned, rather than quietly dropping the rows that carry it."""
        jobs = [inbox.Job.from_row(row(status="shortlisted"))]
        assert len(inbox.shortlist(jobs)) == 1

    def test_hiding_nothing_shows_the_history_too(self):
        jobs = [inbox.Job.from_row(row(status=s))
                for s in ("new", "applied", "expired")]
        assert len(inbox.shortlist(jobs, hidden=())) == 3

    def test_the_dead_and_the_done_are_what_is_hidden(self):
        for status in ("expired", "saved", "applied", "rejected", "archived"):
            jobs = [inbox.Job.from_row(row(status=status))]
            assert inbox.shortlist(jobs) == [], status


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


class TestWhichStampTheAgeComesFrom:
    """Discovery, not publication. Boards give a bare day, so counting from
    publication made a posting found three hours ago read as a day old because
    the board called it yesterday's."""

    def test_the_radar_finding_it_is_what_starts_the_clock(self):
        job = inbox.Job.from_row(
            row(posted_at=(date.today() - timedelta(days=1)).isoformat(),
                first_seen=datetime.now().isoformat()))
        assert job.age_days == 0 and job.age_label.endswith("h")

    def test_publication_is_the_fallback_where_nothing_found_it(self):
        job = inbox.Job.from_row(
            row(posted_at=(date.today() - timedelta(days=5)).isoformat()))
        assert job.age_days == 5

    def test_neither_is_no_age_rather_than_today(self):
        assert inbox.Job.from_row(row()).age_days is None


class TestOrderBy:
    """Every sort the screen offers has to reach the rows. Re-sorting by score
    whatever was chosen left `posted` and `found` doing nothing at all, and the
    only sign of it was a list that did not change."""

    def jobs(self, sort, *dates):
        field = "posted_at" if sort == "posted" else "first_seen"
        return [inbox.Job.from_row(row(job_id=f"id{i}", score=float(i),
                                       **{field: d}))
                for i, d in enumerate(dates)]

    def test_every_option_orders_by_its_own_key(self):
        for sort, field in (("posted", "posted_at"), ("seen", "first_seen")):
            jobs = self.jobs(sort, "2026-01-01", "2026-03-01", "2026-02-01")
            got = inbox.order_by(jobs, sort)
            assert [getattr(j, field) for j in got] == [
                "2026-03-01", "2026-02-01", "2026-01-01"], sort

    def test_a_date_the_row_does_not_carry_sorts_last(self):
        """Not as the oldest: absent is not a date, and either end of the
        range would be a claim the row never made."""
        jobs = self.jobs("posted", "2026-01-01", None, "2026-03-01")
        assert [j.posted_at for j in inbox.order_by(jobs, "posted")] == [
            "2026-03-01", "2026-01-01", None]

    def test_the_other_key_is_not_what_orders_it(self):
        """`posted` and `found` differ whenever a posting is met late, which is
        the reason both are offered."""
        jobs = [inbox.Job.from_row(row(posted_at="2026-01-01",
                                       first_seen="2026-05-01")),
                inbox.Job.from_row(row(posted_at="2026-04-01",
                                       first_seen="2026-04-02"))]
        assert inbox.order_by(jobs, "posted")[0].posted_at == "2026-04-01"
        assert inbox.order_by(jobs, "seen")[0].first_seen == "2026-05-01"

    def test_score_is_still_the_default(self):
        jobs = [inbox.Job.from_row(row(score=s)) for s in (5.0, 9.0, None)]
        assert [j.score for j in inbox.order_by(jobs)] == [9.0, 5.0, None]

    def test_priority_tiers_before_it_scores(self):
        jobs = [inbox.Job.from_row(row(location="London", score=9.0)),
                inbox.Job.from_row(row(location="Glasgow", score=6.0))]
        got = inbox.order_by(jobs, "priority", ("glasgow",))
        assert got[0].location == "Glasgow"

    def test_the_shortlist_passes_the_sort_through(self):
        """The filtering step used to re-sort by score on the way out, which
        undid whatever the screen and the server had agreed on."""
        jobs = self.jobs("posted", "2026-01-01", "2026-03-01")
        got = inbox.shortlist(jobs, sort="posted")
        assert [j.posted_at for j in got] == ["2026-03-01", "2026-01-01"]


class TestNoRowIsUnreachable:
    """The property behind the fetch: whatever the screen is ordered by, every
    row the radar holds is in the set being ordered. The radar's `sort=score`
    answers with scored rows only, so any design that fetches per-sort loses
    the newest vacancies — the ones worth seeing first."""

    def table(self):
        return [inbox.Job.from_row(row(job_id="scored", score=9.0)),
                inbox.Job.from_row(row(job_id="fresh", score=None))]

    def test_every_sort_orders_the_same_rows(self):
        table = self.table()
        for sort in ("priority", "score", "posted", "seen"):
            got = inbox.order_by(table, sort)
            assert {j.job_id for j in got} == {"scored", "fresh"}, sort

    def test_the_shortlist_keeps_an_unscored_row_at_the_default_bar(self):
        got = inbox.shortlist(self.table())
        assert {j.job_id for j in got} == {"scored", "fresh"}


class TestAgeInHours:
    """A column in whole days said `0d` for everything found since midnight,
    which is most of a morning's rows and exactly the ones worth telling
    apart."""

    def stamp(self, hours, tz=None):
        when = datetime.now(tz) - timedelta(hours=hours)
        return when.isoformat()

    def test_the_hours_are_counted_when_the_stamp_has_a_clock(self):
        job = inbox.Job.from_row(row(posted_at=self.stamp(5)))
        assert 4.9 < job.age_hours < 5.1
        assert job.age_label == "5h"

    def test_a_bare_date_alone_gives_no_hour(self):
        """Midnight is the parser's invention, not the board's, and a row the
        radar never stamped has nothing finer to offer."""
        job = inbox.Job.from_row(row(posted_at=date.today().isoformat()))
        assert job.age_hours is None
        assert job.age_label == "0d"

    def test_the_hour_comes_from_the_stamp_the_radar_wrote(self):
        """`posted_at` is `2026-09-08` and nothing more on every board, while
        the radar stamps the second a scan met the posting. The hour is only
        in one of them."""
        job = inbox.Job.from_row(row(posted_at=date.today().isoformat(),
                                     first_seen=self.stamp(4)))
        assert 3.9 < job.age_hours < 4.1
        assert job.age_label == "4h"

    def test_a_board_calling_it_yesterday_does_not_age_a_fresh_find(self):
        """The bug this replaced: found three hours ago, shown as `1d`,
        buried under rows the radar had known about for longer."""
        job = inbox.Job.from_row(
            row(posted_at=(date.today() - timedelta(days=1)).isoformat(),
                first_seen=self.stamp(3)))
        assert job.age_label == "3h"

    def test_the_first_hour_is_not_rounded_down_to_nothing(self):
        job = inbox.Job.from_row(row(posted_at=self.stamp(0.3)))
        assert job.age_label == "<1h"

    def test_past_a_day_it_goes_back_to_days(self):
        """Four characters of column, and `54h` is harder to read than `2d`."""
        job = inbox.Job.from_row(row(posted_at=self.stamp(54)))
        assert job.age_label == "2d"

    def test_an_hour_label_fits_the_column(self):
        """Five characters, which is what the column gives it: anything longer
        is truncated, and `1000` reads as a number rather than a cut."""
        for hours in (0.1, 1, 9, 23, 25, 24 * 400):
            for field in ("posted_at", "first_seen"):
                job = inbox.Job.from_row(row(**{field: self.stamp(hours)}))
                assert len(job.age_label) <= 5, job.age_label

    def test_a_zulu_stamp_is_read_as_utc_not_as_local(self):
        """Off by one for half the British year, which is a whole hour of a
        column that only has hours in it."""
        when = datetime.now(timezone.utc) - timedelta(hours=3)
        job = inbox.Job.from_row(
            row(posted_at=when.strftime("%Y-%m-%dT%H:%M:%SZ")))
        assert 2.9 < job.age_hours < 3.1

    def test_a_stamp_in_the_future_is_not_a_negative_age(self):
        """Boards do post ahead, and `-2h` in the column reads as a bug."""
        job = inbox.Job.from_row(row(posted_at=self.stamp(-2)))
        assert job.age_hours == 0.0 and job.age_label == "<1h"

    def test_no_stamp_at_all_still_says_so(self):
        assert inbox.Job.from_row(row()).age_label == "-"

    def test_an_unreadable_stamp_is_not_an_age(self):
        assert inbox.Job.from_row(row(posted_at="last tuesday")).age_label == "-"

    def test_a_row_with_only_a_discovery_stamp_is_no_different(self):
        assert inbox.Job.from_row(row(first_seen=self.stamp(2))).age_label == "2h"

    def test_the_phrase_says_the_same_thing_in_words(self):
        assert inbox.Job.from_row(
            row(posted_at=self.stamp(1))).age_phrase == "1 hour ago"
        assert inbox.Job.from_row(
            row(posted_at=self.stamp(5))).age_phrase == "5 hours ago"
        assert inbox.Job.from_row(
            row(posted_at=self.stamp(0.2))).age_phrase == "less than an hour ago"
        assert inbox.Job.from_row(
            row(posted_at=self.stamp(54))).age_phrase == "2 days ago"
        assert inbox.Job.from_row(
            row(posted_at=date.today().isoformat())).age_phrase == "today"
        assert inbox.Job.from_row(row()).age_phrase == ""

    def test_the_day_count_still_counts_calendar_days(self):
        """`age_days` is what the 48h and 7d filters count. A clock on the
        stamp must not turn a row posted late yesterday into a nought-day row
        the `48h` filter then keeps for an extra day."""
        yesterday = datetime.combine(date.today() - timedelta(days=1),
                                     datetime.min.time()).replace(hour=23)
        job = inbox.Job.from_row(row(posted_at=yesterday.isoformat()))
        assert job.age_days == 1


class TestFetchAll:
    """One request for the whole table, because the radar's list API has no
    paging and no filter for unscored rows: `limit`, `sort` and `q` are all of
    it. Every bug in this file's history was a page that could not contain the
    row someone was looking for."""

    def calls(self, monkeypatch, rows=3):
        log = []

        def fake(limit=200, query=None, sort="score", base=None, token=None):
            log.append((limit, sort, query))
            return [inbox.Job.from_row(row(job_id=f"id{i}")) for i in range(rows)]

        monkeypatch.setattr(inbox, "fetch", fake)
        return log

    def test_it_asks_for_more_rows_than_the_radar_can_hold(self, monkeypatch):
        log = self.calls(monkeypatch)
        inbox.fetch_all()
        assert log[0][0] == inbox.WHOLE_TABLE

    def test_it_asks_once(self, monkeypatch):
        """The set is held here, so ordering it costs nothing further."""
        log = self.calls(monkeypatch)
        inbox.fetch_all()
        assert len(log) == 1

    def test_it_asks_by_discovery_so_a_full_table_loses_the_oldest(self,
                                                                  monkeypatch):
        """Not by score: that ordering answers without the unscored rows, which
        are the ones worth keeping when something has to be dropped."""
        log = self.calls(monkeypatch)
        inbox.fetch_all()
        assert log[0][1] == "seen"

    def test_a_deep_search_is_the_same_request_with_the_query(self, monkeypatch):
        log = self.calls(monkeypatch)
        inbox.fetch_all("spark")
        assert log[0] == (inbox.WHOLE_TABLE, "seen", "spark")

    def test_a_short_answer_is_the_whole_table(self, monkeypatch):
        self.calls(monkeypatch, rows=3)
        assert not inbox.truncated(inbox.fetch_all())

    def test_a_full_answer_is_not_trusted_to_be_everything(self, monkeypatch):
        """The day the table outgrows one response, the screen has to say so.
        A list quietly missing its tail is the failure this exists to stop."""
        self.calls(monkeypatch, rows=inbox.WHOLE_TABLE)
        assert inbox.truncated(inbox.fetch_all())

    def test_a_failure_is_still_a_failure(self, monkeypatch):
        def fake(**kw):
            raise inbox.RadarError("radar is down")
        monkeypatch.setattr(inbox, "fetch", fake)
        with pytest.raises(inbox.RadarError):
            inbox.fetch_all()
