# MERIDIAN LOOM — Build State

> Resumption state. Updated after every completed task. If the session is interrupted, read this file and DECISIONS.md first, then continue from the recorded task.

**GOVERNING ORDER (changed mid-build — see DECISIONS.md G-0):** the repo owner committed `gaps-requirements.md` + `gaps_implementation.md` (+ `gaps_guix.md`, `gaps_guix_implementation.md`), which supersede the S0 → GUI → C1…C6 sequencing. New order: **F−1 (legal gate, human-gated — see DECISIONS.md) → F0 Flight Recorder → F1 Governor → F2 Evidence Gate (human-run) → F3 Orchestra → F4+ (old C3–C6).** All six original spec files remain requirement sources; copies of all ten docs are in `docs/spec/`.

- **Current phase:** F1 — Governor
- **Current workstream:** G — Remaining observers — **done**
- **Current task:** workstream H next — GF1 screens (task 31: 10.1 Command Center, 10.6 Gate Room, 10.27 Decision Stream, 10.28 Steer & Clarify, 10.32 Roles, 10.47 Trust Observatory, 10.49 Cross-Vendor Spend, 10.43 Adapter Bay, 10.16 Inspector, 10.50 Unlock; task 32: X-31 parity check — human-timed, 5 engineers). Webview paths belong to the parallel session; my half is extension-host plumbing incl. the D33 `spend/ceiling` pause handler.
- **Last commit:** 2289a36 — workstream G done (task 30): Cursor/Codex/Devin observers at telemetry-trailer/inferred floor (D34), never direct, NFR-32 degrade per vendor, pid-scoped X-29 tests; 39 new tests + 74 observer-suite + 106 no-regression all green; no new RPCs (reuse observe/sessions, observe/health). Workstream F complete at 3608ecd (D33 host-side pause OPEN). Workstream E complete at f3cafd3. Decisions D28–D34 in DECISIONS.md. (FR-M25-01/02/03/04/06 + honest observe-only controls NOT_HOSTED; extension vitest 347; note: shared-index incident with the parallel session repaired via plumbing, final tree byte-identical, nothing pushed)
- **Orchestrator note:** parallel session works in this tree — never stage or overwrite files outside your task; stage by explicit pathspec. FR-M18-06/09 out of F1 scope per gaps plan (SHOULD v1.x).

## Mapping of completed S0 work onto the new plan

| Old (S0) | New (F0) | Status | Proof |
|---|---|---|---|
| A1 scaffold (FR-M1-01..03) | F0-A1 | done — fuller superset (5 views, 12 commands) retained, see DECISIONS.md G-0 | `manifest.test.ts`, commit 4e52a8a |
| A2 thread discipline (FR-M1-04) | — (baseline) | done | `thread-discipline.test.ts`, 2a7a1f6 |
| A3 SecretStorage adapter (FR-M1-06/07) | F0-A4 | done | `secrets.test.ts`, 558d779 |
| A4 progress/cancellation (FR-M1-09) | — (baseline) | done | `progress.test.ts`, 6779a7b |
| A5 bundling (FR-M1-10) | — (baseline) | done — dist/meridian-loom-0.0.1.vsix | c0df98d |
| B6 spawn + framed JSON-RPC (FR-M3-01/09) | F0-A2 | done | e2e stdio test, 43a907e |
| B7 dual teardown (FR-M3-02/03) | F0-A2 | done — orphan-guard test | a64eee4 |
| B8 spawn errors + interpreter chain (FR-M3-04/05/05a) | F0-A3 | done | ac274dc |
| B9 remote support (FR-M3-11) | F0-A3 | done | bde3e95 |
| B10 health/restart/versioned RPC/no-listener (FR-M3-06/08/10) | F0-A5 | done | ecf7de9 |
| B11 generated bus types + staleness check (FR-M32-09 foundation) | F0-A5 | done — `npm run check:contracts` blocks divergence | 1527530 |

## Phase F0 exit criteria (from gaps_implementation.md §F0)

| # | Criterion | Status | Proof |
|---|---|---|---|
| 1 | AC-30 first value < 15 min, no model credential, Weave shows external session with vendor tags, any-line provenance | pass (engineering) / human-gated (measurement) | 10.45/10.46/10.40 screens on real sidecar data (40d8e30, c3aa115, 73922f7); real claude.exe session detected live on the dev machine (X-29 e2e); the 5-person 15-minute measurement is human-gated — NFR-28 |
| 2 | AC-33 provenance survives uninstall; bundle verifies with open verifier on clean machine | pass (engineering) / human-gated (uninstall act) | open verifier tests verify exported bundles using only bundled material, no Meridian installed (4dfbdb1 — verify.py + Rust meridian-verify); trailer persistence in git is filesystem-verified by hook e2e tests (86aec58); the physical VSIX uninstall is a human/CI-matrix act |
| 3 | AC-34 (partial) rejection rate per agent split greenfield/brownfield reconciles to ledger over ≥10 sessions | partially — engineering half proven: `test_reconciliation` recomputes the rate independently from raw ledger rows and asserts equality with the trust/rejectionRate RPC result (df7bf0a); ≥10-sessions human half remains pending-human-evidence |
| 4 | NFR-28 first value < 15 min (5-person measurement — human-gated; engineering proxies automated) | human-gated | 10.40 First-Run four steps on real data (73922f7); the 5-person measurement cannot be run by the build agent |
| 5 | NFR-29 observation ≤5% latency, never blocks | **pass** | measured: hook burst ~0.0ms, RPC reads ~0.0ms during 500ms in-flight observation (9e190c0); budget 100ms |
| 6 | FR-M36-07 zero model calls — CI test fails on any model-client import in F0 paths | **pass** | `test_no_model_calls.py` (13) + `no-model-calls.test.ts` (12), ed66495 |
| 7 | Chain verification passes; corrupted entry detected and sequence named | **pass** | `test_ledger_verify.py` (10) — 3.2s/100k, payload/prev-hash/gap divergence naming (60858d5) |
| 8 | Broken observer telemetry degrades to `inferred` with visible warning within one session, never silence | **pass** | observer framework NFR-32 downgrade tests (522d07b); visible warning surfaced in 10.46 observer health (c3aa115) |
| 9 | No orphaned sidecar after window close/reload/disable (all platforms, Remote SSH) | pass (mechanism) / matrix human-gated | dual-teardown orphan-guard tests both halves (a64eee4); Windows/macOS/Linux/Remote-SSH matrix is CI/human |
| 10 | G5 tier isolation: disabling Governor/Orchestra leaves Flight Recorder fully functional | **pass** | tiers e2e on real sidecar: upper-tier RPCs refused with structured error, FR fully functional, config-only re-enable (4059975) |

## F0 workstream progress

| Workstream | Tasks | Status |
|---|---|---|
| A — Shell and sidecar, minimum viable | 1–7 | **done** (4059975; doctor 5730d66; tiers e2e prove G5) |
| B — Ledger core | 8–12 | **done** (e25a530; 631f86f run_id/origin v2 migration per gaps_initiation §5) |
| C — Deterministic attribution (no model calls) | 13–16 | **done** (ed66495; FR-M36-07 exit criterion 6 proven by test) |
| D — Observers | 17–22 | **done** (c60874b; X-29 + NFR-29 measured within budget; SEC-27 pass) |
| E — Portable provenance | 23–27 | **done** (481f5fa hook UI command; 90b5e6c agent identity trailers; abfc94c full signed bundle — proofs/signature/compliance; 4dfbdb1 open verifier verify.py + meridian-verify; 1ea71c8 spec docs) |
| F — Rejection measurement, minimum | 28–30 | **done** (5b54279 rejection capture + ledger v4 rejection entries; 820f59a greenfield/brownfield classification; df7bf0a ledger-derived rejection rate, cached, split, reconciling) |
| G — The three screens (interlock GF0) | 31–36 | **done** (82b84b9 export plumbing; 40d8e30 10.45 Flight Recorder; c3aa115 10.46 External Agents; 5f082f6 10.7 Ledger; 73922f7 10.40 First-Run; c0a1243 X-27…X-30 invariants; b3732aa theme close-out) |

## Later phases (per gaps_implementation.md)

- F1 Governor — ACP host (M34), gates over external PRs, roles, trust analytics, spend, 10 screens — **in progress (workstream A)**
- F2 Evidence Gate — human-run, 20 real stories; recorded as pending-human-evidence (DECISIONS.md)
- F3 Orchestra — old C1+C2 re-based on ACP; Simulation Core built here as regression harness
- F4+ — old C3–C6

## F1 workstream progress

| Workstream | Tasks | Status |
|---|---|---|
| A — ACP host | 1–8 | tasks 1–5, 8 done (c4a4805 client; df4b267 adapter re-base; f22ef6a registry; 289d33a permission gate SEC-28; 8ed0bcf conformance; task 5 worktree isolation below); 6–7 done (eeec15a MCP server FR-M34-06; 88a2b32 upstream tracking FR-M34-05) |
| B — Gates over other people's work | 9–14 | **done** (47e809b policy engine; 0791ec9 merge gate; 3abb236 halt; 7f68ec5 pr/ingest + pr/status FR-M35-04/05 with AC-32 one-range reconciliation; 4ae3cc7 pr/conflicts FR-M35-07; 910aad8 E-GR-03 taxonomy in policy/) |
| C — Human identity and roles | 15–16 | not started |
| D — Steer and clarify | 17–18 | not started |
| E — Trust analytics | 19–25 | not started |
| F — Cross-vendor spend | 26–29 | not started |
| G — Remaining observers | 30 | not started |
| H — Screens (interlock GF1) | 31–32 | not started |

## Decisions closed

- D4, D10, D18 — pre-decided (kickoff)
- D20 — Claude Code + Copilot observers first (DECISIONS.md)
- D23 — commit-msg hook default, git notes fallback (DECISIONS.md)
- D22 — OPEN, human-gated (DECISIONS.md → Deferred)

## Phase log

- F1 Workstream B tasks 12–14 done — external PR gating + multi-agent conflicts + rework taxonomy. New sidecar module `core/meridian_core/pr/` (ingest: gh-api payload → Meridian story — origin record actionType pr_ingest origin connector, per-agent attributed hunks via trailers > author markers > inferred fallback, agent pass as proposed-change entries, routing through verify/security/review gate profiles; conflicts: per-commit hunk attribution over a git range, agent-vs-agent overlaps as the distinct class agent-conflict). New RPCs `pr/ingest`, `pr/status`, `pr/conflicts` in governor-tier capability `governor.pr-gates` (single ownership holds; G5 refusal tested). Merge gate `check_merge` gains an explicit `requires_approval` override so a PR subject targeting a protected base branch needs a recorded human approval bound to the head digest; AC-32 test proves the agent's pass, the gates and the approver in one contiguous ledger range. E-GR-03: no spec defines the taxonomy, so it is DEFINED in `policy/rework-reasons.yaml` (versioned, 8 classes) with the rationale in `core/meridian_core/rejection/taxonomy.py`'s docstring; `trust/detectRejections` gains reason/reasonNote params, and both the F0 rejection detector and the conflict detector stamp fail-closed (unknown → other + note; the mechanical shape moves to tool_calls, idempotency keys on it). Suite: pytest 639 green at the full root run (test_pr_ingest 22, test_pr_conflicts 10, test_rework_taxonomy 13 among them), extension vitest 317 passed, `check:contracts` green, no-model-calls green.

- F1 Workstream A task 6 (MCP server exposure, FR-M34-06) done: new sidecar RPC `mcp/invoke` in capability `governor.mcp-server` (single-ownership registry holds; bus types regenerated) — the governor tier gate is the permission gate (disabled ⇒ TIER_DISABLED, G5), every call is ledger-recorded as a `tool_call` entry (vendor `mcp`, direct confidence, story `mcp:<tool>`) BEFORE it executes, and the tool maps onto the existing read-only handler (ledger_query/export_bundle/verify, trust_rejection_rate). Extension: `extension/src/mcp/server.ts` implements MCP 2025-03-26 directly (initialize/ping/tools/list/tools/call/resources/list/resources/read; NDJSON stdio; no protocol deps); structured sidecar errors mirrored verbatim (TIER_DISABLED shape included); resources `meridian://open-ledger-spec` + live `meridian://doctor-report`. `extension/src/mcp/main.ts` is the standalone vscode-free entrypoint (same framed sidecar spawn, FR-M3-01/11; stdout MCP-only per FR-M3-09); bundled via `npm run build` to `dist/mcp/mcp-server.js` and smoke-tested as a real spawned process. Suite: pytest 500→512 (test_mcp_invoke 12), extension vitest 282→296 (mcp-server 13 unit + 1 real-sidecar e2e), `tsc --noEmit` clean, `check:contracts` green, no-model-calls green.
- F1 Workstream A task 7 (upstream contribution, FR-M34-05) done: `extension/src/acp/UPSTREAM.md` (host-generic vs Meridian-specific inventory; Apache-2.0 publication plan — LICENSE stays with the human owner per D22; layering strategy on native ACP; supported-SDK declaration `<!-- supported-acp-sdk: 0.4.5 -->`), `docs/upstream/vscode-acp-issue.md` (tracks microsoft/vscode#265496, signal order, review cadence), `extension/test/acp-upstream-version.test.ts` (4 tests; warns never fails on SDK drift). Deferred: wiring the MCP server into VS Code via `vscode.lm.registerMcpServerDefinitionProvider` (needs a newer `@types/vscode` than 1.95 pinned in the repo) — the server is spawnable and tested standalone today.

- F1 Workstream A task 5 (worktree isolation, M18) done: new `core/meridian_core/worktree/` (manager: create/list/remove/abort/conflicts — dedicated branch `meridian/<story>` under `.meridian/worktrees/<story-id>/`, worktree-local agent identity + `Meridian-Hosted-Agent` trailer hook via per-worktree `core.hooksPath`, abort deletes never-pushed branch and leaves the primary tree byte-identical). Sidecar RPCs `worktree/create|list|remove|abortStory|conflicts` in a new governor-tier capability `governor.worktrees` (single-ownership assertion holds); create/remove/abort ledger-recorded with `worktree_ref`. Extension: `meridian.abortStory` wired to the abort RPC (confirm-first), new `meridian.openWorktree` command (worktree/list → `vscode.openFolder` new window, FR-M18-08). AC-13/AC-14-shaped tests by name; conflict report consumed later by the M40 RunRequest/preflight flow. Suite: pytest 457→500 (test_worktree 43), extension vitest 268→282 (worktree-commands 13, manifest 1), `tsc --noEmit` clean, `check:contracts` green. FR-M18-06 (signed agent commits, SecretStorage key) and FR-M18-09 (GC retention) remain v1.x per spec — not built here.

- Workstream E (tasks 23–27) done: pytest 360→406, extension vitest 128→137, `tsc --noEmit` clean, `check:contracts` green throughout. Proof commits 481f5fa, 90b5e6c, abfc94c, 4dfbdb1, 1ea71c8. Cargo-based verifier tests skip-and-notice when cargo is off PATH.
- Workstream F (tasks 28–30) done: pytest 406→448 collected (test_rejection 20, test_greenfield 14, test_trust_metrics 9, schema tests updated for v4; cargo-based verifier tests skip-and-notice when cargo is off PATH), extension vitest unchanged at 137, `tsc --noEmit` clean, `check:contracts` green throughout. Proof commits 5b54279, 820f59a, df7bf0a. New surface: `trust/detectRejections`, `trust/classify`, `trust/rejectionRate` (capability `recorder.trust-metrics`, flight-recorder tier); ledger schema v4 (rejected_sequence/rejected_commit/rejecting_commit); workspace settings `meridian.rejectionWindowDays` (7), `meridian.greenfieldNewFileRatio` (0.5), `meridian.greenfieldMaxMedianAgeDays` (30).
- GF0 foundation (G0a–G0d) done: new `webview/` workspace (Vite+React+TS, vitest+RTL) — six themes + follow-vscode default, Iron Gall forced on high contrast; comfortable density default; Archivo + JetBrains Mono via @fontsource (latin subset; Commit Mono deferred, see `webview/FONTS.md`); invariant components (X-27 ConfidenceBar, RationaleBlock, AgentToken, ActionClassChip, VendorTag with geometric SVG glyphs — V10 glyph pass deferred); `shared/ts/webview-messages.ts` (hand-written, not generated — `check:contracts` green); extension host `RecorderPanel` (CSP nonce, asWebviewUri, serializer, no web storage), pure tier-gated `dispatchWebviewMessage` proxy, rename `meridian.openDashboard`→`meridian.openRecorder` (gaps §F0 names it; DECISIONS.md G-0), packaging copies `webview/dist`→`extension/webview-dist`. Suite: pytest 448, extension vitest 137→158 (recorder-panel 12, webview-rpc-proxy 8, webview-e2e 1 real sidecar round-trip), webview vitest 70, both `tsc --noEmit` clean, `npm run build` green (webview bundle 154.79 kB). Proof commits 2c563a7, 6999b8c, afbaf98.
