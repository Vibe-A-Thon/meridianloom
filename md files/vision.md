# Meridian Loom — Vision

**A governed, observable, self-improving AI engineering department that lives inside VS Code.**

| | |
|---|---|
| **Document** | vision.md |
| **Status** | Draft v1.0 — architecture vision |
| **Author** | Ravaleedhar Reddy |
| **Codename** | Meridian Loom *(provisional; CodeLoom is the alternate under consideration)* |
| **Artifact type** | Product + architecture vision. Buildable detail lives in `Requirements.md`. |

---

## 1. Premise

A Jira story lands in the workspace. `EDB-12345.txt` carries the acceptance criteria and the app context. The Chief Orchestrator — the Delivery Head Agent — picks it up, decides whether this is a greenfield Spring Boot service or a change to an existing repo, convenes the right agents for each phase of the SDLC, and drives the work to a reviewed pull request. A human never prompts a single step. A human approves the gates.

That is the product in one paragraph. Everything below is the architecture that makes it survivable in an enterprise.

### 1.1 The design constraint nobody can skip

Meridian Loom is being built against evidence that cuts against naive automation:

- METR's randomised controlled trial of experienced developers on mature repositories found them **19% slower** with AI assistance while they believed they were **20% faster** — a ~39-point gap between perceived and actual productivity.
- The 2025 DORA report (~5,000 respondents, 90% AI adoption) found AI adoption continues to have a **negative relationship with software delivery stability**. DORA's framing: *AI amplifies what already exists* — it accelerates healthy systems and magnifies dysfunction.
- Long-horizon maintenance benchmarks report a majority of tested models **breaking previously working code** on real repositories even when their patches initially pass all tests.

The conclusion is not "don't build this." The conclusion is that **the ledger, the gates, and the rework loop are the product; the autonomy is what the system earns.** Meridian Loom is designed to catch AI error, price it, attribute it, and learn from it. Throughput without that is a liability generator.

### 1.2 What this vision deliberately does not promise

Three ambitions in the original brief are restated here as engineering targets rather than guarantees, because no available evidence supports the absolute form:

| Original ambition | Restated as |
|---|---|
| 100% on-time delivery | A delivery SLA with predictive slip detection, escalation, and human gates. Never a guarantee. |
| Fully autonomous SDLC across all stacks and domains | Bounded autonomy: named stacks, named task classes, graduated autonomy tiers earned per agent. |
| Self-replicating agents | Manifest-driven agent onboarding with probation tasks and portable export packages. Real and shippable. Autonomous replication is not. |
| Self-evolving agents | Supervised evolution of prompts, policies and playbooks under regression gates with one-click rollback. Agents rewriting their own source is out of scope. |

---

## 2. Agent Taxonomy

Meridian Loom models a delivery organisation, not a chatbot swarm. Agents are organised in tiers, with three cross-cutting families and four meta-agents that operate *on* the organisation rather than *in* it.

### 2.1 Tier L0 — Chief Orchestrator (Delivery Head Agent)

Single instance per workspace. Owns the story end-to-end.

- Ingests the story artifact (`EDB-12345.txt`, Jira/Rally connector, or free text) and classifies it: greenfield vs. brownfield, blast radius, affected services, stack set.
- Selects the phase sequence and the autonomy tier for this story.
- Convenes Phase Orchestrators, holds the global budget (tokens, wall-clock, cost), and owns escalation to the human.
- Is the **only** agent that talks to the human as "delivery." Everything else reports upward.
- Never writes code.

### 2.2 Tier L1 — Phase Orchestrators

One per SDLC phase. Each owns its phase's entry and exit gates, assembles the role agents it needs, and reports a phase verdict upward.

`IntakeOrchestrator` · `DesignOrchestrator` · `PlanOrchestrator` · `BuildOrchestrator` · `VerifyOrchestrator` · `SecurityOrchestrator` · `ReviewOrchestrator` · `ReleaseOrchestrator` · `OperateOrchestrator`

A Phase Orchestrator cannot advance the story. It can only declare its exit gate met or unmet and hand the verdict to L0.

### 2.3 Tier L2 — Role Agents

The recognisable delivery roles, modelled on what a CMMI-L5 engineering organisation actually staffs.

| Role Agent | Owns | Human analogue |
|---|---|---|
| `AnalystAgent` | Requirement clarification, ambiguity detection, Definition of Ready | BA / Product Owner |
| `ArchitectAgent` | Solution design, ADRs, interface contracts, NFR allocation | Solution Architect |
| `TechLeadAgent` | Decomposition, sequencing, work packet contracts | Tech Lead |
| `DeveloperAgent` | Implementation (binds to a Stack Agent skill) | Engineer |
| `FrontendAgent` | UI implementation, accessibility, design-system conformance | Frontend Engineer |
| `QAEngineerAgent` | Test design and authoring, coverage of acceptance criteria | QA Engineer |
| `QALeadAgent` | Test strategy, Definition of Done, release readiness verdict | QA Lead |
| `ReviewerAgent` | Adversarial code critique, standards conformance | Senior Reviewer |
| `SecurityAgent` | SAST/SCA/secrets, threat surface delta | AppSec Engineer |
| `ReleaseAgent` | Build, versioning, release notes, deployment plan | Release Engineer |
| `SREAgent` | Observability hooks, SLO impact, rollback plan | SRE |
| `ScrumMasterAgent` | Flow control, blocker detection, loop health | Scrum Master |

### 2.4 Tier L3 — Stack Agents (the skill mechanic)

A Stack Agent is **not** a separate hard-coded agent. It is a Role Agent bound to a **Skill Pack** at runtime.

> Upload a Go skill pack, and the Developer Agent becomes a Go developer. Upload a Java-full-stack skill pack, and it becomes a Java full-stack engineer. The identity is data, not code.

This is the single highest-leverage design decision in Meridian Loom, and it is buildable on an open, cross-vendor standard (the `SKILL.md` Agent Skills format: a folder with YAML frontmatter, progressive disclosure across discovery → activation → execution, and optional bundled scripts and reference material). Discovery costs roughly a hundred tokens per skill, so a large catalogue can be resident without flooding context.

Target skill catalogue at GA:

`java-spring-gradle` · `java-fullstack` · `python-service` · `golang-service` · `react-frontend` · `node-service` · `dotnet-service` · `aws-iac` · `sql-migration` · `api-contract-first`

Each skill pack carries: coding standards, project layout conventions, build/test invocations, framework idioms, review checklist, and the organisation's own house rules.

### 2.5 Tier L4 — Sub-Agents and the Swarm

Ephemeral workers fanned out by a Phase Orchestrator for **genuinely independent** units of work: a Java backend change, a Go microservice change, and a React frontend change that touch no shared surface.

The governing rule, and it is a hard one:

> **Multiple agents may contribute intelligence in parallel. Writes to a given service or file remain single-threaded.**

Industry evidence is clear that parallel agents writing interdependent code produce non-composing output, because each lacks the other's implicit design decisions. Meridian Loom fans out for reading, analysis, test generation, and independent services. It does not fan out inside one service's implementation.

### 2.6 Cross-cutting family — XAI Agents

Not a tier. An overlay. XAI Agents attach to any decision and produce the explanation record described in §9. They can force an ablation replay on a high-blast-radius decision before it reaches a gate.

### 2.7 Meta-agents — the organisation operating on itself

| Meta-agent | Function |
|---|---|
| `TrainerAgent` | Mines the ledger for approved-vs-reworked signal and proposes prompt/policy/playbook updates. Cannot self-promote — every update passes a regression gate and a human approval. |
| `OnboardingAgent` | Instantiates a brand-new agent role from a manifest, runs it through probation tasks, and scores it before it can take live work. This is how new automation ships **without redeploying the extension**. |
| `GovernanceAgent` | Enforces policy: autonomy tiers, egress rules, gate integrity, budget caps. Can halt the Chief Orchestrator. |
| `ReplicatorAgent` | Packages a tuned agent — policy, skills, evaluation results, provenance — into a portable export another team can import. |

The Ledger is deliberately **not** an agent. It is a service. An audit log that an agent could rewrite is not an audit log.

---

## 3. SDLC Coverage Matrix

| # | Phase | Orchestrator | Primary agents | Entry gate | Exit gate | Ledger artifacts |
|---|---|---|---|---|---|---|
| 1 | Intake & Analysis | `IntakeOrchestrator` | Analyst, XAI | Story artifact present | **Definition of Ready** met; ambiguities resolved or escalated | Clarified spec, ambiguity register, DoR verdict |
| 2 | Architecture & Design | `DesignOrchestrator` | Architect, SRE, Security | DoR met | Design approved; ADRs recorded; NFRs allocated | ADRs, interface contracts, threat delta |
| 3 | Planning & Decomposition | `PlanOrchestrator` | Tech Lead, Scrum Master | Design approved | Work packets contracted with acceptance tests | Work packet graph, sequencing plan |
| 4 | Implementation | `BuildOrchestrator` | Developer + Stack skill, Frontend, sub-agent swarm | Work packets contracted | Code compiles; unit tests authored and green | Diffs, prompts, tool calls, confidence |
| 5 | Verification | `VerifyOrchestrator` | QA Engineer, QA Lead | Build green | Acceptance criteria demonstrably covered and passing | Test suites, run results, coverage delta |
| 6 | Security & Compliance | `SecurityOrchestrator` | Security, Governance | Verification passed | No new high/critical findings; SBOM delta clean | Scan results, SBOM delta, waivers |
| 7 | Review & Integration | `ReviewOrchestrator` | Reviewer, Architect | Security clear | Human approval recorded; PR opened | Critique record, human approver identity |
| 8 | Release | `ReleaseOrchestrator` | Release, SRE | PR merged | Release artifact + rollback plan produced | Release notes, deployment plan |
| 9 | Operate & Maintain | `OperateOrchestrator` | SRE, Developer | Deployed | SLOs held; regressions triaged | Incident links, SLO impact, feedback to Trainer |

Phases 8 and 9 are Phase-4 scope. Phases 1–7 constitute the shippable core.

---

## 4. Loop Engineering — the Graph of Loops

Meridian Loom's control model is not a pipeline. It is a **graph of nested, budgeted, checkpointed loops**. Every loop declares five things, and the runtime refuses to execute a loop that omits any of them:

1. **Entry condition** — what must be true to enter
2. **Body** — the agent invocation graph
3. **Exit criteria** — objective and machine-checkable wherever possible
4. **Bounds** — max iterations, token budget, wall-clock budget, cost ceiling
5. **Escalation** — what happens when bounds are hit without exit

### 4.1 The six canonical loops

```
L6  Organisation loop    KPIs → autonomy tier adjustment → policy
 └─ L5  Learning loop    ledger → Trainer → regression gate → promote | rollback
     └─ L4  Delivery loop    story → PR → merge → production feedback
         └─ L3  Phase loop       entry gate → phase work → exit gate → advance | rework
             └─ L2  Task loop        plan → act → test → review → rework
                 └─ L1  Micro loop       act → verify → repair
```

| Loop | Exits when | Bound | On bound breach |
|---|---|---|---|
| **L1 Micro** | Unit compiles and its tests pass | 3 iterations | Surface to L2 with failure trace |
| **L2 Task** | Reviewer approves and tests green | 5 iterations | Escalate work packet to human |
| **L3 Phase** | Exit gate satisfied | 3 rework cycles | Escalate phase to human with gate diff |
| **L4 Delivery** | PR merged | Story budget | Chief Orchestrator escalates to human |
| **L5 Learning** | Candidate policy beats incumbent on regression suite | Per training cycle | Discard candidate, log the attempt |
| **L6 Organisation** | Continuous | — | Governance review |

### 4.2 Why loops, not a DAG

Self-correction is the whole point: if tests fail or a reviewer rejects the output, the system loops back to *act* and retries with the failure as feedback, rather than waiting for a human to re-prompt. That requires cycles. Cycles require termination guarantees, which is why every loop is bounded and every iteration is checkpointed durably — the sidecar can be killed mid-loop, the VS Code window can be reloaded, and the loop resumes from its last checkpoint rather than from the beginning.

### 4.3 Loop observability

Every loop iteration emits a ledger entry. The dashboard renders the live loop graph: which loops are open, at what iteration, against what budget, and how close to escalation. A loop that keeps hitting iteration 4 of 5 across many stories is a training signal, not just an incident.

---

## 5. Orchestration Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  VS CODE EXTENSION HOST  (TypeScript)                        │
│  • Activation, commands, tree views                          │
│  • Webview dashboard host (React, CSP + nonce sandbox)       │
│  • Workspace + SCM access, diff application                  │
│  • SecretStorage (OS keychain) for model credentials         │
│  • Sidecar lifecycle: spawn, health, guaranteed teardown     │
└───────────────┬─────────────────────────────────────────────┘
                │  JSON-RPC over stdio (framed, versioned)
┌───────────────▼─────────────────────────────────────────────┐
│  MERIDIAN CORE  (Python sidecar)                             │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ Loop Runtime — durable graph execution, checkpoints,   │ │
│  │ interrupt/resume, budget enforcement                    │ │
│  ├────────────────────────────────────────────────────────┤ │
│  │ Agent Registry  │ Skill Loader  │ Memory Fabric        │ │
│  ├────────────────────────────────────────────────────────┤ │
│  │ Model Router (tiering, caching, budget)                │ │
│  ├────────────────────────────────────────────────────────┤ │
│  │ Tool Layer — MCP client, repo tools, build/test runner │ │
│  ├────────────────────────────────────────────────────────┤ │
│  │ Ledger Service (SQLite, hash-chained, signed)          │ │
│  └────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
```

**Why a Python sidecar.** The brief requires agent logic in Python. It is also where the orchestration ecosystem lives, and it keeps long-running work off the extension host, where synchronous work blocks every other extension in the window. The cost is process-lifecycle risk — orphaned sidecars after a host crash are a documented failure mode across shipping agent extensions — so guaranteed teardown and parent-death self-termination are hard requirements, not nice-to-haves.

**Orchestration engine.** A durable graph runtime with typed state, reducer-merged concurrent updates, checkpointer-backed persistence, and first-class interrupt/resume for human gates. LangGraph is the reference implementation of this shape; the requirements specify the *capabilities* so the engine remains substitutable.

**Model access.** Two paths. The VS Code Language Model API (`vscode.lm`) for in-editor, consent-gated, Copilot-backed calls; direct provider APIs from the sidecar with keys in SecretStorage for the orchestration workload. The second path is primary — it avoids per-extension consent friction and provider quota opacity, and it gives the Model Router real control over tiering and cost.

**Tools.** MCP is the tool transport. It is generally available in VS Code, spec-complete, and gives Meridian Loom the whole existing server ecosystem for Jira, Git, CI, and internal systems without bespoke integrations.

---

## 6. The Ledger and the Chain Viewer

### 6.1 What it is, stated honestly

A local, append-only, **hash-chained Merkle log** with signed tree heads — the transparency-log design proven by Certificate Transparency, Trillian, and Sigstore Rekor. Not a blockchain.

This distinction matters and should be stated plainly in every stakeholder conversation:

> A hash chain is **tamper-evident, not tamper-proof**. It detects modification. It does not prevent a local user with disk access from rewriting the entire chain — **unless entries are signed and tree heads are externally anchored.**

An actual distributed ledger buys nothing here that a signed, anchored Merkle log does not, and costs latency, spend, and operational burden. The "blockchain viewer" is the right *user experience*; the substrate underneath it is a transparency log. Where regulatory pressure demands stronger non-repudiation, tree heads are anchored to an external timestamp authority or internal transparency service.

### 6.2 Entry schema

```sql
CREATE TABLE ledger_entry (
  seq            INTEGER PRIMARY KEY,   -- monotonic, gapless
  ts_utc         TEXT    NOT NULL,
  prev_hash      BLOB    NOT NULL,      -- SHA-256 of previous entry_hash
  entry_hash     BLOB    NOT NULL,      -- SHA-256 over canonicalised payload

  story_id       TEXT    NOT NULL,      -- e.g. EDB-12345
  phase          TEXT    NOT NULL,
  loop_id        TEXT    NOT NULL,
  loop_iteration INTEGER NOT NULL,

  actor_id       TEXT    NOT NULL,      -- e.g. developer-agent
  actor_version  TEXT    NOT NULL,
  actor_kind     TEXT    NOT NULL,      -- orchestrator|role|stack|sub|xai|meta
  policy_version TEXT    NOT NULL,
  skill_id       TEXT,
  skill_version  TEXT,
  model_id       TEXT,
  model_version  TEXT,

  action_type    TEXT    NOT NULL,      -- plan|prompt|tool_call|diff|test_run|
                                        -- review|scan|gate|approval|policy_update|export
  input_digest   BLOB,                  -- hash of full prompt/context
  input_ref      TEXT,                  -- blob store path
  output_digest  BLOB,
  output_ref     TEXT,
  tool_calls     TEXT,                  -- JSON array

  confidence     REAL,                  -- self-reported, uncalibrated at capture
  decision       TEXT,                  -- proposed|approved|rejected|reworked
  human_actor    TEXT,                  -- identity of approver, when applicable
  rework_reason  TEXT,

  tokens_in      INTEGER,
  tokens_out     INTEGER,
  cost_usd       REAL,
  latency_ms     INTEGER,

  signature      BLOB                   -- optional per-entry signature
);

CREATE TABLE tree_head (
  seq         INTEGER PRIMARY KEY,      -- ledger seq this head covers
  root_hash   BLOB NOT NULL,            -- Merkle root
  signed_at   TEXT NOT NULL,
  signature   BLOB NOT NULL,
  anchor_ref  TEXT                      -- external anchor, when configured
);
```

This single schema answers the compliance question the brief demands — *which agent wrote this code, what was it told, what was its confidence, who approved it* — and simultaneously satisfies AI Act Article 12 record-keeping, ISO/IEC 42001 traceability, and the Trainer Agent's need for approved-vs-reworked signal. One structure, three jobs.

### 6.3 The viewer

- Chain integrity banner: verified to seq N, or a loud tamper indication with the first divergent sequence
- Block stream filterable by story, agent, phase, loop, decision
- Inclusion proof and consistency proof inspection for any entry
- Diff view: the exact change an entry produced, side by side with the prompt that produced it
- Cost and confidence overlays across the chain

---

## 7. The Liveness Dashboard

The human control plane. Built as a React webview under a strict CSP with nonce-scoped scripts and `asWebviewUri` resource loading; state persisted through `setState`/serializer so a hidden or reloaded panel restores rather than resets.

**Views:** Agent Roster (heartbeat, current loop, queue depth, trust score, autonomy tier) · Loop Graph (live, animated, budget-aware) · Story Board (phase progress against gates) · Chain Viewer · Training Queue · Skill Catalogue · Cost & KPI panel.

**Actions, all ledger-recorded with approver identity:**

| Action | Effect |
|---|---|
| **Approve** | Satisfies a gate; the story advances |
| **Rework** | Rejects output with a reason; re-enters the loop with the reason as feedback |
| **Train** | Queues the agent for a Trainer cycle against recent ledger evidence |
| **Onboard** | Launches the manifest-driven wizard for a new agent role, into probation |
| **Export** | Packages a tuned agent for another team |
| **Pause / Retire** | Suspends or removes an underperforming agent from live work |

---

## 8. Self-Evolution and Replication

### 8.1 Evolution — what actually works

Optimising an agent's **prompts, policies and playbooks** from execution traces is demonstrated and credible. Reflective prompt evolution against a Pareto frontier has been shown to outperform reinforcement-style optimisation by roughly 10% on average while using up to 35× fewer rollouts; structured playbook evolution has matched much larger systems using smaller models. Optimising an agent's **source code** is research-grade and out of scope.

The Trainer cycle:

```
harvest      ledger slice: approved vs. reworked, with rework reasons
   ↓
propose      candidate policy delta (prompt, playbook, checklist, skill binding)
   ↓
isolate      candidate runs in a sandboxed evaluation workspace
   ↓
evaluate     frozen regression suite + recent real stories replayed
   ↓
attribute    which delta produced which improvement
   ↓
gate         must beat incumbent AND violate no safety invariant
   ↓
approve      human approves in the Training Queue
   ↓
promote      versioned, ledger-recorded, one-click rollback retained
```

**Monotonic safety invariant:** an evolution step may never weaken a declared constraint. A candidate that improves throughput by relaxing a security check or a test gate is rejected regardless of its score.

### 8.2 Replication — reframed and shippable

Two mechanics deliver what "self-replicating, exportable to other work teams" needs:

**Export/import.** A tuned agent packages as: manifest + policy and prompt set + skill bindings + selected memory + evaluation results + full provenance. A signed agent card establishes identity and integrity. Another team imports it and starts from a *trained* agent rather than a generic prompt. Cross-org agent identity and capability advertisement have an emerging standard (A2A, now under the Linux Foundation with signed agent cards) — with the caveat that none of the current interop protocols natively express authorisation policy, so Meridian Loom wraps its own governance around them.

**Onboarding.** A new agent role arrives as a manifest plus onboarding wizard. The OnboardingAgent runs it through **probation tasks** with known-good outcomes, scores it, and only then admits it to live work at the lowest autonomy tier. No extension redeployment. This is the honest version of "the organisation grows itself."

---

## 9. XAI — Explainability Requirements

### 9.1 The constraint

Chain-of-thought is **not a faithful account of the model's actual computation**. Published evaluation found reasoning models mentioning a decisive hint they had been given only a minority of the time — roughly a quarter to under 40% depending on model — with the conclusion that CoT monitoring is unlikely to reliably catch rare, serious behaviour. Any system claiming to show "why the agent did X" from its narration is overclaiming.

### 9.2 What Meridian Loom will and will not claim

| Meridian Loom provides | Honestly labelled as |
|---|---|
| Full decision trace: inputs, retrieved context, tool calls, outputs | **What happened.** Verifiable fact. |
| Self-reported rationale | **Unverified narrative.** Displayed with that label in the UI. |
| Confidence score + tracked calibration over time | **Estimate**, with historical calibration shown alongside |
| Ablation replay — re-run with a factor removed | **Evidence.** The most defensible "why" available. |
| Attribution of an outcome to a contributing agent | **Estimate**, from trace and contribution analysis |

**Hard rule:** an explanation never substitutes for a verification gate. No agent may pass a gate by explaining itself well. It passes by tests, scans, and human approval.

---

## 10. Security and Governance

### 10.1 The threat that defines the architecture

Meridian Loom, by default, holds all three legs of the **lethal trifecta**: access to private data (the repo, credentials), exposure to untrusted content (repo files, Jira text, issue comments, dependencies), and an external communication channel (PRs, network egress, model APIs). That combination is the documented precondition for data exfiltration via prompt injection, and prompt injection is not a bug with a patch — models cannot reliably separate instruction from data.

**Therefore, and non-negotiably:**

- **The story artifact is untrusted input.** `EDB-12345.txt` is a primary injection vector. So is every file the agents read.
- **No single un-gated flow holds all three trifecta properties.** Flows are decomposed so that untrusted-content processing and egress capability are not simultaneously available to the same un-gated step.
- **Sandboxed execution.** Agent-run builds, tests, and scripts execute in a constrained environment.
- **Egress allow-list.** Model endpoints, approved package registries, approved internal systems. Nothing else.
- **Least-privilege tooling.** Each agent identity carries a scoped tool and permission set. Skill packs declare their required tools explicitly.
- **Skill packs are executable code and are vetted as such** — reviewed on intake, pinned by version and digest, sandboxed on execution.
- **Secrets never enter agent context.** Credentials live in the OS keychain via SecretStorage and are injected at the tool boundary.

### 10.2 Governance

- **Autonomy tiers**, earned per agent per task class: `suggest` → `approve-each-action` → `approve-per-phase` → `autonomous-within-bounds`. Promotion requires sustained first-pass yield; regression demotes automatically.
- **The GovernanceAgent can halt the Chief Orchestrator.** Policy outranks delivery.
- **Every gate decision is ledger-recorded with human approver identity.**
- **Compliance alignment:** EU AI Act Article 12 (logging and traceability; high-risk obligations from August 2026, with deployer log retention of at least six months), ISO/IEC 42001, and NIST AI RMF. The ledger is the primary compliance artifact.

---

## 11. Extensibility

Four extension points, each data-driven, none requiring an extension redeploy:

1. **Skill Packs** — new stack or domain capability (`SKILL.md` folder)
2. **Agent Manifests** — new role, onboarded through probation
3. **MCP Servers** — new tools and system integrations
4. **Policy Packs** — organisation-specific gates, standards, and thresholds

The house standards of a top-tier product organisation — the coding conventions, review checklists, and documentation expectations the brief calls for — enter through Skill Packs and Policy Packs. They are configuration, not code, so each account and each team can differ without a fork.

---

## 12. KPIs

There is no published standard for measuring an agentic engineering workforce. Meridian Loom defines one, anchored to established delivery measurement and extended with agent-specific signal.

**Delivery health (DORA four keys + stability).** Deployment frequency · lead time for change · change failure rate · failed-deployment recovery time · **rework rate**. Instrumented specifically to detect the DORA finding that AI raises throughput while eroding stability — if Meridian Loom raises throughput and change failure rate together, that is a failure, not a win.

**Agent workforce.**

| KPI | Definition | Why it matters |
|---|---|---|
| **First-pass yield** | Outputs approved without rework, % | The headline quality metric |
| Human intervention rate | Gates requiring correction rather than approval | Measures real autonomy |
| Rework rate by agent, phase, loop | Where the organisation actually fails | Drives the Trainer |
| **Cost per merged PR** | Fully loaded model spend | The economic reality check |
| Tokens per story | Distribution, not average | The dominant cost driver |
| Time to merge | Story ingest → merge | End-to-end throughput |
| Agent trust score | Composite of yield, calibration, tenure | Gates autonomy tier promotion |
| Escaped defect density | Defects attributable to agent-authored change | The lagging quality truth |
| Confidence calibration error | Stated confidence vs. observed outcome | Whether the XAI signal is worth anything |

**Developer experience.** Because the METR result is a warning about self-reported speed, Meridian Loom measures *actual* cycle time alongside perceived usefulness, and reports both. A system that feels fast and measures slow must be caught by its own instrumentation.

---

## 13. Delivery Approach

| Phase | Scope | Proves |
|---|---|---|
| **0 — Foundation** | Extension shell, React dashboard, Python sidecar with guaranteed teardown, SecretStorage, ledger substrate | The platform is stable |
| **1 — First value** | Java/Spring only. One slice: story → PR. Single strong Developer Agent + reflection loop + human gate. Full ledger and XAI trace from day one. | First-pass yield and cost per story are acceptable |
| **2 — Quality gates** | QA, Security, Reviewer agents as evaluator gates. Skill Packs for stack swapping. DoR/DoD wired into the loop graph. | The system catches its own errors |
| **3 — Orchestration & learning** | Phase Orchestrators, parallel sub-agents on genuinely independent services, Trainer Agent under regression gates | The organisation improves itself |
| **4 — Portability & compliance** | Export/import, onboarding wizard, release and operate phases, private-marketplace distribution, external ledger anchoring | It scales across teams and survives audit |

**The sequencing principle:** prove first-pass yield and unit economics on one stack and one slice before adding a single additional agent. Every phase after 1 is an amplifier. Amplifying an unproven core amplifies error.

---

## 14. Open Decisions

| # | Decision | Bearing |
|---|---|---|
| D1 | Orchestration engine: adopt LangGraph-class runtime vs. build a minimal in-house loop runtime | Velocity vs. control |
| D2 | Model routing strategy and tiering policy across phases | Dominant cost lever |
| D3 | Ledger anchoring: local signing only, internal transparency service, or external timestamp authority | Compliance strength vs. ops burden |
| D4 | Python distribution: platform-specific VSIX targets vs. consuming the workspace interpreter | Install friction vs. package size |
| D5 | Whether the Trainer may propose skill-pack edits or only policy/prompt deltas | Blast radius of self-evolution |
| D6 | Autonomy tier promotion thresholds, per task class | Risk appetite |

---

## 15. The One-Line Version

**Meridian Loom is a living software organisation that runs inside the editor — one that records everything it does, proves what it changed, asks permission at the gates that matter, and gets measurably better at your codebase every time you approve or reject its work.**

The agents are the visible part. The ledger, the gates, and the loops are why it can be trusted in production.
