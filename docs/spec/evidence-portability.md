# Keeping, reading and leaving with your evidence

**Requirements:** FR-M43-12 (headless collector and verifier), FR-M43-13
(exports stay readable), NFR-39 (verification on a clean machine).

Everything here works with **no extension, no editor and no running sidecar**.
It reads and writes the same `.meridian/` folder the extension uses.

```console
python -m meridian_core.cli --help
```

In an installed extension the package sits at `<extension>/sidecar`, so:

```console
cd <extension>/sidecar && python -m meridian_core.cli --help
```

---

## What Meridian has written, and where

```console
python -m meridian_core.cli paths --workspace .
```

Prints every artefact, what it is for and how large it is. Nothing is hidden
in a home directory or a cloud account: the record lives in the repository you
pointed Meridian at.

| Path | What it holds |
| --- | --- |
| `.meridian/ledger` | the hash-chained ledger, its encrypted blobs and signing metadata |
| `.meridian/workbench` | agents, skills, instructions and run history |
| `.meridian/policy` | this workspace's permission policy overrides |
| `.meridian/worktrees` | isolated story worktrees, if any remain |
| `.meridian/state` | pending commit-trailer records |

Credentials are **not** in this list. Integration secrets go to the OS
keychain and never to the workspace.

## Export

```console
python -m meridian_core.cli export --workspace . --out bundle.json \
    --signing-key-file ledger.key
```

Optional `--from-sequence`, `--to-sequence` and `--story` narrow the range.

The bundle carries the entries, a signed tree head, Merkle inclusion proofs,
the public key, **the ledger schema version** and **the collection profile in
force**. The last two are what make it readable years later by someone who
does not have us to ask: the schema version says what shape the entries are,
and the redaction section says whether an absent field means "nothing
happened" or "policy said do not record it". Those are different facts and the
difference cannot be recovered from the entries alone.

### Why it asks for a signing key

Export refuses to run without one rather than falling back to a throwaway key.
A bundle signed by a key nobody has ever seen verifies perfectly and proves
nothing, which is worse than no bundle at all — it looks like evidence.

Supply it with `--signing-key-file` (32 raw bytes or 64 hex characters) or
`MERIDIAN_LEDGER_SIGNING_KEY` in the environment. In the editor the key comes
from the OS keychain; headless, you provide it, because headless there is no
keychain prompt and no user to answer it.

## Verify

```console
python -m meridian_core.cli verify bundle.json
```

This runs `verify.py` — the same standalone reference verifier an outsider
runs, invoked as a subprocess rather than imported, so what is checked is the
artefact the claim is about. You can equally run it directly, which is what to
hand an auditor:

```console
python <extension>/sidecar/verify.py bundle.json
```

It reports three separate verdicts: whether the signature is valid, whether
the signer is one you trust, and whether the evidence covers what is claimed.
Read them rather than the exit code alone — a valid signature from an unknown
signer is a meaningful answer, not a pass.

To go from a commit to the entries behind it, see
[the `Meridian-Ledger` trailer specification](meridian-ledger-trailer.md).

## Erase a subject

```console
python -m meridian_core.cli erase --workspace . \
    --subject <id> --reason "erasure request" --signing-key-file ledger.key
```

This is **crypto-shredding**, not deletion. The subject's key is destroyed, so
its content becomes unreadable for good, while the entries and the hash chain
remain intact and still verify. That is deliberate: deleting entries would
break the chain and destroy everyone else's evidence along with that subject's.

Three things to know, none of them obvious:

- The erasure is itself recorded as chain entries, so the fact that it
  happened is part of the record.
- **A backup taken before now still holds the key.** Restoring one restores
  readability. Replay the erasure into any restored copy — the erasure entries
  in the live ledger are what makes that possible.
- Archived (cold) blobs are covered too. The key is the erasure, not the file,
  so a cold copy is as unreadable as a hot one.

## Leave

```console
python -m meridian_core.cli uninstall --workspace .
```

Lists what would be removed and deletes **nothing**. It also points you at
`export` first, because the alternative is discovering afterwards that leaving
meant losing the record.

```console
python -m meridian_core.cli uninstall --workspace . --yes
```

Removes the workspace data, and removes `.meridian` itself if nothing else is
using it. Uninstalling the extension is separate and is done in the editor;
this command only removes what was written into the workspace.

**A bundle you exported before uninstalling still verifies afterwards.** That
is a tested property, not an intention: the test exports, deletes every trace
of Meridian from the workspace, and verifies the bundle.

---

## Compare two bundles

Two bundles of the same change, from two editors or two SCM providers, differ
in almost every value. What must not differ is what a reader needs in order to
interpret either one. `compare-evidence` checks both halves:

```console
python -m meridian_core.cli compare-evidence first.json second.json
```

It runs `verify.py` on each bundle, then compares their evidence shape: the
format and schema versions, the sections present, the fields an entry carries
and the type of each, and the redaction, enforcement and compliance structure.
Values such as timestamps, keys, vendors and approvers are not compared. A
field that is empty in one bundle and filled in the other is not a difference;
a field that is text in one and a number in the other is. **Exit 0 means both
bundles verify and their shapes agree.**

This is the check `AC-50` needs: two editors, two SCM providers, one evidence
shape. That test itself has not been performed. It needs a customer, and a
second editor that the compatibility matrix supports.

## Export for other tools

Meridian's attribution can be read without Meridian, in two formats:

```console
python -m meridian_core.cli export-attribution --workspace . \
    --format attribution-json --out attribution.json
python -m meridian_core.cli export-attribution --workspace . --format git-notes --write
```

- **`attribution-json`** (`meridian-loom/attribution-export@1`) lists every
  line of the files asked for, grouped into spans by the commit that
  introduced them. Each commit is attributed as agent, human or unattributed,
  with its evidence and confidence, and each file carries counts. A line
  Meridian cannot attribute is counted as unattributed, never as human. No
  line content is included.
- **`git-notes`** writes one JSON note per commit
  (`meridian-loom/commit-attribution@1`) under
  `refs/notes/meridian-attribution`, so any tool that reads git notes can read
  them. Without `--write` it only reports what it would write. A note that
  already says the same thing is left alone, and the notes are authored as
  Meridian Loom rather than as whoever ran the command.

In both formats, a commit whose records disagree about who produced it carries
the disagreement's digest, unresolved: see
`python -m meridian_core.cli` and the Evidence screen's Provenance
reconciliation tab. Given the signing key, Meridian's own ledger evidence is
included; without it the export is made from git evidence alone and says so.

**Neither format claims to match another tool's schema.** Other tools'
formats are described in this project's competitive review, but none is
specified here, and a compatibility nobody has checked is not a claim this
document makes.

## What is not built yet

**FR-M43-14 — opt-in export to OTLP and evaluation systems.** Not
implemented. When it is, the rule it has to keep is that those systems receive
a *copy* and never become the record of authority: the ledger stays the thing
that decides what happened, because a record you can edit in a dashboard is
not a record. Until it ships, the honest answer is that you can export bundles
and route them yourself.
