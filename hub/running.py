"""A tailoring that outlives the keystroke that started it.

Writing a CV takes minutes. Doing it in the foreground meant the screen went
away for the whole of it, so the one thing you could not do while an
application was being tailored was look at any of the others — and the reason
to be on that screen at all is usually comparing them.

So the work is started and let go of. What survives the keystroke is two
files in the application folder:

    .tailoring   pid and start time, deleted once the process is gone
    .tailor.log  everything it printed, kept afterwards

Nothing here talks to the agent. The background job is `jam tailor <app_id>`
run unbuffered with its output redirected — the same command anyone would
type, so there is no second code path that can behave differently from the
one that is used by hand.

The marker is reaped by whoever asks rather than by the child: a process that
crashed cannot tidy up after itself, and a folder that stays `tailoring…`
forever because of it is the failure this has to not have.
"""
from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

MARKER = ".tailoring"
LOG = ".tailor.log"

# Longer than the agent's own timeout, so a run that is simply slow is never
# called dead. This is the backstop for a pid that was recycled onto another
# process — `alive` would say yes forever, and a folder cannot be stuck.
STALE = timedelta(minutes=30)


@dataclass
class Run:
    pid: int
    started: datetime

    @property
    def age(self) -> timedelta:
        return datetime.now() - self.started


def alive(pid: int) -> bool:
    """Whether the process is still there.

    Signal 0 asks the kernel without sending anything. A permission error
    means it exists and belongs to somebody else, which is still alive.
    """
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except (OSError, OverflowError, ValueError):
        return False
    return True


def current(folder: Path) -> Run | None:
    """The tailoring running in this folder, if there is one.

    Reaps as it reads: a marker whose process is gone is deleted here, so the
    stage a screen shows is worked out from what is actually running rather
    than from what was once started.
    """
    path = folder / MARKER
    try:
        data = json.loads(path.read_text())
        run = Run(int(data["pid"]), datetime.fromisoformat(data["started"]))
    except FileNotFoundError:
        return None
    except (OSError, ValueError, KeyError, TypeError):
        _forget(path)
        return None
    if run.age > STALE or not alive(run.pid):
        _forget(path)
        return None
    return run


def _forget(path: Path) -> None:
    try:
        path.unlink()
    except OSError:
        pass


def start(folder: Path, app_id: str, cwd: Path) -> Run:
    """Start `jam tailor` in the background and return once it is running.

    Started through a shell that backgrounds it and exits, so the agent ends
    up orphaned onto init rather than left as a child of the screen. A child
    that is merely detached still becomes a zombie when it exits, and a zombie
    answers `os.kill(pid, 0)` — so a run that finished in a second would have
    read `tailoring…` until the marker went stale.

    `start_new_session` puts it outside this terminal's process group as well:
    ctrl-c in the screen must not kill an agent halfway through a CV.
    """
    log = folder / LOG
    log.write_text("")
    # -u so the log is readable while it is still being written; the point of
    # keeping it is watching a run that has not finished.
    inner = " ".join(shlex.quote(part) for part in
                     [sys.executable, "-u", "-m", "hub.cli", "tailor", app_id])
    proc = subprocess.run(
        ["/bin/sh", "-c", f"{inner} >{shlex.quote(str(log))} 2>&1 & echo $!"],
        cwd=str(cwd), stdin=subprocess.DEVNULL, capture_output=True,
        text=True, start_new_session=True)
    try:
        pid = int(proc.stdout.strip())
    except ValueError as exc:
        raise OSError(f"could not start the tailoring: {proc.stderr}") from exc
    run = Run(pid, datetime.now())
    (folder / MARKER).write_text(json.dumps(
        {"pid": run.pid, "started": run.started.isoformat()}) + "\n")
    return run


# How many agents may be writing CVs at once. Taking eight vacancies out of
# the inbox in one sitting is normal, and each one is a Claude run and a
# LaTeX compile; starting eight is a machine nobody can use and a bill nobody
# chose. The rest are not lost — they are folders with no CV yet, which is a
# stage the screens already know how to show and one key already fixes.
LIMIT = 3


def all_running(root: Path) -> list[tuple[str, Run]]:
    """Every tailoring under way, newest last. Reaps as it goes."""
    out = []
    for path in sorted(root.glob(f"*/{MARKER}")):
        run = current(path.parent)
        if run:
            out.append((path.parent.name, run))
    return sorted(out, key=lambda pair: pair[1].started)


def room_for_more(root: Path) -> bool:
    return len(all_running(root)) < LIMIT


def tail(folder: Path, lines: int = 10) -> list[str]:
    """The last few lines it printed, newest last.

    Kept after the run ends rather than deleted with the marker: what the
    agent did is the only account of why a folder ended up as it did, and it
    is wanted most in the minute after it finished badly.
    """
    try:
        text = (folder / LOG).read_text()
    except (OSError, ValueError):
        return []
    return [line for line in text.splitlines() if line.strip()][-lines:]
