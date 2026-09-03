# MERIDIAN LOOM — Build State

> Resumption state. Updated after every completed task. If the session is interrupted, read this file and DECISIONS.md first, then continue from the recorded task.

**GOVERNING ORDER (changed mid-build — see DECISIONS.md G-0):** the repo owner committed `gaps-requirements.md` + `gaps_implementation.md` (+ `gaps_guix.md`, `gaps_guix_implementation.md`), which supersede the S0 → GUI → C1…C6 sequencing. New order: **F−1 (legal gate, human-gated — see DECISIONS.md) → F0 Flight Recorder → F1 Governor → F2 Evidence Gate (human-run) → F3 Orchestra → F4+ (old C3–C6).** All six original spec files remain requirement sources; copies of all ten docs are in `docs/spec/`.

- **Current phase:** F0 — Flight Recorder
- **Current workstream:** B — Ledger core
- **Current task:** 8 — Append-only SQLite with §7.2 schema + v2.1 fields + vendor/observation_confidence/external_session_id (FR-M10-01)
- **Last commit:** 4059975 — feat(f0): tiering scaffold (FR-M36-05, X-28) — F0 Workstream A complete (tasks 1–7; doctor via 5730d66)
- **Updated:** _(see git log)_

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
| 1 | AC-30 first value < 15 min, no model credential, Weave shows external session with vendor tags, any-line provenance | not-yet | |
| 2 | AC-33 provenance survives uninstall; bundle verifies with open verifier on clean machine | not-yet | |
| 3 | AC-34 (partial) rejection rate per agent split greenfield/brownfield reconciles to ledger over ≥10 sessions | not-yet | |
| 4 | NFR-28 first value < 15 min (5-person measurement — human-gated; engineering proxies automated) | not-yet | |
| 5 | NFR-29 observation ≤5% latency, never blocks | not-yet | |
| 6 | FR-M36-07 zero model calls — CI test fails on any model-client import in F0 paths | not-yet | |
| 7 | Chain verification passes; corrupted entry detected and sequence named | not-yet | |
| 8 | Broken observer telemetry degrades to `inferred` with visible warning within one session, never silence | not-yet | |
| 9 | No orphaned sidecar after window close/reload/disable (all platforms, Remote SSH) | partially — orphan-guard test green (a64eee4); cross-platform matrix pending CI | |
| 10 | G5 tier isolation: disabling Governor/Orchestra leaves Flight Recorder fully functional | not-yet | |

## F0 workstream progress

| Workstream | Tasks | Status |
|---|---|---|
| A — Shell and sidecar, minimum viable | 1–7 | **done** (4059975; doctor 5730d66; tiers e2e prove G5) |
| B — Ledger core | 8–12 | in progress |
| C — Deterministic attribution (no model calls) | 13–16 | not started |
| D — Observers | 17–22 | not started |
| E — Portable provenance | 23–27 | not started |
| F — Rejection measurement, minimum | 28–30 | not started |
| G — The three screens (interlock GF0) | 31–36 | not started |

## Later phases (per gaps_implementation.md)

- F1 Governor — ACP host (M34), gates over external PRs, roles, trust analytics, spend, 10 screens
- F2 Evidence Gate — human-run, 20 real stories; recorded as pending-human-evidence (DECISIONS.md)
- F3 Orchestra — old C1+C2 re-based on ACP; Simulation Core built here as regression harness
- F4+ — old C3–C6

## Decisions closed

- D4, D10, D18 — pre-decided (kickoff)
- D20 — Claude Code + Copilot observers first (DECISIONS.md)
- D23 — commit-msg hook default, git notes fallback (DECISIONS.md)
- D22 — OPEN, human-gated (DECISIONS.md → Deferred)

## Phase log

_(F0 in progress)_
