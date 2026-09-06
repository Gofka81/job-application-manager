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

    def render(self, row: object) -> str:
        text = str(self.value(row))[: self.width]
        return text.rjust(self.width) if self.right else text.ljust(self.width)


class Picker:
    def __init__(self, rows: Sequence, columns: Sequence[Column],
                 title: str = "", search: Callable[[object], str] | None = None,
                 detail: Callable[[object], str] | None = None):
        self.all = list(rows)
        self.columns = list(columns)
        self.title = title
        self.search = search or (lambda r: str(r))
        self.detail = detail
        self.query = ""
        self.cursor = 0
        self.top = 0

    @property
    def rows(self) -> list:
        if not self.query:
            return self.all
        q = self.query.lower()
        return [r for r in self.all if q in self.search(r).lower()]

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

    def _draw(self, screen):
        screen.erase()
        height, width = screen.getmaxyx()
        rows = self.rows
        # Two lines of chrome at the top, two at the bottom.
        body = max(1, height - 5 - (3 if self.detail else 0))
        self.cursor = max(0, min(self.cursor, len(rows) - 1)) if rows else 0
        self.top = max(min(self.top, self.cursor), self.cursor - body + 1, 0)

        head = f"{self.title}   {len(rows)} of {len(self.all)}"
        if self.query:
            head += f"   /{self.query}"
        screen.addnstr(0, 0, head, width - 1, curses.color_pair(2) | curses.A_BOLD)

        header = "  " + " ".join(c.header.ljust(c.width)[:c.width] for c in self.columns)
        screen.addnstr(1, 0, header, width - 1, curses.A_DIM)

        for i, row in enumerate(rows[self.top:self.top + body]):
            line = "  " + " ".join(c.render(row) for c in self.columns)
            selected = self.top + i == self.cursor
            screen.addnstr(2 + i, 0, line.ljust(width - 1)[: width - 1],
                           width - 1,
                           curses.color_pair(1) if selected else curses.A_NORMAL)

        if self.detail and rows:
            text = self.detail(rows[self.cursor]) or ""
            for j, chunk in enumerate(_wrap(text, width - 3, 2)):
                screen.addnstr(2 + body + j, 2, chunk, width - 3,
                               curses.color_pair(3))

        hint = "  ↑↓ move   enter choose   / filter   esc clear   q quit"
        screen.addnstr(height - 1, 0, hint[: width - 1], width - 1, curses.A_DIM)
        screen.refresh()

    # --- input ---------------------------------------------------------

    def _key(self, key):
        """False keeps looping; anything else is the result."""
        rows = self.rows
        if key in (curses.KEY_DOWN, ord("j")):
            self.cursor += 1
        elif key in (curses.KEY_UP, ord("k")):
            self.cursor = max(0, self.cursor - 1)
        elif key == curses.KEY_NPAGE:
            self.cursor += 10
        elif key == curses.KEY_PPAGE:
            self.cursor = max(0, self.cursor - 10)
        elif key in (curses.KEY_HOME, ord("g")):
            self.cursor = 0
        elif key in (curses.KEY_END, ord("G")):
            self.cursor = len(rows) - 1
        elif key in (10, 13, curses.KEY_ENTER):
            return rows[self.cursor] if rows else None
        elif key == ord("/"):
            self.query = ""
        elif key == 27:                      # esc clears the filter
            self.query = ""
        elif key in (ord("q"),):
            return None
        elif key in (curses.KEY_BACKSPACE, 127, 8):
            self.query = self.query[:-1]
        elif 32 <= key < 127:
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
