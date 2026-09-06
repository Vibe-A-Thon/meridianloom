# 7. The bundle format

`ledger.exportBundle` (FR-M36-04) produces a single JSON document — a
**signed audit bundle** — for any sequence range, date range, agent or
story, without the orchestration tier installed. The bundle verifies
standalone (§8, SEC-29): everything needed travels inside it.

## 7.1 Top level

```
{
  "formatVersion": 1,              // MUST be 1
  "generatedAt":   "<ISO 8601 UTC>",
  "signer":        { "algorithm": "Ed25519", "publicKey": "<base64, 32 B>" },
  "treeHead":      { ... },        // §5.1; absent only when the ledger is empty
  "range":         { "fromSequence": n, "toSequence": m },
  "filter":        { ... },        // the filters actually applied (§7.3)
  "entries":       [ ... ],        // §7.2
  "proofs":        { ... },        // §7.4
  "compliance":    { ... },        // §7.6
  "signature":     { ... }         // §7.5
}
```

`additionalProperties` is false everywhere: fields not in this
specification invalidate the bundle (they would invalidate the §7.5
signature in any case).

## 7.2 `entries[]`

Each entry is the wire projection of one ledger row: the stream fields
(`sequence`, `timestamp`, `storyId`, `phase`, `loopId`, `loopIteration`,
`actorId`, `actorVersion`, `actorKind`, `policyVersion`, `skillId`,
`skillVersion`, `modelId`, `modelVersion`, `actionType`, `decision`,
`confidence`, `humanActor`, `humanRole`, `reworkReason`, `tokensIn`,
`tokensOut`, `costUsd`, `latencyMs`, `worktreeRef`, `repoId`, `replayOf`,
`runId`, `origin`, `vendor`, `observationConfidence`, `externalSessionId`,
`simulated`, `entryHash`, `previousHash`) plus the ciphertext side-channels
(`hasInputBlob`, `hasOutputBlob`, `inputDigest`, `inputRef`, `outputDigest`,
`outputRef` — digests lowercase hex, refs as stored).

Two wire-shape rules a verifier MUST know:

- **`simulated`** is a JSON **boolean** on the wire (`true`/`false`) — the
  human-readable view. The hashed payload (§7.2.1) carries the ledger's
  stored form, the integer `1`/`0`, because the database column is
  INTEGER. The boolean itself is **not** hashed.
- **`hashPayload`** (below) is the anchor of truth; sibling fields are a
  view. Tampering with a view field is detected by the §7.5 signature;
  tampering with `hashPayload` is detected by the §3 entry hash.

### 7.2.1 `hashPayload` — the exact hash preimage

`hashPayload` is the JSON-native payload object of §2.3/§3.1, carried
verbatim: the full ledger column set **minus `prev_hash`/`entry_hash`**,
byte columns (`input_digest`, `output_digest`, `signature`) hex-projected
to lowercase hex strings, `simulated` as integer `0`/`1`, `tool_calls` as
the stored serialized text, everything else as its JSON-native value.
`entry_hash` is recomputed as:

```
SHA-256( bytes.fromhex(previousHash) || canonical_json(hashPayload) )
```

and MUST equal the entry's `entryHash` (§3.2 step 1).

## 7.3 `filter`

The filters applied within the sequence range — any subset of `storyId`,
`agentId`, `fromTimestamp`, `toTimestamp` (ISO 8601 UTC, inclusive bounds on
`ts_utc`) — echoed for the record. Export filters within the range; they
never widen it.

## 7.4 `proofs`

```
{
  "treeSize": <int>,               // the WHOLE ledger size at export, == treeHead.seq
  "rootHash": "<64-hex>",          // MTH over all treeSize leaves (§4.1)
  "inclusion": [
    { "sequence": s,               // 1-based ledger sequence
      "leafIndex": s − 1,
      "path": ["<64-hex>", ...] },// RFC 6962 §2.1.1 audit path, leaf-to-root
    ...
  ]
}
```

One inclusion proof per included entry, anchoring it into the full-ledger
tree the signed head commits to — the subset nature of a filtered export is
therefore harmless (§3.2).

## 7.5 `signature` — the bundle signature block

```
{
  "algorithm": "Ed25519",
  "signedAt":  "<ISO 8601 UTC>",
  "digest":    "<64-hex>",   // SHA-256 over the canonical JSON of the ENTIRE
                             // bundle object minus this "signature" field
  "signature": "<128-hex>"   // pure Ed25519 over the 32 raw digest bytes
}
```

Any modification of any other field in the bundle changes the canonical
bytes and therefore the digest — the signature block binds the whole
document. The verifying key is `signer.publicKey` (§5.3): verification
trusts nothing outside the bundle.

## 7.6 `compliance`

```
{
  "standards": ["NIST SSDF (SP 800-218 v1.1)",
                "ISO/IEC 42001:2023",
                "EU AI Act (Regulation (EU) 2024/1689), Article 12"],
  "mappings": [
    { "framework": "...", "reference": "...", "requirement": "...",
      "bundleFields": ["entries", "treeHead", ...], "note": "..." },
    ...
  ]
}
```

Per FR-M12-11 (as amended by gaps-requirements M12: NIST SSDF AI provenance
first), each mapping names a standard, the clause or practice, the
requirement in plain language, and the bundle fields that satisfy it. The
mapping is data for auditors, not legal advice; verifiers check presence and
shape, not the legal accuracy.

## 7.7 Size limits

One export call returns at most 10 000 entries; larger ranges are exported
in consecutive slices (each slice carries its own tree head and proofs for
its entries).
