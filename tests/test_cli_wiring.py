"""What the command functions hand back to each other.

The screens are exercised through their own units; these cover the joins
between them, which is where a refactor breaks something no unit test sees.
"""
from __future__ import annotations

import dataclasses
from unittest.mock import patch

import pytest

from hub import cli, inbox, picker


def job(**over):
    base = {"job_id": "a" * 16, "company": "Northwind", "title": "Data Engineer",
            "url": "https://example.com/1", "source": "linkedin",
            "location": "London", "status": "new", "score": 8.0}
    return inbox.Job.from_row({**base, **over})


class TestPickReturnsAChoice:
    """The bug this exists for: `_pick` built a Picker and returned it instead
    of running it, so the caller reached for `.job_id` on the screen object."""

    def test_it_returns_the_chosen_job(self):
        with patch.object(picker.Picker, "run",
                          lambda self: self.rows[0] if self.rows else None):
            chosen = cli._pick([job(), job(job_id="b" * 16)])
        assert isinstance(chosen, inbox.Job) and chosen.job_id == "a" * 16

    def test_backing_out_returns_nothing(self):
        with patch.object(picker.Picker, "run", lambda self: None):
            assert cli._pick([job()]) is None

    def test_what_it_returns_carries_a_job_id(self):
        """`cmd_inbox` reaches straight for this."""
        with patch.object(picker.Picker, "run",
                          lambda self: self.rows[0] if self.rows else None):
            assert cli._pick([job()]).job_id


class TestPickFilters:
    def test_the_filter_bar_is_built_from_the_jobs_it_was_given(self):
        jobs = [job(source="linkedin", locations=["London"]),
                job(source="reed", locations=["Glasgow"], job_id="b" * 16)]
        with patch.object(picker.Picker, "run", lambda self: self) as _:
            screen = cli._pick(jobs)
        names = [f.name for f in screen.filters]
        assert names == ["age", "sort", "fit", "where", "source"]

    def test_locations_come_from_the_radars_canonical_set(self):
        jobs = [job(locations=["London", "UK"]),
                job(locations=["London"], job_id="b" * 16)]
        with patch.object(picker.Picker, "run", lambda self: self):
            screen = cli._pick(jobs)
        where = next(f for f in screen.filters if f.name == "where")
        assert [label for label, _ in where.options][:2] == ["any", "London"]

    def test_sorting_is_left_to_the_server(self):
        """Ordering a page here would silently drop rows it never contained."""
        with patch.object(picker.Picker, "run", lambda self: self):
            screen = cli._pick([job()])
        sort = next(f for f in screen.filters if f.name == "sort")
        assert sort.reload is not None and sort.keep is None


class TestEveryMenuPathOpens:
    """Each menu entry has to reach a screen. The inbox reached one and handed
    the screen object back instead of what was chosen; these check the others
    actually open and return an exit code."""

    @pytest.fixture
    def empty(self, tmp_path):
        """A config pointing at nothing.

        Built directly rather than through the environment: `paths.applications`
        in config.yaml overrides JAM_DATA_DIR, so setting the variable would
        have quietly read the real folder.
        """
        from hub import config
        real = config.load()
        (tmp_path / "applications").mkdir()
        (tmp_path / "logs").mkdir()
        return dataclasses.replace(real, data=tmp_path,
                                   applications_override=tmp_path / "applications")

    def run_all(self, cfg):
        opened = []
        with patch.object(picker.Picker, "run",
                          lambda self: opened.append(self.title) or None):
            codes = [cli._list_applications(cfg), cli._answers_screen(cfg),
                     cli._gaps_screen(cfg)]
        return codes, opened

    def test_each_returns_an_exit_code_rather_than_a_screen(self, empty):
        assert self.run_all(empty)[0] == [0, 0, 0]

    def test_each_opens_something(self, empty):
        assert len(self.run_all(empty)[1]) == 3

    def test_an_empty_repository_explains_itself(self, empty):
        """Rather than an empty list with no clue what to do next."""
        shown = []
        with patch.object(picker.Picker, "run",
                          lambda self: shown.extend(self.all) or None):
            cli._list_applications(empty)
        assert any("Take a vacancy" in line for line in shown)

    def test_a_missing_answer_bank_says_how_to_make_one(self, empty):
        shown = []
        with patch.object(picker.Picker, "run",
                          lambda self: shown.extend(self.all) or None):
            cli._answers_screen(empty)
        assert any("jam answers --init" in line for line in shown)

    def test_no_coverage_yet_explains_what_it_would_be_for(self, empty):
        shown = []
        with patch.object(picker.Picker, "run",
                          lambda self: shown.extend(self.all) or None):
            cli._gaps_screen(empty)
        assert any("to learn next" in line for line in shown)
