# 8. The verification algorithm

Normative pseudocode for verifying a bundle (§7). A conforming verifier
implements exactly these checks and reports every failure it finds — one
actionable message per problem — rather than stopping at the first. Inputs:
the decoded bundle JSON; outputs: a list of problems (empty ⇔ the bundle
verifies). Nothing outside the bundle is read.

```
VERIFY(bundle):

  problems := []

  # 0. Shape
  require bundle is an object and bundle.formatVersion == 1
  pk := base64_decode_strict(bundle.signer.publicKey)
  require len(pk) == 32                        # else: "signer.publicKey ..."
  entries := bundle.entries                    # must be an array

  # 1. Chain continuity + per-entry hash recompute   (§3)
  prev := null
  for entry in entries:
    require hex(entry.previousHash, 32 bytes) decodes
    require hex(entry.entryHash, 32 bytes) decodes
    require entry.hashPayload is an object
    recomputed := SHA256(bytes(entry.previousHash)
                         || canonical_json(entry.hashPayload))   # §2 byte rules!
    require recomputed == entry.entryHash
       else "entry {seq}: entryHash does not match its content"
    if prev != null:
      require entry.previousHash == prev
       else "entry {seq}: chain link broken"
    prev := entry.entryHash

  # 2. Inclusion proofs                              (§4.2)
  proofs := bundle.proofs
  require proofs.treeSize is an integer; root := hex(proofs.rootHash)
  bySeq := { e.sequence: e for e in entries }
  proven := {}
  for proof in proofs.inclusion:
    entry := bySeq[proof.sequence]              # else "proof for unknown sequence"
    path  := [hex(node) for node in proof.path]
    require RFC9162_VERIFY_INCLUSION(proof.leafIndex,
                                     bytes(entry.entryHash),
                                     proofs.treeSize, path, root)
       else "entry {seq}: Merkle inclusion proof does not verify"
    proven += proof.sequence
  for seq in bySeq: require seq in proven
       else "entry {seq}: no inclusion proof included"

  # 3. Signed tree head                              (§5)
  if entries non-empty: require bundle.treeHead present
  head := bundle.treeHead
  require head.seq == proofs.treeSize
  require head.rootHash == proofs.rootHash
  message := canonical_json({"root_hash": head.rootHash,
                             "seq":       head.seq,
                             "signed_at": head.signedAt})
  require ED25519_VERIFY(pk, bytes(head.signature), message)
     else "treeHead signature does not verify with the bundled public key"

  # 4. Bundle signature                              (§7.5)
  core    := bundle without the "signature" key
  digest  := SHA256(canonical_json(core))
  require digest == bytes(signature.digest)
     else "signature.digest does not match the bundle content"
  require ED25519_VERIFY(pk, bytes(signature.signature), digest)
     else "bundle signature does not verify with the bundled public key"

  # 5. Compliance section                            (§7.6)
  require bundle.compliance.standards non-empty
  require bundle.compliance.mappings  non-empty

  return problems
```

Exit behaviour (both reference verifiers): `0` and a one-line summary on
stdout when `problems` is empty; `1` with one `FAIL: <message>` line per
problem on stderr otherwise; `2` for usage, unreadable input or invalid
JSON.

## Notes

- **canonical_json everywhere is §2.** The float caveat (§2.2) is the most
  common cause of a conforming verifier rejecting a genuine bundle in an
  independent implementation.
- The first entry's `previousHash` is validated for shape and used in the
  hash recompute, but its *link* to earlier history is anchored by check 2
  (the proof ties it to the full-ledger tree). If the bundle starts at seq
  1, the genesis link (32 zero bytes) applies.
- `ED25519_VERIFY` is pure Ed25519 (RFC 8032, cofactorless check
  `[S]B = R + [k]A`, `k = SHA-512(R || A || M) mod L`, reject `S ≥ L` and
  non-canonical encodings). The Python reference implements it from scratch
  so the verifier stays dependency-free.
