"""FR-M43-09 / FR-M43-10 (N2 Workstream D task 20): versioned attestations
linking a commit, the policy decision behind it, reviewer assurance,
evidence, dependency digests and the ledger root — in an in-toto
-compatible envelope, with build provenance and agent activity as
**distinct predicates** (FR-M43-10).

Envelope layout (DSSE-style; the payload bytes are what is signed)::

    {
      "payloadType": "application/vnd.meridian.attestation.v1+json",
      "payload": "<base64 canonical JSON>",
      "signatures": [{"keyid": "<sha256 of raw ed25519 public key, hex>",
                      "sig": "<base64 raw 64-byte ed25519 signature>"}]
    }

Decoded payload::

    {
      "attestationVersion": 1,          # unknown versions raise, never mis-parse
      "attestationId": "<hex>",          # shared by every statement of one event
      "statements": [ <in-toto Statement v1>, ... ]
    }

Each statement is an in-toto Statement (``_type``
``https://in-toto.io/Statement/v1``) with ``subject`` identifiers kept
readable (FR-M43-09: source identifiers are preserved, not hashed away).
A single event with both build and agent aspects produces TWO statements
under one attestationId, with separate predicate types
``https://meridian.dev/predicates/build-provenance/v1`` and
``https://meridian.dev/predicates/agent-activity/v1`` — the two are never
merged (FR-M43-10).
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import uuid
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from meridian_core.ledger.canonical import canonical_json
from meridian_core.ledger.keys import public_key_bytes

PAYLOAD_TYPE = "application/vnd.meridian.attestation.v1+json"
ATTESTATION_VERSION = 1
STATEMENT_TYPE = "https://in-toto.io/Statement/v1"
BUILD_PROVENANCE_PREDICATE = "https://meridian.dev/predicates/build-provenance/v1"
AGENT_ACTIVITY_PREDICATE = "https://meridian.dev/predicates/agent-activity/v1"

SUPPORTED_ATTESTATION_VERSIONS = {ATTESTATION_VERSION}


class AttestationError(ValueError):
    """Malformed attestation envelope. Carries the requirement ID."""


class UnknownAttestationVersion(AttestationError):
    """NFR-39 analogue for attestations: refuse, never mis-parse."""


def key_id_for_public_key(public_key: bytes) -> str:
    """The DSSE ``keyid``: sha256 of the raw 32-byte Ed25519 public key."""
    if len(public_key) != 32:
        raise AttestationError("FR-M43-09: public key must be 32 raw bytes")
    return hashlib.sha256(public_key).hexdigest()


def _subject(name: str, digest: str) -> dict[str, Any]:
    # Source identifiers stay readable in the statement (FR-M43-09).
    return {"name": name, "digest": {"sha256": digest}}


def build_statements(
    *,
    attestation_id: str | None = None,
    commit: str,
    policy_decision: Mapping[str, Any],
    approvals: Sequence[Mapping[str, Any]] = (),
    evidence: Sequence[str] = (),
    dependency_digests: Mapping[str, str] | None = None,
    ledger_root: str,
    build_provenance: Mapping[str, Any] | None = None,
    agent_activity: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """The decoded payload: versioned, one or two in-toto statements.

    ``build_provenance`` and ``agent_activity`` are separate aspects. Both
    present -> two statements, one attestationId, distinct predicate types
    (FR-M43-10). Neither present -> AttestationError: an attestation must
    attest to something.
    """
    if build_provenance is None and agent_activity is None:
        raise AttestationError(
            "FR-M43-09: an attestation needs a build-provenance and/or an"
            " agent-activity aspect"
        )
    attestation_id = attestation_id or uuid.uuid4().hex
    common_subject = [
        _subject(
            f"git-commit:{commit}",
            hashlib.sha256(commit.encode("utf-8")).hexdigest(),
        ),
        _subject(
            f"ledger-root:{ledger_root}",
            hashlib.sha256(ledger_root.encode("utf-8")).hexdigest(),
        ),
    ]
    statements: list[dict[str, Any]] = []
    if build_provenance is not None:
        statements.append(
            {
                "_type": STATEMENT_TYPE,
                "subject": common_subject
                + [
                    _subject(name, digest)
                    for name, digest in sorted(
                        (dependency_digests or {}).items()
                    )
                ],
                "predicateType": BUILD_PROVENANCE_PREDICATE,
                "predicate": {
                    "attestationId": attestation_id,
                    "commit": commit,
                    "ledgerRoot": ledger_root,
                    "policyDecision": dict(policy_decision),
                    "builder": dict(build_provenance),
                },
            }
        )
    if agent_activity is not None:
        statements.append(
            {
                "_type": STATEMENT_TYPE,
                "subject": list(common_subject),
                "predicateType": AGENT_ACTIVITY_PREDICATE,
                "predicate": {
                    "attestationId": attestation_id,
                    "commit": commit,
                    "ledgerRoot": ledger_root,
                    "policyDecision": dict(policy_decision),
                    "reviewerAssurance": [dict(a) for a in approvals],
                    "evidence": list(evidence),
                    "activity": dict(agent_activity),
                },
            }
        )
    return {
        "attestationVersion": ATTESTATION_VERSION,
        "attestationId": attestation_id,
        "statements": statements,
    }


def sign_envelope(
    payload: dict[str, Any], private_key: Ed25519PrivateKey
) -> dict[str, Any]:
    """DSSE-sign the canonical-JSON-encoded payload."""
    payload_bytes = canonical_json(payload)
    signature = private_key.sign(payload_bytes)
    public_key = public_key_bytes(private_key)
    return {
        "payloadType": PAYLOAD_TYPE,
        "payload": base64.b64encode(payload_bytes).decode("ascii"),
        "signatures": [
            {
                "keyid": key_id_for_public_key(public_key),
                "sig": base64.b64encode(signature).decode("ascii"),
            }
        ],
    }


@dataclass(frozen=True)
class ParsedAttestation:
    """A verified-shape envelope, decoded. Trust comes from the keys."""

    payload: dict[str, Any]
    payload_bytes: bytes
    signatures: list[dict[str, str]]

    @property
    def attestation_id(self) -> str:
        return str(self.payload["attestationId"])

    @property
    def statements(self) -> list[dict[str, Any]]:
        return list(self.payload["statements"])

    def statements_by_predicate(self, predicate_type: str) -> list[dict[str, Any]]:
        return [
            s for s in self.statements if s.get("predicateType") == predicate_type
        ]


def parse_envelope(raw: bytes | str) -> ParsedAttestation:
    """Decode and version-check an envelope. Unknown versions raise
    UnknownAttestationVersion — never silently mis-parse (FR-M43-09)."""
    if isinstance(raw, str):
        raw = raw.encode("utf-8")
    try:
        envelope = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AttestationError(f"FR-M43-09: envelope is not JSON: {exc}")
    if envelope.get("payloadType") != PAYLOAD_TYPE:
        raise AttestationError(
            f"FR-M43-09: payloadType must be {PAYLOAD_TYPE!r}, got"
            f" {envelope.get('payloadType')!r}"
        )
    try:
        payload_bytes = base64.b64decode(envelope["payload"], validate=True)
    except (KeyError, binascii.Error, ValueError) as exc:  # type: ignore[name-defined]
        raise AttestationError(f"FR-M43-09: payload is not valid base64: {exc}")
    try:
        payload = json.loads(payload_bytes)
    except json.JSONDecodeError as exc:
        raise AttestationError(f"FR-M43-09: payload is not JSON: {exc}")
    version = payload.get("attestationVersion")
    if version not in SUPPORTED_ATTESTATION_VERSIONS:
        raise UnknownAttestationVersion(
            f"FR-M43-09: unsupported attestationVersion {version!r}; this"
            f" parser understands {sorted(SUPPORTED_ATTESTATION_VERSIONS)}"
        )
    signatures = envelope.get("signatures") or []
    if not signatures:
        raise AttestationError("FR-M43-09: envelope carries no signatures")
    return ParsedAttestation(
        payload=payload, payload_bytes=payload_bytes, signatures=signatures
    )


def verify_envelope(
    parsed: ParsedAttestation, trusted_keys: Mapping[str, bytes]
) -> bool:
    """True iff at least one signature verifies against a trusted keyid.

    ``trusted_keys`` maps keyid -> raw 32-byte Ed25519 public key, the same
    keyid scheme as :func:`sign_envelope`.
    """
    for signature in parsed.signatures:
        public_key = trusted_keys.get(signature.get("keyid", ""))
        if public_key is None:
            continue
        try:
            Ed25519PublicKey.from_public_bytes(public_key).verify(
                base64.b64decode(signature["sig"], validate=True),
                parsed.payload_bytes,
            )
        except (InvalidSignature, ValueError, KeyError):
            continue
        return True
    return False
