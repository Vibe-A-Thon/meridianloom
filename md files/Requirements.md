# Meridian Loom — Engineering Requirements Specification

| | |
|---|---|
| **Document** | Requirements.md |
| **Version** | 1.0 (Draft for build) |
| **Author** | Ravaleedhar Reddy |
| **Companion documents** | `vision.md` (architecture vision), Executive Plan (`Meridian_Loom_Executive_Plan.docx`) |
| **Deliverable** | `meridian-loom.vsix` — a Visual Studio Code extension |
| **Audience** | Engineers implementing the plugin. This document is written to be built from. |

---

## Table of Contents

1. [Scope and Objectives](#1-scope-and-objectives)
2. [Glossary](#2-glossary)
3. [Design Principles](#3-design-principles)
4. [System Architecture](#4-system-architecture)
5. [Module Requirements M1–M17](#5-module-requirements)
6. [Agent Requirements by SDLC Phase](#6-agent-requirements-by-sdlc-phase)
7. [Data Models](#7-data-models)
8. [Non-Functional Requirements](#8-non-functional-requirements)
9. [Security Requirements](#9-security-requirements)
10. [Acceptance Criteria](#10-acceptance-criteria)
11. [Phased Delivery Plan](#11-phased-delivery-plan)
12. [Risk Register](#12-risk-register)
13. [Open Decisions](#13-open-decisions)

---

## 1. Scope and Objectives

### 1.1 Primary objective

Deliver a VS Code extension that ingests a work item (a Jira story file such as `EDB-12345.txt`, or a connector-fetched issue) and drives it through the software development lifecycle using a hierarchy of AI agents, producing a reviewed pull request, with every agent action recorded in a tamper-evident local ledger and every consequential decision gated by a human.

### 1.2 In scope

- VS Code extension (TypeScript) with React webview dashboard
- Python sidecar hosting the agent runtime and loop engine
- Skill Pack loading, enabling runtime respecialisation of agents by tech stack
- Hash-chained, signed ledger with a chain viewer
- Human-in-the-loop governance: approve, rework, train, onboard, export, pause, retire
- Supervised agent evolution from ledger evidence, under regression gates
- Agent export/import packaging for cross-team portability
- Greenfield scaffolding and brownfield modification for the target stacks

### 1.3 Out of scope (v1)

- Agents modifying their own source code
- Autonomous merge without human approval at any autonomy tier
- Cloud-hosted multi-tenant execution (v1 is workspace-local)
- Production deployment execution (release *planning* is in scope; execution is Phase 4)
- Any claim of guaranteed on-time delivery

### 1.4 Target platforms

Windows x64/arm64, macOS x64/arm64, Linux x64/arm64. VS Code Desktop only — **VS Code Web and vscode.dev are explicitly unsupported in v1** because the architecture requires a local child process.

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

---

## 4. System Architecture

### 4.1 Process topology

```
VS Code Window
│
├── Extension Host (Node.js)          ← meridian-loom extension
│   ├── activation / commands / views
│   ├── Webview Dashboard host (React)
│   ├── Workspace + SCM adapter
│   ├── SecretStorage adapter
│   └── Sidecar Supervisor ──────────┐
│                                     │ JSON-RPC / stdio (framed)
└── Meridian Core (Python 3.11+) ◄───┘
    ├── Loop Runtime (durable, checkpointed)
    ├── Agent Registry + Skill Loader
    ├── Memory Fabric
    ├── Model Router
    ├── Tool Layer (MCP client + native tools)
    ├── Ledger Service (SQLite + blob store)
    └── Governance / Policy Engine
```

### 4.2 Storage layout

```
<workspace>/.meridian/
├── config.json               # workspace configuration (committed)
├── policy/                   # policy packs (committed)
├── skills/                   # workspace-local skill packs (committed)
├── agents/                   # agent manifests (committed)
├── ledger/
│   ├── ledger.db             # SQLite hash-chained log (not committed)
│   └── blobs/                # prompt/output blobs, content-addressed
├── memory/
│   ├── procedural/           # playbooks, conventions (committed)
│   ├── semantic/             # project facts + vector index
│   └── episodic/             # per-story trace summaries
├── checkpoints/              # loop runtime durable state
└── exports/                  # agent export packages
```

`.meridian/ledger`, `.meridian/checkpoints`, and `.meridian/memory/episodic` MUST be added to `.gitignore` on initialisation.

---

## 5. Module Requirements

### M1 — Extension Host

| ID | Requirement | Priority |
|---|---|---|
| FR-M1-01 | The extension SHALL declare granular activation events. It SHALL NOT use `*`. Preferred: `onCommand:*`, `onView:meridianLoom.*`, and `onStartupFinished` where background readiness is required. | MUST |
| FR-M1-02 | The extension SHALL contribute an Activity Bar container with tree views: Agents, Stories, Loops, Skills, Ledger. | MUST |
| FR-M1-03 | The extension SHALL register commands: `meridian.ingestStory`, `meridian.openDashboard`, `meridian.installSkill`, `meridian.onboardAgent`, `meridian.exportAgent`, `meridian.importAgent`, `meridian.verifyChain`, `meridian.haltAll`. | MUST |
| FR-M1-04 | The extension SHALL NOT perform blocking synchronous work exceeding 50 ms on the extension host thread. All orchestration executes in the sidecar. | MUST |
| FR-M1-05 | The extension SHALL apply diffs to the workspace via the VS Code workspace edit API, never by direct filesystem writes, so that undo, file watchers, and dirty-state behave correctly. | MUST |
| FR-M1-06 | The extension SHALL store all model credentials in `context.secrets` (SecretStorage). Credentials SHALL NOT be written to settings, workspace files, or logs. | MUST |
| FR-M1-07 | The extension SHALL detect SecretStorage unavailability (notably Linux without a keyring backend) and refuse to start rather than falling back to plaintext storage. | MUST |
| FR-M1-08 | The extension SHALL expose read-only workspace context (open files, selection, SCM branch, diagnostics) to the sidecar over the RPC channel on request. | SHOULD |
| FR-M1-09 | The extension SHALL surface all long-running work through `withProgress` with a cancellation token wired to sidecar loop cancellation. | MUST |
| FR-M1-10 | The extension SHALL be bundled with esbuild via `vscode:prepublish`, with `vscode` marked external and a `.vscodeignore` excluding sources, tests, and dev assets. | MUST |

### M2 — Webview Dashboard

| ID | Requirement | Priority |
|---|---|---|
| FR-M2-01 | The dashboard SHALL be a React application hosted in a VS Code webview. | MUST |
| FR-M2-02 | Every webview SHALL set a Content Security Policy of the form `default-src 'none'; script-src 'nonce-<n>'; style-src ${webview.cspSource}; img-src ${webview.cspSource} data:; font-src ${webview.cspSource}`. Inline scripts without a nonce SHALL NOT be used. | MUST |
| FR-M2-03 | All local resources SHALL be loaded via `Webview.asWebviewUri()` with directories declared in `localResourceRoots`. | MUST |
| FR-M2-04 | The dashboard SHALL persist UI state via `getState()`/`setState()` and restore through a registered `WebviewPanelSerializer`. It SHALL NOT rely on `retainContextWhenHidden` for correctness. | MUST |
| FR-M2-05 | All extension↔webview messages SHALL pass through a single typed message bus with a discriminated-union message contract and a schema version field. | MUST |
| FR-M2-06 | The dashboard SHALL theme entirely from VS Code CSS custom properties (`--vscode-*`) and SHALL render correctly in light, dark, and high-contrast themes. | MUST |
| FR-M2-07 | The dashboard SHALL provide these views: Agent Roster, Loop Graph, Story Board, Chain Viewer, Training Queue, Skill Catalogue, Cost & KPI panel. | MUST |
| FR-M2-08 | The Loop Graph SHALL render live loop state (open loops, current iteration, budget consumed, distance to escalation) with sub-second update latency, using a client-side graph library operating within the CSP sandbox. | MUST |
| FR-M2-09 | The dashboard SHALL degrade gracefully when the sidecar is unavailable, showing last-known state marked stale rather than an empty or erroring view. | MUST |
| FR-M2-10 | The dashboard SHALL meet WCAG 2.1 AA for contrast, keyboard navigation, and focus order. | SHOULD |
| FR-M2-11 | Any agent-produced text rendered in the dashboard SHALL be escaped. Markdown rendering SHALL sanitise HTML and strip scripts and event handlers. | MUST |

### M3 — Sidecar and IPC

| ID | Requirement | Priority |
|---|---|---|
| FR-M3-01 | The extension SHALL spawn Meridian Core as a child process and communicate over framed JSON-RPC 2.0 on stdio. | MUST |
| FR-M3-02 | The Sidecar Supervisor SHALL terminate the child process in `deactivate()`, on webview disposal where it is the last consumer, and on extension deactivation for any reason. | MUST |
| FR-M3-03 | Meridian Core SHALL independently monitor for parent-process death and self-terminate within 10 seconds if orphaned. **Orphaned sidecars are a documented failure mode in shipping agent extensions; both halves of this contract are mandatory.** | MUST |
| FR-M3-04 | The Supervisor SHALL handle the `error` event on spawn distinctly from a non-zero exit, and SHALL produce actionable diagnostics for `ENOENT` (interpreter not found), `EACCES`, and policy-blocked execution. | MUST |
| FR-M3-05 | Python interpreter resolution SHALL follow this order: (1) `meridian.python.interpreterPath` setting, (2) the VS Code Python extension's environment API if present, (3) a bundled runtime if shipped, (4) `python3`/`python` on PATH. The resolved path SHALL be shown in the status bar. | MUST |
| FR-M3-05a | Where a bundled runtime is shipped, the extension SHALL be published as **platform-specific VSIX targets** (`--target win32-x64`, `darwin-arm64`, `linux-x64`, …) rather than a single universal package. | MUST |
| FR-M3-06 | The Supervisor SHALL implement health checks (heartbeat every 5 s) and SHALL restart the sidecar at most 3 times in 5 minutes before entering a failed state requiring user action. | MUST |
| FR-M3-07 | On sidecar restart, in-flight loops SHALL resume from their last durable checkpoint, not from the beginning. | MUST |
| FR-M3-08 | The RPC contract SHALL be versioned. On version mismatch the extension SHALL refuse to proceed and prompt the user to reinstall rather than operating with an incompatible core. | MUST |
| FR-M3-09 | Sidecar stdout SHALL carry only framed RPC. All logging SHALL go to stderr and a rotating log file, never to stdout. | MUST |
| FR-M3-10 | The sidecar SHALL bind no network listener by default. If a local HTTP/WS transport is enabled for debugging, it SHALL bind to loopback only with a per-session bearer token. | MUST |

### M4 — Loop Runtime

| ID | Requirement | Priority |
|---|---|---|
| FR-M4-01 | The Loop Runtime SHALL execute a directed graph of agent invocations supporting cycles. | MUST |
| FR-M4-02 | Every loop definition SHALL declare: entry condition, body graph, exit criteria, max iterations, token budget, wall-clock budget, cost ceiling, escalation target. A loop missing any field SHALL fail validation at load time and SHALL NOT execute. | MUST |
| FR-M4-03 | The runtime SHALL implement the six canonical loops (L1 Micro, L2 Task, L3 Phase, L4 Delivery, L5 Learning, L6 Organisation) with the default bounds specified in §6.1. | MUST |
| FR-M4-04 | State SHALL be typed, and concurrent updates from parallel branches SHALL merge through declared reducers. Silent last-write-wins is prohibited. | MUST |
| FR-M4-05 | The runtime SHALL checkpoint durably after every node execution, such that a process kill loses at most one node's work. | MUST |
| FR-M4-06 | The runtime SHALL support interrupt/resume for human gates: a loop suspends at a gate, persists, releases resources, and resumes on a dashboard action. | MUST |
| FR-M4-07 | The runtime SHALL support time-travel: replaying a loop from any checkpoint with modified state, for debugging and ablation. | SHOULD |
| FR-M4-08 | On any bound breach the runtime SHALL halt the loop, write a ledger entry with the breach reason, and escalate per the declared escalation target. It SHALL NOT silently continue or silently abandon. | MUST |
| FR-M4-09 | Parallel fan-out SHALL be permitted only where the Tech Lead Agent has declared work packets non-overlapping at file-path granularity. The runtime SHALL reject a fan-out whose packets share a target path. | MUST |
| FR-M4-10 | The runtime SHALL enforce a global concurrency cap (default 4 concurrent sub-agents, configurable) to bound cost and local resource use. | MUST |
| FR-M4-11 | Every loop iteration SHALL emit at least one ledger entry before the next iteration begins. | MUST |

### M5 — Agent Registry and Manifests

| ID | Requirement | Priority |
|---|---|---|
| FR-M5-01 | Every agent SHALL be defined by a versioned manifest (schema in §7.1), never by hard-coded source. | MUST |
| FR-M5-02 | The manifest SHALL declare: id, version, kind, tier, role, system policy reference, permitted tools, permitted skills, autonomy tier, budget defaults, escalation target, and probation criteria. | MUST |
| FR-M5-03 | The registry SHALL validate manifests against the schema and reject any agent declaring a tool not present in the workspace policy allow-list. | MUST |
| FR-M5-04 | Agent versions SHALL be immutable. A policy change produces a new version. The ledger records the exact version that acted. | MUST |
| FR-M5-05 | The registry SHALL support agent states: `probation`, `active`, `paused`, `retired`. Only `active` agents may take live work. | MUST |
| FR-M5-06 | Retiring an agent SHALL NOT delete its manifest or its ledger history. | MUST |

### M6 — Skill Loader

| ID | Requirement | Priority |
|---|---|---|
| FR-M6-01 | A Skill Pack SHALL be a folder containing a `SKILL.md` with YAML frontmatter (`name` ≤64 chars, lowercase-hyphenated; `description` ≤1024 chars; optional `allowed-tools`) plus optional scripts and reference files. | MUST |
| FR-M6-02 | The loader SHALL implement three-stage progressive disclosure: **discovery** (name + description only, resident in context), **activation** (full `SKILL.md` loaded on task match), **execution** (bundled files loaded on demand). | MUST |
| FR-M6-03 | Discovery metadata for the entire installed catalogue SHALL consume no more than 3,000 tokens. If exceeded, the loader SHALL warn and require catalogue pruning. | MUST |
| FR-M6-04 | Binding a Skill Pack to a Role Agent SHALL respecialise that agent for the duration of a work packet — the mechanic by which a Developer Agent becomes a Go developer or a Java full-stack engineer. | MUST |
| FR-M6-05 | Skill Packs SHALL be pinned by version and content digest. The digest SHALL be recorded in every ledger entry produced under that skill. | MUST |
| FR-M6-06 | On installation of any skill pack from outside the workspace, the loader SHALL present a review UI listing every file, every script, and every external URL referenced, and SHALL require explicit user confirmation. **Skill packs are executable code and a malicious pack can exfiltrate data or execute harmful actions.** | MUST |
| FR-M6-07 | Skill-bundled scripts SHALL execute only in the sandbox defined in FR-M9-05, with the tool set constrained by the pack's `allowed-tools` intersected with the agent's permitted tools. | MUST |
| FR-M6-08 | The loader SHALL ship a baseline catalogue: `java-spring-gradle`, `java-fullstack`, `python-service`, `golang-service`, `react-frontend`, `node-service`, `dotnet-service`, `aws-iac`, `sql-migration`, `api-contract-first`. | MUST |
| FR-M6-09 | Reference files SHALL be at most one directory level below `SKILL.md` to keep resolution predictable. | SHOULD |

### M7 — Memory Fabric

| ID | Requirement | Priority |
|---|---|---|
| FR-M7-01 | Memory SHALL be file-based within `.meridian/memory/` and SHALL be tiered: **procedural** (playbooks, conventions), **semantic** (project facts, entities, embeddings index), **episodic** (per-story trace summaries). | MUST |
| FR-M7-02 | Procedural memory SHALL be human-readable Markdown, reviewable in a pull request, and committed to the repository. | MUST |
| FR-M7-03 | Semantic memory SHALL be a local embedding index over an embedded store, rebuildable from source at any time. Memory SHALL never be the only copy of a fact. | MUST |
| FR-M7-04 | Every memory entry SHALL carry provenance: origin ledger sequence, author agent, timestamp, and confidence. | MUST |
| FR-M7-05 | Memory writeback SHALL be gated: a candidate entry is validated against existing entries for contradiction before commit, and contradictions SHALL surface for human resolution. | MUST |
| FR-M7-06 | The fabric SHALL implement retention: episodic entries older than a configurable horizon (default 90 days) are consolidated into summaries and the raw traces archived. | MUST |
| FR-M7-07 | Content originating from untrusted sources (story text, third-party repo files, dependency documentation) SHALL be tagged as untrusted in memory and SHALL NOT be promoted to procedural memory without human approval. **This is the primary defence against memory poisoning.** | MUST |
| FR-M7-08 | Memory retrieval SHALL be logged: which entries were retrieved into which agent's context, recorded in the ledger entry's input digest. | MUST |

### M8 — Model Router

| ID | Requirement | Priority |
|---|---|---|
| FR-M8-01 | The router SHALL support two access paths: direct provider APIs from the sidecar (primary) and the VS Code Language Model API (`vscode.lm`) proxied through the extension (secondary). | MUST |
| FR-M8-02 | Model selection SHALL be policy-driven per phase and per task class, permitting a cheaper model for mechanical tasks and a frontier model for design and review. | MUST |
| FR-M8-03 | The router SHALL enforce per-story, per-phase, and per-agent budgets and SHALL refuse a call that would breach a ceiling, escalating instead. | MUST |
| FR-M8-04 | The router SHALL implement prompt/result caching keyed on the canonicalised request, with cache hits recorded in the ledger. | SHOULD |
| FR-M8-05 | The router SHALL record for every call: model id and version, tokens in/out, latency, cost, and cache status. | MUST |
| FR-M8-06 | The router SHALL implement retry with exponential backoff for transient failures, with retries capped and counted against budget. | MUST |
| FR-M8-07 | Where `vscode.lm` is used, the router SHALL handle `NoPermissions`, `NotFound`, and `Blocked` error conditions distinctly, and SHALL surface consent prompts as user-initiated actions rather than firing at activation. | MUST |
| FR-M8-08 | The router SHALL support provider substitution through configuration without code change. | MUST |

### M9 — Tool Layer

| ID | Requirement | Priority |
|---|---|---|
| FR-M9-01 | The sidecar SHALL act as an MCP client, consuming stdio-transport MCP servers configured in workspace settings. | MUST |
| FR-M9-02 | Native tools SHALL be provided for: repository read, patch application, build invocation, test invocation, static analysis invocation, dependency scan, and SCM operations (branch, commit, PR draft). | MUST |
| FR-M9-03 | Every tool invocation SHALL be checked against the calling agent's permitted-tool set before execution. Denials SHALL be logged to the ledger. | MUST |
| FR-M9-04 | Tool results SHALL be size-capped and truncated with an explicit truncation marker rather than silently trimmed. | MUST |
| FR-M9-05 | Build, test, and script execution SHALL run in a constrained environment: a dedicated working directory, a scrubbed environment (no inherited credentials), an egress allow-list, and a wall-clock timeout. | MUST |
| FR-M9-06 | Agent-initiated dependency additions SHALL be flagged as a distinct, separately approvable change class, given supply-chain risk. | MUST |
| FR-M9-07 | The tool layer SHALL never expose raw credentials to agent context. Credentials are injected at the tool boundary and redacted from all logged inputs and outputs. | MUST |
| FR-M9-08 | MCP servers SHALL be pinned by version, and installing a new server SHALL require explicit user confirmation with a trust warning, since local MCP servers execute arbitrary code. | MUST |

### M10 — Ledger Service

| ID | Requirement | Priority |
|---|---|---|
| FR-M10-01 | The ledger SHALL be an append-only SQLite store implementing the schema in §7.2. Updates and deletes SHALL be prevented by trigger. | MUST |
| FR-M10-02 | Each entry SHALL carry `prev_hash` (the previous entry's `entry_hash`) and `entry_hash` (SHA-256 over a canonical serialisation of the entry payload), forming an unbroken chain from sequence 1. | MUST |
| FR-M10-03 | The ledger SHALL maintain a Merkle tree over entries and SHALL produce **inclusion proofs** and **consistency proofs** on request. | MUST |
| FR-M10-04 | The ledger SHALL emit a signed tree head at a configurable cadence (default: every 100 entries or 10 minutes, whichever first), signed with a key held in the OS keychain. | MUST |
| FR-M10-05 | The ledger SHALL support optional external anchoring of tree heads to a configured timestamp authority or internal transparency service. | SHOULD |
| FR-M10-06 | Documentation and UI SHALL state plainly that the ledger is **tamper-evident, not tamper-proof** — it detects modification but does not prevent a local user from rewriting the chain unless entries are signed and heads externally anchored. **The product SHALL NOT be described as using a blockchain.** | MUST |
| FR-M10-07 | Large payloads (prompts, outputs, diffs) SHALL be stored content-addressed in `.meridian/ledger/blobs/` with only their digest and reference in the entry row. | MUST |
| FR-M10-08 | Ledger writes SHALL be synchronous with respect to the action they record: an agent action is not considered complete until its entry is committed. | MUST |
| FR-M10-09 | Chain verification SHALL run on sidecar start and on demand, completing in under 5 seconds for 100,000 entries, and SHALL report the first divergent sequence on failure. | MUST |
| FR-M10-10 | The ledger SHALL capture sufficient fields to answer, for any line of agent-authored code: which agent wrote it, at which version, under which skill and model, what it was told, what its stated confidence was, and which human approved it. | MUST |
| FR-M10-11 | Ledger retention SHALL default to no automatic deletion. Where a retention policy is configured it SHALL NOT permit a horizon shorter than six months, consistent with AI Act deployer log-retention expectations. | MUST |

### M11 — Chain Viewer

| ID | Requirement | Priority |
|---|---|---|
| FR-M11-01 | The viewer SHALL display a chain integrity banner: verified through sequence N, or a prominent tamper indication naming the first divergent sequence. | MUST |
| FR-M11-02 | The viewer SHALL provide a filterable entry stream by story, agent, phase, loop, action type, and decision. | MUST |
| FR-M11-03 | Selecting an entry SHALL show: the full prompt/context that produced it, the output, the tool calls made, the confidence, the cost, and the resulting diff where applicable. | MUST |
| FR-M11-04 | The viewer SHALL allow inspection of an inclusion proof for any entry and a consistency proof between any two tree heads. | SHOULD |
| FR-M11-05 | The viewer SHALL support export of a filtered slice as a signed audit bundle (JSON + proofs) for external review. | SHOULD |

### M12 — Governance and Policy Engine

| ID | Requirement | Priority |
|---|---|---|
| FR-M12-01 | Policy SHALL be declarative, versioned, and stored in `.meridian/policy/` under source control. | MUST |
| FR-M12-02 | The engine SHALL implement four autonomy tiers: `suggest`, `approve-each-action`, `approve-per-phase`, `autonomous-within-bounds`. | MUST |
| FR-M12-03 | Every new agent SHALL start at `suggest`. Promotion SHALL require meeting configured thresholds on first-pass yield, sample size, and confidence calibration for that task class. | MUST |
| FR-M12-04 | Tier demotion SHALL be automatic on threshold regression, and SHALL be recorded in the ledger. | MUST |
| FR-M12-05 | **No autonomy tier SHALL permit merge to a protected branch without recorded human approval.** | MUST |
| FR-M12-06 | The Governance engine SHALL be able to halt the Chief Orchestrator and all running loops. Policy outranks delivery. | MUST |
| FR-M12-07 | Every gate decision SHALL record the approving human identity in the ledger. Anonymous approval SHALL NOT be possible. | MUST |
| FR-M12-08 | Policy packs SHALL express: coding standards references, gate criteria, budget ceilings, egress allow-lists, permitted tools, and tier thresholds. | MUST |
| FR-M12-09 | The engine SHALL enforce Definition of Ready and Definition of Done as machine-checkable gate criteria wherever the criterion admits it, with human judgement as the fallback rather than the default. | MUST |

### M13 — XAI Service

| ID | Requirement | Priority |
|---|---|---|
| FR-M13-01 | Every consequential agent decision SHALL produce a decision record containing: inputs, retrieved memory, tool calls, output, and stated confidence. | MUST |
| FR-M13-02 | Self-reported rationale SHALL be stored and displayed **explicitly labelled as unverified narrative**. The UI SHALL carry this label wherever rationale is shown. **Chain-of-thought is documented not to be a faithful account of a model's actual computation.** | MUST |
| FR-M13-03 | Confidence scores SHALL be recorded at capture and calibration tracked over time; the dashboard SHALL display an agent's historical calibration error alongside any current confidence claim. | MUST |
| FR-M13-04 | The service SHALL support **ablation replay**: re-running a decision with a specified input factor removed, to test whether that factor changed the output. Ablation results SHALL be marked as evidence, in contrast to narrative. | MUST |
| FR-M13-05 | Ablation replay SHALL be mandatory before a gate for decisions classified high blast radius (schema migration, public API contract change, security-relevant change, cross-service change). | MUST |
| FR-M13-06 | The service SHALL produce contribution attribution across agents for a completed story, marked as an estimate. | SHOULD |
| FR-M13-07 | **No gate SHALL be passable on the basis of an explanation.** Gates are satisfied by tests, scans, and approvals only. | MUST |

### M14 — Trainer Agent

| ID | Requirement | Priority |
|---|---|---|
| FR-M14-01 | The Trainer SHALL harvest ledger slices of approved vs. reworked outputs, including rework reasons, for a target agent and task class. | MUST |
| FR-M14-02 | The Trainer SHALL propose deltas to prompts, playbooks, checklists, and skill bindings. It SHALL NOT propose changes to extension or sidecar source code. | MUST |
| FR-M14-03 | Candidate policies SHALL be evaluated in an isolated workspace against a frozen regression suite plus a replay set of recent real stories. | MUST |
| FR-M14-04 | A candidate SHALL be promoted only if it (a) beats the incumbent on the evaluation set by a configured margin, and (b) violates no declared safety invariant. | MUST |
| FR-M14-05 | **Monotonic safety invariant:** a candidate that improves any metric by weakening a security check, a test gate, or an approval requirement SHALL be rejected regardless of score. | MUST |
| FR-M14-06 | Promotion SHALL require explicit human approval from the Training Queue. The Trainer SHALL NOT self-promote. | MUST |
| FR-M14-07 | Every promoted policy SHALL be versioned, ledger-recorded with its evaluation evidence, and reversible by a single dashboard action. | MUST |
| FR-M14-08 | The Trainer SHALL retain the previous N policy versions (default 10) to guarantee rollback. | MUST |
| FR-M14-09 | The Trainer SHALL run on a schedule or on explicit Train action, never mid-story. | MUST |

### M15 — Onboarding Agent

| ID | Requirement | Priority |
|---|---|---|
| FR-M15-01 | A new agent role SHALL be addable via manifest and wizard **without redeploying or modifying the extension**. | MUST |
| FR-M15-02 | The wizard SHALL collect: role, tier, responsibilities, permitted tools, permitted skills, gate ownership, and probation criteria. | MUST |
| FR-M15-03 | Newly onboarded agents SHALL enter `probation` state and SHALL execute a probation task set with known-good expected outcomes before admission. | MUST |
| FR-M15-04 | Probation results SHALL be scored and presented for human admission decision. A failing agent SHALL NOT be admitted. | MUST |
| FR-M15-05 | Admitted agents SHALL enter at the `suggest` autonomy tier regardless of probation score. | MUST |

### M16 — Replicator (Export / Import)

| ID | Requirement | Priority |
|---|---|---|
| FR-M16-01 | Export SHALL produce a portable package containing: agent manifest, policy and prompt set, skill bindings and digests, selected procedural memory, evaluation results, and provenance metadata. | MUST |
| FR-M16-02 | The export package SHALL carry an agent card describing identity, capabilities, and version, and SHALL be signed. | MUST |
| FR-M16-03 | Export SHALL exclude, by default and irreversibly for the exported artifact: credentials, episodic memory, ledger blobs, and any content tagged untrusted or containing detected secrets. A pre-export scan SHALL enforce this and SHALL block export on detection. | MUST |
| FR-M16-04 | Import SHALL verify the package signature, present a full diff of what will be introduced, and require explicit confirmation. | MUST |
| FR-M16-05 | An imported agent SHALL enter `probation` and SHALL run the importing workspace's probation task set before admission. A trained agent from another team is not trusted on arrival. | MUST |
| FR-M16-06 | Import SHALL be refused where a required skill pack or tool is unavailable in the importing workspace, with a clear statement of what is missing. | MUST |
| FR-M16-07 | Where cross-organisation agent interoperability is enabled, Meridian Loom SHALL apply its own authorisation policy layer, since current agent interoperability protocols do not natively express authorisation or governance policy. | MUST |

### M17 — Telemetry and KPI Service

| ID | Requirement | Priority |
|---|---|---|
| FR-M17-01 | The service SHALL compute and expose: first-pass yield, human intervention rate, rework rate (by agent, phase, loop), cost per merged PR, tokens per story (distribution, not mean), time to merge, agent trust score, escaped defect density, and confidence calibration error. | MUST |
| FR-M17-02 | The service SHALL compute DORA four keys plus a rework signal from SCM and CI data where available. | MUST |
| FR-M17-03 | The dashboard SHALL display throughput and stability **together**, and SHALL raise an explicit warning when throughput rises while change failure rate also rises — the documented AI-adoption failure pattern. | MUST |
| FR-M17-04 | The service SHALL record measured cycle time independently of any perceived-speed signal, and SHALL report both. | MUST |
| FR-M17-05 | All KPIs SHALL be derivable from the ledger, requiring no separate instrumentation store. | MUST |
| FR-M17-06 | No telemetry SHALL leave the workspace without explicit opt-in. Default is fully local. | MUST |

---

## 6. Agent Requirements by SDLC Phase

### 6.1 Loop bounds (defaults, all policy-overridable)

| Loop | Max iterations | Token budget | Wall clock | Escalation |
|---|---|---|---|---|
| L1 Micro (act→verify→repair) | 3 | 50k | 5 min | Surface to L2 with failure trace |
| L2 Task (plan→act→test→review→rework) | 5 | 300k | 30 min | Escalate work packet to human |
| L3 Phase (gate→work→gate) | 3 rework cycles | 800k | 2 h | Escalate phase with gate diff |
| L4 Delivery (story→PR→merge) | — | 2M | 8 h | Chief Orchestrator escalates |
| L5 Learning | 1 per cycle | 500k | 1 h | Discard candidate, log attempt |

### 6.2 Phase 1 — Intake & Analysis

| ID | Requirement |
|---|---|
| FR-P1-01 | `IntakeOrchestrator` SHALL accept a story from: a workspace file (e.g. `EDB-12345.txt`), an MCP-connected issue tracker, or direct text entry. |
| FR-P1-02 | Story content SHALL be tagged **untrusted** on ingest and SHALL be processed under the untrusted-content constraints of §9. |
| FR-P1-03 | `AnalystAgent` SHALL extract: intent, acceptance criteria, affected applications, constraints, and explicit non-goals. |
| FR-P1-04 | `AnalystAgent` SHALL produce an **ambiguity register** listing every underspecified point with a proposed resolution and a confidence score. |
| FR-P1-05 | Ambiguities above a configured severity SHALL be escalated to the human rather than resolved by assumption. Silent assumption is a defect. |
| FR-P1-06 | The **Definition of Ready** gate SHALL require: testable acceptance criteria, identified affected services, no unresolved high-severity ambiguity. |
| FR-P1-07 | The clarified specification SHALL be written to the workspace as a reviewable artifact, not held only in agent memory. |

### 6.3 Phase 2 — Architecture & Design

| ID | Requirement |
|---|---|
| FR-P2-01 | `ArchitectAgent` SHALL produce a design covering: component changes, interface contracts, data model changes, and NFR allocation. |
| FR-P2-02 | Every non-trivial decision SHALL produce an **Architecture Decision Record** written to the repository. |
| FR-P2-03 | `ArchitectAgent` SHALL classify blast radius (`low`/`medium`/`high`) and SHALL flag schema migrations, public API contract changes, cross-service changes, and security-relevant changes as high. |
| FR-P2-04 | `SecurityAgent` SHALL produce a threat-surface delta at design time, not only at scan time. |
| FR-P2-05 | `SREAgent` SHALL declare observability requirements and rollback strategy for the proposed change. |
| FR-P2-06 | High-blast-radius designs SHALL require human approval before Phase 3 regardless of the agent's autonomy tier. |

### 6.4 Phase 3 — Planning & Decomposition

| ID | Requirement |
|---|---|
| FR-P3-01 | `TechLeadAgent` SHALL decompose the design into **Work Packets** (schema §7.3). |
| FR-P3-02 | Each Work Packet SHALL declare: target files/paths, target stack, required skill pack, acceptance tests, dependencies on other packets, and estimated budget. |
| FR-P3-03 | The packet graph SHALL be validated acyclic, and packets marked parallelisable SHALL be verified non-overlapping at file-path granularity. |
| FR-P3-04 | `ScrumMasterAgent` SHALL sequence packets and identify the critical path. |
| FR-P3-05 | The phase exit gate SHALL require every packet to have at least one acceptance test defined before implementation begins. **Tests are contracted before code is written.** |

### 6.5 Phase 4 — Implementation

| ID | Requirement |
|---|---|
| FR-P4-01 | `BuildOrchestrator` SHALL bind each Work Packet to a `DeveloperAgent` (or `FrontendAgent`) instance carrying the packet's required Skill Pack. |
| FR-P4-02 | For greenfield work the agent SHALL scaffold per the Skill Pack's project-layout conventions, not from generic templates. |
| FR-P4-03 | For brownfield work the agent SHALL first analyse existing conventions in the target repository and conform to them where they conflict with Skill Pack defaults. **Repository reality outranks skill defaults.** |
| FR-P4-04 | Implementation SHALL run the L1 Micro loop: write → compile/lint → run unit tests → repair, bounded per §6.1. |
| FR-P4-05 | Parallel packets SHALL execute concurrently only when FR-M4-09 permits. Within a single service's implementation, writes SHALL remain single-threaded. |
| FR-P4-06 | Every produced diff SHALL be ledger-recorded with the prompt, context, tool calls, and stated confidence that produced it. |
| FR-P4-07 | The agent SHALL NOT modify files outside its packet's declared target paths. Out-of-scope modification SHALL be blocked and escalated. |
| FR-P4-08 | Dependency additions SHALL be surfaced as a separately approvable change class per FR-M9-06. |
| FR-P4-09 | The phase exit gate SHALL require: compiles clean, lint clean, unit tests authored and passing, no out-of-scope modification. |

### 6.6 Phase 5 — Verification

| ID | Requirement |
|---|---|
| FR-P5-01 | `QAEngineerAgent` SHALL author tests traceable to specific acceptance criteria. Each criterion SHALL map to at least one test. |
| FR-P5-02 | Tests SHALL be authored by an agent instance distinct from the one that wrote the implementation. |
| FR-P5-03 | The agent SHALL verify tests genuinely fail against the pre-change baseline where applicable, to detect vacuous tests. |
| FR-P5-04 | `QALeadAgent` SHALL produce a **Definition of Done** verdict covering acceptance coverage, regression status, and coverage delta. |
| FR-P5-05 | A coverage decrease SHALL block the gate unless explicitly waived by a human with a recorded reason. |
| FR-P5-06 | Regression suites SHALL run against the full affected surface, not only changed files, given documented evidence that agents break previously working code during maintenance work. |

### 6.7 Phase 6 — Security & Compliance

| ID | Requirement |
|---|---|
| FR-P6-01 | `SecurityAgent` SHALL run SAST, dependency/SCA scan, and secrets detection over the change. |
| FR-P6-02 | New high or critical findings SHALL block the gate. Waivers require human approval with a recorded justification. |
| FR-P6-03 | The agent SHALL produce an SBOM delta for the change. |
| FR-P6-04 | The agent SHALL specifically check for injected instructions in agent-authored content and for unexpected network egress introduced by the change. |
| FR-P6-05 | `GovernanceAgent` SHALL verify that all prior gates were satisfied and that no gate was bypassed. Chain integrity SHALL be verified at this gate. |

### 6.8 Phase 7 — Review & Integration

| ID | Requirement |
|---|---|
| FR-P7-01 | `ReviewerAgent` SHALL critique the change adversarially against the Skill Pack review checklist and the organisation's policy pack. |
| FR-P7-02 | The reviewer SHALL be a distinct agent instance from both implementer and test author. |
| FR-P7-03 | Reviewer rejection SHALL re-enter the L2 Task loop with the critique as feedback, not merely surface a comment. |
| FR-P7-04 | The PR body SHALL be generated to include: the originating story, the agents involved with versions, the gates passed, the ledger sequence range, cost, and a link to the chain viewer slice. |
| FR-P7-05 | **Human approval SHALL be mandatory before PR merge at every autonomy tier.** |
| FR-P7-06 | Review turnaround SHALL be measured and reported, since review latency is a dominant driver of delivery performance and agent throughput increases review load. |

### 6.9 Phases 8–9 — Release, Operate & Maintain (Phase 4 scope)

| ID | Requirement |
|---|---|
| FR-P8-01 | `ReleaseAgent` SHALL produce release notes, version increment, and a deployment plan with an explicit rollback procedure. |
| FR-P9-01 | `SREAgent` SHALL correlate post-deployment SLO movement with the change and feed regressions back to the Trainer as negative signal. |
| FR-P9-02 | Escaped defects SHALL be attributed to the originating ledger sequence range where determinable. |

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
permitted_tools:
  - repo.read
  - repo.patch
  - build.invoke
  - test.invoke
permitted_skills:
  - java-spring-gradle
  - java-fullstack
  - python-service
  - golang-service
  - node-service
autonomy_tier: approve-per-phase
budgets:
  tokens_per_packet: 300000
  cost_usd_per_packet: 4.00
  wallclock_minutes: 30
escalation_target: build-orchestrator
probation:
  task_set: probation/developer/
  pass_threshold: 0.85
owns_gates: []
```

### 7.2 Ledger Entry — see `vision.md` §6.2 for the full DDL

Canonicalisation rule for `entry_hash`: JSON with keys sorted lexicographically, UTF-8, no insignificant whitespace, `prev_hash` and `entry_hash` excluded from the hashed payload, digests hex-encoded lowercase.

### 7.3 Work Packet

```json
{
  "packet_id": "EDB-12345-P03",
  "story_id": "EDB-12345",
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
  "estimated_tokens": 180000
}
```

### 7.4 Decision Record (XAI)

```json
{
  "ledger_seq": 4417,
  "decision": "Use a database-backed idempotency store rather than in-memory",
  "inputs": { "context_digest": "sha256:…", "memory_refs": [1182, 1190] },
  "tool_calls": [ { "tool": "repo.read", "args": "…" } ],
  "stated_confidence": 0.82,
  "rationale": "…",
  "rationale_label": "UNVERIFIED_NARRATIVE",
  "ablation": {
    "performed": true,
    "removed_factor": "memory_ref:1190",
    "output_changed": true,
    "conclusion": "EVIDENCE: retrieved convention record was material to this decision"
  },
  "calibration_context": { "agent_historical_calibration_error": 0.11 }
}
```

---

## 8. Non-Functional Requirements

| ID | Requirement |
|---|---|
| NFR-01 | Extension activation SHALL complete in under 500 ms. Sidecar startup SHALL NOT block activation. |
| NFR-02 | Dashboard interactions SHALL respond within 100 ms; loop-state updates SHALL propagate within 1 s. |
| NFR-03 | Chain verification SHALL complete in under 5 s for 100,000 entries. |
| NFR-04 | The extension SHALL operate correctly on repositories of at least 1 million lines and 50,000 files. |
| NFR-05 | Idle memory footprint of the sidecar SHALL not exceed 400 MB. |
| NFR-06 | A VS Code window reload SHALL lose at most one loop node of work. |
| NFR-07 | All persistent state SHALL be recoverable from disk; no state SHALL exist only in memory. |
| NFR-08 | Sidecar crash SHALL not corrupt the ledger; writes SHALL be transactional. |
| NFR-09 | The extension SHALL function fully offline apart from model API calls. |
| NFR-10 | Every user-visible error SHALL name a cause and a next action. Bare stack traces SHALL NOT surface to users. |
| NFR-11 | The published VSIX SHALL be bundled; unbundled multi-thousand-file packages SHALL NOT be published. |
| NFR-12 | The extension SHALL be distributable through the enterprise Private Marketplace and through manual VSIX installation. |
| NFR-13 | All agent-facing prompts, policies, and playbooks SHALL be plain text under source control and diffable in review. |

---

## 9. Security Requirements

**Threat model premise.** Meridian Loom by default holds all three legs of the *lethal trifecta* — access to private data, exposure to untrusted content, and an external communication channel. That combination is the documented precondition for exfiltration via prompt injection, and prompt injection has no general fix because models cannot reliably distinguish instruction from data.

| ID | Requirement |
|---|---|
| SEC-01 | All repository content, story text, issue comments, dependency metadata, and third-party documentation SHALL be treated as untrusted input. |
| SEC-02 | Untrusted content SHALL be delimited in prompts with explicit markers, and agents SHALL be instructed that content inside those markers is data, never instruction. This is mitigation, not a solution, and SHALL NOT be relied upon alone. |
| SEC-03 | **No single un-gated execution step SHALL simultaneously hold private-data access, untrusted-content processing, and unrestricted egress capability.** Flows SHALL be decomposed so that at most two of the three are present in any un-gated step. |
| SEC-04 | Network egress from agent-executed processes SHALL be restricted to a configured allow-list: model endpoints, approved package registries, approved internal systems. |
| SEC-05 | Build, test, and skill-script execution SHALL occur in a sandbox with a scrubbed environment and no inherited credentials. |
| SEC-06 | Credentials SHALL reside only in OS-keychain-backed SecretStorage and SHALL be injected at the tool boundary, never placed in agent context. |
| SEC-07 | All logged inputs and outputs SHALL pass a secret-redaction filter before persistence. |
| SEC-08 | Skill Packs and MCP servers SHALL be reviewed on install, pinned by version and digest, and executed within the sandbox. Their required tools SHALL be declared and enforced. |
| SEC-09 | Agent-initiated dependency changes SHALL be a distinct approvable class with the resolved version and source registry displayed. |
| SEC-10 | Each agent SHALL have a scoped identity with a least-privilege tool set. The identity SHALL be recorded in every ledger entry. |
| SEC-11 | Force-push, history rewrite, protected-branch modification, and credential-file modification SHALL be unconditionally prohibited to all agents at all tiers. |
| SEC-12 | Export packages SHALL be scanned for secrets and untrusted-tagged content, and export SHALL be blocked on detection. |
| SEC-13 | The extension SHALL provide a single **Halt All** action that immediately stops every loop, terminates the sidecar, and leaves the workspace in a consistent state. |
| SEC-14 | The ledger SHALL record every denied tool invocation, blocked egress attempt, and out-of-scope modification attempt. |

---

## 10. Acceptance Criteria

### 10.1 Phase 1 (first value) acceptance

The build is accepted for Phase 1 when, on a designated Java/Spring reference repository:

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

### 10.2 Quality bar for graduating Phase 1

Phase 2 SHALL NOT begin until, over at least 20 real stories: first-pass yield is measured and reported, cost per merged PR is within the agreed ceiling, and change failure rate for agent-authored merges is not worse than the team's pre-Meridian baseline. **Amplifying an unproven core amplifies error.**

---

## 11. Phased Delivery Plan

| Phase | Modules | Exit condition |
|---|---|---|
| **P0 — Foundation** | M1, M2 (shell), M3, M10 (ledger substrate) | Extension installs on all platforms; sidecar spawns and tears down cleanly with zero orphans; ledger writes and verifies |
| **P1 — First value** | M4, M5, M6 (single skill), M7 (procedural + semantic), M8, M9, M10, M11, M13, plus Analyst/Architect/TechLead/Developer/QA/Reviewer | AC-01 … AC-12 met on the reference repository |
| **P2 — Quality gates** | M12, Security phase, full DoR/DoD gating, full skill catalogue | Gates block real defects; skill swapping proven across three stacks |
| **P3 — Orchestration & learning** | Phase Orchestrators, sub-agent fan-out, M14 Trainer | Trainer demonstrably raises first-pass yield under regression gating, with rollback exercised |
| **P4 — Portability & compliance** | M15, M16, M17 full, Release/Operate phases, private-marketplace distribution, ledger anchoring | Agent exported and imported across two teams; audit bundle accepted in a compliance review |

---

## 12. Risk Register

| # | Risk | Impact | Mitigation |
|---|---|---|---|
| R1 | Prompt injection via story text or repository content | Critical | SEC-01…SEC-05; trifecta decomposition; sandbox; egress allow-list; ledger of denied attempts |
| R2 | Orphaned sidecar processes | High | FR-M3-02, FR-M3-03 dual contract; AC-08 tested on all platforms |
| R3 | Cost blowup from loop retries | High | Bounded loops; per-phase and per-story budgets; model tiering; caching; cost surfaced live |
| R4 | Over-trust — the system feels fast and measures slow | High | NFR/FR-M17-04: measure actual cycle time; display throughput and stability together |
| R5 | Agents break working code on mature repos | High | Full-surface regression (FR-P5-06); distinct test-author agent; blast-radius gating |
| R6 | Multi-agent output that does not compose | High | P3 principle: writes single-threaded per service; fan-out only on verified non-overlap |
| R7 | Memory poisoning from untrusted content | High | FR-M7-07: untrusted tagging, no promotion to procedural memory without human approval |
| R8 | Ledger over-claimed as tamper-proof | Medium | FR-M10-06: explicit tamper-*evident* language in docs and UI; signing and anchoring for stronger claims |
| R9 | Trainer degrades an agent | Medium | Frozen regression suite; monotonic safety invariant; human promotion gate; 10-version rollback |
| R10 | Skill pack supply chain | High | FR-M6-06 review UI; digest pinning; sandboxed execution; declared tool constraints |
| R11 | Python distribution friction across enterprise endpoints | Medium | Platform-specific VSIX targets; interpreter resolution chain; clear diagnostics |
| R12 | Reviewer overload from increased agent throughput | Medium | FR-P7-06 review latency measurement; batch and prioritise by blast radius |
| R13 | Model/provider capability or pricing shift | Medium | FR-M8-08 provider substitution by configuration |

---

## 13. Open Decisions

| # | Decision | Owner | Needed by |
|---|---|---|---|
| D1 | Adopt an existing durable graph runtime vs. build a minimal in-house loop runtime | Architecture | Start of P1 |
| D2 | Model routing and tiering policy per phase | Architecture + Finance | Start of P1 |
| D3 | Ledger anchoring: local signing only, internal transparency service, or external timestamp authority | Security + Compliance | P4 |
| D4 | Python distribution: platform-specific VSIX with bundled runtime vs. workspace interpreter | Platform | P0 |
| D5 | Whether the Trainer may propose Skill Pack edits or only policy/prompt deltas | Governance | P3 |
| D6 | Autonomy tier promotion thresholds per task class | Governance | P2 |
| D7 | Whether Phase 8–9 (Release/Operate) execute deployments or only produce plans | Delivery | P4 |

---

*End of specification. Companion documents: `vision.md` for architecture rationale, and the Executive Plan for the stakeholder-facing summary.*
