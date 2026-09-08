"""A vacancy that did not come from the radar.

The agent's half is one turn that returns JSON; everything here is what
happens to that JSON, which is where a bad posting becomes a bad application.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from hub import agent, intake

POSTING = {"company": "Northwind", "title": "Data Engineer",
           "location": "London", "description": "5+ years of Python."}


class TestSpottingALink:
    @pytest.mark.parametrize("text", ["https://boards.greenhouse.io/x/jobs/1",
                                      "http://example.com/job"])
    def test_a_url_is_a_url(self, text):
        assert intake.looks_like_url(text)

    @pytest.mark.parametrize("text", ["data idols", "la fosse", "a" * 16,
                                      "greenhouse.io/x"])
    def test_everything_else_is_a_search(self, text):
        """A company name must not be mistaken for a link, and a bare host is
        not one either — `jam take reed` is a search."""
        assert not intake.looks_like_url(text)


class TestWhichBoard:
    """Where the posting lives is not where you found it (D25), and the host
    is the only part of a link that says the former."""

    @pytest.mark.parametrize("url,board", [
        ("https://boards.greenhouse.io/acme/jobs/1", "greenhouse"),
        ("https://jobs.lever.co/acme/abc", "lever"),
        ("https://uk.linkedin.com/jobs/view/x", "linkedin"),
        ("https://acme.com/careers/1", "acme.com"),
        ("https://www.acme.com/careers/1", "acme.com"),
    ])
    def test_the_host_names_it(self, url, board):
        assert intake.channel_of(url) == board

    def test_a_link_with_no_host_is_not_guessed_at(self):
        assert intake.channel_of("not a url") is None


class TestReadingTheReply:
    def test_a_clean_object_comes_through(self):
        assert intake.parse(json.dumps(POSTING))["title"] == "Data Engineer"

    def test_a_sentence_around_it_is_not_a_failure(self):
        """A model that adds a line of preamble has still done the job."""
        text = f"Here is the posting:\n```json\n{json.dumps(POSTING)}\n```"
        assert intake.parse(text)["company"] == "Northwind"

    def test_no_json_at_all_says_what_came_back_instead(self):
        with pytest.raises(intake.IntakeError, match="did not return JSON"):
            intake.parse("I could not open that page.")

    def test_broken_json_is_not_a_crash(self):
        with pytest.raises(intake.IntakeError, match="did not parse"):
            intake.parse('{"company": "Northwind",}')

    def test_the_agent_saying_it_is_not_a_posting_is_believed(self):
        """A login wall and a list of other jobs both look like a page."""
        with pytest.raises(intake.IntakeError, match="a login wall"):
            intake.parse('{"error": "a login wall"}')

    @pytest.mark.parametrize("absent", intake.WANTED)
    def test_a_posting_missing_what_it_needs_is_refused(self, absent):
        """The company and title are the folder's name; the description is the
        whole reason to have taken it."""
        body = {**POSTING, absent: ""}
        with pytest.raises(intake.IntakeError, match=absent):
            intake.parse(json.dumps(body))


class TestTheJobRow:
    def test_it_carries_what_the_page_said(self):
        row = intake.job_row("https://jobs.lever.co/acme/1", POSTING)
        assert row["company"] == "Northwind" and row["source"] == "lever"
        assert row["jd_full"] is True

    def test_the_radar_s_fields_are_empty_rather_than_defaulted(self):
        """A score invented here would be indistinguishable later from one the
        radar gave, and `score_source` exists to keep that answerable."""
        row = intake.job_row("https://x.com/1", POSTING)
        assert row["score"] is None and row["job_id"] is None

    def test_a_pasted_description_wins_over_the_agent_s(self):
        """The paste is the fallback for a fetch that came back thin."""
        row = intake.job_row("https://x.com/1", POSTING, description="the real one")
        assert row["description"] == "the real one"

    def test_an_empty_description_is_not_a_full_jd(self):
        """Coverage judged from nothing is guesswork, and `jd_full` is what
        says so."""
        row = intake.job_row("https://x.com/1", POSTING, description="  ")
        assert row["jd_full"] is False


class TestWhatTheAgentIsAllowed:
    def test_the_tools_that_act_are_denied_not_merely_unlisted(self,
                                                              monkeypatch):
        """The bug this exists for: `--allowed-tools WebFetch` is an approval
        list, not a restriction. A run given only WebFetch fetched the page
        with curl instead, and denying Bash alone moved it to another tool
        that runs commands."""
        seen = {}
        monkeypatch.setattr(agent, "run", lambda *a, **kw: (
            seen.update(kw) or agent.Result(True, json.dumps(POSTING))))
        intake.from_url("https://x.com/1", Path("."))
        assert "Bash" in seen["deny"] and "Task" in seen["deny"]
        assert seen["tools"] == "WebFetch"

    def test_a_refusal_is_reported_rather_than_parsed(self, monkeypatch):
        monkeypatch.setattr(agent, "run",
                            lambda *a, **kw: agent.Result(False, "Not logged in"))
        with pytest.raises(intake.IntakeError, match="Not logged in"):
            intake.from_url("https://x.com/1", Path("."))
