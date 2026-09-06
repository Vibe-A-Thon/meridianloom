# 6. The blob encryption envelope

Large payloads (prompts, outputs, diffs) live outside the ledger in an
encrypted, content-addressed blob store (FR-M10-07); the entry row carries
only digests and references. The chain hashes **ciphertext** — this is what
makes erasure (§6.4) compatible with verification.

## 6.1 Blob file format

A blob file is exactly:

```
nonce (12 bytes, random) || AES-256-GCM ciphertext
```

- AEAD: AES-256-GCM. The 16-byte GCM authentication tag is appended to the
  ciphertext by the AEAD construction (last 16 bytes of the ciphertext
  portion).
- AAD: the ASCII bytes `meridian/blob/v1`.
- Key: the subject's per-subject 256-bit key, identified by the entry's
  `blob_key_id` (`bk:<subject>`). **Key material never appears in the
  ledger, in bundles, or in this specification** — only its id does.

## 6.2 Content addressing

The blob's reference (`input_ref`/`output_ref`) is its storage path,
relative to the blob root: `<first-2-hex-of-digest>/<digest-hex>.blob`,
where the digest is

```
digest = SHA-256(nonce || AES-256-GCM ciphertext)      — hex, lowercase
```

i.e. the content address is the SHA-256 of the **ciphertext including the
nonce**. The entry's `input_digest`/`output_digest` columns hold exactly
this digest. Consequences:

- identical plaintexts do **not** deduplicate (random nonce), by design;
- the chain commits to ciphertext, so a blob can be checked for integrity
  with only the bundle: recompute SHA-256 over the blob file's bytes and
  compare with `input_digest`/`output_digest`.

## 6.3 What a third party can and cannot check

With a bundle and the blob files, a verifier can prove a blob's bytes match
what the ledger committed to (SHA-256 over the file == the entry digest).
It cannot decrypt: the per-subject key lives only in the workspace key
registry. Verification never needs plaintext.

## 6.4 Erasure (crypto-shredding, FR-M10-14)

Each subject key is stored wrapped (AES-GCM under a workspace master key)
in the `blob_key` registry with its `key_id` and `subject_id`. Erasure
deletes the wrapped-key row; the subject's blobs become unreadable
permanently, **no ledger row is deleted**, and the chain still verifies
because it hashes ciphertext. A verifier treats a missing `blob_key_id` row
as "payload unavailable", never as an integrity failure.
