"""FR-M42-13/14 + SEC-35 (FUT-015; N2 Workstream C task T11): signed
policy bundles with activation, expiry and precedence, plus the emergency
revocation and the offline-hosted policy lease.

FR-M42-13: an organisation distributes policy as a **signed bundle** — the
workspace's policy pack text, the ledger's own Ed25519 key signing a
canonical digest of the pack plus the bundle metadata (activation time,
expiry, precedence). The bundle carries:

* ``activation`` — the ISO instant the bundle takes effect; before it the
  bundle is ``pending`` and the local pack still governs;
* ``expiry`` — the ISO instant the bundle lapses; after it the bundle is
  ``expired`` and the local pack governs again;
* ``precedence`` — an integer; an ACTIVE bundle with precedence >= 1
  overrides the local pack, and among active bundles the higher precedence
  wins (explicit precedence over local policy, newest-lapsing tie-break).

SEC-35: the signature is verified BEFORE a bundle can activate, and an
unverifiable bundle fails closed — :func:`evaluate_bundle` reports it
``invalid`` and :func:`select_policy` never applies it. Verification
recomputes the canonical signed payload from the bundle's own fields, so a
tampered pack text, metadata, signature or public key all fail.

FR-M42-14: an **emergency revocation** is a ``policy_bundle_revocation``
ledger row; like FR-M42-06 identity revocations (NFR-36) it takes effect
IMMEDIATELY in-process — every check below reads the ledger anew, so a
revocation committed by any handler binds the very next evaluation, well
inside the five-minute online bound (the bound is the outer envelope for
other replicas; in-process latency is one ledger read).

An **offline hosted run** stops when its **policy lease** expires: a lease
is issued against a bundle and expires with it; the hosted session's
checkpoint gate calls :func:`lease_checkpoint` at its turn boundary (the
same pause-at-checkpoint pattern as the FR-M39-02 spend ceiling). An
expired or revoked lease returns ``stop_*`` and the stop is
ledger-recorded once per lease — the run halts at the next checkpoint even
with no connectivity, because the check is a local clock read against the
lease, never a network call.

Zero model calls (FR-M36-07): canonicalisation, hashing, signature
verification and clock comparisons only.
"""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from ..ledger.canonical import canonical_json
from ..ledger.core import Ledger, utc_now
from .policy import PolicyPack, fail_closed_pack, parse_policy_pack

__all__ = [
    "BUNDLE_REVOCATION_ACTION",
    "BUNDLE_SCHEMA_VERSION",
    "BundleEvaluation",
    "LeaseCheck",
    "PolicyBundle",
    "PolicyLease",
    "PolicySelection",
    "evaluate_bundle",
    "issue_lease",
    "lease_checkpoint",
    "pack_sha256",
    "revoke_bundle",
    "revoked_bundle_ids",
    "select_policy",
    "sign_bundle",
    "bundle_from_dict",
    "bundle_to_dict",
    "fail_closed_selection",
]

#: Bundle schema version — recorded on every bundle and in the signed
#: payload so an old bundle is interpretable (and re-verifiable) without
#: this module.
BUNDLE_SCHEMA_VERSION = "policy-bundle/v1"

#: Ledger action_type of an emergency revocation row (FR-M42-14).
BUNDLE_REVOCATION_ACTION = "policy_bundle_revocation"

#: A precedence of 1 already overrides the local pack (the organisation's
#: distributed policy wins over a workspace default by default); higher
#: integers order multiple active bundles.
LOCAL_PRECEDENCE = 0


def _parse_instant(value: str) -> datetime | None:
    """An ISO-8601 instant, None when malformed (never a raise — policy
    content is validated into errors, fail-closed like the pack parser)."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def pack_sha256(pack_text: str) -> str:
    """The digest of the RAW pack text the signature commits to — signing
    the bytes, not a re-serialisation, so any edit of the file fails."""
    return hashlib.sha256(pack_text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class PolicyBundle:
    """One signed policy bundle (FR-M42-13)."""

    bundle_id: str
    pack_text: str  # the raw policy-pack YAML the signature commits to
    activation: str  # ISO instant the bundle takes effect
    expiry: str  # ISO instant the bundle lapses
    precedence: int  # >= 1 overrides the local pack while active
    signature: bytes  # Ed25519 over the canonical bundle payload
    public_key: bytes  # the signing key the verifier checks against

    def signed_payload(self) -> dict[str, Any]:
        """The canonical metadata the signature commits to. Recomputed
        from the bundle's OWN fields at verification (SEC-35) — nothing
        signed is taken on trust from outside the recompute."""
        return {
            "schemaVersion": BUNDLE_SCHEMA_VERSION,
            "bundleId": self.bundle_id,
            "packSha256": pack_sha256(self.pack_text),
            "activation": self.activation,
            "expiry": self.expiry,
            "precedence": self.precedence,
        }

    def signed_bytes(self) -> bytes:
        return canonical_json(self.signed_payload())


def sign_bundle(
    ledger: Ledger,
    *,
    bundle_id: str,
    pack_text: str,
    activation: str,
    expiry: str,
    precedence: int = 1,
) -> PolicyBundle:
    """Pack and sign a bundle with the ledger's Ed25519 key (FR-M42-13 —
    reuse of the ledger signing key, the same key the tree heads and audit
    bundle blocks are signed with)."""
    if not bundle_id.strip():
        raise ValueError("a bundle needs a non-empty bundle_id")
    bundle = PolicyBundle(
        bundle_id=bundle_id.strip(),
        pack_text=pack_text,
        activation=activation,
        expiry=expiry,
        precedence=int(precedence),
        signature=b"",
        public_key=ledger.signing_public_key,
    )
    return PolicyBundle(
        bundle_id=bundle.bundle_id,
        pack_text=bundle.pack_text,
        activation=bundle.activation,
        expiry=bundle.expiry,
        precedence=bundle.precedence,
        signature=ledger.sign(bundle.signed_bytes()),
        public_key=bundle.public_key,
    )


def bundle_to_dict(bundle: PolicyBundle) -> dict[str, Any]:
    """The transport/persistence shape: bytes become base64, the pack text
    rides verbatim (the signature commits to its exact bytes)."""
    return {
        "schemaVersion": BUNDLE_SCHEMA_VERSION,
        "bundleId": bundle.bundle_id,
        "packText": bundle.pack_text,
        "activation": bundle.activation,
        "expiry": bundle.expiry,
        "precedence": bundle.precedence,
        "signature": base64.b64encode(bundle.signature).decode("ascii"),
        "publicKey": base64.b64encode(bundle.public_key).decode("ascii"),
    }


def bundle_from_dict(raw: Mapping[str, Any]) -> PolicyBundle:
    """Inverse of :func:`bundle_to_dict`. Malformed payloads raise
    ValueError — a caller that cannot even decode a bundle treats it as
    unverifiable (SEC-35 fail closed), never as applicable."""
    try:
        return PolicyBundle(
            bundle_id=str(raw["bundleId"]),
            pack_text=str(raw["packText"]),
            activation=str(raw["activation"]),
            expiry=str(raw["expiry"]),
            precedence=int(raw["precedence"]),
            signature=base64.b64decode(str(raw["signature"]), validate=True),
            public_key=base64.b64decode(str(raw["publicKey"]), validate=True),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"not a policy bundle: {error}") from error


@dataclass(frozen=True)
class BundleEvaluation:
    """A bundle verified and placed on its activation timeline (SEC-35 +
    FR-M42-13). ``valid`` False means fail-closed: the bundle can never
    supply policy. ``status`` is ``pending`` | ``active`` | ``expired`` |
    ``invalid``."""

    bundle: PolicyBundle
    valid: bool
    status: str
    errors: tuple[str, ...] = ()
    pack: PolicyPack | None = None

    @property
    def applicable(self) -> bool:
        """May this bundle supply policy right now?"""
        return self.valid and self.status == "active"


def evaluate_bundle(bundle: PolicyBundle, *, now: str | None = None) -> BundleEvaluation:
    """Verify the signature (SEC-35) and place the bundle on its timeline.
    Every problem is an error and yields valid=False — an unverifiable,
    malformed or mis-ordered bundle NEVER activates."""
    errors: list[str] = []
    try:
        Ed25519PublicKey.from_public_bytes(bundle.public_key).verify(
            bundle.signature, bundle.signed_bytes()
        )
    except (InvalidSignature, ValueError) as error:
        errors.append(f"signature verification failed: {error!r}")

    pack = parse_policy_pack(bundle.pack_text, f"bundle:{bundle.bundle_id}")
    if pack.fail_closed:
        errors.extend(pack.errors)

    activation = _parse_instant(bundle.activation)
    expiry = _parse_instant(bundle.expiry)
    if activation is None:
        errors.append(f"activation '{bundle.activation}' is not an ISO-8601 instant")
    if expiry is None:
        errors.append(f"expiry '{bundle.expiry}' is not an ISO-8601 instant")
    if activation is not None and expiry is not None and expiry <= activation:
        errors.append("expiry must be after activation")

    valid = not errors
    status = "invalid"
    if valid:
        moment = _parse_instant(now) if now is not None else _parse_instant(utc_now())
        if moment is None:
            errors.append(f"now '{now}' is not an ISO-8601 instant")
            valid = False
        elif moment < activation:
            status = "pending"
        elif moment > expiry:
            status = "expired"
        else:
            status = "active"
    return BundleEvaluation(
        bundle=bundle,
        valid=valid,
        status=status,
        errors=tuple(errors),
        pack=pack if valid else None,
    )


# -- emergency revocation (FR-M42-14) -------------------------------------------


def revoke_bundle(
    ledger: Ledger,
    *,
    bundle_id: str,
    revoked_by: str | None = None,
    reason: str | None = None,
    revoked_at: str | None = None,
) -> int:
    """Append the emergency revocation row. Durable before return
    (FR-M10-08) and effective in-process from commit — the very next
    :func:`revoked_bundle_ids` read sees it (NFR-36 in-process latency:
    one ledger read, far inside the five-minute online bound)."""
    if not bundle_id.strip():
        raise ValueError("revocation needs a non-empty bundle_id")
    detail: dict[str, Any] = {
        "method": "policy.bundle.revoke",
        "bundleId": bundle_id.strip(),
        "revokedAt": revoked_at or utc_now(),
    }
    if revoked_by:
        detail["revokedBy"] = revoked_by
    if reason:
        detail["reason"] = reason
    result = ledger.append(
        {
            "story_id": f"policy-bundle:{bundle_id.strip()}",
            "phase": "review",
            "loop_id": "governance",
            "loop_iteration": 1,
            "actor_id": "governor",
            "actor_version": "0",
            "actor_kind": "meta",
            "policy_version": "governance/bundle/v1",
            "action_type": BUNDLE_REVOCATION_ACTION,
            "decision": "revoked",
            "vendor": "meridian",
            "observation_confidence": "direct",
            "input": json.dumps(detail, ensure_ascii=False),
        }
    )
    return result.sequence


def revoked_bundle_ids(ledger: Ledger, *, limit: int = 10_000) -> set[str]:
    """Currently-revoked bundle ids (v1 knows only ``revoked``; newest
    entry per bundle wins, so a future ``reinstated`` row clears it)."""
    revoked: set[str] = set()
    seen: set[str] = set()
    for row in reversed(ledger.query(action_type=BUNDLE_REVOCATION_ACTION, limit=limit)):
        ref = row.get("input_ref")
        key_id = row.get("blob_key_id")
        bundle_id = ""
        if ref and key_id:
            try:
                detail = json.loads(ledger.read_blob(ref, key_id).decode("utf-8"))
                bundle_id = str(detail.get("bundleId") or "")
            except (ValueError, KeyError, OSError):
                bundle_id = ""
        if not bundle_id or bundle_id in seen:
            continue
        seen.add(bundle_id)
        if row.get("decision") == "revoked":
            revoked.add(bundle_id)
    return revoked


# -- precedence selection (FR-M42-13) --------------------------------------------


@dataclass(frozen=True)
class PolicySelection:
    """Which policy governs right now, and honestly where it came from."""

    pack: PolicyPack
    source: str  # "local" or the winning bundle id
    policy_version: str
    note: str = ""


def select_policy(
    ledger: Ledger,
    *,
    local: PolicyPack,
    bundles: Sequence[PolicyBundle],
    now: str | None = None,
) -> PolicySelection:
    """The governing policy at ``now``: the applicable (verified, active,
    NOT revoked — revoked read fresh from the ledger, FR-M42-14) bundle
    with the highest precedence wins over the local pack; ties break on
    the lexicographically-greatest bundle id (deterministic). No
    applicable bundle: the local pack governs."""
    revoked = revoked_bundle_ids(ledger)
    candidates = [
        evaluation
        for evaluation in (evaluate_bundle(bundle, now=now) for bundle in bundles)
        if evaluation.applicable and evaluation.bundle.bundle_id not in revoked
    ]
    if not candidates:
        return PolicySelection(
            pack=local,
            source="local",
            policy_version=local.policy_version,
            note="no applicable signed bundle — the local pack governs",
        )
    winner = max(
        candidates,
        key=lambda evaluation: (
            evaluation.bundle.precedence,
            evaluation.bundle.bundle_id,
        ),
    )
    return PolicySelection(
        pack=winner.pack,
        source=winner.bundle.bundle_id,
        policy_version=winner.pack.policy_version,
        note=(
            f"signed bundle '{winner.bundle.bundle_id}' (precedence "
            f"{winner.bundle.precedence}) overrides local policy; verified "
            "per SEC-35, activation window honoured per FR-M42-13"
        ),
    )


# -- the offline-hosted policy lease (FR-M42-14) ---------------------------------


@dataclass(frozen=True)
class PolicyLease:
    """A hosted session's policy lease: the session may run only while
    the lease is unexpired and its bundle unrevoked. The lease expires
    WITH the bundle — an offline run stops when the wall clock passes
    ``expires_at``, no connectivity needed."""

    lease_id: str
    session_id: str
    bundle_id: str
    issued_at: str
    expires_at: str


def issue_lease(
    bundle: PolicyBundle,
    *,
    lease_id: str,
    session_id: str,
    issued_at: str | None = None,
) -> PolicyLease:
    """Issue the lease a hosted session runs under (FR-M42-14). The lease
    expires when the bundle does — the bundle's expiry IS the offline
    stop condition."""
    if not lease_id.strip() or not session_id.strip():
        raise ValueError("a lease needs non-empty lease and session ids")
    return PolicyLease(
        lease_id=lease_id.strip(),
        session_id=session_id.strip(),
        bundle_id=bundle.bundle_id,
        issued_at=issued_at or utc_now(),
        expires_at=bundle.expiry,
    )


@dataclass(frozen=True)
class LeaseCheck:
    """One checkpoint-gate decision for a hosted session."""

    decision: str  # "ok" | "stop_expired" | "stop_revoked"
    reason: str
    recorded_sequence: int | None = None


_LEASE_CHECKPOINT_ACTION = "policy_lease_checkpoint"


def lease_checkpoint(
    ledger: Ledger, lease: PolicyLease, *, now: str | None = None
) -> LeaseCheck:
    """The checkpoint-gate check a hosted session runs at its turn
    boundary (the FR-M39-02 pause-at-checkpoint pattern; the extension
    host owns the wire, this is the sidecar-side decision). A STOP is
    ledger-recorded once per lease — the halt is durable before the
    caller acts on it (FR-M10-08). An OK is not recorded (a checkpoint
    log per turn would be noise); the stop IS, because a stop is a
    governance event."""
    moment = _parse_instant(now) if now is not None else _parse_instant(utc_now())
    if lease.bundle_id in revoked_bundle_ids(ledger):
        return _record_stop(
            ledger, lease, "stop_revoked",
            f"policy bundle '{lease.bundle_id}' was revoked — the hosted "
            "session must stop at this checkpoint (FR-M42-14)",
        )
    expires = _parse_instant(lease.expires_at)
    if expires is None:
        return _record_stop(
            ledger, lease, "stop_expired",
            f"lease '{lease.lease_id}' carries an unparseable expiry "
            f"'{lease.expires_at}' — fail closed (SEC-35)",
        )
    if moment is not None and moment > expires:
        return _record_stop(
            ledger, lease, "stop_expired",
            f"policy lease '{lease.lease_id}' expired at {lease.expires_at} "
            "— the offline hosted run stops at this checkpoint (FR-M42-14)",
        )
    return LeaseCheck(decision="ok", reason="lease unexpired and bundle unrevoked")


def _record_stop(
    ledger: Ledger, lease: PolicyLease, decision: str, reason: str
) -> LeaseCheck:
    existing = [
        row
        for row in ledger.query(action_type=_LEASE_CHECKPOINT_ACTION, limit=10_000)
        if row.get("decision") == decision
        and _blob_detail(ledger, row).get("leaseId") == lease.lease_id
    ]
    if existing:
        return LeaseCheck(
            decision=decision,
            reason=reason,
            recorded_sequence=int(existing[-1]["seq"]),
        )
    result = ledger.append(
        {
            "story_id": f"policy-lease:{lease.lease_id}",
            "phase": "build",
            "loop_id": "acp-host",
            "loop_iteration": 1,
            "actor_id": "governor",
            "actor_version": "0",
            "actor_kind": "meta",
            "policy_version": "governance/bundle/v1",
            "action_type": _LEASE_CHECKPOINT_ACTION,
            "decision": decision,
            "vendor": "meridian",
            "observation_confidence": "direct",
            "external_session_id": lease.session_id,
            "input": json.dumps(
                {
                    "method": "policy.lease.checkpoint",
                    "leaseId": lease.lease_id,
                    "sessionId": lease.session_id,
                    "bundleId": lease.bundle_id,
                    "expiresAt": lease.expires_at,
                    "reason": reason,
                },
                ensure_ascii=False,
            ),
        }
    )
    return LeaseCheck(
        decision=decision, reason=reason, recorded_sequence=result.sequence
    )


def _blob_detail(ledger: Ledger, row: dict[str, Any]) -> dict[str, Any]:
    ref = row.get("input_ref")
    key_id = row.get("blob_key_id")
    if not ref or not key_id:
        return {}
    try:
        return json.loads(ledger.read_blob(ref, key_id).decode("utf-8"))
    except (ValueError, KeyError, OSError):
        return {}


def fail_closed_selection(reason: str) -> PolicySelection:
    """The selection that denies everything (a caller holding an
    unverifiable bundle with no local pack — SEC-35 fail closed)."""
    pack = fail_closed_pack("policy-bundle", [reason])
    return PolicySelection(
        pack=pack, source="fail-closed", policy_version=pack.policy_version, note=reason
    )
