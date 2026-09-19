# Meridian Loom — Engineering Requirements Specification

| | |
|---|---|
| **Document** | Requirements_Final.md |
| **Version** | **2.0 — merged and reconciled** |
| **Supersedes** | `Requirements.md` v1.0 · `Requirements-Additions.md` v1.0 |
| **Author** | Ravaleedhar Reddy |
| **Companions** | `vision.md` (architecture vision) · `VIGUIX.md` (interface spec) · `VIGUIX_GAPS.md` (interface gap analysis) · `viguix-implementation.md` (GUI build order) |
| **Deliverable** | `meridian-loom.vsix` — a Visual Studio Code extension |
| **Audience** | Engineers implementing the plugin. This document is written to be built from. |
| **Scale** | 30 modules · 9 SDLC phases · ~445 numbered requirements |

---

## Table of Contents

0. [About This Merge](#0-about-this-merge)
1. [Scope and Objectives](#1-scope-and-objectives)
2. [Glossary](#2-glossary)
3. [Design Principles](#3-design-principles)
4. [System Architecture](#4-system-architecture)
5. [Module Requirements — M1 to M30](#5-module-requirements)
6. [Agent Requirements by SDLC Phase](#6-agent-requirements-by-sdlc-phase)
7. [Data Models](#7-data-models)
8. [Non-Functional Requirements](#8-non-functional-requirements)
9. [Security Requirements](#9-security-requirements)
10. [Acceptance Criteria](#10-acceptance-criteria)
11. [Ecosystem Integration](#11-ecosystem-integration)
12. [Phased Delivery Plan](#12-phased-delivery-plan)
13. [Risk Register](#13-risk-register)
14. [Open Decisions](#14-open-decisions)
15. [Resolved Tensions](#15-resolved-tensions)
16. [Changes from v1.0](#16-changes-from-v10)
17. [Requirement Index](#17-requirement-index)

---

## 0. About This Merge

### 0.1 What was merged

`Requirements.md` v1.0 defined 17 modules and 227 requirements. `Requirements-Additions.md` v1.0 proposed 13 further modules, ~189 additional requirements, and identified 12 tensions where the base document was silent or self-contradictory.

This document is the reconciled result. Three things were done beyond concatenation:

1. **Extensions were merged into their parent modules**, not appended. `FR-M7-09` through `FR-M7-13` now sit inside M7, in sequence, so a reader of M7 sees the whole module.
2. **The twelve tensions were resolved, and the resolutions applied to the base text.** Where a base requirement was wrong or incomplete in light of an addition, the base requirement was amended in place and the amendment recorded in §16. This is the substantive difference between this document and a stapled pair of files.
3. **Release targets were assigned to every requirement.** The base document used bare MUST/SHOULD/COULD; the additions used MUST/SHOULD/COULD plus v1/v1.x/v2. All requirements now carry both.

### 0.2 ID stability

**Every requirement ID from both source documents is preserved unchanged.** No ID was renumbered, merged, or retired. A cross-reference written against either source document still resolves. §17 gives the full index.

### 0.3 Release target vocabulary

| Target | Meaning |
|---|---|
| **v1** | Required before Phase 1 acceptance (§10.1). Without it the product is either unsafe or untestable. |
| **v1.x** | Required before enterprise rollout beyond the first pilot team. |
| **v2** | Differentiating. Not blocking. |

### 0.4 The one editorial judgment applied

The base document's requirements carried no release target. Targets were derived from the base §11 phased delivery plan by this rule, and the derivation is the only place this merge exercised judgment not present in either source:

- Modules delivered in base phases **P0 and P1** → **v1**
- Modules delivered in **P2** → **v1.x**, except requirements that Phase 1 acceptance criteria depend on (notably `FR-M12-05` and `FR-M12-07`), which are **v1**
- Modules delivered in **P3 and P4** → **v1.x**, except where the base document marked them COULD → **v2**

Where this derivation produced a target that contradicts a source document's explicit statement, the source wins. Any target a reviewer disagrees with can be changed without touching the requirement text.

### 0.5 Conflict resolution log

| Conflict | Resolution |
|---|---|
| `FR-M1-05` (apply diffs via workspace edit API) vs. `FR-M18-01` (agents write only in a story worktree) | `FR-M1-05` amended: the workspace edit API is used, but always targeting the story worktree, never the primary tree. |
| `FR-M10-01` (append-only, deletes prevented by trigger) vs. `FR-M10-14` (right-to-erasure) | `FR-M10-01` amended with an explicit crypto-shredding carve-out. Blob keys are destroyed; no row is ever deleted; the chain still verifies because it hashes ciphertext. |
| Base §6.1 L4 loop exits at "PR merged" vs. `FR-M23-01/02` (CI in the loop) | L4 exit criterion amended to "merged **and** CI green". |
| Base §1.4 silent on VS Code Remote vs. `FR-M3-11` | §1.4 rewritten to name supported remote configurations explicitly. |
| `FR-M14-01` (harvest gate decisions) vs. `FR-M23-03`, `FR-M25-05`, `FR-P9-03/04` | `FR-M14-01` amended to enumerate all six signal sources. |
| Base §1.2 implies polyglot parallelism vs. absence of multi-repo support | §1.3 now states plainly that v1 is single-repository; M22 is v1.x. |

---

## 1. Scope and Objectives

### 1.1 Primary objective

Deliver a VS Code extension that ingests a work item (a Jira story file such as `EDB-12345.txt`, a connector-fetched issue, or direct text) and drives it through the software development lifecycle using a hierarchy of AI agents, producing a reviewed and merged pull request, with every agent action recorded in a tamper-evident local ledger and every consequential decision gated by an authenticated human.

### 1.2 In scope

- VS Code extension (TypeScript) with React webview dashboard
- Python sidecar hosting the agent runtime and loop engine, running locally or on a remote host
- **Isolated git worktree per story** — agents never write to the human's working tree
- Skill Pack loading, enabling runtime respecialisation of agents by tech stack
- Hash-chained, signed ledger with a chain viewer and a query API
- Human-in-the-loop governance: approve, rework, **steer**, escalate, waive, train, onboard, export, pause, retire
- **Clarifying-question protocol and uncertainty-triggered escalation** — agents ask rather than guess
- **Deterministic replay** of any story from a recorded cassette, and a golden story corpus as the runtime's regression suite
- Supervised agent evolution from ledger evidence, under regression gates
- Agent export/import packaging for cross-team portability
- Greenfield scaffolding and brownfield modification for the target stacks
- Code intelligence: language server, tree-sitter, semantic search, reuse-first policy
- Work item connector integration with write-back
- CI integration and merge, closing the delivery loop

### 1.3 Out of scope (v1)

- **Multi-repository stories.** v1 is single-repository. M22 delivers cross-repo in v1.x. The vision's polyglot-parallelism promise is a v1.x capability and should not be represented as v1.
- Agents modifying their own source code — at any version
- Autonomous merge without human approval — at any version, at any autonomy tier
- Cloud-hosted multi-tenant execution (v1 is workspace-local, with a remote sidecar option)
- Deployment execution (release *planning* is v1.x; execution is v2, `FR-P8-02`)
- Any claim of guaranteed on-time delivery. Delivery SLA with slip prediction (`FR-M21-06`) is the honest implementation.

### 1.4 Target platforms

**Local:** Windows x64/arm64, macOS x64/arm64, Linux x64/arm64.

**Remote (v1 MUST, `FR-M3-11`):** VS Code Remote — SSH, WSL, Dev Containers, and GitHub Codespaces, with the sidecar running on the remote host where the repository lives. This is the dominant enterprise configuration and is not optional.

**Unsupported:** VS Code Web and vscode.dev, because the architecture requires a local child process. This exclusion is permanent for the current architecture.

### 1.5 Release targets

See §0.3. Every requirement in this document carries one.

---

## 2. Glossary

| Term | Meaning |
|---|---|
| **Chief Orchestrator** | The Delivery Head Agent (L0). One per workspace. Owns a story end-to-end. |
| **Phase Orchestrator** | L1 agent owning one SDLC phase and its gates. |
| **Role Agent** | L2 agent modelling a delivery role (Analyst, Architect, Developer…). |
| **Skill Pack** | A versioned folder (`SKILL.md` + assets) that respecialises a Role Agent to a stack or domain. |
| **Sub-Agent** | L4 ephemeral worker fanned out for an independent unit of work. |
| **Loop** | A bounded, checkpointed control cycle with declared entry, exit, bounds, and escalation. |
| **Gate** | A checkpoint where the story cannot advance without an objective criterion and/or human approval. |
| **Ledger** | The local append-only hash-chained Merkle log of all agent activity. |
| **Work Packet** | The smallest contracted unit of implementable work, with its own acceptance tests. |
| **Autonomy Tier** | The permission level an agent has earned for a task class. |
| **Trust Score** | Composite metric gating autonomy tier promotion. |
| **First-Pass Yield (FPY)** | Percentage of agent outputs approved without rework. The headline quality metric. |
| **Story Worktree** | The isolated git worktree in which all agents for one story do their writing. |
| **Steer** | Human guidance injected into a running loop without triggering a full rework. |
| **Cassette** | A recorded set of model calls and tool results keyed by canonical request hash, enabling deterministic replay. |
| **Golden Story Corpus** | The maintained set of ≥20 real stories replayed in CI as the runtime's regression suite. |
| **Complexity Tier** | S / M / L / XL classification assigned at ingest, selecting loop bounds and model tiering. |
| **Human Role** | Engineer, Reviewer, Approver, Governor, or Auditor — determines permitted gate actions. |
| **Separation of Duties (SoD)** | Policy preventing the same identity from both producing and approving the same work. |
| **Crypto-shredding** | Erasure of personal data by destroying its encryption key, leaving the hash chain intact. |
| **Blast Radius** | Low / medium / high classification of a change's risk, driving gate strictness. |
| **Tenant** | An isolated client boundary in an IT-services deployment — repositories, memory, ledger, and models. |

---

## 3. Design Principles

| # | Principle | Consequence |
|---|---|---|
| P1 | **The ledger is the product.** | Nothing an agent does may bypass the ledger. Logging is not optional or best-effort. |
| P2 | **Verification outranks explanation.** | No agent passes a gate by explaining well. It passes by tests, scans, and approvals. |
| P3 | **Writes are single-threaded per service.** | Fan out for reading, analysis, and independent services only. Never for interdependent implementation. |
| P4 | **Autonomy is earned, never granted.** | Every agent starts at the lowest tier and is promoted on sustained measured performance. |
| P5 | **All input is untrusted.** | Repo content, story text, dependencies and skill packs are treated as adversarial by default. |
| P6 | **Identity is data, not code.** | New stacks and new roles arrive as Skill Packs and manifests, never as extension source changes. |
| P7 | **Every loop is bounded.** | A loop without max iterations, a budget, and an escalation path will not execute. |
| P8 | **Measure actual, not perceived.** | Instrument real cycle time and quality, because perceived AI speedup is documented to diverge from measured outcome by roughly 39 points. |
| P9 | **Safety is monotonic.** | No evolution step may weaken a declared constraint, whatever its performance score. |
| P10 | **Fail visible, not silent.** | Budget breaches, gate failures, and chain-integrity failures surface loudly in the dashboard. |
| **P11** | **The human's working tree is sacred.** | Agents write only in a story worktree. No agent action may modify, stage, or discard a human's uncommitted work. |
| **P12** | **Ask rather than assume.** | Below a confidence threshold, or on an unresolved ambiguity, the agent stops and asks. Silent assumption is a defect, not efficiency. |
| **P13** | **The runtime must be testable without a model.** | Every model call is recordable and replayable. A change to the loop runtime is proven against the golden corpus, offline, in CI. |
| **P14** | **Learn from every signal, not just the gate.** | Rework is only the loudest signal. CI failures, review comments, human edits, and incidents are richer and must all reach the Trainer. |
| **P15** | **Reuse before writing.** | An agent searches for an existing implementation before creating a new one, and cites what it found or why nothing fit. |

---

## 4. System Architecture

### 4.1 Process topology

```
VS Code Window  (local, or client of a Remote host)
│
├── Extension Host (Node.js)          ← meridian-loom extension
│   ├── activation / commands / views / chat participant
│   ├── Webview Dashboard host (React)
│   ├── Workspace + SCM adapter  ──→ story worktrees only
│   ├── SecretStorage adapter
│   └── Sidecar Supervisor ──────────┐
│                                     │ JSON-RPC / stdio (framed, versioned)
└── Meridian Core (Python 3.11+) ◄───┘   [local host, or the Remote host]
    ├── Loop Runtime — durable graph execution, checkpoints, interrupt/resume
    ├── Agent Registry │ Skill Loader │ Memory Fabric
    ├── Model Router — tiering, caching, redaction, failover, backpressure
    ├── Tool Layer — MCP client, LSP bridge, tree-sitter, repo/build/test tools
    ├── Ledger Service — SQLite, hash-chained, signed, queryable
    ├── Governance / Policy Engine
    ├── Replay Recorder — cassettes, fault injection
    └── Connector Layer — issue trackers, CI, SCM forge
```

### 4.2 Storage layout

```
<workspace>/.meridian/
├── config.json               # workspace configuration (committed)
├── policy/                   # policy packs, git-backed (committed)
├── skills/                   # workspace-local skill packs (committed)
├── agents/                   # agent manifests (committed)
├── memory/
│   ├── procedural/           # playbooks, conventions (committed)
│   ├── semantic/             # project facts + vector index
│   └── episodic/             # per-story trace summaries (not committed)
├── worktrees/                # one isolated git worktree per active story (not committed)
│   └── <story-id>/
├── ledger/
│   ├── ledger.db             # SQLite hash-chained log (not committed)
│   └── blobs/                # prompt/output blobs, content-addressed, encrypted
├── cassettes/                # replay recordings (not committed)
├── checkpoints/              # loop runtime durable state (not committed)
└── exports/                  # agent export packages
```

`.meridian/ledger`, `.meridian/checkpoints`, `.meridian/memory/episodic`, `.meridian/worktrees`, and `.meridian/cassettes` MUST be added to `.gitignore` on initialisation.

### 4.3 Module map

Thirty modules, in numeric order, grouped by the concern each serves. Numbering follows source-document order and is stable.

| Family | Modules |
|---|---|
| **Platform & runtime** | M1 Extension Host · M2 Webview Dashboard · M3 Sidecar & IPC · M4 Loop Runtime · M27 Replay & Runtime Testing · M30 Runtime Operations |
| **The agent organisation** | M5 Agent Registry · M6 Skill Loader · M7 Memory Fabric · M15 Onboarding · M16 Replicator |
| **Intelligence & economics** | M8 Model Router · M26 Cost Forecasting |
| **Code & tools** | M9 Tool Layer · M28 Code Intelligence |
| **Record & assurance** | M10 Ledger · M11 Chain Viewer · M12 Governance · M13 XAI · M20 Human Identity & Roles |
| **Learning** | M14 Trainer |
| **Work & delivery** | M18 Workspace Isolation · M19 Work Item Connectors · M21 Portfolio Orchestration · M22 Multi-Repository · M23 CI/CD & Merge · M25 Steering & HITL Refinement |
| **Surfaces & output** | M24 Chat & Editor Integration · M29 Documentation |
| **Measurement** | M17 Telemetry & KPI |

---

## 5. Module Requirements

### M1 — Extension Host

*Platform & runtime.* The VS Code-side shell: activation, commands, views, workspace access, credentials, sidecar lifecycle.

| ID | Requirement | Priority |
|---|---|---|
| FR-M1-01 | The extension SHALL declare granular activation events. It SHALL NOT use `*`. Preferred: `onCommand:*`, `onView:meridianLoom.*`, and `onStartupFinished` where background readiness is required. | MUST v1 |
| FR-M1-02 | The extension SHALL contribute an Activity Bar container with tree views: Agents, Stories, Loops, Skills, Ledger. | MUST v1 |
| FR-M1-03 | The extension SHALL register commands: `meridian.ingestStory`, `meridian.openDashboard`, `meridian.installSkill`, `meridian.onboardAgent`, `meridian.exportAgent`, `meridian.importAgent`, `meridian.verifyChain`, `meridian.haltAll`, `meridian.steer`, `meridian.dryRun`, `meridian.abortStory`, `meridian.doctor`. | MUST v1 |
| FR-M1-04 | The extension SHALL NOT perform blocking synchronous work exceeding 50 ms on the extension host thread. All orchestration executes in the sidecar. | MUST v1 |
| FR-M1-05 | **[AMENDED]** The extension SHALL apply diffs via the VS Code workspace edit API, never by direct filesystem writes, so that undo, file watchers, and dirty-state behave correctly. **All such edits SHALL target the story worktree (`FR-M18-01`). No agent-originated edit SHALL ever be applied to the user's primary working tree.** | MUST v1 |
| FR-M1-06 | The extension SHALL store all model credentials in `context.secrets` (SecretStorage). Credentials SHALL NOT be written to settings, workspace files, or logs. | MUST v1 |
| FR-M1-07 | The extension SHALL detect SecretStorage unavailability (notably Linux without a keyring backend) and refuse to start rather than falling back to plaintext storage. | MUST v1 |
| FR-M1-08 | The extension SHALL expose read-only workspace context (open files, selection, SCM branch, diagnostics) to the sidecar over the RPC channel on request. | SHOULD v1 |
| FR-M1-09 | The extension SHALL surface all long-running work through `withProgress` with a cancellation token wired to sidecar loop cancellation. | MUST v1 |
| FR-M1-10 | The extension SHALL be bundled with esbuild via `vscode:prepublish`, with `vscode` marked external and a `.vscodeignore` excluding sources, tests, and dev assets. | MUST v1 |

### M2 — Webview Dashboard

*Platform & runtime.* The interface surface. Visual and interaction specification lives in `VIGUIX.md`; this module states the platform contract it must honour.

| ID | Requirement | Priority |
|---|---|---|
| FR-M2-01 | The dashboard SHALL be a React application hosted in a VS Code webview. | MUST v1 |
| FR-M2-02 | Every webview SHALL set a Content Security Policy of the form `default-src 'none'; script-src 'nonce-<n>'; style-src ${webview.cspSource}; img-src ${webview.cspSource} data:; font-src ${webview.cspSource}`. Inline scripts without a nonce SHALL NOT be used. | MUST v1 |
| FR-M2-03 | All local resources SHALL be loaded via `Webview.asWebviewUri()` with directories declared in `localResourceRoots`. | MUST v1 |
| FR-M2-04 | The dashboard SHALL persist UI state via `getState()`/`setState()` and restore through a registered `WebviewPanelSerializer`. It SHALL NOT rely on `retainContextWhenHidden` for correctness. | MUST v1 |
| FR-M2-05 | All extension↔webview messages SHALL pass through a single typed message bus with a discriminated-union message contract and a schema version field. | MUST v1 |
| FR-M2-06 | The dashboard SHALL theme entirely from VS Code CSS custom properties (`--vscode-*`) and SHALL render correctly in light, dark, and high-contrast themes. | MUST v1 |
| FR-M2-07 | The dashboard SHALL provide the screens specified in `VIGUIX.md` §10 and `VIGUIX_GAPS.md` Part A, delivered in the order given by `viguix-implementation.md`. | MUST v1 |
| FR-M2-08 | The Loop Graph SHALL render live loop state (open loops, current iteration, budget consumed, distance to escalation) with sub-second update latency, using a client-side graph library operating within the CSP sandbox. | MUST v1 |
| FR-M2-09 | The dashboard SHALL degrade gracefully when the sidecar is unavailable, showing last-known state marked stale rather than an empty or erroring view. | MUST v1 |
| FR-M2-10 | The dashboard SHALL meet WCAG 2.1 AA for contrast, keyboard navigation, and focus order. | SHOULD v1 |
| FR-M2-11 | Any agent-produced text rendered in the dashboard SHALL be escaped. Markdown rendering SHALL sanitise HTML and strip scripts and event handlers. | MUST v1 |

### M3 — Sidecar and IPC

*Platform & runtime.* Process lifecycle is the single largest reliability risk in this architecture. FR-M3-02 and FR-M3-03 are a dual contract; both halves are mandatory.

| ID | Requirement | Priority |
|---|---|---|
| FR-M3-01 | The extension SHALL spawn Meridian Core as a child process and communicate over framed JSON-RPC 2.0 on stdio. | MUST v1 |
| FR-M3-02 | The Sidecar Supervisor SHALL terminate the child process in `deactivate()`, on webview disposal where it is the last consumer, and on extension deactivation for any reason. | MUST v1 |
| FR-M3-03 | Meridian Core SHALL independently monitor for parent-process death and self-terminate within 10 seconds if orphaned. **Orphaned sidecars are a documented failure mode in shipping agent extensions; both halves of this contract are mandatory.** | MUST v1 |
| FR-M3-04 | The Supervisor SHALL handle the `error` event on spawn distinctly from a non-zero exit, and SHALL produce actionable diagnostics for `ENOENT` (interpreter not found), `EACCES`, and policy-blocked execution. | MUST v1 |
| FR-M3-05 | Python interpreter resolution SHALL follow this order: (1) `meridian.python.interpreterPath` setting, (2) the VS Code Python extension's environment API if present, (3) a bundled runtime if shipped, (4) `python3`/`python` on PATH. The resolved path SHALL be shown in the status bar. | MUST v1 |
| FR-M3-05a | Where a bundled runtime is shipped, the extension SHALL be published as **platform-specific VSIX targets** (`--target win32-x64`, `darwin-arm64`, `linux-x64`, …) rather than a single universal package. | MUST v1 |
| FR-M3-06 | The Supervisor SHALL implement health checks (heartbeat every 5 s) and SHALL restart the sidecar at most 3 times in 5 minutes before entering a failed state requiring user action. | MUST v1 |
| FR-M3-07 | On sidecar restart, in-flight loops SHALL resume from their last durable checkpoint, not from the beginning. | MUST v1 |
| FR-M3-08 | The RPC contract SHALL be versioned. On version mismatch the extension SHALL refuse to proceed and prompt the user to reinstall rather than operating with an incompatible core. | MUST v1 |
| FR-M3-09 | Sidecar stdout SHALL carry only framed RPC. All logging SHALL go to stderr and a rotating log file, never to stdout. | MUST v1 |
| FR-M3-10 | The sidecar SHALL bind no network listener by default. If a local HTTP/WS transport is enabled for debugging, it SHALL bind to loopback only with a per-session bearer token. | MUST v1 |
| FR-M3-11 | The extension SHALL function under **VS Code Remote — SSH, WSL, Dev Containers, and GitHub Codespaces**, with the sidecar running on the remote host where the repository lives. | MUST v1 |
| FR-M3-12 | Sidecar resource limits (CPU, memory) SHALL be configurable and enforced via cgroups or job objects where the platform permits. | SHOULD v1.x |
| FR-M3-13 | The sidecar SHALL expose a **versioned local API** (Unix socket / named pipe, token-authenticated) so external tools and the CLI can drive it. | SHOULD v1.x |

### M4 — Loop Runtime

*Platform & runtime.* Durable, bounded, checkpointed graph execution with cycles.

| ID | Requirement | Priority |
|---|---|---|
| FR-M4-01 | The Loop Runtime SHALL execute a directed graph of agent invocations supporting cycles. | MUST v1 |
| FR-M4-02 | Every loop definition SHALL declare: entry condition, body graph, exit criteria, max iterations, token budget, wall-clock budget, cost ceiling, escalation target. A loop missing any field SHALL fail validation at load time and SHALL NOT execute. | MUST v1 |
| FR-M4-03 | The runtime SHALL implement the six canonical loops (L1 Micro, L2 Task, L3 Phase, L4 Delivery, L5 Learning, L6 Organisation) with the default bounds specified in §6.1. | MUST v1 |
| FR-M4-04 | State SHALL be typed, and concurrent updates from parallel branches SHALL merge through declared reducers. Silent last-write-wins is prohibited. | MUST v1 |
| FR-M4-05 | The runtime SHALL checkpoint durably after every node execution, such that a process kill loses at most one node's work. | MUST v1 |
| FR-M4-06 | The runtime SHALL support interrupt/resume for human gates: a loop suspends at a gate, persists, releases resources, and resumes on a dashboard action. | MUST v1 |
| FR-M4-07 | The runtime SHALL support time-travel: replaying a loop from any checkpoint with modified state, for debugging and ablation. Forked replays SHALL be ledger-tagged as replays and never counted as live work. | MUST v1 |
| FR-M4-08 | On any bound breach the runtime SHALL halt the loop, write a ledger entry with the breach reason, and escalate per the declared escalation target. It SHALL NOT silently continue or silently abandon. | MUST v1 |
| FR-M4-09 | Parallel fan-out SHALL be permitted only where the Tech Lead Agent has declared work packets non-overlapping at file-path granularity. The runtime SHALL reject a fan-out whose packets share a target path. | MUST v1 |
| FR-M4-10 | The runtime SHALL enforce a global concurrency cap (default 4 concurrent sub-agents, configurable) to bound cost and local resource use. | MUST v1 |
| FR-M4-11 | Every loop iteration SHALL emit at least one ledger entry before the next iteration begins. | MUST v1 |

### M5 — Agent Registry and Manifests

*The agent organisation.*

| ID | Requirement | Priority |
|---|---|---|
| FR-M5-01 | Every agent SHALL be defined by a versioned manifest (schema in §7.1), never by hard-coded source. | MUST v1 |
| FR-M5-02 | The manifest SHALL declare: id, version, kind, tier, role, system policy reference, permitted tools, permitted skills, autonomy tier, budget defaults, escalation target, and probation criteria. | MUST v1 |
| FR-M5-03 | The registry SHALL validate manifests against the schema and reject any agent declaring a tool not present in the workspace policy allow-list. | MUST v1 |
| FR-M5-04 | Agent versions SHALL be immutable. A policy change produces a new version. The ledger records the exact version that acted. | MUST v1 |
| FR-M5-05 | The registry SHALL support agent states: `probation`, `active`, `paused`, `retired`. Only `active` agents may take live work. | MUST v1 |
| FR-M5-06 | Retiring an agent SHALL NOT delete its manifest or its ledger history. | MUST v1 |

### M6 — Skill Loader

*The agent organisation.* The mechanic by which a Developer Agent becomes a Go developer.

| ID | Requirement | Priority |
|---|---|---|
| FR-M6-01 | A Skill Pack SHALL be a folder containing a `SKILL.md` with YAML frontmatter (`name` ≤64 chars, lowercase-hyphenated; `description` ≤1024 chars; optional `allowed-tools`) plus optional scripts and reference files. | MUST v1 |
| FR-M6-02 | The loader SHALL implement three-stage progressive disclosure: **discovery** (name + description only, resident in context), **activation** (full `SKILL.md` loaded on task match), **execution** (bundled files loaded on demand). | MUST v1 |
| FR-M6-03 | Discovery metadata for the entire installed catalogue SHALL consume no more than 3,000 tokens. If exceeded, the loader SHALL warn and require catalogue pruning. | MUST v1 |
| FR-M6-04 | Binding a Skill Pack to a Role Agent SHALL respecialise that agent for the duration of a work packet. | MUST v1 |
| FR-M6-05 | Skill Packs SHALL be pinned by version and content digest. The digest SHALL be recorded in every ledger entry produced under that skill. | MUST v1 |
| FR-M6-06 | On installation of any skill pack from outside the workspace, the loader SHALL present a review UI listing every file, every script, and every external URL referenced, and SHALL require explicit user confirmation. **Skill packs are executable code and a malicious pack can exfiltrate data or execute harmful actions.** | MUST v1 |
| FR-M6-07 | Skill-bundled scripts SHALL execute only in the sandbox defined in `FR-M9-05`, with the tool set constrained by the pack's `allowed-tools` intersected with the agent's permitted tools. | MUST v1 |
| FR-M6-08 | The loader SHALL ship a baseline catalogue: `java-spring-gradle`, `java-fullstack`, `python-service`, `golang-service`, `react-frontend`, `node-service`, `dotnet-service`, `aws-iac`, `sql-migration`, `api-contract-first`. | MUST v1 |
| FR-M6-09 | Reference files SHALL be at most one directory level below `SKILL.md` to keep resolution predictable. | SHOULD v1 |

### M7 — Memory Fabric

*The agent organisation.* Tiered, file-based, layered, human-curatable.

| ID | Requirement | Priority |
|---|---|---|
| FR-M7-01 | Memory SHALL be file-based within `.meridian/memory/` and SHALL be tiered: **procedural** (playbooks, conventions), **semantic** (project facts, entities, embeddings index), **episodic** (per-story trace summaries). | MUST v1 |
| FR-M7-02 | Procedural memory SHALL be human-readable Markdown, reviewable in a pull request, and committed to the repository. | MUST v1 |
| FR-M7-03 | Semantic memory SHALL be a local embedding index over an embedded store, rebuildable from source at any time. Memory SHALL never be the only copy of a fact. | MUST v1 |
| FR-M7-04 | Every memory entry SHALL carry provenance: origin ledger sequence, author agent, timestamp, and confidence. | MUST v1 |
| FR-M7-05 | Memory writeback SHALL be gated: a candidate entry is validated against existing entries for contradiction before commit, and contradictions SHALL surface for human resolution. | MUST v1 |
| FR-M7-06 | The fabric SHALL implement retention: episodic entries older than a configurable horizon (default 90 days) are consolidated into summaries and the raw traces archived. | MUST v1 |
| FR-M7-07 | Content originating from untrusted sources (story text, third-party repo files, dependency documentation) SHALL be tagged as untrusted in memory and SHALL NOT be promoted to procedural memory without human approval. **This is the primary defence against memory poisoning.** | MUST v1 |
| FR-M7-08 | Memory retrieval SHALL be logged: which entries were retrieved into which agent's context, recorded in the ledger entry's input digest. | MUST v1 |
| FR-M7-09 | **Organisation-level memory**: procedural memory SHALL be layerable — organisation → team → repository — with lower layers overriding higher, so house standards propagate without duplication. | MUST v1.x |
| FR-M7-10 | Memory SHALL be **exportable and importable** as a reviewable Markdown bundle, and diffable across versions. | SHOULD v1 |
| FR-M7-11 | **Human-curated memory** SHALL be first-class: a human SHALL be able to author, edit, and pin procedural entries that agents may not modify. | MUST v1 |
| FR-M7-12 | Memory entries SHALL carry a **freshness score** and SHALL be flagged stale when the code they describe has changed since they were written. | SHOULD v1.x |
| FR-M7-13 | Context assembly SHALL be **budgeted and ranked**: each agent invocation declares a context budget and the fabric fills it by relevance, provenance trust, and freshness, logging what was included and what was cut. | MUST v1 |

### M8 — Model Router

*Intelligence & economics.* Token spend is the dominant cost driver; this module is the main lever.

| ID | Requirement | Priority |
|---|---|---|
| FR-M8-01 | The router SHALL support two access paths: direct provider APIs from the sidecar (primary) and the VS Code Language Model API (`vscode.lm`) proxied through the extension (secondary). | MUST v1 |
| FR-M8-02 | Model selection SHALL be policy-driven per phase and per task class, permitting a cheaper model for mechanical tasks and a frontier model for design and review. | MUST v1 |
| FR-M8-03 | The router SHALL enforce per-story, per-phase, and per-agent budgets and SHALL refuse a call that would breach a ceiling, escalating instead. | MUST v1 |
| FR-M8-04 | The router SHALL implement prompt/result caching keyed on the canonicalised request, with cache hits recorded in the ledger. | SHOULD v1 |
| FR-M8-05 | The router SHALL record for every call: model id and version, tokens in/out, latency, cost, and cache status. | MUST v1 |
| FR-M8-06 | The router SHALL implement retry with exponential backoff for transient failures, with retries capped and counted against budget. | MUST v1 |
| FR-M8-07 | Where `vscode.lm` is used, the router SHALL handle `NoPermissions`, `NotFound`, and `Blocked` error conditions distinctly, and SHALL surface consent prompts as user-initiated actions rather than firing at activation. | MUST v1 |
| FR-M8-08 | The router SHALL support provider substitution through configuration without code change. | MUST v1 |
| FR-M8-09 | **Multi-provider failover** with health checks and automatic rerouting, ledger-recorded. | MUST v1.x |
| FR-M8-10 | **Local model support** (Ollama, vLLM, LM Studio, or any OpenAI-compatible endpoint) for air-gapped or data-residency-constrained deployments. | MUST v1.x |
| FR-M8-11 | **PII and secret redaction** of prompts before transmission to any external provider, with a redaction log. | MUST v1 |
| FR-M8-12 | **Data residency** policy: providers SHALL be tagged by region, and policy SHALL be able to restrict which providers a workspace may use. | MUST v1.x |
| FR-M8-13 | Provider **rate-limit backpressure** SHALL pause loops gracefully at a checkpoint rather than failing them. | MUST v1 |
| FR-M8-14 | Structured output enforcement: agent outputs that must be machine-parsed SHALL use schema-constrained generation where the provider supports it, with validation and bounded retry otherwise. | MUST v1 |

### M9 — Tool Layer

*Code & tools.*

| ID | Requirement | Priority |
|---|---|---|
| FR-M9-01 | The sidecar SHALL act as an MCP client, consuming stdio-transport MCP servers configured in workspace settings. | MUST v1 |
| FR-M9-02 | Native tools SHALL be provided for: repository read, patch application, build invocation, test invocation, static analysis invocation, dependency scan, and SCM operations (branch, commit, PR draft). | MUST v1 |
| FR-M9-03 | Every tool invocation SHALL be checked against the calling agent's permitted-tool set before execution. Denials SHALL be logged to the ledger. | MUST v1 |
| FR-M9-04 | Tool results SHALL be size-capped and truncated with an explicit truncation marker rather than silently trimmed. | MUST v1 |
| FR-M9-05 | Build, test, and script execution SHALL run in a constrained environment: a dedicated working directory, a scrubbed environment (no inherited credentials), an egress allow-list, and a wall-clock timeout. | MUST v1 |
| FR-M9-06 | Agent-initiated dependency additions SHALL be flagged as a distinct, separately approvable change class, given supply-chain risk. | MUST v1 |
| FR-M9-07 | The tool layer SHALL never expose raw credentials to agent context. Credentials are injected at the tool boundary and redacted from all logged inputs and outputs. | MUST v1 |
| FR-M9-08 | MCP servers SHALL be pinned by version, and installing a new server SHALL require explicit user confirmation with a trust warning, since local MCP servers execute arbitrary code. | MUST v1 |

### M10 — Ledger Service

*Record & assurance.* Tamper-evident, not tamper-proof. The distinction is normative (`FR-M10-06`).

| ID | Requirement | Priority |
|---|---|---|
| FR-M10-01 | **[AMENDED]** The ledger SHALL be an append-only SQLite store implementing the schema in §7.2. Updates and deletes SHALL be prevented by trigger. **The sole exception is key destruction under `FR-M10-14`, which renders a blob unreadable without deleting any row or breaking the chain.** | MUST v1 |
| FR-M10-02 | Each entry SHALL carry `prev_hash` (the previous entry's `entry_hash`) and `entry_hash` (SHA-256 over a canonical serialisation of the entry payload), forming an unbroken chain from sequence 1. | MUST v1 |
| FR-M10-03 | The ledger SHALL maintain a Merkle tree over entries and SHALL produce **inclusion proofs** and **consistency proofs** on request. | MUST v1 |
| FR-M10-04 | The ledger SHALL emit a signed tree head at a configurable cadence (default: every 100 entries or 10 minutes, whichever first), signed with a key held in the OS keychain. | MUST v1 |
| FR-M10-05 | The ledger SHALL support optional external anchoring of tree heads to a configured timestamp authority or internal transparency service. | SHOULD v1.x |
| FR-M10-06 | Documentation and UI SHALL state plainly that the ledger is **tamper-evident, not tamper-proof** — it detects modification but does not prevent a local user from rewriting the chain unless entries are signed and heads externally anchored. **The product SHALL NOT be described as using a blockchain.** | MUST v1 |
| FR-M10-07 | Large payloads (prompts, outputs, diffs) SHALL be stored content-addressed in `.meridian/ledger/blobs/` with only their digest and reference in the entry row. | MUST v1 |
| FR-M10-08 | Ledger writes SHALL be synchronous with respect to the action they record: an agent action is not considered complete until its entry is committed. | MUST v1 |
| FR-M10-09 | Chain verification SHALL run on sidecar start and on demand, completing in under 5 seconds for 100,000 entries, and SHALL report the first divergent sequence on failure. | MUST v1 |
| FR-M10-10 | The ledger SHALL capture sufficient fields to answer, for any line of agent-authored code: which agent wrote it, at which version, under which skill and model, what it was told, what its stated confidence was, and which human approved it. | MUST v1 |
| FR-M10-11 | **[AMENDED]** Ledger retention SHALL default to no automatic deletion. Where a retention policy is configured it SHALL NOT permit a horizon shorter than six months, consistent with AI Act deployer log-retention expectations. **Subject-scoped erasure under `FR-M10-14` is not deletion and is permitted at any time.** | MUST v1 |
| FR-M10-12 | A **ledger query API** (filter, aggregate, time-range, full-text over blobs) SHALL be exposed to the dashboard, CLI, and external tools. | MUST v1 |
| FR-M10-13 | **Natural-language ledger queries** via the chat participant: "why was the store made database-backed?" resolves to the decision record and its evidence. | SHOULD v1.x |
| FR-M10-14 | **Right-to-erasure compatibility**: personal data in ledger blobs SHALL be encrypted with per-subject keys so that erasure is achievable by key destruction (crypto-shredding) without breaking the hash chain. The erasure event SHALL itself be a ledger entry. | MUST v1.x |
| FR-M10-15 | Ledger **compaction**: blobs older than the retention horizon MAY be archived to cold storage with their digests retained in the chain, so verification still passes. | SHOULD v1.x |
| FR-M10-16 | **Annotations and bookmarks** on entries, by humans, stored as separate signed entries referencing the original. | COULD v2 |
| FR-M10-17 | **Shareable slices**: a ledger range SHALL be exportable as a signed, self-verifying HTML bundle for review by someone without the extension. | SHOULD v1.x |

### M11 — Chain Viewer

*Record & assurance.*

| ID | Requirement | Priority |
|---|---|---|
| FR-M11-01 | The viewer SHALL display a chain integrity banner: verified through sequence N, or a prominent tamper indication naming the first divergent sequence. | MUST v1 |
| FR-M11-02 | The viewer SHALL provide a filterable entry stream by story, agent, phase, loop, action type, and decision. | MUST v1 |
| FR-M11-03 | Selecting an entry SHALL show: the full prompt/context that produced it, the output, the tool calls made, the confidence, the cost, and the resulting diff where applicable. | MUST v1 |
| FR-M11-04 | The viewer SHALL allow inspection of an inclusion proof for any entry and a consistency proof between any two tree heads. | SHOULD v1.x |
| FR-M11-05 | The viewer SHALL support export of a filtered slice as a signed audit bundle (JSON + proofs) for external review. | SHOULD v1.x |

### M12 — Governance and Policy Engine

*Record & assurance.* Policy outranks delivery.

| ID | Requirement | Priority |
|---|---|---|
| FR-M12-01 | Policy SHALL be declarative, versioned, and stored in `.meridian/policy/` under source control. | MUST v1 |
| FR-M12-02 | The engine SHALL implement four autonomy tiers: `suggest`, `approve-each-action`, `approve-per-phase`, `autonomous-within-bounds`. | MUST v1.x |
| FR-M12-03 | Every new agent SHALL start at `suggest`. Promotion SHALL require meeting configured thresholds on first-pass yield, sample size, and confidence calibration for that task class. | MUST v1.x |
| FR-M12-04 | Tier demotion SHALL be automatic on threshold regression, and SHALL be recorded in the ledger. | MUST v1.x |
| FR-M12-05 | **No autonomy tier SHALL permit merge to a protected branch without recorded human approval.** | MUST v1 |
| FR-M12-06 | The Governance engine SHALL be able to halt the Chief Orchestrator and all running loops. Policy outranks delivery. | MUST v1 |
| FR-M12-07 | Every gate decision SHALL record the approving human identity in the ledger. Anonymous approval SHALL NOT be possible. | MUST v1 |
| FR-M12-08 | Policy packs SHALL express: coding standards references, gate criteria, budget ceilings, egress allow-lists, permitted tools, and tier thresholds. | MUST v1 |
| FR-M12-09 | The engine SHALL enforce Definition of Ready and Definition of Done as machine-checkable gate criteria wherever the criterion admits it, with human judgement as the fallback rather than the default. | MUST v1 |
| FR-M12-10 | **Regulatory policy packs** (PCI-DSS, HIPAA, SOC 2, GDPR) SHALL be installable and SHALL add gate criteria, redaction rules, and retention constraints. | SHOULD v1.x |
| FR-M12-11 | **Compliance evidence export**: an audit bundle mapped to ISO/IEC 42001 clauses and EU AI Act Article 12 record-keeping requirements. | SHOULD v1.x |
| FR-M12-12 | Policy changes SHALL be **git-backed** and reviewable via PR, with the ledger recording the commit that activated each policy version. | MUST v1.x |
| FR-M12-13 | **Emergency / hotfix fast path**: a policy-defined reduced gate set for incident response, requiring Governor activation, time-boxed, and prominently marked in the ledger and PR. | SHOULD v1.x |
| FR-M12-14 | **Kill switch per agent class**: policy SHALL be able to disable a class of agent (e.g., all Trainers) organisation-wide. | MUST v1.x |

### M13 — XAI Service

*Record & assurance.* Chain-of-thought is not a faithful account of computation. This module is built around that constraint.

| ID | Requirement | Priority |
|---|---|---|
| FR-M13-01 | Every consequential agent decision SHALL produce a decision record containing: inputs, retrieved memory, tool calls, output, and stated confidence. | MUST v1 |
| FR-M13-02 | Self-reported rationale SHALL be stored and displayed **explicitly labelled as unverified narrative**. The UI SHALL carry this label wherever rationale is shown. | MUST v1 |
| FR-M13-03 | Confidence scores SHALL be recorded at capture and calibration tracked over time; the dashboard SHALL display an agent's historical calibration error alongside any current confidence claim. | MUST v1 |
| FR-M13-04 | The service SHALL support **ablation replay**: re-running a decision with a specified input factor removed, to test whether that factor changed the output. Ablation results SHALL be marked as evidence, in contrast to narrative. | MUST v1 |
| FR-M13-05 | Ablation replay SHALL be mandatory before a gate for decisions classified high blast radius (schema migration, public API contract change, security-relevant change, cross-service change). | MUST v1 |
| FR-M13-06 | The service SHALL produce contribution attribution across agents for a completed story, marked as an estimate. | SHOULD v1.x |
| FR-M13-07 | **No gate SHALL be passable on the basis of an explanation.** Gates are satisfied by tests, scans, and approvals only. | MUST v1 |
| FR-M13-08 | **Counterfactual queries**: "what would have changed if criterion 3 had been present?" via targeted replay from checkpoint. | COULD v2 |
| FR-M13-09 | Calibration SHALL be tracked **per action class** (design, code, test, review), not only per agent, since agents are systematically over-confident in some classes and not others. | SHOULD v1 |
| FR-M13-10 | Every explanation surface SHALL display the **model and model version** that produced the decision, since explanations are not portable across models. | MUST v1 |

### M14 — Trainer Agent

*Learning.* Supervised evolution of prompts, policies and playbooks. Never source code.

| ID | Requirement | Priority |
|---|---|---|
| FR-M14-01 | **[AMENDED]** The Trainer SHALL harvest ledger slices for a target agent and task class from **all six signal sources**: (a) gate approvals and rework with reasons, (b) CI failures (`FR-M23-02`), (c) human PR review comments (`FR-M23-03`), (d) human edits to agent output (`FR-M25-05`), (e) post-merge human corrections (`FR-P9-04`), and (f) production incidents linked to the change (`FR-P9-03`). | MUST v1.x |
| FR-M14-02 | The Trainer SHALL propose deltas to prompts, playbooks, checklists, and skill bindings. It SHALL NOT propose changes to extension or sidecar source code. | MUST v1.x |
| FR-M14-03 | Candidate policies SHALL be evaluated in an isolated workspace against a frozen regression suite plus a replay set of recent real stories. | MUST v1.x |
| FR-M14-04 | A candidate SHALL be promoted only if it (a) beats the incumbent on the evaluation set by a configured margin, and (b) violates no declared safety invariant. | MUST v1.x |
| FR-M14-05 | **Monotonic safety invariant:** a candidate that improves any metric by weakening a security check, a test gate, or an approval requirement SHALL be rejected regardless of score. | MUST v1.x |
| FR-M14-06 | Promotion SHALL require explicit human approval from the Training Queue. The Trainer SHALL NOT self-promote. | MUST v1.x |
| FR-M14-07 | Every promoted policy SHALL be versioned, ledger-recorded with its evaluation evidence, and reversible by a single dashboard action. | MUST v1.x |
| FR-M14-08 | The Trainer SHALL retain the previous N policy versions (default 10) to guarantee rollback. | MUST v1.x |
| FR-M14-09 | The Trainer SHALL run on a schedule or on explicit Train action, never mid-story. | MUST v1.x |
| FR-M14-10 | **Adversarial breaker**: a Breaker Agent SHALL generate failure cases for candidate policies, and a candidate SHALL be evaluated against them before promotion. | SHOULD v1.x |
| FR-M14-11 | **Quality-diversity archive**: the Trainer SHALL maintain a behavioural archive of candidates so that policy evolution does not converge prematurely on one style. | COULD v2 |
| FR-M14-12 | **Cross-team learning** SHALL be opt-in: a team's rework signal SHALL NOT feed another team's Trainer without explicit configuration. | MUST v1.x |
| FR-M14-13 | Trainer evaluation SHALL run the **golden story corpus** (`FR-M27-03`) as part of every regression, so a promoted policy has been proven on real work. | MUST v1.x |

### M15 — Onboarding Agent

*The agent organisation.* New agent roles without redeploying the extension.

| ID | Requirement | Priority |
|---|---|---|
| FR-M15-01 | A new agent role SHALL be addable via manifest and wizard **without redeploying or modifying the extension**. | MUST v1.x |
| FR-M15-02 | The wizard SHALL collect: role, tier, responsibilities, permitted tools, permitted skills, gate ownership, and probation criteria. | MUST v1.x |
| FR-M15-03 | Newly onboarded agents SHALL enter `probation` state and SHALL execute a probation task set with known-good expected outcomes before admission. | MUST v1.x |
| FR-M15-04 | Probation results SHALL be scored and presented for human admission decision. A failing agent SHALL NOT be admitted. | MUST v1.x |
| FR-M15-05 | Admitted agents SHALL enter at the `suggest` autonomy tier regardless of probation score. | MUST v1.x |

### M16 — Replicator (Export / Import)

*The agent organisation.* The honest form of "self-replicating, exportable to other work teams".

| ID | Requirement | Priority |
|---|---|---|
| FR-M16-01 | Export SHALL produce a portable package containing: agent manifest, policy and prompt set, skill bindings and digests, selected procedural memory, evaluation results, and provenance metadata. | MUST v1.x |
| FR-M16-02 | The export package SHALL carry an agent card describing identity, capabilities, and version, and SHALL be signed. | MUST v1.x |
| FR-M16-03 | Export SHALL exclude, by default and irreversibly for the exported artifact: credentials, episodic memory, ledger blobs, and any content tagged untrusted or containing detected secrets. A pre-export scan SHALL enforce this and SHALL block export on detection. | MUST v1.x |
| FR-M16-04 | Import SHALL verify the package signature, present a full diff of what will be introduced, and require explicit confirmation. | MUST v1.x |
| FR-M16-05 | An imported agent SHALL enter `probation` and SHALL run the importing workspace's probation task set before admission. A trained agent from another team is not trusted on arrival. | MUST v1.x |
| FR-M16-06 | Import SHALL be refused where a required skill pack or tool is unavailable in the importing workspace, with a clear statement of what is missing. | MUST v1.x |
| FR-M16-07 | Where cross-organisation agent interoperability is enabled, Meridian Loom SHALL apply its own authorisation policy layer, since current agent interoperability protocols do not natively express authorisation or governance policy. | MUST v1.x |
| FR-M16-08 | An **internal registry** for agent packages and skill packs, with signing, versioning, download counts, and per-package yield telemetry. | SHOULD v1.x |
| FR-M16-09 | Skill pack **upgrade** SHALL run the agents bound to it through regression before the new version becomes active. | MUST v1.x |
| FR-M16-10 | **Retirement handover**: retiring an agent SHALL offer to transfer its procedural memory to a named successor, with the transfer ledger-recorded. | COULD v2 |

### M17 — Telemetry and KPI Service

*Measurement.* Every KPI derives from the ledger. No number in this product is unauditable.

| ID | Requirement | Priority |
|---|---|---|
| FR-M17-01 | The service SHALL compute and expose: first-pass yield, human intervention rate, rework rate (by agent, phase, loop), cost per merged PR, tokens per story (distribution, not mean), time to merge, agent trust score, escaped defect density, and confidence calibration error. | MUST v1 |
| FR-M17-02 | The service SHALL compute DORA four keys plus a rework signal from SCM and CI data where available. | MUST v1.x |
| FR-M17-03 | The dashboard SHALL display throughput and stability **together**, and SHALL raise an explicit warning when throughput rises while change failure rate also rises — the documented AI-adoption failure pattern. | MUST v1.x |
| FR-M17-04 | The service SHALL record measured cycle time independently of any perceived-speed signal, and SHALL report both. | MUST v1 |
| FR-M17-05 | All KPIs SHALL be derivable from the ledger, requiring no separate instrumentation store. | MUST v1 |
| FR-M17-06 | No telemetry SHALL leave the workspace without explicit opt-in. Default is fully local. | MUST v1 |
| FR-M17-07 | **Tech-debt registry**: agents SHALL record debt they encounter or introduce (with justification), and the registry SHALL be queryable and exportable to the issue tracker. | SHOULD v1.x |
| FR-M17-08 | **Agent-vs-human baseline**: for the same task class, yield, cost, and cycle time SHALL be comparable against a human baseline captured before rollout. | SHOULD v1.x |
| FR-M17-09 | **Token efficiency ratio**: useful output tokens per total tokens, per agent and per phase, to expose wasteful loops. | SHOULD v1 |

### M18 — Workspace Isolation and Story Branching

*Work & delivery.* **The resolution of T1.** Without this the product will destroy a human's uncommitted work.

| ID | Requirement | Priority |
|---|---|---|
| FR-M18-01 | Each story SHALL execute in a dedicated **git worktree** under `.meridian/worktrees/<story-id>/`, never in the user's primary working tree. | MUST v1 |
| FR-M18-02 | Story branches SHALL follow a configurable naming convention (default `meridian/<story-id>`), created from a configurable base branch. | MUST v1 |
| FR-M18-03 | The extension SHALL detect when the human has uncommitted changes to a file an agent packet targets and SHALL surface the conflict before the packet starts. | MUST v1 |
| FR-M18-04 | A **story abort** action SHALL remove the worktree, delete the branch if unpushed, release all claims, and leave the primary working tree untouched. The abort SHALL be ledger-recorded. | MUST v1 |
| FR-M18-05 | Agents SHALL commit with a dedicated agent identity (name, email) distinct from the human's, so `git blame` and history attribute authorship correctly. | MUST v1 |
| FR-M18-06 | Agent commits SHOULD be signed (SSH or GPG) with a per-workspace agent key held in SecretStorage, so authorship is non-repudiable. | SHOULD v1.x |
| FR-M18-07 | Commit messages SHALL follow a configurable convention (default Conventional Commits) and SHALL include the ledger sequence range in a trailer (`Meridian-Ledger: 4392-4417`). | MUST v1 |
| FR-M18-08 | The human SHALL be able to open the story worktree in a new VS Code window or check out the story branch into the primary tree on demand. | SHOULD v1 |
| FR-M18-09 | Worktrees SHALL be garbage-collected after merge or abort, with a configurable retention period (default 7 days) for post-mortem. | SHOULD v1.x |

### M19 — Work Item Connectors

*Work & delivery.*

| ID | Requirement | Priority |
|---|---|---|
| FR-M19-01 | First-class connectors SHALL exist for **Jira Cloud, Jira Data Center, Rally, Azure DevOps Boards, and GitHub Issues**, each mapping fields to the story schema (§7.5). Jira Cloud is v1; the rest are v1.x. | MUST v1 (Jira) / v1.x |
| FR-M19-02 | Connectors SHALL support **write-back**: story status transitions, comments summarising phase completion, links to the PR, and a link to the ledger slice. | MUST v1.x |
| FR-M19-03 | Write-back SHALL be opt-in per transition and SHALL never move a story to a Done state without a human approval recorded in the ledger. | MUST v1.x |
| FR-M19-04 | Connectors SHALL ingest attachments and linked pages (Confluence, wiki) as untrusted context, tagged per `FR-M7-07`. | SHOULD v1.x |
| FR-M19-05 | The story schema SHALL support **story templates** per organisation, pre-populating acceptance-criteria structure and required fields. | SHOULD v1.x |
| FR-M19-06 | A story SHALL be classifiable by **complexity tier** (S / M / L / XL) at ingest, using a configurable heuristic, and the tier SHALL select the loop-bound profile and model-tiering policy. | SHOULD v1 |
| FR-M19-07 | Stories SHALL be ingestible in **batch** (an epic's children) with dependency ordering respected. | COULD v2 |

### M20 — Human Identity, Roles and Separation of Duties

*Record & assurance.* **The resolution of T2.** The base document said "human approval" forty times without defining a human.

| ID | Requirement | Priority |
|---|---|---|
| FR-M20-01 | Every human action SHALL be attributed to an authenticated identity (VS Code account, SSO/OIDC, or Git identity), never a free-text name. | MUST v1 |
| FR-M20-02 | The system SHALL define human roles — **Engineer, Reviewer, Approver, Governor, Auditor** — with a policy mapping roles to permitted gate actions. | MUST v1.x |
| FR-M20-03 | **Separation of duties** SHALL be enforceable by policy: the identity that ingested or authored a story SHALL NOT be able to approve its merge gate alone if the policy requires it. | MUST v1.x |
| FR-M20-04 | High-blast-radius gates SHALL support **N-of-M approval** (e.g., two of three Approvers). | SHOULD v1.x |
| FR-M20-05 | Approval **delegation** with expiry SHALL be supported and ledger-recorded. | SHOULD v1.x |
| FR-M20-06 | The system SHALL track **approval latency and depth** per human — time from gate open to decision, and whether the artifact was expanded before approval — and SHALL surface a rubber-stamping warning when approvals are consistently under a configurable threshold. | SHOULD v1.x |
| FR-M20-07 | Only the **Governor** role SHALL be able to change policy, promote autonomy tiers, or promote trainer candidates. | MUST v1.x |
| FR-M20-08 | The **Auditor** role SHALL be read-only across the ledger and SHALL be able to export audit bundles. | SHOULD v1.x |

### M21 — Multi-Story and Portfolio Orchestration

*Work & delivery.*

| ID | Requirement | Priority |
|---|---|---|
| FR-M21-01 | The Chief Orchestrator SHALL manage a **story queue** with priority, WIP limits, and dependency ordering. | MUST v1.x |
| FR-M21-02 | Concurrent stories SHALL be isolated by worktree (M18) and SHALL NOT share in-flight agent instances. | MUST v1.x |
| FR-M21-03 | **Resource contention** across stories — model rate limits, sandbox slots, budget — SHALL be arbitrated by priority, with starvation prevention. | MUST v1.x |
| FR-M21-04 | A **portfolio view** SHALL show every active story's phase, gate state, spend, and predicted completion. | SHOULD v1.x |
| FR-M21-05 | Stories touching overlapping files SHALL be detected at plan time and serialised or flagged for human sequencing. | MUST v1.x |
| FR-M21-06 | **Delivery SLA per story** with slip prediction from loop-iteration trend, surfacing predicted breach before it happens. This is the honest implementation of "on-time delivery". | SHOULD v1.x |

### M22 — Multi-Repository and Cross-Service Changes

*Work & delivery.* **The resolution of T4.** v1 is single-repository; this module makes the vision's polyglot promise real in v1.x.

| ID | Requirement | Priority |
|---|---|---|
| FR-M22-01 | A story SHALL be able to span **multiple repositories** declared in a workspace manifest, each with its own worktree, branch, and PR. | MUST v1.x |
| FR-M22-02 | Cross-repository work packets SHALL declare **interface contracts** (OpenAPI, protobuf, GraphQL schema) that both sides build against, generated by the Architect Agent before implementation. | MUST v1.x |
| FR-M22-03 | Multi-repo PRs SHALL be linked and SHALL merge in dependency order, with the orchestrator waiting on upstream merge before requesting downstream. | SHOULD v1.x |
| FR-M22-04 | Monorepo support: packets SHALL scope to a path prefix and SHALL run only the affected build targets (Bazel / Nx / Gradle composite aware). | SHOULD v1.x |

### M23 — CI/CD and Merge Integration

*Work & delivery.* **The resolution of T5.** The loop ends at merged and green, not at PR opened.

| ID | Requirement | Priority |
|---|---|---|
| FR-M23-01 | The system SHALL integrate with **GitHub Actions, GitLab CI, Azure Pipelines, and Jenkins** to await CI completion and ingest results. GitHub Actions is v1; the rest v1.x. | MUST v1 (GH) / v1.x |
| FR-M23-02 | CI failure SHALL re-enter the L2 Task loop with the failing job's log as feedback, subject to the same bounds. | MUST v1.x |
| FR-M23-03 | **Human review comments on the PR** SHALL be ingested as rework signal, attributed to the reviewer, and fed to the Trainer. | MUST v1.x |
| FR-M23-04 | **CODEOWNERS** SHALL be respected for reviewer assignment; agent PRs SHALL request review from the owning humans. | SHOULD v1.x |
| FR-M23-05 | Merge queue / auto-merge integration, gated on human approval per `FR-M12-05`. | SHOULD v1.x |
| FR-M23-06 | PR descriptions SHALL be generated from a template and SHALL include the fields in `FR-P7-04` plus a **verification checklist** the reviewer can tick. | MUST v1 |

### M24 — Chat Participant and Editor Integration

*Surfaces & output.* VS Code's native surfaces are cheaper than the dashboard and are where engineers already are.

| ID | Requirement | Priority |
|---|---|---|
| FR-M24-01 | A **`@meridian` Chat Participant** SHALL be registered, supporting slash commands: `/ingest`, `/status`, `/explain <seq>`, `/why <file:line>`, `/halt`, `/approve <gate>`, `/steer`. | SHOULD v1 |
| FR-M24-02 | **Hover provenance**: hovering an agent-authored line SHALL show the agent, version, confidence, and ledger sequence, with a link to the entry. | SHOULD v1 |
| FR-M24-03 | **Code actions**: "Ask Meridian to fix", "Ask Meridian to test this", "Explain this change" SHALL be available on selections. | SHOULD v1.x |
| FR-M24-04 | **Git blame decoration** SHALL distinguish agent commits visually and link to the ledger. | SHOULD v1.x |
| FR-M24-05 | Diagnostics (Problems panel) SHALL include agent-detected issues with the originating agent and a quick-fix where one exists. | COULD v2 |
| FR-M24-06 | The Terminal SHALL expose a `meridian` CLI for status, halt, and ledger queries, so the product is scriptable. | SHOULD v1.x |

### M25 — Steering, Clarification and Human-in-the-Loop Refinement

*Work & delivery.* **The resolution of T8 and T11.** Approve/Rework/Escalate/Waive is too coarse an instrument for real collaboration.

| ID | Requirement | Priority |
|---|---|---|
| FR-M25-01 | **Steer**: a human SHALL be able to inject guidance into a running loop without a full rework — the guidance enters the next iteration's context and is ledger-recorded. | MUST v1 |
| FR-M25-02 | **Clarifying-question protocol**: an agent SHALL be able to pause a loop and pose a structured question (with proposed options and its own recommendation) to the human; the loop SHALL resume on answer. | MUST v1 |
| FR-M25-03 | **Uncertainty-triggered escalation**: when stated confidence for an action class falls below a per-class threshold, the agent SHALL ask rather than act. | MUST v1 |
| FR-M25-04 | **Partial acceptance**: a human SHALL be able to accept some hunks and rework others in one action. | SHOULD v1 |
| FR-M25-05 | **Human-edit ingestion**: when a human edits agent-authored code before merge, the diff SHALL be captured as rework signal with reason "human corrected". | MUST v1.x |
| FR-M25-06 | **Dry-run / plan-only mode**: a story SHALL be runnable through Intake, Design, and Plan only, producing the packet graph and cost estimate without implementation. | MUST v1 |
| FR-M25-07 | **Shadow mode**: an agent SHALL be runnable in parallel with a human on the same packet, proposing without applying, so its output can be compared before it is trusted. | SHOULD v1.x |
| FR-M25-08 | Out-of-hours policy: gates opened outside configured hours SHALL queue without notifying, unless the story is flagged urgent. | SHOULD v1.x |

### M26 — Cost Forecasting and Economics

*Intelligence & economics.*

| ID | Requirement | Priority |
|---|---|---|
| FR-M26-01 | At ingest, the system SHALL produce a **cost and duration estimate** with a confidence interval, from story complexity tier and historical ledger data for similar stories. | SHOULD v1 |
| FR-M26-02 | Budget increases mid-story SHALL require approval from an Approver role and SHALL be ledger-recorded with justification. | MUST v1.x |
| FR-M26-03 | Cost SHALL be attributable to **team, project, client, and cost centre** via story metadata, exportable for chargeback. | MUST v1.x |
| FR-M26-04 | The Model Router SHALL support **prompt caching, context compaction, and tool-result summarisation** as configurable cost levers, with their savings reported. | MUST v1 |
| FR-M26-05 | A **model comparison harness** SHALL allow the same golden story to be run against N model configurations and the results compared on yield, cost, and latency. | SHOULD v1.x |
| FR-M26-06 | Effort reporting: per-story human time (gate decisions, steering, rework) SHALL be tracked alongside agent cost, for a true cost-per-change. | SHOULD v1.x |

### M27 — Deterministic Replay and Runtime Testing

*Platform & runtime.* **The resolution of T6.** This is a build enabler, not a feature. Without it the runtime cannot be tested.

| ID | Requirement | Priority |
|---|---|---|
| FR-M27-01 | Every model call and tool result SHALL be recordable to a **replay cassette** keyed by canonical request hash. | MUST v1 |
| FR-M27-02 | A story SHALL be **replayable deterministically** from its cassette with no model calls, producing an identical ledger. | MUST v1 |
| FR-M27-03 | A **golden story corpus** (minimum 20 stories across the supported stacks) SHALL be maintained as the runtime's regression suite, run in CI on every change to the loop runtime, agents, or policies. | MUST v1 |
| FR-M27-04 | **Fault injection**: the runtime SHALL support injected model timeouts, tool failures, sidecar kills, and corrupted ledger entries, to verify checkpoint recovery and chain verification. | MUST v1 |
| FR-M27-05 | Load test: 10 concurrent stories on a reference machine without budget or checkpoint failures. | SHOULD v1.x |

### M28 — Code Intelligence Substrate

*Code & tools.* Agents that edit code need structural understanding, not text manipulation.

| ID | Requirement | Priority |
|---|---|---|
| FR-M28-01 | The Tool Layer SHALL consume **Language Server** diagnostics, symbol resolution, references, and rename refactoring, so agents use the same truth the editor does. | MUST v1 |
| FR-M28-02 | **Tree-sitter** parsing SHALL be available for structural edits, AST-aware diffs, and syntax validation before any file write. | MUST v1 |
| FR-M28-03 | **Semantic code search** over the repository (embedding index, incrementally updated) SHALL be a native tool. | MUST v1 |
| FR-M28-04 | **Reuse-first policy**: before writing a new function or class, the agent SHALL search for existing implementations and SHALL cite what it found or why nothing fit. Duplicate detection SHALL flag re-implementation. | MUST v1 |
| FR-M28-05 | Large-file handling: files above a configurable size SHALL be edited by targeted hunk, never regenerated whole. | MUST v1 |
| FR-M28-06 | Repository indexing SHALL be incremental and SHALL complete initial indexing of a 1M-LOC repository in under 10 minutes on a reference machine. | SHOULD v1 |
| FR-M28-07 | Binary and generated files (lockfiles, build outputs, minified assets) SHALL be excluded from agent editing by default, with an allow-list. | MUST v1 |

### M29 — Documentation and Knowledge Output

*Surfaces & output.* The original brief demanded top coding **and documenting** standards.

| ID | Requirement | Priority |
|---|---|---|
| FR-M29-01 | A **Documentation Agent** SHALL produce or update: API documentation, README sections, inline docs, changelog entries, and runbooks affected by the change. | MUST v1.x |
| FR-M29-02 | Documentation SHALL be a gate criterion: public API changes without updated documentation SHALL block Review. | SHOULD v1.x |
| FR-M29-03 | The story's **journey report** — spec, decisions, packets, tests, gates, cost — SHALL be exportable as Markdown, PDF, and a Confluence page. | SHOULD v1.x |
| FR-M29-04 | ADRs SHALL be enforced: a **fitness function** (ArchUnit-style) SHALL check code against ADR constraints at the Verify gate. | SHOULD v1.x |

### M30 — Runtime Operations and Lifecycle

*Platform & runtime.*

| ID | Requirement | Priority |
|---|---|---|
| FR-M30-01 | `meridian doctor`: a self-diagnostic that checks interpreter, sidecar, keychain, ledger integrity, MCP servers, skill digests, and reports actionable results. | MUST v1 |
| FR-M30-02 | **Backup and restore** of `.meridian/` (ledger, memory, checkpoints, policy) with integrity verification on restore. | MUST v1.x |
| FR-M30-03 | **State migration** across extension versions SHALL be automatic, versioned, and reversible. | MUST v1 |
| FR-M30-04 | Sidecar **auto-update** with signature verification, staged rollout, and rollback. | SHOULD v1.x |
| FR-M30-05 | **Scheduled tasks**: recurring agent work (nightly dependency updates, weekly tech-debt scan) with their own budgets and gates. | COULD v2 |
| FR-M30-06 | **OpenTelemetry export** of runtime traces, metrics, and logs to the organisation's observability stack. | SHOULD v1.x |
| FR-M30-07 | Crash reporting with PII scrubbing, opt-in. | SHOULD v1.x |
| FR-M30-08 | Clean uninstall SHALL remove the sidecar, keychain entries, and optionally `.meridian/`, and SHALL never remove the ledger without explicit confirmation. | MUST v1 |

---

## 6. Agent Requirements by SDLC Phase

### 6.1 Loop bounds (defaults, all policy-overridable, tier-selected per `FR-M19-06`)

| Loop | Max iterations | Token budget | Wall clock | Exit criterion | On bound breach |
|---|---|---|---|---|---|
| **L1 Micro** | 3 | 50k | 5 min | Unit compiles, its tests pass | Surface to L2 with failure trace |
| **L2 Task** | 5 | 300k | 30 min | Reviewer approves and tests green | Escalate work packet to human |
| **L3 Phase** | 3 rework cycles | 800k | 2 h | Exit gate satisfied | Escalate phase with gate diff |
| **L4 Delivery** | — | 2M | 8 h | **[AMENDED]** PR **merged and CI green** (`FR-M23-01/02`) | Chief Orchestrator escalates |
| **L5 Learning** | 1 per cycle | 500k | 1 h | Candidate beats incumbent on regression | Discard candidate, log the attempt |
| **L6 Organisation** | continuous | — | — | — | Governance review |

### 6.2 Phase 1 — Intake and Analysis

| ID | Requirement | Priority |
|---|---|---|
| FR-P1-01 | `IntakeOrchestrator` SHALL accept a story from: a workspace file (e.g. `EDB-12345.txt`), a connector (M19), or direct text entry. | MUST v1 |
| FR-P1-02 | Story content SHALL be tagged **untrusted** on ingest and SHALL be processed under the untrusted-content constraints of §9. | MUST v1 |
| FR-P1-03 | `AnalystAgent` SHALL extract: intent, acceptance criteria, affected applications, constraints, and explicit non-goals. | MUST v1 |
| FR-P1-04 | `AnalystAgent` SHALL produce an **ambiguity register** listing every underspecified point with a proposed resolution and a confidence score. | MUST v1 |
| FR-P1-05 | Ambiguities above a configured severity SHALL be escalated to the human via the clarifying-question protocol (`FR-M25-02`) rather than resolved by assumption. Silent assumption is a defect. | MUST v1 |
| FR-P1-06 | The **Definition of Ready** gate SHALL require: testable acceptance criteria, identified affected services, no unresolved high-severity ambiguity. | MUST v1 |
| FR-P1-07 | The clarified specification SHALL be written to the story worktree as a reviewable artifact, not held only in agent memory. | MUST v1 |

### 6.3 Phase 2 — Architecture and Design

| ID | Requirement | Priority |
|---|---|---|
| FR-P2-01 | `ArchitectAgent` SHALL produce a design covering: component changes, interface contracts, data model changes, and NFR allocation. | MUST v1 |
| FR-P2-02 | Every non-trivial decision SHALL produce an **Architecture Decision Record** written to the repository. | MUST v1 |
| FR-P2-03 | `ArchitectAgent` SHALL classify blast radius (`low`/`medium`/`high`) and SHALL flag schema migrations, public API contract changes, cross-service changes, and security-relevant changes as high. | MUST v1 |
| FR-P2-04 | `SecurityAgent` SHALL produce a threat-surface delta at design time, not only at scan time. | MUST v1 |
| FR-P2-05 | `SREAgent` SHALL declare observability requirements and rollback strategy for the proposed change. | MUST v1 |
| FR-P2-06 | High-blast-radius designs SHALL require human approval before Phase 3 regardless of the agent's autonomy tier. | MUST v1 |

### 6.4 Phase 3 — Planning and Decomposition

| ID | Requirement | Priority |
|---|---|---|
| FR-P3-01 | `TechLeadAgent` SHALL decompose the design into **Work Packets** (schema §7.3). | MUST v1 |
| FR-P3-02 | Each Work Packet SHALL declare: target files/paths, target stack, required skill pack, acceptance tests, dependencies on other packets, and estimated budget. | MUST v1 |
| FR-P3-03 | The packet graph SHALL be validated acyclic, and packets marked parallelisable SHALL be verified non-overlapping at file-path granularity. | MUST v1 |
| FR-P3-04 | `ScrumMasterAgent` SHALL sequence packets and identify the critical path. | MUST v1 |
| FR-P3-05 | The phase exit gate SHALL require every packet to have at least one acceptance test defined before implementation begins. **Tests are contracted before code is written.** | MUST v1 |

### 6.5 Phase 4 — Implementation

| ID | Requirement | Priority |
|---|---|---|
| FR-P4-01 | `BuildOrchestrator` SHALL bind each Work Packet to a `DeveloperAgent` (or `FrontendAgent`) instance carrying the packet's required Skill Pack. | MUST v1 |
| FR-P4-02 | For greenfield work the agent SHALL scaffold per the Skill Pack's project-layout conventions, not from generic templates. | MUST v1 |
| FR-P4-03 | For brownfield work the agent SHALL first analyse existing conventions in the target repository and conform to them where they conflict with Skill Pack defaults. **Repository reality outranks skill defaults.** | MUST v1 |
| FR-P4-04 | Implementation SHALL run the L1 Micro loop: write → compile/lint → run unit tests → repair, bounded per §6.1. | MUST v1 |
| FR-P4-05 | Parallel packets SHALL execute concurrently only when `FR-M4-09` permits. Within a single service's implementation, writes SHALL remain single-threaded. | MUST v1 |
| FR-P4-06 | Every produced diff SHALL be ledger-recorded with the prompt, context, tool calls, and stated confidence that produced it. | MUST v1 |
| FR-P4-07 | The agent SHALL NOT modify files outside its packet's declared target paths. Out-of-scope modification SHALL be blocked and escalated. | MUST v1 |
| FR-P4-08 | Dependency additions SHALL be surfaced as a separately approvable change class per `FR-M9-06`. | MUST v1 |
| FR-P4-09 | The phase exit gate SHALL require: compiles clean, lint clean, unit tests authored and passing, no out-of-scope modification. | MUST v1 |
| FR-P4-10 | **Database migration safety**: migrations SHALL be classified reversible / irreversible; irreversible migrations and any migration touching a table above a configurable row count SHALL be high-blast-radius. | MUST v1 |
| FR-P4-11 | **Feature flag integration**: risky changes SHALL be wrappable in a feature flag (LaunchDarkly, Unleash, or config) by policy, with the flag recorded in the packet. | SHOULD v1.x |
| FR-P4-12 | **License compliance**: agent-added dependencies SHALL be checked against an allowed-license list before the packet exit gate. | MUST v1.x |
| FR-P4-13 | **Contract-first**: for new APIs, the OpenAPI / protobuf / GraphQL contract SHALL be generated and approved before implementation begins. | SHOULD v1.x |

### 6.6 Phase 5 — Verification

| ID | Requirement | Priority |
|---|---|---|
| FR-P5-01 | `QAEngineerAgent` SHALL author tests traceable to specific acceptance criteria. Each criterion SHALL map to at least one test. | MUST v1 |
| FR-P5-02 | Tests SHALL be authored by an agent instance distinct from the one that wrote the implementation. | MUST v1 |
| FR-P5-03 | The agent SHALL verify tests genuinely fail against the pre-change baseline where applicable, to detect vacuous tests. | MUST v1 |
| FR-P5-04 | `QALeadAgent` SHALL produce a **Definition of Done** verdict covering acceptance coverage, regression status, and coverage delta. | MUST v1 |
| FR-P5-05 | A coverage decrease SHALL block the gate unless explicitly waived by a human with a recorded reason. | MUST v1 |
| FR-P5-06 | Regression suites SHALL run against the full affected surface, not only changed files, given documented evidence that agents break previously working code during maintenance work. | MUST v1 |
| FR-P5-07 | **Mutation testing** SHALL be run on agent-authored tests at a configurable sample rate, and a mutation score below threshold SHALL flag the tests as weak. | SHOULD v1.x |
| FR-P5-08 | **Flake quarantine**: tests failing non-deterministically across retries SHALL be quarantined and reported, never silently retried to green. | MUST v1 |
| FR-P5-09 | **Property-based and fuzz test generation** for pure functions and parsers. | COULD v2 |
| FR-P5-10 | **Ephemeral test environments** via Testcontainers or equivalent for integration tests; the agent SHALL NOT be permitted to point tests at shared environments. | MUST v1.x |
| FR-P5-11 | **Contract tests** (consumer-driven) for cross-service packets (M22). | SHOULD v1.x |
| FR-P5-12 | **Performance regression gate**: for packets touching hot paths (declared or detected), a benchmark SHALL run and a regression above threshold SHALL block. | SHOULD v1.x |
| FR-P5-13 | **Accessibility testing** (axe-core or equivalent) SHALL be a gate criterion for front-end packets. | SHOULD v1.x |

### 6.7 Phase 6 — Security and Compliance

| ID | Requirement | Priority |
|---|---|---|
| FR-P6-01 | `SecurityAgent` SHALL run SAST, dependency/SCA scan, and secrets detection over the change. | MUST v1 |
| FR-P6-02 | New high or critical findings SHALL block the gate. Waivers require human approval with a recorded justification. | MUST v1 |
| FR-P6-03 | The agent SHALL produce an SBOM delta for the change. | MUST v1 |
| FR-P6-04 | The agent SHALL specifically check for injected instructions in agent-authored content and for unexpected network egress introduced by the change. | MUST v1 |
| FR-P6-05 | `GovernanceAgent` SHALL verify that all prior gates were satisfied and that no gate was bypassed. Chain integrity SHALL be verified at this gate. | MUST v1 |
| FR-P6-06 | **Threat model artifact** (STRIDE or equivalent) SHALL be produced for changes classified security-relevant, attached to the design gate. | SHOULD v1.x |
| FR-P6-07 | **Privacy impact**: changes touching personal-data fields (detected via schema annotations or name heuristics) SHALL raise a privacy checklist at the design gate. | SHOULD v1.x |
| FR-P6-08 | **AI-BOM**: the SBOM delta SHALL include the models, skill packs, and policies that produced the change. | SHOULD v1.x |
| FR-P6-09 | **Provenance attestation**: agent-authored commits SHALL carry an in-toto / SLSA-style attestation referencing the ledger range, verifiable in CI. | SHOULD v1.x |

### 6.8 Phase 7 — Review and Integration

| ID | Requirement | Priority |
|---|---|---|
| FR-P7-01 | `ReviewerAgent` SHALL critique the change adversarially against the Skill Pack review checklist and the organisation's policy pack. | MUST v1 |
| FR-P7-02 | The reviewer SHALL be a distinct agent instance from both implementer and test author. | MUST v1 |
| FR-P7-03 | Reviewer rejection SHALL re-enter the L2 Task loop with the critique as feedback, not merely surface a comment. | MUST v1 |
| FR-P7-04 | The PR body SHALL be generated to include: the originating story, the agents involved with versions, the gates passed, the ledger sequence range, cost, and a link to the chain viewer slice. | MUST v1 |
| FR-P7-05 | **Human approval SHALL be mandatory before PR merge at every autonomy tier.** | MUST v1 |
| FR-P7-06 | Review turnaround SHALL be measured and reported, since review latency is a dominant driver of delivery performance and agent throughput increases review load. | MUST v1 |
| FR-P7-07 | **Multi-reviewer consensus**: for high-blast-radius changes, N reviewer agents with different policies SHALL critique independently and disagreements SHALL be surfaced, not averaged. | SHOULD v1.x |
| FR-P7-08 | Reviewer agents SHALL check for **secrets, debug artifacts, TODO markers, and commented-out code** as explicit criteria. | MUST v1 |

### 6.9 Phases 8–9 — Release, Operate and Maintain

| ID | Requirement | Priority |
|---|---|---|
| FR-P8-01 | `ReleaseAgent` SHALL produce release notes, version increment, and a deployment plan with an explicit rollback procedure. | MUST v1.x |
| FR-P8-02 | **Deployment execution** (behind a Governor-enabled flag) via the organisation's existing pipeline, never via agent-issued cloud CLI commands. | COULD v2 |
| FR-P9-01 | `SREAgent` SHALL correlate post-deployment SLO movement with the change and feed regressions back to the Trainer as negative signal. | MUST v1.x |
| FR-P9-02 | Escaped defects SHALL be attributed to the originating ledger sequence range where determinable. | MUST v1.x |
| FR-P9-03 | **Incident linkage**: incidents from the organisation's incident system (PagerDuty, ServiceNow) SHALL be linkable to the ledger range of the deployed change, and linked incidents SHALL feed the Trainer as strong negative signal. | SHOULD v1.x |
| FR-P9-04 | **Post-merge human edit tracking**: human commits that modify agent-authored lines within N days of merge SHALL be captured as delayed rework signal. | SHOULD v1.x |

### 6.10 Agent roster

| Agent | Tier | Phase | Introduced | Priority |
|---|---|---|---|---|
| Chief Orchestrator (Delivery Head) | L0 | all | base | MUST v1 |
| Phase Orchestrators (×9) | L1 | one each | base | MUST v1 |
| Analyst | L2 | 1 | base | MUST v1 |
| Architect | L2 | 2 | base | MUST v1 |
| Tech Lead | L2 | 3 | base | MUST v1 |
| Scrum Master | L2 | 3 | base | MUST v1 |
| Developer (skill-bound) | L2/L3 | 4 | base | MUST v1 |
| Front-end Engineer | L2/L3 | 4 | base | MUST v1 |
| QA Engineer | L2 | 5 | base | MUST v1 |
| QA Lead | L2 | 5 | base | MUST v1 |
| Security | L2 | 2, 6 | base | MUST v1 |
| Reviewer | L2 | 7 | base | MUST v1 |
| Release | L2 | 8 | base | MUST v1.x |
| SRE | L2 | 2, 9 | base | MUST v1.x |
| XAI (overlay) | — | all | base | MUST v1 |
| Trainer | meta | — | base | MUST v1.x |
| Onboarding | meta | — | base | MUST v1.x |
| Governance | meta | all | base | MUST v1 |
| Replicator | meta | — | base | MUST v1.x |
| **Documentation** | L2 | 4, 7 | M29 | MUST v1.x |
| **Refactoring** | L2 | 4 | additions | SHOULD v1.x |
| **Legacy Comprehension** | L2 | 1, 2 | additions | SHOULD v1.x |
| **Breaker** | meta | — | `FR-M14-10` | SHOULD v1.x |
| **Performance** | L2 | 5 | `FR-P5-12` | SHOULD v1.x |
| **Dependency** | L2 | 4 | additions | COULD v2 |

The Refactoring Agent operates under strict behaviour-preservation gates: characterisation tests before, equivalence after. The Legacy Comprehension Agent reverse-engineers undocumented modules into procedural memory and ADRs before change — critical for brownfield IT-services work.

---

## 7. Data Models

### 7.1 Agent Manifest

```yaml
id: developer-agent
version: 1.4.0
kind: role                      # orchestrator | role | stack | sub | xai | meta
tier: L2
role: Developer
state: active                   # probation | active | paused | retired
policy_ref: policy/agents/developer.md
policy_version: 1.4.0
permitted_tools: [repo.read, repo.patch, build.invoke, test.invoke, lsp.query, ast.parse, search.semantic]
permitted_skills: [java-spring-gradle, java-fullstack, python-service, golang-service, node-service]
autonomy_tier: approve-per-phase
budgets:
  tokens_per_packet: 300000
  cost_usd_per_packet: 4.00
  wallclock_minutes: 30
  context_tokens: 120000          # FR-M7-13
confidence_thresholds:            # FR-M25-03, per action class
  design: 0.70
  code: 0.60
  test: 0.65
  review: 0.75
escalation_target: build-orchestrator
probation:
  task_set: probation/developer/
  pass_threshold: 0.85
owns_gates: []
```

### 7.2 Ledger Entry

Full DDL in `vision.md` §6.2. Canonicalisation for `entry_hash`: JSON with keys sorted lexicographically, UTF-8, no insignificant whitespace, `prev_hash` and `entry_hash` excluded from the hashed payload, digests hex-encoded lowercase.

Fields added by this merge: `human_role` (M20), `worktree_ref` (M18), `repo_id` (M22), `replay_of` (null for live work, source sequence for a fork, `FR-M4-07`), `blob_key_id` (crypto-shredding, `FR-M10-14`).

### 7.3 Work Packet

```json
{
  "packet_id": "EDB-12345-P03",
  "story_id": "EDB-12345",
  "repo_id": "payments-service",
  "worktree": ".meridian/worktrees/EDB-12345/",
  "branch": "meridian/EDB-12345",
  "title": "Add idempotency key to payment submission endpoint",
  "target_paths": [
    "src/main/java/com/acme/payments/PaymentController.java",
    "src/main/java/com/acme/payments/IdempotencyStore.java"
  ],
  "stack": "java-spring-gradle",
  "required_skill": "java-spring-gradle@2.1.0",
  "acceptance_tests": [
    "Duplicate submission with identical key returns the original result",
    "Distinct keys create distinct payments",
    "Key expiry after configured TTL"
  ],
  "depends_on": ["EDB-12345-P01"],
  "parallelisable": true,
  "blast_radius": "medium",
  "contract_ref": null,
  "feature_flag": null,
  "estimated_tokens": 180000,
  "estimated_cost_usd": 2.70
}
```

### 7.4 Decision Record (XAI)

```json
{
  "ledger_seq": 4417,
  "decision": "Use a database-backed idempotency store rather than in-memory",
  "model": "…", "model_version": "…",
  "action_class": "design",
  "inputs": { "context_digest": "sha256:…", "memory_refs": [1182, 1190],
              "context_included": 41, "context_cut": 12 },
  "reuse_search": { "performed": true, "candidates": ["CacheStore"],
                    "rejected_because": "no TTL semantics" },
  "tool_calls": [ { "tool": "repo.read", "args": "…" } ],
  "stated_confidence": 0.82,
  "threshold_for_class": 0.70,
  "rationale": "…",
  "rationale_label": "UNVERIFIED_NARRATIVE",
  "ablation": {
    "performed": true, "removed_factor": "memory_ref:1190", "output_changed": true,
    "conclusion": "EVIDENCE: retrieved convention record was material to this decision"
  },
  "calibration_context": { "agent_class_calibration_error": 0.11 }
}
```

### 7.5 Story *(new — M19, M21, M26)*

```json
{
  "story_id": "EDB-12345",
  "source": { "connector": "jira-cloud", "key": "EDB-12345", "url": "…" },
  "title": "…", "intent": "…",
  "acceptance_criteria": [ { "id": "AC1", "text": "…", "covered_by": ["testId"] } ],
  "ambiguities": [ { "id": "A1", "text": "…", "proposal": "…", "confidence": 0.6,
                     "state": "escalated" } ],
  "complexity_tier": "M",
  "repos": ["payments-service"],
  "worktrees": { "payments-service": ".meridian/worktrees/EDB-12345/" },
  "priority": 3,
  "sla": { "due": "2026-09-10T17:00:00Z", "predicted": "2026-09-09T11:00:00Z",
           "slip_risk": "low" },
  "budget": { "estimate_usd": 3.10, "interval": [2.10, 5.40],
              "ceiling_usd": 6.00, "spent_usd": 2.18 },
  "attribution": { "team": "payments", "client": "internal", "cost_centre": "ENG-114" },
  "state": "build", "autonomy_profile": "standard"
}
```

### 7.6 Human Identity and Role *(new — M20)*

```json
{
  "identity": "vikram@example.com",
  "source": "oidc",
  "roles": ["Engineer", "Approver"],
  "permitted_gate_actions": ["approve", "rework", "steer", "escalate"],
  "delegations": [ { "to": "…", "scope": "approve", "expires": "…" } ],
  "session": { "authenticated_at": "…", "max_age_hours": 8 },
  "sod_constraints": ["cannot_approve_own_ingested_story"],
  "approval_stats": { "median_seconds_on_artifact": 94, "expansion_rate": 0.81 }
}
```

### 7.7 Replay Cassette *(new — M27)*

```json
{
  "cassette_id": "EDB-12345",
  "recorded_at": "…",
  "runtime_version": "…",
  "entries": [ { "request_hash": "sha256:…", "kind": "model|tool",
                 "provider": "…", "model": "…",
                 "response_digest": "sha256:…", "response_ref": "blobs/…",
                 "tokens_in": 4102, "tokens_out": 811, "latency_ms": 3400 } ],
  "expected_ledger_root": "sha256:…"
}
```

### 7.8 Policy Pack *(new — M12)*

Declarative, git-backed, versioned. Expresses: phase set and gate criteria, DoR/DoD, autonomy tier thresholds, budget ceilings per tier and phase, model routing and residency, egress allow-list, permitted tools per agent kind, role→action mapping, SoD rules, waiver policy, blast-radius rules, retention, and regulatory pack inclusions.

---

## 8. Non-Functional Requirements

| ID | Requirement | Priority |
|---|---|---|
| NFR-01 | Extension activation SHALL complete in under 500 ms. Sidecar startup SHALL NOT block activation. | MUST v1 |
| NFR-02 | Dashboard interactions SHALL respond within 100 ms; loop-state updates SHALL propagate within 1 s. | MUST v1 |
| NFR-03 | Chain verification SHALL complete in under 5 s for 100,000 entries. | MUST v1 |
| NFR-04 | The extension SHALL operate correctly on repositories of at least 1 million lines and 50,000 files. | MUST v1 |
| NFR-05 | Idle memory footprint of the sidecar SHALL not exceed 400 MB. | MUST v1 |
| NFR-06 | A VS Code window reload SHALL lose at most one loop node of work. | MUST v1 |
| NFR-07 | All persistent state SHALL be recoverable from disk; no state SHALL exist only in memory. | MUST v1 |
| NFR-08 | Sidecar crash SHALL not corrupt the ledger; writes SHALL be transactional. | MUST v1 |
| NFR-09 | The extension SHALL function fully offline apart from model API calls. | MUST v1 |
| NFR-10 | Every user-visible error SHALL name a cause and a next action. Bare stack traces SHALL NOT surface to users. | MUST v1 |
| NFR-11 | The published VSIX SHALL be bundled; unbundled multi-thousand-file packages SHALL NOT be published. | MUST v1 |
| NFR-12 | The extension SHALL be distributable through the enterprise Private Marketplace and through manual VSIX installation. | MUST v1.x |
| NFR-13 | All agent-facing prompts, policies, and playbooks SHALL be plain text under source control and diffable in review. | MUST v1 |
| NFR-14 | **Time-to-first-value**: from extension install to a completed dry-run of a sample story in under 15 minutes, with no manual configuration beyond a model credential. | MUST v1 |
| NFR-15 | **Long-running stories**: a story SHALL survive being paused for 30 days and resume with all context intact. | MUST v1.x |
| NFR-16 | **Multi-day human absence**: a gate SHALL remain open indefinitely without resource consumption; the loop is fully unloaded at the checkpoint. | MUST v1 |
| NFR-17 | **Concurrency**: 10 concurrent stories on a reference machine (8 cores, 16 GB) with no checkpoint loss. | MUST v1.x |
| NFR-18 | **Ledger scale**: 1 million entries with verification under 30 seconds and query latency under 200 ms for indexed filters. | MUST v1.x |
| NFR-19 | **Repository scale**: initial index of 1M LOC in under 10 minutes; incremental re-index of a 500-line change in under 2 seconds. | MUST v1 |
| NFR-20 | **Air-gapped operation**: full functionality with a local model provider and no external network, verified in CI. | MUST v1.x |
| NFR-21 | **Localisation**: all user-facing strings externalised; UI SHALL ship with English and be translatable. Agent prompts remain English by default with a per-workspace override. | SHOULD v1.x |
| NFR-22 | **VS Code version compatibility**: a published compatibility matrix, tested against the current stable and the two prior minor releases. | MUST v1 |
| NFR-23 | **Upgrade safety**: an upgrade SHALL never lose a checkpoint, a ledger entry, or a memory entry; verified by the golden corpus before and after. | MUST v1 |

---

## 9. Security Requirements

**Threat model premise.** Meridian Loom by default holds all three legs of the *lethal trifecta* — access to private data, exposure to untrusted content, and an external communication channel. That combination is the documented precondition for exfiltration via prompt injection, and prompt injection has no general fix because models cannot reliably distinguish instruction from data.

| ID | Requirement | Priority |
|---|---|---|
| SEC-01 | All repository content, story text, issue comments, dependency metadata, and third-party documentation SHALL be treated as untrusted input. | MUST v1 |
| SEC-02 | Untrusted content SHALL be delimited in prompts with explicit markers, and agents SHALL be instructed that content inside those markers is data, never instruction. This is mitigation, not a solution, and SHALL NOT be relied upon alone. | MUST v1 |
| SEC-03 | **No single un-gated execution step SHALL simultaneously hold private-data access, untrusted-content processing, and unrestricted egress capability.** Flows SHALL be decomposed so that at most two of the three are present in any un-gated step. | MUST v1 |
| SEC-04 | Network egress from agent-executed processes SHALL be restricted to a configured allow-list: model endpoints, approved package registries, approved internal systems. | MUST v1 |
| SEC-05 | Build, test, and skill-script execution SHALL occur in a sandbox with a scrubbed environment and no inherited credentials. | MUST v1 |
| SEC-06 | Credentials SHALL reside only in OS-keychain-backed SecretStorage and SHALL be injected at the tool boundary, never placed in agent context. | MUST v1 |
| SEC-07 | All logged inputs and outputs SHALL pass a secret-redaction filter before persistence. | MUST v1 |
| SEC-08 | Skill Packs and MCP servers SHALL be reviewed on install, pinned by version and digest, and executed within the sandbox. Their required tools SHALL be declared and enforced. | MUST v1 |
| SEC-09 | Agent-initiated dependency changes SHALL be a distinct approvable class with the resolved version and source registry displayed. | MUST v1 |
| SEC-10 | Each agent SHALL have a scoped identity with a least-privilege tool set. The identity SHALL be recorded in every ledger entry. | MUST v1 |
| SEC-11 | Force-push, history rewrite, protected-branch modification, and credential-file modification SHALL be unconditionally prohibited to all agents at all tiers. | MUST v1 |
| SEC-12 | Export packages SHALL be scanned for secrets and untrusted-tagged content, and export SHALL be blocked on detection. | MUST v1.x |
| SEC-13 | The extension SHALL provide a single **Halt All** action that immediately stops every loop, terminates the sidecar, and leaves the workspace in a consistent state. | MUST v1 |
| SEC-14 | The ledger SHALL record every denied tool invocation, blocked egress attempt, and out-of-scope modification attempt. | MUST v1 |
| SEC-15 | **Prompt-injection classifier**: a lightweight classifier SHALL screen untrusted content before it enters agent context, and detections SHALL be ledger-recorded and surfaced. This complements, and does not replace, SEC-01 to SEC-05. | MUST v1 |
| SEC-16 | **Tool-call anomaly detection**: tool invocations statistically unusual for an agent (new hosts, new paths, unusual volume) SHALL be flagged and, above a threshold, paused for human confirmation. | SHOULD v1.x |
| SEC-17 | **Sandbox escape tests** SHALL be part of the security regression suite. | MUST v1 |
| SEC-18 | **Agent identity keys** SHALL be rotatable, and rotation SHALL be ledger-recorded. | MUST v1.x |
| SEC-19 | **Skill pack revocation**: a skill pack SHALL be revocable organisation-wide, and agents bound to it SHALL be paused until rebound. | MUST v1.x |
| SEC-20 | **Model output scanning**: generated code SHALL be scanned for known-malicious patterns, obfuscation, and embedded credentials before it reaches the working tree. | MUST v1.x |
| SEC-21 | **Data classification awareness**: repositories or paths tagged confidential SHALL be restricted to approved (e.g., local or in-region) model providers. | MUST v1.x |
| SEC-22 | **Human session security**: gate actions SHALL require a recent authentication (configurable, default 8 hours) and SHALL be blocked from an unauthenticated session. | MUST v1.x |
| SEC-23 | **Tenant isolation** for IT-services deployments: client repositories, memory, ledger, and models SHALL be isolatable per client with no cross-tenant memory or training leakage. | MUST v1.x |

---

## 10. Acceptance Criteria

### 10.1 Phase 1 (first value) acceptance

Accepted when, on a designated Java/Spring reference repository:

| # | Criterion |
|---|---|
| AC-01 | A story file placed in the workspace is ingested and produces a clarified specification with an ambiguity register. |
| AC-02 | The Chief Orchestrator drives Intake → Design → Plan → Build → Verify → Review without any manual per-step prompting. |
| AC-03 | Implementation compiles, unit tests are authored and pass, and acceptance criteria are traceably covered. |
| AC-04 | A pull request is opened containing the story reference, agents and versions, gates passed, ledger range, and cost. |
| AC-05 | Every action appears in the ledger; chain verification passes; the viewer answers "which agent wrote this, what was it told, what was its confidence, who approved it" for any changed line. |
| AC-06 | A human rework action re-enters the loop with the reason as feedback and produces a revised output without manual re-prompting. |
| AC-07 | Killing the sidecar mid-loop and reloading the window resumes from checkpoint, losing at most one node of work. |
| AC-08 | No orphaned Python process remains after window close, reload, or extension disable — verified on all three platforms. |
| AC-09 | Swapping the Skill Pack from `java-spring-gradle` to `golang-service` changes the Developer Agent's output conventions accordingly, with no extension change. |
| AC-10 | Measured first-pass yield and cost per merged PR are reported on the dashboard across a run of at least 20 real stories. |
| AC-11 | A prompt-injection payload placed in the story file and in a repository comment does not cause tool invocation outside the agent's permitted set, and the attempt is ledger-recorded. |
| AC-12 | No path exists by which a change reaches a protected branch without a recorded human approval identity. |
| AC-13 | A human edits a file in the primary working tree while an agent packet targets it; the conflict is surfaced before the packet starts, and the human's edit is never lost. |
| AC-14 | A story aborted mid-Build leaves the primary working tree byte-identical to its pre-story state. |
| AC-15 | A story replayed from its cassette produces a byte-identical ledger. |
| AC-16 | The golden story corpus passes in CI with no model calls. |
| AC-17 | A steer injected mid-loop is visible in the next iteration's context and in the ledger. |
| AC-18 | An agent below its confidence threshold asks a structured clarifying question rather than acting, and the loop resumes correctly on answer. |
| AC-19 | The extension operates correctly under VS Code Remote — SSH with the repository on the remote host. |
| AC-20 | A dry-run produces a packet graph and cost estimate without writing a single file. |
| AC-21 | `git blame` on an agent-authored line shows the agent identity and the commit trailer resolves to the correct ledger range. |
| AC-22 | A prompt containing a synthetic credential is transmitted to the model provider with the credential redacted, and the redaction is logged. |

### 10.2 Quality bar for graduating Phase 1

Phase 2 SHALL NOT begin until, over at least 20 real stories: first-pass yield is measured and reported, cost per merged PR is within the agreed ceiling, and change failure rate for agent-authored merges is not worse than the team's pre-Meridian baseline. **Amplifying an unproven core amplifies error.**

---

## 11. Ecosystem Integration

Meridian Loom is one product in a larger programme. Interfaces are declared here even where implementation is later, so that modules do not re-implement what a sibling product already provides.

| ID | Integration | Requirement | Priority |
|---|---|---|---|
| ECO-01 | **Knowledge Brain** | The Memory Fabric SHALL be able to federate semantic memory from the Knowledge Brain graph as a read-only tier, so agents understand systems beyond the current repository. | SHOULD v1.x |
| ECO-02 | **Veritas (evolution engine)** | The Trainer Agent SHALL be implementable as a Veritas client: propose / isolate / apply / evaluate / attribute / promote maps directly onto M14, and the Breaker (`FR-M14-10`), quality-diversity archive (`FR-M14-11`), and Shapley attribution (`FR-M13-06`) are Veritas capabilities. Declare the interface so M14 does not re-implement them. | SHOULD v1.x |
| ECO-03 | **CodeTwin / CodeMap** | The CodeMap Viewer SHALL consume the CodeMap JSON format as its graph source rather than defining a new one. | MUST v1 |
| ECO-04 | **Codeweb / `.cgw`** | Cross-repository graphs (M22) SHALL be addressable by `.cgw` so multi-repo stories share one code graph. | SHOULD v1.x |
| ECO-05 | **ABCD (Agent's Bitbyte Code Depot)** | Where ABCD is the forge, M18 worktrees and M23 PRs SHALL target it natively, and the ledger SHALL be linkable from ABCD's own audit surface. | SHOULD v1.x |
| ECO-06 | **Navion MCP browser** | Available to agents as an MCP tool for documentation retrieval, under the egress allow-list. | COULD v2 |
| ECO-07 | **Epic-to-story upstream** | The autonomous-SDLC ecosystem's epic decomposition produces Jira-ingestible stories; M19 SHALL accept that artifact format directly. | SHOULD v1.x |
| ECO-08 | **teamlore** | Human-curated memory (`FR-M7-11`) SHALL be importable from a teamlore store. | COULD v2 |

---

## 12. Phased Delivery Plan

Engineering phases P0–P4, now mapped to release targets. GUI phases G0–G8 run alongside (`viguix-implementation.md`).

| Phase | Modules | Release | Exit condition |
|---|---|---|---|
| **P0 — Foundation** | M1, M2 (shell), M3 (incl. remote), **M18**, M10 (substrate), **M27** (cassette + fault injection), M30 (doctor, migration, uninstall) | v1 | Extension installs on all platforms and under Remote SSH; sidecar spawns and tears down with zero orphans; ledger writes and verifies; a story worktree is created, used, and aborted cleanly; a trivial story replays deterministically |
| **P1 — First value** | M4, M5, M6 (single skill), M7 (incl. human-curated, budgeted context), M8 (incl. redaction, backpressure, structured output), M9, **M28**, M10, M11, M13, **M20** (identity), **M25**, **M26** (estimate), M17 (core), **M19** (Jira), **M23** (GitHub) + Analyst/Architect/TechLead/Developer/QA/Reviewer | v1 | AC-01 … AC-22 met on the reference repository; §10.2 quality bar cleared |
| **P2 — Quality gates** | M12, Security phase, full skill catalogue, M16 (upgrade/revocation), Phase 5–7 additions | v1.x | Gates block real defects; skill swapping proven across three stacks |
| **P3 — Orchestration & learning** | Phase Orchestrators, sub-agent fan-out, **M14** (all six signal sources), **M21**, **M22**, M29 | v1.x | Trainer demonstrably raises first-pass yield under regression gating, with rollback exercised; a multi-repo story completes |
| **P4 — Portability & compliance** | M15, M16 (full), M17 (full), M24, M30 (full), Release/Operate phases, private-marketplace distribution, ledger anchoring, crypto-shredding, tenant isolation | v1.x | Agent exported and imported across two teams; audit bundle accepted in a compliance review; an erasure request completes with the chain still verifying |
| **P5 — Differentiation** | All v2 items | v2 | — |

### 12.1 v1 addition summary

The additions promoted into v1, without which Phase 1 is either unsafe or untestable:

M18 worktrees · M27 replay and golden corpus · `FR-M3-11` remote · `FR-M20-01` identity · M25 steer/clarify/dry-run · `FR-M7-11`/`FR-M7-13` human memory and budgeted context · M28 code intelligence · `FR-M8-11`/`13`/`14` redaction, backpressure, structured output · `FR-M10-12` query API · `FR-P4-10` migration safety · `FR-P5-08` flake quarantine · `FR-P7-08` reviewer hygiene · `FR-M30-01`/`03`/`08` doctor, migration, uninstall · `ECO-03` CodeMap source · `NFR-14` time-to-first-value.

---

## 13. Risk Register

| # | Risk | Impact | Mitigation |
|---|---|---|---|
| R1 | Prompt injection via story text or repository content | Critical | SEC-01…05, SEC-15; trifecta decomposition; sandbox; egress allow-list; ledger of denied attempts |
| R2 | Orphaned sidecar processes | High | `FR-M3-02`/`03` dual contract; AC-08 tested on all platforms |
| R3 | Cost blowup from loop retries | High | Bounded loops; per-phase and per-story budgets; model tiering; caching; `FR-M26-01` forecast; cost surfaced live |
| R4 | Over-trust — the system feels fast and measures slow | High | `FR-M17-04`; throughput and stability displayed together; `FR-M20-06` rubber-stamp detection |
| R5 | Agents break working code on mature repos | High | `FR-P5-06` full-surface regression; distinct test-author agent; blast-radius gating; `FR-P9-04` delayed rework capture |
| R6 | Multi-agent output that does not compose | High | P3 principle; fan-out only on verified non-overlap; `FR-M22-02` contracts for cross-service |
| R7 | Memory poisoning from untrusted content | High | `FR-M7-07` untrusted tagging; SEC-15 classifier; no promotion without human approval |
| R8 | Ledger over-claimed as tamper-proof | Medium | `FR-M10-06` explicit language; signing and anchoring for stronger claims |
| R9 | Trainer degrades an agent | Medium | Frozen regression suite; monotonic safety invariant; `FR-M14-13` golden corpus; human promotion gate; 10-version rollback |
| R10 | Skill pack supply chain | High | `FR-M6-06` review UI; digest pinning; sandboxed execution; SEC-19 revocation |
| R11 | Python distribution friction across enterprise endpoints | Medium | Platform-specific VSIX targets; interpreter resolution chain; `FR-M30-01` doctor |
| R12 | Reviewer overload from increased agent throughput | Medium | `FR-P7-06` review latency measurement; blast-radius prioritisation; batching by risk class |
| R13 | Model/provider capability or pricing shift | Medium | `FR-M8-08` substitution; `FR-M8-09` failover; `FR-M8-10` local models |
| **R14** | **Agent destroys uncommitted human work** | **Critical** | M18 worktree isolation; `FR-M18-03` conflict detection; AC-13, AC-14 |
| **R15** | **Runtime regressions ship undetected because the runtime cannot be tested offline** | **High** | M27 cassettes and golden corpus; AC-15, AC-16; CI gate on every runtime change |
| **R16** | **Immutable ledger blocks a lawful erasure request** | **High** | `FR-M10-14` crypto-shredding; `FR-M10-01`/`11` amended; erasure itself ledger-recorded |
| **R17** | **Approval becomes rubber-stamping at scale** | **High** | `FR-M20-06` latency and expansion tracking; N-of-M for high blast radius; SoD; blast-radius routing away from batch |
| **R18** | **Setup friction kills adoption before value is seen** | **Medium** | `NFR-14` 15-minute target; `FR-M30-01` doctor; guided first-run |
| **R19** | **Cross-tenant leakage in an IT-services deployment** | **Critical** | SEC-23 tenant isolation; `FR-M14-12` opt-in cross-team learning; `FR-M16-03` export scanning |
| **R20** | **Duplicate implementation accumulates as agents re-write existing code** | **Medium** | `FR-M28-04` reuse-first with citation; duplicate detection; `FR-M17-07` debt registry |

---

## 14. Open Decisions

Decisions that remain genuinely open. Twelve tensions from the additions document are resolved and recorded in §15.

| # | Decision | Owner | Needed by |
|---|---|---|---|
| D1 | Adopt an existing durable graph runtime vs. build a minimal in-house loop runtime | Architecture | Start of P1 |
| D2 | Model routing and tiering policy per phase | Architecture + Finance | Start of P1 |
| D3 | Ledger anchoring: local signing only, internal transparency service, or external timestamp authority | Security + Compliance | P4 |
| D4 | Python distribution: platform-specific VSIX with bundled runtime vs. workspace interpreter | Platform | P0 |
| D5 | Whether the Trainer may propose Skill Pack edits or only policy/prompt deltas | Governance | P3 |
| D6 | Autonomy tier promotion thresholds per task class | Governance | P2 |
| D7 | Whether Phase 8–9 (Release/Operate) execute deployments or only produce plans | Delivery | P4 |
| **D8** | Whether the SDLC phase set is fixed at nine or configurable per organisation. Affects M4, M12, §6, and every phase-indexed GUI surface. | Architecture | Start of P1 |
| **D9** | Identity source of record: VS Code account, corporate SSO/OIDC, or Git identity — and whether more than one is supported simultaneously | Security | P1 |
| **D10** | Golden corpus governance: who curates it, how a story is admitted, and how cassettes are refreshed when a provider changes | Engineering | P0 |
| **D11** | Whether v1 ships the `@meridian` chat participant (`FR-M24-01`) or dashboard-only. Chat is cheap and where engineers are; it also widens the prompt-injection surface | Product + Security | P1 |
| **D12** | Workspace currency and cost display for a globally billing organisation | Finance | P1 |
| **D13** | Whether Meridian owns tenant isolation (SEC-23) or inherits it from the surrounding platform | Architecture | P4 |

---

## 15. Resolved Tensions

The twelve tensions identified in `Requirements-Additions.md` Part I, and how each is resolved in this document. Each resolution is applied to the requirement text, not merely noted.

| # | Tension | Resolution in this document |
|---|---|---|
| T1 | Agents edit the human's working tree | **M18 adopted as v1 MUST.** `FR-M1-05` amended. `P11` added to design principles. AC-13, AC-14 added. R14 added. |
| T2 | "Human approval" has no identity model | **`FR-M20-01` v1 MUST**; full role model (M20) v1.x. §7.6 data model added. D9 opened for the identity source. |
| T3 | Immutable ledger vs. right to erasure | **Crypto-shredding (`FR-M10-14`) v1.x.** `FR-M10-01` and `FR-M10-11` amended with explicit carve-outs. R16 added. |
| T4 | Vision promises polyglot parallelism; spec is single-workspace | **§1.3 now states plainly that v1 is single-repository.** M22 is v1.x. The vision's claim is scoped, not quietly dropped. |
| T5 | The loop ends at "PR opened", not "merged" | **L4 exit criterion amended to "merged and CI green".** M23 adopted; `FR-M23-01` GitHub Actions promoted to v1. |
| T6 | The runtime cannot be tested as specified | **M27 adopted as v1 MUST.** `P13` added to design principles. AC-15, AC-16 added. R15 added. |
| T7 | §1.4 excludes VS Code Web but is silent on Remote | **`FR-M3-11` v1 MUST.** §1.4 rewritten to name SSH, WSL, Dev Containers, and Codespaces explicitly. AC-19 added. |
| T8 | Gate actions are coarse | **M25 adopted in v1** — Steer, clarifying questions, partial acceptance, dry-run. AC-17, AC-20 added. |
| T9 | Memory has no human authorship path | **`FR-M7-11` v1 MUST.** Human-pinned procedural entries are agent-immutable. |
| T10 | Trainer learns only from gate decisions | **`FR-M14-01` amended to enumerate six signal sources.** `P14` added to design principles. |
| T11 | Confidence thresholds exist for tiers but not for actions | **`FR-M25-03` v1 MUST.** Per-action-class thresholds added to the agent manifest (§7.1) and the decision record (§7.4). AC-18 added. |
| T12 | No time-to-first-value target | **`NFR-14` adopted** — 15 minutes, install to completed dry-run. R18 added. |

---

## 16. Changes from v1.0

### 16.1 Amended base requirements

Five base requirements were changed in place. Each is marked **[AMENDED]** at its location.

| ID | Change | Driver |
|---|---|---|
| FR-M1-05 | Added: all workspace edits target the story worktree; no agent edit ever touches the primary tree | T1 |
| FR-M10-01 | Added: crypto-shredding carve-out to the no-delete rule | T3 |
| FR-M10-11 | Added: subject-scoped erasure is not deletion and is permitted at any time | T3 |
| FR-M14-01 | Rewritten: six enumerated signal sources instead of gate decisions alone | T10 |
| §6.1 L4 loop | Exit criterion changed from "PR merged" to "merged and CI green" | T5 |

### 16.2 Amended base sections

§1.2 in-scope list extended · §1.3 rewritten to scope multi-repo out of v1 explicitly · §1.4 rewritten for Remote · §2 glossary gained 10 terms · §3 gained P11–P15 · §4.1 topology gained connector layer, replay recorder, and remote-host annotation · §4.2 storage layout gained `worktrees/` and `cassettes/` · §4.3 module map added · §6.1 loop bounds gained an exit-criterion column · §6.10 agent roster added · §7 gained four data models · §12 delivery plan re-mapped to release targets with a v1 addition summary · §13 gained R14–R20 · §14 gained D8–D13.

### 16.3 Additions carried forward unchanged

13 modules (M18–M30) · 132 module requirements · 20 phase requirements · 10 NFRs · 9 SEC · 10 AC · 8 ECO. Every ID preserved.

### 16.4 Not carried into this document

`Requirements-Additions.md` **Part H** (five recommended enhancements to `vision.md`) is not a requirements matter and belongs in that document. It is retained in the additions file as the record of the recommendation. The five items are: a "where agents write" section, the human organisation alongside the agent organisation, the portfolio layer, the learning loop's full input sources, and an ecosystem diagram.

---

## 17. Requirement Index

| Group | Range | Count |
|---|---|---|
| M1 Extension Host | FR-M1-01 … 10 | 10 |
| M2 Webview Dashboard | FR-M2-01 … 11 | 11 |
| M3 Sidecar & IPC | FR-M3-01 … 13 (+05a) | 14 |
| M4 Loop Runtime | FR-M4-01 … 11 | 11 |
| M5 Agent Registry | FR-M5-01 … 06 | 6 |
| M6 Skill Loader | FR-M6-01 … 09 | 9 |
| M7 Memory Fabric | FR-M7-01 … 13 | 13 |
| M8 Model Router | FR-M8-01 … 14 | 14 |
| M9 Tool Layer | FR-M9-01 … 08 | 8 |
| M10 Ledger | FR-M10-01 … 17 | 17 |
| M11 Chain Viewer | FR-M11-01 … 05 | 5 |
| M12 Governance | FR-M12-01 … 14 | 14 |
| M13 XAI | FR-M13-01 … 10 | 10 |
| M14 Trainer | FR-M14-01 … 13 | 13 |
| M15 Onboarding | FR-M15-01 … 05 | 5 |
| M16 Replicator | FR-M16-01 … 10 | 10 |
| M17 Telemetry | FR-M17-01 … 09 | 9 |
| M18 Workspace Isolation | FR-M18-01 … 09 | 9 |
| M19 Connectors | FR-M19-01 … 07 | 7 |
| M20 Human Identity | FR-M20-01 … 08 | 8 |
| M21 Portfolio | FR-M21-01 … 06 | 6 |
| M22 Multi-Repository | FR-M22-01 … 04 | 4 |
| M23 CI/CD & Merge | FR-M23-01 … 06 | 6 |
| M24 Chat & Editor | FR-M24-01 … 06 | 6 |
| M25 Steering & HITL | FR-M25-01 … 08 | 8 |
| M26 Cost & Economics | FR-M26-01 … 06 | 6 |
| M27 Replay & Testing | FR-M27-01 … 05 | 5 |
| M28 Code Intelligence | FR-M28-01 … 07 | 7 |
| M29 Documentation | FR-M29-01 … 04 | 4 |
| M30 Runtime Operations | FR-M30-01 … 08 | 8 |
| **Module subtotal** | | **283** |
| Phase 1 Intake | FR-P1-01 … 07 | 7 |
| Phase 2 Design | FR-P2-01 … 06 | 6 |
| Phase 3 Plan | FR-P3-01 … 05 | 5 |
| Phase 4 Implementation | FR-P4-01 … 13 | 13 |
| Phase 5 Verification | FR-P5-01 … 13 | 13 |
| Phase 6 Security | FR-P6-01 … 09 | 9 |
| Phase 7 Review | FR-P7-01 … 08 | 8 |
| Phase 8 Release | FR-P8-01 … 02 | 2 |
| Phase 9 Operate | FR-P9-01 … 04 | 4 |
| **Phase subtotal** | | **67** |
| Non-functional | NFR-01 … 23 | 23 |
| Security | SEC-01 … 23 | 23 |
| Acceptance criteria | AC-01 … 22 | 22 |
| Ecosystem | ECO-01 … 08 | 8 |
| Risks | R1 … R20 | 20 |
| Open decisions | D1 … D13 | 13 |
| **Total numbered items** | | **459** |

---

*End of specification. This document supersedes `Requirements.md` v1.0 and `Requirements-Additions.md` v1.0. Both remain valid as the record of how this specification was arrived at.*
