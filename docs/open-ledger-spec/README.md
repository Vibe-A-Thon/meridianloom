# The Meridian Open Ledger Specification

**Status:** normative, v1 · **Requirements:** FR-M36-06 (open specification with
a reference verifier), NFR-31 (portable verification), SEC-29 (verification
without trusting Meridian's servers), FR-M36-04 (the signed audit bundle),
FR-M12-11 (compliance mapping).

This specification is all a third party needs to validate a Meridian audit
bundle on a machine with **no Meridian installed**. It pins, byte for byte:

1. [The ledger entry schema](01-entry-schema.md) — every column.
2. [Canonical JSON](02-canonical-json.md) — the byte rules every hash relies on.
3. [The hash chain](03-hash-chain.md) — how entries bind to each other.
4. [The Merkle tree](04-merkle-tree.md) — RFC 6962/9162 as implemented.
5. [The signed tree head](05-signed-tree-head.md) — Ed25519 over the root.
6. [The blob encryption envelope](06-blob-envelope.md) — ciphertext format, no keys.
7. [The bundle format](07-bundle-format.md) — `ledger.exportBundle` output.
8. [The verification algorithm](08-verification-algorithm.md) — pseudocode.
9. [verify.md](verify.md) — quick-start with the reference verifiers.

## Reference implementations

Two verifiers implement §8 identically and are kept in lock-step by CI:

- `verifier/verify.py` — single file, Python 3.11+ standard library only
  (Ed25519 verification is a pure-Python RFC 8032 implementation, so nothing
  needs to be installed).
- `verifier/` (cargo) — the `meridian-verify` binary; pinned dependencies
  `serde_json`, `sha2`, `ed25519-dalek` (parsing, SHA-256, Ed25519 only —
  canonical JSON including CPython float rendering, RFC 6962 verification and
  base64 are implemented in the crate, not delegated).

Both exit `0` and print a one-line summary when a bundle verifies, exit `1`
with one actionable `FAIL:` line per problem on stderr otherwise, and exit `2`
on usage/IO/JSON errors.

## Conformance

A bundle **conforms** when the algorithm in §8 reports no problems. A
verifier **conforms** when it accepts every conforming bundle and rejects at
least: any single-field modification of a conforming bundle, a re-signed
bundle under any key not equal to the bundled public key, and any bundle
whose Merkle proofs were recomputed against a different tree.

## Language

The key words **MUST**, **MUST NOT** and **MAY** are to be interpreted as
described in RFC 2119.
