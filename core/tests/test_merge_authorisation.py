"""Merge authorisation binding (FR-M42-01/02; FUT-002; N2-T02/T03).

The merge gate's authorisation token binds repository, PR identity, base
and head commits, diff digest, policy version, the evidence set, the
approver and its approvedBy class, and an expiry — signed with the
ledger's Ed25519 key. These tests prove the FR-M42-02 invalidation
matrix: force-push, rebase, changed base, changed policy version,
expired authorisation, replayed approval on a different binding and
missing evidence each block with the violated field named, a tampered
object fails its signature, and an unchanged valid PR still merges —
both at the evaluator and through merge_gate.check_merge.

Zero model calls (FR-M36-07): everything here is local cryptography.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from meridian_core.governance import merge_authorisation, merge_gate, policy
from meridian_core.ledger.core import Ledger
from meridian_core.ledger.keys import EphemeralSigningKeyProvider

PACK_TEXT = """
version: 2
protectedBranches: [main]
profiles:
  review:
    criteria:
      - id: lead-approval
        kind: humanApproval
        roles: [lead]
"""

ISSUED = "2026-09-10T00:00:00.000000Z"
EXPIRES = "2026-09-11T00:00:00.000000Z"
NOW = "2026-09-10T12:00:00.000000Z"
TOO_LATE = "2026-09-12T00:00:00.000000Z"

REPOSITORY = "git.example.com/acme/widget"
SUBJECT = "pr:acme/widget#42"
BASE = "b" * 40
HEAD = "h" * 40
HEAD_FORCE_PUSHED = "H" * 40
POLICY_VERSION = "governance/v2"
EVIDENCE = ("tests:run-100", "security-scan:sast-7")


def patch_digest(marker: str) -> str:
    return merge_authorisation.diff_digest(
        (("src/app.py", marker * 64), ("README.md", "r" * 64))
    )


DIGEST = patch_digest("a")
REBASED_DIGEST = patch_digest("c")


@pytest.fixture()
def keys() -> EphemeralSigningKeyProvider:
    return EphemeralSigningKeyProvider()


@pytest.fixture()
def authorisation(keys) -> merge_authorisation.MergeAuthorisation:
    return issue(keys)


def issue(keys, **overrides) -> merge_authorisation.MergeAuthorisation:
    fields = {
        "repository": REPOSITORY,
        "subject": SUBJECT,
        "base_commit": BASE,
        "head_commit": HEAD,
        "digest": DIGEST,
        "policy_version": POLICY_VERSION,
        "evidence": EVIDENCE,
        "approver": "Ada Lovelace <ada@example.com>",
        "approved_by_class": "human_individual",
        "issued_at": ISSUED,
        "expires_at": EXPIRES,
    }
    fields.update(overrides)
    return merge_authorisation.issue_authorisation(keys, **fields)


def presented(**overrides) -> merge_authorisation.MergeBinding:
    state = {
        "repository": REPOSITORY,
        "subject": SUBJECT,
        "base_commit": BASE,
        "head_commit": HEAD,
        "diff_digest": DIGEST,
        "policy_version": POLICY_VERSION,
        "evidence": frozenset(EVIDENCE),
        "now": NOW,
    }
    state.update(overrides)
    return merge_authorisation.MergeBinding(**state)


@pytest.fixture()
def ledger(tmp_path: Path) -> Ledger:
    return Ledger(tmp_path / "ledger", EphemeralSigningKeyProvider())


@pytest.fixture()
def pack() -> policy.PolicyPack:
    parsed = policy.parse_policy_pack(PACK_TEXT, "test-pack")
    assert parsed.errors == []
    return parsed


def append_approval(ledger: Ledger, subject: str, commit: str) -> int:
    """The ledger shape gate.approve writes."""
    result = ledger.append(
        {
            "story_id": f"gate:{subject}",
            "phase": "review",
            "loop_id": "governance",
            "loop_iteration": 1,
            "actor_id": "governor",
            "actor_version": "0",
            "actor_kind": "meta",
            "policy_version": POLICY_VERSION,
            "action_type": "approval",
            "decision": "approved",
            "human_actor": "Ada Lovelace <ada@example.com>",
            "human_role": "lead",
            "vendor": "meridian",
            "observation_confidence": "direct",
            "input": json.dumps(
                {"method": "gate.approve", "subject": subject, "commit": commit}
            ),
        }
    )
    return result.sequence


# -- FR-M42-01: the binding itself ---------------------------------------------


class TestAuthorisationBinding:
    def test_binds_every_fr_m42_01_element(self, authorisation):
        # FR-M42-01: repository, PR identity, base+head, diff digest,
        # policy version, evidence set, authenticated approver, expiry.
        assert authorisation.repository == REPOSITORY
        assert authorisation.subject == SUBJECT
        assert authorisation.base_commit == BASE
        assert authorisation.head_commit == HEAD
        assert authorisation.diff_digest == DIGEST
        assert authorisation.policy_version == POLICY_VERSION
        assert authorisation.evidence == tuple(sorted(EVIDENCE))
        assert authorisation.approver == "Ada Lovelace <ada@example.com>"
        assert authorisation.approved_by_class == "human_individual"
        assert authorisation.expires_at == EXPIRES

    def test_payload_binds_every_field_into_the_signature(self, keys):
        # The signature must cover the bound fields and nothing else:
        # re-signing the payload with the same key reproduces validity.
        auth = issue(keys)
        assert merge_authorisation.verify_signature(auth) is True
        assert merge_authorisation.verify_signature(
            merge_authorisation.MergeAuthorisation(
                version=auth.version,
                repository=auth.repository,
                subject=auth.subject,
                base_commit=auth.base_commit,
                head_commit=auth.head_commit,
                diff_digest=auth.diff_digest,
                policy_version=auth.policy_version,
                evidence=auth.evidence,
                approver=auth.approver,
                approved_by_class=auth.approved_by_class,
                issued_at=auth.issued_at,
                expires_at=auth.expires_at,
                signature=auth.signature,
                signer_public_key=auth.signer_public_key,
            )
        ) is True

    def test_signed_with_the_ledger_key_pattern(self, keys):
        # Reuse of the ledger signing pattern (N2-T02): the token
        # verifies against the signer's public key like a tree head.
        auth = issue(keys)
        from meridian_core.ledger.keys import public_key_bytes

        assert auth.signer_public_key == public_key_bytes(keys.private_key())
        assert merge_authorisation.verify_signature(auth) is True

    def test_unknown_key_fails_verification(self, keys):
        stranger = EphemeralSigningKeyProvider()
        auth = issue(keys)
        tampered = merge_authorisation.MergeAuthorisation(
            **{**auth.__dict__, "signer_public_key": public_key_of(stranger)}
        )
        assert merge_authorisation.verify_signature(tampered) is False

    def test_wire_roundtrip_preserves_the_binding(self, authorisation):
        decoded = merge_authorisation.MergeAuthorisation.from_wire(
            authorisation.to_wire()
        )
        assert decoded == authorisation
        assert merge_authorisation.verify_signature(decoded) is True

    def test_wire_rejects_malformed_objects(self):
        with pytest.raises(ValueError):
            merge_authorisation.MergeAuthorisation.from_wire({"version": "m42-1"})

    def test_unsupported_version_fails_closed(self, keys):
        auth = issue(keys)
        future = merge_authorisation.MergeAuthorisation(
            **{**auth.__dict__, "version": "m42-99"}
        )
        verdict = merge_authorisation.evaluate_authorisation(future, presented())
        assert verdict.allowed is False
        assert verdict.violated == ("signature",)

    def test_default_ttl_issues_a_lease(self, keys):
        auth = merge_authorisation.issue_authorisation(
            keys,
            repository=REPOSITORY,
            subject=SUBJECT,
            base_commit=BASE,
            head_commit=HEAD,
            digest=DIGEST,
            policy_version=POLICY_VERSION,
            evidence=EVIDENCE,
            approver="Ada <ada@example.com>",
            approved_by_class="human_individual",
            issued_at=ISSUED,
            expires_at=None,
        )
        assert auth.expires_at > ISSUED


def public_key_of(provider) -> bytes:
    from meridian_core.ledger.keys import public_key_bytes

    return public_key_bytes(provider.private_key())


# -- FR-M42-02: the invalidation matrix ----------------------------------------


class TestInvalidation:
    def test_unchanged_binding_is_allowed(self, authorisation):
        verdict = merge_authorisation.evaluate_authorisation(
            authorisation, presented()
        )
        assert verdict.allowed is True
        assert verdict.violated == ()

    def test_force_push_invalidates_head_commit(self, authorisation):
        verdict = merge_authorisation.evaluate_authorisation(
            authorisation, presented(head_commit=HEAD_FORCE_PUSHED)
        )
        assert verdict.allowed is False
        assert verdict.violated == ("head_commit",)
        assert any("head_commit" in note for note in verdict.notes)

    def test_rebase_invalidates_diff_digest(self, authorisation):
        # Same tree endpoint, different content history: the diff the
        # approver read is not the diff that would land.
        verdict = merge_authorisation.evaluate_authorisation(
            authorisation, presented(diff_digest=REBASED_DIGEST)
        )
        assert verdict.allowed is False
        assert verdict.violated == ("diff_digest",)

    def test_changed_base_invalidates_base_commit(self, authorisation):
        verdict = merge_authorisation.evaluate_authorisation(
            authorisation, presented(base_commit="B" * 40)
        )
        assert verdict.allowed is False
        assert verdict.violated == ("base_commit",)

    def test_changed_policy_version_invalidates(self, authorisation):
        verdict = merge_authorisation.evaluate_authorisation(
            authorisation, presented(policy_version="governance/v3")
        )
        assert verdict.allowed is False
        assert verdict.violated == ("policy_version",)

    def test_expired_authorisation_invalidates(self, authorisation):
        verdict = merge_authorisation.evaluate_authorisation(
            authorisation, presented(now=TOO_LATE)
        )
        assert verdict.allowed is False
        assert verdict.violated == ("expires_at",)

    def test_replay_on_a_different_pr_invalidates_subject(self, authorisation):
        # The same validly-signed approval replayed against a different
        # PR binding: the signature verifies, the binding does not.
        replayed = presented(subject="pr:acme/widget#43")
        verdict = merge_authorisation.evaluate_authorisation(authorisation, replayed)
        assert verdict.allowed is False
        assert "subject" in verdict.violated

    def test_replay_on_a_different_repository_invalidates(self, authorisation):
        replayed = presented(repository="git.example.com/acme/other")
        verdict = merge_authorisation.evaluate_authorisation(authorisation, replayed)
        assert verdict.allowed is False
        assert "repository" in verdict.violated

    def test_missing_evidence_invalidates(self, authorisation):
        verdict = merge_authorisation.evaluate_authorisation(
            authorisation, presented(evidence=frozenset({"tests:run-100"}))
        )
        assert verdict.allowed is False
        assert verdict.violated == ("evidence",)
        assert any("security-scan:sast-7" in note for note in verdict.notes)

    def test_extra_evidence_does_not_invalidate(self, authorisation):
        # A PR may gain evidence after approval; losing covered evidence
        # may not.
        verdict = merge_authorisation.evaluate_authorisation(
            authorisation,
            presented(evidence=frozenset((*EVIDENCE, "review:manual"))),
        )
        assert verdict.allowed is True

    def test_tampered_field_fails_signature_first(self, authorisation):
        tampered = merge_authorisation.MergeAuthorisation(
            **{**authorisation.__dict__, "head_commit": HEAD_FORCE_PUSHED}
        )
        verdict = merge_authorisation.evaluate_authorisation(tampered, presented())
        assert verdict.allowed is False
        assert verdict.violated == ("signature",)

    def test_multiple_violations_are_all_named(self, authorisation):
        verdict = merge_authorisation.evaluate_authorisation(
            authorisation,
            presented(head_commit=HEAD_FORCE_PUSHED, base_commit="B" * 40, now=TOO_LATE),
        )
        assert verdict.allowed is False
        assert set(verdict.violated) == {"head_commit", "base_commit", "expires_at"}


# -- consumed at merge evaluation (merge_gate.check_merge) ----------------------


class TestMergeGateConsumption:
    def approve_and_present(self, ledger, keys, **binding_overrides):
        append_approval(ledger, SUBJECT, HEAD)
        auth = issue(keys)
        return auth, presented(**binding_overrides)

    def test_unchanged_valid_pr_merges(self, ledger, pack, keys):
        auth, binding = self.approve_and_present(ledger, keys)
        verdict = merge_gate.check_merge(
            ledger,
            pack,
            subject=SUBJECT,
            head_commit=HEAD,
            requires_approval=True,
            authorisation=auth,
            binding=binding,
        )
        assert verdict.allowed is True
        assert verdict.status == "approved"

    def test_no_authorisation_path_unchanged(self, ledger, pack, keys):
        # The v1 approval-only path (no authorisation presented) is
        # untouched: FR-M42-01 binds additionally, not instead.
        del keys
        append_approval(ledger, SUBJECT, HEAD)
        verdict = merge_gate.check_merge(
            ledger, pack, subject=SUBJECT, head_commit=HEAD, requires_approval=True
        )
        assert verdict.allowed is True

    @pytest.mark.parametrize(
        ("override", "field"),
        [
            ({"head_commit": HEAD_FORCE_PUSHED}, "head_commit"),
            ({"diff_digest": REBASED_DIGEST}, "diff_digest"),
            ({"base_commit": "B" * 40}, "base_commit"),
            ({"policy_version": "governance/v3"}, "policy_version"),
            ({"now": TOO_LATE}, "expires_at"),
            ({"subject": "pr:acme/widget#43"}, "subject"),
            ({"evidence": frozenset({"tests:run-100"})}, "evidence"),
        ],
    )
    def test_each_change_blocks_merge_naming_the_field(
        self, ledger, pack, keys, override, field
    ):
        auth, binding = self.approve_and_present(ledger, keys, **override)
        verdict = merge_gate.check_merge(
            ledger,
            pack,
            subject=SUBJECT,
            head_commit=override.get("head_commit", HEAD),
            requires_approval=True,
            authorisation=auth,
            binding=binding,
        )
        assert verdict.allowed is False, field
        assert any(field in note for note in verdict.missing), verdict.missing

    def test_authorisation_without_binding_blocks(self, ledger, pack, keys):
        append_approval(ledger, SUBJECT, HEAD)
        auth = issue(keys)
        verdict = merge_gate.check_merge(
            ledger,
            pack,
            subject=SUBJECT,
            head_commit=HEAD,
            requires_approval=True,
            authorisation=auth,
            binding=None,
        )
        assert verdict.allowed is False
        assert any("authorisation" in note for note in verdict.missing)

    def test_binding_without_authorisation_blocks(self, ledger, pack, keys):
        del keys
        append_approval(ledger, SUBJECT, HEAD)
        verdict = merge_gate.check_merge(
            ledger,
            pack,
            subject=SUBJECT,
            head_commit=HEAD,
            requires_approval=True,
            authorisation=None,
            binding=presented(),
        )
        assert verdict.allowed is False
        assert any("authorisation" in note for note in verdict.missing)

    def test_replayed_approval_on_another_pr_blocks(self, ledger, pack, keys):
        # The approval and authorisation for PR #42 replayed against
        # PR #43's binding: both the ledger approval (subject mismatch)
        # and the authorisation (subject mismatch) refuse.
        auth, binding = self.approve_and_present(ledger, keys, subject="pr:acme/widget#43")
        verdict = merge_gate.check_merge(
            ledger,
            pack,
            subject="pr:acme/widget#43",
            head_commit=HEAD,
            requires_approval=True,
            authorisation=auth,
            binding=binding,
        )
        assert verdict.allowed is False
        assert any("subject" in note for note in verdict.missing)
