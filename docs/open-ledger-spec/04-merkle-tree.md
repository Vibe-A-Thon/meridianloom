# 4. The Merkle tree

A Merkle tree over all `entry_hash` values gives third parties
**inclusion** evidence (this entry is in the ledger) and the ledger
**consistency** evidence (this tree extends that earlier tree) without
reading every entry (FR-M10-03).

The tree is the left-complete binary history tree of **RFC 6962 §2.1**,
with leaves equal to the raw 32-byte `entry_hash` values in `seq` order
(leaf *i* is entry *seq i+1*). The reference algorithms are RFC 6962
§2.1.1 (audit paths) and RFC 9162 §2.1.3.2 (inclusion verification) /
§2.1.4 (consistency). This document restates the shapes so the verifier can
be implemented from the RFCs alone; where wording differs, the RFCs win.

## 4.1 Tree hash

```
MTH({})    = SHA-256("")                       (the empty root)
MTH({d})   = SHA-256(0x00 || d)                (leaf)
MTH(D[n])  = SHA-256(0x01 || MTH(D[0:k]) || MTH(D[k:n]))
             where k is the largest power of two strictly less than n
```

## 4.2 Inclusion proofs (audit paths)

An inclusion proof for leaf index *m* in a tree of *n* leaves is the list of
sibling subtree hashes on the path from the leaf to the root. Verification
(RFC 9162 §2.1.3.2, reproduced by both reference verifiers):

```
fn := m; sn := n − 1; r := SHA-256(0x00 || leaf)
for each p in path (leaf-to-root order):
    if sn == 0: return false
    if fn is odd or fn == sn:
        r := SHA-256(0x01 || p || r)
        if fn is even:
            while fn is even and fn != 0: fn >>= 1; sn >>= 1
    else:
        r := SHA-256(0x01 || r || p)
    fn >>= 1; sn >>= 1
return sn == 0 and r == claimed_root
```

## 4.3 Consistency proofs

A consistency proof between an earlier size *m* and a later size *n* is the
RFC 9162 §2.1.4.1 subproof that the first *m* leaves form the earlier tree;
verification follows §2.1.4.2. Bundles (§7) use inclusion proofs; the
`ledger.proof` RPC exposes both shapes for interactive inspection.

## 4.4 Properties a verifier relies on

- A proof MUST verify against the **tree size and root it was issued for**;
  a proof recomputed against a different tree (different size or root) MUST
  NOT verify.
- Leaf *i* of the proof tree is entry *seq i+1* — the bundle's inclusion
  proofs therefore anchor entries into the whole ledger, even when the
  bundle itself contains only a filtered subset.
