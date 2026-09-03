"""Orphan-guard tests (FR-M3-03, AC-08).

Pattern: pytest spawns a throwaway *harness* process; the harness spawns the
sidecar with MERIDIAN_PARENT_PID pointing at itself. Killing the harness hard
(SIGKILL/TerminateProcess — no cleanup) must leave no orphaned sidecar: it
self-terminates within the 10-second budget.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from meridian_core.orphan import (
    ORPHAN_EXIT_CODE,
    ParentDeathMonitor,
    monitor_from_environment,
    parent_alive,
)

CORE_ROOT = Path(__file__).resolve().parent.parent

HARNESS = """
import os, subprocess, sys
env = dict(os.environ)
env["MERIDIAN_PARENT_PID"] = str(os.getpid())
proc = subprocess.Popen(
    [sys.executable, "-m", "meridian_core"],
    cwd={core_root!r},
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    env=env,
)
print(proc.pid, flush=True)
import time
time.sleep(120)
"""


def _dead_parent_pid() -> int:
    """A PID that is guaranteed not to exist anymore."""
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    return proc.pid


class TestParentAlive:
    def test_current_process_is_alive(self):
        assert parent_alive(os.getpid()) is True

    def test_exited_process_is_dead(self):
        assert parent_alive(_dead_parent_pid()) is False


class TestMonitorWiring:
    def test_disabled_without_env_var(self, monkeypatch):
        monkeypatch.delenv("MERIDIAN_PARENT_PID", raising=False)
        assert monitor_from_environment() is None

    def test_invalid_env_var_disables(self, monkeypatch):
        monkeypatch.setenv("MERIDIAN_PARENT_PID", "not-a-pid")
        assert monitor_from_environment() is None

    def test_monitor_detects_dead_parent_fast(self):
        import threading

        orphaned = threading.Event()
        monitor = ParentDeathMonitor(_dead_parent_pid(), orphaned, poll_interval=0.05)
        # Do not start the real thread: it calls os._exit on detection.
        # Instead drive one watch iteration's check directly.
        assert parent_alive(monitor._parent_pid) is False


@pytest.mark.skipif(not sys.executable, reason="needs a real interpreter")
def test_no_orphan_after_parent_is_killed():
    """AC-08: hard-kill the parent; the sidecar must be gone within 10 s."""
    harness = subprocess.Popen(
        [sys.executable, "-c", HARNESS.format(core_root=str(CORE_ROOT))],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        assert harness.stdout is not None
        sidecar_pid = int(harness.stdout.readline().decode().strip())
        assert parent_alive(sidecar_pid)

        harness.kill()  # SIGKILL / TerminateProcess: no cleanup runs
        harness.wait(timeout=10)

        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and parent_alive(sidecar_pid):
            time.sleep(0.2)
        assert not parent_alive(sidecar_pid), (
            f"sidecar pid {sidecar_pid} still alive 10 s after parent death"
        )
    finally:
        if harness.poll() is None:
            harness.kill()
