"""Signed audit bundle assembly (FR-M36-04, SEC-29, FR-M12-11; F0-E task 25).

The full bundle, replacing the Workstream-B placeholder:

- **entries** for any sequence range / date range / agent / story filter,
  each carrying its exact ``hashPayload`` — the JSON-native preimage of
  its ``entry_hash`` — so a third party recomputes hashes byte-for-byte
  with no schema knowledge;
- a **signed tree head** at the ledger tip (emitted on demand when the
  cadence has not produced one covering the range end);
- **Merkle inclusion proofs** (RFC 6962 §2.1.1) anchoring every included
  entry into the tree the signed head commits to;
- a **signature block**: Ed25519 over the SHA-256 digest of the canonical
  JSON of the whole bundle minus the block itself — any field tampered
  with anywhere invalidates the digest;
- the **compliance section** mapping bundle fields to NIST SSDF, ISO/IEC
  42001 and EU AI Act Article 12 (compliance.py).

Verification needs only this bundle (see verifier/, FR-M36-06): the
public key travels inside it (SEC-29 — no trust in Meridian's servers).
"""

from __future__ import annotations

import base64
import hashlib
from typing import Any

from . import canonical, compliance, merkle, schema, wire
from .core import utc_now

#: Export cap per call; ranges larger than this are exported in slices.
EXPORT_LIMIT = 10_000


def _redaction_section() -> dict[str, Any]:
    """What content capture was in force, and what the labels mean.

    FR-M43-13. Without this a reader cannot tell an absent field from a
    withheld one, and the two have opposite meanings: one says nothing
    happened, the other says something happened and was deliberately not
    recorded. The marker is included verbatim so a reader can search for it
    rather than having to know it.
    """
    from . import privacy, redaction

    return {
        "defaultProfile": privacy.DEFAULT_PROFILE,
        "redactedMarker": redaction.REDACTED,
        "profiles": {
            name: {
                "capturesInput": profile.capture_input,
                "capturesOutput": profile.capture_output,
                "redactsSecrets": profile.redact,
                "requiresConsent": profile.requires_consent,
                "captures": list(profile.captures),
            }
            for name, profile in sorted(privacy.COLLECTION_PROFILES.items())
        },
        "note": (
            "A field absent from an entry was either never produced or not "
            "captured under the profile in force; a field containing the "
            "redacted marker was produced and deliberately withheld. These "
            "are different facts and the distinction is not recoverable from "
            "the entries alone."
        ),
    }


def _enforcement_section() -> dict[str, Any]:
    """FR-M42-12: every control's effective enforcement point, from the
    governance registry. Imported lazily to keep the ledger package
    free of a governance dependency at module load."""
    from ..governance import enforcement_points

    return enforcement_points.enforcement_section()


def build_bundle(ledger: Any, params: dict[str, Any]) -> dict[str, Any]:
    """Assemble the full wire bundle for the given filters."""
    params = params or {}
    from_seq = params.get("fromSequence") or 1
    to_seq = min(params.get("toSequence") or ledger.last_sequence, ledger.last_sequence)

    rows: list[dict[str, Any]] = []
    if to_seq >= from_seq and to_seq > 0:
        # query_all, not query: a bundle whose range says 1..N must contain
        # every entry in it. One page (<= 1,000 rows) silently cut the rest.
        rows = ledger.query_all(
            story_id=params.get("storyId"),
            actor_id=params.get("agentId"),
            from_sequence=from_seq,
            to_sequence=to_seq,
            from_timestamp=params.get("fromTimestamp"),
            to_timestamp=params.get("toTimestamp"),
        )

    # A signed head must cover the range end; emit one at the tip if the
    # cadence has not produced one yet (FR-M10-04).
    head_row = ledger.latest_tree_head()
    head_wire = None
    if ledger.last_sequence and (head_row is None or head_row["seq"] < to_seq):
        head_wire = ledger.emit_tree_head_now()  # already wire shape
    elif head_row is not None:
        head_wire = wire.tree_head_to_wire(head_row)

    leaves = ledger.leaf_hashes()
    inclusion = [
        {
            "sequence": row["seq"],
            "leafIndex": row["seq"] - 1,
            "path": [node.hex() for node in merkle.inclusion_proof(leaves, row["seq"] - 1)],
        }
        for row in rows
    ]

    bundle: dict[str, Any] = {
        "formatVersion": 1,
        # FR-M43-13: a customer who leaves keeps readable records, which needs
        # more than the bundle's own format version. `schemaVersion` is the
        # ledger schema the entries were written under — the shape of an entry
        # changed across versions, so a reader without it has to guess which
        # one it is holding. `redaction` says what content capture was in
        # force, which is the difference between "this field is absent because
        # nothing happened" and "this field is absent because policy said not
        # to record it". Both were missing, and neither is recoverable later.
        "schemaVersion": schema.SCHEMA_VERSION,
        "redaction": _redaction_section(),
        "generatedAt": utc_now(),
        "signer": {
            "algorithm": "Ed25519",
            "publicKey": base64.b64encode(ledger.signing_public_key).decode(),
        },
        **({"treeHead": head_wire} if head_wire is not None else {}),
        "range": {"fromSequence": from_seq, "toSequence": to_seq},
        "filter": {
            key: value
            for key, value in (
                ("storyId", params.get("storyId")),
                ("agentId", params.get("agentId")),
                ("fromTimestamp", params.get("fromTimestamp")),
                ("toTimestamp", params.get("toTimestamp")),
            )
            if value is not None
        },
        "entries": [wire.row_to_bundle_entry(row) for row in rows],
        # FR-M42-12 / FR-M12-11: the effective enforcement point of every
        # control, so a reviewer holding only this bundle can state, per
        # decision, what could have bypassed it and who could have done so.
        "enforcement": _enforcement_section(),
        "proofs": {
            "treeSize": len(leaves),
            "rootHash": ledger.root_hash().hex(),
            "inclusion": inclusion,
        },
        "compliance": compliance.compliance_section(),
    }

    # Signature block: digest the canonical bundle core (bundle minus this
    # block), then sign the 32 digest bytes with the ledger key. Any later
    # tamper with any field invalidates the digest; the public key in the
    # bundle verifies it without trusting Meridian (SEC-29).
    digest = hashlib.sha256(canonical.canonical_json(bundle)).digest()
    bundle["signature"] = {
        "algorithm": "Ed25519",
        "signedAt": bundle["generatedAt"],
        "digest": digest.hex(),
        "signature": ledger.sign(digest).hex(),
    }
    return bundle
