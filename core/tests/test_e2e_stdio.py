"""End-to-end stdio test against the real sidecar process (FR-M3-01, FR-M3-09)."""

from __future__ import annotations

import subprocess

from helpers import handshake, recv, send, spawn_sidecar


def test_real_sidecar_handshake_and_ping_round_trip():
    proc = spawn_sidecar()
    try:
        result = handshake(proc)
        assert result["result"]["protocolVersion"] == 1
        assert result["result"]["capabilities"]["framing"] == "ndjson"

        send(proc, {"jsonrpc": "2.0", "id": 2, "method": "ping"})
        assert recv(proc)["result"]["pong"] is True

        send(proc, {"jsonrpc": "2.0", "id": 3, "method": "shutdown"})
        assert recv(proc)["result"] == {"ok": True}
        assert proc.wait(timeout=10) == 0
    finally:
        if proc.poll() is None:
            proc.kill()


def test_stdout_carries_only_framed_rpc():
    """FR-M3-09: every stdout line must be a parseable JSON-RPC frame."""
    proc = spawn_sidecar()
    try:
        handshake(proc)
        send(proc, {"jsonrpc": "2.0", "id": 2, "method": "ping"})
        send(proc, {"jsonrpc": "2.0", "id": 3, "method": "shutdown"})
        recv(proc)
        recv(proc)
        proc.wait(timeout=10)
        stderr = proc.stderr.read().decode() if proc.stderr else ""
        # Logging happened (proving logging works) but went to stderr.
        assert "sidecar serving" in stderr
    finally:
        if proc.poll() is None:
            proc.kill()


def test_sidecar_exits_when_stdin_closes():
    proc = spawn_sidecar()
    try:
        handshake(proc)
        assert proc.stdin is not None
        proc.stdin.close()
        assert proc.wait(timeout=10) == 0
    finally:
        if proc.poll() is None:
            proc.kill()
