# Quick start: verifying a bundle

Two reference verifiers ship in this repository and implement the same
algorithm ([§8](08-verification-algorithm.md)). Both need **only the bundle
file** — no Meridian, no credentials, no network.

## Python (nothing to install)

Requires Python 3.11+ (standard library only — Ed25519 is implemented in
the file itself):

```sh
python verifier/verify.py bundle.json
# or from stdin:
cat bundle.json | python verifier/verify.py -
```

## Rust (`meridian-verify`)

Requires a Rust toolchain (cargo). Build once, run anywhere the binary goes:

```sh
cargo build --release --manifest-path verifier/Cargo.toml
./verifier/target/release/meridian-verify bundle.json
```

(The binary also reads stdin with `-`.)

## Reading the result

**Exit 0** — the bundle verifies:

```
OK: bundle verifies — 7 entries, tree size 7, chain, Merkle proofs, tree head and bundle signature all valid
```

**Exit 1** — the bundle does not verify; every problem is one line:

```
FAIL: entry 3: entryHash does not match its content (hashPayload was tampered with, or the entry was altered)
FAIL: signature.digest does not match the bundle content — a field was tampered with after signing
```

**Exit 2** — the verifier could not run: bad usage, unreadable file, or
invalid JSON (not a verdict about the bundle).

## What is being proven

- the entries are the ones the ledger committed to (hash chain, §3);
- each entry is included in the ledger's Merkle tree (RFC 6962 proofs, §4);
- the tree root is signed by the key whose public half is inside the
  bundle (Ed25519 tree head, §5 — no trust in Meridian's servers, SEC-29);
- no field anywhere in the bundle was altered after export (bundle
  signature, §7.5).

Export a bundle from the VS Code command line / RPC surface with
`ledger.exportBundle` (any sequence range, date range, agent or story), or
ask a Meridian user for one. The format is specified in
[§7](07-bundle-format.md).
