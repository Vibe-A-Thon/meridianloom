# Support, upgrades, and leaving

What an organisation can plan around. `MVP-R8.3`, `NFR-55`, `AC-71`.

This product's central promise is that you can **operate it and leave without
talking to us**. That promise is worth nothing if the terms of it are not
written down, so here they are — including the parts that are thinner than a
buyer would like.

## Supported versions

| Version | Status |
| --- | --- |
| `0.1.x` | **Current.** Fixes land here |
| earlier `0.0.x` pre-releases | Unsupported. Upgrade; the state migrates |

One supported line, because one maintainer cannot honestly maintain two.
When `0.2.0` ships, `0.1.x` receives **security fixes only, for 90 days**,
and then nothing.

## What counts as a breaking change, and the notice it carries

A change is breaking if, after upgrading, something that worked stops
working without you doing anything: a removed RPC method or command, a
renamed setting, a change to the ledger schema that an older sidecar cannot
read, or a narrowing of what an existing policy file is allowed to say.

| | Notice |
| --- | --- |
| Breaking change | Announced in the release notes of the release **before** it lands, and again in its own |
| Removal of a deprecated thing | Not less than **one minor version** after it is first marked deprecated |
| Ledger schema change | Migration ships with it, runs on open, and is one-way — see below |

A change to a documented *limitation* — something moving from "cannot" to
"can" — is not breaking and carries no notice. It does update
`docs/claims.md`, which is where the current set of claims lives.

## What survives an upgrade

- **Every ledger entry.** The chain is append-only and schema migrations add
  columns; they do not rewrite history. An upgrade that could not preserve
  acknowledged entries would fail the release (`NFR-42`), not ship with a
  note.
- **Your workspace state** — agents, skills, instruction documents,
  integrations, learning notes — in `.meridian/`.
- **Your policy files.** `.meridian/policy/*.yaml` is yours; the product
  scaffolds defaults into it once and never edits them afterwards.
- **Blob keys**, and therefore your ability to read recorded content.

**Migrations are one-way.** A ledger migrated forward cannot be read by the
previous sidecar. Take an export before a major upgrade if you need the
option to go back — which is the same export the next section is about, so
the cost of insurance here is one command.

## Leaving

The exit path is not a promise; it is a feature with tests behind it.

1. **Export a signed evidence bundle** — Evidence → Audit ledger → Export.
   It carries the entries, the Merkle inclusion proofs, a signed tree head,
   the public key, the schema version and the collection profile in force.
2. **Verify it with nothing of ours installed.** `verify.py` ships inside the
   package and is a single standard-library Python file. Hand it and the
   bundle to an auditor who has never heard of this tool.
3. **Take the workspace.** `.meridian/` is plain files — YAML policy,
   JSON state, Markdown agents and skills. Nothing needs this product to be
   read.
4. **Uninstall.** `docs/SECURITY-AND-DATA.md` §8. Removing the extension
   leaves your repository as it was; the worktrees Meridian created are
   removed with their stories and never touched your primary working tree.

Nothing in the export is encrypted to a key only we hold. There is no
licence server, no activation, and nothing that stops working when a
subscription does — because there is no subscription.

## What support actually means today

There is no commercial support offering, and pretending otherwise would be
the kind of claim the rest of this repository is built to prevent.

| | |
| --- | --- |
| Bugs and questions | GitHub issues, best effort |
| Security reports | `SECURITY.md`, with the response times stated there |
| Response time for anything else | **Not committed.** One part-time maintainer |
| Paid support, SLAs, professional services | **None.** No offering exists |

If you need a contractual support commitment before adopting this, the
honest answer today is that it does not exist yet — not that it can be
arranged. That is worth knowing before a pilot rather than after one.
