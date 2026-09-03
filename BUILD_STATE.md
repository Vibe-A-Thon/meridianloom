# MERIDIAN LOOM — Build State

> Resumption state. Updated after every completed task. If the session is interrupted, read this file and DECISIONS.md first, then continue from the recorded task.

- **Current phase:** S0 — Simulation Core & Contracts
- **Current workstream:** A — Extension host and lifecycle
- **Current task:** 1 — Extension scaffold (FR-M1-01..03)
- **Last commit:** _(pending — initial layout commit)_
- **Updated:** _(see git log)_

## Phase S0 exit criteria (from Requirements-implementation.md §S0)

| # | Criterion | Status | Proof |
|---|---|---|---|
| 1 | Installs and activates on Windows, macOS, Linux, and under Remote SSH (AC-19) | not-yet | |
| 2 | AC-08 no orphaned process | not-yet | |
| 3 | AC-07 checkpoint resume | not-yet | |
| 4 | AC-14 abort leaves the tree byte-identical | not-yet | |
| 5 | AC-13 conflict surfaced | not-yet | |
| 6 | AC-21 blame and trailer | not-yet | |
| 7 | Chain verification passes; corrupted entry detected and sequence named | not-yet | |
| 8 | A recorded operation replays deterministically (AC-15 rehearsed) | not-yet | |
| 9 | Every FR-M32-04 scenario runs on the Simulation Core, real ledger entries marked `simulated`, zero model calls | not-yet | |
| 10 | Contract-drift check green and blocks a deliberately introduced divergence | not-yet | |
| 11 | `meridian doctor` reports every check with an actionable result | not-yet | |
| 12 | NFR-01, NFR-05, NFR-08, NFR-26 | not-yet | |

## Workstream progress (S0)

| Workstream | Tasks | Status |
|---|---|---|
| A — Extension host and lifecycle | 1–5 | in progress |
| B — Sidecar and IPC | 6–11 | not started |
| C — Workspace isolation | 12 | not started |
| D — Ledger substrate | 13–16a | not started |
| E — Replay and Simulation Core | 17–24 | not started |
| F — Operations | 25 | not started |

## Decisions to close in S0

- D4 (Python distribution) — pre-decided: workspace interpreter via FR-M3-05 resolution chain, no bundled runtime in v1
- D10 (golden corpus layout) — pre-decided: `/golden/<story-id>/`, `meridian corpus refresh`
- D18 (learned/ persistence) — pre-decided: committed under `.meridian/adapters/<id>/learned/`

## Phase log

_(empty — S0 in progress)_
