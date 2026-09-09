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

from . import canonical, compliance, merkle, wire
from .core import utc_now

#: Export cap per call; ranges larger than this are exported in slices.
EXPORT_LIMIT = 10_000


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
        rows = ledger.query(
            story_id=params.get("storyId"),
            actor_id=params.get("agentId"),
            from_sequence=from_seq,
            to_sequence=to_seq,
            from_timestamp=params.get("fromTimestamp"),
            to_timestamp=params.get("toTimestamp"),
            limit=EXPORT_LIMIT,
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
