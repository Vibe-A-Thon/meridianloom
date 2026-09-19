"""FR-M43-01 / SEC-36 / D39 (N2 Workstream D task 13): customer-controlled
receipt storage for signed ledger roots.

Receipts make rollback/replacement detection possible (FR-M43-02); here we
prove: the local file store is the default and is durable/round-trippable;
the HTTP endpoint store is behind config and off by default; with no
remote witness configured remote witnessing is a no-op whose limitation is
stated (FR-M43-03); a receipt verifies with public keys only — nothing
from Meridian's or the witness operator's servers (SEC-36); and signer
enrolment, rotation and revocation are recorded as ordinary ledger
entries, so the trusted-key history is hash-chained, not side-tabled.
"""

from __future__ import annotations

import base64
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
)

from meridian_core.ledger import (
    EphemeralSigningKeyProvider,
    Ledger,
    ProvisionedSigningKeyProvider,
)
from meridian_core.ledger import receipts as rc


def make_entry(seq: int, **extra) -> dict:
    entry = {
        "story_id": "RCPT-1",
        "phase": "build",
        "loop_id": "L2-task",
        "loop_iteration": 1,
        "actor_id": "agent-rcpt",
        "actor_version": "0.0.1",
        "actor_kind": "role",
        "policy_version": "policy-v1",
        "action_type": "diff",
        "ts_utc": f"2026-09-01T00:00:{seq:06d}Z",
    }
    entry.update(extra)
    return entry


@pytest.fixture()
def ledger(tmp_path):
    led = Ledger(tmp_path / "ledger", EphemeralSigningKeyProvider())
    for seq in range(1, 6):
        led.append(make_entry(seq))
    led.emit_tree_head_now()
    yield led
    led.close()


def test_file_receipt_store_roundtrip(tmp_path, ledger):
    store = rc.FileReceiptStore(tmp_path / "receipts")
    receipt = rc.make_receipt(
        ledger.latest_tree_head() and _wire_head(ledger),
        ledger.signing_public_key,
        witness_id="local-file-store",
    )
    rid = store.store(receipt)
    assert rid == rc.receipt_id(receipt)
    loaded = store.get(rid)
    assert loaded == receipt
    assert store.list() == [receipt]
    # Content-addressed: the id commits to the receipt body.
    assert len(rid) == 64
    assert store.get("ff" * 32) is None


def _wire_head(ledger) -> dict:
    return {
        "seq": ledger.latest_tree_head()["seq"],
        "rootHash": ledger.latest_tree_head()["root_hash"].hex(),
        "signedAt": ledger.latest_tree_head()["signed_at"],
        "signature": ledger.latest_tree_head()["signature"].hex(),
    }


def test_receipt_verifies_with_public_keys_only(ledger):
    """SEC-36: receipt verification needs only the receipt document and
    public keys — no server, no ledger, no keystore."""
    witness_key = Ed25519PrivateKey.generate()
    receipt = rc.make_receipt(
        _wire_head(ledger), ledger.signing_public_key, "customer-witness-1", witness_key
    )
    detached = json.loads(json.dumps(receipt))  # simulate receiving it cold
    assert rc.verify_receipt_tree_head(detached)
    assert rc.verify_witness_signature(detached)
    # Tampering with the recorded root breaks BOTH verifications.
    tampered = json.loads(json.dumps(receipt))
    tampered["treeHead"]["rootHash"] = "ab" * 32
    assert not rc.verify_receipt_tree_head(tampered)
    assert not rc.verify_witness_signature(tampered)


def test_witness_key_is_independent_of_ledger_key(ledger):
    """The witness countersigns with its OWN key; compromising the ledger
    signer does not let anyone forge witness receipts."""
    witness_key = Ed25519PrivateKey.generate()
    receipt = rc.make_receipt(
        _wire_head(ledger), ledger.signing_public_key, "w", witness_key
    )
    # The ledger key CANNOT verify the witness signature...
    from cryptography.exceptions import InvalidSignature

    with pytest.raises(InvalidSignature):
        ledger._signing_key.private_key().public_key().verify(
            bytes.fromhex(receipt["witnessSignature"]), rc._receipt_body(receipt)
        )
    # ...and a different witness key cannot either.
    other = Ed25519PrivateKey.generate()
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

    other_pub = Ed25519PrivateKey.generate().public_key().public_bytes(
        Encoding.Raw, PublicFormat.Raw
    )
    assert not rc.verify_witness_signature(
        {**receipt, "witness": {**receipt["witness"], "publicKey": base64.b64encode(other_pub).decode()}}
    )


class _ReceiptHandler(BaseHTTPRequestHandler):
    received: list[bytes] = []

    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        type(self).received.append(body)
        self.send_response(200)
        self.end_headers()

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b"[]")

    def log_message(self, *args):
        pass


def test_http_receipt_store_posts_to_customer_endpoint(tmp_path, ledger):
    """The remote endpoint store is real but only ever used when the
    customer configures it (D39)."""
    _ReceiptHandler.received = []
    server = HTTPServer(("127.0.0.1", 0), _ReceiptHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        store = rc.HttpReceiptStore(f"http://127.0.0.1:{server.server_port}/")
        receipt = rc.make_receipt(
            _wire_head(ledger), ledger.signing_public_key, "remote-witness"
        )
        rid = store.store(receipt)
        assert rid == rc.receipt_id(receipt)
        assert _ReceiptHandler.received, "receipt must be POSTed to the endpoint"
        posted = json.loads(_ReceiptHandler.received[0])
        assert posted["kind"] == rc.RECEIPT_KIND
        assert store.list() == []
    finally:
        server.shutdown()
        server.server_close()


def test_http_store_requires_https_for_remote_hosts():
    with pytest.raises(rc.ReceiptStoreError):
        rc.HttpReceiptStore("http://receipts.example.com/")


def test_http_store_failure_raises_not_silent(tmp_path, ledger):
    store = rc.HttpReceiptStore("http://127.0.0.1:1/", timeout=0.5)
    receipt = rc.make_receipt(
        _wire_head(ledger), ledger.signing_public_key, "unreachable"
    )
    with pytest.raises(rc.ReceiptStoreError):
        store.store(receipt)


def test_remote_witnessing_off_by_default(tmp_path):
    """D39: the seam exists but is a no-op until the customer configures
    an endpoint; the default is the local file store."""
    config = rc.ReceiptConfig(store_dir=tmp_path / "receipts")
    assert not rc.remote_witnessing(config)
    store = rc.receipt_store_from_config(config)
    assert isinstance(store, rc.FileReceiptStore)
    # Fully unconfigured: a null store with the limitation attached.
    null = rc.receipt_store_from_config(rc.ReceiptConfig())
    assert isinstance(null, rc.NullReceiptStore)
    assert null.store({"kind": rc.RECEIPT_KIND}) == ""
    assert null.list() == []


def test_configured_remote_endpoint_selects_http_store(tmp_path):
    config = rc.ReceiptConfig(
        store_dir=tmp_path / "receipts", remote_url="https://witness.example.com/"
    )
    assert rc.remote_witnessing(config)
    assert isinstance(rc.receipt_store_from_config(config), rc.HttpReceiptStore)


def test_no_witness_is_noop_with_stated_limitation(tmp_path, ledger):
    """FR-M43-03: unconfigured witnessing is a no-op AND the interface
    states the limitation honestly."""
    config = rc.ReceiptConfig(store_dir=tmp_path / "receipts")
    assert not rc.remote_witnessing(config)
    limitation = rc.unwitnessed_limitation()
    assert "wholesale ledger replacement" in limitation
    assert "witness" in limitation.lower()
    # The limitation is also what the null store and the open verifiers
    # surface, so it cannot drift silently.
    assert rc.NullReceiptStore.limitation == limitation


def test_signer_enrolment_rotation_revocation_are_ledger_entries(ledger):
    """FR-M43-01: the signer lifecycle is recorded IN the chain."""
    key_a = Ed25519PrivateKey.generate().public_key()
    key_b = Ed25519PrivateKey.generate().public_key()
    rc.record_signer_event(
        ledger,
        "enrol",
        key_id="signer:2026-Q3",
        public_key=key_a.public_bytes_raw(),
        reason="initial enrolment",
        actor="security-admin",
    )
    rc.record_signer_event(
        ledger,
        "rotate",
        key_id="signer:2026-Q4",
        public_key=key_b.public_bytes_raw(),
        previous_key_id="signer:2026-Q3",
        reason="quarterly rotation",
        actor="security-admin",
    )
    rc.record_signer_event(
        ledger, "revoke", key_id="signer:2026-Q3", reason="suspected compromise", actor="security-admin"
    )
    # Ordinary chain entries: the history is hash-chained and verifies.
    assert ledger.verify().ok
    history = rc.signer_history(ledger)
    assert [h.event for h in history] == [
        "signer_enrol",
        "signer_rotate",
        "signer_revoke",
    ]
    assert history[0].key_id == "signer:2026-Q3"
    assert history[1].previous_key_id == "signer:2026-Q3"
    assert history[0].public_key is not None
    assert history[2].public_key is None  # revocation names, does not publish

    # trusted_keys_at replays the recorded lifecycle.
    assert rc.trusted_keys_at(history, history[0].sequence) == {"signer:2026-Q3"}
    assert rc.trusted_keys_at(history, history[1].sequence) == {
        "signer:2026-Q3",
        "signer:2026-Q4",
    }
    assert rc.trusted_keys_at(history, history[2].sequence) == {"signer:2026-Q4"}


def test_signer_event_rejects_unknown_events(ledger):
    with pytest.raises(ValueError):
        rc.record_signer_event(ledger, "defenestrate", key_id="x")


def test_receipt_store_acknowledged_write_survives(tmp_path, ledger):
    """FR-M10-08 durability standard applied to receipts: an acknowledged
    store() leaves the receipt on disk (atomic replace + fsync)."""
    store = rc.FileReceiptStore(tmp_path / "receipts")
    receipt = rc.make_receipt(
        _wire_head(ledger), ledger.signing_public_key, "durability"
    )
    rid = store.store(receipt)
    # Re-open from disk only, as a fresh process would.
    fresh = rc.FileReceiptStore(tmp_path / "receipts")
    assert fresh.get(rid) == receipt
