"""Helpers for sidecar tests: spawn the real sidecar on stdio."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

CORE_ROOT = Path(__file__).resolve().parent.parent


def spawn_sidecar(**popen_kwargs) -> subprocess.Popen:
    """Spawn ``python -m meridian_core`` with piped stdio."""
    env = dict(os.environ)
    env["MERIDIAN_PARENT_PID"] = str(os.getpid())
    env.setdefault("PYTHONUNBUFFERED", "1")
    return subprocess.Popen(
        [sys.executable, "-m", "meridian_core"],
        cwd=CORE_ROOT,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        **popen_kwargs,
    )


def send(proc: subprocess.Popen, message: dict) -> None:
    assert proc.stdin is not None
    proc.stdin.write(json.dumps(message).encode("utf-8") + b"\n")
    proc.stdin.flush()


def recv(proc: subprocess.Popen) -> dict:
    assert proc.stdout is not None
    line = proc.stdout.readline()
    assert line, "sidecar closed stdout without responding"
    return json.loads(line.decode("utf-8"))


def handshake(proc: subprocess.Popen, protocol_version: int = 1) -> dict:
    send(
        proc,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "handshake",
            "params": {"protocolVersion": protocol_version, "client": "pytest"},
        },
    )
    return recv(proc)
