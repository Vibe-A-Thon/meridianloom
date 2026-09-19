"""FR-M42-01/02 (FUT-002; N2-T02/T03): the merge authorisation binding.

The merge gate's authorisation token (FR-M42-01): a signed, structured
object created when a human approves a PR and consumed when the merge is
evaluated. It binds, into one signed payload:

* the repository and the pull-request identity (``subject``),
* the base and head commit identifiers,
* the diff digest of the change under review,
* the policy version in force at approval,
* the test/security evidence set the approval covered,
* the authenticated approver identity and its approvedBy class
  (FR-M42-07/08), and
* an expiry — an authorisation is a lease, not a standing grant.

The signature is Ed25519 over the canonical JSON of the bound fields,
reusing the ledger's signing keys and canonicalisation
(:mod:`meridian_core.ledger.keys`, :mod:`meridian_core.ledger.canonical`) —
the same patterns tree heads use.

Invalidation (FR-M42-02): any change to a bound element invalidates the
authorisation. :func:`evaluate_authorisation` re-derives the violation
from the presented SCM state and names the violated field — a force-push
changes ``head_commit``, a rebase changes ``diff_digest``, a retarget
changes ``base_commit``, a policy rollout changes ``policy_version``,
lapsed time changes ``expires_at``, a replayed approval signature on a
different binding changes ``subject``/``repository``, and a dropped
evidence item changes ``evidence``. A tampered object fails
``signature`` first, so no field can be silently re-pointed.

D37: in v1 the binding is consumed inside Meridian (the SCM-native check
is REFUSED until a pilot customer exists); the enforcement point is
declared per FR-M42-11/12 in :mod:`meridian_core.governance.enforcement_points`.

Zero model calls (FR-M36-07): signing and evaluation are pure local
cryptography over caller-supplied values.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from ..ledger.canonical import canonical_json
from ..ledger.core import utc_now
from ..ledger.keys import (
    SIGNING_ALGORITHM,
    SigningKeyProvider,
    public_key_bytes,
)

#: Payload schema version. Bump when the bound-field set changes; an
#: evaluator MUST NOT accept a version it does not understand (a newer
#: object with an unbound field would otherwise verify against an
#: incomplete payload — fail closed instead).
AUTHORISATION_VERSION = "m42-1"

#: Canonical binding-field names, in evaluation order. The violated field
#: named in an invalidation note is always one of these (or "signature").
BOUND_FIELDS = (
    "repository",
    "subject",
    "base_commit",
    "head_commit",
    "diff_digest",
    "policy_version",
    "evidence",
    "expires_at",
)

#: Default authorisation lease. An approval is re-validated against the
#: live binding at merge time; the lease bounds how stale the approved
#: state may be before a fresh human look is required.
DEFAULT_TTL_SECONDS = 24 * 3600


@dataclass(frozen=True)
class MergeBinding:
    """The SCM state a merge would land in right now — the presented
    binding the authorisation is evaluated against.

    ``evidence`` is the evidence-set currently attached to the PR (test
    and security result references). ``now`` overrides the clock for
    expiry evaluation (tests); None means the wall clock.
    """

    repository: str
    subject: str
    base_commit: str
    head_commit: str
    diff_digest: str
    policy_version: str
    evidence: frozenset[str]
    now: str | None = None


@dataclass(frozen=True)
class MergeAuthorisation:
    """The signed FR-M42-01 authorisation token.

    Every field except ``signature`` and ``signer_public_key`` is bound
    into the signed payload; changing any of them invalidates the
    signature as well as the named-field check.
    """

    version: str
    repository: str
    subject: str
    base_commit: str
    head_commit: str
    diff_digest: str
    policy_version: str
    evidence: tuple[str, ...]
    approver: str
    approved_by_class: str
    issued_at: str
    expires_at: str
    signature: bytes
    signer_public_key: bytes

    def to_wire(self) -> dict[str, Any]:
        """JSON-safe transport shape (e.g. carried by the future SCM
        status-check payload, D37/T04)."""
        return {
            "version": self.version,
            "repository": self.repository,
            "subject": self.subject,
            "baseCommit": self.base_commit,
            "headCommit": self.head_commit,
            "diffDigest": self.diff_digest,
            "policyVersion": self.policy_version,
            "evidence": list(self.evidence),
            "approver": self.approver,
            "approvedByClass": self.approved_by_class,
            "issuedAt": self.issued_at,
            "expiresAt": self.expires_at,
            "signature": self.signature.hex(),
            "signerPublicKey": self.signer_public_key.hex(),
            "signingAlgorithm": SIGNING_ALGORITHM,
        }

    @staticmethod
    def from_wire(raw: dict[str, Any]) -> "MergeAuthorisation":
        """Decode :meth:`to_wire` output; malformed input is a ValueError,
        never a half-built object."""
        try:
            return MergeAuthorisation(
                version=str(raw["version"]),
                repository=str(raw["repository"]),
                subject=str(raw["subject"]),
                base_commit=str(raw["baseCommit"]),
                head_commit=str(raw["headCommit"]),
                diff_digest=str(raw["diffDigest"]),
                policy_version=str(raw["policyVersion"]),
                evidence=tuple(sorted(str(item) for item in raw["evidence"])),
                approver=str(raw["approver"]),
                approved_by_class=str(raw["approvedByClass"]),
                issued_at=str(raw["issuedAt"]),
                expires_at=str(raw["expiresAt"]),
                signature=bytes.fromhex(str(raw["signature"])),
                signer_public_key=bytes.fromhex(str(raw["signerPublicKey"])),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(f"malformed authorisation object: {error}") from error


def diff_digest(files: Iterable[tuple[str, str]]) -> str:
    """The FR-M42-01 diff digest: SHA-256 over the canonical JSON of the
    PR's ``(path, content-sha256)`` pairs. Content digests make the
    digest survive line-ending noise; any real change to the reviewed
    content changes it."""
    pairs = sorted((str(path), str(digest)) for path, digest in files)
    return hashlib.sha256(canonical_json({"files": pairs})).hexdigest()


def _payload(authorisation: MergeAuthorisation) -> dict[str, Any]:
    """The signed payload: every bound field, nothing else."""
    return {
        "version": authorisation.version,
        "repository": authorisation.repository,
        "subject": authorisation.subject,
        "base_commit": authorisation.base_commit,
        "head_commit": authorisation.head_commit,
        "diff_digest": authorisation.diff_digest,
        "policy_version": authorisation.policy_version,
        "evidence": list(authorisation.evidence),
        "approver": authorisation.approver,
        "approved_by_class": authorisation.approved_by_class,
        "issued_at": authorisation.issued_at,
        "expires_at": authorisation.expires_at,
    }


def issue_authorisation(
    provider: SigningKeyProvider,
    *,
    repository: str,
    subject: str,
    base_commit: str,
    head_commit: str,
    digest: str,
    policy_version: str,
    evidence: Iterable[str],
    approver: str,
    approved_by_class: str,
    issued_at: str | None = None,
    expires_at: str | None = None,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> MergeAuthorisation:
    """Create and sign the authorisation at approval time (FR-M42-01).

    ``issued_at``/``expires_at`` default to now / now + ``ttl_seconds``
    (the DEFAULT_TTL_SECONDS lease); pass explicit values for
    deterministic tests. The signer is the ledger's Ed25519 key — the
    same key that signs tree heads, so the token verifies against the
    ledger identity the audit bundle already publishes (SEC-29).
    """
    issued = issued_at or utc_now()
    if expires_at is None:
        moment = datetime.fromisoformat(issued.replace("Z", "+00:00"))
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        expires = moment.timestamp() + ttl_seconds
        expiry_dt = datetime.fromtimestamp(expires, tz=timezone.utc)
        expiry = expiry_dt.isoformat(timespec="microseconds").replace("+00:00", "Z")
    else:
        expiry = expires_at
    unsigned = MergeAuthorisation(
        version=AUTHORISATION_VERSION,
        repository=repository,
        subject=subject,
        base_commit=base_commit,
        head_commit=head_commit,
        diff_digest=digest,
        policy_version=policy_version,
        evidence=tuple(sorted({str(item) for item in evidence})),
        approver=approver,
        approved_by_class=approved_by_class,
        issued_at=issued,
        expires_at=expiry,
        signature=b"",
        signer_public_key=public_key_bytes(provider.private_key()),
    )
    signature = provider.private_key().sign(canonical_json(_payload(unsigned)))
    return MergeAuthorisation(
        version=unsigned.version,
        repository=unsigned.repository,
        subject=unsigned.subject,
        base_commit=unsigned.base_commit,
        head_commit=unsigned.head_commit,
        diff_digest=unsigned.diff_digest,
        policy_version=unsigned.policy_version,
        evidence=unsigned.evidence,
        approver=unsigned.approver,
        approved_by_class=unsigned.approved_by_class,
        issued_at=unsigned.issued_at,
        expires_at=unsigned.expires_at,
        signature=signature,
        signer_public_key=unsigned.signer_public_key,
    )


def verify_signature(authorisation: MergeAuthorisation) -> bool:
    """True when the signature covers the bound payload under the
    embedded public key. A tampered field fails here before any
    field-by-field check could be misled."""
    if authorisation.version != AUTHORISATION_VERSION:
        return False
    try:
        Ed25519PublicKey.from_public_bytes(authorisation.signer_public_key).verify(
            authorisation.signature,
            canonical_json(_payload(authorisation)),
        )
    except (InvalidSignature, ValueError):
        return False
    return True


def _parse_ts(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


@dataclass(frozen=True)
class AuthorisationVerdict:
    """The FR-M42-02 evaluation result. ``violated`` names the binding
    field(s) that no longer hold — the merge gate reports these names
    verbatim so the blocked merge carries a readable reason (AC-45)."""

    allowed: bool
    violated: tuple[str, ...]
    notes: tuple[str, ...]


def evaluate_authorisation(
    authorisation: MergeAuthorisation,
    binding: MergeBinding,
) -> AuthorisationVerdict:
    """Consume the authorisation against the presented SCM state
    (FR-M42-02). Every mismatch — force-push, rebase, retarget, policy
    rollout, expiry, replay, missing evidence — invalidates with the
    violated field named; only the fully unchanged binding passes."""
    violated: list[str] = []
    notes: list[str] = []

    if not verify_signature(authorisation):
        return AuthorisationVerdict(
            allowed=False,
            violated=("signature",),
            notes=(
                "authorisation invalidated: signature does not verify over the "
                "bound payload — the object was tampered with or signed by an "
                "unknown key",
            ),
        )

    def check(field: str, bound: Any, presented: Any) -> None:
        if bound != presented:
            violated.append(field)
            notes.append(
                f"authorisation invalidated: {field} changed "
                f"(bound {bound!r}, presented {presented!r})"
            )

    check("repository", authorisation.repository, binding.repository)
    check("subject", authorisation.subject, binding.subject)
    check("base_commit", authorisation.base_commit, binding.base_commit)
    check("head_commit", authorisation.head_commit, binding.head_commit)
    check("diff_digest", authorisation.diff_digest, binding.diff_digest)
    check("policy_version", authorisation.policy_version, binding.policy_version)

    missing_evidence = set(authorisation.evidence) - set(binding.evidence)
    if missing_evidence:
        violated.append("evidence")
        notes.append(
            "authorisation invalidated: evidence changed — the evidence the "
            f"approval covered is no longer all present (missing "
            f"{sorted(missing_evidence)!r})"
        )

    now = _parse_ts(binding.now) if binding.now else datetime.now(timezone.utc)
    try:
        expired = now >= _parse_ts(authorisation.expires_at)
    except ValueError:
        expired = True
    if expired:
        violated.append("expires_at")
        notes.append(
            f"authorisation invalidated: expires_at lapsed "
            f"(expired {authorisation.expires_at!r}, now {binding.now or 'now'!r})"
        )

    return AuthorisationVerdict(
        allowed=not violated,
        violated=tuple(violated),
        notes=tuple(notes),
    )
