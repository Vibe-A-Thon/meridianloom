# Meridian Loom — Engineering Implementation Plan

| | |
|---|---|
| **Document** | Requirements-implementation.md |
| **Version** | 1.0 |
| **Author** | Ravaleedhar Reddy |
| **Governs** | The build order for everything specified in `Requirements_Final.md` v2.0 |
| **Companions** | `Requirements_Final.md` (30 modules, ~459 items) · `vision.md` (architecture) · `VIGUIX_Final.md` (interface) · `viguix-implementation.md` (GUI build order) |
| **Scale** | 6 phases · 30 modules · 9 SDLC phases · 384 release-targeted requirements |

---

## Table of Contents

0. [About This Plan](#0-about-this-plan)
1. [How to Use This Document](#1-how-to-use-this-document)
2. [Build Principles](#2-build-principles)
3. [Stack Decisions](#3-stack-decisions)
4. [Phase Map](#4-phase-map)
5. [P0 — Foundation](#p0--foundation)
6. [P1 — First Value](#p1--first-value)
7. [P2 — Quality Gates](#p2--quality-gates)
8. [P3 — Orchestration & Learning](#p3--orchestration--learning)
9. [P4 — Portability & Compliance](#p4--portability--compliance)
10. [P5 — Differentiation](#p5--differentiation)
11. [Cross-Cutting Workstreams](#11-cross-cutting-workstreams)
12. [Definition of Done — Any Module](#12-definition-of-done--any-module)
13. [Sequencing Dependencies](#13-sequencing-dependencies)
14. [GUI Interlock](#14-gui-interlock)
15. [Slip Plan](#15-slip-plan)
16. [Risk Retirement Schedule](#16-risk-retirement-schedule)
17. [Decision Schedule](#17-decision-schedule)
18. [Traceability Appendix](#18-traceability-appendix)

---

## 0. About This Plan

### 0.1 What this document is

`Requirements_Final.md` says *what* to build and assigns each requirement a release target (v1 / v1.x / v2). Its §12 sketches five delivery phases at module granularity. **This document turns that into a build order at requirement granularity** — what gets built in which phase, in what sequence within a phase, with the exit gate that lets the next phase start.

It is the engineering counterpart to `viguix-implementation.md`, and the two interlock in §14.

### 0.2 The scheduling conflict found while writing this

`Requirements_Final.md` §12 assigns modules to phases. Cross-checking that against each requirement's release target surfaces **13 requirements marked `v1` whose owning module or SDLC phase is scheduled in P2 or later**. A strict reading of §12 would ship Phase 1 without them.

| Requirement | Priority | §12 places it | Placed here | Why it cannot wait |
|---|---|---|---|---|
| FR-M12-01 | MUST v1 | P2 (M12) | **P1** | Policy must exist and be versioned before any gate can reference it |
| FR-M12-05 | MUST v1 | P2 (M12) | **P1** | `AC-12` is a Phase 1 acceptance criterion. §12 already flags this. |
| FR-M12-06 | MUST v1 | P2 (M12) | **P1** | Halt All (`SEC-13`) needs the governance engine to be able to stop the orchestrator |
| FR-M12-07 | MUST v1 | P2 (M12) | **P1** | `AC-12`. Approver identity in the ledger. §12 already flags this. |
| FR-M12-08 | MUST v1 | P2 (M12) | **P1** | Gate criteria and budget ceilings are expressed in policy packs; P1 gates need them |
| FR-M12-09 | MUST v1 | P2 (M12) | **P1** | DoR and DoD are the P1 gates (`FR-P1-06`, `FR-P5-04`) |
| FR-P6-01…05 | MUST v1 | P2 (Security phase) | **P1** | All marked MUST v1. See §0.3. |
| FR-M24-01 | SHOULD v1 | P4 (M24) | **P1**, gated on `D11` | Chat participant is v1-targeted; P4 is three phases too late |
| FR-M24-02 | SHOULD v1 | P4 (M24) | **P1** | Hover provenance is the cheapest possible XAI reach |

### 0.3 A related inconsistency worth a decision

`AC-02` describes the Phase 1 chain as *Intake → Design → Plan → Build → Verify → Review*. **Security is absent from that chain**, yet `FR-P6-01` through `FR-P6-05` are all MUST v1, and `AC-11` (prompt-injection containment) presumes security enforcement exists.

Two readings, and they need reconciling before P1 starts:

- **Reading A** — the Security *phase* is P2, but the security *controls* (`SEC-01`…`SEC-14`, tool permissions, sandbox, egress allow-list) are P1. `FR-P6-01`…`05` then belong in P2 with the phase.
- **Reading B** — `FR-P6-01`…`05` mean what their priority says, and `AC-02` is simply incomplete.

**This plan adopts Reading B** and places `FR-P6-01`…`05` in P1, because scanning a change for secrets and vulnerabilities before a human is asked to approve it is not a "quality gate" refinement — it is the minimum for letting agent-authored code reach a pull request. `AC-02` should be amended to read *Intake → Design → Plan → Build → Verify → Security → Review*. **Raised as `D14` in §17.**

### 0.4 Release target → phase mapping

| Target | Phases | Requirement count |
|---|---|---|
| **v1** | P0, P1 | 235 |
| **v1.x** | P2, P3, P4 | 138 |
| **v2** | P5 | 11 |

Within v1, the split is by *kind*: **P0 is platform** (nothing that reasons), **P1 is the first vertical slice** (one story, one stack, ingest to merge).

---

## 1. How to Use This Document

Six phases. Each is independently shippable and leaves a working system. Each has a hard exit gate; the next phase does not start until the gate is met.

**The rule that governs everything:** the exit gate for P1 is `AC-01`…`AC-22` plus the §10.2 quality bar, and **P2 does not begin until that bar is cleared on at least 20 real stories**. `Requirements_Final.md` states the reason plainly and it is worth repeating here: everything after P1 is an amplifier, and amplifying an unproven core amplifies error.

Two rules that follow from the evidence in `vision.md` §1.1:

- **Instrument before you accelerate.** Measured cycle time, first-pass yield and cost per merged PR exist from P1 (`FR-M17-01`, `FR-M17-04`), not from P4. A system that feels fast and measures slow must be caught by its own instrumentation.
- **The gates are the product.** Governance requirements are not a later phase. The six v1 governance requirements move into P1 (§0.2).

---

## 2. Build Principles

Ten principles, each derived from a design principle in `Requirements_Final.md` §3 or a tension in §15.

| # | Principle | Consequence |
|---|---|---|
| **E1** | **The ledger is built before anything that writes to it.** | M10's substrate is P0. No module ships a code path that acts without recording, because retro-fitting the ledger means auditing every call site. |
| **E2** | **Isolation before autonomy.** | M18 worktrees are P0, before a single agent exists. The first agent that runs must already be unable to touch the human's tree. |
| **E3** | **Replay before reasoning.** | M27 cassettes and the golden corpus harness are P0. If the runtime cannot be tested offline, every later phase is untestable and every regression is found in production. |
| **E4** | **One stack, one slice, all the way through.** | P1 is Java/Spring only, story→merge. Breadth is P2+. A half-depth product across five stacks proves nothing. |
| **E5** | **Every loop is bounded from its first commit.** | `FR-M4-02` validation runs at load time from day one. A loop without bounds never executes, even in development. |
| **E6** | **Untrusted-by-default is a P0 posture, not a P2 feature.** | `SEC-01`…`SEC-05` shape the tool layer and prompt assembly from the first agent invocation. Adding a trust boundary later means re-designing the context pipeline. |
| **E7** | **Human identity before human approval.** | `FR-M20-01` lands in P1. "Approved by someone" is not an audit record. |
| **E8** | **Nothing ships without its cost visible.** | Token accounting (`FR-M8-05`) is instrumented in P1 with the router itself, not added when the bill arrives. |
| **E9** | **Signals accumulate from P1 even though the Trainer arrives in P3.** | Gate decisions, CI failures, review comments and human edits are recorded from the moment they exist. `FR-M14-01` needs history, and history cannot be back-filled. |
| **E10** | **Every module ships with fault injection.** | `FR-M27-04` covers the runtime; each module extends it with its own failure modes. A module whose failure path has never been exercised is not done. |

---

## 3. Stack Decisions

Settle in P0. Changing them later is expensive. `D`-numbered rows are open decisions from `Requirements_Final.md` §14.

| Concern | Decision | Rationale |
|---|---|---|
| **Extension host** | TypeScript, esbuild-bundled, platform-specific VSIX targets where a runtime is bundled | `FR-M1-10`, `FR-M3-05a` |
| **Sidecar language** | Python 3.11+ | Stated constraint; where the orchestration ecosystem lives |
| **IPC** | Framed JSON-RPC 2.0 over stdio, schema-versioned, handshake-checked | `FR-M3-01`, `FR-M3-08` |
| **Loop runtime** | **`D1` — open.** Durable graph runtime (LangGraph-class) vs. minimal in-house. Requirements specify *capabilities* so the engine stays substitutable. | Must close before P1 |
| **Checkpointer** | SQLite-backed, local. No external database in v1. | `FR-M4-05`, workspace-local architecture |
| **Ledger store** | SQLite, append-only with delete/update triggers, content-addressed encrypted blob store | `FR-M10-01`, `FR-M10-07`, `FR-M10-14` |
| **Merkle / signing** | SHA-256 chain + Merkle tree; signing key in OS keychain via SecretStorage | `FR-M10-02`…`04` |
| **Anchoring** | **`D3` — open.** Local signing only / internal transparency service / external TSA. | Must close by P4 |
| **Isolation** | Git worktree per story, agent git identity, optional SSH/GPG commit signing | M18 |
| **Tools** | MCP client (stdio) + native tool set; LSP bridge; tree-sitter | M9, `FR-M28-01`, `FR-M28-02` |
| **Semantic search** | Local embedding index, incrementally updated, rebuildable from source | `FR-M28-03`, `FR-M7-03` |
| **Model access** | Direct provider APIs from the sidecar (primary); `vscode.lm` proxied (secondary) | `FR-M8-01` |
| **Model routing** | **`D2` — open.** Tiering policy per phase and task class. | Must close before P1 |
| **Structured output** | Schema-constrained generation where supported; validation + bounded retry otherwise | `FR-M8-14` |
| **Replay** | Cassettes keyed by canonical request hash; golden corpus in CI with zero model calls | M27 |
| **Python distribution** | **`D4` — open.** Bundled runtime in platform-specific VSIX vs. workspace interpreter. | Must close in P0 |
| **Remote** | SSH / WSL / Dev Containers / Codespaces, sidecar on the remote host | `FR-M3-11` |
| **Identity** | **`D9` — open.** VS Code account / SSO-OIDC / Git identity, and whether more than one at once. | Must close in P1 |
| **Connectors** | Jira Cloud first (P1); Rally, ADO, Jira DC, GitHub Issues in P3 | `FR-M19-01` |
| **CI** | GitHub Actions first (P1); GitLab, ADO, Jenkins in P3 | `FR-M23-01` |
| **Telemetry export** | OpenTelemetry, opt-in, local by default | `FR-M30-06`, `FR-M17-06` |

---

## 4. Phase Map

| Phase | Name | Modules | Release | Duration signal |
|---|---|---|---|---|
| **P0** | Foundation | M1, M2 *(shell)*, M3, M10 *(substrate)*, M18, M27, M30 *(partial)* | v1 | The platform is stable and records reliably |
| **P1** | First Value | M4, M5, M6 *(single skill)*, M7, M8, M9, M10, M11, M12 *(v1 subset)*, M13, M17 *(core)*, M19 *(Jira)*, M20 *(identity)*, M23 *(GitHub)*, M24 *(hover + chat)*, M25, M26, M28, SDLC phases 1–7 | v1 | One story, one stack, ingest to merge, gated and recorded |
| **P2** | Quality Gates | M12 *(full)*, M6 *(full catalogue)*, M16 *(upgrade/revocation)*, SDLC phase 5–7 additions | v1.x | The system reliably catches its own errors |
| **P3** | Orchestration & Learning | Phase Orchestrators, sub-agent fan-out, M14, M19 *(rest)*, M21, M22, M23 *(rest)*, M29 | v1.x | The organisation coordinates at scale and improves itself |
| **P4** | Portability & Compliance | M15, M16 *(full)*, M17 *(full)*, M24 *(rest)*, M26 *(rest)*, M30 *(full)*, SDLC phases 8–9, anchoring, crypto-shredding, tenant isolation | v1.x | It scales across teams and survives audit |
| **P5** | Differentiation | 11 v2 items | v2 | Not blocking |

---

## P0 — Foundation

**Goal.** Nothing reasons yet. The platform installs everywhere, spawns and tears down cleanly, isolates every write, records tamper-evidently, and can replay itself offline.

**Modules.** M1 · M2 (shell only) · M3 · M10 (substrate) · M18 · M27 · M30 (doctor, migration, uninstall)

### Workstream A — Extension host and lifecycle

1. **Extension scaffold.** Granular activation events, never `*` (`FR-M1-01`). Activity Bar container with the five tree views (`FR-M1-02`). The twelve commands (`FR-M1-03`).
2. **Thread discipline.** No blocking synchronous work over 50 ms on the extension host (`FR-M1-04`). All orchestration in the sidecar.
3. **SecretStorage adapter** (`FR-M1-06`) with **refuse-to-start on unavailability** (`FR-M1-07`) — notably Linux without a keyring. Silent plaintext fallback is a security defect, not a degraded mode.
4. **Progress and cancellation** wired to sidecar loop cancellation (`FR-M1-09`).
5. **Bundling** with esbuild via `vscode:prepublish`, `vscode` external, `.vscodeignore` (`FR-M1-10`).

### Workstream B — Sidecar and IPC *(the largest reliability risk)*

6. **Spawn and framed JSON-RPC over stdio** (`FR-M3-01`). stdout carries only RPC; logging to stderr and a rotating file (`FR-M3-09`).
7. **The dual teardown contract.** Supervisor terminates on `deactivate()`, webview disposal and any deactivation (`FR-M3-02`) **and** the sidecar independently self-terminates within 10 s if orphaned (`FR-M3-03`). **Both halves. Orphaned sidecars are a documented failure mode in shipping agent extensions.**
8. **Spawn error handling** distinguishing the `error` event from a non-zero exit, with actionable diagnostics for `ENOENT`, `EACCES` and policy-blocked execution (`FR-M3-04`).
9. **Interpreter resolution chain** with the resolved path in the status bar (`FR-M3-05`). **Close `D4`**, then implement platform-specific VSIX targets if a runtime is bundled (`FR-M3-05a`).
10. **Remote support** — SSH, WSL, Dev Containers, Codespaces, sidecar on the remote host (`FR-M3-11`). Build this in P0, not as a later port; the process model differs.
11. **Health checks and restart policy** — 5 s heartbeat, at most 3 restarts in 5 minutes before a failed state (`FR-M3-06`).
12. **Versioned RPC contract** with refusal on mismatch (`FR-M3-08`). No network listener by default (`FR-M3-10`).
13. **Resource limits** via cgroups or job objects where supported (`FR-M3-12`). *(SHOULD v1.x — build the hook in P0, enforce in P4.)*

### Workstream C — Workspace isolation *(the T1 resolution)*

14. **Worktree manager.** One git worktree per story under `.meridian/worktrees/<story-id>/` (`FR-M18-01`). Branch naming from configurable convention off a configurable base (`FR-M18-02`).
15. **Conflict detection** — human uncommitted changes overlapping a packet's target paths, surfaced *before* the packet starts (`FR-M18-03`).
16. **Story abort** — remove worktree, delete unpushed branch, release claims, leave the primary tree untouched, ledger-record the abort (`FR-M18-04`).
17. **Agent git identity**, distinct from the human's (`FR-M18-05`). Commit convention with the ledger range in a trailer (`FR-M18-07`).
18. **Open worktree in a new window / check out the story branch** (`FR-M18-08`).
19. **`.gitignore` initialisation** for `ledger`, `checkpoints`, `episodic`, `worktrees`, `cassettes` (§4.2).

### Workstream D — Ledger substrate

20. **Append-only SQLite** with delete/update prevented by trigger (`FR-M10-01`), implementing the §7.2 schema including the fields the merge added: `human_role`, `worktree_ref`, `repo_id`, `replay_of`, `blob_key_id`.
21. **Hash chain and Merkle tree** with inclusion and consistency proofs (`FR-M10-02`, `FR-M10-03`). Canonicalisation rule implemented exactly as §7.2 states.
22. **Signed tree heads** on the configured cadence, key in the OS keychain (`FR-M10-04`).
23. **Content-addressed encrypted blob store** with per-subject keys, so `FR-M10-14` crypto-shredding is possible in P4 without a schema migration. **Encrypt from day one; retro-fitting is a data migration across every blob.**
24. **Chain verification** on start and on demand, under 5 s for 100k entries, reporting the first divergent sequence (`FR-M10-09`).
25. **Synchronous write semantics** — an action is not complete until its entry commits (`FR-M10-08`).
26. **Ledger query API** (`FR-M10-12`) — filter, aggregate, time-range, full-text. The dashboard, CLI and external tools all consume it.

### Workstream E — Replay and testability

27. **Cassette recorder.** Every model call and tool result recorded, keyed by canonical request hash (`FR-M27-01`).
28. **Deterministic replay** producing an identical ledger with zero model calls (`FR-M27-02`).
29. **Fault injection console** — model timeouts, tool failures, sidecar kills, corrupted ledger entries (`FR-M27-04`).
30. **Golden corpus harness.** The runner, the corpus format and the CI job exist in P0 even though the corpus is empty; **`D10` (corpus governance) must close here.** Stories accumulate through P1.

### Workstream F — Operations

31. **`meridian doctor`** — interpreter, sidecar, keychain, ledger integrity, MCP servers, skill digests, each with a fix-it action (`FR-M30-01`).
32. **State migration** across extension versions, automatic, versioned, reversible (`FR-M30-03`).
33. **Clean uninstall** that never removes the ledger without explicit confirmation (`FR-M30-08`).

### Data contracts
`handshake` · `state.snapshot` · `state.patch` · `error.raised` · `worktree.create|abort|status` · `ledger.append|query|verify|proof` · `cassette.record|replay` · `fault.inject` · `doctor.run`

### Exit criteria
- [ ] Extension installs and activates on Windows, macOS and Linux, **and under VS Code Remote — SSH with the repository on the remote host** (`AC-19`)
- [ ] `AC-08` — no orphaned Python process after window close, reload or extension disable, verified on all three platforms
- [ ] `AC-07` — killing the sidecar mid-operation and reloading the window resumes from checkpoint, losing at most one node
- [ ] `AC-14` — a story aborted mid-flight leaves the primary working tree byte-identical to its pre-story state
- [ ] `AC-13` — a human edit overlapping a pending packet is surfaced before the packet starts, and is never lost
- [ ] `AC-21` — `git blame` shows the agent identity; the commit trailer resolves to the correct ledger range
- [ ] Chain verification passes; a deliberately corrupted entry is detected and its sequence named
- [ ] A trivial recorded operation replays deterministically to an identical ledger
- [ ] Fault injection exercises all four failure classes and each recovery path holds
- [ ] `meridian doctor` reports every check with an actionable result
- [ ] `NFR-01` activation ≤500 ms · `NFR-05` sidecar idle ≤400 MB · `NFR-08` transactional ledger writes

### Decisions to close
`D4` Python distribution · `D10` golden corpus governance

### Risks retired
`R2` orphaned sidecars · `R14` destroyed uncommitted work · `R11` distribution friction (partially)

---

## P1 — First Value

**Goal.** One story. One stack. Ingest to merged pull request. Every action recorded, every gate human-approved, every cost visible.

**Scope discipline (`E4`).** Java/Spring only. Single repository. One skill pack. Breadth is P2 and later. **This is the phase the entire programme is judged on.**

**Modules.** M4 · M5 · M6 (single skill) · M7 · M8 · M9 · M10 · M11 · **M12 (v1 subset — see §0.2)** · M13 · M17 (core) · M19 (Jira) · M20 (identity) · M23 (GitHub) · **M24 (hover + chat)** · M25 · M26 · M28 · SDLC phases 1–7 · ECO-03

### Workstream A — Loop runtime

1. **Close `D1`** — adopt a durable graph runtime or build a minimal one. Blocks everything else in this phase.
2. **Cyclic graph execution** with typed state and reducer-merged concurrent updates; silent last-write-wins prohibited (`FR-M4-01`, `FR-M4-04`).
3. **Loop definition validation at load time.** A loop missing entry condition, body, exit criteria, max iterations, token budget, wall-clock budget, cost ceiling or escalation target **fails validation and does not execute** (`FR-M4-02`, `E5`).
4. **The six canonical loops** with §6.1 default bounds, including the amended L4 exit criterion — **merged *and* CI green** (`FR-M4-03`).
5. **Durable checkpointing after every node** (`FR-M4-05`) and **interrupt/resume for human gates** that persists and releases resources (`FR-M4-06`).
6. **Time-travel replay from any checkpoint**, ledger-tagged as a replay, never counted as live work (`FR-M4-07`).
7. **Bound-breach handling** — halt, ledger-record the reason, escalate; never silently continue or abandon (`FR-M4-08`).
8. **Fan-out guard** — rejected when packets share a target path (`FR-M4-09`). Global concurrency cap (`FR-M4-10`).
9. **One ledger entry per iteration minimum** (`FR-M4-11`).

### Workstream B — Agents, skills and memory

10. **Agent registry** — manifests only, never hard-coded (`FR-M5-01`…`06`), implementing the §7.1 schema including per-action-class confidence thresholds and the context budget.
11. **Skill loader** with three-stage progressive disclosure and the 3,000-token discovery budget (`FR-M6-01`…`03`). **One pack in P1: `java-spring-gradle`.**
12. **Skill install review UI and sandbox constraint** (`FR-M6-06`, `FR-M6-07`) — built now even with one pack, because it is a security surface and retro-fitting review to an installed-pack flow is worse.
13. **Memory fabric** — three tiers, file-based, provenance on every entry (`FR-M7-01`…`04`).
14. **Contradiction gating on writeback** (`FR-M7-05`) and **untrusted tagging with no promotion without human approval** (`FR-M7-07`). *The primary defence against memory poisoning.*
15. **Human-curated, agent-immutable procedural memory** (`FR-M7-11`).
16. **Budgeted, ranked context assembly** logging what was included and what was cut (`FR-M7-13`).
17. **Retrieval logging into the ledger input digest** (`FR-M7-08`).

### Workstream C — Model router

18. **Close `D2`** — routing and tiering policy per phase and task class (`FR-M8-02`).
19. **Dual access paths** — direct provider APIs primary, `vscode.lm` proxied secondary with distinct handling of `NoPermissions` / `NotFound` / `Blocked` (`FR-M8-01`, `FR-M8-07`).
20. **Budget enforcement** per story, phase and agent, refusing rather than overrunning (`FR-M8-03`).
21. **Full call accounting** — model and version, tokens in/out, latency, cost, cache status (`FR-M8-05`). `E8`.
22. **PII and secret redaction before transmission, with a redaction log** (`FR-M8-11`). `AC-22`.
23. **Rate-limit backpressure that pauses loops at a checkpoint** rather than failing them (`FR-M8-13`).
24. **Structured output enforcement** with validation and bounded retry (`FR-M8-14`).
25. **Prompt/result caching and context compaction as measured cost levers** (`FR-M8-04`, `FR-M26-04`).

### Workstream D — Tools and code intelligence

26. **MCP client** over stdio with version pinning and trust-warning install (`FR-M9-01`, `FR-M9-08`).
27. **Native tool set** — repo read, patch apply, build, test, static analysis, dependency scan, SCM (`FR-M9-02`).
28. **Permission check before every invocation, denials ledger-recorded** (`FR-M9-03`, `SEC-14`).
29. **Sandboxed execution** — dedicated working directory, scrubbed environment, egress allow-list, wall-clock timeout (`FR-M9-05`). `SEC-05`.
30. **Credentials injected at the tool boundary, never in agent context, redacted from all logs** (`FR-M9-07`, `SEC-06`, `SEC-07`).
31. **LSP bridge** — diagnostics, symbols, references, rename (`FR-M28-01`).
32. **Tree-sitter** for structural edits, AST-aware diffs and pre-write syntax validation (`FR-M28-02`).
33. **Semantic code search**, incremental, meeting `NFR-19` (1M LOC initial index under 10 minutes) (`FR-M28-03`, `FR-M28-06`).
34. **Reuse-first policy with citation** and duplicate detection (`FR-M28-04`). `E10` of the design principles; `R20`.
35. **Large-file hunk-only editing** and **binary/generated file exclusion** (`FR-M28-05`, `FR-M28-07`).

### Workstream E — Governance, identity and XAI *(promoted from P2 — §0.2)*

36. **Policy engine, declarative and version-controlled** (`FR-M12-01`), expressing gate criteria, budget ceilings, egress allow-lists, permitted tools (`FR-M12-08`).
37. **DoR and DoD as machine-checkable gate criteria** with human judgement as fallback, not default (`FR-M12-09`).
38. **No merge to a protected branch without recorded human approval, at any tier** (`FR-M12-05`). `AC-12`.
39. **Approver identity in the ledger; anonymous approval impossible** (`FR-M12-07`).
40. **Governance can halt the Chief Orchestrator and all loops** (`FR-M12-06`) — the engine behind `SEC-13` Halt All.
41. **Authenticated human identity** — VS Code account, SSO/OIDC or Git identity, never free text (`FR-M20-01`). **Close `D9`.**
42. **Decision records** on every consequential decision (`FR-M13-01`).
43. **Rationale stored and surfaced as explicitly unverified narrative** (`FR-M13-02`) and **confidence recorded with calibration tracked over time** (`FR-M13-03`), per action class (`FR-M13-09`).
44. **Ablation replay**, mandatory before high-blast-radius gates (`FR-M13-04`, `FR-M13-05`).
45. **Model and version on every explanation surface** (`FR-M13-10`).
46. **No gate passable on an explanation** (`FR-M13-07`) — enforced in the gate evaluator, not by convention.

### Workstream F — Steering and human-in-the-loop

47. **Steer** — guidance injected into a running loop without a full rework, ledger-recorded (`FR-M25-01`).
48. **Clarifying-question protocol** — structured question with options and the agent's own recommendation; loop resumes on answer (`FR-M25-02`).
49. **Uncertainty-triggered escalation** on per-action-class confidence thresholds (`FR-M25-03`). `AC-18`.
50. **Partial acceptance** of hunks (`FR-M25-04`) and **dry-run / plan-only mode** (`FR-M25-06`). `AC-20`.

### Workstream G — The SDLC chain, phases 1–7

51. **Phase 1 Intake.** Story from file, Jira connector or text (`FR-P1-01`). **Story tagged untrusted on ingest** (`FR-P1-02`). Ambiguity register with confidence (`FR-P1-04`); high-severity ambiguities escalate via the question protocol, never resolved by assumption (`FR-P1-05`). DoR gate (`FR-P1-06`). Spec written to the worktree as a reviewable artifact (`FR-P1-07`).
52. **Phase 2 Design.** ADRs to the repository (`FR-P2-02`). **Blast-radius classification** (`FR-P2-03`) — this drives gate strictness everywhere downstream, so it is not optional in P1. Threat-surface delta at design time (`FR-P2-04`). Observability and rollback strategy (`FR-P2-05`). High-blast designs need human approval regardless of tier (`FR-P2-06`).
53. **Phase 3 Plan.** Work packets per §7.3 with target paths, stack, skill, acceptance tests, dependencies, budget (`FR-P3-01`, `FR-P3-02`). Acyclic validation and non-overlap verification (`FR-P3-03`). **Every packet has at least one acceptance test before implementation begins** (`FR-P3-05`) — tests are contracted before code is written.
54. **Phase 4 Build.** Skill-bound developer agents (`FR-P4-01`). **Repository conventions outrank skill defaults on brownfield** (`FR-P4-03`). L1 micro loop (`FR-P4-04`). Single-threaded writes per service (`FR-P4-05`). Out-of-scope modification blocked and escalated (`FR-P4-07`). **Migration safety classification** (`FR-P4-10`). Dependency additions as a separate approvable class (`FR-P4-08`, `SEC-09`).
55. **Phase 5 Verify.** Tests traced to criteria (`FR-P5-01`), authored by a **different agent instance** from the implementer (`FR-P5-02`), verified to fail against baseline (`FR-P5-03`). DoD verdict (`FR-P5-04`). **Full-affected-surface regression, not changed-files-only** (`FR-P5-06`) — this is the control for `R5`. **Flake quarantine, never silent retry-to-green** (`FR-P5-08`).
56. **Phase 6 Security** *(promoted — §0.3)*. SAST, SCA, secrets (`FR-P6-01`). New high/critical findings block; waivers need justification (`FR-P6-02`). SBOM delta (`FR-P6-03`). **Injected-instruction and unexpected-egress checks** (`FR-P6-04`). Governance verifies no gate was bypassed and the chain verifies (`FR-P6-05`).
57. **Phase 7 Review.** Adversarial critique against the skill checklist and policy pack (`FR-P7-01`), by an instance distinct from implementer *and* test author (`FR-P7-02`). Rejection re-enters L2 with the critique as feedback (`FR-P7-03`). **PR body per `FR-P7-04` plus the verification checklist** (`FR-M23-06`). **Human approval mandatory before merge at every tier** (`FR-P7-05`). Review turnaround measured (`FR-P7-06`) — `R12`. Secrets, debug artifacts, TODOs and commented-out code as explicit criteria (`FR-P7-08`).

### Workstream H — Connectors, CI and surfaces

58. **Jira Cloud connector** with field mapping to the §7.5 story schema (`FR-M19-01`). **Complexity tier at ingest** selecting loop bounds and model tiering (`FR-M19-06`).
59. **GitHub Actions integration** — await CI, ingest results (`FR-M23-01`).
60. **Hover provenance** on agent-authored lines (`FR-M24-02`) and **gutter thread marks** (`FR-M1-05` decorations).
61. **`@meridian` chat participant** with the seven slash commands (`FR-M24-01`) — **gated on `D11`**; if the decision is "not in v1", this drops and nothing else changes.
62. **Diff application via the workspace edit API, always targeting the story worktree** (`FR-M1-05` as amended).

### Workstream I — Measurement

63. **Core KPIs from the ledger** — first-pass yield, intervention rate, rework rate, cost per merged PR, tokens per story as a distribution, time to merge, calibration error (`FR-M17-01`).
64. **Measured cycle time recorded independently of any perceived-speed signal** (`FR-M17-04`). This is the `R4` control and it exists in P1 or it never exists.
65. **All KPIs derived from the ledger, no separate instrumentation store** (`FR-M17-05`). **Telemetry local by default** (`FR-M17-06`).
66. **Cost estimate at ingest with a confidence interval** (`FR-M26-01`).
67. **Signal accumulation begins** (`E9`) — gate decisions with reasons, CI failures, human edits, all recorded from now even though the Trainer arrives in P3.

### Workstream J — Security posture

68. `SEC-01`…`SEC-14` implemented as the operating posture, not a checklist: untrusted-by-default, delimiting, **trifecta decomposition** (`SEC-03`), egress allow-list, sandbox, keychain credentials, redaction, pinned skills and MCP servers, scoped agent identities, prohibited git operations, Halt All, and denial logging.
69. **Prompt-injection classifier** screening untrusted content before it enters context, detections ledger-recorded (`SEC-15`).
70. **Sandbox escape tests in the security regression suite** (`SEC-17`).

### Exit criteria — the P1 gate

**All 22 acceptance criteria in §10.1**, plus:

- [ ] `AC-01`…`AC-06` the chain runs end to end without per-step prompting and produces a PR
- [ ] `AC-09` swapping the skill pack changes output conventions with no extension change
- [ ] `AC-10` first-pass yield and cost per merged PR reported across ≥20 real stories
- [ ] `AC-11` a prompt-injection payload in the story file and a repo comment causes no out-of-permission tool invocation, and the attempt is recorded
- [ ] `AC-12` no path reaches a protected branch without a recorded approver identity
- [ ] `AC-15`, `AC-16` deterministic replay and a passing golden corpus with zero model calls
- [ ] `AC-17`, `AC-18` steer visible in the next iteration; sub-threshold confidence produces a question, not an action
- [ ] `AC-20` dry-run produces a packet graph and cost estimate without writing a file
- [ ] `AC-22` a synthetic credential is redacted before transmission and the redaction logged
- [ ] **§10.2 quality bar** — measured FPY, cost per merged PR within ceiling, and **change failure rate for agent-authored merges no worse than the team's pre-Meridian baseline**

### Decisions to close
`D1` loop runtime · `D2` model routing · `D9` identity source · `D11` chat participant · `D12` workspace currency

### Risks retired or controlled
`R1` prompt injection · `R3` cost blowup · `R4` over-trust · `R5` breaking working code · `R6` non-composing output · `R7` memory poisoning · `R15` untestable runtime · `R20` duplicate implementation

> **Do not start P2 until the §10.2 bar is cleared.** This is the single most important scheduling rule in the programme.

---

## P2 — Quality Gates

**Goal.** The system reliably catches its own errors, and specialisation works across the technology estate.

**Modules.** M12 (full) · M6 (full catalogue) · M16 (upgrade and revocation) · SDLC phase 5–7 additions

### Tasks

1. **Autonomy tiers** — four levels, every agent starting at `suggest`, promotion on measured thresholds, automatic demotion on regression, all ledger-recorded (`FR-M12-02`…`04`). **Close `D6`** (thresholds per task class).
2. **Full skill catalogue** — the remaining nine packs (`FR-M6-08`), each with its own review, digest pinning and review checklist.
3. **Skill pack upgrade** running bound agents through regression before activation (`FR-M16-09`) and **revocation** pausing bound agents until rebound (`SEC-19`).
4. **Mutation testing** on agent-authored tests at a configurable sample rate (`FR-P5-07`).
5. **Ephemeral test environments** via Testcontainers; agents may not point tests at shared environments (`FR-P5-10`).
6. **Performance regression gate** on declared or detected hot paths (`FR-P5-12`) and **accessibility gate** for front-end packets (`FR-P5-13`).
7. **Threat model artifact** for security-relevant changes (`FR-P6-06`) and **privacy impact checklist** for personal-data changes (`FR-P6-07`).
8. **Multi-reviewer consensus** on high-blast changes, with disagreements surfaced rather than averaged (`FR-P7-07`).
9. **License compliance** on agent-added dependencies (`FR-P4-12`).
10. **Feature flag integration** for risky changes (`FR-P4-11`).
11. **Tool-call anomaly detection** against an agent's baseline, pausing above threshold (`SEC-16`).
12. **Model output scanning** for malicious patterns, obfuscation and embedded credentials before code reaches the tree (`SEC-20`).
13. **DORA four keys plus rework signal** from SCM and CI (`FR-M17-02`) and the **throughput-vs-stability divergence warning** (`FR-M17-03`) — the `R4` and `R12` instrument.

### Exit criteria
- [ ] Gates block real defects — verified by deliberately introducing a defect class per gate and confirming each is caught
- [ ] Skill swapping proven across **three stacks** with conventions correctly applied on brownfield repositories
- [ ] A revoked skill pack pauses every bound agent
- [ ] An agent's autonomy tier promotes on sustained performance and demotes automatically on regression
- [ ] Throughput and stability are reported together and the divergence warning fires on synthetic data
- [ ] Mutation score, performance and accessibility gates each block a deliberately weak change

### Decisions to close
`D6` autonomy tier thresholds

### Risks retired
`R10` skill supply chain · `R12` reviewer overload (instrumented)

---

## P3 — Orchestration & Learning

**Goal.** The organisation coordinates at scale, spans repositories, and improves itself from its own history.

**Modules.** Phase Orchestrators · sub-agent fan-out · M14 · M19 (remaining connectors) · M21 · M22 · M23 (remaining CI) · M29

### Workstream A — Orchestration at scale

1. **Phase Orchestrators** — one per SDLC phase, owning entry and exit gates, reporting a verdict upward and unable to advance the story themselves.
2. **Sub-agent fan-out** on genuinely non-overlapping packets only, under `FR-M4-09` and the global concurrency cap.
3. **Story queue** with priority, WIP limits and dependency ordering (`FR-M21-01`). **Worktree isolation per concurrent story** (`FR-M21-02`).
4. **Resource contention arbitration** — model rate limits, sandbox slots, budget — by priority with starvation prevention (`FR-M21-03`).
5. **Overlapping-file detection at plan time**, serialised or flagged for human sequencing (`FR-M21-05`).
6. **Delivery SLA with slip prediction** from loop-iteration trend (`FR-M21-06`). *The honest implementation of "on-time delivery".*

### Workstream B — Multi-repository

7. **Multi-repo stories** from a workspace manifest, each repo with its own worktree, branch and PR (`FR-M22-01`).
8. **Interface contracts** — OpenAPI / protobuf / GraphQL — generated by the Architect Agent before implementation (`FR-M22-02`, `FR-P4-13`).
9. **Linked PRs merging in dependency order** (`FR-M22-03`). **Consumer-driven contract tests** (`FR-P5-11`).
10. **Monorepo support** — path-prefix scoping and affected-target builds (`FR-M22-04`).

### Workstream C — Closing the delivery loop

11. **Remaining CI integrations** — GitLab, Azure Pipelines, Jenkins (`FR-M23-01`).
12. **CI failure re-enters L2** with the failing job log as feedback (`FR-M23-02`).
13. **PR review comment ingestion** as rework signal, attributed to the reviewer (`FR-M23-03`).
14. **CODEOWNERS-derived reviewer assignment** (`FR-M23-04`) and **merge queue integration** gated on human approval (`FR-M23-05`).
15. **Remaining connectors** — Jira DC, Rally, Azure DevOps Boards, GitHub Issues (`FR-M19-01`), **write-back** with the Done-transition approval prerequisite (`FR-M19-02`, `FR-M19-03`), attachments as untrusted context (`FR-M19-04`), story templates (`FR-M19-05`).

### Workstream D — The Trainer

16. **Harvest from all six signal sources** (`FR-M14-01` as amended) — gate decisions, CI failures, review comments, human edits, post-merge corrections, incidents. **This is why `E9` mattered in P1**: the history exists.
17. **Human-edit ingestion** before merge as "human corrected" signal (`FR-M25-05`).
18. **Candidate proposal** limited to prompts, playbooks, checklists and skill bindings — **never source code** (`FR-M14-02`).
19. **Isolated evaluation** against a frozen regression suite plus replayed recent stories (`FR-M14-03`), including **the golden corpus** (`FR-M14-13`).
20. **Promotion gating** — beats incumbent by margin *and* violates no safety invariant (`FR-M14-04`).
21. **Monotonic safety invariant** — a candidate that improves a metric by weakening a security check, test gate or approval requirement is rejected regardless of score (`FR-M14-05`). **Close `D5`** (may the Trainer edit skill packs, or only policy?).
22. **Human promotion approval; no self-promotion** (`FR-M14-06`). Versioned, ledger-recorded, one-action rollback with 10 retained versions (`FR-M14-07`, `FR-M14-08`).
23. **Adversarial Breaker agent** generating failure cases (`FR-M14-10`).
24. **Cross-team learning opt-in only** (`FR-M14-12`).
25. **Contribution attribution across agents** (`FR-M13-06`).

### Workstream E — Documentation and memory maturity

26. **Documentation Agent** — API docs, README, inline docs, changelog, runbooks (`FR-M29-01`), with documentation as a Review gate criterion for public API changes (`FR-M29-02`).
27. **ADR fitness functions** checked at the Verify gate (`FR-M29-04`).
28. **Organisation → team → repository memory layering** (`FR-M7-09`), **freshness scoring** (`FR-M7-12`), **Markdown import/export with diff** (`FR-M7-10`).
29. **Multi-provider failover** with health checks (`FR-M8-09`) and **local model support** for air-gapped operation (`FR-M8-10`).

### Exit criteria
- [ ] Ten concurrent stories run without checkpoint loss (`NFR-17`, `FR-M27-05`)
- [ ] A multi-repository story completes with linked PRs merging in dependency order
- [ ] A CI failure re-enters L2 and produces a corrected change without manual re-prompting
- [ ] The Trainer demonstrably raises first-pass yield under regression gating, and **rollback is exercised for real, not simulated**
- [ ] A candidate that improves a metric by weakening a control is rejected and displayed as a failure
- [ ] Review comments and human edits appear as Trainer signal with correct attribution
- [ ] SLA slip prediction fires before a real breach on at least one story

### Decisions to close
`D5` Trainer scope

### Risks retired
`R9` Trainer degrading an agent · `R6` non-composing output at scale

---

## P4 — Portability & Compliance

**Goal.** The capability scales across teams and clients, and withstands a formal audit.

**Modules.** M15 · M16 (full) · M17 (full) · M24 (remaining) · M26 (remaining) · M30 (full) · SDLC phases 8–9 · anchoring · crypto-shredding · tenant isolation

### Tasks

1. **Onboarding** — new agent roles by manifest and wizard without redeploying the extension (`FR-M15-01`…`05`), probation with known-good outcomes, admission blocked on failure, entry at `suggest` regardless of score.
2. **Export packaging** — manifest, policy, skill bindings and digests, selected procedural memory, evaluation results, provenance, signed agent card (`FR-M16-01`, `FR-M16-02`).
3. **Export exclusion enforced by pre-scan** — credentials, episodic memory, ledger blobs, untrusted content, detected secrets; blocked on detection (`FR-M16-03`, `SEC-12`).
4. **Import** — signature verification, full introduction diff, probation on arrival, refusal on missing skills or tools (`FR-M16-04`…`06`).
5. **Authorisation wrapper over interop protocols**, since none natively express governance policy (`FR-M16-07`).
6. **Internal registry** for agent packages and skill packs with yield telemetry (`FR-M16-08`).
7. **Human roles and separation of duties** — Engineer, Reviewer, Approver, Governor, Auditor (`FR-M20-02`); SoD enforcement (`FR-M20-03`); N-of-M approval (`FR-M20-04`); delegation with expiry (`FR-M20-05`); **approval hygiene tracking with a rubber-stamping warning** (`FR-M20-06`) — the `R17` control; Governor-only policy and promotion (`FR-M20-07`); read-only Auditor (`FR-M20-08`).
8. **Session security** — recent authentication required for gate actions (`SEC-22`).
9. **Regulatory policy packs** — PCI-DSS, HIPAA, SOC 2, GDPR (`FR-M12-10`) and **compliance evidence export** mapped to ISO/IEC 42001 and AI Act Article 12 (`FR-M12-11`).
10. **Git-backed policy with PR review** (`FR-M12-12`), **emergency fast path** with Governor activation and time-boxing (`FR-M12-13`), **kill switch per agent class** (`FR-M12-14`).
11. **Crypto-shredding** — per-subject blob keys, erasure by key destruction, the erasure itself a ledger entry, chain still verifying (`FR-M10-14`). **The blob store was encrypted in P0 precisely so this is not a migration.** `R16`.
12. **External anchoring** of tree heads (`FR-M10-05`) — **close `D3`**. **Ledger compaction** to cold storage retaining digests (`FR-M10-15`). **Shareable signed HTML slices** (`FR-M10-17`).
13. **Natural-language ledger queries** (`FR-M10-13`).
14. **Tenant isolation** — repositories, memory, ledger and models isolatable per client with no cross-tenant memory or training leakage (`SEC-23`). `R19`.
15. **Agent identity key rotation**, ledger-recorded (`SEC-18`). **Data classification awareness** restricting confidential paths to approved providers (`SEC-21`, `FR-M8-12`).
16. **Release and Operate phases** — release notes, versioning, deployment plan with rollback (`FR-P8-01`); SLO correlation feeding the Trainer (`FR-P9-01`); escaped defect attribution (`FR-P9-02`); **incident linkage as strong negative signal** (`FR-P9-03`); **post-merge human edit tracking** as delayed rework signal (`FR-P9-04`).
17. **AI-BOM** including models, skill packs and policies (`FR-P6-08`) and **in-toto / SLSA provenance attestation** verifiable in CI (`FR-P6-09`).
18. **Full telemetry** — tech-debt registry (`FR-M17-07`), agent-vs-human baseline (`FR-M17-08`), token efficiency ratio (`FR-M17-09`).
19. **Cost governance** — budget increase approval (`FR-M26-02`), chargeback attribution (`FR-M26-03`), model comparison harness (`FR-M26-05`), human-time reporting (`FR-M26-06`).
20. **Remaining editor surfaces** — code actions (`FR-M24-03`), git blame decoration (`FR-M24-04`), `meridian` CLI (`FR-M24-06`).
21. **Operations completion** — backup and restore with integrity verification (`FR-M30-02`), sidecar auto-update with signature verification and rollback (`FR-M30-04`), OpenTelemetry export (`FR-M30-06`), crash reporting with PII scrubbing (`FR-M30-07`), sidecar resource limits enforced (`FR-M3-12`), **versioned local sidecar API** (`FR-M3-13`).
22. **Private marketplace distribution** (`NFR-12`) and **air-gapped verification in CI** (`NFR-20`).
23. **Ecosystem interfaces** — Knowledge Brain memory federation (`ECO-01`), Veritas Trainer client (`ECO-02`), `.cgw` cross-repo graphs (`ECO-04`), ABCD forge targeting (`ECO-05`), epic-to-story ingestion (`ECO-07`).

### Exit criteria
- [ ] An agent is exported from one team and adopted by another, entering probation and passing before live work
- [ ] An audit bundle is accepted in a real compliance review
- [ ] **An erasure request completes and the chain still verifies** — the definitive `R16` test
- [ ] SoD blocks a same-identity approval and names the alternative approver
- [ ] Cross-tenant memory or training leakage is impossible — verified by attempting it
- [ ] `NFR-15` a story pauses 30 days and resumes with context intact
- [ ] `NFR-18` one million ledger entries verify under 30 s with sub-200 ms indexed queries
- [ ] `NFR-20` full functionality on a local provider with no external network
- [ ] `NFR-23` an upgrade loses no checkpoint, ledger entry or memory entry, verified by golden corpus before and after

### Decisions to close
`D3` anchoring · `D7` deployment execution · `D13` tenant isolation ownership

### Risks retired
`R8` ledger over-claiming · `R16` erasure conflict · `R17` rubber-stamping · `R19` cross-tenant leakage · `R13` provider shift

---

## P5 — Differentiation

**Goal.** Capabilities that widen the lead. None blocking.

| Item | Capability |
|---|---|
| `FR-M10-16` | Human annotations and bookmarks on ledger entries |
| `FR-M13-08` | Counterfactual queries via targeted replay from checkpoint |
| `FR-M14-11` | Quality-diversity archive preventing premature convergence |
| `FR-M16-10` | Retirement handover — procedural memory transferred to a named successor |
| `FR-M19-07` | Batch epic ingestion with dependency ordering |
| `FR-M24-05` | Agent-detected issues in the Problems panel with quick-fixes |
| `FR-M30-05` | Scheduled tasks — nightly dependency updates, weekly tech-debt scan |
| `FR-P5-09` | Property-based and fuzz test generation |
| `FR-P8-02` | Deployment execution behind a Governor flag, via the existing pipeline |
| `ECO-06` | Navion MCP browser as a documentation tool |
| `ECO-08` | teamlore import for human-curated memory |

---

## 11. Cross-Cutting Workstreams

Run continuously from P0. Never scheduled as a phase.

| Workstream | Cadence | Notes |
|---|---|---|
| **Golden corpus** | Every phase adds stories; CI runs the full corpus on every runtime, agent or policy change | `FR-M27-03`. Governance closed by `D10` in P0. |
| **Fault injection** | Every module extends the injection set with its own failure modes | `E10`, `FR-M27-04` |
| **Security regression** | Every commit: sandbox escape, injection payloads, egress attempts, permission denials | `SEC-17` |
| **Cross-platform** | Every phase exit on Windows, macOS, Linux, **and under Remote SSH** | `NFR-22`, `FR-M3-11` |
| **Performance budgets** | CI from P0; low-spec profiling at each phase exit | `NFR-01`…`NFR-06`, `NFR-17`…`NFR-19` |
| **Ledger integrity** | Verified on every sidecar start and in CI on every ledger schema change | `FR-M10-09` |
| **Cost telemetry** | Instrumented with the router in P1; reviewed at every phase exit | `E8` |
| **Signal accumulation** | From P1, all six Trainer signal sources recorded even before the Trainer exists | `E9`, `FR-M14-01` |
| **Prompt and policy review** | All prompts, policies and playbooks are plain text under source control and reviewed as code | `NFR-13` |

---

## 12. Definition of Done — Any Module

- [ ] Every requirement in the module implemented, or explicitly deferred with its phase named
- [ ] **Every action the module takes writes a ledger entry before it is considered complete** (`E1`, `FR-M10-08`)
- [ ] Loops the module introduces declare all eight bound fields and fail validation without them (`E5`)
- [ ] Untrusted inputs the module handles are tagged and delimited (`E6`, `SEC-01`, `SEC-02`)
- [ ] Tool invocations are permission-checked; denials are logged (`FR-M9-03`)
- [ ] No credential enters agent context; all logged I/O passes redaction (`SEC-06`, `SEC-07`)
- [ ] **Fault injection cases exist for the module's failure modes and each recovery path is verified** (`E10`)
- [ ] Deterministic replay produces identical behaviour with zero model calls
- [ ] Golden corpus extended where the module changes agent behaviour
- [ ] Cross-platform verified, including under Remote SSH
- [ ] Performance budgets met on a low-spec reference machine
- [ ] Every user-visible error names a cause and a next action (`NFR-10`)
- [ ] State is recoverable from disk; nothing exists only in memory (`NFR-07`)
- [ ] Migration path exists and is reversible (`FR-M30-03`)
- [ ] The GUI contract for the module is published to `viguix-implementation.md`'s message-bus types

---

## 13. Sequencing Dependencies

```
P0 Foundation
 │   M1 · M2(shell) · M3(+remote) · M18 worktrees · M10 substrate · M27 replay · M30(partial)
 │
 └─→ P1 First Value  ◄── the gate the programme is judged on
     │   M4 · M5 · M6(1 skill) · M7 · M8 · M9 · M28 · M11 · M12(v1) · M13 · M17(core)
     │   M19(Jira) · M20(identity) · M23(GitHub) · M24(hover) · M25 · M26 · phases 1–7
     │
     │   ══ §10.2 QUALITY BAR — 20 real stories ══
     │
     ├─→ P2 Quality Gates ──┐
     │     M12(full) · M6(catalogue) · M16(upgrade) · phase 5–7 additions
     │                       │
     └─→ P3 Orchestration ──┴─→ P4 Portability & Compliance ──→ P5
           Phase Orchestrators · M14 · M21 · M22 · M23(rest) · M29
```

**Parallelisable:** P2 and P3 can overlap once P1's bar is cleared, with separate teams — P2 is depth on the existing slice, P3 is breadth. They converge before P4.

**Hard serial:** P0 → P1. Nothing in P1 can start meaningfully without worktrees, the ledger and replay.

**The critical path** is `P0 → P1`. Everything after amplifies a proven core, or amplifies an unproven one.

---

## 14. GUI Interlock

The engineering and interface plans must land together. A screen without its data is a mock; a module without its surface is unusable.

| Engineering | GUI | Joint deliverable |
|---|---|---|
| **P0** | **G0, G1** | Platform + design system + shell. The Command Center is wired to real sidecar state the day P0 exits. |
| **P1** | **G2, G3, G4** | The Weave and Ledger render real ledger data; Gate Room, Steer and Decision Stream drive real loops; the Floor shows real agent state. |
| **P2** | **G5, G6** | CodeMap consumes the real code graph; UML and C4 generate from the real repository. |
| **P3** | **G6.5** | Portfolio, Connectors, Delivery Pipeline and Repositories become meaningful only with M21, M19, M23 and M22. |
| **P4** | **G7, G8** | Config, Memory Studio, Routing Observatory, Calibration, Exchange and Runtime surface the P4 modules. First-run and editor surfaces close the product. |

**The interlock rule:** a GUI phase does not start until its engineering counterpart's data contracts are published and stable. `viguix-implementation.md`'s own rule — *no screen ships against mock data* — depends on this plan holding its dates.

---

## 15. Slip Plan

Cut in this order. Each cut leaves a working, safe system.

| Order | Cut | Cost |
|---|---|---|
| 1 | All P5 items | None. Differentiation only. |
| 2 | Remaining connectors and CI integrations beyond Jira and GitHub Actions | Narrows the pilot to one toolchain. Acceptable. |
| 3 | M22 multi-repository | The vision's polyglot promise slips to a later release. §1.3 already scopes v1 to single-repository, so this is honest rather than a retreat. |
| 4 | M29 Documentation Agent | Loses the "documenting standards" half of the original brief. Painful but survivable. |
| 5 | M14 Trainer | Loses self-improvement. **Keep the signal accumulation (`E9`) regardless** — history cannot be back-filled, and the Trainer becomes trivially addable later. |
| 6 | M21 portfolio and multi-story | Confines the product to one story at a time. Significant, and only under real pressure. |

**Never cut:** worktree isolation (M18) · the ledger and its verification (M10, M11) · human approval before merge (`FR-M12-05`, `FR-P7-05`) · authenticated identity (`FR-M20-01`) · the security posture (`SEC-01`…`SEC-15`) · deterministic replay and the golden corpus (M27) · confidence-with-calibration (`FR-M13-03`) · the evidence-versus-narrative distinction (`FR-M13-02`, `FR-M13-04`) · steer and clarifying questions (M25) · full-surface regression (`FR-P5-06`).

**Every one of these is a control on a documented failure mode.** Cutting any of them does not make the product smaller; it makes it unsafe.

---

## 16. Risk Retirement Schedule

| Risk | Retired or controlled in | Primary control |
|---|---|---|
| R1 prompt injection | P1 | `SEC-01`…`05`, `SEC-15`, trifecta decomposition |
| R2 orphaned sidecars | **P0** | `FR-M3-02` + `FR-M3-03` dual contract, `AC-08` |
| R3 cost blowup | P1 | Bounded loops, budgets, tiering, caching, `FR-M26-01` |
| R4 over-trust | P1, instrumented; P2 fully | `FR-M17-04`, `FR-M17-03` divergence warning |
| R5 breaking working code | P1 | `FR-P5-06` full-surface regression, distinct test author |
| R6 non-composing output | P1 (single-threaded writes); P3 (contracts) | `FR-M4-09`, `FR-M22-02` |
| R7 memory poisoning | **P1** | `FR-M7-07` untrusted tagging, `SEC-15` classifier |
| R8 ledger over-claimed | P4 | `FR-M10-06` language, signing and anchoring |
| R9 Trainer degradation | P3 | Frozen suite, monotonic invariant, golden corpus, rollback |
| R10 skill supply chain | P1 (review); P2 (revocation) | `FR-M6-06`, `SEC-19` |
| R11 distribution friction | P0 | Platform targets, resolution chain, doctor |
| R12 reviewer overload | P2 | `FR-P7-06` measurement, blast-radius prioritisation |
| R13 provider shift | P4 | `FR-M8-08`, `FR-M8-09`, `FR-M8-10` |
| R14 destroyed uncommitted work | **P0** | M18, `AC-13`, `AC-14` |
| R15 untestable runtime | **P0** | M27, `AC-15`, `AC-16` |
| R16 erasure conflict | P4 *(enabled in P0)* | `FR-M10-14` crypto-shredding on P0's encrypted blob store |
| R17 rubber-stamping | P4 | `FR-M20-06`, N-of-M, SoD |
| R18 setup friction | P0 (doctor); GUI G8 (first-run) | `FR-M30-01`, `NFR-14` |
| R19 cross-tenant leakage | P4 | `SEC-23`, `FR-M14-12` |
| R20 duplicate implementation | P1 | `FR-M28-04` reuse-first with citation |

---

## 17. Decision Schedule

| # | Decision | Must close by |
|---|---|---|
| `D4` | Python distribution — bundled runtime vs. workspace interpreter | **P0 week 1** |
| `D10` | Golden corpus governance — who curates, admission, cassette refresh | **P0** |
| `D1` | Loop runtime — adopt vs. build | **P1 start** |
| `D2` | Model routing and tiering policy | **P1 start** |
| `D9` | Identity source of record, and whether multiple at once | **P1** |
| `D11` | Chat participant in v1 — reach vs. injection surface | **P1** |
| `D12` | Workspace currency for a globally billing organisation | **P1** |
| **`D14`** | **New — is the Security phase P1 or P2, and should `AC-02` name it?** See §0.3. | **P1 start** |
| `D6` | Autonomy tier promotion thresholds per task class | **P2** |
| `D8` | Phase set fixed at nine or configurable | **P1** *(the GUI plan already assumes configurable)* |
| `D5` | Trainer scope — skill pack edits or policy only | **P3** |
| `D3` | Ledger anchoring — local, internal service, or external TSA | **P4** |
| `D7` | Release and Operate — execute deployments or plan only | **P4** |
| `D13` | Tenant isolation owned by Meridian or inherited from the platform | **P4** |

---

## 18. Traceability Appendix

Every requirement group mapped to a phase. **Bold** marks an item whose §12 placement was later than its release target and which was promoted here (§0.2).

### Modules

| Phase | Modules and scope |
|---|---|
| **P0** | M1 *(all)* · M2 *(shell)* · M3 *(all except FR-M3-12/13)* · M10 *(01–12)* · M18 *(all)* · M27 *(01–04)* · M30 *(01, 03, 08)* |
| **P1** | M4 *(all)* · M5 *(all)* · M6 *(01–07, 09; one pack)* · M7 *(01–08, 11, 13)* · M8 *(01–08, 11, 13, 14)* · M9 *(all)* · M11 *(all)* · **M12 *(01, 05, 06, 07, 08, 09)*** · M13 *(01–05, 07, 09, 10)* · M17 *(01, 04, 05, 06)* · M19 *(01 Jira, 06)* · M20 *(01)* · M23 *(01 GitHub, 06)* · **M24 *(01, 02)*** · M25 *(01–04, 06)* · M26 *(01, 04)* · M28 *(all)* |
| **P2** | M12 *(02, 03, 04)* · M6 *(08 full catalogue)* · M16 *(09)* · M17 *(02, 03)* |
| **P3** | M14 *(all)* · M19 *(02–06)* · M21 *(all)* · M22 *(all)* · M23 *(02–05)* · M29 *(all)* · M7 *(09, 10, 12)* · M8 *(09, 10)* · M13 *(06)* · M25 *(05, 07, 08)* |
| **P4** | M15 *(all)* · M16 *(01–08)* · M17 *(07, 08, 09)* · M20 *(02–08)* · M24 *(03, 04, 06)* · M26 *(02, 03, 05, 06)* · M30 *(02, 04, 06, 07)* · M3 *(12, 13)* · M10 *(13, 14, 15, 17)* · M12 *(10–14)* · M8 *(12)* · M27 *(05)* |
| **P5** | M10 *(16)* · M13 *(08)* · M14 *(11)* · M16 *(10)* · M19 *(07)* · M24 *(05)* · M30 *(05)* |

### SDLC phase requirements

| Phase | Requirements |
|---|---|
| **P1** | FR-P1-01…07 · FR-P2-01…06 · FR-P3-01…05 · FR-P4-01…10 · FR-P5-01…06, 08 · **FR-P6-01…05** · FR-P7-01…06, 08 |
| **P2** | FR-P4-11, 12 · FR-P5-07, 10, 12, 13 · FR-P6-06, 07 · FR-P7-07 |
| **P3** | FR-P4-13 · FR-P5-11 |
| **P4** | FR-P6-08, 09 · FR-P8-01 · FR-P9-01…04 |
| **P5** | FR-P5-09 · FR-P8-02 |

### Non-functional

| Phase | NFRs |
|---|---|
| **P0** | NFR-01, 05, 07, 08, 09, 11, 22 |
| **P1** | NFR-02, 03, 04, 06, 10, 13, 16, 19, 23 |
| **P3** | NFR-17 |
| **P4** | NFR-12, 14 *(with GUI G8)*, 15, 18, 20, 21 |

### Security

| Phase | SEC |
|---|---|
| **P0** | SEC-06, 07, 11, 13 *(mechanism)* |
| **P1** | SEC-01…05, 08, 09, 10, 12 *(scan)*, 14, 15, 17 |
| **P2** | SEC-16, 19, 20 |
| **P4** | SEC-18, 21, 22, 23 |

### Acceptance criteria

| Phase | AC |
|---|---|
| **P0** | AC-07, AC-08, AC-13, AC-14, AC-19, AC-21 |
| **P1** | AC-01…06, AC-09…12, AC-15…18, AC-20, AC-22, §10.2 quality bar |

### Ecosystem

| Phase | ECO |
|---|---|
| **P1** | ECO-03 CodeMap JSON |
| **P4** | ECO-01, 02, 04, 05, 07 |
| **P5** | ECO-06, 08 |

---

*End of plan. This document governs the build of `Requirements_Final.md` v2.0 and interlocks with `viguix-implementation.md` v2.0 at §14.*
