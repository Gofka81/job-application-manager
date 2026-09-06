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
