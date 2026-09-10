"""FR-M43-02: independent verification reports THREE separate verdicts.

    valid_signature   — the bundle is internally sound: every entry hash
                        recomputes from its hashPayload, entries link
                        head-to-tail, inclusion proofs anchor entries into
                        the tree the signed head commits to, and the tree
                        head and bundle signatures verify against the
                        bundled public key. A changed entry or a broken
                        chain lands HERE.
    trusted_signer    — the bundled public key is in the verifier's
                        trusted set (signer enrolment history, see
                        receipts.py). An un-enrolled or revoked signer
                        fails HERE while the signature may still be
                        mathematically valid. None when no trusted set
                        was supplied — the verifier refuses to invent a
                        trust opinion.
    evidence_coverage — the evidence covers everything a witness saw.
                        Given receipts for previously witnessed roots:
                        a bundle presenting fewer entries than the
                        witness countersigned is rollback/truncation
                        (coverage fails); a bundle whose prefix does not
                        hash to the witnessed root is a fork or wholesale
                        replacement (coverage fails). CRUCIALLY, a
                        witness mismatch is reported as
                        ``valid_signature: True`` +
                        ``evidence_coverage: False``, NOT a signature
                        failure — the fork was re-signed honestly by
                        whoever holds the key.

FR-M43-03 / T15: with no receipts supplied, coverage is False with the
stated limitation (see `unwitnessed_limitation`): Meridian does not claim
to detect wholesale ledger replacement without a witness.

This module is the package-side twin of the open verifiers' verdict mode
(verifier/verify.py `--witness`, and meridian-verify's `--witness`): same
receipt shape, same three verdicts, same semantics.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
from dataclasses import dataclass
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from . import canonical, keys, merkle
from .receipts import (
    UNWITNESSED_LIMITATION,
    verify_receipt_tree_head,
    verify_witness_signature,
)


@dataclass(frozen=True)
class Verdicts:
    """FR-M43-02's three independent verdicts."""

    valid_signature: bool
    trusted_signer: bool | None
    evidence_coverage: bool
    detail: str = ""
    problems: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "valid_signature": self.valid_signature,
            "trusted_signer": self.trusted_signer,
            "evidence_coverage": self.evidence_coverage,
            "detail": self.detail,
            "problems": list(self.problems),
        }


def _hex(value: Any, length: int = 32) -> bytes | None:
    if not isinstance(value, str) or len(value) != length * 2:
        return None
    try:
        return bytes.fromhex(value)
    except ValueError:
        return None


def _bundled_public_key(bundle: dict[str, Any]) -> bytes | None:
    signer = bundle.get("signer") or {}
    key_b64 = signer.get("publicKey")
    if not isinstance(key_b64, str):
        return None
    try:
        raw = base64.b64decode(key_b64, validate=True)
    except (binascii.Error, ValueError):
        return None
    return raw if len(raw) == 32 else None


def _ed25519_verify(public_key: bytes, signature: bytes, message: bytes) -> bool:
    try:
        Ed25519PublicKey.from_public_bytes(public_key).verify(signature, message)
    except (InvalidSignature, ValueError):
        return False
    return True


def _valid_signature_problems(bundle: dict[str, Any]) -> list[str]:
    """Changed-entry / broken-chain / bad-signature detection, mirroring
    the open verifier's checks 2–5 (same messages, same semantics)."""
    problems: list[str] = []
    entries = bundle.get("entries")
    if not isinstance(entries, list):
        return ["entries must be an array"]

    previous_hash: bytes | None = None
    entry_hashes: list[bytes] = []
    for position, entry in enumerate(entries):
        label = f"entry {entry.get('sequence', position)}"
        entry_hash = _hex(entry.get("entryHash"))
        prev_hash = _hex(entry.get("previousHash"))
        payload = entry.get("hashPayload")
        if entry_hash is None:
            problems.append(f"{label}.entryHash is missing or malformed")
        if prev_hash is None:
            problems.append(f"{label}.previousHash is missing or malformed")
        if not isinstance(payload, dict):
            problems.append(f"{label}: hashPayload must be an object")
        elif entry_hash is not None and prev_hash is not None:
            recomputed = hashlib.sha256(
                prev_hash + canonical.canonical_json(payload)
            ).digest()
            if recomputed != entry_hash:
                problems.append(
                    f"{label}: entryHash does not match its content (hashPayload "
                    "was tampered with, or the entry was altered)"
                )
        if previous_hash is not None and prev_hash is not None and prev_hash != previous_hash:
            problems.append(
                f"{label}: chain link broken — previousHash does not match the "
                "preceding entry's entryHash"
            )
        if entry_hash is not None:
            previous_hash = entry_hash
            entry_hashes.append(entry_hash)

    proofs = bundle.get("proofs") or {}
    tree_size = proofs.get("treeSize")
    root = _hex(proofs.get("rootHash"))
    if not isinstance(tree_size, int):
        problems.append("proofs.treeSize must be an integer")
        tree_size = None
    if root is None:
        problems.append("proofs.rootHash is missing or malformed")
    inclusion = proofs.get("inclusion")
    if not isinstance(inclusion, list):
        problems.append("proofs.inclusion must be an array")
        inclusion = []
    by_sequence = {
        e.get("sequence"): e for e in entries if isinstance(e, dict)
    }
    proven: set[Any] = set()
    if tree_size is not None and root is not None:
        for proof in inclusion:
            if not isinstance(proof, dict):
                problems.append("proofs.inclusion: item is not an object")
                continue
            sequence = proof.get("sequence")
            entry = by_sequence.get(sequence)
            if entry is None:
                problems.append(f"proof for unknown sequence {sequence}")
                continue
            proven.add(sequence)
            leaf_index = proof.get("leafIndex")
            path_hex = proof.get("path")
            if not isinstance(leaf_index, int) or not isinstance(path_hex, list):
                problems.append(f"proof {sequence}: malformed leafIndex/path")
                continue
            path: list[bytes] = []
            for node in path_hex:
                decoded = _hex(node)
                if decoded is None:
                    path = []
                    break
                path.append(decoded)
            entry_hash = _hex(entry.get("entryHash"))
            if entry_hash is not None and not merkle.verify_inclusion(
                leaf_index, entry_hash, tree_size, path, root
            ):
                problems.append(
                    f"entry {sequence}: Merkle inclusion proof does not verify"
                )
    for sequence in by_sequence:
        if sequence not in proven:
            problems.append(f"entry {sequence}: no inclusion proof included")

    head = bundle.get("treeHead")
    public_key = _bundled_public_key(bundle)
    if entries:
        if not isinstance(head, dict):
            problems.append("treeHead is required when entries exist")
        elif public_key is not None and root is not None:
            head_seq = head.get("seq")
            head_sig = _hex(head.get("signature"), 64)
            signed_at = head.get("signedAt")
            if head_seq != tree_size:
                problems.append("treeHead.seq does not match proofs.treeSize")
            if _hex(head.get("rootHash")) != root:
                problems.append("treeHead.rootHash does not match proofs.rootHash")
            if not isinstance(head_seq, int) or head_sig is None or not isinstance(signed_at, str):
                problems.append("treeHead is malformed")
            elif not keys.verify_tree_head(
                public_key, head_seq, root, signed_at, head_sig
            ):
                problems.append(
                    "treeHead signature does not verify with the bundled public key"
                )

    signature = bundle.get("signature") or {}
    if public_key is not None:
        core = {k: v for k, v in bundle.items() if k != "signature"}
        try:
            digest = hashlib.sha256(canonical.canonical_json(core)).digest()
        except ValueError as error:
            problems.append(f"bundle is not canonically serializable: {error}")
            digest = None
        declared = _hex(signature.get("digest")) if isinstance(signature, dict) else None
        sig = (
            _hex(signature.get("signature"), 64)
            if isinstance(signature, dict)
            else None
        )
        if digest is not None and declared is not None and digest != declared:
            problems.append(
                "signature.digest does not match the bundle content — a field "
                "was tampered with after signing"
            )
        if digest is not None and sig is not None and not _ed25519_verify(
            public_key, sig, digest
        ):
            problems.append(
                "bundle signature does not verify with the bundled public key"
            )
    return problems


def _prefix_root(entry_hashes: list[bytes], count: int) -> bytes:
    """RFC 6962 root over the first `count` leaves (entry hashes)."""
    if count <= 0:
        return merkle.EMPTY_ROOT
    if count == len(entry_hashes):
        return merkle.root(entry_hashes)
    return merkle.root(entry_hashes[:count])


def _contiguous_prefix_length(entries: list[dict[str, Any]]) -> int:
    """How many entries form the gapless prefix 1..N (N is the deepest
    sequence the bundle's chain can speak for)."""
    prefix = 0
    for expected, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict) or entry.get("sequence") != expected:
            break
        prefix += 1
    return prefix


def verify_bundle_verdicts(
    bundle: dict[str, Any],
    *,
    receipts: list[dict[str, Any]] | None = None,
    trusted_keys: set[bytes] | None = None,
    trusted_witness_keys: set[bytes] | None = None,
) -> Verdicts:
    """Compute the three FR-M43-02 verdicts for an exported bundle.

    `receipts` — witness receipts (receipts.py shape) for previously
    witnessed roots. `trusted_keys` — raw Ed25519 public keys the
    verifier enrolled out of band; None means no opinion (trusted_signer
    is None). `trusted_witness_keys` — witness keys pinned out of band;
    a receipt whose embedded witness key is not pinned does NOT count
    towards coverage (the embedded key is self-asserted).
    """
    signature_problems = _valid_signature_problems(bundle)
    valid_signature = not signature_problems

    bundled_key = _bundled_public_key(bundle)
    if trusted_keys is None:
        trusted_signer: bool | None = None
    else:
        trusted_signer = bundled_key in trusted_keys if bundled_key else False

    coverage, coverage_detail = _evidence_coverage(
        bundle, receipts or [], trusted_witness_keys
    )

    return Verdicts(
        valid_signature=valid_signature,
        trusted_signer=trusted_signer,
        evidence_coverage=coverage,
        detail=coverage_detail,
        problems=tuple(signature_problems),
    )


def _evidence_coverage(
    bundle: dict[str, Any],
    receipts: list[dict[str, Any]],
    trusted_witness_keys: set[bytes] | None,
) -> tuple[bool, str]:
    if not receipts:
        return False, UNWITNESSED_LIMITATION

    entries = bundle.get("entries")
    entries = entries if isinstance(entries, list) else []
    entry_hashes: list[bytes] = []
    for entry in entries:
        digest = _hex(entry.get("entryHash")) if isinstance(entry, dict) else None
        if digest is None:
            return False, "bundle has malformed entries; coverage undetermined"
        entry_hashes.append(digest)
    prefix = _contiguous_prefix_length(entries)

    checked = 0
    for receipt in receipts:
        head = receipt.get("treeHead") or {}
        witnessed_seq = head.get("seq")
        if not isinstance(witnessed_seq, int) or witnessed_seq < 1:
            continue
        if not verify_receipt_tree_head(receipt):
            continue  # receipt for a head the ledger signer never signed
        witness = receipt.get("witness") or {}
        witness_key_b64 = witness.get("publicKey")
        unsigned_reception = "witnessSignature" not in receipt
        if unsigned_reception:
            # Local reception receipts (the default file store) record
            # that a root existed, without a detachable countersignature.
            # They count for rollback/fork coverage but are weaker: an
            # administrator of the receipt host could have deleted or
            # rewritten them. Coverage pinning does not apply.
            provenance = "reception receipt (unsigned, local store)"
        else:
            if not verify_witness_signature(receipt):
                continue
            if trusted_witness_keys is not None:
                try:
                    embedded = base64.b64decode(witness_key_b64 or "", validate=True)
                except (binascii.Error, ValueError, TypeError):
                    continue
                if embedded not in trusted_witness_keys:
                    continue  # self-asserted witness key, not pinned
            provenance = f"witness '{witness.get('id')}' countersignature"
        checked += 1
        if prefix < witnessed_seq:
            return (
                False,
                f"rollback/truncation: a root at sequence {witnessed_seq} was "
                f"recorded ({provenance}), but this bundle presents only "
                f"{prefix} contiguous entries from genesis",
            )
        witnessed_root = _hex(head.get("rootHash"))
        if witnessed_root is None:
            continue
        if _prefix_root(entry_hashes, witnessed_seq) != witnessed_root:
            return (
                False,
                "wholesale replacement or fork: entries "
                f"1..{witnessed_seq} of this bundle do not hash to the "
                f"recorded root {head.get('rootHash')} ({provenance})",
            )
        return True, (
            f"recorded root at sequence {witnessed_seq} ({provenance}); "
            "this bundle extends it"
        )
    if checked == 0:
        return (
            False,
            "no usable witness receipts (bad ledger signature, bad witness "
            "signature, or witness key not pinned); coverage undetermined",
        )
    return False, "witness receipts did not match this bundle's history"


def verdict_lines(verdicts: Verdicts) -> list[str]:
    """Human-readable three-verdict report (also emitted by the open
    verifiers' --witness mode; keep the wording in sync)."""
    lines = [
        f"VERDICT valid_signature: {'pass' if verdicts.valid_signature else 'FAIL'}",
        "VERDICT trusted_signer: "
        + (
            "pass"
            if verdicts.trusted_signer
            else ("FAIL" if verdicts.trusted_signer is False else "unknown (no trusted-key set supplied)")
        ),
        f"VERDICT evidence_coverage: {'pass' if verdicts.evidence_coverage else 'FAIL'}",
    ]
    if verdicts.detail:
        lines.append(f"coverage detail: {verdicts.detail}")
    if not verdicts.evidence_coverage and not verdicts.detail:
        lines.append(f"coverage detail: {UNWITNESSED_LIMITATION}")
    for problem in verdicts.problems:
        lines.append(f"signature problem: {problem}")
    return lines
