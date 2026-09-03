# Meridian Loom — Engineering Implementation Plan

| | |
|---|---|
| **Document** | Requirements-implementation.md |
| **Version** | **2.0 — re-sequenced for GUI-first, pluggable agent adapters, and Python-first / LLM-minimal execution** |
| **Supersedes** | Requirements-implementation.md v1.0 |
| **Author** | Ravaleedhar Reddy |
| **Governs** | The build order for everything specified in `Requirements_Final.md` v2.1 |
| **Companions** | `Requirements_Final.md` (33 modules, ~533 items) · `vision.md` v1.1 · `VIGUIX_Final.md` v2.1 · `viguix-implementation.md` v2.1 |
| **Scale** | 7 engineering phases (S0, C1–C6) around 10 GUI phases · 33 modules · 9 SDLC phases |

---

## Table of Contents

0. [About This Plan](#0-about-this-plan)
1. [How to Use This Document](#1-how-to-use-this-document)
2. [Build Principles](#2-build-principles)
3. [Stack Decisions](#3-stack-decisions)
4. [Phase Map](#4-phase-map)
5. [S0 — Simulation Core & Contracts](#s0--simulation-core--contracts)
6. [The GUI — G0 to G8](#the-gui--g0-to-g8)
7. [C1 — Control Layer](#c1--control-layer)
8. [C2 — Adapters & Prebuilt Agents](#c2--adapters--prebuilt-agents-first-value)
9. [C3 — Quality Gates](#c3--quality-gates)
10. [C4 — Learning & Portability](#c4--learning--portability)
11. [C5 — Orchestration, Scale & Compliance](#c5--orchestration-scale--compliance)
12. [C6 — Differentiation](#c6--differentiation)
13. [Cross-Cutting Workstreams](#13-cross-cutting-workstreams)
14. [Definition of Done — Any Module](#14-definition-of-done--any-module)
15. [Sequencing Dependencies](#15-sequencing-dependencies)
16. [GUI Interlock](#16-gui-interlock)
17. [Slip Plan](#17-slip-plan)
18. [Risk Retirement Schedule](#18-risk-retirement-schedule)
19. [Decision Schedule](#19-decision-schedule)
20. [Changes from v1.0](#20-changes-from-v10)
21. [Traceability Appendix](#21-traceability-appendix)

---

## 0. About This Plan

### 0.1 What this document is

`Requirements_Final.md` v2.1 says *what* to build and assigns each requirement a release target. This document turns that into a build order at requirement granularity, honouring three stated constraints that v1.0 of this plan did not have:

1. **The entire interface is built first**, then the controlling layer, then everything else.
2. **Every agent is a pluggable, portable adapter** — the prebuilt roster, the organisation's existing agents, and any custom agent — with what it learns travelling with it.
3. **Python does the heavy lifting; the model is the last resort.**

### 0.2 How "GUI first" squares with "no mock data"

v1.0's founding rule was that no screen ships against mock data. The new build order does not break it — it satisfies it differently.

**S0 delivers the Simulation Core (M32):** a real sidecar implementing the complete message-bus contract, writing real hash-chained entries through the real Ledger Service, driving real loop-state transitions through the real runtime state machine, with the reasoning step replayed from cassettes or produced by deterministic simulators. It makes **zero model calls**. The entire GUI (G0–G8) is built against it. When the control layer lands in C1, the GUI switches to the production sidecar with no change — enforced by a contract-drift check in CI (`FR-M32-09`, `AC-28`).

The Simulation Core is never thrown away. It becomes the golden-corpus runner and the fault-injection harness (`FR-M32-07`), and the harness a custom-agent author tests against (`FR-M32-08`).

**What it costs:** first value — a real story through a real chain — arrives in C2, after the full GUI, not alongside it. **What it buys:** an interface that is complete, exercised on every screen against real data structures, and never rebuilt.

### 0.3 The scheduling conflict carried forward from v1.0

v1.0 §0.2 found 13 requirements marked `v1` whose module was scheduled later than their target, and `D14` (whether the Security phase is in the first-value chain, and whether `AC-02` should name it). Both are carried into this version unchanged: the 13 are placed in C1/C2, and `D14` must close before C2 starts.

### 0.4 Release target → phase mapping

| Target | Phases |
|---|---|
| **v1** | S0, C1, C2 |
| **v1.x** | C3, C4, C5 |
| **v2** | C6 |

Within v1: **S0 is platform and simulation** (nothing that reasons live), **C1 is the control layer** (reasons, but no agent workforce yet), **C2 is the first vertical slice** — adapters, prebuilt agents, one stack, ingest to merge.

---

## 1. How to Use This Document

Seven engineering phases, S0 and C1–C6, with all ten GUI phases between S0 and C1. Each is independently shippable. Each has a hard exit gate.

**The rule that governs everything:** the exit gate for C2 is `AC-01`…`AC-29` plus the §10.2 quality bar, and **C3 does not begin until that bar is cleared on at least 20 real stories.** Everything after C2 is an amplifier, and amplifying an unproven core amplifies error.

Three rules that follow from the evidence in `vision.md` §1.1 and from the v2.1 constraints:

- **Instrument before you accelerate.** Measured cycle time, first-pass yield, cost per merged PR *and the LLM dependency ratio* exist from C2 (`FR-M17-01`, `FR-M17-04`, `FR-M17-10`).
- **The gates are the product.** Governance's v1 subset is in C1, before any agent exists.
- **The prebuilt agents are the first adapters.** The adapter framework is proven by the product's own workforce in C2 before an external agent plugs in.

---

## 2. Build Principles

E1–E10 carry over from v1.0. E11–E14 are new.

| # | Principle | Consequence |
|---|---|---|
| **E1** | **The ledger is built before anything that writes to it.** | M10's substrate is S0. No module ships a code path that acts without recording. |
| **E2** | **Isolation before autonomy.** | M18 worktrees are S0, before a single agent exists. |
| **E3** | **Replay before reasoning.** | M27 cassettes and the golden-corpus harness are S0. The Simulation Core is built on them. |
| **E4** | **One stack, one slice, all the way through.** | C2 is Java/Spring only, story→merge. Breadth is C3+. |
| **E5** | **Every loop is bounded from its first commit.** | `FR-M4-02` validation runs at load time from day one. |
| **E6** | **Untrusted-by-default is an S0 posture, not a C3 feature.** | `SEC-01`…`SEC-05` shape the tool layer and prompt assembly from the first agent invocation. |
| **E7** | **Human identity before human approval.** | `FR-M20-01` lands in C1. |
| **E8** | **Nothing ships without its cost visible.** | Token accounting and `why_llm` (`FR-M8-05`, `FR-M8-16`) are instrumented with the router in C1. |
| **E9** | **Signals accumulate from C2 even though the Trainer arrives in C4.** | History cannot be back-filled. |
| **E10** | **Every module ships with fault injection.** | `FR-M27-04` covers the runtime; each module extends it. |
| **E11** *(v2.0)* | **The Simulation Core is the first backend, and it is real.** | Contracts, ledger and loop state are production code from S0. Only the reasoning step is replayed. Contract drift fails the build. |
| **E12** *(v2.0)* | **Every agent goes through the adapter protocol — including ours.** | No prebuilt agent has a private path into the runtime. If the prebuilt Developer cannot be unplugged and re-plugged, the framework is not done. |
| **E13** *(v2.0)* | **Deterministic first, and the model must say why.** | Every action class is dispatched to the Deterministic Engine before the router. A model call without a recorded `why_llm` is a defect. |
| **E14** *(v2.0)* | **Learning writes only to `learned/`.** | The Trainer, and any bridged agent's own mechanism, may not touch an adapter's code, manifest, or the runtime. What is in `learned/` is data, validated against a schema, and travels with the agent. |

---

## 3. Stack Decisions

Settle in S0. Rows marked **new** were added or changed by v2.0.

| Concern | Decision | Rationale |
|---|---|---|
| Extension host | TypeScript, esbuild-bundled, platform-specific VSIX targets where a runtime is bundled | `FR-M1-10`, `FR-M3-05a` |
| Sidecar language | Python 3.11+ | Stated; where the orchestration ecosystem lives |
| IPC | Framed JSON-RPC 2.0 over stdio, schema-versioned, handshake-checked, **types generated once and shared by the Simulation Core, the production sidecar, and the webview** | `FR-M3-01`, `FR-M3-08`, **`FR-M32-09`** |
| Loop runtime | **`D1` — open.** Durable graph runtime (LangGraph-class) vs. minimal in-house. Must close before C1. | Capabilities are specified; engine substitutable |
| Checkpointer | SQLite-backed, local | `FR-M4-05` |
| Ledger store | SQLite, append-only with triggers, content-addressed **encrypted** blob store from S0 | `FR-M10-01`, `FR-M10-07`, enables `FR-M10-14` without migration |
| Merkle / signing | SHA-256 chain + Merkle tree; key in OS keychain | `FR-M10-02`…`04` |
| Anchoring | **`D3` — open.** Close by C5. | |
| Isolation | Git worktree per story, agent git identity, optional signing | M18 |
| **Adapter protocol** *(new)* | A versioned Python protocol (`AgentAdapter`), a manifest schema (§7.9), a discovery walker over three tiers, and a hot-reload watcher. **Bridges for MCP and plain-Python in C2; `D15` decides the rest.** | M31 |
| **Adapter SDK** *(new)* | `meridian-adapter` package: protocol, `meridian adapter new` scaffold, local harness against the Simulation Core, conformance suite | `FR-M31-11`, `FR-M32-08` |
| **Deterministic Engine** *(new)* | A Python dispatch layer in front of the router, keyed by action class (§7.10), owning tree-sitter, LSP, tool runners, template scaffolding, graph analysis, rules from `learned/rules/` | M33 |
| **Action-class policy** *(new)* | YAML in the policy pack (§7.10); reclassification is a reviewed policy change (`D16`) | `FR-M33-01`, `FR-M33-10` |
| **Learned-state schema** *(new)* | Declarative schemas for `learned/policy`, `learned/rules`, `learned/memory`, `learned/calibration`; the engine refuses executable content | `SEC-26` |
| Tools | MCP client (stdio) + native tool set; LSP bridge; tree-sitter | M9, M28 |
| Semantic search | Local embedding index, incrementally updated | `FR-M28-03` |
| Model access | Direct provider APIs (primary); `vscode.lm` proxied (secondary); **router sits behind the Deterministic Engine and refuses calls with a deterministic path** | `FR-M8-01`, **`FR-M8-15`** |
| Model routing | **`D2` — open.** Tiering per phase and task class; **`FR-M8-18` smallest tier that satisfies the schema for assisted classes** | Close before C1 |
| Structured output | Schema-constrained where supported; validation + bounded retry | `FR-M8-14` |
| Replay | Cassettes keyed by canonical request hash; golden corpus in CI with zero model calls; **the Simulation Core is the runner** | M27, M32 |
| Python distribution | **`D4` — open.** Close in S0. | |
| Remote | SSH / WSL / Dev Containers / Codespaces, sidecar on the remote host | `FR-M3-11` |
| Identity | **`D9` — open.** Close in C1. | |
| Connectors | Jira Cloud first (C2); rest C5 | `FR-M19-01` |
| CI | GitHub Actions first (C2); rest C5 | `FR-M23-01` |
| Telemetry export | OpenTelemetry, opt-in, local by default | `FR-M30-06`, `FR-M17-06` |

---

## 4. Phase Map

| Phase | Name | Modules | Release | Exit signal |
|---|---|---|---|---|
| **S0** | Simulation Core & Contracts | M1, M2 *(shell)*, M3, M10 *(substrate)*, M18, M27, **M32**, M30 *(partial)*, generated bus types | v1 | Every screen's scenario runs on the Simulation Core; contract-drift check green; zero model calls |
| **G0–G8** | The entire GUI | `viguix-implementation.md` v2.1 | v1 | All 44 screens complete against the Simulation Core |
| **C1** | Control Layer | M4, M5, M7 *(incl. Instruction Library)*, M8 *(LLM-minimal)*, M9, M12 *(v1 subset)*, M13, M20 *(identity)*, M25, M26 *(estimate + levers)*, M28, **M33** | v1 | Live loops drive the existing GUI unchanged; `AC-27`, `AC-28` |
| **C2** | Adapters & Prebuilt Agents — *first value* | **M31**, the §6.10 roster as adapters, M6 *(one skill)*, M17 *(core)*, M19 *(Jira)*, M23 *(GitHub)*, M24 *(hover + chat)*, SDLC phases 1–7, one plain-Python bridge | v1 | `AC-01`…`AC-29`; §10.2 quality bar |
| **C3** | Quality Gates | M12 *(full)*, M6 *(catalogue)*, M16 *(upgrade/revocation)*, phase 5–7 additions | v1.x | Gates block real defects; three stacks; `NFR-25` held |
| **C4** | Learning & Portability | M14 *(per-adapter, `learned/` only, distillation)*, M15, M16 *(adapter packages)*, remaining bridges | v1.x | Trainer raises FPY and moves ≥1 action class to deterministic; an adapter round-trips with its learning |
| **C5** | Orchestration, Scale & Compliance | Phase Orchestrators, M21, M22, M19 *(rest)*, M23 *(rest)*, M29, M17 *(full)*, M20 *(full)*, M30 *(full)*, phases 8–9, anchoring, crypto-shredding, tenant isolation | v1.x | Multi-story, multi-repo, audit bundle accepted, erasure completes |
| **C6** | Differentiation | 11 v2 items | v2 | — |

---

## S0 — Simulation Core & Contracts

**Goal.** A real platform the entire interface can be built against, with zero model calls. Installs everywhere, spawns and tears down cleanly, isolates every write, records tamper-evidently, replays itself offline — and simulates every scenario the GUI needs.

**Modules.** M1 · M2 (shell) · M3 · M10 (substrate) · M11 · M18 · M27 · **M32** · M30 (doctor, migration, uninstall)

### Workstream A — Extension host and lifecycle
1. **Extension scaffold** — granular activation, never `*` (`FR-M1-01`); Activity Bar container and five tree views (`FR-M1-02`); the twelve commands (`FR-M1-03`).
2. **Thread discipline** — nothing over 50 ms on the host thread (`FR-M1-04`).
3. **SecretStorage adapter** with refuse-to-start on unavailability (`FR-M1-06`, `FR-M1-07`).
4. **Progress and cancellation** wired to sidecar loop cancellation (`FR-M1-09`).
5. **Bundling** (`FR-M1-10`).

### Workstream B — Sidecar and IPC
6. **Spawn and framed JSON-RPC over stdio** (`FR-M3-01`, `FR-M3-09`).
7. **The dual teardown contract** — `FR-M3-02` and `FR-M3-03`, both halves mandatory.
8. **Spawn error handling** (`FR-M3-04`). **Interpreter resolution** (`FR-M3-05`); **close `D4`**; platform-specific VSIX targets if bundling (`FR-M3-05a`).
9. **Remote support** — SSH, WSL, Dev Containers, Codespaces (`FR-M3-11`). Built here, not ported later.
10. **Health checks and restart policy** (`FR-M3-06`); **versioned RPC** with refusal on mismatch (`FR-M3-08`); no listener by default (`FR-M3-10`).
11. **Generated message-bus types** shared by the Simulation Core, the production sidecar and the webview — the single source the contract-drift check (`FR-M32-09`) compares.

### Workstream C — Workspace isolation
12. **Worktree manager** (`FR-M18-01`, `FR-M18-02`). **Conflict detection** before a packet starts (`FR-M18-03`). **Story abort** leaving the primary tree untouched (`FR-M18-04`). **Agent git identity** and commit trailer (`FR-M18-05`, `FR-M18-07`). Open-in-window (`FR-M18-08`). `.gitignore` initialisation (§4.2), now including `adapters/*/learned/` policy per `D18`.

### Workstream D — Ledger substrate
13. **Append-only SQLite** with the §7.2 schema including `human_role`, `worktree_ref`, `repo_id`, `replay_of`, `blob_key_id`, and the **`simulated` marker** (`FR-M32-02`) (`FR-M10-01`).
14. **Hash chain, Merkle tree, inclusion and consistency proofs** (`FR-M10-02`, `FR-M10-03`). **Signed tree heads** (`FR-M10-04`).
15. **Content-addressed encrypted blob store** with per-subject keys from day one, so crypto-shredding in C5 is not a migration.
16. **Chain verification** under 5 s for 100k entries (`FR-M10-09`). **Synchronous write semantics** (`FR-M10-08`). **Ledger query API** (`FR-M10-12`).
16a. **Chain Viewer backend** (M11) — the integrity verdict and first-divergent-sequence report for the banner (`FR-M11-01`), the filterable entry stream and full-entry detail the viewer renders (`FR-M11-02`, `FR-M11-03`), inclusion and consistency proofs on request (`FR-M11-04`), and signed audit-bundle export (`FR-M11-05`). Built in S0 because 10.7 is a G2 screen and needs real proofs from the Simulation Core.

### Workstream E — Replay and the Simulation Core
17. **Cassette recorder** keyed by canonical request hash (`FR-M27-01`). **Deterministic replay** to an identical ledger with zero model calls (`FR-M27-02`).
18. **Fault injection console** (`FR-M27-04`). **Golden corpus harness** with an empty corpus; **close `D10`**.
19. **Simulation Core — the full contract** (`FR-M32-01`). Every request, response and subscription the production sidecar will emit, served from simulated state.
20. **Real ledger, real loop state** (`FR-M32-02`, `FR-M32-03`): the six loops' state machine with bounds, checkpoints, interrupts and gates, with the reasoning step satisfied by cassette or simulator.
21. **Scripted scenarios** (`FR-M32-04`): clean story · rework and unravels · loop bound hit · blocked gate · clarifying question · steer · multi-story portfolio · tamper-detected ledger · budget breach · **adapter plug and unplug**. One per screen's data needs; a screen without a scenario cannot start (`viguix-implementation.md` B13).
22. **Time control** — pause, step, play at N×, jump to sequence (`FR-M32-06`).
23. **Zero model calls, enforced** — a model-call code path inside the Simulation Core fails a test (`FR-M32-05`).
24. **Contract-drift check in CI** (`FR-M32-09`, `NFR-26`).

### Workstream F — Operations
25. **`meridian doctor`** (`FR-M30-01`). **State migration** (`FR-M30-03`). **Clean uninstall** never removing the ledger without confirmation (`FR-M30-08`).

### Exit criteria
- [ ] Installs and activates on Windows, macOS, Linux, and under Remote SSH (`AC-19`)
- [ ] `AC-08` no orphaned process · `AC-07` checkpoint resume · `AC-14` abort leaves the tree byte-identical · `AC-13` conflict surfaced · `AC-21` blame and trailer
- [ ] Chain verification passes; a corrupted entry is detected and its sequence named
- [ ] A recorded operation replays deterministically (`AC-15` rehearsed)
- [ ] **Every `FR-M32-04` scenario runs on the Simulation Core, producing real ledger entries marked `simulated`, with zero model calls**
- [ ] **The contract-drift check is green and blocks a deliberately introduced divergence**
- [ ] `meridian doctor` reports every check with an actionable result
- [ ] `NFR-01`, `NFR-05`, `NFR-08`, `NFR-26`

### Decisions to close
`D4` · `D10` · `D18` (where `learned/` is persisted — affects `.gitignore` now)

### Risks retired
`R2` · `R14` · `R15` · `R22` (contract drift — controlled from here) · `R11` (partially)

---

## The GUI — G0 to G8

All ten GUI phases run here, in full, against the Simulation Core, per `viguix-implementation.md` v2.1. Engineering's only obligations during this span:

- Keep the Simulation Core's scenarios ahead of the screens being built (`FR-M32-04`) — a screen without a scenario cannot start.
- Keep the contract-drift check green while the production sidecar's contract is designed in parallel for C1.
- Extend the Simulation Core with the **adapter plug/unplug** and **instruction-file** scenarios before G1 and G7 respectively.

**Exit:** all 44 screens complete against the Simulation Core; `viguix-implementation.md` G8 exit criteria met.

---

## C1 — Control Layer

**Goal.** Live reasoning drives the interface that already exists — with no change to the interface. Loops run, tools execute, governance gates, identity is authenticated, and the model is called last and must say why.

**No agent workforce yet.** C1 proves the runtime with a single generic executor against the golden corpus; the roster arrives in C2 as adapters.

**Modules.** M4 · M5 · M7 (incl. Instruction Library) · M8 (LLM-minimal contract) · M9 · M12 (v1 subset) · M13 · M20 (identity) · M25 · M26 (estimate + levers) · M28 · **M33**

### Workstream A — Loop runtime
1. **Close `D1`.** Cyclic graph execution, typed state, reducer-merged updates (`FR-M4-01`, `FR-M4-04`).
2. **Load-time loop validation** — all eight bound fields or the loop does not execute (`FR-M4-02`).
3. **The six canonical loops** with §6.1 bounds and the amended L4 exit — merged *and* CI green (`FR-M4-03`).
4. **Durable checkpointing after every node** (`FR-M4-05`); **interrupt/resume for gates** (`FR-M4-06`); **time-travel replay** tagged as replay (`FR-M4-07`).
5. **Bound-breach handling** (`FR-M4-08`); **fan-out guard** and **concurrency cap** (`FR-M4-09`, `FR-M4-10`); one ledger entry per iteration (`FR-M4-11`).
6. **Cut over from the Simulation Core** — the production sidecar handshakes with the existing webview; every screen's scenario re-runs on live state (`AC-28`).

### Workstream B — Deterministic Engine *(the Python-first commitment)*
7. **Action-class catalogue** in policy (§7.10) (`FR-M33-01`). **Close `D16`** — who owns it.
8. **The deterministic capability set** (`FR-M33-02`): tree-sitter parsing and structural edits; LSP symbol resolution and references; build, test, lint and scanner runners; diff and patch; template scaffolding from skill packs; dependency, license and migration-reversibility classification; blast-radius from graph analysis; packet decomposition from the dependency graph; coverage-to-criteria mapping; cost estimation from ledger history; rule-based ambiguity detection; convention checks from `learned/rules/`.
9. **Deterministic-first dispatch** — every action tries the engine before the router (`FR-M33-03`).
10. **Assisted mode** — the engine does the work and hands the model a bounded, schema-typed gap, then validates the return (`FR-M33-04`).
11. **Generative mode** — every model output validated deterministically before it takes effect; failure is rework (`FR-M33-05`).
12. **Per-class reporting** — deterministic hit rate, assisted and generative rates, latency and cost saved (`FR-M33-07`). **Replay-identical deterministic paths** (`FR-M33-08`, `NFR-27`). **Model-call ceilings** (`FR-M33-09`).
13. **Loader for `learned/rules/`** with schema validation and refusal of executable content (`FR-M33-06`, `SEC-26`) — the hook the Trainer fills in C4.

### Workstream C — Model router, behind the engine
14. **Close `D2`.** Dual access paths (`FR-M8-01`, `FR-M8-07`); policy-driven tiering (`FR-M8-02`); budgets that refuse rather than overrun (`FR-M8-03`).
15. **Refusal of calls with a deterministic path** (`FR-M8-15`) and **`why_llm` on every permitted call** (`FR-M8-16`). **LLM dependency ratio exposed** (`FR-M8-17`, `FR-M17-10`). **Smallest tier that satisfies the schema** for assisted classes (`FR-M8-18`).
16. **Full call accounting** (`FR-M8-05`); **redaction with a log** (`FR-M8-11`); **backpressure pausing at checkpoints** (`FR-M8-13`); **structured output** (`FR-M8-14`); **caching and compaction as measured levers** (`FR-M8-04`, `FR-M26-04`).

### Workstream D — Tools and code intelligence
17. **MCP client** with pinning and trust-warning install (`FR-M9-01`, `FR-M9-08`). **Native tool set** (`FR-M9-02`). **Permission check before every call, denials recorded** (`FR-M9-03`, `SEC-14`).
18. **Sandbox** — dedicated directory, scrubbed environment, egress allow-list, timeout (`FR-M9-05`). **Credentials at the tool boundary only** (`FR-M9-07`).
19. **LSP bridge** (`FR-M28-01`), **tree-sitter** (`FR-M28-02`), **semantic search** meeting `NFR-19` (`FR-M28-03`, `FR-M28-06`), **reuse-first with citation** (`FR-M28-04`), **hunk-only large-file editing** and **generated-file exclusion** (`FR-M28-05`, `FR-M28-07`).

### Workstream E — Registry, memory, instructions
20. **Agent registry populated by adapter discovery** — the hook M31 fills in C2 (`FR-M5-01` as amended, `FR-M5-07`). Immutable versions, lifecycle states (`FR-M5-02`…`06`).
21. **Memory fabric** — three tiers, provenance, contradiction gating, untrusted tagging, human-curated agent-immutable entries, budgeted context assembly, retrieval logging (`FR-M7-01`…`08`, `FR-M7-11`, `FR-M7-13`).
22. **Instruction Library** (`FR-M7-14`…`16`) — discovery across adapter → workspace → user → organisation, precedence, digests recorded per invocation, trust boundary enforced.

### Workstream F — Governance, identity, XAI, HITL
23. **Policy engine** (`FR-M12-01`, `FR-M12-08`); **DoR/DoD as machine-checkable gates** (`FR-M12-09`); **no merge without recorded approval at any tier** (`FR-M12-05`); **approver identity in the ledger** (`FR-M12-07`); **governance can halt everything** (`FR-M12-06`).
24. **Authenticated human identity** (`FR-M20-01`). **Close `D9`.**
25. **Decision records; rationale labelled unverified; confidence with calibration per action class; ablation replay mandatory for high blast radius; model version on every explanation; no gate passable on an explanation** (`FR-M13-01`…`05`, `07`, `09`, `10`).
26. **Steer, clarifying questions, uncertainty escalation, partial acceptance, dry-run** (`FR-M25-01`…`04`, `06`).
27. **Cost estimate at ingest** (`FR-M26-01`).

### Workstream G — Security posture
28. `SEC-01`…`SEC-15`, `SEC-17` as the operating posture: untrusted-by-default, delimiting, **trifecta decomposition**, egress allow-list, sandbox, keychain credentials, redaction, pinned skills and servers, scoped identities, prohibited git operations, Halt All, denial logging, **injection classifier**, sandbox-escape tests.

### Exit criteria
- [ ] **The existing GUI runs unchanged on the production sidecar** — every scenario from `FR-M32-04` re-run live, contract-drift green (`AC-28`)
- [ ] The golden corpus (still small) runs live and replays identically (`AC-15`, `AC-16`)
- [ ] A loop missing a bound field fails to load
- [ ] `AC-27` — a model call attempted for an action class with a deterministic path is refused and recorded
- [ ] Every permitted model call carries a `why_llm`
- [ ] `AC-12` — no path to a protected branch without a recorded approver identity
- [ ] `AC-17`, `AC-18`, `AC-20`, `AC-22`
- [ ] `NFR-02`, `NFR-03`, `NFR-04`, `NFR-06`, `NFR-10`, `NFR-13`, `NFR-16`, `NFR-19`, `NFR-27`

### Decisions to close
`D1` · `D2` · `D9` · `D12` · `D14` · `D16`

### Risks retired or controlled
`R1` · `R3` · `R7` · `R20` · `R24` (controlled — per-class reporting exists before any reclassification)

---

## C2 — Adapters & Prebuilt Agents *(first value)*

**Goal.** The agent workforce arrives — as adapters. One story, one stack, ingest to merged pull request, through a roster that can be unplugged and re-plugged, alongside one of the organisation's own agents wrapped by a bridge. **This is the phase the programme is judged on.**

**Scope discipline (`E4`).** Java/Spring only. Single repository. One skill pack. One bridge.

**Modules.** **M31** · the §6.10 roster as adapters · M6 (one skill) · M17 (core) · M19 (Jira) · M23 (GitHub) · M24 (hover + chat) · SDLC phases 1–7

### Workstream A — The adapter framework
1. **`AgentAdapter` protocol** — `describe`, `plan`, `act`, `reflect`, `learn`, `export_state` / `import_state`, `health`, `probation_tasks`, versioned (`FR-M31-01`).
2. **Discovery** over `.meridian/adapters/` → `~/.meridian/adapters/` → registry, on start and on filesystem change (`FR-M31-02`). **Validation** with plain-language errors, invalid adapters listed not loaded (`FR-M31-03`).
3. **Hot plug and unplug** with no redeploy and no restart; in-flight work checkpointed and escalated (`FR-M31-04`, `NFR-24`).
4. **Probation for every adapter** at `suggest` (`FR-M31-07`). **Trainable surfaces** declared and honoured (`FR-M31-08`). **Action classes** declared per adapter (`FR-M31-09`).
5. **Adapters governed as executable code** — review, digest, sandbox, tool scope, revocation, signing for external sources (`FR-M31-10`, `SEC-24`).
6. **Portability** — `learned/` is the complete record; `export_state` / `import_state` over it (`FR-M31-12`).
7. **Close `D15`.** Ship the **plain-Python bridge** and the **MCP bridge** (`FR-M31-05`), each translating without modifying the wrapped agent, running it in the sandbox, routing every tool call through the permission check (`FR-M31-06`, `SEC-25`).
8. **Wrap one of the organisation's existing agents** with the plain-Python bridge and admit it through probation. `AC-24`.

### Workstream B — The prebuilt roster, built as adapters (`E12`)
9. **Chief Orchestrator**, **Analyst**, **Architect**, **Tech Lead**, **Scrum Master**, **Developer**, **Front-end**, **QA Engineer**, **QA Lead**, **Security**, **Reviewer**, **Governance** — each an adapter folder with manifest, `agent.py`, `skills/`, `instructions/`, `probation/`, `tests/`, and an empty `learned/`. **XAI** as the overlay.
10. Every prebuilt adapter declares its action classes per §7.10 so that scaffold, parse, test, classify and blast-radius run deterministically (`AC-26`), and passes the conformance suite.
11. **Unplug/re-plug test** on every prebuilt adapter — the framework is not done until the product's own workforce survives it.

### Workstream C — Skills and instructions
12. **Skill loader** — progressive disclosure, 3,000-token discovery budget, install review, sandboxed scripts (`FR-M6-01`…`07`, `09`). **One pack: `java-spring-gradle`**, shipped inside the Developer adapter (`FR-M6-10`).
13. **Prebuilt instruction files** — `AGENTS.md` and `CONVENTIONS.md` per adapter, and a workspace `AGENTS.md` template, wired through the Instruction Library.

### Workstream D — The SDLC chain, phases 1–7
14. **Phase 1 Intake** (`FR-P1-01`…`07`) — untrusted on ingest, ambiguity register with confidence, escalation via the question protocol, DoR gate, spec to the worktree. Ambiguity detection deterministic-first (rules), assisted for proposals.
15. **Phase 2 Design** (`FR-P2-01`…`06`) — ADRs, **blast-radius classification** deterministic from graph analysis, threat-surface delta, rollback strategy, human approval for high blast radius.
16. **Phase 3 Plan** (`FR-P3-01`…`05`) — packets **decomposed deterministically** from the dependency graph, acyclic and non-overlap validation, tests contracted before code.
17. **Phase 4 Build** (`FR-P4-01`…`10`) — skill-bound adapters, repository conventions outrank skill defaults, L1 micro loop, single-threaded writes, out-of-scope blocked, **migration classification deterministic**, dependency additions as a separate class.
18. **Phase 5 Verify** (`FR-P5-01`…`06`, `08`) — tests traced to criteria by a distinct adapter instance, baseline-fail verification, DoD, **full-surface regression**, flake quarantine.
19. **Phase 6 Security** (`FR-P6-01`…`05`) — per `D14`, resolved before this phase starts.
20. **Phase 7 Review** (`FR-P7-01`…`06`, `08`) — adversarial critique by a distinct instance, rejection re-enters L2, PR body with the verification checklist (`FR-M23-06`), **human approval mandatory at every tier**, review turnaround measured, hygiene criteria.

### Workstream E — Connectors, CI, surfaces, measurement
21. **Jira Cloud connector** (`FR-M19-01`) and **complexity tier at ingest** (`FR-M19-06`).
22. **GitHub Actions** — await CI, ingest results (`FR-M23-01`).
23. **Hover provenance** and gutter marks (`FR-M24-02`, `FR-M1-05`); **`@meridian` chat** gated on `D11` (`FR-M24-01`).
24. **Core KPIs from the ledger** including **the LLM dependency ratio** (`FR-M17-01`, `FR-M17-10`); **measured cycle time independent of perception** (`FR-M17-04`); ledger-derived, local by default (`FR-M17-05`, `FR-M17-06`).
25. **Signal accumulation begins** (`E9`) — every source the Trainer will need in C4 is recorded from now.

### Exit criteria — the C2 gate
**All 29 acceptance criteria in §10.1**, including the v2.1 six:
- [ ] `AC-23` an adapter folder plugs in within 5 s and unplugs with history intact
- [ ] `AC-24` an existing agent wrapped by the plain-Python bridge completes a packet under full governance, unmodified
- [ ] `AC-25` rehearsed: an exported adapter's `learned/` is complete (full round-trip is a C4 criterion)
- [ ] `AC-26` scaffold, parse, test, classify and blast-radius run with zero model calls on the reference story; LLM dependency ratio ≤ 0.35
- [ ] `AC-27`, `AC-28`, `AC-29` a bridged agent's out-of-allow-list egress is paused and recorded
- [ ] `AC-01`…`AC-22` as in v1.0
- [ ] **Every prebuilt adapter survives unplug and re-plug**
- [ ] **§10.2 quality bar** — FPY reported, cost per merged PR within ceiling, change failure rate no worse than the pre-Meridian baseline, over ≥20 real stories

### Decisions to close
`D11` · `D15`

### Risks retired or controlled
`R4` · `R5` · `R6` · `R10` (review) · `R21` (adapter supply chain — controlled) · `R23` (bridge escape — controlled)

> **Do not start C3 until the §10.2 bar is cleared.**

---

## C3 — Quality Gates

**Goal.** The system reliably catches its own errors, and specialisation works across the estate.

**Modules.** M12 (full) · M6 (full catalogue) · M16 (upgrade/revocation) · SDLC phase 5–7 additions

1. **Autonomy tiers** with promotion on thresholds and automatic demotion (`FR-M12-02`…`04`). **Close `D6`.**
2. **Full skill catalogue** (`FR-M6-08`), each pack shipped inside the relevant prebuilt adapter or standalone.
3. **Skill and adapter upgrade** through regression before activation (`FR-M16-09`, `FR-M31-14`); **revocation** pausing bound agents (`SEC-19`).
4. **Mutation testing** (`FR-P5-07`); **ephemeral environments** (`FR-P5-10`); **performance** and **accessibility** gates (`FR-P5-12`, `FR-P5-13`).
5. **Threat model** and **privacy impact** at design (`FR-P6-06`, `FR-P6-07`). **Multi-reviewer consensus** on high blast radius (`FR-P7-07`).
6. **License compliance** (`FR-P4-12`); **feature flags** (`FR-P4-11`).
7. **Tool-call anomaly detection** (`SEC-16`); **model output scanning** (`SEC-20`).
8. **DORA four keys plus rework** and the **throughput-vs-stability warning** (`FR-M17-02`, `FR-M17-03`).
9. **`NFR-25` held** — the LLM dependency ratio on the golden corpus does not rise between releases without a policy decision.

### Exit criteria
- [ ] Each gate blocks a deliberately introduced defect of its class
- [ ] Skill swapping proven across three stacks on brownfield repositories
- [ ] A revoked skill pack or adapter pauses every bound agent
- [ ] Tiers promote and demote on measured performance
- [ ] Throughput and stability reported together; the divergence warning fires on synthetic data
- [ ] `NFR-25`

### Decisions to close
`D6`

---

## C4 — Learning & Portability

**Goal.** Every adapter — prebuilt, custom, bridged — improves from its own history, writes only to `learned/`, turns recurring model output into deterministic rules, and travels with everything it learned.

**Modules.** M14 · M15 · M16 (adapter packages) · remaining bridges

### Workstream A — The Trainer
1. **Harvest from all six signal sources** (`FR-M14-01`); **human-edit ingestion** (`FR-M25-05`).
2. **Candidate deltas limited to prompts, playbooks, checklists and skill bindings** (`FR-M14-02`), **written only to `learned/`** (`FR-M14-14`, `E14`).
3. **Isolated evaluation** against the frozen suite, replayed stories and the golden corpus (`FR-M14-03`, `FR-M14-13`). **Promotion gating** (`FR-M14-04`). **Monotonic safety invariant** (`FR-M14-05`). **Human approval, no self-promotion** (`FR-M14-06`). Versioned, rollback-able, ten versions retained (`FR-M14-07`, `FR-M14-08`). Scheduled, never mid-story (`FR-M14-09`).
4. **Distillation to rules** — recurring model-produced patterns proposed as deterministic rules or templates into `learned/rules/`, gate-evaluated, so action classes move toward deterministic (`FR-M14-15`, `FR-M33-06`). **Close `D5`.**
5. **Identical operation on prebuilt, custom and bridged adapters** per their trainable surfaces (`FR-M14-16`). **Bridged agents' own learning mechanism** — run, suspend or shadow (`FR-M14-17`); **close `D17`.**
6. **Adversarial Breaker** (`FR-M14-10`). **Cross-team learning opt-in only** (`FR-M14-12`). **Contribution attribution** (`FR-M13-06`).
7. **Learned skill packs** into `learned/` (`FR-M6-11`).

### Workstream B — Onboarding and portability
8. **Onboarding as the human path onto hot plug** — new role or plug-in-existing, probation, admission blocked on failure, entry at `suggest` (`FR-M15-01`…`05`).
9. **Export is the adapter folder including `learned/`** (`FR-M16-01`, `FR-M31-12`); signed agent card (`FR-M16-02`); **exclusion scan** blocking on credentials, episodic memory, ledger blobs, untrusted content (`FR-M16-03`, `SEC-12`); **import** with signature, diff, probation, refusal on missing dependencies (`FR-M16-04`…`06`); **authorisation wrapper over interop protocols** (`FR-M16-07`); **internal registry** (`FR-M16-08`).
10. **Remaining bridges** per `D15` — A2A, LangGraph, CrewAI, OpenAI Agents (`FR-M31-05`). **Adapter SDK** — scaffold, local harness against the Simulation Core, conformance suite (`FR-M31-11`, `FR-M32-08`). **Concurrent adapters for one role** with selection policy (`FR-M31-13`). **Adapter dependencies** (`FR-M31-15`).
11. **Memory maturity** — layering, freshness, import/export (`FR-M7-09`, `FR-M7-10`, `FR-M7-12`). **Failover and local models** (`FR-M8-09`, `FR-M8-10`).

### Exit criteria
- [ ] The Trainer demonstrably raises first-pass yield under regression gating, and **rollback is exercised for real**
- [ ] **At least one action class moves from assisted or generative to deterministic through a promoted distilled rule, and the golden corpus's LLM dependency ratio falls as a result**
- [ ] A candidate that weakens a control is rejected and displayed as a failure
- [ ] `AC-25` — an adapter exported after learning a convention applies it on first use in a fresh workspace from `learned/rules/`, with no model call
- [ ] A bridged agent with its own learning mechanism behaves per `D17`, and the choice is in the ledger
- [ ] A custom adapter developed against the Simulation Core with the SDK passes conformance and enters probation live

### Decisions to close
`D5` · `D17`

### Risks retired
`R9` · `R25` (poisoned learned state — controlled)

---

## C5 — Orchestration, Scale & Compliance

**Goal.** Many stories, many repositories, many humans, many clients — and an audit.

**Modules.** Phase Orchestrators · M21 · M22 · M19 (rest) · M23 (rest) · M29 · M17 (full) · M20 (full) · M30 (full) · SDLC phases 8–9 · anchoring · crypto-shredding · tenant isolation

1. **Phase Orchestrators** and **sub-agent fan-out** under `FR-M4-09`.
2. **Story queue, worktree isolation per story, contention arbitration, overlap detection, SLA slip prediction** (`FR-M21-01`…`06`).
3. **Multi-repository** — manifest, interface contracts, linked PRs in order, monorepo scoping, contract tests (`FR-M22-01`…`04`, `FR-P4-13`, `FR-P5-11`).
4. **Remaining CI** and **CI failure re-entering L2**, **review-comment ingestion**, **CODEOWNERS**, **merge queue** (`FR-M23-01`…`05`). **Remaining connectors, write-back, attachments, templates** (`FR-M19-01`…`05`).
5. **Documentation Agent** as an adapter (`FR-M29-01`…`04`).
6. **Human roles, SoD, N-of-M, delegation, approval hygiene, Governor and Auditor** (`FR-M20-02`…`08`). **Session security** (`SEC-22`).
7. **Regulatory packs, compliance export, git-backed policy, emergency fast path, kill switch** (`FR-M12-10`…`14`).
8. **Crypto-shredding** on the S0 encrypted blob store (`FR-M10-14`); **anchoring** — **close `D3`** (`FR-M10-05`); **compaction**, **shareable slices**, **natural-language queries** (`FR-M10-15`, `FR-M10-17`, `FR-M10-13`).
9. **Tenant isolation** (`SEC-23`); **close `D13`**. **Key rotation** and **data classification** (`SEC-18`, `SEC-21`, `FR-M8-12`).
10. **Release and Operate** — plans with rollback, SLO correlation, escaped defects, incident linkage, post-merge edit tracking (`FR-P8-01`, `FR-P9-01`…`04`). **Close `D7`.**
11. **AI-BOM and provenance attestation** (`FR-P6-08`, `FR-P6-09`).
12. **Full telemetry** (`FR-M17-07`…`09`); **cost governance** (`FR-M26-02`, `03`, `05`, `06`); **remaining editor surfaces** (`FR-M24-03`, `04`, `06`); **operations completion** (`FR-M30-02`, `04`, `06`, `07`, `FR-M3-12`, `FR-M3-13`).
13. **Private marketplace** (`NFR-12`); **air-gapped CI verification** (`NFR-20`). **Ecosystem interfaces** (`ECO-01`, `02`, `04`, `05`, `07`).

### Exit criteria
- [ ] Ten concurrent stories without checkpoint loss (`NFR-17`, `FR-M27-05`)
- [ ] A multi-repository story completes with linked PRs merging in order
- [ ] A CI failure re-enters L2 and produces a corrected change unprompted
- [ ] An adapter exported by one team is adopted by another through probation
- [ ] An audit bundle is accepted in a real compliance review
- [ ] **An erasure request completes and the chain still verifies**
- [ ] SoD blocks a same-identity approval and names the alternative
- [ ] Cross-tenant leakage is impossible — verified by attempting it
- [ ] `NFR-15`, `NFR-18`, `NFR-20`, `NFR-23`

### Decisions to close
`D3` · `D7` · `D13`

### Risks retired
`R8` · `R12` · `R13` · `R16` · `R17` · `R19`

---

## C6 — Differentiation

| Item | Capability |
|---|---|
| `FR-M10-16` | Annotations and bookmarks on ledger entries |
| `FR-M13-08` | Counterfactual queries via targeted replay |
| `FR-M14-11` | Quality-diversity archive |
| `FR-M16-10` | Retirement handover of procedural memory |
| `FR-M19-07` | Batch epic ingestion |
| `FR-M24-05` | Agent-detected issues in the Problems panel |
| `FR-M30-05` | Scheduled tasks |
| `FR-P5-09` | Property-based and fuzz test generation |
| `FR-P8-02` | Deployment execution behind a Governor flag |
| `ECO-06` | Navion MCP browser as a documentation tool |
| `ECO-08` | teamlore import |

---

## 13. Cross-Cutting Workstreams

| Workstream | Cadence | Notes |
|---|---|---|
| **Simulation scenarios** *(v2.0)* | Ahead of every GUI phase; extended by every module that adds state | `FR-M32-04`. A screen without a scenario cannot start. |
| **Contract drift** *(v2.0)* | Every commit | `FR-M32-09`, `NFR-26`. Divergence fails the build. |
| **Golden corpus** | Every phase adds stories; CI runs the corpus on every runtime, agent, adapter or policy change | `FR-M27-03`; the Simulation Core is the runner |
| **LLM dependency ratio** *(v2.0)* | Every corpus run; reviewed at every phase exit | `NFR-25`, `FR-M17-10`. Must not rise without a policy decision. |
| **Adapter conformance** *(v2.0)* | Every adapter change, prebuilt or external | `FR-M31-11`. Unplug/re-plug is part of the suite. |
| **Fault injection** | Every module extends the set | `E10` |
| **Security regression** | Every commit | `SEC-17`, plus bridge-escape attempts from C2 |
| **Cross-platform** | Every phase exit, incl. Remote SSH | `NFR-22`, `FR-M3-11` |
| **Performance budgets** | CI from S0; low-spec profiling at phase exits | NFRs |
| **Signal accumulation** | From C2 | `E9` |
| **Prompt, policy, instruction and learned-state review** | All plain text under source control, reviewed as code | `NFR-13`, `SEC-26` |

---

## 14. Definition of Done — Any Module

- [ ] Every requirement implemented, or explicitly deferred with its phase named
- [ ] Every action writes a ledger entry before it is complete (`E1`)
- [ ] Loops declare all eight bound fields (`E5`)
- [ ] Untrusted inputs tagged and delimited (`E6`)
- [ ] Tool invocations permission-checked; denials logged
- [ ] No credential in agent context; all logged I/O redacted
- [ ] **v2.0** Every action class the module introduces is in the catalogue with a mode, and dispatches deterministic-first (`E13`)
- [ ] **v2.0** Every model call the module makes records a `why_llm`
- [ ] **v2.0** The Simulation Core has a scenario for every state the module adds
- [ ] **v2.0** If the module touches agents, it goes through the adapter protocol — no private path (`E12`)
- [ ] **v2.0** Anything the module learns is written to `learned/` under a validated schema (`E14`)
- [ ] Fault-injection cases exist and recovery paths verified (`E10`)
- [ ] Deterministic replay identical with zero model calls
- [ ] Golden corpus extended where behaviour changes
- [ ] Cross-platform, incl. Remote SSH
- [ ] Performance budgets on low-spec hardware
- [ ] Errors name a cause and a next action (`NFR-10`)
- [ ] State recoverable from disk (`NFR-07`); migration reversible (`FR-M30-03`)
- [ ] GUI contract published as generated types

---

## 15. Sequencing Dependencies

```
S0 Simulation Core & contracts
 │   M1 · M2(shell) · M3(+remote) · M18 · M10 substrate · M27 · M32 · M30(partial) · generated bus types
 │
 └─→ G0 ─ G1 ─ G2 ─ G3 ─ G4 ─ G5 ─ G6 ─ G6.5 ─ G7 ─ G8   ← the entire GUI, against the Simulation Core
      │
      └─→ C1 Control layer  ◄── the GUI switches to live with no change (AC-28)
           │   M4 · M33 · M8 · M9 · M28 · M5 · M7(+instructions) · M12(v1) · M13 · M20(identity) · M25 · M26
           │
           └─→ C2 Adapters & prebuilt agents  ◄── the gate the programme is judged on
                │   M31 · roster as adapters · M6(1 skill) · M17(core) · M19(Jira) · M23(GitHub) · M24 · phases 1–7 · 1 bridge
                │
                │   ══ §10.2 QUALITY BAR — 20 real stories ══
                │
                ├─→ C3 Quality gates ──────┐
                └─→ C4 Learning & portability ┴─→ C5 Orchestration, scale & compliance ──→ C6
```

**Hard serial:** `S0 → GUI → C1 → C2`. **Parallelisable:** C3 and C4 once C2's bar is cleared — C3 is depth on the slice, C4 is learning and portability; they converge before C5.

**The programme-level critical path** is `S0 → G0…G8 → C1 → C2`. It is longer to first value than v1.0's `P0 → P1`, by roughly the duration of G2–G8. That is the price of the stated build order, and it is paid once.

---

## 16. GUI Interlock

| Engineering | GUI | Joint deliverable |
|---|---|---|
| **S0** | — | The Simulation Core and generated types the GUI will be built against; the first scenarios (`FR-M32-04`) |
| **during G0–G8** | **G0 … G8** | Every screen, against the Simulation Core; engineering keeps scenarios ahead of screens and the drift check green |
| **C1** | — | The production sidecar handshakes with the finished GUI; every scenario re-runs live; no GUI change (`AC-28`) |
| **C2** | — | The roster as adapters appears in the Adapter Bay (10.43) and on the Floor; the Instruction Library (10.44) shows the prebuilt files; action classes populate the Observatory (10.31) |
| **C3–C5** | — | Modules light up the surfaces already built for them |

**The interlock rule, v2.0:** a GUI phase does not start until the Simulation Core has its scenarios. An engineering phase does not ship a state the GUI cannot show. Both directions are enforced by the contract-drift check.

---

## 17. Slip Plan

Cut in this order. Each cut leaves a working, safe system.

| Order | Cut | Cost |
|---|---|---|
| 1 | All C6 items | None |
| 2 | Bridges beyond plain-Python and MCP (`D15`) | Existing agents on other frameworks wait; the two shipped bridges cover most cases through MCP |
| 3 | Remaining connectors and CI beyond Jira and GitHub Actions | Narrows the pilot to one toolchain |
| 4 | M22 multi-repository | The polyglot promise slips; §1.3 already scopes v1 to single-repo |
| 5 | M29 Documentation Agent | Loses the documenting half of the brief |
| 6 | Distillation to rules (`FR-M14-15`) — ship the Trainer without it | The LLM dependency ratio plateaus instead of falling. **Keep signal accumulation regardless.** |
| 7 | M14 Trainer entirely | Loses self-improvement; `learned/` stays empty but the framework holds |
| 8 | M21 portfolio | One story at a time. Only under real pressure. |

**Never cut:** the Simulation Core and the contract-drift check · worktree isolation · the ledger and verification · human approval before merge · authenticated identity · the security posture including bridge isolation (`SEC-25`) · deterministic replay and the golden corpus · the adapter protocol and probation for every adapter · deterministic-first dispatch and `why_llm` · confidence-with-calibration · evidence-versus-narrative · steer and clarifying questions · full-surface regression · `learned/` as declarative data only (`SEC-26`).

---

## 18. Risk Retirement Schedule

| Risk | Retired or controlled in | Primary control |
|---|---|---|
| R1 prompt injection | C1 | `SEC-01`…`05`, `SEC-15` |
| R2 orphaned sidecars | **S0** | `FR-M3-02` + `03` |
| R3 cost blowup | C1 | Bounded loops, budgets, ceilings, deterministic-first |
| R4 over-trust | C2 | `FR-M17-04`; C3 `FR-M17-03` |
| R5 breaking working code | C2 | `FR-P5-06`, distinct test author |
| R6 non-composing output | C2, C5 | `FR-M4-09`, `FR-M22-02` |
| R7 memory poisoning | C1 | `FR-M7-07`, `SEC-15`, `FR-M7-16` |
| R8 ledger over-claimed | C5 | `FR-M10-06`, anchoring |
| R9 Trainer degradation | C4 | Frozen suite, invariant, corpus, rollback |
| R10 skill supply chain | C2, C3 | `FR-M6-06`, `SEC-19` |
| R11 distribution friction | S0 | Targets, resolution chain, doctor |
| R12 reviewer overload | C3 | `FR-P7-06`, batching |
| R13 provider shift | C4 | `FR-M8-08`…`10` |
| R14 destroyed uncommitted work | **S0** | M18 |
| R15 untestable runtime | **S0** | M27, M32 |
| R16 erasure conflict | C5 *(enabled S0)* | `FR-M10-14` on the S0 encrypted store |
| R17 rubber-stamping | C5 | `FR-M20-06`, N-of-M, SoD |
| R18 setup friction | S0 + G8 | Doctor, first-run |
| R19 cross-tenant leakage | C5 | `SEC-23`, `FR-M14-12` |
| R20 duplicate implementation | C1 | `FR-M28-04` |
| **R21 adapter supply chain** | **C2** | `SEC-24`, `FR-M31-10`, probation, revocation |
| **R22 contract drift** | **S0** | `FR-M32-09`, `NFR-26`, `AC-28` |
| **R23 bridged agent escapes governance** | **C2** | `FR-M31-06`, `SEC-25` |
| **R24 Python-first degrades quality** | **C1** controlled; C3 measured | `FR-M33-07` per-class reporting; `FR-M33-10` reviewed reclassification; shadow comparison |
| **R25 poisoned learned state travels** | **C4** | `SEC-26`, probation on import, gate-evaluated distillation |

---

## 19. Decision Schedule

| # | Decision | Must close by |
|---|---|---|
| `D4` | Python distribution | **S0 week 1** |
| `D10` | Golden corpus governance | **S0** |
| `D18` | Where `learned/` is persisted — committed, synced to registry, or both | **S0** *(affects `.gitignore` now)* |
| `D1` | Loop runtime | **C1 start** |
| `D2` | Model routing and tiering | **C1 start** |
| `D16` | Action-class catalogue ownership and reclassification evidence bar | **C1** |
| `D9` | Identity source | **C1** |
| `D12` | Workspace currency | **C1** |
| `D14` | Security phase placement and `AC-02` wording | **C2 start** |
| `D15` | Bridge types in v1 | **C2 start** |
| `D11` | Chat participant in v1 | **C2** |
| `D8` | Phase set fixed or configurable | **C1** *(GUI already assumes configurable)* |
| `D6` | Autonomy thresholds | **C3** |
| `D5` | Trainer scope — skill-pack edits or policy only | **C4** |
| `D17` | Bridged agents' own learning: run, suspend, shadow | **C4** |
| `D3` | Anchoring | **C5** |
| `D7` | Deployment execution | **C5** |
| `D13` | Tenant isolation ownership | **C5** |

---

## 20. Changes from v1.0

| Area | Change |
|---|---|
| **Build order** | GUI-first. `P0 → P1 → …` becomes `S0 → G0…G8 → C1 → C2 → …`. §0.2 reconciles this with the no-mock-data rule through the Simulation Core. |
| **Phases** | 6 → 7 engineering phases plus the ten GUI phases in between. Old P1 splits into C1 (control layer, no workforce) and C2 (adapters and prebuilt agents, first value). Old P3 and P4 recombine as C4 (learning and portability) and C5 (orchestration, scale and compliance). |
| **New modules placed** | M32 Simulation Core in S0; M33 Deterministic Engine in C1; M31 Agent Adapter Framework in C2, with remaining bridges and the SDK in C4. |
| **Build principles** | E11–E14 added: the Simulation Core is real; every agent — including ours — goes through the adapter protocol; deterministic first with `why_llm`; learning writes only to `learned/`. |
| **Stack decisions** | Five rows added: adapter protocol, adapter SDK, Deterministic Engine, action-class policy, learned-state schema. Router placed behind the engine. |
| **First-value gate** | Now C2, with `AC-23`…`AC-29` added and every prebuilt adapter required to survive unplug/re-plug. |
| **Definition of done** | Five v2.0 items: action classes catalogued and deterministic-first; `why_llm` recorded; simulation scenario exists; no private path around the adapter protocol; learning to `learned/` only. |
| **Slip plan** | Bridges beyond the two shipped are the second cut; distillation is cuttable before the Trainer; the never-cut list gains the Simulation Core, bridge isolation, deterministic-first dispatch, adapter probation, and `SEC-26`. |
| **Risks and decisions** | R21–R25 and D15–D18 scheduled. |

---

## 21. Traceability Appendix

Every requirement group mapped to a phase. **Bold** marks v2.1 additions or v1.0 promotions.

### Modules

| Phase | Modules and scope |
|---|---|
| **S0** | M1 *(all)* · M2 *(shell)* · M3 *(all except 12, 13)* · M10 *(01–12)* · M11 *(all)* · M18 *(all)* · M27 *(01–04)* · **M32 *(all)*** · M30 *(01, 03, 08)* |
| **C1** | M4 *(all)* · M5 *(01–07)* · M7 *(01–08, 11, 13, **14–16**)* · M8 *(01–08, 11, 13, 14, **15–18**)* · M9 *(all)* · M12 *(01, 05, 06, 07, 08, 09)* · M13 *(01–05, 07, 09, 10)* · M20 *(01)* · M25 *(01–04, 06)* · M26 *(01, 04)* · M28 *(all)* · **M33 *(01–05, 07–09)*** |
| **C2** | **M31 *(01–10, 12; 05 for MCP and Python)*** · M6 *(01–07, 09, **10**)* · M17 *(01, 04, 05, 06, **10**)* · M19 *(01 Jira, 06)* · M23 *(01 GitHub, 06)* · M24 *(01, 02)* |
| **C3** | M12 *(02, 03, 04)* · M6 *(08)* · M16 *(09)* · **M31 *(14)*** · M17 *(02, 03)* |
| **C4** | M14 *(all, incl. **14–17**)* · M15 *(all)* · M16 *(01–08)* · **M31 *(05 rest, 11, 13, 15)*** · **M32 *(08)*** · **M33 *(06, 10)*** · M6 *(**11**)* · M7 *(09, 10, 12)* · M8 *(09, 10)* · M13 *(06)* · M25 *(05, 07, 08)* |
| **C5** | M21, M22, M29 *(all)* · M19 *(02–05)* · M23 *(02–05)* · M17 *(07–09)* · M20 *(02–08)* · M24 *(03, 04, 06)* · M26 *(02, 03, 05, 06)* · M30 *(02, 04, 06, 07)* · M3 *(12, 13)* · M10 *(13, 14, 15, 17)* · M12 *(10–14)* · M8 *(12)* · M27 *(05)* |
| **C6** | M10 *(16)* · M13 *(08)* · M14 *(11)* · M16 *(10)* · M19 *(07)* · M24 *(05)* · M30 *(05)* |

### SDLC phase requirements

| Phase | Requirements |
|---|---|
| **C2** | FR-P1-01…07 · FR-P2-01…06 · FR-P3-01…05 · FR-P4-01…10 · FR-P5-01…06, 08 · FR-P6-01…05 *(per `D14`)* · FR-P7-01…06, 08 |
| **C3** | FR-P4-11, 12 · FR-P5-07, 10, 12, 13 · FR-P6-06, 07 · FR-P7-07 |
| **C5** | FR-P4-13 · FR-P5-11 · FR-P6-08, 09 · FR-P8-01 · FR-P9-01…04 |
| **C6** | FR-P5-09 · FR-P8-02 |

### Non-functional · Security · Acceptance · Ecosystem

| Phase | NFR | SEC | AC | ECO |
|---|---|---|---|---|
| **S0** | 01, 05, 07, 08, 09, 11, 22, **26** | 06, 07, 11, 13 | 07, 08, 13, 14, 19, 21 | — |
| **C1** | 02, 03, 04, 06, 10, 13, 16, 19, 23, **27** | 01…05, 08, 09, 10, 14, 15, 17, **26** | 12, 15, 16, 17, 18, 20, 22, **27, 28** | 03 |
| **C2** | **24, 25** | 12 *(scan)*, **24, 25** | 01…06, 09, 10, 11, **23, 24, 26, 29**, §10.2 | — |
| **C3** | 25 *(held)* | 16, 19, 20 | — | — |
| **C4** | — | — | **25** | — |
| **C5** | 12, 14, 15, 17, 18, 20, 21 | 18, 21, 22, 23 | — | 01, 02, 04, 05, 07 |
| **C6** | — | — | — | 06, 08 |

---

*End of plan. This document governs the build of `Requirements_Final.md` v2.1 and interlocks with `viguix-implementation.md` v2.1 at §16.*
