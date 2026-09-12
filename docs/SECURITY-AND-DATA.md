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
