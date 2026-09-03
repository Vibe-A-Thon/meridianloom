"""FR-M3-10: the sidecar binds no network listener by default.

Asserts from outside the process: spawn the real sidecar, then enumerate the
OS's listening sockets and prove none belongs to the sidecar's PID. (The
debug HTTP/WS transport the requirement allows does not exist yet; when it
lands, it gets its own loopback+token tests.)
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import time

import pytest

from helpers import handshake, spawn_sidecar


def _listening_pids_windows() -> set[int]:
    out = subprocess.run(
        ["netstat", "-ano"], capture_output=True, text=True, timeout=30
    ).stdout
    pids: set[int] = set()
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 5 and parts[0].startswith("TCP") and parts[3] == "LISTENING":
            pids.add(int(parts[4]))
    return pids


def _socket_inodes(pid: int) -> set[str]:
    fd_dir = f"/proc/{pid}/fd"
    inodes: set[str] = set()
    for fd in os.listdir(fd_dir):
        try:
            target = os.readlink(os.path.join(fd_dir, fd))
        except OSError:
            continue
        match = re.fullmatch(r"socket:\[(\d+)\]", target)
        if match:
            inodes.add(match.group(1))
    return inodes


def _listening_inodes_linux() -> set[str]:
    inodes: set[str] = set()
    for table in ("/proc/net/tcp", "/proc/net/tcp6"):
        try:
            with open(table) as handle:
                lines = handle.readlines()[1:]
        except OSError:
            continue
        for line in lines:
            parts = line.split()
            # parts[3] is the connection state; 0A == LISTEN.
            if len(parts) > 9 and parts[3] == "0A":
                inodes.add(parts[9])
    return inodes


def _listening_pids_macos(pid: int) -> bool:
    out = subprocess.run(
        ["lsof", "-a", "-p", str(pid), "-i", "-sTCP:LISTEN"],
        capture_output=True,
        text=True,
        timeout=30,
    ).stdout
    return any("LISTEN" in line for line in out.splitlines())


def assert_no_listener(pid: int) -> None:
    if sys.platform == "win32":
        assert pid not in _listening_pids_windows(), (
            f"sidecar pid {pid} owns a LISTENING socket"
        )
    elif sys.platform == "darwin":
        assert not _listening_pids_macos(pid)
    else:
        owned = _socket_inodes(pid)
        listeners = _listening_inodes_linux()
        assert not (owned & listeners), (
            f"sidecar pid {pid} owns listening socket inode(s): {owned & listeners}"
        )


def test_sidecar_binds_no_listener_by_default():
    proc = spawn_sidecar()
    try:
        handshake(proc)
        assert proc.pid is not None
        # Give the OS a beat to settle, then check twice.
        for _ in range(2):
            assert_no_listener(proc.pid)
            time.sleep(0.2)
    finally:
        if proc.poll() is None:
            proc.kill()
