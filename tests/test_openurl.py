"""Opening a link.

Terminal hyperlinks are not an option: curses owns the screen and escape
sequences written through it are not reliably passed on.
"""
from __future__ import annotations

from hub import openurl


class TestOpen:
    def test_an_empty_link_says_so_rather_than_launching_anything(self):
        assert openurl.open_url("") == "no link on this one"

    def test_a_missing_opener_is_reported_with_the_url(self, monkeypatch):
        monkeypatch.setattr(openurl, "opener", lambda: None)
        got = openurl.open_url("https://example.com/1")
        assert "https://example.com/1" in got

    def test_a_failure_is_reported_not_raised(self, monkeypatch):
        monkeypatch.setattr(openurl, "opener", lambda: ["definitely-not-a-command"])
        assert "could not open" in openurl.open_url("https://example.com/1")

    def test_success_says_so(self, monkeypatch):
        monkeypatch.setattr(openurl, "opener", lambda: ["true"])
        assert openurl.open_url("https://example.com/1") == "opened in the browser"

    def test_there_is_an_opener_on_this_platform(self):
        assert openurl.opener() is not None


class TestOpenPath:
    """Same mechanism as a link, different message: "opened in the browser" is
    wrong and briefly confusing when what opened was a PDF viewer."""

    def test_a_missing_file_is_said_so_rather_than_shelled_out(self, tmp_path):
        assert openurl.open_path(tmp_path / "nope.pdf") == "not there to open"

    def test_an_existing_file_is_opened(self, tmp_path, monkeypatch):
        pdf = tmp_path / "cv.pdf"
        pdf.write_bytes(b"%PDF")
        monkeypatch.setattr(openurl, "open_url",
                            lambda url: "opened in the browser")
        assert openurl.open_path(pdf) == "opened"

    def test_a_failure_keeps_its_own_message(self, tmp_path, monkeypatch):
        pdf = tmp_path / "cv.pdf"
        pdf.write_bytes(b"%PDF")
        monkeypatch.setattr(openurl, "open_url", lambda url: "could not open it")
        assert openurl.open_path(pdf) == "could not open it"

    def test_nothing_at_all_does_not_raise(self):
        assert openurl.open_path(None) == "not there to open"
