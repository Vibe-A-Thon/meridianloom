"""Shared pytest fixtures for sidecar tests.

The fixture git repo lives next to its builder (test_attribution.py) and is
re-exported here so other test modules (test_symbols, test_heuristics) can
count on a small committed repository without rebuilding it.

**One suite run at a time.** Much of this suite spawns real subprocesses —
`git init`, `git commit`, the Python sidecar over stdio — and two runs on one
machine starve each other badly enough to produce failures that look like
regressions and are not. That has already happened here: a concurrent run
reported 153 failures and 198 errors, every one of which passed when run
alone, and the wreckage was investigated as if it were signal.

The fix is not to remember. A second run now refuses to start, and says why.
"""

from __future__ import annotations

import errno
import os
import sys
import tempfile
from pathlib import Path

import pytest

from test_attribution import ALICE, T0, git

#: One lock for **every** Meridian suite, not one per language.
#:
#: The first version of this guarded pytest against pytest, which was the
#: contention that had already burned a day. It did nothing about the
#: extension's vitest suite, which spawns the same real sidecars and the same
#: real ACP subprocesses — and a Python run measured while that suite ran
#: alongside it produced 11 failures and took twice as long as the same tests
#: had taken unattended. Same mistake, different pair of processes, and the
#: lock watched it happen.
#:
#: So the name is suite-agnostic and `extension/test/run-lock.ts` takes this
#: same file. Whichever starts second waits or refuses.
_LOCK = Path(tempfile.gettempdir()) / "meridian-suite.lock"
_FIXTURE_INPUTS = Path(__file__).resolve().parent / "fixtures"


def _holder_is_alive(pid: int) -> bool:
    """Whether the recorded pid is still running.

    A crashed run leaves its lock behind, and a stale lock that blocks every
    future run would be a worse failure than the one this guards against.

    The platforms genuinely differ here, which is the sort of thing the CI
    matrix exists to catch: on POSIX `os.kill(pid, 0)` raises OSError and the
    errno says which case it is, but on Windows the same call raises
    SystemError for a live process it cannot signal. Windows gets its own
    branch through the Win32 API rather than a broad `except` that would
    silently make the lock a no-op on the platform this was written on.
    """
    if pid <= 0:
        return False
    if sys.platform == "win32":
        import ctypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        handle = kernel32.OpenProcess(
            PROCESS_QUERY_LIMITED_INFORMATION, False, pid
        )
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return False
            return code.value == STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except OSError as error:
        # ESRCH: no such process. EPERM: it exists and is not ours, which on
        # a shared machine still means something holds it.
        return error.errno == errno.EPERM
    return True


def pytest_configure(config: pytest.Config) -> None:
    """Take an exclusive run lock, or refuse with the reason."""
    if os.environ.get("MERIDIAN_ALLOW_CONCURRENT_SUITE") == "1":
        return
    if _is_fixture_input_run(config):
        return
    # xdist workers inherit the parent's lock; only the controller takes one.
    if os.environ.get("PYTEST_XDIST_WORKER"):
        return
    try:
        handle = os.open(str(_LOCK), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        try:
            holder = int(_LOCK.read_text(encoding="utf-8").strip() or 0)
        except (OSError, ValueError):
            holder = 0
        if _holder_is_alive(holder):
            raise pytest.UsageError(
                # ASCII only: this prints to a console, and on Windows the
                # default code page turns an em-dash into a replacement
                # character. A diagnostic that looks corrupted undermines the
                # thing it is trying to tell you.
                f"another Meridian suite run is already going (pid {holder}); "
                "it may be pytest or the extension's vitest suite. "
                "Two runs on one machine spawn competing git and sidecar "
                "subprocesses and starve each other; the failures that produces "
                "are not regressions, and chasing them wastes more time than "
                "waiting did. "
                "If that pid is a parallel build session in this same tree "
                "(BUILD_STATE records the arrangement), wait for it rather "
                "than racing it. Override with "
                "MERIDIAN_ALLOW_CONCURRENT_SUITE=1 only if you genuinely mean "
                "to accept the interference."
            )
        # The holder is gone; the lock is stale. Take it over.
        _LOCK.unlink(missing_ok=True)
        handle = os.open(str(_LOCK), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    os.write(handle, str(os.getpid()).encode("utf-8"))
    os.close(handle)
    config.stash[_lock_taken] = True


def _is_fixture_input_run(config: pytest.Config) -> bool:
    """Fixture corpora are inputs, not independent Meridian suite runs.

    Some capability tests deliberately invoke pytest against a tiny failing
    fixture to prove deterministic failure parsing. That nested process must
    not take the global suite lock held by its parent run.
    """
    args = [
        item.split("::", 1)[0]
        for item in config.args
        if item and not item.startswith("-")
    ]
    if not args:
        return False
    invocation_dir = Path(str(config.invocation_params.dir))
    for arg in args:
        path = Path(arg)
        if not path.is_absolute():
            path = invocation_dir / path
        try:
            path.resolve().relative_to(_FIXTURE_INPUTS)
        except ValueError:
            return False
    return True


_lock_taken = pytest.StashKey[bool]()


def pytest_unconfigure(config: pytest.Config) -> None:
    if config.stash.get(_lock_taken, False):
        _LOCK.unlink(missing_ok=True)


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    git(tmp_path, "init")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.txt").write_text("one\ntwo\nthree\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("hello\n", encoding="utf-8")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-m", "initial", date=T0)
    return tmp_path
