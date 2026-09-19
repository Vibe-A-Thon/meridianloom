# 3. The hash chain

Each entry binds to its predecessor so that history cannot be altered,
inserted into, or reordered without detection (FR-M10-02).

## 3.1 Construction

```
payload(n)    = ledger_entry columns of seq n, minus {prev_hash, entry_hash},
                byte columns hex-projected, values JSON-native   (§2.3)
entry_hash(n) = SHA-256( prev_hash(n) || canonical_json(payload(n)) )
prev_hash(1)  = 0x00 × 32                                        (genesis link)
prev_hash(n)  = entry_hash(n−1)            for n > 1
```

`prev_hash` is prepended **as raw 32 bytes** (not hex) before the canonical
JSON, so a re-pointed link changes the digest even if the payload is
identical. `seq` is part of the payload and is therefore bound into the
hash: a renumbered entry cannot verify.

## 3.2 Verification

Given a consecutive run of entries (a full ledger, or the `entries` array
of a bundle):

1. For each entry, recompute `entry_hash` per §3.1 and require equality with
   the stored `entryHash`. (The bundle carries `hashPayload`, the exact
   pre-canonicalization payload — §7.)
2. For each entry after the first in the run, require
   `previousHash == previous entry's entryHash`.
3. The first entry's `previousHash` binds to a predecessor that is **not**
   part of the run unless the run starts at seq 1; on its own it is an
   unverified claim. A verifier that needs the claim anchored MUST use the
   Merkle proofs (§4), which tie the entry to the signed tree head over the
   whole ledger — the bundle format in §7 always includes those proofs.

A bundle's `entries` are filtered (by range/story/agent/date), so step 2
verifies continuity **within the bundle**; the boundary into earlier
history is anchored by §4 instead.

## 3.3 Limits

- Digests are SHA-256 throughout.
- `entry_hash` and `prev_hash` are 32-byte values; on the wire they are
  lowercase hex strings (64 characters).
