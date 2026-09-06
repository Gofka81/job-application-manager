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
    def screen(self, jobs):
        with patch.object(picker.Picker, "run", lambda self: self):
            return cli._pick(jobs)

    def test_the_bar_holds_what_is_worth_narrowing_by(self):
        assert [f.name for f in self.screen([job()]).filters] == \
            ["age", "sort", "min fit"]

    def test_sorting_is_left_to_the_server(self):
        """Ordering a page here would silently drop rows it never contained."""
        sort = next(f for f in self.screen([job()]).filters if f.name == "sort")
        assert sort.reload is not None and sort.keep is None

    def test_priority_is_the_default(self):
        """The radar's own: location tier first, score inside a tier."""
        sort = next(f for f in self.screen([job()]).filters if f.name == "sort")
        assert [label for label, _ in sort.options] == \
            ["priority", "fit", "posted", "found"]

    def test_age_counts_unknown_as_fresh_rather_than_hiding_it(self):
        age = next(f for f in self.screen([job()]).filters if f.name == "age")
        assert age.keep(job(), 2) is True


class TestFilterMemory:
    """Choosing 7d and 8+ on every open is the friction that ends with the
    filters going unused."""

    @pytest.fixture
    def state(self, tmp_path, monkeypatch):
        path = tmp_path / ".inbox-filters.json"
        monkeypatch.setattr(cli, "_filter_state_path", lambda: path)
        return path

    def filters(self):
        return [picker.Filter("age", [("48h", 2), ("7d", 7), ("all", None)]),
                picker.Filter("min fit", [("any", None), ("8+", 8.0)])]

    def test_what_was_chosen_comes_back(self, state):
        chosen = self.filters()
        chosen[0].index, chosen[1].index = 1, 1
        cli._remember_filters(chosen)

        fresh = self.filters()
        cli._restore_filters(fresh)
        assert [f.label for f in fresh] == ["7d", "8+"]

    def test_nothing_saved_leaves_the_defaults(self, state):
        fresh = self.filters()
        cli._restore_filters(fresh)
        assert [f.label for f in fresh] == ["48h", "any"]

    def test_a_damaged_file_is_ignored_rather_than_fatal(self, state):
        state.write_text("{not json")
        fresh = self.filters()
        cli._restore_filters(fresh)
        assert [f.label for f in fresh] == ["48h", "any"]

    def test_a_remembered_option_that_no_longer_exists_is_skipped(self, state):
        state.write_text('{"age": "30d"}')
        fresh = self.filters()
        cli._restore_filters(fresh)
        assert fresh[0].label == "48h"

    def test_saving_never_fails_a_screen(self, monkeypatch, tmp_path):
        monkeypatch.setattr(cli, "_filter_state_path",
                            lambda: tmp_path / "nope" / "deeper" / "f.json")
        cli._remember_filters(self.filters())      # must not raise


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


class TestStage:
    """Worked out from the folder rather than stored: a stage field would be a
    second truth to keep in step with the files that actually exist."""

    BUILT = ["cv.pdf", "coverage.yaml", "changes.md"]

    def record(self, tmp_path, submitted=None, files=()):
        folder = tmp_path / "2026-09-06--northwind--data-engineer"
        folder.mkdir(parents=True, exist_ok=True)
        for name in files:
            (folder / name).write_text("x")
        return {"app_id": folder.name, "_folder": folder,
                "submitted_at": submitted}

    def test_nothing_built_yet_points_at_tailoring(self, tmp_path):
        stage, action = cli._stage(self.record(tmp_path))
        assert stage == "no cv" and action.startswith("/tailor")

    def test_a_cv_without_coverage_is_still_tailoring(self, tmp_path):
        """The gaps record is the half that survives the application."""
        stage, action = cli._stage(self.record(tmp_path, files=["cv.pdf"]))
        assert stage == "no coverage" and action.startswith("/tailor")

    def test_notes_are_part_of_a_finished_tailoring(self, tmp_path):
        stage, action = cli._stage(
            self.record(tmp_path, files=["cv.pdf", "coverage.yaml"]))
        assert stage == "no notes" and action.startswith("/tailor")

    def test_everything_present_means_it_is_ready_to_fill(self, tmp_path):
        stage, action = cli._stage(self.record(tmp_path, files=self.BUILT))
        assert stage == "ready" and action.startswith("/apply")

    def test_a_cv_over_the_page_budget_is_not_ready(self, tmp_path, monkeypatch):
        """A file existing is not the same as it being usable. One application
        read "ready" on a two-page CV that no recruiter would ever see, because
        the stage asked whether the PDF was there and not whether it passed."""
        monkeypatch.setattr(cli.atscheck, "page_count", lambda pdf: 2)
        stage, action = cli._stage(self.record(tmp_path, files=self.BUILT))
        assert stage == "2 pages" and action.startswith("/tailor")

    def test_an_unreadable_pdf_does_not_invent_a_verdict(self, tmp_path,
                                                        monkeypatch):
        """No page count is not a failing page count."""
        monkeypatch.setattr(cli.atscheck, "page_count", lambda pdf: None)
        stage, _ = cli._stage(self.record(tmp_path, files=self.BUILT))
        assert stage == "ready"

    def test_a_submitted_application_needs_nothing(self, tmp_path):
        stage, action = cli._stage(self.record(
            tmp_path, submitted="2026-09-06T10:00:00+00:00",
            files=self.BUILT))
        assert stage == "submitted" and action == ""

    def test_submitted_wins_over_a_missing_file(self, tmp_path):
        """It already went out; what is on disk cannot un-send it."""
        stage, _ = cli._stage(self.record(tmp_path, submitted="2026-09-06"))
        assert stage == "submitted"


class TestDetailChecks:
    """The stage column has room for one word; the detail has room for the
    number behind it, so "2 pages" can be read without a second command."""

    def folder(self, tmp_path, coverage=None):
        folder = tmp_path / "2026-09-06--northwind--data-engineer"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "cv.pdf").write_text("x")
        if coverage is not None:
            (folder / "coverage.yaml").write_text(coverage)
        return folder

    DOC = """
requirements:
  - {text: Kafka, weight: required, status: missing}
  - {text: dbt, weight: required, status: covered}
  - {text: Athena, weight: preferred, status: partial}
"""

    def test_it_says_how_far_over_the_budget_the_cv_runs(self, tmp_path,
                                                         monkeypatch):
        monkeypatch.setattr(cli.atscheck, "page_count", lambda pdf: 3)
        lines = cli._detail_checks(self.folder(tmp_path))
        assert any("3 (over 1)" in line for line in lines)

    def test_a_cv_inside_the_budget_carries_no_verdict(self, tmp_path,
                                                       monkeypatch):
        monkeypatch.setattr(cli.atscheck, "page_count", lambda pdf: 1)
        lines = cli._detail_checks(self.folder(tmp_path))
        assert any(line.strip() == "pages      1" for line in lines)

    def test_it_counts_coverage_and_names_what_is_missing(self, tmp_path,
                                                          monkeypatch):
        monkeypatch.setattr(cli.atscheck, "page_count", lambda pdf: 1)
        lines = cli._detail_checks(self.folder(tmp_path, self.DOC))
        assert any("required 1/2 (50%)" in line for line in lines)
        assert any("missing  Kafka" in line for line in lines)

    def test_a_damaged_coverage_file_does_not_take_the_screen_down(
            self, tmp_path, monkeypatch):
        monkeypatch.setattr(cli.atscheck, "page_count", lambda pdf: 1)
        lines = cli._detail_checks(self.folder(tmp_path, "requirements: 7"))
        assert any("unreadable" in line for line in lines)

    def test_nothing_built_yet_adds_nothing(self, tmp_path):
        empty = tmp_path / "empty"
        empty.mkdir()
        assert cli._detail_checks(empty) == []
