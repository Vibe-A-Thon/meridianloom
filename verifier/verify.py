#!/usr/bin/env python3
"""meridian-verify — the open reference verifier for Meridian audit bundles.

FR-M36-06 / NFR-31 / SEC-29 (F0 Workstream E task 26): validates a bundle
produced by ledger.exportBundle on a machine with nothing installed —
single file, Python standard library only (Ed25519 verification is a pure
Python implementation of RFC 8032, so no cryptography dependency exists).

Usage:
    python verify.py <bundle.json>
    python verify.py -            (read the bundle from stdin)
    meridian-verify <bundle.json> (the Rust twin, verifier/, identical checks)

Exit 0 and a one-line summary on stdout when the bundle verifies; exit 1
with one actionable line per problem on stderr otherwise. The verification
algorithm is normative and documented in docs/open-ledger-spec/.

What is checked, with only the bundle's own material:
  1. shape      — the v1 schema fields decode (hex digests, base64 key);
  2. chain      — every entry hash recomputes from its hashPayload under
                  the canonical JSON rules, and entries link head-to-tail;
  3. inclusion  — RFC 6962 §2.1.1 proofs anchor each entry into the Merkle
                  tree the signed tree head commits to;
  4. tree head  — the Ed25519 tree-head signature verifies against the
                  public key bundled inside (no trust in Meridian's
                  servers — SEC-29);
  5. signature  — the bundle signature covers the canonical JSON of every
                  other field, so any tampering anywhere is detected.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import sys
from typing import Any

# -- canonical JSON (must match core/meridian_core/ledger/canonical.py) -------


def canonical_json(value: Any) -> bytes:
    """JSON, keys sorted, UTF-8, no insignificant whitespace (§7.2 of the
    open ledger spec). NaN/Infinity are refused."""
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


# -- SHA-256 helpers -----------------------------------------------------------


def sha256(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


# -- Merkle tree (RFC 6962 §2.1 / RFC 9162 §2.1.3.2, as ledger/merkle.py) -----

_LEAF_PREFIX = b"\x00"
_NODE_PREFIX = b"\x01"


def _leaf_hash(data: bytes) -> bytes:
    return sha256(_LEAF_PREFIX + data)


def _node_hash(left: bytes, right: bytes) -> bytes:
    return sha256(_NODE_PREFIX + left + right)


def verify_inclusion(
    index: int, leaf_payload: bytes, tree_size: int, path: list[bytes], root: bytes
) -> bool:
    """RFC 9162 §2.1.3.2 reference inclusion verification."""
    if not 0 <= index < tree_size:
        return False
    fn, sn = index, tree_size - 1
    r = _leaf_hash(leaf_payload)
    for p in path:
        if sn == 0:
            return False
        if fn & 1 or fn == sn:
            r = _node_hash(p, r)
            if not fn & 1:
                while not fn & 1 and fn != 0:
                    fn >>= 1
                    sn >>= 1
        else:
            r = _node_hash(r, p)
        fn >>= 1
        sn >>= 1
    return sn == 0 and r == root


# -- Ed25519 (RFC 8032, pure Python — no third-party dependency) --------------

_P = 2**255 - 19
_L = 2**252 + 27742317777372353535851937790883648493
_D = (-121665 * pow(121666, _P - 2, _P)) % _P
_I = pow(2, (_P - 1) // 4, _P)


def _xrecover(y: int) -> int:
    xx = (y * y - 1) * pow(_D * y * y + 1, _P - 2, _P) % _P
    x = pow(xx, (_P + 3) // 8, _P)
    if (x * x - xx) % _P != 0:
        x = (x * _I) % _P
    if x % 2 != 0:
        x = _P - x
    return x


_BY = (4 * pow(5, _P - 2, _P)) % _P
_B = (_xrecover(_BY), _BY)


def _edwards_add(p: tuple[int, int], q: tuple[int, int]) -> tuple[int, int]:
    x1, y1 = p
    x2, y2 = q
    x3 = (x1 * y2 + x2 * y1) * pow(1 + _D * x1 * x2 * y1 * y2, _P - 2, _P) % _P
    y3 = (y1 * y2 + x1 * x2) * pow(1 - _D * x1 * x2 * y1 * y2, _P - 2, _P) % _P
    return (x3, y3)


def _scalarmult(point: tuple[int, int], scalar: int) -> tuple[int, int]:
    result = (0, 1)
    addend = point
    while scalar:
        if scalar & 1:
            result = _edwards_add(result, addend)
        addend = _edwards_add(addend, addend)
        scalar >>= 1
    return result


def _decode_point(raw: bytes) -> tuple[int, int] | None:
    if len(raw) != 32:
        return None
    y = int.from_bytes(raw, "little") & ((1 << 255) - 1)
    if y >= _P:
        return None
    x = _xrecover(y)
    if x & 1 != raw[31] >> 7:
        x = _P - x
    if (y * y - x * x - 1 - _D * x * x * y * y) % _P != 0:
        return None
    return (x, y)


def ed25519_verify(public_key: bytes, signature: bytes, message: bytes) -> bool:
    """RFC 8032 verification: [S]B = R + [k]A with k = H(R||A||M) mod L."""
    if len(public_key) != 32 or len(signature) != 64:
        return False
    point_r = _decode_point(signature[:32])
    point_a = _decode_point(public_key)
    if point_r is None or point_a is None:
        return False
    s = int.from_bytes(signature[32:], "little")
    if s >= _L:
        return False
    k = int.from_bytes(
        hashlib.sha512(signature[:32] + public_key + message).digest(), "little"
    ) % _L
    return _scalarmult(_B, s) == _edwards_add(point_r, _scalarmult(point_a, k))


# -- bundle verification -------------------------------------------------------


def _hex_bytes(
    value: Any, what: str, problems: list[str], byte_length: int = 32
) -> bytes | None:
    if not isinstance(value, str) or len(value) != byte_length * 2:
        problems.append(
            f"{what} must be a {byte_length * 2}-character hex string"
            f" ({byte_length} bytes)"
        )
        return None
    try:
        return bytes.fromhex(value)
    except ValueError:
        problems.append(f"{what} is not valid hex")
        return None


def verify_bundle(bundle: Any) -> list[str]:
    """Every problem found; an empty list means the bundle verifies."""
    problems: list[str] = []

    def need(condition: bool, message: str) -> None:
        if not condition:
            problems.append(message)

    if not isinstance(bundle, dict):
        return ["bundle is not a JSON object"]

    need(bundle.get("formatVersion") == 1, "formatVersion must be 1")

    signer = bundle.get("signer") or {}
    public_key: bytes | None = None
    key_b64 = signer.get("publicKey")
    if not isinstance(key_b64, str):
        problems.append("signer.publicKey is missing or not a string")
    else:
        try:
            public_key = base64.b64decode(key_b64, validate=True)
        except (binascii.Error, ValueError):
            problems.append("signer.publicKey is not valid base64")
        else:
            need(len(public_key) == 32, "signer.publicKey must decode to 32 bytes")

    entries = bundle.get("entries")
    need(isinstance(entries, list), "entries must be an array")
    entries = entries if isinstance(entries, list) else []

    # 2. Chain continuity + per-entry hash recompute from hashPayload.
    previous_hash: bytes | None = None
    for position, entry in enumerate(entries):
        label = f"entry at position {position}"
        if not isinstance(entry, dict) or "sequence" not in entry:
            problems.append(f"{label}: missing sequence")
            continue
        label = f"entry {entry['sequence']}"
        entry_hash = _hex_bytes(entry.get("entryHash"), f"{label}.entryHash", problems)
        prev_hash = _hex_bytes(
            entry.get("previousHash"), f"{label}.previousHash", problems
        )
        payload = entry.get("hashPayload")
        need(isinstance(payload, dict), f"{label}: hashPayload must be an object")
        if (
            entry_hash is not None
            and prev_hash is not None
            and isinstance(payload, dict)
        ):
            recomputed = sha256(prev_hash + canonical_json(payload))
            need(
                recomputed == entry_hash,
                f"{label}: entryHash does not match its content (hashPayload "
                "was tampered with, or the entry was altered)",
            )
        if previous_hash is not None and prev_hash is not None:
            need(
                prev_hash == previous_hash,
                f"{label}: chain link broken — previousHash does not match the "
                "preceding entry's entryHash",
            )
        if entry_hash is not None:
            previous_hash = entry_hash

    # 3. Inclusion proofs anchor each entry into the signed tree.
    proofs = bundle.get("proofs") or {}
    tree_size = proofs.get("treeSize")
    root_hex = proofs.get("rootHash")
    root = _hex_bytes(root_hex, "proofs.rootHash", problems)
    need(isinstance(tree_size, int), "proofs.treeSize must be an integer")
    inclusion = proofs.get("inclusion")
    need(isinstance(inclusion, list), "proofs.inclusion must be an array")
    inclusion = inclusion if isinstance(inclusion, list) else []
    by_sequence = {e.get("sequence"): e for e in entries if isinstance(e, dict)}
    proven: set[Any] = set()
    for proof in inclusion:
        if not isinstance(proof, dict):
            problems.append("proofs.inclusion: item is not an object")
            continue
        sequence = proof.get("sequence")
        leaf_index = proof.get("leafIndex")
        entry = by_sequence.get(sequence)
        need(entry is not None, f"proof for unknown sequence {sequence}")
        path_hex = proof.get("path")
        need(isinstance(path_hex, list), f"proof {sequence}: path must be an array")
        if entry is None or not isinstance(path_hex, list):
            continue
        proven.add(sequence)
        path: list[bytes] = []
        path_ok = True
        for node in path_hex:
            decoded = _hex_bytes(node, f"proof {sequence}: path node", problems)
            if decoded is None:
                path_ok = False
                break
            path.append(decoded)
        if not path_ok:
            continue
        need(isinstance(leaf_index, int), f"proof {sequence}: leafIndex must be an integer")
        if (
            not isinstance(leaf_index, int)
            or not isinstance(tree_size, int)
            or root is None
            or not isinstance(entry.get("entryHash"), str)
        ):
            continue
        if not verify_inclusion(
            leaf_index,
            bytes.fromhex(entry["entryHash"]),
            tree_size,
            path,
            root,
        ):
            problems.append(
                f"entry {sequence}: Merkle inclusion proof does not verify"
            )
    for sequence in by_sequence:
        need(sequence in proven, f"entry {sequence}: no inclusion proof included")

    # 4. The signed tree head commits to that tree.
    head = bundle.get("treeHead")
    if entries:
        need(isinstance(head, dict), "treeHead is required when entries exist")
    if isinstance(head, dict) and public_key is not None:
        head_seq = head.get("seq")
        need(
            head_seq == tree_size,
            "treeHead.seq does not match proofs.treeSize",
        )
        need(
            head.get("rootHash") == root_hex,
            "treeHead.rootHash does not match proofs.rootHash",
        )
        head_sig = _hex_bytes(
            head.get("signature"), "treeHead.signature", problems, 64
        )
        if head_sig is not None and isinstance(head_seq, int):
            signed_at = head.get("signedAt")
            need(isinstance(signed_at, str), "treeHead.signedAt must be a string")
            if isinstance(signed_at, str) and isinstance(root, bytes):
                message = canonical_json(
                    {"root_hash": root.hex(), "seq": head_seq, "signed_at": signed_at}
                )
                need(
                    ed25519_verify(public_key, head_sig, message),
                    "treeHead signature does not verify with the bundled "
                    "public key",
                )

    # 5. The bundle signature covers every other field.
    signature = bundle.get("signature") or {}
    if public_key is not None:
        core = {key: value for key, value in bundle.items() if key != "signature"}
        try:
            digest = sha256(canonical_json(core))
        except ValueError as error:
            problems.append(f"bundle is not canonically serializable: {error}")
            digest = None
        declared = _hex_bytes(
            signature.get("digest"), "signature.digest", problems
        )
        if digest is not None and declared is not None:
            need(
                digest == declared,
                "signature.digest does not match the bundle content — a field "
                "was tampered with after signing",
            )
        sig = _hex_bytes(
            signature.get("signature"), "signature.signature", problems, 64
        )
        if sig is not None and digest is not None:
            need(
                ed25519_verify(public_key, sig, digest),
                "bundle signature does not verify with the bundled public key",
            )

    compliance = bundle.get("compliance")
    need(isinstance(compliance, dict), "compliance section is missing")
    if isinstance(compliance, dict):
        need(bool(compliance.get("standards")), "compliance.standards is empty")
        need(bool(compliance.get("mappings")), "compliance.mappings is empty")

    return problems


def main(argv: list[str]) -> int:
    if len(argv) > 2 or (len(argv) == 2 and argv[1] in ("-h", "--help")):
        print(__doc__.strip(), file=sys.stderr)
        return 2 if len(argv) > 2 else 0
    try:
        if len(argv) == 1 or argv[1] == "-":
            raw = sys.stdin.buffer.read()
        else:
            with open(argv[1], "rb") as handle:
                raw = handle.read()
    except OSError as error:
        print(f"cannot read bundle: {error}", file=sys.stderr)
        return 2
    try:
        bundle = json.loads(raw)
    except ValueError as error:
        print(f"bundle is not valid JSON: {error}", file=sys.stderr)
        return 2

    problems = verify_bundle(bundle)
    if problems:
        for problem in problems:
            print(f"FAIL: {problem}", file=sys.stderr)
        return 1
    entries = bundle.get("entries") or []
    head = bundle.get("treeHead") or {}
    print(
        "OK: bundle verifies — "
        f"{len(entries)} entries, tree size {head.get('seq', 0)}, "
        "chain, Merkle proofs, tree head and bundle signature all valid"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
