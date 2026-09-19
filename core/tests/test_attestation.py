"""FR-M43-09 / FR-M43-10 (N2 Workstream D task 20): versioned attestations
in an in-toto-compatible envelope; build provenance and agent activity are
distinct predicates sharing one attestation id.
"""

from __future__ import annotations

import base64
import json

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
)

from meridian_core import attestation as at
from meridian_core.ledger import merkle

DECISION = {
    "version": "v1",
    "repository": "git@example.test:acme/app.git",
    "subject": "PR-42",
    "base_commit": "a" * 40,
    "head_commit": "b" * 40,
    "diff_digest": "c" * 64,
    "policy_version": "policy-2026-09",
    "approver": "human@example.test",
    "approved_by_class": "human_individual",
}

APPROVALS = [
    {
        "approver": "human@example.test",
        "approvedBy": {
            "class": "human_individual",
            "identityAssurance": "asserted",
            "classifier": "meridian-governance",
        },
    }
]

EVIDENCE = ["ev://test-run/1", "ev://scan/2"]

DEPS = {"lib/foo.jar": "ab" * 32, "lib/bar.py": "cd" * 32}

BUILDER = {"id": "meridian-loop", "buildRecipe": "gradle build verify"}

ACTIVITY = {"actor": "agent-builder-1", "action": "implement-story"}


def ledger_root_hex(leaves: list[bytes]) -> str:
    return merkle.root(leaves).hex()


def signed_envelope(tmp_path, **kwargs):
    private_key = Ed25519PrivateKey.generate()
    payload = at.build_statements(**kwargs)
    envelope = at.sign_envelope(payload, private_key)
    public_key = at.public_key_bytes(private_key)
    return payload, envelope, at.key_id_for_public_key(public_key), public_key


def test_round_trip_build_sign_parse_verify(tmp_path) -> None:
    leaves = [b"leaf-a", b"leaf-b"]
    payload, envelope, keyid, public_key = signed_envelope(
        tmp_path,
        commit="b" * 40,
        policy_decision=DECISION,
        approvals=APPROVALS,
        evidence=EVIDENCE,
        dependency_digests=DEPS,
        ledger_root=ledger_root_hex(leaves),
        build_provenance=BUILDER,
        agent_activity=ACTIVITY,
    )
    raw = json.dumps(envelope).encode("utf-8")

    parsed = at.parse_envelope(raw)

    assert parsed.attestation_id == payload["attestationId"]
    assert at.verify_envelope(parsed, {keyid: public_key}) is True


def test_tampered_payload_fails_verification(tmp_path) -> None:
    leaves = [b"leaf-a"]
    _, envelope, keyid, public_key = signed_envelope(
        tmp_path,
        commit="b" * 40,
        policy_decision=DECISION,
        ledger_root=ledger_root_hex(leaves),
        build_provenance=BUILDER,
    )
    # Decode, mutate the commit, re-encode without re-signing.
    decoded = json.loads(json.dumps(envelope))
    payload = json.loads(base64.b64decode(decoded["payload"]))
    payload["statements"][0]["predicate"]["commit"] = "f" * 40
    decoded["payload"] = base64.b64encode(
        json.dumps(payload, sort_keys=True).encode("utf-8")
    ).decode("ascii")

    parsed = at.parse_envelope(json.dumps(decoded).encode("utf-8"))

    assert at.verify_envelope(parsed, {keyid: public_key}) is False


def test_unknown_version_raises_not_misparses(tmp_path) -> None:
    private_key = Ed25519PrivateKey.generate()
    payload = at.build_statements(
        commit="b" * 40,
        policy_decision=DECISION,
        ledger_root="ab" * 32,
        build_provenance=BUILDER,
    )
    payload["attestationVersion"] = 99
    envelope = at.sign_envelope(payload, private_key)

    with pytest.raises(at.UnknownAttestationVersion):
        at.parse_envelope(json.dumps(envelope).encode("utf-8"))


def test_combined_event_two_statements_one_id_distinct_predicates(
    tmp_path,
) -> None:
    payload, envelope, keyid, public_key = signed_envelope(
        tmp_path,
        commit="b" * 40,
        policy_decision=DECISION,
        approvals=APPROVALS,
        evidence=EVIDENCE,
        dependency_digests=DEPS,
        ledger_root="ab" * 32,
        build_provenance=BUILDER,
        agent_activity=ACTIVITY,
    )
    parsed = at.parse_envelope(json.dumps(envelope).encode("utf-8"))

    build = parsed.statements_by_predicate(at.BUILD_PROVENANCE_PREDICATE)
    agent = parsed.statements_by_predicate(at.AGENT_ACTIVITY_PREDICATE)
    assert len(build) == 1
    assert len(agent) == 1
    assert build[0]["predicateType"] != agent[0]["predicateType"]
    assert (
        build[0]["predicate"]["attestationId"]
        == agent[0]["predicate"]["attestationId"]
        == parsed.attestation_id
    )


def test_source_identifiers_survive_decoded(tmp_path) -> None:
    _, envelope, _, _ = signed_envelope(
        tmp_path,
        commit="b" * 40,
        policy_decision=DECISION,
        dependency_digests=DEPS,
        ledger_root="ab" * 32,
        build_provenance=BUILDER,
    )
    parsed = at.parse_envelope(json.dumps(envelope).encode("utf-8"))

    decoded = json.dumps(parsed.payload)
    for name in DEPS:
        assert name in decoded
    assert "git-commit:" + "b" * 40 in decoded


def test_ledger_root_matches_independent_merkle(tmp_path) -> None:
    leaves = [b"alpha", b"beta", b"gamma"]
    expected = merkle.root(leaves).hex()
    _, envelope, _, _ = signed_envelope(
        tmp_path,
        commit="b" * 40,
        policy_decision=DECISION,
        ledger_root=expected,
        build_provenance=BUILDER,
        agent_activity=ACTIVITY,
    )
    parsed = at.parse_envelope(json.dumps(envelope).encode("utf-8"))
    for statement in parsed.statements:
        assert statement["predicate"]["ledgerRoot"] == expected


def test_empty_attestation_refused(tmp_path) -> None:
    with pytest.raises(at.AttestationError):
        at.build_statements(
            commit="b" * 40,
            policy_decision=DECISION,
            ledger_root="ab" * 32,
        )


def test_wrong_key_fails(tmp_path) -> None:
    _, envelope, _, _ = signed_envelope(
        tmp_path,
        commit="b" * 40,
        policy_decision=DECISION,
        ledger_root="ab" * 32,
        build_provenance=BUILDER,
    )
    stranger = Ed25519PrivateKey.generate()
    stranger_pub = at.public_key_bytes(stranger)
    parsed = at.parse_envelope(json.dumps(envelope).encode("utf-8"))
    assert at.verify_envelope(parsed, {"0" * 64: stranger_pub}) is False
