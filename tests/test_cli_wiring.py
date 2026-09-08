"""What the command functions hand back to each other.

The screens are exercised through their own units; these cover the joins
between them, which is where a refactor breaks something no unit test sees.
"""
from __future__ import annotations

import dataclasses
from datetime import date, timedelta
from unittest.mock import patch

import pytest

from hub import cli, inbox, picker


def said(lines) -> list[str]:
    """What a screen's lines say, whatever they are made of.

    A line is either prose or a list of (text, role) pieces, and a test asking
    what the screen says should not have to know which.
    """
    return ["".join(t for t, _ in line) if isinstance(line, list) else line
            for line in lines]


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

    def bar(self, sort_label):
        """The min-fit filter, with the sort set to one of its options."""
        filters = self.screen([job()]).filters
        sort = next(f for f in filters if f.name == "sort")
        sort.index = [l for l, _ in sort.options].index(sort_label)
        return next(f for f in filters if f.name == "min fit")

    def test_a_row_the_radar_has_not_scored_yet_survives_the_bar(self):
        """The radar scores overnight, so the morning's arrivals carry no
        number. A bar of 8+ hid exactly the rows worth seeing first, and they
        are not below the bar — they have not been judged against it."""
        for sort in ("priority", "posted", "found"):
            assert self.bar(sort).keep(job(score=None), 8.0) is True, sort

    def test_the_bar_still_holds_against_a_row_that_was_judged(self):
        for sort in ("priority", "fit", "posted", "found"):
            assert self.bar(sort).keep(job(score=6.0), 8.0) is False, sort

    def test_ordering_by_fit_is_the_one_place_an_unscored_row_has_no_seat(self):
        assert self.bar("fit").keep(job(score=None), 8.0) is False

    def test_no_bar_keeps_everything(self):
        assert self.bar("fit").keep(job(score=None), None) is True


class TestTheFirstFetchAgreesWithTheBar:
    """The remembered sort decides which rows are fetched, not only how they
    are ordered, and the fetch happens before the bar is built."""

    @pytest.fixture
    def state(self, tmp_path, monkeypatch):
        path = tmp_path / ".inbox-filters.json"
        monkeypatch.setattr(cli, "_filter_state_path", lambda: path)
        return path

    def test_nothing_remembered_opens_on_priority(self, state):
        assert cli._remembered_sort() == "priority"

    def test_a_remembered_choice_is_what_gets_fetched(self, state):
        state.write_text('{"sort": "found"}')
        assert cli._remembered_sort() == "seen"

    def test_a_label_that_no_longer_exists_falls_back(self, state):
        state.write_text('{"sort": "whatever"}')
        assert cli._remembered_sort() == "priority"

    def test_a_damaged_file_is_not_fatal(self, state):
        state.write_text("{ not json")
        assert cli._remembered_sort() == "priority"

    def test_the_bar_offers_exactly_what_the_fetch_understands(self):
        """Two lists of sorts would drift the first time one was edited."""
        with patch.object(picker.Picker, "run", lambda self: self):
            sort = next(f for f in cli._pick([job()]).filters
                        if f.name == "sort")
        assert list(sort.options) == cli._SORTS


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

    def test_the_menu_offers_a_link_as_well_as_the_radar(self, empty):
        """The radar covers the boards it watches and nothing else, and until
        now the menu offered no other way in."""
        keys = [a.key for a in cli._menu_actions(empty)]
        assert "link" in keys and keys.index("link") == keys.index("inbox") + 1

    def test_the_link_entry_reaches_the_intake(self, empty, monkeypatch):
        taken = []
        monkeypatch.setattr(cli, "_ask", lambda q, default="": "https://x.com/1")
        monkeypatch.setattr(cli, "_take_link",
                            lambda url, **kw: taken.append((url, kw)) or 0)
        entry = next(a for a in cli._menu_actions(empty) if a.key == "link")
        assert entry.run() == 0
        assert taken[0][0] == "https://x.com/1"
        # From a screen the CV starts by itself, as it does from the inbox.
        assert taken[0][1]["tailor"] is True

    def test_an_empty_answer_goes_back_rather_than_failing(self, empty,
                                                           monkeypatch):
        monkeypatch.setattr(cli, "_ask", lambda q, default="": "")
        monkeypatch.setattr(cli, "_take_link",
                            lambda *a, **k: pytest.fail("nothing was given"))
        assert cli._link_screen(empty) == 0

    def test_something_that_is_not_a_link_says_so(self, empty, monkeypatch):
        """Typing a company name here reaches a fetch of nothing."""
        monkeypatch.setattr(cli, "_ask", lambda q, default="": "data idols")
        monkeypatch.setattr(cli, "_take_link",
                            lambda *a, **k: pytest.fail("not a link"))
        assert cli._link_screen(empty) == 1

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

    def test_nothing_built_yet_says_so(self, tmp_path):
        assert cli._stage(self.record(tmp_path))[0] == "no cv"

    def test_a_cv_without_coverage_is_still_tailoring(self, tmp_path):
        """The gaps record is the half that survives the application."""
        assert cli._stage(self.record(tmp_path, files=["cv.pdf"]))[0] \
            == "no coverage"

    def test_notes_are_part_of_a_finished_tailoring(self, tmp_path):
        assert cli._stage(self.record(
            tmp_path, files=["cv.pdf", "coverage.yaml"]))[0] == "no notes"

    def test_everything_present_means_it_is_ready_to_fill(self, tmp_path):
        assert cli._stage(self.record(tmp_path, files=self.BUILT))[0] == "ready"

    def test_a_cv_over_the_page_budget_is_not_ready(self, tmp_path, monkeypatch):
        """A file existing is not the same as it being usable. One application
        read "ready" on a two-page CV that no recruiter would ever see, because
        the stage asked whether the PDF was there and not whether it passed."""
        monkeypatch.setattr(cli.atscheck, "page_count", lambda pdf: 2)
        assert cli._stage(self.record(tmp_path, files=self.BUILT))[0] == "2 pages"

    def test_every_unfinished_stage_names_the_same_command(self, tmp_path,
                                                           monkeypatch):
        """`jam apply` reaches all of them — it tailors what is missing and
        rebuilds what is stale before it opens anything. Naming a different
        command per stage made the reader work out which half they were in."""
        monkeypatch.setattr(cli.atscheck, "page_count", lambda pdf: 2)
        folders = [(), ("cv.pdf",), ("cv.pdf", "coverage.yaml"), self.BUILT]
        wanted = "jam apply 2026-09-06--northwind--data-engineer"
        assert {cli._stage(self.record(tmp_path, files=f))[1]
                for f in folders} == {wanted}

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
        lines = said(cli._detail_checks(self.folder(tmp_path)))
        assert any("3 (over 1)" in line for line in lines)

    def test_a_cv_inside_the_budget_carries_no_verdict(self, tmp_path,
                                                       monkeypatch):
        monkeypatch.setattr(cli.atscheck, "page_count", lambda pdf: 1)
        lines = said(cli._detail_checks(self.folder(tmp_path)))
        pages = next(l for l in lines if l.strip().startswith("pages"))
        assert pages.split() == ["pages", "1"]

    def test_it_counts_coverage_and_names_what_is_missing(self, tmp_path,
                                                          monkeypatch):
        monkeypatch.setattr(cli.atscheck, "page_count", lambda pdf: 1)
        lines = said(cli._detail_checks(self.folder(tmp_path, self.DOC)))
        assert any("required 1/2 (50%)" in line for line in lines)
        assert any("missing  Kafka" in line for line in lines)

    def test_a_damaged_coverage_file_does_not_take_the_screen_down(
            self, tmp_path, monkeypatch):
        monkeypatch.setattr(cli.atscheck, "page_count", lambda pdf: 1)
        lines = said(cli._detail_checks(self.folder(tmp_path, "requirements: 7")))
        assert any("unreadable" in line for line in lines)

    def test_nothing_built_yet_adds_nothing(self, tmp_path):
        empty = tmp_path / "empty"
        empty.mkdir()
        assert cli._detail_checks(empty) == []


class TestRebuild:
    """Compiling and checking are one step here on purpose: a rebuild that
    left a PDF failing its checks used to look exactly like a good one."""

    @pytest.fixture
    def folder(self, tmp_path):
        app = tmp_path / "2026-09-06--northwind--data-engineer"
        app.mkdir()
        return app

    @pytest.fixture
    def cfg(self):
        from hub import config
        return config.load()

    def compiles(self, monkeypatch, folder, ok=True):
        from hub import latex
        built = latex.Built(pdf=folder / ("cv.pdf" if ok else "gone"), log="! bad")
        monkeypatch.setattr(cli.latex, "compile_tex", lambda *a, **k: built)
        return built

    def checks(self, monkeypatch, ok=True, text="cv.pdf: pass (1 page(s))"):
        class Report:
            def report(self):
                return text
        report = Report()
        report.ok = ok
        monkeypatch.setattr(cli.check_mod, "check", lambda *a, **k: report)

    def test_a_good_build_reports_the_check_not_just_the_build(
            self, folder, cfg, monkeypatch):
        (folder / "cv.pdf").write_bytes(b"%PDF")
        self.compiles(monkeypatch, folder)
        self.checks(monkeypatch)
        ok, lines = cli._rebuild(folder, cfg)
        assert ok and any("pass" in line for line in lines)

    def test_a_pdf_that_fails_its_checks_is_not_a_success(
            self, folder, cfg, monkeypatch):
        (folder / "cv.pdf").write_bytes(b"%PDF")
        self.compiles(monkeypatch, folder)
        self.checks(monkeypatch, ok=False, text="cv.pdf: FAIL\n  2 pages")
        ok, lines = cli._rebuild(folder, cfg)
        assert ok is False and any("2 pages" in line for line in lines)

    def test_a_latex_failure_says_the_old_pdf_survived(
            self, folder, cfg, monkeypatch):
        self.compiles(monkeypatch, folder, ok=False)
        ok, lines = cli._rebuild(folder, cfg)
        assert ok is False
        assert any("left untouched" in line for line in lines)
        assert any("! bad" in line for line in lines)

    def test_a_folder_that_cannot_be_built_explains_itself(
            self, folder, cfg, monkeypatch):
        from hub import latex

        def refuse(*a, **k):
            raise latex.BuildError("no cv.tex in northwind")
        monkeypatch.setattr(cli.latex, "compile_tex", refuse)
        ok, lines = cli._rebuild(folder, cfg)
        assert ok is False and lines == ["no cv.tex in northwind"]

    def test_a_missing_extractor_does_not_undo_a_real_build(
            self, folder, cfg, monkeypatch):
        """The PDF was produced; only the verdict on it is unavailable."""
        (folder / "cv.pdf").write_bytes(b"%PDF")
        self.compiles(monkeypatch, folder)

        def missing(*a, **k):
            raise cli.check_mod.atscheck.ExtractorMissing("no pdftotext")
        monkeypatch.setattr(cli.check_mod, "check", missing)
        ok, lines = cli._rebuild(folder, cfg)
        assert ok and any("skipped" in line for line in lines)


class TestApplicationScreenActions:
    """The reason to build is almost always something read on this screen."""

    def screen(self, tmp_path, files=()):
        folder = tmp_path / "2026-09-06--northwind--data-engineer"
        folder.mkdir(parents=True, exist_ok=True)
        for name in files:
            (folder / name).write_text("x")
        record = {"app_id": folder.name, "_folder": folder,
                  "company": "Northwind", "submitted_at": None,
                  "source_url": "https://example.com/1"}
        seen = {}
        with patch.object(picker.Detail, "run",
                          lambda self: seen.update(detail=self)):
            from hub import config
            cli._application_screen(record, config.load())
        return seen["detail"]

    def test_building_is_always_offered(self, tmp_path):
        keys = [a.key for a in self.screen(tmp_path).actions]
        assert "b" in keys

    def test_the_button_works_when_there_is_nothing_to_rebuild(
            self, tmp_path, monkeypatch):
        """The bug: `b` called latexmk on a folder with no cv.tex, so the one
        case that sends you looking for it — tailoring failed, the folder is
        empty — was the one it could only report as an error."""
        started = []
        monkeypatch.setattr(cli.running, "start",
                            lambda folder, app, cwd: started.append(app))
        monkeypatch.setattr(cli, "_rebuild",
                            lambda *a: pytest.fail("nothing to rebuild"))
        detail = self.screen(tmp_path)          # no cv.tex
        message = next(a for a in detail.actions if a.key == "b").run()
        assert started == ["2026-09-06--northwind--data-engineer"]
        assert "tailoring started" in message

    def test_writing_a_cv_is_started_rather_than_waited_for(
            self, tmp_path, monkeypatch):
        """It takes minutes, and an action runs between two redraws. Waiting
        for it is the screen going away for the whole of it — so the one thing
        you could not do while tailoring was look at the other applications."""
        monkeypatch.setattr(cli.running, "start", lambda folder, app, cwd: None)
        monkeypatch.setattr(cli, "_tailor",
                            lambda *a, **k: pytest.fail("not in the foreground"))
        self.screen(tmp_path).actions[0].run()

    def test_recompiling_still_happens_in_place(self, tmp_path, monkeypatch):
        """Seconds, and latexmk and pdftotext both capture their own output.
        Backgrounding it would put a five-second job behind a stage change."""
        monkeypatch.setattr(cli.running, "start",
                            lambda *a: pytest.fail("no agent needed"))
        monkeypatch.setattr(cli, "_rebuild", lambda f, c: (True, ["cv.pdf: pass"]))
        detail = self.screen(tmp_path, cli.TAILOR_WRITES)
        assert "passes" in next(a for a in detail.actions if a.key == "b").run()

    def test_a_second_press_does_not_start_a_second_agent(
            self, tmp_path, monkeypatch):
        """Two agents writing one cv.tex is a CV neither of them wrote."""
        from datetime import datetime
        monkeypatch.setattr(cli.running, "current",
                            lambda folder: cli.running.Run(1, datetime.now()))
        monkeypatch.setattr(cli.running, "start",
                            lambda *a: pytest.fail("one is already running"))
        detail = self.screen(tmp_path)
        assert "already tailoring" in detail.actions[0].run()

    def test_the_cv_can_only_be_viewed_once_it_exists(self, tmp_path):
        assert "v" not in [a.key for a in self.screen(tmp_path).actions]
        assert "v" in [a.key for a in
                       self.screen(tmp_path, ["cv.pdf"]).actions]

    def test_rebuilding_refreshes_what_the_screen_shows(self, tmp_path,
                                                        monkeypatch):
        """Otherwise the page count on screen is the one from before the fix."""
        monkeypatch.setattr(cli, "_rebuild",
                            lambda folder, cfg: (True, ["cv.pdf: pass"]))
        detail = self.screen(tmp_path, cli.TAILOR_WRITES + ("cv.pdf",))
        rebuild = next(a for a in detail.actions if a.key == "b")
        assert "passes" in rebuild.run()
        # The screen rebuilds itself from the folder every tick rather than
        # from whatever the action last returned.
        detail.refresh()
        assert any("stage" in line for line in said(detail.lines))

    def test_a_failed_rebuild_says_so_rather_than_reporting_success(
            self, tmp_path, monkeypatch):
        monkeypatch.setattr(cli, "_rebuild",
                            lambda folder, cfg: (False, ["cv.pdf: FAIL"]))
        detail = self.screen(tmp_path, cli.TAILOR_WRITES + ("cv.pdf",))
        rebuild = next(a for a in detail.actions if a.key == "b")
        assert "does not pass" in rebuild.run()


class TestDeletingAnApplication:
    """Offered from both screens: the list is where you already know a row is
    not wanted, the detail is where you have just read why."""

    def records(self, tmp_path, n=2, submitted=None):
        out = []
        for i in range(n):
            folder = tmp_path / f"2026-09-0{i + 1}--northwind{i}--engineer"
            folder.mkdir(parents=True)
            (folder / "application.json").write_text("{}")
            out.append({"app_id": folder.name, "_folder": folder,
                        "company": f"Northwind{i}", "title": "Engineer",
                        "submitted_at": submitted})
        return out

    def cfg(self, tmp_path):
        from hub import config
        return dataclasses.replace(config.load(), data=tmp_path)

    def list_screen(self, cfg, records):
        seen = {}

        def fake(self):
            seen.setdefault("screen", self)
            return None
        with patch.object(cli, "_applications", lambda c: records), \
             patch.object(picker.Picker, "run", fake):
            cli._list_applications(cfg)
        return seen["screen"]

    def test_the_list_offers_it(self, tmp_path):
        screen = self.list_screen(self.cfg(tmp_path), self.records(tmp_path))
        assert screen.keys[24][0] == "^x delete"

    def test_the_list_asks_before_it_acts(self, tmp_path):
        records = self.records(tmp_path)
        screen = self.list_screen(self.cfg(tmp_path), records)
        result = screen.keys[24][1](screen)
        assert isinstance(result, picker.Ask)
        assert records[0]["_folder"].exists()

    def test_the_question_names_the_row_under_the_cursor(self, tmp_path):
        records = self.records(tmp_path)
        screen = self.list_screen(self.cfg(tmp_path), records)
        screen.cursor = 1
        assert "Northwind1" in screen.keys[24][1](screen).question

    def test_saying_yes_moves_it_and_drops_it_from_the_screen(self, tmp_path):
        records = self.records(tmp_path)
        screen = self.list_screen(self.cfg(tmp_path), records)
        message = screen.keys[24][1](screen).run()
        assert not records[0]["_folder"].exists()
        assert (tmp_path / ".trash" / records[0]["app_id"]).is_dir()
        assert "recoverable" in message
        assert len(screen.rows) == 1

    def test_an_empty_list_has_nothing_to_delete(self, tmp_path):
        screen = self.list_screen(self.cfg(tmp_path), self.records(tmp_path))
        screen.all, screen.base = [], []
        assert screen.keys[24][1](screen) == "nothing selected"

    def test_a_submitted_one_is_asked_about_differently(self, tmp_path):
        """It throws away the record of something that actually happened."""
        plain = self.records(tmp_path, n=1)[0]
        assert "only copy" not in cli._delete_question(plain)
        plain["submitted_at"] = "2026-09-06T10:00:00+00:00"
        assert "only copy" in cli._delete_question(plain)

    def test_the_detail_screen_offers_the_same_thing(self, tmp_path):
        record = self.records(tmp_path, n=1)[0]
        record["source_url"] = "https://example.com/1"
        seen = {}
        with patch.object(picker.Detail, "run",
                          lambda self: seen.update(d=self)):
            cli._application_screen(record, self.cfg(tmp_path))
        delete = next(a for a in seen["d"].actions if a.key == "d")
        assert delete.confirm and delete.closes

    def test_a_failure_to_delete_is_reported_not_raised(self, tmp_path,
                                                        monkeypatch):
        record = self.records(tmp_path, n=1)[0]
        monkeypatch.setattr(cli.take_mod, "discard",
                            lambda *a: (_ for _ in ()).throw(OSError("busy")))
        assert "could not delete" in cli._delete_application(
            record, self.cfg(tmp_path))


class TestRemoteIsNotPartOfThePlaceName:
    """The radar keeps remote as a column of its own; the screen has room for
    one location column, so the word is coloured apart instead."""

    def test_the_word_is_its_own_piece(self):
        parts = cli._where_parts(job(remote=True, location="United Kingdom"))
        assert parts[0] == ("remote", "remote")

    def test_the_place_beside_it_is_still_a_place(self):
        parts = cli._where_parts(job(remote=True, location="United Kingdom"))
        assert [role for _, role in parts[1:]] == ["cell"]

    def test_an_office_job_is_all_place(self):
        assert cli._where_parts(job(location="London")) == [("London", "cell")]

    def test_a_remote_job_with_nowhere_named_is_just_the_word(self):
        assert cli._where_parts(job(remote=True, location="")) == \
            [("remote", "remote")]

    def test_an_unknown_remote_flag_is_not_treated_as_remote(self):
        """Most rows are null rather than false; colouring those as remote
        would be inventing the fact rather than showing it."""
        assert cli._where_parts(job(remote=None, location="London")) == \
            [("London", "cell")]

    def test_the_pieces_say_the_same_thing_the_column_does(self):
        """`where` is what the plain table and any non-drawing caller use."""
        for kw in ({"remote": True, "location": "United Kingdom"},
                   {"remote": True, "location": ""},
                   {"location": "London"}):
            j = job(**kw)
            assert "".join(t for t, _ in cli._where_parts(j)) == j.where


class TestTrafficLightsMatchTheRadar:
    """The radar's own bands, from `tgfmt.dot`, which its comment calls the
    dashboard's badge bands. A 6.5 amber there and red here would make the
    colour worth less than no colour: the reader would have to remember which
    tool they are looking at before they could read it."""

    def light(self, score):
        return cli._fit_role(job(score=score))

    def test_seven_and_up_is_green_as_it_is_in_the_radar(self):
        assert self.light(7.0) == "good" and self.light(9.0) == "good"

    def test_five_to_seven_is_amber(self):
        assert self.light(5.0) == "fair" and self.light(6.9) == "fair"

    def test_below_five_is_red(self):
        assert self.light(4.9) == "poor" and self.light(0.0) == "poor"

    def test_unscored_is_neither_good_nor_bad(self):
        """The radar shows a white dot for these; here they are dim. Red would
        say the radar judged it and thought little of it."""
        assert self.light(None) == "none"

    def test_the_bands_are_the_radar_s_numbers_and_not_a_copy_of_them(self):
        assert cli.FIT_BANDS == (7.0, 5.0)

    def age(self, days):
        return cli._age_role(job(posted_at=None,
                                 first_seen=(date.today() - timedelta(days=days))
                                 .isoformat()))

    def test_inside_the_radar_s_new_window_is_green(self):
        """`RECENT_HOURS = 48` — the dashboard's Recent default and its 🆕
        view's window."""
        assert self.age(0) == "good" and self.age(2) == "good"

    def test_still_live_is_amber(self):
        assert self.age(3) == "fair" and self.age(30) == "fair"

    def test_about_to_be_archived_is_red(self):
        """`archive_after_days: 30`, after which the row leaves the live table
        and the hub stops being able to see it at all."""
        assert self.age(31) == "poor"

    def test_no_date_is_not_a_judgement_either(self):
        assert cli._age_role(job()) == "none"


class TestWhatAStageIsAskingFor:
    """The stage column holds one word. Its colour says what kind of word it
    is, so a list of ten applications answers "what needs me" without being
    read one row at a time."""

    def record(self, tmp_path, **over):
        folder = tmp_path / "2026-09-06--northwind--data-engineer"
        folder.mkdir(parents=True, exist_ok=True)
        for name in over.pop("files", ()):
            (folder / name).write_text("x")
        return {"app_id": folder.name, "_folder": folder, **over}

    BUILT = ["cv.pdf", "coverage.yaml", "changes.md"]

    def test_ready_to_send_is_the_green_one(self, tmp_path):
        assert cli._stage_role(self.record(tmp_path, files=self.BUILT)) == "good"

    def test_work_not_done_yet_is_amber(self, tmp_path):
        """Nothing has failed: a step has not been run."""
        assert cli._stage_role(self.record(tmp_path)) == "fair"

    def test_a_check_that_ran_and_failed_is_red(self, tmp_path, monkeypatch):
        """Different from work outstanding — the CV exists, it is just too
        long to send, and no further tailoring step is missing."""
        monkeypatch.setattr(cli.atscheck, "page_count", lambda pdf: 2)
        assert cli._stage_role(self.record(tmp_path, files=self.BUILT)) == "poor"

    def test_a_sent_application_is_not_asking_for_anything(self, tmp_path):
        record = self.record(tmp_path, files=self.BUILT,
                             submitted_at="2026-09-06T10:00:00+00:00")
        assert cli._stage_role(record) == "none"

    def test_the_radar_s_score_keeps_its_own_bands(self, tmp_path):
        """The inbox row and the application it became are the same number and
        the same verdict."""
        assert cli._score_role(9.0) == "good" and cli._score_role(4.0) == "poor"
        assert cli._score_role(None) == "none"


class TestTheStageIsWorkedOutOnce:
    """Two columns, a colour and a subtitle ask for it, and answering means
    opening the PDF to count its pages."""

    def record(self, tmp_path):
        folder = tmp_path / "2026-09-06--northwind--data-engineer"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "cv.pdf").write_text("x")
        return {"app_id": folder.name, "_folder": folder, "submitted_at": None}

    def test_the_pdf_is_not_reopened_for_every_ask(self, tmp_path, monkeypatch):
        counted = []
        monkeypatch.setattr(cli.atscheck, "page_count",
                            lambda pdf: counted.append(pdf) or 1)
        record = self.record(tmp_path)
        for _ in range(5):
            cli._stage(record)
        assert len(counted) <= 1

    def test_a_rebuild_asks_again(self, tmp_path, monkeypatch):
        """The stage is read off the folder, and a rebuild changes it."""
        monkeypatch.setattr(cli.atscheck, "page_count", lambda pdf: 2)
        record = self.record(tmp_path)
        assert cli._stage(record)[0] == "2 pages"
        monkeypatch.setattr(cli.atscheck, "page_count", lambda pdf: 1)
        record.pop("_stage", None)
        assert cli._stage(record)[0] != "2 pages"


class TestWhereItStands:
    """The stage column has room for a verdict and none for the number behind
    it, and a verdict alone sends you to another command to find out what it
    meant."""

    def record(self, tmp_path, **over):
        folder = tmp_path / "2026-09-06--northwind--data-engineer"
        folder.mkdir(parents=True, exist_ok=True)
        for name in over.pop("files", ()):
            (folder / name).write_text("x")
        if (doc := over.pop("coverage", None)):
            (folder / "coverage.yaml").write_text(doc)
        return {"app_id": folder.name, "_folder": folder, **over}

    DOC = """
requirements:
  - {text: Kafka, weight: required, status: missing}
  - {text: dbt, weight: required, status: covered}
"""

    def test_it_names_the_command_that_moves_it_on(self, tmp_path):
        note = cli._application_note(self.record(tmp_path))
        assert "no cv" in note and "jam apply" in note

    def test_it_says_what_coverage_is_short_of(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cli.atscheck, "page_count", lambda pdf: 1)
        note = cli._application_note(self.record(
            tmp_path, files=["cv.pdf", "changes.md"], coverage=self.DOC))
        assert "required 1/2 (50%)" in note and "missing Kafka" in note

    def test_a_sent_one_says_when_and_how_instead(self, tmp_path):
        """Nothing is left to run, so the useful fact is the record of it."""
        note = cli._application_note(self.record(
            tmp_path, submitted_at="2026-09-06T10:00:00+00:00",
            channel="linkedin"))
        assert note == "submitted 2026-09-06 through linkedin"

    def test_a_damaged_coverage_file_says_so_rather_than_crashing(self,
                                                                  tmp_path):
        note = cli._application_note(self.record(tmp_path,
                                                 coverage="requirements: 7"))
        assert "cannot be read" in note


class TestTheTwoDetailScreensAreLaidOutTheSame:
    """A vacancy and the application it became are the same thing at two
    stages. Two helpers, one for each, drifted a character apart the first
    time one of them was edited."""

    def test_a_field_is_a_name_and_a_value(self):
        assert cli._field("stage", "ready", "good") == \
            [("  stage     ", "name"), ("ready", "good")]

    def test_an_empty_field_is_no_line_at_all(self):
        """A label with nothing after it is a question the screen cannot
        answer, and a row of them is what a form looks like."""
        assert cli._field("channel", None) is None
        assert cli._field("channel", "") is None

    def test_a_section_is_a_rule_with_its_name_in_it(self):
        pieces = cli._section("checks")
        assert [role for _, role in pieces] == ["rule", "name", "rule"]
        assert "checks" in "".join(t for t, _ in pieces)


class TestGettingToACv:
    """`_ensure_cv` is the one step both the screen's button and `jam apply`
    go through, so that "make this application ready" means the same thing
    from either side."""

    @pytest.fixture
    def folder(self, tmp_path):
        app = tmp_path / "2026-09-06--northwind--data-engineer"
        app.mkdir()
        return app

    @pytest.fixture
    def cfg(self):
        from hub import config
        return config.load()

    def test_an_empty_folder_is_tailored_rather_than_compiled(
            self, folder, cfg, monkeypatch):
        ran = []
        monkeypatch.setattr(cli, "_tailor", lambda app, **k: ran.append(app) or 0)
        monkeypatch.setattr(cli, "_rebuild", lambda f, c: (True, ["ok"]))
        cli._ensure_cv(folder, cfg, folder.name)
        assert ran == [folder.name]

    @pytest.mark.parametrize("absent", cli.TAILOR_WRITES)
    def test_anything_a_tailoring_writes_being_absent_means_it_did_not_finish(
            self, folder, cfg, monkeypatch, absent):
        """A cv.tex with no coverage.yaml beside it is a CV nobody can say is
        honest, and recompiling it would report a clean pass."""
        for name in cli.TAILOR_WRITES:
            if name != absent:
                (folder / name).write_text("x")
        ran = []
        monkeypatch.setattr(cli, "_tailor", lambda app, **k: ran.append(app) or 0)
        monkeypatch.setattr(cli, "_rebuild", lambda f, c: (True, ["ok"]))
        cli._ensure_cv(folder, cfg, folder.name)
        assert ran == [folder.name]

    def test_a_finished_folder_is_only_compiled(self, folder, cfg, monkeypatch):
        """Re-tailoring a CV someone has been editing throws the edits away."""
        for name in cli.TAILOR_WRITES:
            (folder / name).write_text("x")
        monkeypatch.setattr(cli, "_tailor",
                            lambda *a, **k: pytest.fail("should not tailor"))
        monkeypatch.setattr(cli, "_rebuild", lambda f, c: (True, ["ok"]))
        assert cli._ensure_cv(folder, cfg, folder.name)[0]

    def test_what_the_agent_wrote_is_rebuilt_rather_than_trusted(
            self, folder, cfg, monkeypatch):
        """The agent reports what it wrote. What has to be true is that the
        PDF on disk came from the cv.tex on disk and still passes, and only
        recompiling establishes that."""
        monkeypatch.setattr(cli, "_tailor", lambda app, **k: 0)
        monkeypatch.setattr(cli, "_rebuild", lambda f, c: (False, ["2 pages"]))
        ok, lines = cli._ensure_cv(folder, cfg, folder.name)
        assert ok is False and lines == ["2 pages"]

    def test_a_failed_tailoring_does_not_go_on_to_compile(
            self, folder, cfg, monkeypatch):
        """latexmk on a folder the agent never wrote to reports a missing
        cv.tex, which buries the reason the agent stopped."""
        monkeypatch.setattr(cli, "_tailor", lambda app, **k: 1)
        monkeypatch.setattr(cli, "_rebuild",
                            lambda *a: pytest.fail("nothing to build"))
        ok, lines = cli._ensure_cv(folder, cfg, folder.name)
        assert ok is False and any("did not finish" in line for line in lines)


class TestApplyFromTheCommandLine:
    """`jam apply` is the join between the deterministic half and the session
    that fills the form. It used to be a string printed for someone to
    retype in another window."""

    def app(self, tmp_path, **over):
        import json
        folder = tmp_path / "applications" / "2026-09-06--northwind--data-engineer"
        folder.mkdir(parents=True)
        (folder / "application.json").write_text(json.dumps(
            {"app_id": folder.name, "company": "Northwind",
             "submitted_at": None, **over}))
        return folder

    def args(self, folder, **over):
        import argparse
        return argparse.Namespace(**{"app": folder.name, "fresh": False,
                                     "ready": True, **over})

    def ready(self, monkeypatch, stage="ready", ok=True):
        monkeypatch.setattr(cli, "_ensure_cv", lambda *a, **k: (ok, ["cv.pdf: pass"]))
        monkeypatch.setattr(cli, "_work_out_stage", lambda r: (stage, ""))

    def use(self, monkeypatch, folder):
        from hub import config
        cfg = dataclasses.replace(config.load(),
                                  applications_override=folder.parent)
        monkeypatch.setattr(cli.config, "load", lambda: cfg)
        monkeypatch.setattr(cli, "_load_env", lambda: None)

    def test_an_unknown_application_is_not_an_empty_success(
            self, tmp_path, monkeypatch):
        folder = self.app(tmp_path)
        self.use(monkeypatch, folder)
        import argparse
        assert cli.cmd_apply(argparse.Namespace(
            app="nope", fresh=False, ready=True)) == 1

    def test_it_refuses_an_application_already_submitted(
            self, tmp_path, monkeypatch):
        """Applying twice to one vacancy is the mistake the inbox screen
        exists to prevent, and the other direction should not reopen it."""
        folder = self.app(tmp_path, submitted_at="2026-09-01T10:00:00")
        self.use(monkeypatch, folder)
        self.ready(monkeypatch)
        assert cli.cmd_apply(self.args(folder)) == 1

    def test_a_cv_that_does_not_pass_stops_before_any_form(
            self, tmp_path, monkeypatch):
        """The point of the command is that the thing being applied with was
        built and checked first."""
        folder = self.app(tmp_path)
        self.use(monkeypatch, folder)
        self.ready(monkeypatch, stage="2 pages", ok=False)
        assert cli.cmd_apply(self.args(folder)) == 3

    def test_a_stage_short_of_ready_stops_even_when_the_build_passed(
            self, tmp_path, monkeypatch):
        """A PDF that compiles and passes is still not an application: the
        coverage record and the notes are what `jam gaps` reads later."""
        folder = self.app(tmp_path)
        self.use(monkeypatch, folder)
        self.ready(monkeypatch, stage="no coverage")
        assert cli.cmd_apply(self.args(folder)) == 3

    def test_ready_stops_without_opening_a_session(self, tmp_path, monkeypatch):
        folder = self.app(tmp_path)
        self.use(monkeypatch, folder)
        self.ready(monkeypatch)
        monkeypatch.setattr(cli.os, "execvp",
                            lambda *a: pytest.fail("should not hand over"))
        assert cli.cmd_apply(self.args(folder)) == 0

    def test_otherwise_it_hands_the_terminal_to_the_skill(
            self, tmp_path, monkeypatch):
        folder = self.app(tmp_path)
        self.use(monkeypatch, folder)
        self.ready(monkeypatch)
        monkeypatch.setattr(cli.agent, "available", lambda: True)
        handed = []
        monkeypatch.setattr(cli.os, "execvp",
                            lambda f, argv: handed.append((f, argv)))
        cli.cmd_apply(self.args(folder, ready=False))
        assert handed == [("claude", ["claude", f"/apply {folder.name}"])]

    def test_without_the_cli_it_says_what_to_run_by_hand(
            self, tmp_path, monkeypatch, capsys):
        folder = self.app(tmp_path)
        self.use(monkeypatch, folder)
        self.ready(monkeypatch)
        monkeypatch.setattr(cli.agent, "available", lambda: False)
        monkeypatch.setattr(cli.os, "execvp",
                            lambda *a: pytest.fail("nothing to hand over to"))
        assert cli.cmd_apply(self.args(folder, ready=False)) == 0
        assert f"/apply {folder.name}" in capsys.readouterr().out


class TestTakingAVacancyStartsItsCv:
    """Press create-application and the CV is already being written. It used
    to be queued and run once the screens closed, so taking three vacancies
    bought three tailorings back to back with nothing else possible."""

    def taken(self, tmp_path, monkeypatch, no_tailor=False):
        import argparse
        from hub import config
        cfg = dataclasses.replace(config.load(), applications_override=tmp_path)
        monkeypatch.setattr(cli.config, "load", lambda: cfg)
        monkeypatch.setattr(cli, "_load_env", lambda: None)
        monkeypatch.setattr(cli.picker, "usable", lambda: True)
        monkeypatch.setattr(cli.inbox_mod, "fetch_all", lambda q=None: [job()])
        monkeypatch.setattr(cli.inbox_mod, "truncated", lambda jobs: False)
        monkeypatch.setattr(cli, "_remembered_sort", lambda: "score")
        started = []
        monkeypatch.setattr(cli.running, "start",
                            lambda folder, app, cwd: started.append(app))
        monkeypatch.setattr(cli, "_tailor",
                            lambda *a, **k: pytest.fail("not in the foreground"))

        # One vacancy taken, then the picker backs out.
        seen = {"n": 0}

        def pick(rows, *a):
            seen["n"] += 1
            return rows[0] if seen["n"] == 1 and rows else None
        monkeypatch.setattr(cli, "_pick", pick)
        monkeypatch.setattr(cli, "_vacancy_screen",
                            lambda job_id, on_taken=None:
                            on_taken(job_id, "2026-09-06--northwind--data-engineer"))
        cli.cmd_inbox(argparse.Namespace(
            plain=False, q=None, min_score=0.0, max_age=None, top=20,
            all=True, why=False, yes=False, no_tailor=no_tailor))
        return started

    def test_the_cv_starts_the_moment_the_vacancy_is_taken(self, tmp_path,
                                                           monkeypatch):
        assert self.taken(tmp_path, monkeypatch) == [
            "2026-09-06--northwind--data-engineer"]

    def test_nothing_waits_for_the_screens_to_close(self, tmp_path,
                                                    monkeypatch):
        """`_tailor` failing the test is the assertion: the foreground path
        must not be reached from a screen at all."""
        self.taken(tmp_path, monkeypatch)

    def test_no_tailor_still_only_takes_it(self, tmp_path, monkeypatch):
        assert self.taken(tmp_path, monkeypatch, no_tailor=True) == []


class TestTakingALink:
    """B1.3. Everything else starts at the radar's list, which covers the
    boards it watches and nothing else — a posting someone sends you had no
    way in at all."""

    def args(self, query, **over):
        import argparse
        return argparse.Namespace(**{"query": query, "yes": True,
                                     "paste": False, **over})

    def use(self, monkeypatch, tmp_path):
        from hub import config
        cfg = dataclasses.replace(config.load(), applications_override=tmp_path)
        monkeypatch.setattr(cli.config, "load", lambda: cfg)
        monkeypatch.setattr(cli, "_load_env", lambda: None)
        monkeypatch.setattr(cli.inbox_mod, "fetch_all",
                            lambda *a: pytest.fail("the radar has never seen it"))
        return cfg

    def read(self, monkeypatch, **over):
        row = {"company": "Northwind", "title": "Data Engineer",
               "url": "https://jobs.lever.co/acme/1", "source": "lever",
               "location": "London", "description": "5+ years of Python.",
               "jd_full": True, "score": None, "job_id": None,
               "posted_at": None, **over}
        monkeypatch.setattr(cli.intake, "from_url", lambda *a, **k: row)
        return row

    def test_a_link_never_reaches_the_radar_search(self, tmp_path, monkeypatch):
        """`jam take <url>` used to go looking for a company called
        "https://…" and report that nothing matched."""
        self.use(monkeypatch, tmp_path)
        self.read(monkeypatch)
        assert cli.cmd_take(self.args("https://jobs.lever.co/acme/1")) == 0

    def test_the_folder_says_it_did_not_come_from_the_radar(self, tmp_path,
                                                            monkeypatch):
        """A funnel counted later has to be able to tell the two apart."""
        self.use(monkeypatch, tmp_path)
        self.read(monkeypatch)
        cli.cmd_take(self.args("https://jobs.lever.co/acme/1"))
        import json
        written = json.loads(
            next(tmp_path.glob("*/application.json")).read_text())
        assert written["discovery"] == "link"
        assert written["radar_job_id"] is None and written["score_source"] is None

    def test_the_jd_is_written_beside_it(self, tmp_path, monkeypatch):
        self.use(monkeypatch, tmp_path)
        self.read(monkeypatch)
        cli.cmd_take(self.args("https://jobs.lever.co/acme/1"))
        assert "5+ years of Python." in next(tmp_path.glob("*/jd.md")).read_text()

    def test_a_page_that_cannot_be_read_falls_back_to_pasting(
            self, tmp_path, monkeypatch):
        """Boards behind a login are common enough that the fallback is part
        of the design rather than an error path."""
        self.use(monkeypatch, tmp_path)

        def refuse(*a, **k):
            raise cli.intake.IntakeError("a login wall")
        monkeypatch.setattr(cli.intake, "from_url", refuse)
        answers = iter(["Northwind", "Data Engineer", ""])
        monkeypatch.setattr(cli, "_ask", lambda q, default="": next(answers))
        monkeypatch.setattr(cli, "_paste_jd", lambda: "5+ years of Python.")
        assert cli.cmd_take(self.args("https://jobs.lever.co/acme/1")) == 0
        assert next(tmp_path.glob("*/application.json")).exists()

    def test_nothing_is_created_without_a_company_and_a_title(
            self, tmp_path, monkeypatch):
        """They are the folder's name. A blank one would collide with the next
        blank one."""
        self.use(monkeypatch, tmp_path)
        monkeypatch.setattr(cli.intake, "from_url",
                            lambda *a, **k: (_ for _ in ()).throw(
                                cli.intake.IntakeError("a login wall")))
        monkeypatch.setattr(cli, "_ask", lambda q, default="": "")
        monkeypatch.setattr(cli, "_paste_jd", lambda: "text")
        assert cli.cmd_take(self.args("https://jobs.lever.co/acme/1")) == 1
        assert list(tmp_path.glob("*/application.json")) == []

    def test_paste_skips_the_fetch_entirely(self, tmp_path, monkeypatch):
        self.use(monkeypatch, tmp_path)
        monkeypatch.setattr(cli.intake, "from_url",
                            lambda *a, **k: pytest.fail("--paste means paste"))
        answers = iter(["Northwind", "Data Engineer", ""])
        monkeypatch.setattr(cli, "_ask", lambda q, default="": next(answers))
        monkeypatch.setattr(cli, "_paste_jd", lambda: "5+ years of Python.")
        assert cli.cmd_take(self.args("https://jobs.lever.co/acme/1",
                                      paste=True)) == 0

    def test_paste_on_a_radar_search_is_refused_rather_than_ignored(self):
        assert cli.cmd_take(self.args("data idols", paste=True)) == 1


class TestOneAgentPerApplication:
    """Two agents writing one cv.tex is a CV neither of them wrote."""

    def app(self, tmp_path, monkeypatch):
        import dataclasses as dc
        from hub import config
        folder = tmp_path / "2026-09-06--northwind--data-engineer"
        folder.mkdir(parents=True)
        cfg = dc.replace(config.load(), applications_override=tmp_path)
        monkeypatch.setattr(cli.config, "load", lambda: cfg)
        return folder

    def test_it_refuses_while_another_process_has_it(self, tmp_path,
                                                     monkeypatch):
        from datetime import datetime
        folder = self.app(tmp_path, monkeypatch)
        monkeypatch.setattr(cli.running, "current",
                            lambda f: cli.running.Run(999_999, datetime.now()))
        monkeypatch.setattr(cli.agent, "tailor",
                            lambda *a, **k: pytest.fail("one is already on it"))
        assert cli._tailor(folder.name) == 1

    def test_the_background_job_does_not_refuse_itself(self, tmp_path,
                                                       monkeypatch):
        """`running.start` spawns this very command and the marker names its
        pid, so comparing pids is what tells "someone else is on it" from
        "this is me"."""
        import os
        from datetime import datetime
        folder = self.app(tmp_path, monkeypatch)
        monkeypatch.setattr(cli.running, "current",
                            lambda f: cli.running.Run(os.getpid(), datetime.now()))
        ran = []
        monkeypatch.setattr(cli.agent, "tailor", lambda *a, **k: (
            ran.append(1) or cli.agent.Result(True, "done")))
        cli._tailor(folder.name)
        assert ran == [1]
