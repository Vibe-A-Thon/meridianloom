"""The full signed audit bundle (FR-M36-04, SEC-29, FR-M12-11; task 25).

Every property is checked the way the open verifier checks it: with the
bundled material alone — the public key inside the bundle, RFC 6962
reference verification, and canonical-JSON recomputation. Task 26 turns
the local ``verify_bundle`` below into the standalone verifier/ scripts;
the algorithm must stay identical.
"""

from __future__ import annotations

import base64
import copy
import hashlib
import json
from pathlib import Path

import pytest

from meridian_core.ledger import (
    EphemeralSigningKeyProvider,
    Ledger,
    canonical,
    merkle,
    verify_inclusion,
    verify_tree_head,
)
from meridian_core.ledger.core import utc_now
from meridian_core.server import SidecarServer


def make_entry(seq: int, **extra) -> dict:
    entry = {
        "story_id": "BUNDLE-A" if seq % 2 else "BUNDLE-B",
        "phase": "build",
        "loop_id": "L2-task",
        "loop_iteration": 1,
        "actor_id": "agent-one" if seq % 2 else "agent-two",
        "actor_version": "0.0.1",
        "actor_kind": "role",
        "policy_version": "policy-v1",
        "action_type": "diff",
        "ts_utc": f"2026-09-01T00:00:{seq:06d}Z",
    }
    entry.update(extra)
    return entry


@pytest.fixture()
def server(tmp_path):
    ledger = Ledger(tmp_path / "ledger", EphemeralSigningKeyProvider())
    instance = SidecarServer(ledger=ledger)
    yield instance
    ledger.close()


def export(server, **params) -> dict:
    response = server.handle_message(
        {
            "jsonrpc": "2.0",
            "id": 11,
            "method": "ledger.exportBundle",
            "params": params,
        }
    )
    assert "error" not in response, response["error"]
    return response["result"]


# -- the standalone verification algorithm (mirrors verifier/verify.py) ------


def verify_bundle(bundle: dict) -> list[str]:
    """Verify with bundled material only; returns a list of problems."""
    problems: list[str] = []

    def need(condition: bool, message: str) -> None:
        if not condition:
            problems.append(message)

    entries = bundle.get("entries", [])
    head = bundle.get("treeHead")
    proofs = bundle.get("proofs", {})
    signature = bundle.get("signature", {})
    signer = bundle.get("signer", {})

    need(bundle.get("formatVersion") == 1, "unsupported formatVersion")
    try:
        public_key = base64.b64decode(signer.get("publicKey", ""), validate=True)
    except Exception:
        public_key = b""
        problems.append("signer.publicKey is not valid base64")
    need(len(public_key) == 32, "signer.publicKey must decode to 32 bytes")

    # 1. Chain continuity within the bundle and per-entry hash recompute.
    for index, entry in enumerate(entries):
        recomputed = hashlib.sha256(
            bytes.fromhex(entry["previousHash"])
            + canonical.canonical_json(entry["hashPayload"])
        ).hexdigest()
        need(
            recomputed == entry["entryHash"],
            f"entry {entry['sequence']}: entryHash does not match its content",
        )
        if index:
            need(
                entry["previousHash"] == entries[index - 1]["entryHash"],
                f"entry {entry['sequence']}: chain link is broken",
            )

    # 2. Inclusion proofs anchor each entry into the signed tree.
    for proof in proofs.get("inclusion", []):
        entry = next(
            (e for e in entries if e["sequence"] == proof["sequence"]), None
        )
        need(entry is not None, f"proof for unknown sequence {proof['sequence']}")
        if entry is None:
            continue
        need(
            verify_inclusion(
                proof["leafIndex"],
                bytes.fromhex(entry["entryHash"]),
                proofs["treeSize"],
                [bytes.fromhex(node) for node in proof["path"]],
                bytes.fromhex(proofs["rootHash"]),
            ),
            f"entry {proof['sequence']}: Merkle inclusion proof does not verify",
        )

    # 3. The signed tree head commits to that tree.
    if head is not None:
        need(
            head["seq"] == proofs.get("treeSize"),
            "tree head sequence does not match the proof tree size",
        )
        need(
            head["rootHash"] == proofs.get("rootHash"),
            "tree head root does not match the proof root",
        )
        need(
            verify_tree_head(
                public_key,
                head["seq"],
                bytes.fromhex(head["rootHash"]),
                head["signedAt"],
                bytes.fromhex(head["signature"]),
            ),
            "tree head signature does not verify with the bundled public key",
        )

    # 4. The bundle signature covers every other field.
    core = {key: value for key, value in bundle.items() if key != "signature"}
    digest = hashlib.sha256(canonical.canonical_json(core)).digest()
    need(
        digest.hex() == signature.get("digest"),
        "bundle digest does not match the content (tampered field?)",
    )
    if len(public_key) == 32:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PublicKey,
        )

        try:
            Ed25519PublicKey.from_public_bytes(public_key).verify(
                bytes.fromhex(signature.get("signature", "")), digest
            )
        except (InvalidSignature, ValueError):
            problems.append("bundle signature does not verify")
    return problems


class TestExportFilters:
    def test_export_by_date_range(self, server):
        ledger = server.ledger
        for seq in range(1, 6):
            ledger.append(make_entry(seq))
        bundle = export(
            server, fromTimestamp="2026-09-01T00:00:000002Z",
            toTimestamp="2026-09-01T00:00:000004Z",
        )
        assert [e["sequence"] for e in bundle["entries"]] == [2, 3, 4]
        assert bundle["filter"]["fromTimestamp"] == "2026-09-01T00:00:000002Z"

    def test_export_by_agent_and_story(self, server):
        ledger = server.ledger
        for seq in range(1, 5):
            ledger.append(make_entry(seq))
        bundle = export(server, storyId="BUNDLE-A", agentId="agent-one")
        assert [e["sequence"] for e in bundle["entries"]] == [1, 3]
        bundle = export(server, agentId="agent-two")
        assert [e["sequence"] for e in bundle["entries"]] == [2, 4]

    def test_export_with_blob_payloads(self, server):
        ledger = server.ledger
        ledger.append(make_entry(1, input="secret prompt", blob_subject="s"))
        bundle = export(server)
        assert bundle["entries"][0]["inputRef"]
        # The preimage carries the hex-projected digest exactly as hashed.
        assert bundle["entries"][0]["hashPayload"]["input_digest"] == (
            bundle["entries"][0]["inputDigest"]
        )


class TestStandaloneVerification:
    @pytest.fixture()
    def bundle(self, server):
        ledger = server.ledger
        for seq in range(1, 9):
            ledger.append(make_entry(seq, confidence=0.5, cost_usd=0.01))
        return export(server, fromSequence=3, toSequence=6)

    def test_bundle_verifies_with_bundled_material_only(self, bundle):
        assert verify_bundle(bundle) == []

    def test_entry_content_tampering_is_rejected(self, bundle):
        # The hash binds hashPayload (the canonical preimage): editing it
        # breaks the entry hash.
        tampered = copy.deepcopy(bundle)
        tampered["entries"][1]["hashPayload"]["phase"] = "tampered"
        problems = verify_bundle(tampered)
        assert any("entry 4: entryHash" in p for p in problems)

    def test_friendly_view_tampering_is_rejected(self, bundle):
        # A field outside hashPayload (the human-readable view) is still
        # caught: the bundle signature digests every field.
        tampered = copy.deepcopy(bundle)
        tampered["entries"][1]["phase"] = "tampered"
        problems = verify_bundle(tampered)
        assert any("digest" in p for p in problems)

    def test_proof_tampering_is_rejected(self, bundle):
        tampered = copy.deepcopy(bundle)
        tampered["proofs"]["inclusion"][0]["path"][0] = "00" * 32
        problems = verify_bundle(tampered)
        assert any("inclusion proof" in p for p in problems)

    def test_signature_tampering_is_rejected(self, bundle):
        tampered = copy.deepcopy(bundle)
        tampered["generatedAt"] = "2099-01-01T00:00:00Z"
        problems = verify_bundle(tampered)
        assert any("digest" in p for p in problems)

    def test_wrong_public_key_is_rejected(self, bundle):
        tampered = copy.deepcopy(bundle)
        tampered["signer"]["publicKey"] = base64.b64encode(b"\x01" * 32).decode()
        problems = verify_bundle(tampered)
        assert any("signature" in p or "tree head" in p for p in problems)


class TestBundleSections:
    def test_compliance_section_maps_all_three_standards(self, server):
        server.ledger.append(make_entry(1))
        bundle = export(server)
        compliance = bundle["compliance"]
        standards = " ".join(compliance["standards"])
        assert "SSDF" in standards
        assert "42001" in standards
        assert "AI Act" in standards
        frameworks = {m["framework"] for m in compliance["mappings"]}
        assert frameworks == {"NIST SSDF", "ISO/IEC 42001:2023", "EU AI Act"}
        for mapping in compliance["mappings"]:
            assert mapping["reference"] and mapping["requirement"]
            assert mapping["bundleFields"]
        # Round-trips through JSON untouched (it is wire data).
        json.dumps(bundle)

    def test_proofs_cover_every_included_entry(self, server):
        ledger = server.ledger
        for seq in range(1, 6):
            ledger.append(make_entry(seq))
        bundle = export(server, storyId="BUNDLE-A")
        proven = {p["sequence"] for p in bundle["proofs"]["inclusion"]}
        included = {e["sequence"] for e in bundle["entries"]}
        assert proven == included
        # The proof tree is the WHOLE ledger, not just the filtered subset.
        assert bundle["proofs"]["treeSize"] == 5
        assert bundle["treeHead"]["seq"] == 5
