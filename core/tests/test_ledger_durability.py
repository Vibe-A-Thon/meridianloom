"""FR-M10-08 synchronous write semantics, proven against a hard kill.

The contract: an append acknowledged over RPC must be durable. The test
spawns the real sidecar, appends (with an encrypted blob payload), reads
the ack, then kills the process with no grace (proc.kill() is
TerminateProcess on Windows — the moral equivalent of kill -9; no
atexit, no WAL checkpoint, no shutdown handler runs). A fresh sidecar on
the same workspace must see the entry and its blob, and the chain must
continue from it.
"""

from __future__ import annotations

import base64

from helpers import recv, send, spawn_sidecar

from meridian_core import protocol

SEED = bytes(range(32))


def _spawn_and_handshake(workspace) -> object:
    proc = spawn_sidecar()
    send(
        proc,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "handshake",
            "params": {
                "protocolVersion": protocol.PROTOCOL_VERSION,
                "client": "pytest",
                "workspaceDir": str(workspace),
                "ledgerSigningKey": base64.b64encode(SEED).decode(),
            },
        },
    )
    response = recv(proc)
    assert "error" not in response, response
    return proc


def _request(proc, request_id: int, method: str, params: dict) -> dict:
    send(proc, {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
    response = recv(proc)
    assert response["id"] == request_id
    return response


def _append_params(seq: int) -> dict:
    return {
        "storyId": "EDB-12345",
        "phase": "build",
        "loopId": "L2-task",
        "loopIteration": 1,
        "actorId": "developer-agent",
        "actorVersion": "0.0.1",
        "actorKind": "role",
        "policyVersion": "policy-v1",
        "actionType": "diff",
        "input": f"prompt for step {seq}: use key AKIAIOSFODNN7EXAMPLE",
        "output": f"step {seq} complete",
        "blobSubject": "story:EDB-12345",
        "timestamp": "2026-09-01T00:00:00.000001Z",
    }


def test_acked_append_survives_kill_minus_9(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    proc = _spawn_and_handshake(workspace)
    response = _request(proc, 2, "ledger.append", _append_params(1))
    assert "error" not in response, response
    assert response["result"]["sequence"] == 1
    acked_hash = response["result"]["hash"]

    # Hard kill with zero grace: everything the ack promised must already
    # be on disk (WAL + synchronous=FULL; blob fsync'd before commit).
    proc.kill()
    proc.wait(timeout=10)

    # Fresh sidecar, same workspace: the entry must be there, the chain
    # must continue from it, and the payload must decrypt.
    proc = _spawn_and_handshake(workspace)
    try:
        response = _request(proc, 2, "ledger.append", _append_params(2))
        assert "error" not in response, response
        assert response["result"]["sequence"] == 2
        assert response["result"]["previousHash"] == acked_hash

        response = _request(proc, 3, "ledger.query", {"fromSequence": 1})
        entries = response["result"]["entries"]
        assert [e["sequence"] for e in entries] == [1, 2]
        assert entries[0]["entryHash"] == acked_hash
        assert entries[0]["hasInputBlob"] and entries[0]["hasOutputBlob"]
        assert entries[0]["simulated"] is False
        # The SEC-07 redaction happened before persistence: the AWS key
        # shape must appear nowhere in the wire stream.
        assert "AKIAIOSFODNN7EXAMPLE" not in str(entries)

        _request(proc, 9, "shutdown", {"reason": "test done"})
        proc.wait(timeout=10)
    finally:
        if proc.poll() is None:
            proc.kill()


def test_ledger_methods_refused_without_workspace():
    """ledger RPCs without a configured workspace fail structurally."""
    proc = spawn_sidecar()
    try:
        send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "handshake",
                "params": {
                    "protocolVersion": protocol.PROTOCOL_VERSION,
                    "client": "pytest",
                },
            },
        )
        assert "error" not in recv(proc)

        response = _request(proc, 2, "ledger.append", _append_params(1))
        assert response["error"]["code"] == protocol.ERROR_LEDGER_UNAVAILABLE
        response = _request(proc, 3, "ledger.query", {})
        assert response["error"]["code"] == protocol.ERROR_LEDGER_UNAVAILABLE

        _request(proc, 9, "shutdown", {})
        proc.wait(timeout=10)
    finally:
        if proc.poll() is None:
            proc.kill()
