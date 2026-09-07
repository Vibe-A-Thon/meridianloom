# Upstream publication plan for the Meridian ACP host

> FR-M34-05 (SHOULD v1): Meridian contributes its ACP host implementation
> upstream under Apache 2.0 where the VS Code ACP integration is concerned,
> and tracks the open VS Code issue so that if Microsoft ships native ACP,
> Meridian layers on it rather than duplicating it.
>
> Risk this answers: `R26` — Microsoft ships native ACP in VS Code and
> Meridian's host is obsolete. The value Meridian keeps in that world is the
> ledger and gates, not the host — so the host is built to be given away.

## What is host-generic (publishable as-is)

These pieces are a plain TypeScript ACP **host/client** for any
Node-capable editor extension. Nothing in them assumes Meridian:

| Module | Host-generic content |
|---|---|
| `client.ts` | Subprocess lifecycle (spawn → initialize negotiation → session/new\|load → prompt → teardown, Windows-robust tree kills), streaming `session/update` re-emission, injectable approver seam (default deny), client-provided `fs/read_text_file` / `fs/write_text_file` rooted at the workspace with a path-escape guard, host-served `terminal/*`, crash-mid-turn → named rejection (never a hang). |
| `protocol.ts` | The pinned SDK re-exports and the wire types an ACP host needs. |
| `permissions.ts` | The vscode window prompt as one implementation of the approver seam — the seam itself, not this file, is the publishable unit. |
| The conformance suite (`test/acp-conformance.test.ts`, `test/acp-client.test.ts`) | Runs the host against fake agents over real stdio; reusable by any ACP host. |

## What is Meridian-governance-specific (stays in Meridian)

- The **tier gate** at the entry point (`index.ts`): hosting is a Governor
  capability; a disabled governor hosts nothing while Flight Recorder keeps
  working (G5). Upstream, this becomes a plain enable/disable, because a
  generic host has no tiers.
- The **policy pre-check** (`../adapters/permission-gate.ts`,
  `../adapters/policy.ts`, SEC-28): the agent's `session/request_permission`
  is checked against Meridian policy and the adapter's tier *before* the
  human sees the prompt; re-requesting cannot escalate. Upstream this is a
  hook ("consult policy before prompting"), with Meridian's implementation
  as one consumer.
- **Ledger recording** (sidecar RPCs `acp/sessionBegin`, `acp/sessionEnd`,
  `acp/permissionDecision`): every hosted-session fact is appended to the
  open ledger. Upstream this becomes an event/telemetry seam; Meridian
  subscribes and records.
- **Worktree isolation** (`worktree/*` sidecar RPCs, task 5): hosted agents
  write only in a per-story worktree. Upstream this maps to the host's
  client-provided fs root; Meridian keeps the stronger guarantee.

Layering rule of thumb: **protocol mechanics are host-generic; policy,
provenance and isolation are Meridian.** The boundary between `acp/` and
`adapters/` is drawn exactly on that line.

## Publication plan (Apache 2.0)

1. **Extract** the host-generic table above into a standalone package
   (`meridian-acp-host` or contributed directly to a VS Code ACP
   integration effort), with the governance hooks as injectable seams, not
   imports. No Meridian module may be reachable from the published tree.
2. **License**: Apache 2.0, per FR-M34-05. Note: the repo carries no
   LICENSE file today — that is deliberate (DECISIONS.md `D22`, the F−1
   legal gate is human-gated and still open). The LICENSE file is added as
   step zero of publication, by the human owner, not by the build.
3. **Tests travel with the code**: the conformance and client suites run
   against the extracted package unchanged.
4. **Reference consumer**: Meridian's extension keeps depending on the
   published package and layers governance back through the seams.
5. **CI seam** (this repo, today): `test/acp-upstream-version.test.ts`
   warns — never fails — when the pinned ACP SDK drifts from the supported
   version declared here, so publication preparation never silently rots.

## Layering strategy if VS Code ships native ACP (`R26`)

Tracked in `docs/upstream/vscode-acp-issue.md`
(microsoft/vscode#265496). The commitment, in order:

1. **Governance layers on whatever host exists.** The moment native ACP
   exists, Meridian's host becomes a fallback for older VS Code versions
   and a reference implementation; the tier gate, policy pre-check, ledger
   recording and worktree isolation re-base onto the native host's
   extension points. The value — ledger and gates — is host-agnostic by
   construction (it already rides injectable seams).
2. **No duplicated protocol.** Where native support covers a surface,
   Meridian's implementation of that surface is deleted, not maintained in
   parallel (G2: where a standard won, implement the standard).
3. **The MCP exposure (FR-M34-06) is unaffected**: it speaks MCP to any
   client and talks to the sidecar, not to the ACP host — VS Code's native
   agent mode gets Meridian's ledger and gates through it either way.

## Supported ACP SDK version

The host pins the official Zed SDK. Drift from the version below is a
warning in CI, not a failure — but publication preparation should bump it
deliberately, with the conformance suite green.

<!-- supported-acp-sdk: 0.4.5 -->
- **Supported**: `@zed-industries/agent-client-protocol` **0.4.5**
  (declared in `extension/package.json`; the conformance suite's capability
  set and protocol negotiation target this revision).
