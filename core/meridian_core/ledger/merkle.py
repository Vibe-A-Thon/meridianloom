"""FR-M10-03: Merkle tree over ledger entries (RFC 6962/9162 shape).

Leaves are the entries' `entry_hash` bytes; the tree is the
left-complete history tree defined by RFC 6962 §2.1:

    MTH({d})   = SHA-256(0x00 || d)                      (leaf)
    MTH(D[n])  = SHA-256(0x01 || MTH(D[0:k]) || MTH(D[k:n]))
                 for k the largest power of two < n      (node)
    MTH({})    = SHA-256("")                             (empty)

Inclusion proofs are RFC 6962 §2.1.1 audit paths; consistency proofs are
RFC 6962 §2.1.2 / RFC 9162 §2.1.4.1 subproofs. Verification follows the
RFC 9162 §2.1.3.2 / §2.1.4.2 reference algorithms exactly, so the open
verifier (FR-M36-06) can reimplement them from the RFC alone.
"""

from __future__ import annotations

import hashlib

LEAF_PREFIX = b"\x00"
NODE_PREFIX = b"\x01"

EMPTY_ROOT = hashlib.sha256(b"").digest()


def leaf_hash(data: bytes) -> bytes:
    return hashlib.sha256(LEAF_PREFIX + data).digest()


def node_hash(left: bytes, right: bytes) -> bytes:
    return hashlib.sha256(NODE_PREFIX + left + right).digest()


def _split(n: int) -> int:
    """Largest power of two strictly smaller than n (n > 1)."""
    return 1 << ((n - 1).bit_length() - 1)


def _root_range(leaves: list[bytes], lo: int, hi: int) -> bytes:
    n = hi - lo
    if n == 0:
        return EMPTY_ROOT
    if n == 1:
        return leaf_hash(leaves[lo])
    k = _split(n)
    return node_hash(
        _root_range(leaves, lo, lo + k), _root_range(leaves, lo + k, hi)
    )


def root(leaves: list[bytes]) -> bytes:
    """MTH over the given leaf payloads (entry hashes)."""
    return _root_range(leaves, 0, len(leaves))


class MerkleFrontier:
    """Incremental tree state: O(log n) per append, O(log n) per root.

    Holds the roots of the maximal perfect subtrees covering the leaves
    appended so far (sizes strictly decreasing). Rebuilt from stored
    entry hashes when the ledger opens.
    """

    def __init__(self) -> None:
        self.count = 0
        self._subtrees: list[tuple[int, bytes]] = []

    def append(self, leaf_payload: bytes) -> None:
        size, carry = 1, leaf_hash(leaf_payload)
        while self._subtrees and self._subtrees[-1][0] == size:
            left_size, left_hash = self._subtrees.pop()
            carry = node_hash(left_hash, carry)
            size += left_size
        self._subtrees.append((size, carry))
        self.count += 1

    def root(self) -> bytes:
        if not self._subtrees:
            return EMPTY_ROOT
        acc = self._subtrees[-1][1]
        for _size, subtree_hash in reversed(self._subtrees[:-1]):
            acc = node_hash(subtree_hash, acc)
        return acc


def inclusion_proof(leaves: list[bytes], index: int) -> list[bytes]:
    """RFC 6962 §2.1.1 audit path for the leaf at `index` (0-based)."""
    n = len(leaves)
    if not 0 <= index < n:
        raise ValueError(f"index {index} out of range for tree of {n}")
    path: list[bytes] = []

    def walk(lo: int, hi: int, idx: int) -> None:
        if hi - lo == 1:
            return
        k = _split(hi - lo)
        if idx < lo + k:
            walk(lo, lo + k, idx)
            path.append(_root_range(leaves, lo + k, hi))
        else:
            walk(lo + k, hi, idx)
            path.append(_root_range(leaves, lo, lo + k))

    walk(0, n, index)
    return path


def verify_inclusion(
    index: int,
    leaf_payload: bytes,
    tree_size: int,
    path: list[bytes],
    expected_root: bytes,
) -> bool:
    """RFC 9162 §2.1.3.2 reference verification of an inclusion proof."""
    if not 0 <= index < tree_size:
        return False
    fn = index
    sn = tree_size - 1
    r = leaf_hash(leaf_payload)
    for p in path:
        if sn == 0:
            return False
        if fn & 1 or fn == sn:
            r = node_hash(p, r)
            if not fn & 1:
                while not fn & 1 and fn != 0:
                    fn >>= 1
                    sn >>= 1
        else:
            r = node_hash(r, p)
        fn >>= 1
        sn >>= 1
    return sn == 0 and r == expected_root


def consistency_proof(leaves: list[bytes], old_size: int) -> list[bytes]:
    """RFC 9162 §2.1.4.1: proof that tree(old_size) is a prefix of this tree."""
    n = len(leaves)
    if not 0 < old_size <= n:
        raise ValueError(f"old size {old_size} out of range for tree of {n}")

    def subproof(lo: int, hi: int, m: int, complete: bool) -> list[bytes]:
        n_sub = hi - lo
        if m == n_sub:
            return [] if complete else [_root_range(leaves, lo, hi)]
        k = _split(n_sub)
        if m <= k:
            return subproof(lo, lo + k, m, complete) + [
                _root_range(leaves, lo + k, hi)
            ]
        return subproof(lo + k, hi, m - k, False) + [
            _root_range(leaves, lo, lo + k)
        ]

    if old_size == n:
        return []
    return subproof(0, n, old_size, True)


def verify_consistency(
    old_size: int,
    old_root: bytes,
    new_size: int,
    new_root: bytes,
    proof: list[bytes],
) -> bool:
    """RFC 9162 §2.1.4.2 reference verification of a consistency proof."""
    if old_size == 0:
        return not proof
    if old_size == new_size:
        return not proof and old_root == new_root
    if old_size > new_size or not proof:
        return False
    path = list(proof)
    if old_size & (old_size - 1) == 0:  # exact power of two
        path.insert(0, old_root)
    fn = old_size - 1
    sn = new_size - 1
    while fn & 1:
        fn >>= 1
        sn >>= 1
    fr = sr = path[0]
    for c in path[1:]:
        if sn == 0:
            return False
        if fn & 1 or fn == sn:
            fr = node_hash(c, fr)
            sr = node_hash(c, sr)
            if not fn & 1:
                while not fn & 1 and fn != 0:
                    fn >>= 1
                    sn >>= 1
        else:
            sr = node_hash(sr, c)
        fn >>= 1
        sn >>= 1
    return sn == 0 and fr == old_root and sr == new_root
