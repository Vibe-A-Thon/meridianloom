#!/usr/bin/env python3
"""meridian-verify — the open reference verifier for Meridian audit bundles.

FR-M36-06 / NFR-31 / SEC-29 (F0 Workstream E task 26): validates a bundle
produced by ledger.exportBundle on a machine with nothing installed —
single file, Python standard library only (Ed25519 verification is a pure
Python implementation of RFC 8032, so no cryptography dependency exists).

Usage:
    python verify.py <bundle.json>
    python verify.py -            (read the bundle from stdin)
    python verify.py <bundle.json> --witness r1.json [--witness r2.json]
        --trusted-keys keys.txt [--trusted-witness-keys wkeys.txt]
    meridian-verify <bundle.json> [--witness ... --trusted-keys ...]
                                  (the Rust twin, verifier/, same checks)

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

FR-M43-02 / FR-M43-03 (N2 Workstream D task 14): with --witness and
--trusted-keys the verifier reports THREE SEPARATE VERDICTS instead of a
single pass/fail:

  VERDICT valid_signature    — checks 1-5 above (changed-entry detection
                               lands here);
  VERDICT trusted_signer     — the bundled public key is in the
                               --trusted-keys set (signer enrolment);
  VERDICT evidence_coverage  — the bundle extends every root recorded in
                               the --witness receipts (rollback/truncation
                               and wholesale-replacement detection land
                               HERE, not in the signature verdict). A
                               witness mismatch is therefore reported as
                               valid_signature: pass + evidence_coverage:
                               fail, never as a signature failure.

Without --witness the coverage verdict cannot pass, and the interface
says so (FR-M43-03 / T15): no witness, no claim of detecting wholesale
ledger replacement by a machine administrator.
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


# -- FR-M43-02: three independent verdicts ------------------------------------
#
# Kept deliberately separate from verify_bundle() above: the classic mode
# stays a single pass/fail, while --witness mode reports valid_signature,
# trusted_signer and evidence_coverage independently. Semantics are
# identical to core/meridian_core/ledger/witness.py and to the Rust
# verifier's verify_with_witness (verifier/src/lib.rs).

UNWITNESSED_LIMITATION = (
    "No witness receipts are configured. Without a witness, Meridian cannot "
    "claim to detect wholesale ledger replacement or rollback by a machine "
    "administrator: a re-signed fork of the ledger still verifies "
    "cryptographically. Changed-entry and chain-link tampering ARE detected "
    "by signature verification alone."
)


def _receipt_canonical_bytes(receipt: Any) -> bytes:
    body = {k: v for k, v in receipt.items() if k != "witnessSignature"}
    return canonical_json(body)


def verify_witness_signature(receipt: Any) -> bool:
    """The embedded witness signature verifies with the embedded witness
    public key (the key is self-asserted; pinning is the caller's job)."""
    if not isinstance(receipt, dict):
        return False
    signature = receipt.get("witnessSignature")
    witness = receipt.get("witness") or {}
    public_key = witness.get("publicKey")
    if not isinstance(signature, str) or not isinstance(public_key, str):
        return False
    try:
        key_bytes = base64.b64decode(public_key, validate=True)
        return ed25519_verify(
            key_bytes, bytes.fromhex(signature), _receipt_canonical_bytes(receipt)
        )
    except (ValueError, binascii.Error):
        return False


def verify_receipt_tree_head(receipt: Any) -> bool:
    """The receipt's embedded ledger tree-head signature verifies with the
    embedded ledger public key."""
    if not isinstance(receipt, dict):
        return False
    try:
        head = receipt["treeHead"]
        public_key = base64.b64decode(receipt["ledgerPublicKey"], validate=True)
        signature = bytes.fromhex(head["signature"])
        root_hash = bytes.fromhex(head["rootHash"])
        message = canonical_json(
            {
                "root_hash": head["rootHash"],
                "seq": head["seq"],
                "signed_at": head["signedAt"],
            }
        )
        return ed25519_verify(public_key, signature, message)
    except (KeyError, TypeError, ValueError, binascii.Error):
        return False


def _contiguous_prefix_length(entries: list[Any]) -> int:
    """How many entries form the gapless prefix 1..N."""
    prefix = 0
    for expected, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict) or entry.get("sequence") != expected:
            break
        prefix += 1
    return prefix


def _merkle_root(leaves: list[bytes]) -> bytes:
    """RFC 6962 tree hash over leaf payloads (entry hashes)."""
    if not leaves:
        return sha256(b"")
    if len(leaves) == 1:
        return _leaf_hash(leaves[0])
    # largest power of two < n
    split = 1 << (len(leaves).bit_length() - 1)
    if split == len(leaves):
        split >>= 1
    return _node_hash(_merkle_root(leaves[:split]), _merkle_root(leaves[split:]))


def _signature_problems(bundle: Any) -> list[str]:
    """Checks 1-5 of verify_bundle scoped to cryptographic validity
    (shape, chain, inclusion, tree head, bundle signature) — everything
    that belongs to the valid_signature verdict. Compliance is excluded:
    a missing compliance section is not a signature failure."""
    problems = verify_bundle(bundle)
    return [
        p
        for p in problems
        if not p.startswith("compliance section")
        and not p.startswith("compliance.standards")
        and not p.startswith("compliance.mappings")
    ]


def verify_bundle_verdicts(
    bundle: Any,
    receipts: list[Any] | None = None,
    trusted_keys: set[bytes] | None = None,
    trusted_witness_keys: set[bytes] | None = None,
) -> dict[str, Any]:
    """FR-M43-02: compute the three verdicts independently.

    Returns {"valid_signature": bool, "trusted_signer": bool | None,
    "evidence_coverage": bool, "detail": str, "problems": [str]}.
    A witness mismatch yields valid_signature True and
    evidence_coverage False — never a signature failure.
    """
    signature_problems = _signature_problems(bundle)
    valid_signature = not signature_problems

    signer = bundle.get("signer") or {} if isinstance(bundle, dict) else {}
    key_b64 = signer.get("publicKey") if isinstance(signer, dict) else None
    bundled_key: bytes | None = None
    if isinstance(key_b64, str):
        try:
            decoded = base64.b64decode(key_b64, validate=True)
            if len(decoded) == 32:
                bundled_key = decoded
        except (ValueError, binascii.Error):
            bundled_key = None
    if trusted_keys is None:
        trusted_signer: bool | None = None
    else:
        trusted_signer = bundled_key in trusted_keys if bundled_key else False

    coverage, detail = _evidence_coverage(bundle, receipts or [], trusted_witness_keys)

    return {
        "valid_signature": valid_signature,
        "trusted_signer": trusted_signer,
        "evidence_coverage": coverage,
        "detail": detail,
        "problems": signature_problems,
    }


def _evidence_coverage(
    bundle: Any, receipts: list[Any], trusted_witness_keys: set[bytes] | None
) -> tuple[bool, str]:
    """Rollback/truncation and wholesale-replacement detection against
    previously recorded roots. Mirrors ledger/witness.py exactly."""
    if not receipts:
        return False, UNWITNESSED_LIMITATION

    entries = bundle.get("entries") if isinstance(bundle, dict) else None
    entries = entries if isinstance(entries, list) else []
    entry_hashes: list[bytes] = []
    for entry in entries:
        digest = _hex_bytes(entry.get("entryHash"), "entryHash", []) if isinstance(entry, dict) else None
        if digest is None:
            return False, "bundle has malformed entries; coverage undetermined"
        entry_hashes.append(digest)
    prefix = _contiguous_prefix_length(entries)

    checked = 0
    for receipt in receipts:
        if not isinstance(receipt, dict):
            continue
        head = receipt.get("treeHead") or {}
        witnessed_seq = head.get("seq")
        if not isinstance(witnessed_seq, int) or witnessed_seq < 1:
            continue
        if not verify_receipt_tree_head(receipt):
            continue
        witness = receipt.get("witness") or {}
        if "witnessSignature" in receipt:
            if not verify_witness_signature(receipt):
                continue
            if trusted_witness_keys is not None:
                try:
                    embedded = base64.b64decode(
                        witness.get("publicKey") or "", validate=True
                    )
                except (ValueError, binascii.Error):
                    continue
                if embedded not in trusted_witness_keys:
                    continue
            provenance = f"witness '{witness.get('id')}' countersignature"
        else:
            provenance = "reception receipt (unsigned, local store)"
        checked += 1
        if prefix < witnessed_seq:
            return (
                False,
                f"rollback/truncation: a root at sequence {witnessed_seq} was "
                f"recorded ({provenance}), but this bundle presents only "
                f"{prefix} contiguous entries from genesis",
            )
        witnessed_root = _hex_bytes(head.get("rootHash"), "rootHash", [])
        if witnessed_root is None:
            continue
        prefix_root = _merkle_root(entry_hashes[:witnessed_seq])
        if prefix_root != witnessed_root:
            return (
                False,
                "wholesale replacement or fork: entries "
                f"1..{witnessed_seq} of this bundle do not hash to the "
                f"recorded root {head.get('rootHash')} ({provenance})",
            )
        return (
            True,
            f"recorded root at sequence {witnessed_seq} ({provenance}); "
            "this bundle extends it",
        )
    if checked == 0:
        return (
            False,
            "no usable witness receipts (bad ledger signature, bad witness "
            "signature, or witness key not pinned); coverage undetermined",
        )
    return False, "witness receipts did not match this bundle's history"


def _load_trusted_keys(path: str) -> set[bytes]:
    """One base64 Ed25519 public key per line; '#' starts a comment."""
    keys_set: set[bytes] = set()
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                raw = base64.b64decode(line, validate=True)
            except (ValueError, binascii.Error) as error:
                raise ValueError(f"{path}: not valid base64: {line[:12]}…") from error
            if len(raw) != 32:
                raise ValueError(f"{path}: key is not 32 bytes: {line[:12]}…")
            keys_set.add(raw)
    return keys_set


def verdict_lines(verdicts: dict[str, Any]) -> list[str]:
    trusted = verdicts["trusted_signer"]
    lines = [
        "VERDICT valid_signature: "
        + ("pass" if verdicts["valid_signature"] else "FAIL"),
        "VERDICT trusted_signer: "
        + (
            "pass"
            if trusted
            else "FAIL" if trusted is False else "unknown (no trusted-key set supplied)"
        ),
        "VERDICT evidence_coverage: "
        + ("pass" if verdicts["evidence_coverage"] else "FAIL"),
        f"coverage detail: {verdicts['detail']}",
    ]
    for problem in verdicts["problems"]:
        lines.append(f"signature problem: {problem}")
    return lines


def _parse_args(argv: list[str]) -> tuple[str | None, dict[str, Any]] | None:
    """argv -> (bundle_path, options) or None for help/usage error."""
    options: dict[str, Any] = {
        "witness": [],
        "trusted_keys": None,
        "trusted_witness_keys": None,
    }
    path: str | None = None
    index = 1
    flags = {
        "--witness": ("witness", list),
        "--trusted-keys": ("trusted_keys", str),
        "--trusted-witness-keys": ("trusted_witness_keys", str),
    }
    while index < len(argv):
        arg = argv[index]
        if arg in flags:
            key, kind = flags[arg]
            index += 1
            if index >= len(argv):
                return None
            value = argv[index]
            if kind is list:
                options[key].append(value)
            else:
                options[key] = value
        elif arg in ("-h", "--help"):
            return None
        elif path is None:
            path = arg
        else:
            return None
        index += 1
    return path, options


def main(argv: list[str]) -> int:
    parsed = _parse_args(argv)
    if parsed is None:
        print(__doc__.strip(), file=sys.stderr)
        return 0 if len(argv) == 2 else 2
    path, options = parsed

    def read_json(source: str, what: str) -> Any:
        try:
            with open(source, "rb") as handle:
                return json.loads(handle.read())
        except OSError as error:
            print(f"cannot read {what}: {error}", file=sys.stderr)
        except ValueError as error:
            print(f"{what} is not valid JSON: {error}", file=sys.stderr)
        raise SystemExit(2)

    try:
        if path is None or path == "-":
            raw = sys.stdin.buffer.read()
        else:
            with open(path, "rb") as handle:
                raw = handle.read()
    except OSError as error:
        print(f"cannot read bundle: {error}", file=sys.stderr)
        return 2
    try:
        bundle = json.loads(raw)
    except ValueError as error:
        print(f"bundle is not valid JSON: {error}", file=sys.stderr)
        return 2

    verdict_mode = bool(options["witness"] or options["trusted_keys"])
    if not verdict_mode:
        # FR-M43-03 / T15: the interface states the unwitnessed limitation.
        print(f"NOTE: {UNWITNESSED_LIMITATION}", file=sys.stderr)

    receipts = [read_json(p, "witness receipt") for p in options["witness"]]
    try:
        trusted_keys = (
            _load_trusted_keys(options["trusted_keys"])
            if options["trusted_keys"]
            else None
        )
        trusted_witness_keys = (
            _load_trusted_keys(options["trusted_witness_keys"])
            if options["trusted_witness_keys"]
            else None
        )
    except (OSError, ValueError) as error:
        print(f"cannot load trusted keys: {error}", file=sys.stderr)
        return 2

    if verdict_mode:
        verdicts = verify_bundle_verdicts(
            bundle, receipts, trusted_keys, trusted_witness_keys
        )
        for line in verdict_lines(verdicts):
            print(line)
        ok = (
            verdicts["valid_signature"]
            and verdicts["evidence_coverage"]
            and verdicts["trusted_signer"] is not False
        )
        return 0 if ok else 1

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
