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


class TestFit:
    """A terminal is often 80 columns and a set written for 120 wrapped, with
    rows running into each other."""

    COLS = [picker.Column("a", 10, str),
            picker.Column("b", 30, str, flex=True),
            picker.Column("c", 20, str)]

    def widths(self, available):
        return [w for _, w in picker.fit(self.COLS, available)]

    def test_everything_fits_and_the_flex_column_absorbs_the_slack(self):
        assert self.widths(120) == [10, 88, 20]

    def test_the_line_never_exceeds_the_space(self):
        for available in (20, 45, 80, 120, 200):
            got = picker.fit(self.COLS, available)
            assert sum(w for _, w in got) + max(0, len(got) - 1) <= available

    def test_columns_that_do_not_fit_are_dropped_from_the_right(self):
        """A half-drawn column reads as corruption."""
        assert len(self.widths(45)) == 2

    def test_without_a_flex_column_the_widest_takes_the_slack(self):
        cols = [picker.Column("a", 10, str), picker.Column("b", 20, str)]
        assert picker.fit(cols, 60)[1][1] == 49

    def test_a_single_column_still_renders(self):
        assert len(self.widths(20)) == 1

    def test_a_column_wider_than_the_terminal_is_narrowed_not_dropped(self):
        """Dropping it rendered a report screen with a header and nothing
        else. One column cut short is readable; an empty screen is not."""
        wide = [picker.Column("", 200, str)]
        assert picker.fit(wide, 80) == [(wide[0], 80)]

    def test_no_room_at_all_means_no_columns(self):
        assert picker.fit(self.COLS, 0) == []

    def test_a_value_is_cut_to_the_width_it_was_given(self):
        assert picker.Column("x", 30, lambda r: "y" * 50).render(None, 8) == "y" * 8


class TestDeepSearch:
    """Typing filters what is on screen. A job description is kilobytes and
    never travels in a list, so `spark` cannot be found that way — tab hands
    the same text to something that can look deeper."""

    @dataclass
    class Row:
        name: str

    def make(self, deep=None):
        rows = [self.Row("Alto"), self.Row("Cognizant")]
        return picker.Picker(
            rows, [picker.Column("n", 12, lambda r: r.name)],
            search=lambda r: r.name,
            deep=deep or (lambda q: [self.Row(f"found {q}")]))

    def type(self, p, text):
        for ch in text:
            p._key(ord(ch))
        return p

    def test_tab_replaces_the_rows_with_what_the_search_returned(self):
        p = self.type(self.make(), "spark")
        p._key(9)
        assert [r.name for r in p.rows] == ["found spark"]

    def test_the_typed_text_moves_into_the_search_and_the_filter_clears(self):
        p = self.type(self.make(), "spark")
        p._key(9)
        assert p.deep_query == "spark" and p.query == ""

    def test_esc_drops_the_search_before_the_filter(self):
        """One key going back one step at a time."""
        p = self.type(self.make(), "spark")
        p._key(9)
        assert p._key(27) is False
        assert [r.name for r in p.rows] == ["Alto", "Cognizant"]
        assert p._key(27) is None

    def test_tab_does_nothing_without_a_query(self):
        p = self.make()
        p._key(9)
        assert not p.searching and len(p.rows) == 2

    def test_a_failing_search_is_reported_not_raised(self):
        def boom(_):
            raise RuntimeError("radar unreachable")
        p = self.type(self.make(deep=boom), "spark")
        p._key(9)
        assert p.rows == [] and "unreachable" in p.deep_query

    def test_without_a_deep_callback_tab_is_inert(self):
        p = picker.Picker([self.Row("Alto")],
                          [picker.Column("n", 12, lambda r: r.name)],
                          search=lambda r: r.name)
        self.type(p, "x")
        p._key(9)
        assert p.query == "x"


class TestFilterable:
    def test_a_fixed_menu_ignores_typed_characters(self):
        """A short fixed list is not something anyone searches, and taking the
        characters only makes the screen look broken."""
        p = picker.Picker(ROWS, COLUMNS, filterable=False)
        p._key(ord("c"))
        assert p.query == "" and len(p.rows) == 3

    def test_a_list_still_filters_by_default(self):
        p = picker.Picker(ROWS, COLUMNS, search=lambda r: r.company)
        p._key(ord("c"))
        assert p.query == "c"


class TestDetail:
    """A list answers "which one"; the detail answers "is it worth it", which
    needs the whole text rather than a truncated column."""

    def make(self, done=None):
        done = done if done is not None else []
        return picker.Detail(
            "Company · Title", ["a line", "", "another"],
            [picker.Act("a", "apply", lambda: done.append("applied") or "created",
                        confirm="create the application?"),
             picker.Act("s", "score it", lambda: "queued")]), done

    def test_an_action_without_a_confirmation_runs_at_once(self):
        d, _ = self.make()
        d._key(ord("s"))
        assert d.message == "queued"

    def test_a_confirmed_action_asks_first_and_does_nothing_yet(self):
        d, done = self.make()
        d._key(ord("a"))
        assert d.pending.confirm == "create the application?" and done == []

    def test_yes_runs_it(self):
        d, done = self.make()
        d._key(ord("a"))
        d._key(ord("y"))
        assert done == ["applied"] and d.message == "created" and d.pending is None

    def test_no_cancels_and_the_screen_stays(self):
        """The thing being decided about stays visible while you decide."""
        d, done = self.make()
        d._key(ord("a"))
        assert d._key(ord("n")) is True
        assert done == [] and d.pending is None

    def test_esc_also_cancels_the_question_rather_than_leaving(self):
        d, _ = self.make()
        d._key(ord("a"))
        assert d._key(27) is True and d.pending is None

    def test_esc_leaves_when_nothing_is_pending(self):
        d, _ = self.make()
        assert d._key(27) is None

    def test_an_unbound_key_does_nothing(self):
        d, _ = self.make()
        assert d._key(ord("z")) is True and d.message == ""

    def test_scrolling_never_goes_above_the_top(self):
        d, _ = self.make()
        d._key(curses.KEY_UP)
        assert d.top == 0


class TestFold:
    def test_a_long_line_is_wrapped_to_the_width(self):
        assert all(len(l) <= 20 for l in picker._fold("word " * 40, 20))

    def test_a_blank_line_survives_as_a_separator(self):
        assert picker._fold("   ", 40) == [""]

    def test_a_short_line_is_left_alone(self):
        assert picker._fold("short", 40) == ["short"]


class TestExtraKeys:
    """Actions bound to control characters. Letters cannot be used: they
    belong to the filter, and taking one back would hide any row whose text
    contains it."""

    def make(self, calls):
        return picker.Picker(
            ROWS, COLUMNS, search=lambda r: r.company,
            keys={20: ("^t score", lambda p: calls.append("t") or "queued 3"),
                  18: ("^r refresh", lambda p: calls.append("r") or "")})

    def test_a_bound_key_runs_and_shows_what_it_did(self):
        calls = []
        p = self.make(calls)
        p._key(20)
        assert calls == ["t"] and p.message == "queued 3"

    def test_an_action_can_report_nothing(self):
        p = self.make([])
        p._key(18)
        assert p.message == ""

    def test_the_screen_stays_open(self):
        assert self.make([])._key(20) is False

    def test_letters_still_reach_the_filter(self):
        p = self.make([])
        p._key(ord("t"))
        assert p.query == "t"

    def test_an_unbound_control_key_does_nothing(self):
        p = self.make([])
        p._key(21)
        assert p.message == "" and p.query == ""
