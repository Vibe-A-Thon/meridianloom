# 5. The signed tree head

The ledger periodically signs the Merkle root at the current tip
(FR-M10-04), so a verifier can anchor a tree root to a signing key without
trusting anything outside the bundle (SEC-29).

## 5.1 Head fields

| Field | Type | Meaning |
|---|---|---|
| `seq` | integer | The ledger sequence this head covers — equal to the tree size. |
| `rootHash` | 64-char lowercase hex | `MTH` over entry hashes 1..`seq` (§4.1). |
| `signedAt` | string | ISO 8601 UTC signing timestamp. Bound into the signature. |
| `signature` | 128-char lowercase hex | Ed25519 signature (§5.2). |
| `anchorRef` | string, optional | External anchor reference, when the deployment configures anchoring. Absent in most bundles; verifiers MUST NOT require it. |

## 5.2 The signed message

The signature is pure Ed25519 (RFC 8032, no pre-hashing) over the canonical
JSON of exactly this object (§2 byte rules):

```json
{"root_hash": "<rootHash hex>", "seq": <seq>, "signed_at": "<signedAt>"}
```

Note the snake_case keys (`root_hash`, `signed_at`) — they differ from the
wire field names on purpose and MUST be reproduced exactly.

## 5.3 Key material

The signing key is a 32-byte Ed25519 seed held in the OS keychain and
provisioned to the sidecar in memory only (FR-M10-04/SEC-06); it is never
written to the ledger. Only the 32-byte public key appears in products (the
bundle's `signer.publicKey`, base64) — verification needs nothing else
(SEC-29: no trust in Meridian's servers, and no trust in any vendor whose
work the ledger records).

## 5.4 Cadence

Heads are emitted at a configurable cadence (default every 100 entries or
10 minutes). `ledger.exportBundle` emits a head at the tip on demand when
the cadence has not produced one covering the exported range, so a bundle's
`treeHead.seq` equals the proof tree size (§7).
