# Tracking: native ACP support in VS Code

> Pointer from `extension/src/acp/UPSTREAM.md` (FR-M34-05, `R26`).
> This file is the repo's living note on the open VS Code issue; keep it
> current when the issue moves.

## What to track

- **Issue:** [microsoft/vscode#265496 — "Add support in vscode for Agent
  Client Protocol (ACP)"](https://github.com/microsoft/vscode/issues/265496)
  (opened 2025-09; uncommitted by Microsoft as of this writing — the
  ecosystem currently uses community ACP-client extensions).
- **Signal, in order of weight:**
  1. Microsoft commits to native ACP on an iteration plan (the issue is
     assigned to a milestone / feature area).
  2. A proposed API or built-in chat participant surface speaks ACP in
     insiders.
  3. The issue is closed as *won't-fix* — then Meridian's host is the VS
     Code ACP host for the foreseeable future and upstream publication
     (UPSTREAM.md) becomes the primary contribution path.

## How Meridian layers when native support lands

The commitment (restated from UPSTREAM.md, in execution order):

1. **Governance layers on whatever host exists.** Tier gate, policy
   pre-check (SEC-28), ledger recording and worktree isolation already ride
   injectable seams — they re-base onto the native host's extension points.
   The value is the ledger and gates; the host is replaceable by design.
2. **No duplicated protocol.** Native-covered surfaces get Meridian's
   parallel implementation deleted, not maintained (G2).
3. **MCP exposure is unaffected.** VS Code's native agent mode reaches
   Meridian's ledger and gates through the MCP server (`mcp/invoke`,
   FR-M34-06) regardless of who hosts ACP sessions.

## Review cadence

Check the issue at each F-phase exit (F1 exit is the next one). Record the
last-checked date below and any change in signal weight.

- Last checked: 2026-09 (F1 Workstream A, task 7) — no Microsoft
  commitment; community extensions are the current path.
