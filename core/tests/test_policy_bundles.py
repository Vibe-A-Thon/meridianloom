"""Signed policy bundles (FR-M42-13), emergency revocation and the
offline-hosted policy lease (FR-M42-14), signature verification fail-closed
(SEC-35) — N2 Workstream C task T11.

The bundle shape: the raw pack text + activation + expiry + precedence,
Ed25519-signed with the ledger's own key over a canonical digest of that
metadata. Verification recomputes the payload from the bundle's own
fields; any tamper fails closed. An emergency revocation is a ledger row
effective immediately in-process; a hosted session's lease expires with
its bundle and its checkpoint gate stops the run locally — no network.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from meridian_core.governance import policy as policy_mod
from meridian_core.governance import policy_bundle
from meridian_core.ledger.core import Ledger
from meridian_core.ledger.keys import EphemeralSigningKeyProvider

NOW = "2026-01-15T12:00:00Z"
ACTIVATION = "2026-01-01T00:00:00Z"
EXPIRY = "2026-02-01T00:00:00Z"

PACK_V1 = """
version: 2
protectedBranches: [main]
profiles:
  verify:
    description: verification
    criteria:
      - id: tests-pass
        kind: testEvidence
"""

PACK_V2 = """
version: 3
protectedBranches: [main, release]
profiles:
  verify:
    description: verification, stricter
    criteria:
      - id: tests-pass
        kind: testEvidence
      - id: lead-approval
        kind: humanApproval
        roles: [lead]
"""


@pytest.fixture()
def ledger(tmp_path: Path) -> Ledger:
    return Ledger(tmp_path / "ledger", EphemeralSigningKeyProvider())


def _sign(ledger: Ledger, **overrides) -> policy_bundle.PolicyBundle:
    params = {
        "bundle_id": "org-bundle-1",
        "pack_text": PACK_V2,
        "activation": ACTIVATION,
        "expiry": EXPIRY,
        "precedence": 1,
    }
    params.update(overrides)
    return policy_bundle.sign_bundle(ledger, **params)


# -- signing + verification (SEC-35) ---------------------------------------------


def test_signed_bundle_verifies_and_round_trips(ledger: Ledger) -> None:
    """A bundle signed with the ledger key verifies clean, carries the
    activation window and the precedence, and survives the transport
    dict shape byte-for-byte (FR-M42-13)."""
    bundle = _sign(ledger)
    evaluation = policy_bundle.evaluate_bundle(bundle, now=NOW)
    assert evaluation.valid
    assert evaluation.status == "active"
    assert evaluation.errors == ()
    assert evaluation.pack is not None and not evaluation.pack.fail_closed
    assert evaluation.pack.profiles["verify"].name == "verify"

    revived = policy_bundle.bundle_from_dict(policy_bundle.bundle_to_dict(bundle))
    assert revived == bundle
    assert policy_bundle.evaluate_bundle(revived, now=NOW).valid


def test_tampered_pack_fails_closed(ledger: Ledger) -> None:
    """SEC-35: editing the pack text after signing breaks the signature —
    the bundle is invalid and can never supply policy."""
    bundle = _sign(ledger)
    tampered = policy_bundle.PolicyBundle(
        bundle_id=bundle.bundle_id,
        pack_text=bundle.pack_text + "\n# sneaky grant\n",
        activation=bundle.activation,
        expiry=bundle.expiry,
        precedence=bundle.precedence,
        signature=bundle.signature,
        public_key=bundle.public_key,
    )
    evaluation = policy_bundle.evaluate_bundle(tampered, now=NOW)
    assert not evaluation.valid
    assert evaluation.status == "invalid"
    assert not evaluation.applicable
    assert any("signature" in error for error in evaluation.errors)


def test_wrong_key_fails_closed(ledger: Ledger, tmp_path: Path) -> None:
    """SEC-35: a bundle whose public key is not the signer's verifies
    false — unverifiable means fail-closed, never 'apply and hope'."""
    bundle = _sign(ledger)
    other = Ledger(tmp_path / "other-ledger", EphemeralSigningKeyProvider())
    foreign = policy_bundle.PolicyBundle(
        bundle_id=bundle.bundle_id,
        pack_text=bundle.pack_text,
        activation=bundle.activation,
        expiry=bundle.expiry,
        precedence=bundle.precedence,
        signature=bundle.signature,
        public_key=other.signing_public_key,
    )
    assert not policy_bundle.evaluate_bundle(foreign, now=NOW).valid


def test_malformed_bundle_metadata_fails_closed(ledger: Ledger) -> None:
    """SEC-35: unparseable activation/expiry or an inverted window is an
    invalid bundle, never an applicable one."""
    bad_window = _sign(ledger, activation=EXPIRY, expiry=ACTIVATION)
    evaluation = policy_bundle.evaluate_bundle(bad_window, now=NOW)
    assert not evaluation.valid
    assert any("expiry" in error for error in evaluation.errors)

    bad_time = _sign(ledger, activation="not-a-time")
    assert not policy_bundle.evaluate_bundle(bad_time, now=NOW).valid


def test_malformed_pack_inside_bundle_fails_closed(ledger: Ledger) -> None:
    """SEC-35: a bundle whose pack text does not parse is invalid — the
    signature can be perfect and the bundle still never opens a gate."""
    broken = _sign(ledger, pack_text="version: [not-a-mapping\n")
    evaluation = policy_bundle.evaluate_bundle(broken, now=NOW)
    assert not evaluation.valid
    assert evaluation.errors


# -- activation window + precedence (FR-M42-13) -----------------------------------


def test_activation_and_expiry_window(ledger: Ledger) -> None:
    """FR-M42-13: before activation the bundle is pending; inside the
    window active; after expiry expired. Only active applies."""
    bundle = _sign(ledger)
    assert policy_bundle.evaluate_bundle(bundle, now="2025-12-01T00:00:00Z").status == "pending"
    assert policy_bundle.evaluate_bundle(bundle, now=NOW).status == "active"
    assert policy_bundle.evaluate_bundle(bundle, now="2026-03-01T00:00:00Z").status == "expired"

    selection = policy_bundle.select_policy(
        ledger,
        local=policy_mod.parse_policy_pack(PACK_V1, "local"),
        bundles=[bundle],
        now="2025-12-01T00:00:00Z",
    )
    assert selection.source == "local"  # pending bundle does not govern


def test_precedence_over_local_policy(ledger: Ledger) -> None:
    """FR-M42-13: an active bundle with precedence overrides the local
    pack; the local pack governs again once the bundle expires."""
    local = policy_mod.parse_policy_pack(PACK_V1, "local")
    bundle = _sign(ledger)
    active = policy_bundle.select_policy(ledger, local=local, bundles=[bundle], now=NOW)
    assert active.source == "org-bundle-1"
    assert active.pack.version == 3  # the bundle's pack, not the local v2
    assert "precedence" in active.note
    expired = policy_bundle.select_policy(
        ledger, local=local, bundles=[bundle], now="2026-03-01T00:00:00Z"
    )
    assert expired.source == "local"
    assert expired.pack.version == 2


def test_higher_precedence_bundle_wins(ledger: Ledger) -> None:
    """Among active bundles the higher precedence wins; the choice is
    deterministic (tie-break on bundle id)."""
    local = policy_mod.parse_policy_pack(PACK_V1, "local")
    low = _sign(ledger, bundle_id="org-low", precedence=1)
    high = _sign(ledger, bundle_id="org-high", precedence=5)
    selection = policy_bundle.select_policy(
        ledger, local=local, bundles=[low, high], now=NOW
    )
    assert selection.source == "org-high"


# -- emergency revocation (FR-M42-14) ---------------------------------------------


def test_emergency_revocation_effective_immediately(ledger: Ledger) -> None:
    """FR-M42-14: a revocation row takes effect in-process from commit —
    the very next selection read excludes the bundle (the five-minute
    bound is the outer envelope for replicas; in-process is one read,
    NFR-36)."""
    local = policy_mod.parse_policy_pack(PACK_V1, "local")
    bundle = _sign(ledger)
    assert (
        policy_bundle.select_policy(ledger, local=local, bundles=[bundle], now=NOW).source
        == "org-bundle-1"
    )
    sequence = policy_bundle.revoke_bundle(
        ledger, bundle_id="org-bundle-1", revoked_by="governor@example.com", reason="incident"
    )
    assert sequence > 0
    assert "org-bundle-1" in policy_bundle.revoked_bundle_ids(ledger)
    selection = policy_bundle.select_policy(ledger, local=local, bundles=[bundle], now=NOW)
    assert selection.source == "local"  # revoked bundle no longer governs
    assert "no applicable signed bundle" in selection.note


def test_revocation_is_durable_before_return(ledger: Ledger) -> None:
    """The revocation row is committed before revoke_bundle returns
    (FR-M10-08): it is visible to a fresh query on the same ledger."""
    policy_bundle.revoke_bundle(ledger, bundle_id="b1", reason="test")
    rows = ledger.query(action_type=policy_bundle.BUNDLE_REVOCATION_ACTION, limit=10)
    assert len(rows) == 1
    assert rows[0]["decision"] == "revoked"


# -- the offline-hosted policy lease (FR-M42-14) -----------------------------------


def test_lease_ok_inside_window(ledger: Ledger) -> None:
    bundle = _sign(ledger)
    lease = policy_bundle.issue_lease(
        bundle, lease_id="lease-1", session_id="session-1", issued_at=NOW
    )
    assert lease.expires_at == EXPIRY  # the lease expires WITH the bundle
    check = policy_bundle.lease_checkpoint(ledger, lease, now=NOW)
    assert check.decision == "ok"


def test_offline_hosted_run_stops_at_lease_expiry(ledger: Ledger) -> None:
    """FR-M42-14: past the lease expiry the checkpoint gate returns
    stop_expired and the stop is ledger-recorded — an offline run halts
    at its next checkpoint with no connectivity, because the check is a
    local clock read."""
    bundle = _sign(ledger)
    lease = policy_bundle.issue_lease(bundle, lease_id="lease-1", session_id="session-1")
    check = policy_bundle.lease_checkpoint(ledger, lease, now="2026-02-02T00:00:00Z")
    assert check.decision == "stop_expired"
    assert check.recorded_sequence is not None
    rows = ledger.query(action_type="policy_lease_checkpoint", limit=10)
    assert len(rows) == 1  # the stop is durable before the caller acts
    assert rows[0]["decision"] == "stop_expired"
    assert rows[0]["external_session_id"] == "session-1"

    # Re-checking the same lease does not duplicate the stop record.
    again = policy_bundle.lease_checkpoint(ledger, lease, now="2026-02-03T00:00:00Z")
    assert again.decision == "stop_expired"
    assert again.recorded_sequence == check.recorded_sequence
    assert len(ledger.query(action_type="policy_lease_checkpoint", limit=10)) == 1


def test_lease_stops_when_bundle_revoked(ledger: Ledger) -> None:
    """FR-M42-14: a revoked bundle stops its hosted sessions at the next
    checkpoint even inside the lease window."""
    bundle = _sign(ledger)
    lease = policy_bundle.issue_lease(bundle, lease_id="lease-1", session_id="session-1")
    policy_bundle.revoke_bundle(ledger, bundle_id="org-bundle-1", reason="incident")
    check = policy_bundle.lease_checkpoint(ledger, lease, now=NOW)
    assert check.decision == "stop_revoked"
    assert check.recorded_sequence is not None
