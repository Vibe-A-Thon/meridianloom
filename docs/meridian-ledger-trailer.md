# The `Meridian-Ledger:` Git Trailer — Specification v1

**Status:** published · **Normative parser/verifier:** `core/meridian_core/ledger/trailer_spec.py` · **Requirements:** FR-M43-11, NFR-39, AC-49

## 1. Purpose

A governed change merged with Meridian's evidence ledger can carry a
`Meridian-Ledger:` trailer binding the merge commit to a **signed ledger
tree head** (FR-M10-04). A third party who can run `git log` — and nothing
else: no Meridian server, no workspace access, no credentials — can parse
the trailer and independently verify that the ledger root it names was
signed by the key it embeds.

What this proves, and what it does not (see also FR-M43-03):

- The trailer proves **signature validity**: the named root was signed by
  the private key matching the embedded public key, at the stated sequence
  and time.
- Signer **trust** is a separate verdict, made against the customer's
  enrolled-key history by the independent verifier (`verifier/`, three
  verdicts: `valid_signature`, `trusted_signer`, `evidence_coverage`).
- The trailer is a **pointer**. Git history is editable; without a
  configured witness or receipt store (`ledger/receipts.py`), Meridian
  claims **no detection of wholesale replacement** of re-signed history.

## 2. Grammar

```
trailer-line  = "Meridian-Ledger:" SP value
value         = "v1" 1*(SP attr)
attr          = seq-attr / root-attr / sig-attr / key-attr / at-attr
seq-attr      = "seq=" 1*DIGIT
root-attr     = "root=" 64(HEXDIG-lc)
sig-attr      = "sig=" 128(HEXDIG-lc)
key-attr      = "key=" 44(base64)   ; standard base64 of 32 raw bytes, with padding
at-attr       = "at=" 1*(VCHAR-SP)  ; RFC 3339 UTC timestamp
```

Example:

```
Meridian-Ledger: v1 seq=42 root=9f2c…(64 hex) sig=8a71…(128 hex) key=3mJ9…(44 b64) at=2026-09-12T00:00:00Z
```

Field semantics, exactly matching the ledger's tree head (FR-M10-04):

| Field | Meaning |
|---|---|
| `v1` | Schema version token. Parsers MUST reject values with an unknown version token rather than attempt to parse them (NFR-39). |
| `seq` | Ledger sequence number the tree head covers. |
| `root` | Merkle tree head root: 32 bytes, 64 lowercase hex. This is `Ledger.root_hash()` / `MerkleFrontier.root()`. |
| `sig` | Ed25519 signature, 64 bytes, 128 lowercase hex, over `tree_head_message(seq, root, at)` = `canonical_json({"root_hash": <hex>, "seq": <n>, "signed_at": <ts>})` (`ledger/keys.py`). |
| `key` | Raw 32-byte Ed25519 public key, standard base64 with padding (same encoding as exported bundles' `publicKey` field). |
| `at` | The `signed_at` timestamp the signature commits to, RFC 3339 UTC. |

Tokens are separated by exactly one space; attribute order is fixed as
above. Each attribute appears at most once.

## 3. Parsing rules

1. Trailer detection follows git trailer-block semantics, shared with the
   rest of Meridian (`meridian_core.trailers`): a `Key: value` line,
   comment lines (`#`) skipped.
2. Multiple `Meridian-Ledger:` trailers MAY appear in one commit (one per
   tree-head epoch). All parse, in order; the **last** is the current one.
3. A malformed `Meridian-Ledger:` value (bad grammar, wrong lengths,
   duplicate attribute, unknown version) MUST NOT raise into the caller
   and MUST NOT verify: it is reported as a warning carrying the
   requirement id. Corrupt input must never crash third-party audit
   tooling.
4. A commit with **no** trailer has state *no trailer*. That state must
   never be presented or read as *verified* (AC-49).

## 4. Verification

Reference verifier (third-party usable):

```bash
# extract commit messages only
git log --format=%B > messages.txt
python -m meridian_core verify-trailers messages.txt   # or the library API below
```

Library API (`meridian_core.ledger.trailer_spec`):

```python
result = parse_meridian_ledger_trailers(message)   # refs + warnings
ref = result.latest                                # None == "no trailer"
ok = ref is not None and verify_trailer(ref)       # signature validity ONLY
```

`verify_trailer` recomputes `tree_head_message(seq, root, at)` and checks
the Ed25519 signature against the embedded `key`. It makes **no trust
claim**; signer trust is the independent verifier's separate verdict.

## 5. Producing a trailer

```python
from meridian_core.ledger import trailer_spec as ts

head = ledger.latest_tree_head()          # or emit_tree_head_now()
value = ts.trailer_from_tree_head(head, ledger.signing_public_key)
message = append_trailer(commit_message, ts.TRAILER_KEY, value)
```

`format_trailer(...)` is the exact inverse of the parser: everything it
emits parses and verifies.

## 6. Versioning

The `v1` token is the schema version. A future v2 introduces a *new* token;
v1 trailers remain parseable forever. Parsers reject unknown versions
explicitly (§3.3) — a version bump is never a silent format change (NFR-39).
