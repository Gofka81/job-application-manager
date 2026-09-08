"""Picker logic, tested without a terminal.

Everything that decides what the user sees lives in plain methods, so the
curses layer stays thin enough to smoke-test and the rest is ordinary code.
"""
from __future__ import annotations

import curses
from dataclasses import dataclass
from unittest.mock import patch

import pytest

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


class TestFilterBar:
    """One bar rather than a key per filter. A screen with six control keys is
    one nobody remembers, which is why the radar's own dashboard puts them
    behind a single control with a count."""

    @dataclass
    class Row:
        age: int
        src: str

    ROWS = [Row(1, "linkedin"), Row(5, "indeed"), Row(30, "reed")]

    def make(self, reload=None):
        filters = [
            picker.Filter("age", [("48h", 2), ("7d", 7), ("all", None)],
                          keep=lambda r, v: v is None or r.age <= v,
                          reload=reload),
            picker.Filter("source", [("any", None), ("linkedin", "linkedin")],
                          keep=lambda r, v: v is None or r.src == v),
        ]
        return picker.Picker(self.ROWS, [picker.Column("a", 6, lambda r: str(r.age))],
                             filters=filters)

    def test_the_first_option_applies_from_the_start(self):
        assert [r.age for r in self.make().rows] == [1]

    def test_the_bar_opens_on_ctrl_f(self):
        p = self.make()
        p._key(6)
        assert p.filters_open

    def test_while_it_is_open_the_arrows_belong_to_it(self):
        p = self.make()
        p._key(6)
        p._key(curses.KEY_DOWN)
        assert p.cursor == 0 and [r.age for r in p.rows] == [1, 5]

    def test_left_and_right_move_between_fields(self):
        p = self.make()
        p._key(6)
        p._key(curses.KEY_RIGHT)
        p._key(curses.KEY_DOWN)
        assert p.filters[1].label == "linkedin"

    def test_filters_combine_rather_than_replace(self):
        p = self.make()
        p._key(6)
        p._key(curses.KEY_DOWN)          # age 7d
        p._key(curses.KEY_RIGHT)
        p._key(curses.KEY_DOWN)          # source linkedin
        assert [r.age for r in p.rows] == [1]

    def test_esc_closes_the_bar_and_keeps_the_choices(self):
        p = self.make()
        p._key(6)
        p._key(curses.KEY_DOWN)
        p._key(27)
        assert not p.filters_open and [r.age for r in p.rows] == [1, 5]

    def test_the_arrows_go_back_to_the_list_once_it_is_closed(self):
        p = self.make()
        p._key(6)
        p._key(27)
        p._key(curses.KEY_DOWN)
        assert p.cursor == 1

    def test_values_wrap_around(self):
        p = self.make()
        p._key(6)
        for _ in range(3):
            p._key(curses.KEY_DOWN)
        assert p.filters[0].label == "48h"

    def test_a_choice_that_needs_refetching_says_so(self):
        seen = []
        p = self.make(reload=lambda pk: seen.append("fetched") or "")
        p._key(6)
        p._key(curses.KEY_DOWN)
        assert seen == ["fetched"]

    def test_only_a_changed_filter_shows_in_the_title(self):
        p = self.make()
        assert p.filters[0].summary() == ""
        p.filters[0].index = 1
        assert p.filters[0].summary() == "age: 7d"

    def test_the_bar_renders_the_focused_field(self):
        p = self.make()
        assert p.filters[0].render(True).startswith("▸")
        assert p.filters[0].render(False).startswith(" ")


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


class TestHints:
    """An option whose meaning is not obvious from its name is one people
    leave alone."""

    def make(self):
        return picker.Filter("sort", [("priority", "p"), ("fit", "s")],
                             hints={"priority": "your cities first",
                                    "fit": "best score first"})

    def test_the_hint_follows_the_selected_option(self):
        f = self.make()
        assert f.hint == "your cities first"
        f.index = 1
        assert f.hint == "best score first"

    def test_an_option_without_one_says_nothing(self):
        assert picker.Filter("x", [("a", 1)]).hint == ""


class TestConfirming:
    """A key that destroys something must not act on one keystroke."""

    def screen(self, run):
        return picker.Picker(
            [{"n": 1}, {"n": 2}],
            [picker.Column("n", 4, lambda r: str(r["n"]))],
            keys={24: ("^x delete", run)},
        )

    def asking(self, ran):
        return lambda screen: picker.Ask("Delete this?",
                                         lambda: ran.append(1) or "deleted")

    def test_the_key_alone_does_nothing_yet(self):
        ran = []
        screen = self.screen(self.asking(ran))
        screen._key(24)
        assert ran == [] and screen.pending is not None

    def test_yes_runs_it(self):
        ran = []
        screen = self.screen(self.asking(ran))
        screen._key(24)
        screen._key(ord("y"))
        assert ran == [1] and screen.message == "deleted"

    def test_no_does_not(self):
        ran = []
        screen = self.screen(self.asking(ran))
        screen._key(24)
        screen._key(ord("n"))
        assert ran == [] and screen.pending is None

    def test_escape_answers_no_rather_than_leaving_the_screen(self):
        """Otherwise a half-asked question is answered by walking away."""
        ran = []
        screen = self.screen(self.asking(ran))
        screen._key(24)
        assert screen._key(27) is False and ran == []

    def test_a_pending_question_swallows_the_arrows(self):
        """Moving the cursor under an open question would change which row the
        answer applies to."""
        screen = self.screen(self.asking([]))
        screen._key(24)
        screen._key(curses.KEY_DOWN)
        assert screen.cursor == 0

    def test_a_handler_returning_plain_text_still_just_reports(self):
        screen = self.screen(lambda s: "nothing selected")
        screen._key(24)
        assert screen.pending is None and screen.message == "nothing selected"


class TestTheScreenSaysWhatEachThingIs:
    """One colour for the whole bar left `age 48h 7d all sort priority fit`
    reading as a single run of words, with nothing to say which of them is a
    field, which is a value, and which is the sentence explaining both."""

    def filters(self):
        return [picker.Filter("age", [("48h", 2), ("7d", 7), ("all", None)],
                              hints={"48h": "published in the last two days"}),
                picker.Filter("sort", [("priority", "p"), ("fit", "s")])]

    def screen(self, focus=0):
        p = picker.Picker([], [], filters=self.filters())
        p.focus = focus
        return p

    def roles(self, line):
        return [role for _, role in line]

    def test_a_field_is_named_and_its_values_are_not(self):
        got = dict((text.strip(), role)
                   for text, role in self.filters()[0].segments(False))
        assert got["age"] == "name"
        assert got["7d"] == "option" and got["all"] == "option"

    def test_the_value_that_is_on_is_marked_apart_from_the_rest(self):
        chosen = [role for text, role in self.filters()[0].segments(False)
                  if "48h" in text]
        assert chosen == ["current"]

    def test_the_field_the_arrows_will_change_is_marked_further(self):
        """Two fields both showing a chosen value, and only one of them is
        what the next keypress edits."""
        chosen = [role for text, role in self.filters()[0].segments(True)
                  if "48h" in text]
        assert chosen == ["focus"]

    def test_the_brackets_stay_so_it_reads_without_colour(self):
        assert "[48h]" in self.filters()[0].render(False)

    def test_the_text_is_the_same_however_it_is_coloured(self):
        """`render` is what the tests and any plain rendering use; the pieces
        are what the screen draws. Two sources for one bar would drift."""
        for focused in (True, False):
            f = self.filters()[0]
            assert f.render(focused) == "".join(t for t, _ in f.segments(focused))

    def test_the_explanation_is_the_colour_the_radar_reasons_in(self):
        """The hint and the triage reason under the list are the same kind of
        writing — the screen talking, rather than the data."""
        hint = self.screen().bar(100)[-2]
        assert self.roles(hint)[-1] == "hint"
        assert self.roles(hint)[0] == "name"

    def test_the_fields_are_ruled_apart_and_not_only_coloured_apart(self):
        """Three spaces between two fields left the eye finding the boundary
        by reading the words. A terminal with no colour has only this."""
        line = next(l for l in self.screen().bar(100) if len(l) > 3)
        assert "rule" in self.roles(line)

    def test_the_bar_is_ruled_off_from_the_list_above_it(self):
        assert self.roles(self.screen().bar(100)[0]) == ["rule"]

    def test_a_narrow_terminal_wraps_the_fields_rather_than_losing_them(self):
        lines = self.screen().bar(30)
        drawn = "".join(t for line in lines for t, _ in line)
        assert "age" in drawn and "sort" in drawn

    def test_the_keys_are_the_last_word_and_are_kept_quiet(self):
        assert self.roles(self.screen().bar(100)[-1]) == ["keys"]


class TestColourIsNotTheOnlyChannel:
    """A terminal without colours, and anyone who cannot tell cyan from
    magenta, still has to be able to work the bar."""

    def test_without_colour_a_chosen_value_is_still_set_apart(self):
        import curses
        assert picker.style("current") == curses.A_BOLD
        assert picker.style("option") == curses.A_DIM

    def test_without_colour_the_focused_value_is_the_loudest(self):
        import curses
        assert picker.style("focus") == curses.A_REVERSE

    def test_a_role_nobody_defined_draws_as_ordinary_text(self):
        import curses
        assert picker.style("nonsense") == curses.A_NORMAL


class TestTrafficLights:
    """A column of scores is read for which ones are high. Reading twenty of
    them digit by digit is the slow way to do that."""

    def rows(self):
        class J:
            def __init__(self, score, days):
                self.score, self.age_days = score, days
        return J

    def test_a_column_with_no_opinion_draws_as_ordinary_text(self):
        """Company and title mean nothing better or worse; colouring them
        would be decoration, and decoration is what makes a screen unreadable."""
        assert picker.Column("company", 8, str).role_of(object()) == "cell"

    def test_a_column_with_one_asks_it_per_row(self):
        column = picker.Column("fit", 4, str, role=lambda r: "good" if r else "poor")
        assert column.role_of(True) == "good" and column.role_of(False) == "poor"


class TestTheCursorIsNotLostToTheColours:
    """Colouring the cells one at a time is what nearly ate the cursor: the
    selected row is one highlight over the whole line, and the role for it has
    to exist or the row draws as ordinary text with nothing marking it."""

    def test_the_selected_row_has_a_style_of_its_own(self):
        import curses
        assert picker.style("selected") != curses.A_NORMAL

    def test_it_survives_a_terminal_without_colour(self):
        import curses
        assert picker.style("selected") == curses.A_REVERSE


class TestTheDetailScreenKeepsItsLayout:
    """`_fold` rejoins words on single spaces, which is right for a paragraph
    of a job description and wrong for a field: every line of the vacancy
    screen was laid out as `fit         9.0/10` and drawn as `fit 9.0/10`."""

    def test_a_laid_out_line_is_not_reflowed(self):
        line = [("  fit      ", "name"), ("9.0/10", "good")]
        d = picker.Detail("t", [line])
        assert d.rows(80) == [line]

    def test_prose_is_still_wrapped_to_the_screen(self):
        d = picker.Detail("t", ["one two three four five six seven eight"])
        assert len(d.rows(20)) > 1

    def test_a_blank_line_stays_a_blank_line(self):
        """The gaps are what separate one section from the next."""
        assert picker.Detail("t", [""]).rows(80) == [[("", "cell")]]

    def test_plain_text_carries_the_ordinary_role(self):
        rows = picker.Detail("t", ["hello"]).rows(80)
        assert rows == [[("hello", "cell")]]

    def test_the_two_kinds_can_sit_in_one_screen(self):
        """A vacancy is fields, then the radar's prose, then the posting."""
        d = picker.Detail("t", [[("  fit      ", "name"), ("9.0", "good")],
                                "", "a paragraph of the job description"])
        roles = [role for line in d.rows(80) for _, role in line]
        assert "name" in roles and "good" in roles and "cell" in roles


class TestTheReasonUnderTheListIsNamed:
    """A yellow paragraph appearing below a list of vacancies could be an
    error, a note, or the start of the posting. A reader who has to work that
    out for themselves generally works it out as noise."""

    def screen(self, label=""):
        return picker.Picker(ROWS, COLUMNS, detail=lambda r: "because",
                             detail_label=label)

    def test_the_name_sits_in_the_rule_that_was_already_there(self):
        """No line of its own: the screen has none to spare, and the rule was
        drawn under the list anyway."""
        pieces = self.screen("why the radar rated it").detail_rule(60)
        assert [role for _, role in pieces] == ["rule", "name", "rule"]
        assert "why the radar rated it" in "".join(t for t, _ in pieces)

    def test_the_rule_still_reaches_across(self):
        assert len("".join(t for t, _ in
                           self.screen("why").detail_rule(60))) == 60

    def test_no_name_is_still_a_rule(self):
        assert self.screen().detail_rule(20) == [("─" * 20, "rule")]

    def test_a_name_wider_than_the_screen_does_not_wrap_the_line(self):
        """A rule that folded onto a second line would push a vacancy off the
        list to say something the reader already knew."""
        pieces = self.screen("a very long label indeed").detail_rule(10)
        assert "\n" not in "".join(t for t, _ in pieces)


class TestARedrawTick:
    """A screen showing something that is still happening has to be able to
    change without being touched. Without a timeout, curses blocks on the next
    keypress and a row keeps saying what was true when the screen opened."""

    class FakeScreen:
        """getch returns -1 the way a timed-out curses screen does."""

        def __init__(self, keys):
            self.keys = list(keys)
            self.timeouts = []

        def getch(self):
            return self.keys.pop(0) if self.keys else 27

        def timeout(self, ms):
            self.timeouts.append(ms)

        def nodelay(self, on):
            pass

        def erase(self):
            pass

        def refresh(self):
            pass

        def addstr(self, *a):
            pass

        def getmaxyx(self):
            return 24, 80

    def loop(self, screen, thing):
        """Run one screen's loop without a terminal under it."""
        with patch.object(picker, "start_colours", lambda: None), \
                patch.object(curses, "curs_set", lambda n: None), \
                patch.object(type(thing), "_draw", lambda self, s: None):
            thing._loop(screen)

    def test_a_tick_redraws_instead_of_being_read_as_a_key(self):
        """-1 is not a keystroke. Passing it on would run it through every
        binding on the screen."""
        seen = []
        d = picker.Detail("t", ["x"], refresh=lambda: seen.append(1),
                          refresh_ms=700)
        self.loop(self.FakeScreen([-1, -1, 27]), d)
        assert len(seen) == 3        # two ticks and the draw before the escape

    def test_the_timeout_is_reapplied_every_time(self):
        """`read_key` restores blocking mode after decoding an escape
        sequence, which cancels a timeout set once at the top."""
        screen = self.FakeScreen([-1, -1, 27])
        self.loop(screen, picker.Detail("t", ["x"], refresh_ms=700))
        assert screen.timeouts == [700, 700, 700]

    def test_a_screen_with_nothing_live_still_blocks(self):
        """Waking a screen that cannot change is a redraw nobody asked for."""
        screen = self.FakeScreen([27])
        self.loop(screen, picker.Detail("t", ["x"]))
        assert screen.timeouts == [-1]

    def test_the_refresh_runs_before_the_draw_not_after(self):
        """Otherwise every screen is one tick behind what it is reporting."""
        order = []
        d = picker.Detail("t", ["x"], refresh=lambda: order.append("refresh"),
                          refresh_ms=700)
        with patch.object(picker, "start_colours", lambda: None), \
                patch.object(curses, "curs_set", lambda n: None), \
                patch.object(picker.Detail, "_draw",
                             lambda self, s: order.append("draw")):
            d._loop(self.FakeScreen([27]))
        assert order[:2] == ["refresh", "draw"]

    def test_a_list_ticks_the_same_way(self):
        screen = self.FakeScreen([-1, 27])
        self.loop(screen, picker.Picker(
            [{"n": 1}], [picker.Column("n", 4, lambda r: "1")], refresh_ms=700))
        assert screen.timeouts == [700, 700]
