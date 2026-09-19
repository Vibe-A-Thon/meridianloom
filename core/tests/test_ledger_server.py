"""Handshake key provisioning for the ledger (FR-M10-04, SEC-06).

The extension host holds the Ed25519 seed in OS-keychain-backed
SecretStorage and provisions it to the sidecar over the stdio handshake.
These tests drive the dispatch layer directly (no subprocess) and assert
the signer identity is stable per seed, that malformed seeds are refused,
and that key material is never persisted under the workspace.
"""

from __future__ import annotations

import base64

import pytest

from meridian_core import protocol
from meridian_core.server import SidecarServer

SEED = bytes(range(32))


def _handshake(server: SidecarServer, **extra) -> dict:
    params = {"protocolVersion": protocol.PROTOCOL_VERSION, "client": "pytest"}
    params.update(extra)
    response = server.handle_message(
        {"jsonrpc": "2.0", "id": 1, "method": "handshake", "params": params}
    )
    assert response is not None
    return response


class TestHandshakeKeyProvisioning:
    def test_seed_provisions_a_stable_signer_identity(self, tmp_path):
        encoded = base64.b64encode(SEED).decode()
        first = SidecarServer()
        _handshake(first, workspaceDir=str(tmp_path), ledgerSigningKey=encoded)
        public_first = first._ensure_ledger().signing_public_key

        second = SidecarServer()
        _handshake(second, workspaceDir=str(tmp_path), ledgerSigningKey=encoded)
        assert second._ensure_ledger().signing_public_key == public_first

    def test_without_seed_an_ephemeral_signer_is_used(self, tmp_path):
        server = SidecarServer()
        _handshake(server, workspaceDir=str(tmp_path))
        # Distinct per process: no keychain, no stable identity.
        other = SidecarServer()
        _handshake(other, workspaceDir=str(tmp_path))
        assert server._ensure_ledger().signing_public_key != (
            other._ensure_ledger().signing_public_key
        )

    def test_malformed_base64_seed_rejected(self, tmp_path):
        server = SidecarServer()
        response = _handshake(
            server, workspaceDir=str(tmp_path), ledgerSigningKey="!!!not-base64"
        )
        assert response["error"]["code"] == protocol.INVALID_PARAMS

    def test_wrong_length_seed_rejected(self, tmp_path):
        server = SidecarServer()
        encoded = base64.b64encode(b"short").decode()
        response = _handshake(
            server, workspaceDir=str(tmp_path), ledgerSigningKey=encoded
        )
        assert response["error"]["code"] == protocol.INVALID_PARAMS
        assert response["error"]["data"]["decodedBytes"] == 5

    def test_seed_never_written_under_the_workspace(self, tmp_path):
        server = SidecarServer()
        _handshake(
            server,
            workspaceDir=str(tmp_path),
            ledgerSigningKey=base64.b64encode(SEED).decode(),
        )
        server._ensure_ledger()
        server.ledger.close()
        for path in tmp_path.rglob("*"):
            if path.is_file():
                assert SEED not in path.read_bytes()

    def test_injected_ledger_is_used_without_handshake(self):
        from meridian_core.ledger import EphemeralSigningKeyProvider, Ledger

        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            ledger = Ledger(
                __import__("pathlib").Path(tmp) / "ledger",
                EphemeralSigningKeyProvider(),
            )
            server = SidecarServer(ledger=ledger)
            assert server.ledger is ledger
            ledger.close()
