# Deploying Meridian Loom

**For whoever is rolling this out to a team.** Version 0.1.0, sideloaded VSIX.

Read [`SECURITY-AND-DATA.md`](SECURITY-AND-DATA.md) first if you are the one
approving it; this document assumes that decision is made.

---

## 1. Before you start

| Requirement | Why | Check |
| --- | --- | --- |
| VS Code 1.95+ | the extension API it is built against | `code --version` |
| Python 3.11+ | the sidecar (governance, ledger, metrics) | `python --version` |
| Node.js 20+ | only if agents are launched via `npx` | `node --version` |
| An agent account | Meridian governs an agent; it is not one | see §4 |

### Tested platforms

<!-- BEGIN GENERATED: compatibility (scripts/check-compatibility.mjs) -->

| Dimension | Supported | Backed by | Last passed |
| --- | --- | --- | --- |
| Operating system | Windows 11 | `extension/test/remote.test.ts` | 2026-09-12 |
| Operating system | Linux (current Ubuntu LTS) | `extension/test/stdio-e2e.test.ts` | 2026-09-12 |
| Operating system | macOS (current and one prior major) | `extension/test/stdio-e2e.test.ts` | 2026-09-12 |
| Editor | VS Code 1.95 or later | `extension/test/manifest.test.ts > declares granular activation events and never "*" (FR-M1-01)` | 2026-09-12 |
| Python | Python 3.11 | `extension/test/stdio-e2e.test.ts` | 2026-09-12 |
| Python | Python 3.12 | `extension/test/stdio-e2e.test.ts` | 2026-09-12 |
| Remote | Remote development (SSH, WSL, Dev Containers, Codespaces) — declared, not yet rehearsed | `extension/test/remote.test.ts > declares extensionKind "workspace" so the sidecar runs on the remote host` | 2026-09-12 |

**A combination not in this table is not claimed.** Adding a row requires a passing smoke test in the same change; a row that cannot be backed is removed rather than marked degraded.

<!-- END GENERATED: compatibility -->

Meridian does **not** bundle a Python runtime. It finds an interpreter through
VS Code's Python extension, then `python3`/`python` on `PATH`, and you can pin
one explicitly (§3).

## 2. Installing

```console
code --install-extension meridian-loom-0.1.0.vsix
```

Verify the artefact's checksum against the one published with it first — the
VSIX is unsigned, as all sideloaded VS Code extensions are.

For many machines, this is the line to put in your existing endpoint-management
or dev-container provisioning. There is no installer, no service, no daemon and
no account to provision.

### Validate the rollout without opening an editor

```console
cd <extension>/sidecar
python -m meridian_core.cli doctor --workspace /path/to/a/repo --signing-key-file /path/to/signing.key
```

Exit status `0` means no check failed and `1` means one did, so this can be the
last line of a provisioning job. It prints JSON: interpreter, sidecar, signing
key, ledger integrity, git hooks and observer health — the same check registry
the editor's **Meridian Loom: Doctor** command runs, so the two cannot disagree.

**Ledger integrity is only checked when you pass the signing key.** With
`--signing-key-file` (or `MERIDIAN_LEDGER_SIGNING_KEY`) doctor opens the ledger,
verifies the whole chain, and exits `1` if any entry has been altered. Without a
key it reports the ledger check as a warning saying it could not look — it does
not pass a chain it never checked. Observer health is only known inside a
running editor, so a headless run always reports it that way.

## 3. Settings worth setting centrally

Push these through your usual VS Code settings policy or a workspace
`.vscode/settings.json`:

| Setting | Why you would set it |
| --- | --- |
| `meridian.python.interpreterPath` | pin the interpreter instead of relying on discovery order |
| `meridian.tiers` | which capability tiers are on (see §5) |
| `meridianLoom.surface` | `editor` (default) or `sidebar` |
| `meridian.sidecar.handshakeTimeoutMs` | raise it if first launch is slow on managed machines with aggressive antivirus |

## 4. Binding an agent

Meridian contains no AI. Each agent profile needs an ACP-speaking executable,
and your people need accounts with that vendor.

Four are offered as one-click presets on every agent card: Claude Agent, Gemini
CLI, Codex CLI and Minion Code. Choosing one sets the command; it does not
install anything or sign anyone in. The list ships inside the package, so this
choice makes no network call.

Authentication is that vendor's own — an account sign-in or an API key in the
environment. **Meridian never asks for, stores or transmits it.** Decide
centrally which vendor your organisation is licensed for before rollout, or
people will each pick differently.

## 5. Tiers

`meridian.tiers` controls which capabilities exist. Changing it takes effect
immediately — no reinstall, no reload.

| Tier | What it adds |
| --- | --- |
| `flight-recorder` | always on: observation, the ledger, attribution, evidence export |
| `governor` | **required to run agents from Meridian**; gates, approvals, spend ceilings |
| `orchestra` | multi-agent orchestration |

A disabled tier is **absent**, not greyed out. Flight Recorder alone is a
legitimate deployment: observe what agents your teams already run, and record
it, without Meridian running anything.

## 6. Policy is a file in the repository

Permissions live in `.meridian/policy/acp-permissions.yaml`, in the repository —
versioned, reviewed and PR'd like any other code. On first run Meridian copies
shipped defaults there and says it has done so.

The default is restrictive: a new agent may only `read` and `search`. If your
pilot expects agents to edit files, widen it deliberately:

```yaml
version: 1
adapters:
  '*':
    probation: [read, search, edit, execute]
```

Commit that file. Central control of this policy is control of what every agent
in that repository may do.

## 7. A sensible rollout order

1. **Flight Recorder only, one team, one repository.** Governor off. Nothing
   runs agents; Meridian records the agents people already use. Low risk, and
   it answers "what is actually happening in our codebase" before you change
   anything.
2. **Export a bundle and verify it** with `verify.py` on a machine that has
   never had Meridian installed. Do this early. If the evidence story does not
   satisfy your auditors, better to learn it in week one.
3. **Enable Governor for the same team.** Bind one agent, keep the probation
   floor, let a refusal happen and watch it get recorded.
4. **Widen the policy deliberately**, one capability at a time.
5. **Then decide about more teams**, on evidence you collected rather than on
   anything claimed here.

## 8. Backup and retention

The ledger is a SQLite database plus encrypted blobs under
`<workspace>/.meridian/ledger`. Back it up the way you back up the repository —
it lives in the same place.

Two things to know:

- **A backup taken before an erasure still holds the erased key.** Restoring
  one restores readability. Replay the erasure into any restored copy; the
  erasure entries in the live ledger are what makes that possible.
- Archive and compaction exist for multi-year retention, and an archived entry
  still verifies against its signed tree head after restore.

## 9. Leaving

```console
python -m meridian_core.cli uninstall --workspace .
```

Lists what it would remove and deletes nothing until you add `--yes`. Export
first. A bundle exported before uninstalling still verifies afterwards.

Uninstalling the extension itself is ordinary VS Code:
`code --uninstall-extension meridianloom.meridian-loom`.

## 10. Known limitations that affect a rollout

- **A developer who does not use Meridian is not gated by it.** Enforcement is
  in the editor; exporting the merge gate as a required SCM status check is
  specified but unbuilt (`DECISIONS.md`, D37).
- **Git identity is asserted, not verified**, by default.
- **Without a witness, ledger replacement by a signing-key holder is not
  detectable** by signature verification alone.
- **No effectiveness claim is made.** The evidence gate for that — twenty real
  stories, measured — is exactly what a pilot is for.

Full detail in [`SECURITY-AND-DATA.md`](SECURITY-AND-DATA.md) §6.
