# Security and data handling

**For the person who has to approve this before anyone installs it.**

Meridian Loom 0.1.0 · sideloaded VSIX · last reviewed 12 September 2026

Every statement here is checkable against the source in this repository. Where
something is a limitation, it is written as one — a security review that finds
an omission you did not disclose is worse than the omission.

---

## 1. What the software is

A VS Code extension plus a local Python process ("the sidecar"). It records
what AI coding agents do in a repository, applies permission policy to them,
and writes a tamper-evident log of the result.

**It contains no AI model and makes no model calls.** It governs agents you
already run and pay for. This is enforced by a test that fails the build on any
model-client import in the recording paths (`core/tests/test_no_model_calls.py`,
`extension/test/no-model-calls.test.ts`).

## 2. Where data goes

**Telemetry: none.** The extension makes no network connection on its own.
The only egress paths are operator-configured: the model provider the
workspace binds (sidecar), the adapter/skill registry URL
(`extension/src/adapters/registry-source.ts`), connector endpoints
(M19, `extension/src/workbench/integrations.ts`), and the headless
collector's opt-in `--sink`. A CI guard fails the build if any unreviewed
network client appears in the host or webview sources
(`npm run check:telemetry`, audit TASK-104).


**Everything is local by default.** The record lives in the repository you open:

| Location | Contents |
| --- | --- |
| `<workspace>/.meridian/ledger` | the hash-chained log, encrypted content blobs, signing metadata |
| `<workspace>/.meridian/workbench` | agent profiles, skills, instruction documents, run history |
| `<workspace>/.meridian/policy` | this workspace's permission policy |
| OS keychain | credentials for any tool integration you configure |

There is **no Meridian server**, no account, and nothing to sign up for.

### Outbound network connections

There are exactly three ways this software opens a network connection, and all
three are things you turn on:

1. **Tool integrations you configure.** GitHub, GitLab, Jira, Slack, Postman,
   Datadog, Kubernetes and similar. Nothing connects until you create a
   connection and supply a credential. **Every integration operation is a
   read.** Nothing creates an issue, triggers a pipeline, posts a message or
   restarts a workload.
2. **The agent you bind.** Launching `npx @zed-industries/claude-agent-acp` or
   similar runs that vendor's software, which talks to that vendor. Meridian
   starts the process; the traffic and the terms are the vendor's.
3. **A witness endpoint, if you configure one.** Optional, off by default, and
   a no-op when unset (`NullReceiptStore`). See §6.

### Telemetry

**None.** There is no analytics, crash reporting, usage tracking or phone-home
of any kind. Nothing about your usage is transmitted anywhere.

The agent runtimes offered on an agent card are shipped inside the package as
a static list, so even choosing one does not call out.

## 3. Credentials

- Integration credentials go to the **OS keychain** (VS Code `SecretStorage`)
  and nowhere else — never the workspace, never an export, never a log.
- If the keychain is unavailable the save is **refused** rather than falling
  back to a file.
- A stored credential is never shown back, **not even masked**, because a mask
  leaks the length.
- Credentials are never placed in process arguments, which are readable by
  other processes on the machine. The service refuses agent arguments matching
  credential-like patterns.
- Errors are passed through a redactor before display or storage.
- No `MERIDIAN_*` environment variable is inherited by any process the sidecar
  starts — git, language servers, sandboxed tool runners. This is enforced
  structurally: a test fails the build if any process spawn omits the scrubbed
  environment (`core/tests/test_childenv.py`).

## 4. What agents are allowed to do

Agents are constrained by a policy file **in your repository**, versioned and
reviewed like any other code (`.meridian/policy/acp-permissions.yaml`).

The shipped default is deliberately restrictive: a newly added agent is on
**probation** and may only `read` and `search`. It cannot edit or execute until
someone widens the policy. Agents that ship in the box arrive the same way, in
Learning mode, with no executable bound.

Policy is checked **before** the user is prompted, so a tool class the policy
does not cover is denied without a prompt that could be click-throughed.

## 5. The record

Entries are hash-chained and signed with Ed25519. Exports carry Merkle
inclusion proofs, a signed tree head, the public key, the schema version and
the collection profile in force.

**Nothing acts before it is recorded.** A run's first ledger entry — carrying
the run id and the door it came through — is written *before* its worktree and
branch are created. The order is what makes the two failure states legible: an
entry with no worktree is a run that plainly did not start, while a worktree
with no entry would be unexplained work on a branch nobody can account for.

**An export verifies without Meridian installed.** A single standard-library
Python file (`verify.py`) ships in the package; hand it and a bundle to an
auditor who has never heard of this tool. The `Meridian-Ledger:` commit trailer
is a published, versioned specification with a reference parser, so a third
party can go from `git log` to verified evidence unaided.

### Content capture is off by default

The default collection profile is `metadata_only`: prompts and outputs are
**not** persisted. Two other profiles exist — `content_redacted` (captured,
with credential-shaped strings redacted) and `content_full` (requires recorded
consent). The profile in force travels inside every export, so a reader can
tell an absent field from a withheld one.

Subject content can be erased on request. Erasure is **crypto-shredding**: the
subject's key is destroyed, its content becomes permanently unreadable, and the
chain remains intact and still verifies.

### Other tools' provenance records

If another provenance tool is already working in your repository — writing
git notes under its own ref, session trailers, co-author lines — Meridian can
read those records and **notarise** them: the digest of the record goes into
the signed ledger.

What that buys you is narrow and real. A note in a repository is a mutable
blob, and anybody who can write the repository can rewrite what it says about
what an agent did last March. Once Meridian has notarised it, a third party
can prove the record has not been altered since Meridian read it.

What it does not buy:

- **Meridian did not observe the work.** It read a file claiming the work
  happened. Every foreign record is attributed to the tool that wrote it and
  recorded at `inferred` — the bottom rung — and there is no path in the code
  that produces anything else for one.
- **Notarising is not endorsing.** Meridian signs the digest, not the claim.
  The ledger entry carries that sentence, because a signature sitting beside
  somebody else's assertion gets read as a signature *on* it otherwise.
- **The content is not copied.** Only the digest is recorded. Meridian is not
  the custodian of another tool's data, and taking a copy — even a tidy
  structured one — would make it one, with the retention and erasure
  obligations that follow. Notarisation runs only when you ask for it: it is not part of the commit hook and adds nothing to a commit.

The record itself is untrusted input: parsed under an allow-list, never
executed, and capped in size with oversize reported rather than silently
dropped. A record that has been **removed** since it was notarised is
reported as gone, not as altered; a tool cleaning up its own notes is
ordinary and accusing it of tampering would make the check worthless.

**When two records disagree, you are told, and nothing is decided for you.**
One tool's note may name one agent for a commit while another record — a
co-author line, a session trailer, another tool's note, or Meridian's own
ledger — names a different one. Meridian then reports a disagreement with every
claim beside it, and does not choose. That includes its own ledger: a signed
entry proves what Meridian recorded, not that the other record is wrong.
Recording a disagreement is a separate action, and what goes into the ledger is
the digests of the records, never their content. Two limits:

- the comparison is per commit, so a disagreement about some lines of a commit
  is reported about the whole commit;
- a report covers only the history it walked, and says so when it stopped early.

## 6. Limitations we are telling you about

- **Without a witness, a re-signed fork of the whole ledger still verifies.**
  Signature verification detects a changed entry and a broken chain link. It
  does not, by itself, detect wholesale replacement by someone holding the
  signing key. The verifier says so in its own output. A witness endpoint is a
  configuration seam; the hosted witness service does not exist yet.
- **The commit trailer is editable.** Anyone with commit access can change or
  delete it. It is a pointer into the record, not a proof; the ledger is the
  record.
- **Enforcement is in the editor, not the SCM.** The merge gate binds an
  approval to a commit digest and invalidates it when the code changes, but a
  developer who does not use Meridian is not stopped by it. Exporting the gate
  as a required SCM status check is specified and deliberately unbuilt: the
  binding has to be chosen with a platform team that exists (`DECISIONS.md`,
  D37).
- **Identity is asserted, not verified, by default.** Git `user.name` and
  `user.email` are locally set and spoofable. Meridian records which assurance
  level was used, and policy can require a verified (OIDC-backed) identity —
  but the default is `asserted` and it is labelled as such.
- **Effectiveness is unmeasured.** The project's own gate for claiming this
  improves delivery outcomes — twenty real stories through a real team,
  measured — has not been run. We make no productivity, quality or ROI claim.

## 7. Supply chain

- No runtime dependency is copyleft; all are Apache-2.0, MIT, BSD or ISC.
  Bundled fonts are SIL OFL-1.1 (attribution only).
- The Python sidecar's evidence path is standard library only — the Ed25519
  verification is a pure-Python RFC 8032 implementation with no crypto
  dependency to audit.
- The extension bundle is built by `esbuild` from sources in this repository.
- **The package is unsigned.** VS Code does not sign sideloaded VSIX files, so
  the integrity check available to you is the digest published beside it as
  `meridian-loom-<version>.vsix.sha256`. Compare before installing:

  ```console
  sha256sum -c meridian-loom-0.1.0.vsix.sha256      # Linux, macOS
  Get-FileHash meridian-loom-0.1.0.vsix -Algorithm SHA256   # Windows
  ```

  This proves the file was not altered in transit from whoever gave it to you.
  It is not a signature and does not establish who built it.

### Agents you install from somewhere else

Three separate things are checked, and each one proves less than the next one
sounds like it does.

- **The adapter folder is pinned by content digest.** Whatever Meridian
  installs — from the ACP Registry or from a package you supplied — is
  digested at install and checked on every load. A folder that has changed
  since does **not** load, and the refusal names the digest recorded at
  install and the digest on disk, so you can tell your own edit from somebody
  else's. The refusal is recorded in the ledger as well, with both digests and never the adapter's contents. The adapter's own `learned/` directory is excluded, because it is
  where the adapter records what it learned and pinning it would make every
  adapter drift the moment it learned anything.

  A pin proves the bytes did not change. It says nothing about whether they
  were trustworthy when they arrived.

  An adapter you placed in the folder yourself is reported as **unpinned**,
  not as passing. There is no baseline to compare it against.

- **The agent binary is identified where it can be.** Before an agent is
  launched, Meridian resolves its command against `PATH` and digests the file
  it found. If that digest changes under an unchanged name, you are told —
  this is the case where the agent's own self-reported name and version
  cannot help you, because both are claims.

  **This does not work for the common case, and it says so.** When the launch
  command is `npx`, `uvx`, `pipx run` or `bunx`, the file on `PATH` is the
  package fetcher and the agent is downloaded afterwards. Meridian reports
  identity as `unverified` and names the fetcher rather than passing the npx
  shim's digest off as the agent's. To get a verifiable identity, point the
  command at an installed executable.

- **A registry listing is a publication, not a recommendation.** Meridian can
  browse the ACP Registry and install from it. That a thing is listed
  establishes that somebody published an entry under that name. It is not a
  review, not a security assessment, and not an endorsement — neither by the
  registry nor by Meridian, and installing one is a decision you are making
  about somebody else's code.

  The index is fetched **only when you ask**, never on activation; the
  no-phone-home statement in §2 covers this feature too. The index is treated
  as untrusted input: it is parsed under an allow-list, only known fields
  reach the interface, and nothing in it is executed. An installed entry
  enters Learning with `read`, `search` and `think` and no command binding,
  exactly like an imported agent — there is no registry fast path.

## 8. Removing it

One command, documented, and it tells you what it will delete before it
deletes anything:

```console
python -m meridian_core.cli uninstall --workspace .
```

A bundle exported beforehand still verifies afterwards. That is a tested
property, not an intention — the test exports, deletes every trace of Meridian
from the workspace, and then verifies the bundle.

See [`evidence-portability.md`](spec/evidence-portability.md) for the full
export, erase and uninstall paths.

---

**Questions this document does not answer** should go to the repository's issue
tracker rather than being guessed at from it.
