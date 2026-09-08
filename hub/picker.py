"""A one-screen list picker.

Typing `jam take 3` works and always will — the agent needs it, and a number
in a script is unambiguous. This exists because a human choosing among twenty
vacancies should not have to read, remember and retype a number.

It is a picker, not a dashboard. No tabs, no panes, no editing: move, filter,
choose. career-ops' equivalent is 11k lines of Go with report previews and an
inline status editor; this is one screen because one screen is what choosing
needs.

Deliberately optional. If stdout is not a terminal — an agent running the
command, a pipe, CI — the caller prints the plain table instead, so nothing
downstream depends on a human being present.
"""
from __future__ import annotations

import curses
import sys
from dataclasses import dataclass, field
from typing import Callable, Sequence


def usable(stream=None) -> bool:
    """Only when a person is actually looking at a terminal."""
    stream = stream or sys.stdout
    return bool(getattr(stream, "isatty", lambda: False)()) and sys.stdin.isatty()


#: What the screen is made of, and what each kind of thing looks like.
#:
#: Four kinds, and the rule is what a piece of text *is*, never where it sits:
#:
#:   name      what something is called — the screen's title, a column header,
#:             a filter's field. Cyan.
#:   current   a value that is switched on right now. Magenta, and bracketed
#:             as well, so it survives a terminal with no colour.
#:   option    a value that is available and not chosen. Dim.
#:   hint      prose explaining the thing above it. Yellow — the same yellow as
#:             the radar's reasoning under the list, because it is the same
#:             kind of writing: the screen talking rather than the data.
#:
#: One colour for the lot is what this replaces: `age 48h 7d all sort priority`
#: read as one run of words with no way to tell a question from an answer.
_PAIRS = {"selected": 1, "name": 2, "hint": 3, "current": 4,
          "good": 5, "poor": 6, "remote": 7}
_ROLES = {
    #: The row the cursor is on, and the yes/no bar, which take a whole line.
    "selected": lambda: curses.color_pair(1),
    "mark": lambda: curses.color_pair(2) | curses.A_BOLD,
    "name": lambda: curses.color_pair(2) | curses.A_BOLD,
    "header": lambda: curses.color_pair(2) | curses.A_DIM,
    "current": lambda: curses.color_pair(4) | curses.A_BOLD,
    #: The current value of the field the arrows are pointing at, which is the
    #: one thing on the bar a keypress will change.
    "focus": lambda: curses.color_pair(1) | curses.A_BOLD,
    "option": lambda: curses.A_DIM,
    "hint": lambda: curses.color_pair(3),
    "keys": lambda: curses.A_DIM,
    "gap": lambda: curses.A_NORMAL,
    "cell": lambda: curses.A_NORMAL,
    #: Traffic lights, for the columns where a number means better or worse.
    #: Bold rather than another hue for the good end: on a dark terminal green
    #: is the quietest of the three, and it is the one worth spotting.
    "good": lambda: curses.color_pair(5) | curses.A_BOLD,
    "fair": lambda: curses.color_pair(3),
    "poor": lambda: curses.color_pair(6),
    "none": lambda: curses.A_DIM,
    #: Not a traffic light: remote is neither good nor bad, it is a different
    #: kind of fact from the place beside it, so it gets a colour of its own
    #: rather than a brighter or dimmer version of the location's.
    "remote": lambda: curses.color_pair(7),
    #: The lines and separators that do the same work as the colours, for a
    #: terminal that has none and for anyone who reads shape faster than hue.
    "rule": lambda: curses.A_DIM,
}


def start_colours() -> None:
    """Sets the pairs up if the terminal has any."""
    if not curses.has_colors():
        return
    curses.use_default_colors()
    curses.init_pair(_PAIRS["selected"], curses.COLOR_BLACK, curses.COLOR_CYAN)
    curses.init_pair(_PAIRS["name"], curses.COLOR_CYAN, -1)
    curses.init_pair(_PAIRS["hint"], curses.COLOR_YELLOW, -1)
    curses.init_pair(_PAIRS["current"], curses.COLOR_MAGENTA, -1)
    curses.init_pair(_PAIRS["good"], curses.COLOR_GREEN, -1)
    curses.init_pair(_PAIRS["poor"], curses.COLOR_RED, -1)
    curses.init_pair(_PAIRS["remote"], curses.COLOR_BLUE, -1)


def style(role: str) -> int:
    """The attribute for one kind of text.

    Without colour the roles collapse onto bold and dim, which still separates
    a chosen value from the rest — the brackets do the rest of the work.
    """
    try:
        coloured = curses.has_colors()
    except curses.error:
        coloured = False               # asked before a screen exists, in a test
    if not coloured:
        return {"current": curses.A_BOLD, "focus": curses.A_REVERSE,
                "selected": curses.A_REVERSE,
                "name": curses.A_BOLD, "good": curses.A_BOLD}.get(
            role, curses.A_DIM
            if role in ("option", "keys", "hint", "rule", "none")
            else curses.A_NORMAL)
    return _ROLES.get(role, lambda: curses.A_NORMAL)()


@dataclass
class Ask:
    """What a key handler returns when it must not act on one keystroke.

    The list's own footer becomes the question, so the row being decided
    about stays on screen while you decide. Destructive keys return one of
    these instead of doing the work.
    """
    question: str
    run: Callable[[], str]


@dataclass
class Column:
    header: str
    width: int
    value: Callable[[object], str]
    right: bool = False
    #: Give this column whatever width is left over. At most one per set.
    flex: bool = False
    #: What this cell is worth, as a role name, for a column whose numbers
    #: mean better and worse. A list of scores is read for which ones are high,
    #: and reading twenty of them digit by digit is the slow way to do it.
    role: Callable[[object], str] | None = None
    #: For a cell that is not all one thing: returns (text, role) pieces. A
    #: location reading `remote · London` is two facts, and only one of them is
    #: the place.
    parts: Callable[[object], list[tuple[str, str]]] | None = None

    def role_of(self, row: object) -> str:
        return self.role(row) if self.role else "cell"

    def pieces(self, row: object, width: int | None = None) -> list[tuple[str, str]]:
        """The cell as (text, role) pieces, cut and padded to the width."""
        width = self.width if width is None else width
        parts = (self.parts(row) if self.parts
                 else [(str(self.value(row)), self.role_of(row))])
        out, used = [], 0
        for text, role in parts:
            if used >= width:
                break
            text = str(text)[: width - used]
            out.append((text, role))
            used += len(text)
        if (pad := width - used) > 0:
            out.insert(0 if self.right else len(out), (" " * pad, "cell"))
        return out

    def render(self, row: object, width: int | None = None) -> str:
        """The same cell as plain text, so the two cannot drift apart."""
        return "".join(text for text, _ in self.pieces(row, width))


def fit(columns: Sequence[Column], available: int) -> list[tuple[Column, int]]:
    """Which columns fit, and how wide each gets.

    A terminal is often 80 columns and a column set written for 120 wrapped,
    with rows running into each other. Columns are laid out left to right
    while there is room; the first to overflow is dropped along with the rest,
    because a half-drawn column reads as corruption.
    """
    out, used = [], 0
    for column in columns:
        need = column.width + (1 if out else 0)
        if used + need > available:
            break
        out.append((column, column.width))
        used += need

    # A single column wider than the terminal used to drop everything, so a
    # report screen rendered its header and nothing else. Narrow it instead:
    # one column cut short is still readable, an empty screen is not.
    if not out and columns and available > 0:
        return [(columns[0], available)]

    if out and (spare := available - used) > 0:
        flexible = next((i for i, (c, _) in enumerate(out) if c.flex), None)
        if flexible is None:
            flexible = max(range(len(out)), key=lambda i: out[i][1])
        column, width = out[flexible]
        out[flexible] = (column, width + spare)
    return out


class Picker:
    def __init__(self, rows: Sequence, columns: Sequence[Column],
                 title: str = "", search: Callable[[object], str] | None = None,
                 detail: Callable[[object], str] | None = None,
                 detail_label: str = "",
                 deep: Callable[[str], Sequence] | None = None,
                 deep_label: str = "deep search",
                 filterable: bool = True,
                 keys: dict[int, tuple[str, Callable[["Picker"], str]]] | None = None,
                 gate: Callable[[object], bool] | None = None,
                 filters: Sequence[Filter] | None = None,
                 extra_label: Callable[["Picker"], str] | None = None):
        self.all = list(rows)
        # Cycled with left/right. A filter the caller wants reachable without
        # leaving the screen and rerunning the command with a flag.
        # Typing filters what is on screen. Some of what you want to search is
        # not on screen — a job description is kilobytes and never travels in a
        # list — so tab hands the same text to something that can look deeper.
        self.deep = deep
        self.deep_label = deep_label
        self.deep_query = ""
        self.base = list(rows)
        # A short fixed list is not something anyone searches, and letting it
        # take typed characters only makes the screen look broken.
        self.filterable = filterable
        # Extra actions, keyed by control character. Letters cannot be used:
        # they belong to the filter, and taking one back would hide any row
        # whose text contains it.
        self.keys = dict(keys or {})
        self.pending: Ask | None = None
        self.message = ""
        # A predicate the caller can flip from a key, kept outside `modes`
        # because it combines with them rather than replacing them.
        self.gate = gate
        self.extra_label = extra_label
        # What the text under the list is. A yellow paragraph appearing below
        # a list of vacancies could be anything — an error, a note, the start
        # of the posting — and a reader who has to work that out for themselves
        # generally works it out as noise and stops looking.
        self.detail_label = detail_label
        # A bar rather than a key per filter: the radar's dashboard puts them
        # behind one control with a count, and a screen with six control keys
        # is one nobody remembers.
        self.filters = list(filters or [])
        self.filters_open = False
        self.focus = 0
        self.columns = list(columns)
        self.title = title
        self.search = search or (lambda r: str(r))
        self.detail = detail
        self.query = ""
        self.cursor = 0
        self.top = 0

    @property
    def searching(self) -> bool:
        return bool(self.deep_query)

    @property
    def rows(self) -> list:
        rows = self.all
        if self.gate:
            rows = [r for r in rows if self.gate(r)]
        for f in self.filters:
            rows = [r for r in rows if f.keeps(r)]
        if self.query:
            q = self.query.lower()
            rows = [r for r in rows if q in self.search(r).lower()]
        return rows

    def run(self):
        """Returns the chosen row, or None if the user backed out."""
        if not self.all:
            return None
        return curses.wrapper(self._loop)

    # --- drawing -------------------------------------------------------

    # Arrow keys reach us one of two ways. With keypad mode on, ncurses
    # decodes the terminal's application-mode sequence (ESC O B) into
    # KEY_DOWN. But tmux, screen and some terminals send the normal-mode form
    # (ESC [ B) regardless, and then ncurses hands over the raw bytes — which
    # would land in the filter as the text "[B" with no sign of what went
    # wrong. Reading the sequence ourselves covers both.
    _SEQUENCE = {ord("A"): curses.KEY_UP, ord("B"): curses.KEY_DOWN,
                 ord("C"): curses.KEY_RIGHT, ord("D"): curses.KEY_LEFT,
                 ord("H"): curses.KEY_HOME, ord("F"): curses.KEY_END,
                 ord("5"): curses.KEY_PPAGE, ord("6"): curses.KEY_NPAGE}

    @classmethod
    def read_key(cls, screen) -> int:
        key = screen.getch()
        if key != 27:
            return key
        screen.nodelay(True)
        try:
            first = screen.getch()
            if first == -1:
                return 27                      # a bare escape
            second = screen.getch()
        finally:
            screen.nodelay(False)
        if first in (ord("["), ord("O")) and second != -1:
            return cls._SEQUENCE.get(second, 27)
        return 27

    def _loop(self, screen):
        curses.curs_set(0)
        start_colours()
        while True:
            self._draw(screen)
            result = self._key(self.read_key(screen))
            if result is not False:
                return result

    def _filter_key(self, key):
        """While the bar is open the arrows belong to it, not to the list."""
        if key in (27, 6, 10, 13, curses.KEY_ENTER):
            self.filters_open = False
            return False
        if key == curses.KEY_RIGHT:
            self.focus = (self.focus + 1) % len(self.filters)
        elif key == curses.KEY_LEFT:
            self.focus = (self.focus - 1) % len(self.filters)
        elif key in (curses.KEY_DOWN, curses.KEY_UP):
            f = self.filters[self.focus]
            step = 1 if key == curses.KEY_DOWN else -1
            f.index = (f.index + step) % len(f.options)
            if f.reload:
                self.message = f.reload(self) or ""
            self.cursor = 0
        elif key in (3, 4):
            return None
        return False

    def bar(self, width: int) -> list[list[tuple[str, str]]]:
        """The filter bar as lines of (text, role) pieces, wrapped to fit.

        Text and role rather than text alone because one colour for the whole
        bar made a field, its values and the line explaining them read as a
        single sentence: `age 48h 7d all sort priority fit` says nothing about
        which of those words is a question and which is an answer.
        """
        # A rule between the fields as well as a colour, and one across the top
        # of the bar. Colour alone leaves the same wall of words on a terminal
        # without it, and where three spaces separated two fields the eye had
        # to find the boundary by reading the words.
        gap = "  │ "
        lines, current, used = [[("─" * max(0, width - 4), "rule")]], [], 0
        for i, f in enumerate(self.filters):
            chunk = f.segments(i == self.focus)
            wide = sum(len(text) for text, _ in chunk)
            if current and used + wide + len(gap) > width - 4:
                lines.append(current)
                current, used = list(chunk), wide
            else:
                if current:
                    current.append((gap, "rule"))
                    used += len(gap)
                current += chunk
                used += wide
        if current:
            lines.append(current)
        focused = self.filters[self.focus]
        if focused.hint:
            # Named the same way it is drawn above, so the line explaining a
            # value points at it by colour as well as by word.
            lines.append([(focused.name, "name"), (" · ", "gap"),
                          (focused.label, "current"), (" — ", "gap"),
                          (focused.hint, "hint")])
        lines.append([("←→ field · ↑↓ value · esc close", "keys")])
        return lines

    def _draw_filters(self, screen, height: int, width: int) -> int:
        """Returns how many lines the bar took."""
        lines = self.bar(width)
        for i, line in enumerate(lines):
            y, x = height - 1 - len(lines) + i, 2
            for text, role in line:
                room = width - 3 - x
                if room <= 0:
                    break
                screen.addnstr(y, x, text[:room], room, style(role))
                x += len(text)
        return len(lines)

    def detail_rule(self, width: int) -> list[tuple[str, str]]:
        """The rule under the list, with the label set into it."""
        if not self.detail_label:
            return [("─" * max(0, width), "rule")]
        label = f" {self.detail_label} "
        lead = "──"
        tail = "─" * max(0, width - len(lead) - len(label))
        return [(lead, "rule"), (label, "name"), (tail, "rule")]

    def _deepen(self) -> None:
        self.deep_query = self.query
        try:
            self.all = list(self.deep(self.query))
        except Exception as exc:                 # a failed search is not a crash
            self.deep_query = f"{self.query} — {exc}"
            self.all = []
        self.query = ""
        self.cursor = 0

    def _draw(self, screen):
        screen.erase()
        height, width = screen.getmaxyx()
        rows = self.rows
        bar = self._draw_filters(screen, height, width) if self.filters_open else 0
        # Two lines of chrome at the top, two at the bottom.
        body = max(1, height - 5 - bar - (4 if self.detail else 0))
        self.cursor = max(0, min(self.cursor, len(rows) - 1)) if rows else 0
        self.top = max(min(self.top, self.cursor), self.cursor - body + 1, 0)

        layout = fit(self.columns, width - 3)
        # The title line is the screen's name and then the state it is in, and
        # the two are coloured apart for the same reason the bar is: a count
        # and a filter are answers, not part of what the screen is called.
        title = [(self.title, "name"), (f"   {len(rows)} of {len(self.all)}",
                                        "current")]
        if self.searching:
            title.append((f"   {self.deep_label}: {self.deep_query}", "current"))
        for summary in (f.summary() for f in self.filters):
            if summary:
                title.append((f"   {summary}", "current"))
        if self.extra_label and (extra := self.extra_label(self)):
            title.append((f"   [{extra}]", "current"))
        if self.query:
            title.append((f"   /{self.query}", "current"))
        x = 0
        for text, role in title:
            if (room := width - 1 - x) <= 0:
                break
            screen.addnstr(0, x, text[:room], room, style(role))
            x += len(text)

        # Column names are names, like the fields on the filter bar, and are
        # coloured as such: the row under them is the vacancy, not a label.
        header = "  " + " ".join(c.header.ljust(w)[:w] for c, w in layout)
        screen.addnstr(1, 0, header, width - 1, style("header"))

        for i, row in enumerate(rows[self.top:self.top + body]):
            if self.top + i == self.cursor:
                # The cursor takes the whole line: a row painted three colours
                # under a highlight reads as damage rather than as selection.
                line = "  " + " ".join(c.render(row, w) for c, w in layout)
                screen.addnstr(2 + i, 0, line.ljust(width - 1)[: width - 1],
                               width - 1, style("selected"))
                continue
            x = 2
            for column, w in layout:
                for text, role in column.pieces(row, w):
                    if (room := width - 1 - x) <= 0:
                        break
                    screen.addnstr(2 + i, x, text[:room], room, style(role))
                    x += len(text)
                x += 1                             # the gap between columns

        if self.message:
            screen.addnstr(height - 2, 2, self.message[: width - 3], width - 3,
                           style("hint") | curses.A_BOLD)
        elif self.detail and rows:
            # The radar's reasoning, and the yellow the filter hints borrow:
            # both are the screen explaining itself rather than listing data.
            # Ruled off from the list for the same reason the bar is — it sits
            # under the rows and is about one of them, not another of them —
            # and the rule carries the name of what is below it, which costs no
            # line of a screen that has none to spare.
            x = 2
            for text, role in self.detail_rule(width - 4):
                if (room := width - 3 - x) <= 0:
                    break
                screen.addnstr(2 + body, x, text[:room], room, style(role))
                x += len(text)
            text = self.detail(rows[self.cursor]) or ""
            for j, chunk in enumerate(_wrap(text, width - 3, 2)):
                screen.addnstr(3 + body + j, 2, chunk, width - 3, style("hint"))

        # Kept terse because it has to survive an 80-column terminal; the
        # current sort and filters are shown in the title instead of here.
        parts = ["↑↓ enter"]
        if self.filterable:
            parts.append("type filter")
        if self.deep:
            parts.append(f"tab {self.deep_label}")
        parts += [label for label, _ in self.keys.values()]
        if self.filters:
            parts.append("^f filters")
        parts.append("esc")
        hint = "  " + " · ".join(parts)
        if self.filters_open:
            hint = ""
        if self.pending:
            question = f"  {self.pending.question}   [y] yes   [n] no"
            screen.addnstr(height - 1, 0, question.ljust(width - 1)[: width - 1],
                           width - 1, curses.color_pair(1))
        elif hint:
            screen.addnstr(height - 1, 0, hint[: width - 1], width - 1,
                           curses.A_DIM)
        screen.refresh()

    # --- input ---------------------------------------------------------

    def _key(self, key):
        """False keeps looping; anything else is the result.

        There are no letter shortcuts. Typing filters, and a picker that also
        bound j/k/g/q swallowed those letters before they reached the filter —
        so a company with a `g` in it could not be searched for at all.
        """
        rows = self.rows
        if self.pending:
            if key in (ord("y"), ord("Y")):
                ask, self.pending = self.pending, None
                self.message = ask.run() or ""
            elif key in (ord("n"), ord("N"), 27):
                self.pending = None
                self.message = "cancelled"
            return False
        if self.filters_open:
            return self._filter_key(key)
        if key == 6 and self.filters:            # ctrl-f
            self.filters_open = True
            self.message = ""
        elif key == curses.KEY_DOWN:
            self.cursor += 1
        elif key == curses.KEY_UP:
            self.cursor = max(0, self.cursor - 1)
        elif key == curses.KEY_NPAGE:
            self.cursor += 10
        elif key == curses.KEY_PPAGE:
            self.cursor = max(0, self.cursor - 10)
        elif key == curses.KEY_HOME:
            self.cursor = 0
        elif key == curses.KEY_END:
            self.cursor = len(rows) - 1
        elif key in (10, 13, curses.KEY_ENTER):
            return rows[self.cursor] if rows else None
        elif key in self.keys:
            result = self.keys[key][1](self)
            if isinstance(result, Ask):
                self.pending, self.message = result, ""
            else:
                self.message = result or ""
        elif key == 9 and self.deep and self.query:
            self._deepen()
        elif key == 27:
            # Esc goes back one step at a time: it drops a deep search first,
            # then the filter, and only leaves when there is nothing left to
            # undo.
            if self.searching:
                self.deep_query = ""
                self.all = list(self.base)
                self.cursor = 0
            elif self.query:
                self.query = ""
                self.cursor = 0
            else:
                return None
        elif key in (3, 4):                  # ctrl-c, ctrl-d
            return None
        elif key in (curses.KEY_BACKSPACE, 127, 8):
            self.query = self.query[:-1]
            self.cursor = 0
        elif 32 <= key < 127 and self.filterable:
            self.query += chr(key)
            self.cursor = 0
        return False


def _wrap(text: str, width: int, lines: int) -> list[str]:
    words, out, current = text.split(), [], ""
    for word in words:
        if len(current) + len(word) + 1 > width:
            out.append(current)
            current = word
            if len(out) == lines:
                return out
        else:
            current = f"{current} {word}".strip()
    if current and len(out) < lines:
        out.append(current)
    return out


def view(lines: Sequence[str], title: str = "") -> None:
    """A read-only screen for a report.

    Reports used to be printed and followed by an "press enter" prompt, which
    left the previous screen's output on the terminal and made every action
    exit differently from the inbox. One rule everywhere instead: esc goes
    back, and nothing else is needed to leave.
    """
    rows = list(lines) or ["nothing to show"]
    Picker(rows, [Column("", 200, lambda line: line, flex=True)], title=title,
           search=lambda line: line).run()


@dataclass
class Filter:
    """One control in the filter bar.

    `keep` narrows the rows here; `reload` means the choice has to be fetched
    again — sorting is done by the server, because ordering a page in the
    client silently drops rows the page never contained.
    """
    name: str
    options: Sequence[tuple[str, object]]
    index: int = 0
    keep: Callable[[object, object], bool] | None = None
    reload: Callable[[object], object] | None = None
    #: One line per option, shown while the field is focused. An option whose
    #: meaning is not obvious from its name is one people leave alone.
    hints: dict = field(default_factory=dict)

    @property
    def hint(self) -> str:
        return self.hints.get(self.label, "")

    @property
    def value(self):
        return self.options[self.index][1]

    @property
    def label(self) -> str:
        return self.options[self.index][0]

    def keeps(self, row) -> bool:
        return True if self.keep is None else self.keep(row, self.value)

    def summary(self) -> str:
        """Shown in the title only when it is not the default."""
        return "" if self.index == 0 else f"{self.name}: {self.label}"

    def segments(self, focused: bool) -> list[tuple[str, str]]:
        """The control in pieces, each saying what it is: the field's name,
        then its options with the current one marked.

        Brackets as well as colour. A terminal with no colours, or a reader who
        cannot tell two of them apart, still has to see which value is on.
        """
        out = [("▸" if focused else " ", "mark"), (f"{self.name} ", "name")]
        for i, (label, _) in enumerate(self.options):
            if i == self.index:
                out.append((f"[{label}]", "focus" if focused else "current"))
            else:
                out.append((f" {label} ", "option"))
        return out

    def render(self, focused: bool) -> str:
        """The same bar as plain text, so the two cannot drift apart."""
        return "".join(text for text, _ in self.segments(focused))


@dataclass
class Act:
    """One thing you can do from a detail screen.

    `confirm` turns the action bar into a yes/no question instead of opening
    another screen: the thing being decided about stays visible while you
    decide.

    `closes` ends the screen after the action ran. An action that removes the
    record it was invoked from has nothing left to show.
    """
    key: str
    label: str
    run: Callable[[], str]
    confirm: str | None = None
    closes: bool = False


class Detail:
    """One record in full, with what you can do to it along the bottom.

    A list answers "which one"; this answers "is it worth it", which needs the
    whole text rather than a truncated column. Letters are actions here
    because there is nothing to filter.
    """

    def __init__(self, title: str, lines: Sequence,
                 actions: Sequence[Act] = (), subtitle: str = ""):
        self.title = title
        self.subtitle = subtitle
        self.lines = list(lines)
        self.actions = list(actions)
        self.top = 0
        self.message = ""
        self.pending: Act | None = None

    def run(self) -> None:
        curses.wrapper(self._loop)

    def _loop(self, screen):
        curses.curs_set(0)
        start_colours()
        while True:
            self._draw(screen)
            if self._key(Picker.read_key(screen)) is None:
                return

    def rows(self, width: int) -> list[list[tuple[str, str]]]:
        """The body as lines of (text, role) pieces.

        A plain string is prose and gets wrapped to the screen. A line already
        in pieces is laid out — a label and its value, one under the next — and
        is passed through untouched. Wrapping ran over both before, and since
        it rejoins on single spaces it quietly turned `fit         8.0/10` into
        `fit 8.0/10`: every field on the vacancy screen lost its column.
        """
        out = []
        for line in self.lines:
            if isinstance(line, str):
                out += [[(chunk, "cell")] for chunk in (_fold(line, width) or [""])]
            else:
                out.append(list(line))
        return out

    def _draw(self, screen):
        screen.erase()
        height, width = screen.getmaxyx()
        body = max(1, height - 5)
        rows = self.rows(width - 4)
        self.top = max(0, min(self.top, max(0, len(rows) - body)))

        screen.addnstr(0, 0, self.title[: width - 1], width - 1, style("name"))
        if self.subtitle:
            screen.addnstr(1, 0, "  " + self.subtitle, width - 1, style("keys"))
        for i, line in enumerate(rows[self.top:self.top + body]):
            x = 2
            for text, role in line:
                if (room := width - 1 - x) <= 0:
                    break
                screen.addnstr(2 + i, x, text[:room], room, style(role))
                x += len(text)

        if len(rows) > body:
            pos = f"{self.top + 1}-{min(self.top + body, len(rows))} of {len(rows)}"
            screen.addnstr(height - 3, 2, pos, width - 3, style("keys"))
        if self.message:
            screen.addnstr(height - 2, 2, self.message[: width - 3], width - 3,
                           style("hint"))

        if self.pending:
            bar = f"  {self.pending.confirm}   [y] yes   [n] no"
            screen.addnstr(height - 1, 0, bar.ljust(width - 1)[: width - 1],
                           width - 1, style("selected"))
        else:
            # The keys are what someone is looking for on this bar, so they are
            # the part that is coloured; the words are what the key means.
            bar = [("  ↑↓ scroll", "keys")]
            for a in self.actions:
                bar += [(f"   [{a.key}]", "current"), (f" {a.label}", "keys")]
            bar.append(("   esc back", "keys"))
            x = 0
            screen.addnstr(height - 1, 0, " " * (width - 1), width - 1,
                           curses.A_NORMAL)
            for text, role in bar:
                if (room := width - 1 - x) <= 0:
                    break
                screen.addnstr(height - 1, x, text[:room], room, style(role))
                x += len(text)
        screen.refresh()

    def _key(self, key):
        """None ends the screen; anything else keeps it open."""
        height = 20
        if self.pending:
            if key in (ord("y"), ord("Y")):
                action, self.pending = self.pending, None
                self.message = action.run() or ""
                if action.closes:
                    return None
            elif key in (ord("n"), ord("N"), 27):
                self.pending = None
                self.message = "cancelled"
            return True

        if key == curses.KEY_DOWN:
            self.top += 1
        elif key == curses.KEY_UP:
            self.top = max(0, self.top - 1)
        elif key == curses.KEY_NPAGE:
            self.top += height
        elif key == curses.KEY_PPAGE:
            self.top = max(0, self.top - height)
        elif key in (27, 3, 4):
            return None
        else:
            for action in self.actions:
                if key == ord(action.key):
                    if action.confirm:
                        self.pending = action
                        self.message = ""
                    else:
                        self.message = action.run() or ""
                        if action.closes:
                            return None
                    break
        return True


def _fold(text: str, width: int) -> list[str]:
    """Wrap one line to the screen, keeping blank lines as separators."""
    if not text.strip():
        return [""]
    out, line = [], ""
    for word in text.split():
        if len(line) + len(word) + 1 > width:
            out.append(line)
            line = word
        else:
            line = f"{line} {word}".strip()
    if line:
        out.append(line)
    return out
