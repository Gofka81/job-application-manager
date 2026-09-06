"""Picker logic, tested without a terminal.

Everything that decides what the user sees lives in plain methods, so the
curses layer stays thin enough to smoke-test and the rest is ordinary code.
"""
from __future__ import annotations

import curses
from dataclasses import dataclass

from hub import picker


@dataclass
class Row:
    company: str
    title: str
    score: float


ROWS = [Row("Northwind", "Senior Data Engineer", 9.0),
        Row("Contoso", "Backend Engineer", 8.0),
        Row("Fabrikam", "Data Platform Engineer", 7.0)]

COLUMNS = [picker.Column("fit", 4, lambda r: f"{r.score:.1f}", right=True),
           picker.Column("company", 12, lambda r: r.company)]


def make(rows=ROWS):
    return picker.Picker(rows, COLUMNS, search=lambda r: f"{r.company} {r.title}")


class TestColumns:
    def test_a_value_is_padded_to_its_width(self):
        assert COLUMNS[1].render(ROWS[0]) == "Northwind   "

    def test_a_long_value_is_cut_not_wrapped(self):
        assert len(COLUMNS[1].render(Row("A" * 40, "", 1))) == 12

    def test_right_alignment(self):
        assert COLUMNS[0].render(ROWS[0]) == " 9.0"


class TestFiltering:
    def test_no_query_shows_everything(self):
        assert len(make().rows) == 3

    def test_typing_filters_on_the_search_text(self):
        p = make()
        for ch in "contoso":
            p._key(ord(ch))
        assert [r.company for r in p.rows] == ["Contoso"]

    def test_the_title_is_searched_too(self):
        p = make()
        for ch in "platform":
            p._key(ord(ch))
        assert [r.company for r in p.rows] == ["Fabrikam"]

    def test_backspace_widens_it_again(self):
        p = make()
        for ch in "contoso":
            p._key(ord(ch))
        p._key(127)
        assert len(p.rows) == 1
        for _ in range(6):
            p._key(127)
        assert len(p.rows) == 3

    def test_escape_clears_the_filter(self):
        p = make()
        for ch in "contoso":
            p._key(ord(ch))
        p._key(27)
        assert len(p.rows) == 3

    def test_filtering_resets_the_cursor(self):
        """Otherwise the highlight sits past the end of a shorter list."""
        p = make()
        p._key(curses.KEY_DOWN)
        p._key(curses.KEY_DOWN)
        p._key(ord("c"))
        assert p.cursor == 0


class TestChoosing:
    def test_enter_returns_the_highlighted_row(self):
        p = make()
        p._key(curses.KEY_DOWN)
        assert p._key(10).company == "Contoso"

    def test_esc_backs_out_when_there_is_no_filter(self):
        assert make()._key(27) is None

    def test_esc_clears_the_filter_before_it_leaves(self):
        """The same key going back one step at a time."""
        p = make()
        p._key(ord("c"))
        assert p._key(27) is False and p.query == ""
        assert p._key(27) is None

    def test_ctrl_c_leaves(self):
        assert make()._key(3) is None

    def test_enter_on_an_empty_filter_result_returns_nothing(self):
        p = make()
        for ch in "zzz":
            p._key(ord(ch))
        assert p._key(10) is None

    def test_movement_keeps_looping(self):
        assert make()._key(curses.KEY_DOWN) is False


class TestAvailability:
    def test_not_a_terminal_means_not_usable(self):
        class NotATty:
            def isatty(self):
                return False
        assert not picker.usable(NotATty())

    def test_an_empty_list_never_opens(self):
        assert picker.Picker([], COLUMNS).run() is None


class TestWrap:
    def test_it_stops_at_the_line_budget(self):
        assert len(picker._wrap("word " * 200, 20, 2)) == 2

    def test_short_text_is_one_line(self):
        assert picker._wrap("short reason", 40, 2) == ["short reason"]


class TestArrowSequences:
    """Both encodings must work, not the one that happened to be tested.

    With keypad mode on, ncurses decodes the application-mode sequence
    (ESC O B) into KEY_DOWN. tmux, screen and some terminals send the
    normal-mode form (ESC [ B) anyway, and then the raw bytes arrive — which
    would land in the filter as the text "[B" with nothing to show what broke.
    """

    class FakeScreen:
        def __init__(self, keys):
            self.keys = list(keys)

        def getch(self):
            return self.keys.pop(0) if self.keys else -1

        def nodelay(self, _flag):
            pass

    def read(self, *keys):
        return picker.Picker.read_key(self.FakeScreen(keys))

    def test_application_mode_is_decoded_by_ncurses(self):
        assert self.read(curses.KEY_DOWN) == curses.KEY_DOWN

    def test_normal_mode_bytes_are_decoded_here(self):
        assert self.read(27, ord("["), ord("B")) == curses.KEY_DOWN
        assert self.read(27, ord("["), ord("A")) == curses.KEY_UP

    def test_the_o_form_is_decoded_too(self):
        assert self.read(27, ord("O"), ord("B")) == curses.KEY_DOWN

    def test_a_bare_escape_stays_an_escape(self):
        assert self.read(27) == 27

    def test_an_unknown_sequence_does_not_reach_the_filter(self):
        assert self.read(27, ord("["), ord("Z")) == 27

    def test_an_ordinary_key_passes_straight_through(self):
        assert self.read(ord("j")) == ord("j")


class TestLettersReachTheFilter:
    """The bug this class exists for: the picker bound j, k, g, G and q, so
    those letters never reached the filter and a company containing one could
    not be searched for."""

    def type(self, text):
        p = make()
        for ch in text:
            p._key(ord(ch))
        return p

    def test_g_filters_instead_of_jumping(self):
        assert self.type("g").query == "g"

    def test_q_filters_instead_of_quitting(self):
        p = self.type("q")
        assert p.query == "q"

    def test_j_and_k_filter_instead_of_moving(self):
        p = self.type("jk")
        assert p.query == "jk" and p.cursor == 0

    def test_a_real_company_name_with_those_letters(self):
        p = self.type("cognizant")
        assert p.query == "cognizant"


class TestModes:
    def rows_with(self, *ages):
        @dataclass
        class Aged:
            age: int
        return [Aged(a) for a in ages]

    def picker_with(self, rows):
        return picker.Picker(
            rows, [picker.Column("age", 4, lambda r: str(r.age))],
            modes=[("48h", lambda r: r.age <= 2),
                   ("7d", lambda r: r.age <= 7),
                   ("all", lambda r: True)])

    def test_the_first_mode_applies_from_the_start(self):
        p = self.picker_with(self.rows_with(1, 5, 30))
        assert [r.age for r in p.rows] == [1]

    def test_right_widens_it(self):
        p = self.picker_with(self.rows_with(1, 5, 30))
        p._key(curses.KEY_RIGHT)
        assert [r.age for r in p.rows] == [1, 5] and p.mode_label == "7d"

    def test_it_wraps_around(self):
        p = self.picker_with(self.rows_with(1, 5, 30))
        for _ in range(3):
            p._key(curses.KEY_RIGHT)
        assert p.mode_label == "48h"

    def test_left_goes_the_other_way(self):
        p = self.picker_with(self.rows_with(1, 5, 30))
        p._key(curses.KEY_LEFT)
        assert p.mode_label == "all" and len(p.rows) == 3

    def test_a_mode_and_a_filter_apply_together(self):
        p = self.picker_with(self.rows_with(1, 5, 30))
        p._key(curses.KEY_LEFT)          # all
        p._key(ord("3"))                 # matches "30"
        assert [r.age for r in p.rows] == [30]

    def test_no_modes_means_no_filtering_by_mode(self):
        assert len(make().rows) == 3
