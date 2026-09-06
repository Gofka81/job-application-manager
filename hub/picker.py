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
from dataclasses import dataclass
from typing import Callable, Sequence


def usable(stream=None) -> bool:
    """Only when a person is actually looking at a terminal."""
    stream = stream or sys.stdout
    return bool(getattr(stream, "isatty", lambda: False)()) and sys.stdin.isatty()


@dataclass
class Column:
    header: str
    width: int
    value: Callable[[object], str]
    right: bool = False
    #: Give this column whatever width is left over. At most one per set.
    flex: bool = False

    def render(self, row: object, width: int | None = None) -> str:
        width = self.width if width is None else width
        text = str(self.value(row))[:width]
        return text.rjust(width) if self.right else text.ljust(width)


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
                 modes: Sequence[tuple[str, Callable[[object], bool]]] | None = None,
                 deep: Callable[[str], Sequence] | None = None,
                 deep_label: str = "deep search",
                 filterable: bool = True,
                 keys: dict[int, tuple[str, Callable[["Picker"], str]]] | None = None):
        self.all = list(rows)
        # Cycled with left/right. A filter the caller wants reachable without
        # leaving the screen and rerunning the command with a flag.
        self.modes = list(modes or [])
        self.mode = 0
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
        self.message = ""
        self.columns = list(columns)
        self.title = title
        self.search = search or (lambda r: str(r))
        self.detail = detail
        self.query = ""
        self.cursor = 0
        self.top = 0

    @property
    def mode_label(self) -> str:
        return self.modes[self.mode][0] if self.modes else ""

    @property
    def searching(self) -> bool:
        return bool(self.deep_query)

    @property
    def rows(self) -> list:
        rows = self.all
        if self.modes:
            rows = [r for r in rows if self.modes[self.mode][1](r)]
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
        if curses.has_colors():
            curses.use_default_colors()
            curses.init_pair(1, curses.COLOR_BLACK, curses.COLOR_CYAN)
            curses.init_pair(2, curses.COLOR_CYAN, -1)
            curses.init_pair(3, curses.COLOR_YELLOW, -1)
        while True:
            self._draw(screen)
            result = self._key(self.read_key(screen))
            if result is not False:
                return result

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
        # Two lines of chrome at the top, two at the bottom.
        body = max(1, height - 5 - (3 if self.detail else 0))
        self.cursor = max(0, min(self.cursor, len(rows) - 1)) if rows else 0
        self.top = max(min(self.top, self.cursor), self.cursor - body + 1, 0)

        layout = fit(self.columns, width - 3)
        head = f"{self.title}   {len(rows)} of {len(self.all)}"
        if self.searching:
            head += f"   {self.deep_label}: {self.deep_query}"
        if self.modes:
            head += f"   [{self.mode_label}]"
        if self.query:
            head += f"   /{self.query}"
        screen.addnstr(0, 0, head, width - 1, curses.color_pair(2) | curses.A_BOLD)

        header = "  " + " ".join(c.header.ljust(w)[:w] for c, w in layout)
        screen.addnstr(1, 0, header, width - 1, curses.A_DIM)

        for i, row in enumerate(rows[self.top:self.top + body]):
            line = "  " + " ".join(c.render(row, w) for c, w in layout)
            selected = self.top + i == self.cursor
            screen.addnstr(2 + i, 0, line.ljust(width - 1)[: width - 1],
                           width - 1,
                           curses.color_pair(1) if selected else curses.A_NORMAL)

        if self.message:
            screen.addnstr(height - 2, 2, self.message[: width - 3], width - 3,
                           curses.color_pair(3) | curses.A_BOLD)
        elif self.detail and rows:
            text = self.detail(rows[self.cursor]) or ""
            for j, chunk in enumerate(_wrap(text, width - 3, 2)):
                screen.addnstr(2 + body + j, 2, chunk, width - 3,
                               curses.color_pair(3))

        hint = "  ↑↓ move   enter choose"
        if self.filterable:
            hint += "   type to filter"
        if self.deep:
            hint += f"   tab {self.deep_label}"
        for label, _ in self.keys.values():
            hint += f"   {label}"
        if self.modes:
            hint += "   ←→ " + "/".join(label for label, _ in self.modes)
        hint += "   esc back"
        screen.addnstr(height - 1, 0, hint[: width - 1], width - 1, curses.A_DIM)
        screen.refresh()

    # --- input ---------------------------------------------------------

    def _key(self, key):
        """False keeps looping; anything else is the result.

        There are no letter shortcuts. Typing filters, and a picker that also
        bound j/k/g/q swallowed those letters before they reached the filter —
        so a company with a `g` in it could not be searched for at all.
        """
        rows = self.rows
        if key == curses.KEY_DOWN:
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
        elif key in (curses.KEY_RIGHT, curses.KEY_LEFT) and self.modes:
            step = 1 if key == curses.KEY_RIGHT else -1
            self.mode = (self.mode + step) % len(self.modes)
            self.cursor = 0
        elif key in (10, 13, curses.KEY_ENTER):
            return rows[self.cursor] if rows else None
        elif key in self.keys:
            self.message = self.keys[key][1](self) or ""
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
class Act:
    """One thing you can do from a detail screen.

    `confirm` turns the action bar into a yes/no question instead of opening
    another screen: the thing being decided about stays visible while you
    decide.
    """
    key: str
    label: str
    run: Callable[[], str]
    confirm: str | None = None


class Detail:
    """One record in full, with what you can do to it along the bottom.

    A list answers "which one"; this answers "is it worth it", which needs the
    whole text rather than a truncated column. Letters are actions here
    because there is nothing to filter.
    """

    def __init__(self, title: str, lines: Sequence[str],
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
        if curses.has_colors():
            curses.use_default_colors()
            curses.init_pair(1, curses.COLOR_BLACK, curses.COLOR_CYAN)
            curses.init_pair(2, curses.COLOR_CYAN, -1)
            curses.init_pair(3, curses.COLOR_YELLOW, -1)
        while True:
            self._draw(screen)
            if self._key(Picker.read_key(screen)) is None:
                return

    def _draw(self, screen):
        screen.erase()
        height, width = screen.getmaxyx()
        body = max(1, height - 5)
        wrapped = []
        for line in self.lines:
            wrapped += _fold(line, width - 4) or [""]
        self.top = max(0, min(self.top, max(0, len(wrapped) - body)))

        screen.addnstr(0, 0, self.title[: width - 1], width - 1,
                       curses.color_pair(2) | curses.A_BOLD)
        if self.subtitle:
            screen.addnstr(1, 0, "  " + self.subtitle, width - 1, curses.A_DIM)
        for i, line in enumerate(wrapped[self.top:self.top + body]):
            screen.addnstr(2 + i, 2, line, width - 3)

        if len(wrapped) > body:
            pos = f"{self.top + 1}-{min(self.top + body, len(wrapped))} of {len(wrapped)}"
            screen.addnstr(height - 3, 2, pos, width - 3, curses.A_DIM)
        if self.message:
            screen.addnstr(height - 2, 2, self.message[: width - 3], width - 3,
                           curses.color_pair(3))

        if self.pending:
            bar = f"  {self.pending.confirm}   [y] yes   [n] no"
            style = curses.color_pair(1)
        else:
            bar = "  ↑↓ scroll" + "".join(
                f"   [{a.key}] {a.label}" for a in self.actions) + "   esc back"
            style = curses.A_DIM
        screen.addnstr(height - 1, 0, bar.ljust(width - 1)[: width - 1],
                       width - 1, style)
        screen.refresh()

    def _key(self, key):
        """None ends the screen; anything else keeps it open."""
        height = 20
        if self.pending:
            if key in (ord("y"), ord("Y")):
                action, self.pending = self.pending, None
                self.message = action.run() or ""
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
