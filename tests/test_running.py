"""A tailoring that outlives the keystroke that started it.

These cover the bookkeeping, not the agent: what is running, what was, and
what happens to a marker whose process died without tidying up.
"""
from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from hub import running


def marker(folder, pid=None, started=None):
    (folder / running.MARKER).write_text(json.dumps({
        "pid": os.getpid() if pid is None else pid,
        "started": (started or datetime.now()).isoformat()}))


class TestWhatIsRunning:
    def test_nothing_is_running_in_a_fresh_folder(self, tmp_path):
        assert running.current(tmp_path) is None

    def test_a_live_marker_is_a_run(self, tmp_path):
        marker(tmp_path)
        assert running.current(tmp_path).pid == os.getpid()

    def test_the_age_is_how_long_it_has_been_going(self, tmp_path):
        marker(tmp_path, started=datetime.now() - timedelta(seconds=90))
        assert 89 <= running.current(tmp_path).age.total_seconds() <= 95


class TestReaping:
    """The child cannot tidy up after itself — a process that crashed is
    exactly the one that will not have — so whoever asks does it."""

    def test_a_dead_process_is_not_running(self, tmp_path):
        marker(tmp_path, pid=999_999)
        assert running.current(tmp_path) is None

    def test_and_its_marker_is_gone(self, tmp_path):
        """Otherwise the folder reads `tailoring…` for ever."""
        marker(tmp_path, pid=999_999)
        running.current(tmp_path)
        assert not (tmp_path / running.MARKER).exists()

    def test_an_old_marker_is_dead_however_alive_its_pid_looks(self, tmp_path):
        """A pid gets recycled onto some unrelated process, and `alive` would
        then say yes for as long as that process lived."""
        marker(tmp_path, started=datetime.now() - running.STALE - timedelta(minutes=1))
        assert running.current(tmp_path) is None

    def test_an_unreadable_marker_is_cleared_rather_than_believed(self, tmp_path):
        (tmp_path / running.MARKER).write_text("{ not json")
        assert running.current(tmp_path) is None
        assert not (tmp_path / running.MARKER).exists()

    @pytest.mark.parametrize("body", ['{}', '{"pid": "x", "started": "y"}',
                                      '{"pid": 1}', 'null'])
    def test_a_marker_missing_what_it_needs_is_the_same_as_none(
            self, tmp_path, body):
        (tmp_path / running.MARKER).write_text(body)
        assert running.current(tmp_path) is None


class TestAlive:
    def test_this_process_is(self):
        assert running.alive(os.getpid())

    def test_one_that_never_existed_is_not(self):
        assert not running.alive(999_999)

    def test_a_nonsense_pid_is_not_a_crash(self):
        """It comes out of a file anyone could have edited. A negative pid
        signals a whole process group, which is not a question worth asking
        and definitely not one worth raising over."""
        assert not running.alive(-12345)
        assert not running.alive(2 ** 70)


class TestStarting:
    def spawned(self, monkeypatch, stdout="4242\n", stderr=""):
        seen = {}

        def run(argv, **kw):
            seen["argv"], seen["kw"] = argv, kw
            return SimpleNamespace(stdout=stdout, stderr=stderr, returncode=0)
        monkeypatch.setattr(subprocess, "run", run)
        return seen

    def test_it_runs_the_same_command_a_person_would(self, tmp_path,
                                                     monkeypatch):
        """The background job is `jam tailor <app>`, so there is no second
        code path that can behave differently from the one used by hand."""
        seen = self.spawned(monkeypatch)
        running.start(tmp_path, "2026-09-06--northwind--data-engineer", tmp_path)
        script = seen["argv"][-1]
        assert "hub.cli tailor 2026-09-06--northwind--data-engineer" in script
        assert " -u " in script          # so the log reads while it is live

    def test_the_worker_is_orphaned_rather_than_left_as_a_child(
            self, tmp_path, monkeypatch):
        """The bug this exists for: a detached child still becomes a zombie
        when it exits, and a zombie answers `os.kill(pid, 0)` — so a run that
        finished in a second read `tailoring…` until the marker went stale.
        Backgrounding it inside a shell that then exits reparents it onto
        init, and the pid stops existing the moment it does."""
        seen = self.spawned(monkeypatch)
        running.start(tmp_path, "app", tmp_path)
        script = seen["argv"][-1]
        assert script.rstrip().endswith("& echo $!")

    def test_it_survives_the_screen_that_started_it(self, tmp_path, monkeypatch):
        """Quitting the screen, or ctrl-c in it, must not kill an agent
        halfway through writing a CV."""
        seen = self.spawned(monkeypatch)
        running.start(tmp_path, "app", tmp_path)
        assert seen["kw"]["start_new_session"] is True
        assert seen["kw"]["stdin"] is subprocess.DEVNULL

    def test_the_marker_names_the_process_it_started(self, tmp_path,
                                                     monkeypatch):
        self.spawned(monkeypatch)
        run = running.start(tmp_path, "app", tmp_path)
        written = json.loads((tmp_path / running.MARKER).read_text())
        assert run.pid == 4242 and written["pid"] == 4242

    def test_an_app_id_cannot_smuggle_shell_into_the_command(
            self, tmp_path, monkeypatch):
        """It is a folder name, but it reaches a shell, and a folder name is
        not a promise about what is in it."""
        seen = self.spawned(monkeypatch)
        running.start(tmp_path, "app; rm -rf /", tmp_path)
        assert "; rm -rf /" not in seen["argv"][-1].replace("'app; rm -rf /'", "")

    def test_a_shell_that_says_nothing_is_an_error_not_a_run(
            self, tmp_path, monkeypatch):
        """A marker with a nonsense pid is a folder stuck at `tailoring…`."""
        self.spawned(monkeypatch, stdout="", stderr="sh: not found")
        with pytest.raises(OSError, match="not found"):
            running.start(tmp_path, "app", tmp_path)
        assert not (tmp_path / running.MARKER).exists()

    def test_a_new_run_does_not_inherit_the_last_one_s_log(self, tmp_path,
                                                           monkeypatch):
        (tmp_path / running.LOG).write_text("from the run before\n")
        self.spawned(monkeypatch)
        running.start(tmp_path, "app", tmp_path)
        assert "from the run before" not in (tmp_path / running.LOG).read_text()


class TestTheLog:
    def test_nothing_written_yet_is_no_lines(self, tmp_path):
        assert running.tail(tmp_path) == []

    def test_it_is_the_end_that_is_wanted(self, tmp_path):
        (tmp_path / running.LOG).write_text(
            "".join(f"line {i}\n" for i in range(50)))
        assert running.tail(tmp_path, 3) == ["line 47", "line 48", "line 49"]

    def test_blank_lines_do_not_take_up_the_room(self, tmp_path):
        """The agent's output is spaced out; four lines of it should be four
        things it did."""
        (tmp_path / running.LOG).write_text("a\n\n\nb\n\nc\n")
        assert running.tail(tmp_path, 3) == ["a", "b", "c"]

    def test_it_outlives_the_run(self, tmp_path):
        """The minute after a tailoring fails is exactly when what it was
        doing matters, and by then the process is gone."""
        marker(tmp_path, pid=999_999)
        (tmp_path / running.LOG).write_text("Bash latexmk\n")
        running.current(tmp_path)                # reaps the marker
        assert running.tail(tmp_path) == ["Bash latexmk"]


class TestHowManyAtOnce:
    """Taking eight vacancies out of the inbox in one sitting is normal, and
    each one is a Claude run and a LaTeX compile. Starting eight is a machine
    nobody can use and a bill nobody chose."""

    def app(self, root, name, pid=None):
        folder = root / name
        folder.mkdir(parents=True, exist_ok=True)
        marker(folder, pid=pid)
        return folder

    def test_nothing_running_is_room(self, tmp_path):
        assert running.room_for_more(tmp_path)

    def test_under_the_limit_is_room(self, tmp_path):
        for i in range(running.LIMIT - 1):
            self.app(tmp_path, f"app{i}")
        assert running.room_for_more(tmp_path)

    def test_at_the_limit_is_not(self, tmp_path):
        for i in range(running.LIMIT):
            self.app(tmp_path, f"app{i}")
        assert not running.room_for_more(tmp_path)

    def test_a_dead_one_does_not_hold_a_place(self, tmp_path):
        """Otherwise three crashed agents block every later tailoring until
        their markers go stale."""
        for i in range(running.LIMIT):
            self.app(tmp_path, f"app{i}", pid=999_990 + i)
        assert running.room_for_more(tmp_path)

    def test_it_lists_what_is_running_oldest_first(self, tmp_path):
        from datetime import timedelta
        for i, name in enumerate(["b", "a"]):
            folder = tmp_path / name
            folder.mkdir()
            marker(folder, started=datetime.now() - timedelta(minutes=10 - i))
        assert [name for name, _ in running.all_running(tmp_path)] == ["b", "a"]

    def test_a_folder_with_no_marker_is_not_counted(self, tmp_path):
        (tmp_path / "quiet").mkdir()
        assert running.all_running(tmp_path) == []
