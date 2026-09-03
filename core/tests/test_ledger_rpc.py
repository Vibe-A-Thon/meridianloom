"""Ledger query API (FR-M10-12) and Chain Viewer backend (FR-M11-01..05)
over the bus: filters, entry detail, integrity verdict, proofs and the
audit-bundle assembly.

Drives the dispatch layer with an injected ledger — the stdio framing is
covered by test_ledger_durability.py and the TS e2e.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

import bus_types

from meridian_core import protocol
from meridian_core.ledger import (
    BlobKeyMissing,
    EphemeralSigningKeyProvider,
    Ledger,
    verify_consistency,
    verify_inclusion,
    verify_tree_head,
)
from meridian_core.server import SidecarServer


def make_entry(seq: int, **extra) -> dict:
    entry = {
        "story_id": "EDB-12345",
        "phase": "build",
        "loop_id": "L2-task",
        "loop_iteration": 1,
        "actor_id": "developer-agent",
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


def call(server: SidecarServer, request_id: int, method: str, params: dict) -> dict:
    response = server.handle_message(
        {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
    )
    assert response is not None and response["id"] == request_id
    return response


def result(server, method, params=None):
    response = call(server, 7, method, params or {})
    assert "error" not in response, response["error"]
    return response["result"]


class TestQueryFilters:
    @pytest.fixture(autouse=True)
    def seed(self, server):
        ledger = server.ledger
        for seq in range(1, 6):
            ledger.append(
                make_entry(
                    seq,
                    story_id="EDB-A" if seq <= 3 else "EDB-B",
                    actor_id="agent-one" if seq % 2 else "agent-two",
                    vendor="claude-code" if seq == 5 else "meridian",
                    action_type="diff" if seq <= 4 else "review",
                )
            )

    def test_no_filter_returns_all(self, server):
        entries = result(server, "ledger.query")["entries"]
        assert [e["sequence"] for e in entries] == [1, 2, 3, 4, 5]

    def test_story_filter(self, server):
        entries = result(server, "ledger.query", {"storyId": "EDB-B"})["entries"]
        assert [e["sequence"] for e in entries] == [4, 5]

    def test_agent_filter(self, server):
        entries = result(server, "ledger.query", {"actorId": "agent-two"})["entries"]
        assert [e["sequence"] for e in entries] == [2, 4]

    def test_vendor_filter(self, server):
        entries = result(server, "ledger.query", {"vendor": "claude-code"})["entries"]
        assert [e["sequence"] for e in entries] == [5]
        assert entries[0]["observationConfidence"] == "direct"

    def test_action_filter(self, server):
        entries = result(server, "ledger.query", {"actionType": "review"})["entries"]
        assert [e["sequence"] for e in entries] == [5]

    def test_sequence_range(self, server):
        entries = result(
            server, "ledger.query", {"fromSequence": 2, "toSequence": 4}
        )["entries"]
        assert [e["sequence"] for e in entries] == [2, 3, 4]

    def test_time_range(self, server):
        entries = result(
            server,
            "ledger.query",
            {"fromTimestamp": "2026-09-01T00:00:000002Z",
             "toTimestamp": "2026-09-01T00:00:000004Z"},
        )["entries"]
        assert [e["sequence"] for e in entries] == [2, 3, 4]

    def test_limit(self, server):
        entries = result(server, "ledger.query", {"limit": 2})["entries"]
        assert len(entries) == 2

    def test_stream_shape(self, server):
        entry = result(server, "ledger.query", {"fromSequence": 5})["entries"][0]
        assert entry["vendor"] == "claude-code"
        assert entry["simulated"] is False
        assert entry["entryHash"] != "0" * 64


class TestGetEntry:
    def test_detail_with_decrypted_blobs(self, server):
        server.ledger.append(
            make_entry(
                1,
                input="write the handler",
                output="done",
                tool_calls=[{"tool": "edit", "path": "a.py"}],
                blob_subject="story:EDB-A",
                confidence=0.8,
                cost_usd=0.01,
            )
        )
        detail = result(server, "ledger.getEntry", {"sequence": 1})
        assert detail["input"] == "write the handler"
        assert detail["output"] == "done"
        assert detail["inputAvailable"] and detail["outputAvailable"]
        assert detail["toolCalls"] == [{"tool": "edit", "path": "a.py"}]
        assert detail["confidence"] == 0.8
        assert detail["costUsd"] == 0.01
        assert detail["blobKeyId"] == "bk:story:EDB-A"
        assert detail["inputDigest"] and detail["inputRef"]
        # FR-M11-03 shape carries the chain hashes too.
        assert detail["entryHash"] and detail["previousHash"]

    def test_shredded_key_reports_unavailable_not_error(self, server):
        server.ledger.append(
            make_entry(1, input="personal", blob_subject="subject-x")
        )
        assert server.ledger.shred_subject("subject-x") is True
        detail = result(server, "ledger.getEntry", {"sequence": 1})
        assert detail["input"] is None
        assert detail["inputAvailable"] is False

    def test_missing_sequence_rejected(self, server):
        response = call(server, 3, "ledger.getEntry", {"sequence": 99})
        assert response["error"]["code"] == protocol.INVALID_PARAMS


class TestVerifyMethod:
    def test_verified_verdict(self, server):
        server.ledger.append(make_entry(1))
        server.ledger.append(make_entry(2))
        verdict = result(server, "ledger.verify")
        assert verdict["ok"] is True
        assert verdict["entriesChecked"] == 2
        assert verdict["firstDivergentSequence"] is None
        assert verdict["verifiedAt"]

    def test_tamper_names_first_divergent(self, server):
        ledger = server.ledger
        for seq in range(1, 4):
            ledger.append(make_entry(seq))
        ledger.conn.execute("DROP TRIGGER ledger_entry_no_update")
        ledger.conn.execute(
            "UPDATE ledger_entry SET cost_usd = 9.99 WHERE seq = 2"
        )
        ledger.conn.commit()
        verdict = result(server, "ledger.verify")
        assert verdict["ok"] is False
        assert verdict["firstDivergentSequence"] == 2


class TestProofs:
    def test_inclusion_proof_verifies(self, server):
        ledger = server.ledger
        for seq in range(1, 8):
            ledger.append(make_entry(seq))
        proof = result(server, "ledger.proof", {"sequence": 3})["inclusion"]
        assert proof["treeSize"] == 7
        assert proof["leafIndex"] == 2
        assert verify_inclusion(
            proof["leafIndex"],
            bytes.fromhex(proof["leafHash"]),
            proof["treeSize"],
            [bytes.fromhex(node) for node in proof["path"]],
            bytes.fromhex(proof["rootHash"]),
        )
        # A forged leaf at the same position must not verify.
        assert not verify_inclusion(
            proof["leafIndex"],
            b"\xde" * 32,
            proof["treeSize"],
            [bytes.fromhex(node) for node in proof["path"]],
            bytes.fromhex(proof["rootHash"]),
        )

    def test_consistency_proof_verifies(self, server):
        ledger = server.ledger
        for seq in range(1, 10):
            ledger.append(make_entry(seq))
        proof = result(server, "ledger.proof", {"fromSize": 4, "toSize": 9})[
            "consistency"
        ]
        assert verify_consistency(
            proof["fromSize"],
            bytes.fromhex(proof["fromRootHash"]),
            proof["toSize"],
            bytes.fromhex(proof["toRootHash"]),
            [bytes.fromhex(node) for node in proof["path"]],
        )

    def test_param_combinations_validated(self, server):
        server.ledger.append(make_entry(1))
        response = call(server, 3, "ledger.proof", {})
        assert response["error"]["code"] == protocol.INVALID_PARAMS
        response = call(
            server, 4, "ledger.proof", {"sequence": 1, "fromSize": 1, "toSize": 1}
        )
        assert response["error"]["code"] == protocol.INVALID_PARAMS
        response = call(server, 5, "ledger.proof", {"fromSize": 2, "toSize": 1})
        assert response["error"]["code"] == protocol.INVALID_PARAMS


class TestExportBundle:
    def test_bundle_assembly_and_signature(self, server):
        ledger = server.ledger
        for seq in range(1, 4):
            ledger.append(make_entry(seq, input=f"payload {seq}", blob_subject="s"))
        bundle = result(
            server, "ledger.exportBundle", {"fromSequence": 2, "toSequence": 3}
        )
        assert bundle["formatVersion"] == 1
        assert bundle["range"] == {"fromSequence": 2, "toSequence": 3}
        assert [e["sequence"] for e in bundle["entries"]] == [2, 3]
        # Chain linkage inside the range is present and correct.
        assert bundle["entries"][1]["previousHash"] == bundle["entries"][0]["entryHash"]
        # The head covers the range end and its signature verifies with
        # the bundled public key alone (SEC-29).
        head = bundle["treeHead"]
        assert head["seq"] >= 3
        assert verify_tree_head(
            base64.b64decode(bundle["signer"]["publicKey"]),
            head["seq"],
            bytes.fromhex(head["rootHash"]),
            head["signedAt"],
            bytes.fromhex(head["signature"]),
        )
        # Entries carry ciphertext refs so a third party checks the chain
        # without keys.
        assert bundle["entries"][0]["inputDigest"]
        assert bundle["entries"][0]["inputRef"]

    def test_bundle_filter(self, server):
        ledger = server.ledger
        ledger.append(make_entry(1, story_id="EDB-A"))
        ledger.append(make_entry(2, story_id="EDB-B"))
        bundle = result(
            server, "ledger.exportBundle", {"storyId": "EDB-B", "agentId": "developer-agent"}
        )
        assert bundle["filter"] == {
            "storyId": "EDB-B",
            "agentId": "developer-agent",
        }
        assert [e["sequence"] for e in bundle["entries"]] == [2]


class TestDoctorWiring:
    def test_ledger_checks_report_real_state(self, server):
        ledger = server.ledger
        ledger.append(make_entry(1))
        checks = result(server, "doctor/run", {"checks": ["ledger", "signing-key"]})
        by_id = {c["id"]: c for c in checks["checks"]}
        # Chain verified at ledger open (FR-M10-09) and reported here.
        assert by_id["ledger"]["status"] == "pass"
        assert "sequence 1" in by_id["ledger"]["detail"]
        # The injected ledger has no provisioned seed: an honest fail, not
        # the old not-installed warn.
        assert by_id["signing-key"]["status"] == "fail"

    def test_tampered_chain_fails_doctor_ledger_check(self, server):
        ledger = server.ledger
        ledger.append(make_entry(1))
        ledger.append(make_entry(2))
        ledger.conn.execute("DROP TRIGGER ledger_entry_no_update")
        ledger.conn.execute("UPDATE ledger_entry SET phase = 'tampered' WHERE seq = 2")
        ledger.conn.commit()
        ledger.last_verify = None  # force a fresh verification
        checks = result(server, "doctor/run", {"checks": ["ledger"]})
        check = checks["checks"][0]
        assert check["status"] == "fail"
        assert "sequence 2" in check["detail"]


class TestTierOwnership:
    def test_all_ledger_methods_owned_by_flight_recorder(self):
        ledger_methods = [
            method
            for capability in bus_types.CAPABILITIES
            if capability["id"] == "recorder.ledger"
            for method in capability["rpcMethods"]
        ]
        assert sorted(ledger_methods) == [
            "ledger.append",
            "ledger.exportBundle",
            "ledger.getEntry",
            "ledger.proof",
            "ledger.query",
            "ledger.verify",
        ]
        # Single ownership across the whole registry (the sidecar asserts
        # this at startup; this is the schema-side witness).
        claims = [
            method
            for capability in bus_types.CAPABILITIES
            for method in capability["rpcMethods"]
        ]
        assert len(claims) == len(set(claims))

    def test_ssdf_mapping_is_marked_todo_in_contract(self):
        # The SSDF/ISO-42001 mapping is F0-E task 25; the contract carries
        # the pointer so the GUI and reviewers see it.
        schema_path = (
            Path(__file__).resolve().parent.parent.parent
            / "shared" / "schema" / "methods.json"
        )
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        description = schema["x-methods"]["ledger.exportBundle"]["description"]
        assert "SSDF" in description
        assert "task 25" in description
