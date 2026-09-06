"""Turning a vacancy into an application folder."""
from __future__ import annotations

import json
from datetime import date
from types import SimpleNamespace

import pytest

from hub import take

WHEN = date(2026, 9, 6)
JOB = {
    "job_id": "40d1235ff9e381e4", "company": "Data Idols",
    "title": "Senior Data Engineer", "url": "https://example.com/1",
    "source": "linkedin", "score": 9.0, "description": "Azure and Databricks",
    "jd_full": True, "posted_at": "2026-09-04",
}


class TestAppId:
    def test_it_is_the_date_the_company_and_the_role(self):
        assert take.app_id("Data Idols", "Senior Data Engineer", WHEN) == \
            "2026-09-06--data-idols--senior-data-engineer"

    def test_punctuation_becomes_separators(self):
        got = take.app_id("Oliver Bernard", "Senior DE – (London, Hybrid)", WHEN)
        assert got == "2026-09-06--oliver-bernard--senior-de-london-hybrid"

    def test_a_long_title_is_cut_not_wrapped(self):
        got = take.app_id("C", "x" * 90, WHEN)
        assert len(got.split("--")[-1]) <= 40

    def test_an_empty_name_still_yields_an_id(self):
        assert take.app_id("", "", WHEN) == "2026-09-06--unknown--unknown"


class TestRecord:
    def test_the_channel_comes_from_the_source(self):
        assert take.record(JOB, WHEN)["channel"] == "linkedin"

    def test_an_unknown_source_is_passed_through(self):
        assert take.record({**JOB, "source": "obscure"}, WHEN)["channel"] == "obscure"

    def test_discovery_says_the_radar_found_it(self):
        assert take.record(JOB, WHEN)["discovery"] == "radar"

    def test_there_is_no_status_field(self):
        """Status is a fold of the log; a copy here would be a second truth."""
        assert "status" not in take.record(JOB, WHEN)

    def test_submitted_at_stays_empty_until_a_submission_happens(self):
        """A folder that exists is not an application that happened (D9)."""
        assert take.record(JOB, WHEN)["submitted_at"] is None

    def test_the_jd_is_hashed_for_the_repost_detector(self):
        assert len(take.record(JOB, WHEN)["jd_hash"]) == 40

    def test_no_text_means_no_hash(self):
        assert take.record({**JOB, "description": ""}, WHEN)["jd_hash"] is None


class TestCreate:
    def test_it_writes_both_files(self, tmp_path):
        folder, _ = take.create(tmp_path, JOB, WHEN)
        assert (folder / "application.json").exists()
        assert "Azure and Databricks" in (folder / "jd.md").read_text()

    def test_the_jd_keeps_a_link_back_to_the_posting(self, tmp_path):
        folder, _ = take.create(tmp_path, JOB, WHEN)
        assert JOB["url"] in (folder / "jd.md").read_text()

    def test_a_missing_jd_says_so_rather_than_writing_an_empty_file(self, tmp_path):
        folder, _ = take.create(tmp_path, {**JOB, "description": ""}, WHEN)
        assert "Read it from the page" in (folder / "jd.md").read_text()

    def test_the_record_round_trips_as_json(self, tmp_path):
        folder, record = take.create(tmp_path, JOB, WHEN)
        assert json.loads((folder / "application.json").read_text()) == record


class TestDuplicates:
    """The same vacancy resurfaces months later from another source, and by
    then nobody remembers (D27)."""

    def test_it_finds_an_earlier_application_to_the_same_role(self, tmp_path):
        take.create(tmp_path, JOB, date(2026, 7, 1))
        assert take.already_applied(tmp_path, "Data Idols", "Senior Data Engineer") \
            == ["2026-07-01--data-idols--senior-data-engineer"]

    def test_punctuation_does_not_hide_a_duplicate(self):
        assert take.slugify("Data  Idols!") == take.slugify("data-idols")

    def test_a_different_role_at_the_same_company_is_not_one(self, tmp_path):
        take.create(tmp_path, JOB, date(2026, 7, 1))
        assert take.already_applied(tmp_path, "Data Idols", "Analytics Engineer") == []

    def test_an_unreadable_folder_is_skipped_not_fatal(self, tmp_path):
        (tmp_path / "broken").mkdir()
        (tmp_path / "broken" / "application.json").write_text("{not json")
        assert take.already_applied(tmp_path, "Anyone", "Anything") == []


class TestDiscard:
    """Moved, not deleted. A folder holds a tailored CV, a coverage record and
    the notes behind both, and a wrong `y` should be recoverable."""

    def app(self, tmp_path, name="2026-09-06--northwind--data-engineer"):
        folder = tmp_path / "applications" / name
        folder.mkdir(parents=True)
        (folder / "application.json").write_text("{}")
        (folder / "cv.pdf").write_bytes(b"%PDF")
        return folder

    def test_it_leaves_the_working_set(self, tmp_path):
        folder = self.app(tmp_path)
        take.discard(folder, tmp_path / ".trash")
        assert not folder.exists()

    def test_nothing_is_actually_destroyed(self, tmp_path):
        folder = self.app(tmp_path)
        gone = take.discard(folder, tmp_path / ".trash")
        assert (gone / "cv.pdf").read_bytes() == b"%PDF"

    def test_the_trash_is_made_if_it_is_the_first_one(self, tmp_path):
        take.discard(self.app(tmp_path), tmp_path / ".trash")
        assert (tmp_path / ".trash").is_dir()

    def test_deleting_the_same_id_twice_does_not_overwrite_the_first(
            self, tmp_path):
        """Taking a vacancy again and discarding it again is ordinary."""
        first = take.discard(self.app(tmp_path), tmp_path / ".trash")
        second = take.discard(self.app(tmp_path), tmp_path / ".trash")
        assert first.exists() and second.exists() and first != second

    def test_a_folder_that_is_not_there_says_so(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            take.discard(tmp_path / "nope", tmp_path / ".trash")

    def test_the_trash_is_invisible_to_the_applications_list(self, tmp_path):
        """The list globs applications/*/application.json, so the trash has to
        sit outside that folder, not inside it."""
        from hub import cli
        applications = tmp_path / "applications"
        take.discard(self.app(tmp_path), tmp_path / ".trash")
        cfg = SimpleNamespace(applications=applications)
        assert cli._applications(cfg) == []
