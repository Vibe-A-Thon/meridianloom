# The `Meridian-Ledger` commit trailer — specification version 1

**Status:** stable. **Version:** 1. **Reference parser:** `verifier/meridian_trailer.py`,
shipped inside the extension at `<extension>/sidecar/meridian_trailer.py`.

This document is the specification. The reference parser implements it; where
the two disagree, this document is correct and the parser has a bug.

---

## 1. What the trailer is for

A commit says what changed. It does not say who decided, under whose
authority, or what was checked first. Meridian records that separately, in a
hash-chained append-only ledger, and the trailer is the one-line pointer from
the commit into that record:

```text
Meridian-Ledger: 412-418
```

The point of publishing this is independence. Given a repository and an
exported bundle, a third party — an auditor, a customer's security team, an
acquirer's diligence process — can go from `git log` to verified evidence
using only this document and the two reference tools, on a machine that has
never had Meridian installed and never will (`NFR-39`, `AC-49`).

This trailer is a **pointer, not a proof.** It is written in a commit message,
which anybody can edit. It carries no signature and asserts no authority. All
it does is name a range; everything that makes that range trustworthy lives in
the ledger and its signed tree head, and is checked by the verifier in §6.
A trailer naming a range that no bundle contains simply resolves to nothing.

## 2. Where it appears

In the commit message's **trailer block**: the last paragraph of the message,
where every line has the form `Key: value`. This is git's own definition, and
`git interpret-trailers` agrees with it.

A paragraph in which any line is not a trailer is not a trailer block. So a
line reading `Meridian-Ledger: 3-9` inside prose in the body has no meaning,
and a parser must not treat it as one. The rule exists so that quoting the
trailer while discussing it cannot change what a commit claims.

## 3. Grammar

```abnf
trailer      = key ":" WSP value
key          = %s"Meridian-Ledger"   ; compared case-insensitively
value        = sequence / range
range        = sequence "-" sequence ; inclusive at both ends
sequence     = 1*DIGIT               ; decimal, no sign, no separators, >= 1
```

- `sequence` is a ledger entry sequence number. Sequences start at **1** and
  increase by one per appended entry; they are never reused.
- A bare `sequence` means the single-entry range `(n, n)`.
- In `range`, the second sequence MUST NOT be lower than the first.
- Exactly one space or tab separates the colon from the value. Surrounding
  whitespace in the value is not significant.

### Conformance

A parser:

- **MUST** ignore a commit with no `Meridian-Ledger` trailer. That is an
  ordinary commit, not an error.
- **MUST** refuse a value that does not match the grammar, rather than
  guessing. A misread range is worse than a refused one: it reports evidence
  for the wrong entries.
- **MUST** refuse two `Meridian-Ledger` trailers with different values in one
  commit. Which one is binding would otherwise be a matter of opinion.
- **MAY** accept a future version's grammar only if it also recognises the
  version. Version 1 has no in-band version marker precisely because it is
  the first; a later version that widens the grammar will introduce one, and
  a version-1 parser will correctly refuse what it cannot read.

## 4. Semantics

The range names ledger entries recorded for **the work this commit contains**.
It is written by Meridian's `commit-msg` hook at commit time, from the entries
appended while that content was produced.

What it does **not** mean:

- It is not a claim that the entries are correct, only that they exist and
  describe this commit's work.
- It is not a claim of review, approval or test status. Those are recorded
  *as entries*, inside the range, and must be read from there.
- Absence of a trailer is not a claim that no agent was involved. A commit
  made outside Meridian, or with the hook uninstalled, simply has no pointer.
  Meridian reports such a commit as unattributed rather than as human-written.

## 5. Resolving a trailer to a bundle range

A **bundle** is Meridian's export format: a JSON document containing entries,
a signed tree head, Merkle inclusion proofs and the public key. Its `entries`
array holds objects with an integer `sequence`.

To resolve:

1. Parse the trailer to `(first, last)`.
2. Check the bundle contains an entry for **every** sequence in `first..last`.
   A partial bundle does not cover the commit, and the gap should be reported
   by sequence rather than as a bare failure.
3. Verify the bundle (§6). Coverage without verification proves nothing: an
   unverified bundle is a JSON file somebody handed you.

Steps 1 and 2 are what `meridian_trailer.py` does. Step 3 is `verify.py`.
They are separate programs because they answer separate questions, and the
second is useful on its own.

## 6. Worked example — third-party verification, start to finish

On a clean machine, with Python 3.11+ and git, and no Meridian installed.
You have been given a repository and `bundle.json`.

```console
$ git log -1 --format=%B 9f2c1ab | python meridian_trailer.py
{
  "specVersion": 1,
  "trailer": {
    "from": 412,
    "to": 418,
    "count": 7
  }
}
```

The commit claims seven ledger entries. Does the bundle contain them?

```console
$ git log -1 --format=%B 9f2c1ab > msg.txt
$ python meridian_trailer.py --message-file msg.txt --bundle bundle.json
{
  "specVersion": 1,
  "trailer": { "from": 412, "to": 418, "count": 7 },
  "covered": true
}
OK: the bundle contains every entry this commit claims.
Now verify the bundle itself: python verify.py <bundle>
```

Then verify the bundle, which is the step that actually establishes trust:

```console
$ python verify.py bundle.json
```

`verify.py` checks the hash chain, the Merkle inclusion proofs, the tree-head
signature and the bundle signature against the public key **in the bundle**,
and reports three separate verdicts — whether the signature is valid, whether
the signer is one you trust, and whether the evidence covers what is claimed.
Read its output rather than its exit code alone: a valid signature from an
unknown signer is a meaningful answer, not a pass.

Exit status of `meridian_trailer.py`: `0` parsed (and covered, if a bundle was
given), `1` malformed or not covered, `2` usage or I/O error.

## 7. Stability

Version 1 is stable. Within it:

- The key name will not change.
- The value grammar will not narrow. A value valid under version 1 stays
  valid.
- The meaning of a range will not change.

A future version may widen the grammar. It will be a new version, announced by
a marker in the value, and a version-1 parser will refuse it — which is the
correct outcome, because a parser that guesses at a form it does not know is
how a pointer silently starts pointing somewhere else.

## 8. Limitations, stated plainly

- **The trailer is editable.** Anyone with commit access can write, change or
  delete it. It is a pointer; the ledger is the record. A forged trailer
  resolves to entries that either do not exist or do not verify.
- **Without a witness, a re-signed fork of the whole ledger still verifies.**
  Signature verification detects a changed entry and a broken chain link. It
  does not, by itself, detect wholesale replacement by someone holding the
  signing key. `verify.py` says so in its own output rather than letting a
  reader infer more than was proven.
- **Coverage is not correctness.** That a bundle contains the claimed entries,
  and that those entries verify, says the record is intact — not that the work
  it describes was good.
