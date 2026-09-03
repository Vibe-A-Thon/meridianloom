# Meridian Loom — Gaps Implementation Plan

| | |
|---|---|
| **Document** | gaps_implementation.md |
| **Version** | 1.0 |
| **Author** | Ravaleedhar Reddy |
| **Governs** | The build order for `gaps-requirements.md` v1.0 |
| **Supersedes** | `Requirements-implementation.md` v2.0 §4 phase map and §15 sequencing. Its phase *contents* survive; the order and the entry point do not. |
| **Companions** | `gaps-requirements.md` · `gaps_guix.md` · `HONEST_ASSESSMENT.md` · `Requirements_Final.md` v2.1 · `VIGUIX_Final.md` v2.1 |
| **Scale** | 1 gate + 4 build phases + 1 evidence gate · 6 new modules · 47 new requirements · ~120 reused from the existing 533 |

---

## Table of Contents

0. [About This Plan](#0-about-this-plan)
1. [How to Use This Document](#1-how-to-use-this-document)
2. [Build Principles](#2-build-principles)
3. [Stack Decisions](#3-stack-decisions)
4. [Phase Map](#4-phase-map)
5. [F−1 — Gate Zero: Legal Clearance](#f1--gate-zero-legal-clearance)
6. [F0 — Flight Recorder](#f0--flight-recorder)
7. [F1 — Governor](#f1--governor)
8. [F2 — Evidence Gate](#f2--evidence-gate)
9. [F3 — Orchestra](#f3--orchestra)
10. [F4+ — Learning, Scale, Compliance](#f4--learning-scale-compliance)
11. [Cross-Cutting Workstreams](#11-cross-cutting-workstreams)
12. [Definition of Done](#12-definition-of-done)
13. [Sequencing Dependencies](#13-sequencing-dependencies)
14. [GUI Interlock](#14-gui-interlock)
15. [Kill Criteria](#15-kill-criteria)
16. [Slip Plan](#16-slip-plan)
17. [Risk Retirement Schedule](#17-risk-retirement-schedule)
18. [Decision Schedule](#18-decision-schedule)
19. [What Happens to the Existing 533 Requirements](#19-what-happens-to-the-existing-533-requirements)
20. [Traceability Appendix](#20-traceability-appendix)

---

## 0. About This Plan

### 0.1 What changed and why

`Requirements-implementation.md` v2.0 sequenced the build as `S0 → the entire GUI → C1 control layer → C2 first value`. The honest assessment found that order to be the most expensive possible way to discover the thesis is wrong: no real story runs until roughly 70% of the effort is spent.

`gaps-requirements.md` repositioned the product — from an agent orchestra that competes with Cursor and Copilot, to the **governance, provenance and trust layer beneath every agent a team already runs**. This plan is the build order for that repositioning.

The change in one line: **the first thing built is the thing that is valuable on its own, works with somebody else's agent, and requires no model credential.**

### 0.2 The three shapes of a phase here

- **F−1 and F2 are gates, not build phases.** F−1 is a legal clearance. F2 is an evidence gate with explicit stop conditions. Neither produces code, and both can end the programme.
- **F0 and F1 are build phases** with hard exit criteria.
- **F3 and F4+ are the existing plan**, re-based, and reached only if F2 passes.

### 0.3 What this plan does not do

It does not discard the 533 existing requirements. §19 states exactly what is reused in F0/F1, what moves to F3, and what is deferred until the evidence justifies it. Every requirement ID survives.

---

## 1. How to Use This Document

**F−1 must close before any code is written.** Not "before release" — before the first commit. It is the highest-probability failure mode in the entire programme and it costs a lawyer's afternoon to resolve.

**F2 is a real gate, not a milestone.** It has stop conditions (§15). If the governance layer does not demonstrably improve rejection rate or catch defects the agents missed, F3 does not start and the Flight Recorder ships as the product. That outcome is a success, and the plan is written so that it is.

**Every exit criterion is a passing test or a measured number**, not a judgement. Where a criterion is a measurement, the measurement method is named.

---

## 2. Build Principles

`E1`–`E14` from `Requirements-implementation.md` v2.0 remain in force where they apply. These are added, each derived from a principle in `gaps-requirements.md` §1.

| # | Principle | Consequence | From |
|---|---|---|---|
| **G1** | **Nothing is built that requires a Meridian agent to be useful.** | Every F0 and F1 capability must demonstrate value with Claude Code, Copilot or Cursor doing the work. A feature that only lights up in the Orchestra tier belongs in F3. | P20 |
| **G2** | **Where a standard won, implement the standard.** | ACP for editor↔agent, MCP for agent↔tool, git trailers for authorship, OTel for telemetry, SSDF/42001 for evidence. Meridian writes no bespoke equivalent of any of these. | P21 |
| **G3** | **Observation degrades, never goes silent.** | Every observer has a documented fallback chain ending in git-and-filesystem inference. A vendor changing its telemetry format produces a visible confidence downgrade within one session, never a gap in the cloth. | `NFR-32` |
| **G4** | **Provenance must survive Meridian's own uninstallation.** | Git trailers and the open ledger spec are not features; they are the proof that the product is not a lock-in. Test them by uninstalling. | `FR-M36-03`, `AC-33` |
| **G5** | **A tier that is disabled must leave no scar.** | Disabling Orchestra leaves Governor and Flight Recorder fully functional, with no broken screens, no empty orchestra, no orphaned data. Tested every phase. | `FR-M36-05` |
| **G6** | **Measure the thing the market says it does not trust.** | Rejection rate, split greenfield/brownfield, per agent, from F0. Not as a KPI panel — as the reason the product exists. | `BT-5` |
| **G7** | **Time-box F0 and cut scope, never quality.** | If F0 exceeds its band (§6.7), cut observers, cut screens, cut the verifier — never cut the ledger's integrity, the trailer, or the confidence labelling. | `S-2` |

---

## 3. Stack Decisions

Settle in F0. Rows are new to this plan; the rest inherit from `Requirements-implementation.md` v2.0 §3.

| Concern | Decision | Rationale |
|---|---|---|
| **ACP client** | The official Rust/TypeScript ACP schema crate for types; a TypeScript host implementation in the extension. Python SDK (`agent-client-protocol`, 3.10+) in the sidecar only if an adapter needs it. | `FR-M34-01`, `G2` |
| **Observation transport, per vendor** | Claude Code → OpenTelemetry export where configured, else `Co-Authored-By` trailers, else inference. Copilot → SCM/PR API (direct). Cursor / Codex / Devin → git + filesystem inference until a first-party surface exists. | `FR-M35-02`, `D20` |
| **Trailer injection** | `commit-msg` git hook installed into the workspace (opt-in, visible, removable), appending `Meridian-Ledger: <range>`. Fallback: `git notes` for repositories where hooks are unavailable. **`D23` decides which is default.** | `FR-M36-03` |
| **Agent-vs-human change attribution** | VS Code `onDidChangeTextDocument` heuristics — burst size, multi-line insertion rate, absence of keystroke cadence — combined with active-session detection. **Always labelled `inferred`.** Never presented as fact. | `FR-M35-02`, `G3` |
| **Ledger** | Unchanged from v2.0: SQLite, append-only triggers, SHA-256 chain, Merkle tree, signed tree heads, encrypted content-addressed blobs from day one. | `FR-M10-*` |
| **Open verifier** | A single-file Python script and a Rust binary, both Apache 2.0, that validate a Meridian audit bundle with no Meridian installed. Published in the same repository. | `FR-M36-06`, `NFR-31`, `G4` |
| **Tiering** | A capability registry in the extension host; the sidecar refuses RPCs for a disabled tier; the webview's command registry filters by tier. No feature flags scattered in code. | `FR-M36-05`, `X-28` |
| **Deterministic attribution** | tree-sitter for line→symbol mapping, libgit2/`git` for blame and diff, LSP where available. No model calls anywhere in F0. | `FR-M36-07`, `FR-M33-02` |
| **Trust metrics store** | Derived from the ledger on demand, cached. No separate metrics database (`FR-M17-05`). | `FR-M37-*` |
| **Distribution** | VS Code Marketplace for the Flight Recorder tier, free. Governor and Orchestra gated by licence key. **`D19` decides open-core.** | `D19` |

---

## 4. Phase Map

| Phase | Kind | Name | Modules | Exit |
|---|---|---|---|---|
| **F−1** | Gate | Legal clearance | — | `D22` closed in writing |
| **F0** | Build | **Flight Recorder** | M36, M35 *(2 observers)*, M10, M11, M33 *(attribution subset)*, M1/M3 *(minimum)*, M20-01, M37 *(rejection subset)* | `AC-30`, `AC-33`, `AC-34` *(partial)*, `NFR-28` |
| **F1** | Build | **Governor** | M34, M12 *(v1 subset)*, M20 *(roles)*, M25 *(steer, questions)*, M37 *(full)*, M39, M35 *(remaining observers)*, M18 *(for hosted agents)* | `AC-31`, `AC-32`, `AC-34`, `AC-36`, `AC-37` |
| **F2** | Gate | **Evidence** | — | 20 real stories; stop conditions in §15 |
| **F3** | Build | **Orchestra** | M4, M31 *(re-based on ACP)*, M5, M6, M7, M8, M9, M28, M33 *(full)*, M38, M13, M26, the roster, the remaining GUI | `AC-01`…`AC-29`, `AC-35` |
| **F4+** | Build | Learning, scale, compliance | As `Requirements-implementation.md` C3–C6 | Unchanged |

---

## F−1 — Gate Zero: Legal Clearance

**This is not optional and it is not last.**

`HONEST_ASSESSMENT.md` BT-6 identifies the highest-probability failure mode in the programme: an employee of a top-5 IT services firm building an agentic SDLC product squarely inside the employer's actual and anticipated line of business, where standard Indian invention-assignment language commonly covers work "relating to the Company's actual or anticipated business" regardless of when or where it was done.

### Tasks

1. Read the invention-assignment, confidentiality and moonlighting clauses in your employment agreement, in full, including anything incorporated by reference from a handbook.
2. Take thirty minutes with an Indian employment lawyer. Bring the clauses and a one-paragraph description of the product.
3. Decide the path and record it in `DECISIONS.md`:
   - **(a) Sanctioned internal initiative** — take it to the firm. Highest career upside, no IP exposure, you do not own it.
   - **(b) Independent build** — clean room, personal equipment, personal accounts, personal network, no company confidential information, documented from day one.
   - **(c) Open-source contribution** — Apache 2.0 from the first commit, which changes the ownership question materially and aligns with `D19`.
4. If path (b): create the clean-room evidence trail *before* the first commit — a personal device, a personal GitHub account, a written prior-inventions declaration if your agreement provides for one, and a note of the date the work began.

### Exit criterion
- [ ] `D22` closed in writing, with the chosen path and its reasoning recorded

**No task in F0 begins until this box is ticked.**

---

## F0 — Flight Recorder

**Goal.** A team installs Meridian, runs the agent they already use, and within fifteen minutes can answer *which agent wrote this line, what was it told, how confident was it, who approved it* — and that answer survives Meridian being uninstalled.

**Modules.** M36 · M35 *(Claude Code + Copilot observers)* · M10 *(substrate)* · M11 · M33 *(attribution subset)* · M1 and M3 *(minimum)* · M20-01 · M37 *(rejection subset)*

**Explicitly not in F0.** No Meridian agents. No loop runtime. No model router. No model credentials. No gates beyond the record. No worktrees — external agents write where the user runs them, and Meridian records rather than isolates. **Say this honestly in the product**: Flight Recorder observes; it does not protect the working tree. Protection arrives with hosted agents in F1.

### Workstream A — Shell and sidecar, minimum viable

1. **Extension scaffold** — granular activation (`FR-M1-01`), one Activity Bar container, three commands: `meridian.openRecorder`, `meridian.exportBundle`, `meridian.doctor` (`FR-M1-03` subset).
2. **Sidecar spawn over framed JSON-RPC** (`FR-M3-01`) with the **dual teardown contract** — supervisor kills on deactivate, sidecar self-terminates if orphaned (`FR-M3-02`, `FR-M3-03`). Both halves, in F0, because orphaned processes are the documented failure mode.
3. **Interpreter resolution chain** (`FR-M3-05`) and remote support (`FR-M3-11`). Remote is F0 because enterprise development is remote.
4. **SecretStorage adapter** with refuse-to-start on unavailability (`FR-M1-06`, `FR-M1-07`) — used in F0 only for the ledger signing key, not for model credentials.
5. **Versioned RPC contract** with generated shared types (`FR-M3-08`).
6. **`meridian doctor`** (`FR-M30-01`) — interpreter, sidecar, keychain, ledger integrity, git hooks, observer health.
7. **Tiering scaffold** (`FR-M36-05`): capability registry, sidecar tier enforcement, webview command-registry filtering. Built now so `G5` is testable from the first phase.

### Workstream B — Ledger core

8. **Append-only SQLite** with delete/update triggers, the §7.2 schema plus the v2.1 fields **and** the new `vendor`, `observation_confidence`, `external_session_id` columns (`FR-M10-01`).
9. **Hash chain, Merkle tree, inclusion and consistency proofs** (`FR-M10-02`, `FR-M10-03`); **signed tree heads** with the key in the OS keychain (`FR-M10-04`).
10. **Encrypted content-addressed blob store** with per-subject keys **from day one** — so crypto-shredding in F4 is not a migration (`FR-M10-07`).
11. **Chain verification** under 5 s for 100k entries, reporting the first divergent sequence (`FR-M10-09`); **synchronous write semantics** (`FR-M10-08`).
12. **Ledger query API** (`FR-M10-12`) and the **Chain Viewer backend** (M11, all five requirements) — the Selvage strip and entry detail need real proofs.

### Workstream C — Deterministic attribution *(no model calls)*

13. **Diff and blame engine** — git-native, mapping every changed line to a commit, an author identity and a time.
14. **tree-sitter line→symbol mapping** so provenance answers name a function, not only a line number (`FR-M33-02` subset).
15. **Human vs. agent change heuristics** — burst size, multi-line insertion rate, keystroke-cadence absence, cross-referenced with active-session detection. **Every result labelled `inferred`** (`G3`).
16. **Zero-model-call assertion** — a CI test that fails if any F0 code path imports or calls a model client (`FR-M36-07`).

### Workstream D — Observers

17. **Observer framework** (`FR-M35-08`): a versioned observer interface, per-vendor implementations, health reporting, and the documented fallback chain with confidence downgrade (`G3`, `NFR-32`).
18. **Claude Code observer** — OpenTelemetry export where the team has it configured; `Co-Authored-By` trailer parsing otherwise; filesystem inference as the floor. **`direct` is not available for local Claude Code without OTel; say so in the UI rather than overclaiming.**
19. **Copilot observer** — SCM and PR API. `direct` confidence for PR-level attribution; `inferred` for in-editor changes.
20. **Session detection** (`X-29`) — an external agent session is visible in the Crown within 2 seconds.
21. **Observation overhead budget** — no more than 5% latency added to a hosted session, never blocking an observed one (`NFR-29`).
22. **One-way isolation** — observed agents gain no access to Meridian credentials, policy or signing key (`SEC-27`).

### Workstream E — Portable provenance

23. **`commit-msg` git hook** appending `Meridian-Ledger: <seq range>`, opt-in, visible in the UI, removable in one action. **Close `D23`** (hook vs. `git notes` as default).
24. **Agent identity trailers** — preserve and read every vendor's `Co-Authored-By`; add Meridian's own only for Meridian-authored commits.
25. **Signed audit bundle** (`FR-M36-04`) for any range, agent or story, mapped to **NIST SSDF AI provenance** and ISO/IEC 42001 record-keeping (`M12` amendment).
26. **Open verifier** — a Python script and a Rust binary, Apache 2.0, validating a bundle with no Meridian installed (`FR-M36-06`, `NFR-31`, `SEC-29`).
27. **Open ledger specification** published alongside the verifier.

### Workstream F — Rejection measurement, minimum

28. **Rejection capture** — a change is rejected when it is reverted, force-amended away, or replaced within a configurable window; captured deterministically from git without any gate existing yet (`FR-M37-01` subset).
29. **Greenfield / brownfield classification** per story or session — ratio of new files to modified files, and repository age of touched code (`FR-M37-06`). **In F0 because it is the split that makes every later number meaningful.**
30. **Rejection rate per agent, per repository, split greenfield/brownfield**, computed from the ledger (`FR-M17-05`).

### Workstream G — The three screens *(interlock: GUI phase GF0)*

31. **10.45 Flight Recorder** — the Weave (agent-agnostic), This Session, Any Line, Export, Selvage.
32. **10.46 External Agents** — session list, per-session detail, observer health.
33. **10.7 Ledger** — Selvage strip, filterable entry stream, entry detail, proof inspection, bundle export.
34. **10.40 First-Run**, rewritten: connect repository → run your existing agent → see the Weave → export a bundle. Four steps, no credential, no Meridian agent.
35. **X-27 `VendorTag` and confidence glyph** as a component-level invariant; **X-28 tier-aware disclosure**; **X-29 external-session awareness**; **X-30 provenance hover everywhere**.
36. **Design tokens, six themes, density modes** — the `VIGUIX_Final.md` §4–§6 foundation, but only the primitives these three screens need.

### F0 exit criteria

- [ ] **`AC-30`** On a fresh machine with no model credential, Meridian is installed, pointed at a repository, the team's existing agent is run, and within 15 minutes the Weave shows that session's passes with vendor tags and any changed line answers the provenance question
- [ ] **`AC-33`** Meridian is uninstalled; `git log` still shows the trailers; the exported bundle verifies with the open verifier on a clean machine
- [ ] **`AC-34` (partial)** Rejection rate per agent, split greenfield/brownfield, reconciles to the ledger over ≥10 sessions
- [ ] **`NFR-28`** First value under 15 minutes, measured with five people who have not seen the product
- [ ] **`NFR-29`** Observation adds ≤5% latency to a session; never blocks
- [ ] **`FR-M36-07`** Zero model calls — asserted by a CI test that fails on any model-client import in F0 paths
- [ ] Chain verification passes; a deliberately corrupted entry is detected and its sequence named
- [ ] An observer whose telemetry format is deliberately broken degrades to `inferred` with a visible warning within one session, never to silence
- [ ] No orphaned sidecar after window close, reload or disable, on all three platforms, and under Remote SSH
- [ ] Disabling the (not yet built) Governor and Orchestra tiers leaves Flight Recorder fully functional — `G5` tested even with nothing above it

### F0 realistic duration

**6–10 weeks** for one experienced engineer with a competent coding agent. The assessment's "weeks" is achievable for the ledger and the first observer; the honest additions are the open verifier, the trailer mechanism, and the fifteen-minute first-value target, which is a product-design problem more than an engineering one.

**What drives the band:** the Claude Code OTel observer and the human-vs-agent heuristics are the two tasks most likely to double. If F0 crosses 10 weeks, cut the Copilot observer to F1 (`G7`) rather than extending.

### Decisions to close
`D20` *(which observers first)* · `D23` *(trailer mechanism)*

### Risks retired or controlled
`R27` *(observer blindness — the fallback chain and degradation are proven)* · `R30` *(vendor dependence — observation uses only open surfaces)* · `R2` · `R15` *(from the base plan)*

---

## F1 — Governor

**Goal.** The recorded work becomes governed work. External agents' PRs pass through Meridian's gates. Meridian hosts ACP agents in VS Code — as well as Devin Desktop hosts them — and adds what Devin cannot: provenance, gates and trust.

**Modules.** M34 · M12 *(v1 subset)* · M20 *(roles)* · M25 *(steer, questions)* · M37 *(full)* · M39 · M35 *(remaining observers)* · M18 *(for hosted agents only)*

### Workstream A — ACP host

1. **ACP client in the extension host** (`FR-M34-01`) — subprocess launch, sessions, streaming updates, permission-gated tool execution, client-provided filesystem and terminal access.
2. **`AgentAdapter` re-based on ACP** (`FR-M34-02`): an adapter is an ACP agent plus a Meridian governance manifest. **Delete the bespoke protocol.** Retain M31's discovery, validation, hot plug, probation, trainable surfaces, portability and governance (`FR-M31-02`…`04`, `06`…`10`, `12`…`15`).
3. **ACP Registry integration** (`FR-M34-03`) — any registered agent one click from probation in the Adapter Bay.
4. **Policy-checked permission requests** (`FR-M34-04`, `SEC-28`) — the agent's ACP permission request is checked against Meridian policy and the agent's tier *before* the human sees the prompt; re-requesting cannot escalate.
5. **Worktree isolation for hosted agents** (M18) — now possible, because Meridian launches the process. Conflict detection, story abort, agent git identity (`FR-M18-01`…`05`, `07`, `08`).
6. **Meridian agents exposed as MCP servers** (`FR-M34-06`) so VS Code's native agent mode still gets the ledger and gates.
7. **Upstream contribution** (`FR-M34-05`) — publish the VS Code ACP host, track the open VS Code issue, design to layer on native support if it lands (`R26`).
8. **ACP conformance in CI** (`NFR-30`).

### Workstream B — Gates over other people's work

9. **Policy engine** (`FR-M12-01`, `FR-M12-08`) with DoR/DoD as machine-checkable criteria (`FR-M12-09`).
10. **No merge to a protected branch without recorded human approval** (`FR-M12-05`) and **approver identity in the ledger** (`FR-M12-07`). Applied to external-agent PRs, not only Meridian's.
11. **Governance can halt** (`FR-M12-06`) — for hosted agents, terminate the session; for observed agents, block the merge and warn.
12. **External PR gating** (`FR-M35-04`) and **PR ingest as a story** (`FR-M35-05`) — a Copilot-from-Jira PR becomes a Meridian story with attributed hunks, routed to the gates.
13. **Multi-agent conflict detection** (`FR-M35-07`) — hunks from different agents on the same story, surfaced as a distinct rework class.
14. **Rework reason taxonomy** (`E-GR-03`) — every rejection carries a reason, which is what makes `FR-M37-02` possible.

### Workstream C — Human identity and roles

15. **Authenticated identity** (`FR-M20-01`) — **close `D9`**.
16. **Roles, SoD, N-of-M, delegation, approval hygiene** (`FR-M20-02`…`08`). Approval hygiene in F1 rather than later, because gating other people's agents at volume is exactly where rubber-stamping appears.

### Workstream D — Steer and clarify, applied to hosted agents

17. **Steer** into a running ACP session (`FR-M25-01`); **clarifying questions** with resume (`FR-M25-02`); **uncertainty escalation** where the agent exposes confidence (`FR-M25-03`); **partial acceptance** (`FR-M25-04`); **dry-run** (`FR-M25-06`).
18. Where an observed (not hosted) agent cannot be steered, the UI says so plainly rather than offering a control that does nothing.

### Workstream E — Trust analytics

19. **Rejection rate, full** (`FR-M37-01`) — per agent, action class, phase, story, repository.
20. **Rejection reason distribution** per agent (`FR-M37-02`).
21. **Trust score with decomposition** (`FR-M37-03`) — yield, rejection, calibration, post-merge revert, incident linkage.
22. **Agent-vs-agent comparison** including external agents (`FR-M37-04`, `FR-M25-07` extended).
23. **The J-curve** (`FR-M37-05`) — throughput and stability before and after adoption, with the dip labelled as a phase.
24. **Tokenmaxxing detection** (`FR-M37-07`).
25. **DORA-compatible metrics export and OTel** (`FR-M37-08`).

### Workstream F — Cross-vendor spend

26. **Spend across every observed agent** by vendor, model, agent, story, team, cost centre (`FR-M39-01`).
27. **Ceilings on hosted agents** (pause at checkpoint) and **warnings on observed ones** (`FR-M39-02`).
28. **Monthly forecast with budget alert** (`FR-M39-03`).
29. **Predictable-by-design pricing** (`FR-M39-04`) — Flight Recorder makes no model calls and has no usage cost; higher tiers report their own spend in the same ledger.

### Workstream G — Remaining observers

30. **Cursor, Codex, Devin observers** at whatever confidence their surfaces permit (`D20`). Where only `inferred` is achievable, ship it labelled rather than not shipping it.

### Workstream H — Screens *(interlock: GUI phase GF1)*

31. **10.1 Command Center** (Governor's front door) · **10.6 Gate Room** · **10.27 Decision Stream** · **10.28 Steer & Clarify** · **10.32 Roles** · **10.47 Trust Observatory** · **10.49 Cross-Vendor Spend** · **10.43 Adapter Bay as ACP host** · **10.16 Inspector** (external-aware) · **10.50 Unlock**.
32. **X-31 competitor-surface parity check** — task-timing against Devin Desktop's Agent Command Center on start / watch / steer / stop, with five engineers.

### F1 exit criteria

- [ ] **`AC-31`** An agent from the ACP Registry installs via the Adapter Bay, enters probation, completes a packet under Meridian governance, with every permission request policy-checked before the human sees it
- [ ] **`AC-32`** A PR opened by Copilot's coding agent from a Jira ticket is ingested, routed through Security and Review gates, and merged only after a recorded human approval — Copilot's pass, the gates and the approver in one ledger range
- [ ] **`AC-34`** After 20 stories across two agents, rejection rate and reason distribution per agent, split greenfield/brownfield, reconcile to the ledger
- [ ] **`AC-36`** With Orchestra disabled, Flight Recorder and Governor function fully; no screen errors, no empty orchestra
- [ ] **`AC-37`** A story worked by one hosted and one observed agent shows both agents' spend by vendor and model, reconciling to the ledger
- [ ] **`NFR-30`** ACP conformance suite green in CI
- [ ] **`X-31`** Meridian's Adapter Bay matches Devin Desktop's Agent Command Center on the five core operations, measured
- [ ] No path exists to merge an external agent's PR without a recorded approver identity

### Decisions to close
`D9` *(identity source)* · `D19` *(open core)* · `D21` *(whether Orchestra ships at all)*

### Risks retired or controlled
`R26` *(native ACP — upstream contribution and layering strategy in place)* · `R28` *(incumbent provenance — cross-vendor view is the differentiator and now exists)* · `R17` *(rubber-stamping)*

---

## F2 — Evidence Gate

**Not a build phase. A decision phase with stop conditions.**

Twenty real stories, from the team's own backlog, through F0 + F1, using the team's own agents. No Meridian agents. Measured, not judged.

### What is measured

| Measure | Source | Why it decides |
|---|---|---|
| **Rejection rate before vs. after gating** | `FR-M37-01`, split greenfield/brownfield | If gates do not reduce rejection, the governance layer is ceremony |
| **Defects caught by gates that the agent's own process missed** | Gate outcomes vs. the counterfactual PR | The core value claim, stated as a number |
| **Change failure rate for gated agent merges vs. the team's baseline** | `FR-M17-02` | The DORA stability question, on this team's data |
| **Approval hygiene** | `FR-M20-06` | If approvers are rubber-stamping, the gates are theatre |
| **Time cost per gated PR** | Ledger timings | The tax the layer imposes |
| **Provenance queries actually run** | Ledger query telemetry | Whether anyone uses the thing the product is for |
| **First-value retention** | Are the five F0 testers still using it at week 8? | The honest adoption signal |

### Go / stop / pivot

- **GO to F3** — gates measurably reduce rejection rate *or* catch defects the agents missed, change failure rate is no worse than baseline, and provenance queries are actually being run. Then build the Orchestra.
- **STOP and ship** — the recorder and gates are used and valued, but the evidence does not justify building Meridian's own agents. **Ship Flight Recorder + Governor as the product.** This is a success, not a failure (`R29`).
- **PIVOT** — provenance queries are not run and gates are ceremony, but the trust analytics *are* used. Narrow to the analytics product and drop the gating.
- **KILL** — none of it is used at week 8. §15.

### Exit criterion
- [ ] A written decision recording the measurements and the path chosen, with the raw ledger slice attached

---

## F3 — Orchestra

**Reached only if F2 says GO.**

This is `Requirements-implementation.md` v2.0's C1 and C2, re-based on what F0 and F1 built. The content is unchanged; the foundations underneath it are now real rather than simulated.

**Modules.** M4 · M31 *(re-based on ACP per `FR-M34-02`)* · M5 · M6 · M7 · M8 · M9 · M28 · M33 *(full)* · **M38** · M13 · M26 · the §6.10 roster as ACP agents · the remaining `VIGUIX_Final.md` screens

### Ordering within F3

1. **M33 Deterministic Engine, full** — the action-class catalogue, deterministic-first dispatch, assisted and generative modes, per-class reporting. Before the router, because `E13` requires it.
2. **M8 Model Router behind the engine** — refusal of calls with a deterministic path (`FR-M8-15`), `why_llm` on every permitted call (`FR-M8-16`), LLM dependency ratio (`FR-M8-17`).
3. **M4 Loop Runtime** — six loops, bounds validated at load, checkpoints, interrupt/resume, time travel.
4. **M9, M28** — tools, LSP, tree-sitter beyond F0's attribution subset, semantic search, reuse-first.
5. **M7** — memory fabric and the Instruction Library.
6. **M38 Brownfield Comprehension** — comprehension records, brownfield risk score, characterisation-test gate. **In F3, not later**, because for an IT-services organisation this is where the agents will actually be used and where the evidence says they are weakest.
7. **M31 + the roster as ACP agents** — the prebuilt agents built as ACP-conformant adapters, each surviving unplug and re-plug.
8. **M5, M6, M13, M26**, SDLC phases 1–7, the remaining screens.

### F3 exit criteria
- [ ] `AC-01`…`AC-29` from `Requirements_Final.md` §10.1
- [ ] **`AC-35`** A packet targeting an uncovered high-risk legacy module is blocked until characterisation tests exist, with the block explained by the comprehension record
- [ ] `AC-26` LLM dependency ratio ≤ 0.35 on the reference story
- [ ] Every prebuilt agent survives unplug and re-plug
- [ ] §10.2 quality bar — **now measured against the F2 baseline**, so the question is whether Meridian's own agents beat the team's existing ones, not whether they work at all

---

## F4+ — Learning, Scale, Compliance

As `Requirements-implementation.md` v2.0 phases C3–C6, unchanged in content:

- **C3 Quality Gates** — M12 full, full skill catalogue, M16 upgrade/revocation, phase 5–7 additions
- **C4 Learning & Portability** — M14 with distillation, M15, M16 adapter packages
- **C5 Orchestration, Scale & Compliance** — Phase Orchestrators, M21, M22, M29, M17 full, M30 full, phases 8–9, anchoring, crypto-shredding, tenant isolation
- **C6 Differentiation** — the 11 v2 items

Two changes: **crypto-shredding is cheap** because F0 encrypted blobs from day one; and **M39 cost governance** is already in place from F1, so C5's cost work reduces to chargeback and model comparison.

---

## 11. Cross-Cutting Workstreams

| Workstream | Cadence | Notes |
|---|---|---|
| **Observer health** | Every release of every observed agent | `FR-M35-08`. A vendor's release can silently degrade observation. Automate a check. |
| **Zero-model-call assertion** | Every commit | F0 and Flight Recorder tier paths. A model-client import fails the build. |
| **Tier isolation** | Every commit | `G5`. Disable each tier in CI and run the lower tiers' full suite. |
| **Provenance survival** | Every phase exit | `G4`. Uninstall Meridian, verify trailers and bundle on a clean machine. |
| **Rejection and trust reconciliation** | Weekly from F0 | Every reported number recomputed from the ledger and compared |
| **ACP conformance** | Every commit from F1 | `NFR-30` |
| **Competitor parity** | Every phase exit from F1 | `X-31`. Devin Desktop, Cursor, Copilot surfaces move; re-time the five core operations. |
| **Golden corpus** | From F1 | Real sessions from real agents, replayed. The Simulation Core becomes its runner in F3. |
| **Security regression** | Every commit | `SEC-27`…`29` plus the base `SEC-01`…`26` |
| **Cross-platform** | Every phase exit | Windows, macOS, Linux, Remote SSH |

---

## 12. Definition of Done

Inherits `Requirements-implementation.md` v2.0 §14. Adds:

- [ ] **Works with zero Meridian agents** if the capability is in Flight Recorder or Governor (`G1`)
- [ ] **Vendor tag and observation confidence** on every agent-attributed artifact the capability produces (`X-27`)
- [ ] **Fallback chain documented and tested** for any observation the capability depends on (`G3`)
- [ ] **Survives uninstallation** where the capability produces provenance (`G4`)
- [ ] **Tier-correct** — the capability appears only in its tier, and disabling higher tiers leaves it intact (`G5`)
- [ ] **Greenfield/brownfield split** on any metric the capability reports (`G6`)
- [ ] **No model call** if the capability is in the Flight Recorder tier
- [ ] **Standard implemented, not invented** where one exists (`G2`) — with the standard named in the commit message

---

## 13. Sequencing Dependencies

```
F−1  Legal clearance  ◄── D22 closed in writing. Nothing starts before this.
 │
 └─→ F0  Flight Recorder                                          [6–10 weeks]
      │   ledger · attribution · 2 observers · trailers · verifier · 3 screens
      │   value with somebody else's agent · zero model credentials
      │
      └─→ F1  Governor
           │   ACP host · gates over external work · roles · steer
           │   trust analytics · cross-vendor spend · 10 screens
           │
           └─→ F2  EVIDENCE GATE  ◄── 20 real stories, measured
                │
                ├─ STOP ──→ ship Flight Recorder + Governor. Success.
                ├─ PIVOT ─→ narrow to trust analytics
                ├─ KILL ──→ §15
                └─ GO ────→ F3  Orchestra  ──→ F4+  C3–C6
```

**Hard serial:** F−1 → F0 → F1 → F2. Nothing parallelises across these; each answers a question the next depends on.

**The critical path is F−1 → F0.** Everything else is downstream of proving that a team will install a recorder and use it.

---

## 14. GUI Interlock

Per `gaps_guix.md` §5.

| Engineering | GUI | Joint deliverable |
|---|---|---|
| **F−1** | — | Nothing. |
| **F0** | **GF0 Recorder** | Tokens, shell, X-27…X-30, 10.45, 10.46, 10.7, 10.3 (agent-agnostic), 10.40 rewritten, 10.50. **Built against real external-agent sessions**, not the Simulation Core. |
| **F1** | **GF1 Governor** | 10.1, 10.6, 10.27, 10.28, 10.32, 10.47, 10.49, 10.43 as ACP host, 10.16 external-aware. Built against real gated PRs. |
| **F2** | **GF2 Evidence** | No new screens. The Trust Observatory's numbers are the deliverable. |
| **F3** | **GF3 Orchestra** | The remainder of `VIGUIX_Final.md` §10 — Floor, Dojo, Loops, Portfolio, Memory Studio, modelling surfaces — **only for the data F2 proved matters.** |
| **F4+** | **GF4+** | 10.48 Comprehension Studio (or pulled into GF1 for a brownfield-heavy pilot, `V11`), refinement |

**The interlock rule:** a screen is built against real recorded sessions, not simulated ones, through GF1. The Simulation Core (M32) still gets built — in F3, as the regression harness it was always going to become.

---

## 15. Kill Criteria

A plan that cannot be stopped is not a plan. These are the conditions under which the honest answer is to stop.

| # | Condition | Measured at | Response |
|---|---|---|---|
| **K1** | `D22` resolves against you — the employer owns the IP and will not sanction it | F−1 | Stop, or convert to path (a). Do not proceed on hope. |
| **K2** | Fewer than 2 of 5 F0 testers are still using the recorder at week 8 | F0 + 8 weeks | The provenance problem is not felt strongly enough. Stop or pivot to the analytics-only product. |
| **K3** | No observer achieves better than `inferred` confidence for any major agent, and users do not trust `inferred` data | F0 exit | The product's core claim cannot be delivered. Stop. |
| **K4** | Gates measurably increase cycle time without reducing rejection rate or catching defects | F2 | Drop gating; keep the recorder and analytics. |
| **K5** | Provenance queries are never run — the ledger is written and never read | F2 | The product solves a problem nobody has at the moment of need. Pivot to compliance-export-only, or stop. |
| **K6** | An incumbent ships cross-vendor signed provenance with gates | any | Reassess honestly. The differentiator was structural, not technical; if it closes, the position is gone. |
| **K7** | F0 exceeds 16 weeks | F0 | Scope was wrong. Cut to the ledger, one observer, one screen, and re-time. |

**Stopping at K2 through K5 is not failure.** Each of them costs weeks and saves years.

---

## 16. Slip Plan

Cut in this order. Each cut leaves something a team can use.

| Order | Cut | Cost |
|---|---|---|
| 1 | The Rust verifier (ship the Python one) | Cosmetic |
| 2 | The Copilot observer in F0 (move to F1) | One vendor's provenance waits |
| 3 | Cursor / Codex / Devin observers | Three vendors stay at `inferred` or unobserved |
| 4 | Cross-vendor spend (M39) | Loses a real differentiator; the ledger still holds the data for later |
| 5 | Steer and clarify for hosted agents (M25) | Governor becomes gates-and-analytics only |
| 6 | The ACP host (M34) | Loses the "as good as Devin Desktop" claim; observation-only Governor still works |
| 7 | The entire Orchestra tier (F3) | The product becomes the flight recorder and the governor. **This is the `R29` outcome and it is acceptable.** |

**Never cut:** the ledger's chain integrity · the observation-confidence labelling · the git trailers · the open verifier · the zero-model-call guarantee in Flight Recorder · the greenfield/brownfield split · the tier isolation. Each is either the product's honesty or the product's promise.

---

## 17. Risk Retirement Schedule

| Risk | Retired or controlled in | Control |
|---|---|---|
| **R26** Microsoft ships native ACP | F1 | `FR-M34-05` — contribute upstream, layer governance on whatever host exists |
| **R27** Observers go blind on vendor change | **F0** | `FR-M35-08` versioned observers, `NFR-32` degrade-not-silence, git-trailer floor |
| **R28** Incumbents ship portable provenance | F1 | Cross-vendor single ledger with gates — a single vendor's trailer does not give a team the view across three agents |
| **R29** Orchestra never earns its place | **F2** | Designed as an acceptable outcome; the slip plan ends there |
| **R30** Dependence on incumbent goodwill | **F0** | Observation only via open surfaces — ACP, OTel, git — that no vendor can revoke without breaking their own users |
| R2 Orphaned sidecars | F0 | Dual teardown contract |
| R14 Destroyed uncommitted work | F1 | Worktrees, for hosted agents. **Flight Recorder cannot protect the tree and says so.** |
| R15 Untestable runtime | F0 / F3 | Ledger replay in F0; the Simulation Core as harness in F3 |
| R16 Erasure conflict | F4 *(enabled F0)* | Encrypted blobs from day one |
| R17 Rubber-stamping | **F1** | `FR-M20-06` approval hygiene, measured in F2 |
| R21 Adapter supply chain | F1 | ACP registry trust plus Meridian's own review, probation, revocation |
| R24 Python-first degrades quality | F3 | Per-class reporting before any reclassification |

---

## 18. Decision Schedule

| # | Decision | Must close by |
|---|---|---|
| **`D22`** | **Employment and IP path** | **F−1. Before the first commit.** |
| `D20` | Which observers ship first, and at what confidence each is achievable | F0 week 1 |
| **`D23`** | **Trailer mechanism — `commit-msg` hook vs. `git notes` as default** *(new)* | F0 week 2 |
| `D19` | Open-core: open-source the ledger and ACP host, sell Governor and Orchestra | F1 start |
| `D9` | Identity source of record | F1 |
| `D21` | Whether the Orchestra tier is built at all | **F2** — this is what F2 decides |
| `D1` | Loop runtime — adopt or build | F3 start |
| `D2` | Model routing and tiering | F3 start |
| `D16` | Action-class catalogue ownership | F3 |
| `D14` | Security phase placement | F3 |
| `D5`, `D17` | Trainer scope; bridged agents' own learning | F4 |
| `D3`, `D7`, `D13` | Anchoring; deployment execution; tenant isolation | F4+ |

---

## 19. What Happens to the Existing 533 Requirements

| Disposition | Count (approx.) | Where |
|---|---|---|
| **Reused in F0** | ~55 | M10 (12), M11 (5), M1/M3 minimum (14), M20-01, M30-01, M33 attribution subset (4), M17 core (4), plus NFR and SEC baseline |
| **Reused in F1** | ~65 | M12 v1 subset (6), M20 (8), M25 (8), M18 (9), M31 governance retained (12), plus gates and phase 5–7 criteria applied to external work |
| **Moved to F3** | ~230 | M4, M5, M6, M7, M8, M9, M13, M26, M28, M33 full, the roster, SDLC phases 1–7, the remaining GUI |
| **Moved to F4+** | ~140 | M14, M15, M16, M17 full, M21, M22, M23, M24, M27, M29, M30 full, compliance, tenancy |
| **Superseded** | ~8 | `FR-M31-01` (bespoke protocol), `FR-M31-05` (six bridges), `FR-M31-11` (SDK conformance) → ACP; parts of M32's GUI-first role |
| **Unchanged but re-timed** | rest | Every ID survives; only its phase moved |

**No requirement is deleted.** The specification remains the destination; this plan changes the route and the order in which value is delivered along it.

---

## 20. Traceability Appendix

### New modules to phases

| Module | F0 | F1 | F3 | F4+ |
|---|---|---|---|---|
| **M34 ACP Host** | — | 01–06, 08 | 07 | — |
| **M35 External Agent Proxy** | 01, 02, 03, 06, 08 *(2 observers)* | 04, 05, 07, 08 *(rest)* | — | — |
| **M36 Flight Recorder** | 01–05, 07 | — | — | 06 *(open spec, if not F0)* |
| **M37 Trust Analytics** | 01 *(subset)*, 06 | 01–05, 07, 08 | — | — |
| **M38 Brownfield Comprehension** | — | — | 01–06 | — |
| **M39 Cross-Vendor Spend** | — | 01–04 | — | 05 |

### New NFRs, SEC, AC

| Phase | NFR | SEC | AC |
|---|---|---|---|
| **F0** | 28, 29, 31, 32 | 27, 29 | 30, 33, 34 *(partial)* |
| **F1** | 30 | 28 | 31, 32, 34, 36, 37 |
| **F3** | — | — | 35, plus 01–29 |

### Principles to phases

| Principle | Enforced from |
|---|---|
| P20 Beneath, not against · G1 | F0, every commit |
| P21 Adopt the standard · G2 | F0 (git, OTel, SSDF), F1 (ACP, MCP) |
| P22 Trust is the product · G5 | F0 tiering scaffold |
| P23 First value in weeks · G7 | F0 time-box |
| P24 Vendor-independent · G4 | F0 trailers and verifier |

### Risks and decisions

Risks: `R26` F1 · `R27` **F0** · `R28` F1 · `R29` **F2** · `R30` **F0**
Decisions: `D22` **F−1** · `D20`, `D23` F0 · `D19`, `D9` F1 · `D21` **F2** · rest F3+

---

*End of plan. `D22` gates everything. F2 decides whether F3 exists.*
