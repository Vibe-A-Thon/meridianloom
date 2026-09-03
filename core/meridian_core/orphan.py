"""Orphan guard (FR-M3-03).

The extension supervisor kills the sidecar on teardown (FR-M3-02), but if the
extension host itself dies — window kill, crash, remote disconnect — nothing
sends that shutdown. This module is the second, mandatory half of the dual
teardown contract: the sidecar monitors its parent and self-terminates
within POLL_INTERVAL_SECONDS of losing it, well inside the 10-second budget.

Two independent triggers:

1. stdin EOF — when the parent dies, its end of the stdin pipe closes and the
   serve loop exits (see server.serve). Covers the common case.
2. Parent-PID polling — covers cases where the pipe outlives the parent
   (e.g. a grandchild inherited the write end). The extension passes its PID
   via MERIDIAN_PARENT_PID; if that process disappears we exit with
   ORPHAN_EXIT_CODE.

Stdlib only. On Windows, parent liveness uses OpenProcess +
GetExitCodeProcess via ctypes; on POSIX, os.kill(pid, 0).
"""

from __future__ import annotations

import ctypes
import logging
import os
import sys
import threading

logger = logging.getLogger("meridian_core.orphan")

POLL_INTERVAL_SECONDS = 2.0
ORPHAN_EXIT_CODE = 3
PARENT_PID_ENV = "MERIDIAN_PARENT_PID"

_STILL_ACTIVE = 259
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


def parent_alive(pid: int) -> bool:
    """True while the process with `pid` exists and has not exited."""
    if sys.platform == "win32":
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        handle = kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False
        try:
            exit_code = ctypes.c_ulong()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                return False
            return exit_code.value == _STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists, owned by someone else
    return True


class ParentDeathMonitor:
    """Daemon thread that calls `on_orphaned` when the parent process dies."""

    def __init__(
        self,
        parent_pid: int,
        on_orphaned: "threading.Event | None" = None,
        poll_interval: float = POLL_INTERVAL_SECONDS,
    ) -> None:
        self._parent_pid = parent_pid
        self._poll_interval = poll_interval
        self.on_orphaned = on_orphaned
        self._thread = threading.Thread(
            target=self._watch, name="parent-death-monitor", daemon=True
        )

    def start(self) -> None:
        self._thread.start()

    def _watch(self) -> None:
        while True:
            if not parent_alive(self._parent_pid):
                logger.critical(
                    "parent process %d is gone; self-terminating (FR-M3-03)",
                    self._parent_pid,
                )
                if self.on_orphaned is not None:
                    self.on_orphaned.set()
                # Hard exit: the serve loop may be blocked in readline() on a
                # pipe that never closes, so a graceful return is not
                # guaranteed. os._exit is the point of this guard.
                os._exit(ORPHAN_EXIT_CODE)
            threading.Event().wait(self._poll_interval)


def monitor_from_environment(on_orphaned: "threading.Event | None" = None) -> ParentDeathMonitor | None:
    """Start a monitor for the parent PID passed via MERIDIAN_PARENT_PID.

    Returns None when the variable is absent (e.g. the sidecar was launched
    by hand for debugging) — the stdin-EOF trigger still applies.
    """
    raw = os.environ.get(PARENT_PID_ENV)
    if not raw:
        logger.warning("%s not set; parent-death monitor disabled", PARENT_PID_ENV)
        return None
    try:
        parent_pid = int(raw)
    except ValueError:
        logger.warning("invalid %s=%r; parent-death monitor disabled", PARENT_PID_ENV, raw)
        return None
    monitor = ParentDeathMonitor(parent_pid, on_orphaned)
    monitor.start()
    logger.debug("watching parent pid %d", parent_pid)
    return monitor
