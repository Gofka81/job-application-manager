"""The append-only journal, and folding it into a current status."""
from __future__ import annotations

import pytest

from hub import log


def events(*rows):
    out = []
    for i, row in enumerate(rows):
        out.append({"ts": f"2026-09-0{i + 1}T00:00:00+00:00", **row})
    return out


class TestEvent:
    def test_a_status_outside_the_vocabulary_is_refused(self):
        with pytest.raises(ValueError, match="status must be"):
            log.status_event("a", "maybe")

    def test_a_source_outside_the_vocabulary_is_refused(self):
        with pytest.raises(ValueError, match="source must be"):
            log.status_event("a", "submitted", source="rumour")

    def test_a_retraction_needs_no_status(self):
        assert log.status_event("a", None)["to"] is None

    def test_backfill_is_valid_but_excluded_from_timing(self):
        """A date written after the fact is not an observation of time."""
        assert "backfill" in log.SOURCES
        assert "backfill" not in log.DAY_MATH_SOURCES


class TestFold:
    def test_the_latest_observation_wins(self):
        got = log.fold(events({"app_id": "a", "to": "submitted"},
                              {"app_id": "a", "to": "rejected"}))
        assert got == {"a": "rejected"}

    def test_a_retraction_undoes_the_last_one(self):
        got = log.fold(events({"app_id": "a", "to": "submitted"},
                              {"app_id": "a", "to": "rejected"},
                              {"app_id": "a", "to": None}))
        assert got == {"a": "submitted"}

    def test_retracting_everything_leaves_nothing(self):
        got = log.fold(events({"app_id": "a", "to": "submitted"},
                              {"app_id": "a", "to": None}))
        assert got == {}

    def test_a_correction_replaces_the_same_transition(self):
        got = log.fold(events(
            {"app_id": "a", "to": "submitted"},
            {"app_id": "a", "to": "rejected"},
            {"app_id": "a", "to": "rejected", "source": "correction",
             "note": "it was the 9th"}))
        assert got == {"a": "rejected"}

    def test_applications_are_folded_apart(self):
        got = log.fold(events({"app_id": "a", "to": "submitted"},
                              {"app_id": "b", "to": "rejected"}))
        assert got == {"a": "submitted", "b": "rejected"}

    def test_one_application_can_be_asked_about(self):
        got = log.fold(events({"app_id": "a", "to": "submitted"},
                              {"app_id": "b", "to": "rejected"}), app_id="a")
        assert got == {"a": "submitted"}

    def test_order_comes_from_the_timestamp_not_the_file(self):
        got = log.fold([{"ts": "2026-09-02T00:00:00+00:00", "app_id": "a",
                         "to": "rejected"},
                        {"ts": "2026-09-01T00:00:00+00:00", "app_id": "a",
                         "to": "submitted"}])
        assert got == {"a": "rejected"}


class TestFile:
    def test_a_written_event_reads_back(self, tmp_path):
        path = tmp_path / "status.jsonl"
        log.append(path, log.status_event("a", "submitted"))
        assert log.read(path)[0]["to"] == "submitted"

    def test_events_accumulate_rather_than_replace(self, tmp_path):
        path = tmp_path / "status.jsonl"
        log.append(path, log.status_event("a", "submitted"))
        log.append(path, log.status_event("a", "rejected", "email"))
        assert len(log.read(path)) == 2

    def test_a_damaged_line_is_skipped_not_fatal(self, tmp_path):
        path = tmp_path / "status.jsonl"
        log.append(path, log.status_event("a", "submitted"))
        with path.open("a") as f:
            f.write("{half a line\n")
        assert len(log.read(path)) == 1

    def test_no_file_is_an_empty_history(self, tmp_path):
        assert log.read(tmp_path / "nothing.jsonl") == []
