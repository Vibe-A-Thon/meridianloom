# Meridian Loom — Proposed Additions to Requirements.md

| | |
|---|---|
| **Document** | Requirements-Additions.md |
| **Version** | 1.0 — proposed, for review |
| **Author** | Ravaleedhar Reddy |
| **Against** | Requirements.md v1.0 (17 modules, 227 requirements) |
| **Purpose** | Everything the current specification does not yet cover, organised so each item can be accepted, deferred, or rejected individually |

---

## How to read this

Items are grouped into ten parts. Each has a proposed ID, a priority, and a one-line rationale. Priorities use the same MUST / SHOULD / COULD vocabulary as the base document, but with a target release: **v1** (needed before Phase 1 acceptance), **v1.x** (needed before enterprise rollout), **v2** (differentiating, not blocking).

Part I is different from the rest. It lists places where the current specification is internally inconsistent or silent on something that will bite during build. Those need decisions, not features.

The single most important finding is in Part I, item T1: **the specification assumes agents edit the same working tree the human is using.** That will cause data loss the first time a human and an agent touch the same file. Git worktree isolation (M18) is the fix, and it should be treated as a v1 MUST.

---

## Part A — New Modules

### M18 — Workspace Isolation & Story Branching

The base spec has no model for *where* agents write. Every story needs its own isolated checkout.

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

The base spec mentions "an MCP-connected issue tracker" once. Ingestion and write-back are a full module.

| ID | Requirement | Priority |
|---|---|---|
| FR-M19-01 | First-class connectors SHALL exist for **Jira Cloud, Jira Data Center, Rally, Azure DevOps Boards, and GitHub Issues**, each mapping fields to the story schema. | MUST v1.x (Jira v1) |
| FR-M19-02 | Connectors SHALL support **write-back**: story status transitions, comments summarising phase completion, links to the PR, and a link to the ledger slice. | MUST v1.x |
| FR-M19-03 | Write-back SHALL be opt-in per transition and SHALL never move a story to a Done state without a human approval recorded in the ledger. | MUST v1.x |
| FR-M19-04 | Connectors SHALL ingest attachments and linked pages (Confluence, wiki) as untrusted context, tagged per FR-M7-07. | SHOULD v1.x |
| FR-M19-05 | The story schema SHALL support **story templates** per organisation, pre-populating acceptance-criteria structure and required fields. | SHOULD v1.x |
| FR-M19-06 | A story SHALL be classifiable by **complexity tier** (S / M / L / XL) at ingest, using a configurable heuristic, and the tier SHALL select the loop-bound profile and model-tiering policy. | SHOULD v1 |
| FR-M19-07 | Stories SHALL be ingestible in **batch** (an epic's children) with dependency ordering respected. | COULD v2 |

### M20 — Human Identity, Roles & Separation of Duties

The base spec says "human approval" 40+ times and never defines who a human is.

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

### M21 — Multi-Story & Portfolio Orchestration

The base spec is single-story. An engineering organisation runs dozens.

| ID | Requirement | Priority |
|---|---|---|
| FR-M21-01 | The Chief Orchestrator SHALL manage a **story queue** with priority, WIP limits, and dependency ordering. | MUST v1.x |
| FR-M21-02 | Concurrent stories SHALL be isolated by worktree (M18) and SHALL NOT share in-flight agent instances. | MUST v1.x |
| FR-M21-03 | **Resource contention** across stories — model rate limits, sandbox slots, budget — SHALL be arbitrated by priority, with starvation prevention. | MUST v1.x |
| FR-M21-04 | A **portfolio view** SHALL show every active story's phase, gate state, spend, and predicted completion. | SHOULD v1.x |
| FR-M21-05 | Stories touching overlapping files SHALL be detected at plan time and serialised or flagged for human sequencing. | MUST v1.x |
| FR-M21-06 | **Delivery SLA per story** with slip prediction from loop-iteration trend, surfacing predicted breach before it happens. This is the honest implementation of "on-time delivery". | SHOULD v1.x |

### M22 — Multi-Repository & Cross-Service Changes

The vision promises "a Java backend, a Go microservice and a React frontend" in parallel. The spec assumes one workspace.

| ID | Requirement | Priority |
|---|---|---|
| FR-M22-01 | A story SHALL be able to span **multiple repositories** declared in a workspace manifest, each with its own worktree, branch, and PR. | MUST v1.x |
| FR-M22-02 | Cross-repository work packets SHALL declare **interface contracts** (OpenAPI, protobuf, GraphQL schema) that both sides build against, generated by the Architect Agent before implementation. | MUST v1.x |
| FR-M22-03 | Multi-repo PRs SHALL be linked and SHALL merge in dependency order, with the orchestrator waiting on upstream merge before requesting downstream. | SHOULD v1.x |
| FR-M22-04 | Monorepo support: packets SHALL scope to a path prefix and SHALL run only the affected build targets (Bazel / Nx / Gradle composite aware). | SHOULD v1.x |

### M23 — CI/CD & Merge Integration

The loop ends at "PR opened". The real loop ends at "CI green and merged".

| ID | Requirement | Priority |
|---|---|---|
| FR-M23-01 | The system SHALL integrate with **GitHub Actions, GitLab CI, Azure Pipelines, and Jenkins** to await CI completion and ingest results. | MUST v1.x (GitHub v1) |
| FR-M23-02 | CI failure SHALL re-enter the L2 Task loop with the failing job's log as feedback, subject to the same bounds. | MUST v1.x |
| FR-M23-03 | **Human review comments on the PR** SHALL be ingested as rework signal, attributed to the reviewer, and fed to the Trainer. | MUST v1.x |
| FR-M23-04 | **CODEOWNERS** SHALL be respected for reviewer assignment; agent PRs SHALL request review from the owning humans. | SHOULD v1.x |
| FR-M23-05 | Merge queue / auto-merge integration, gated on human approval per FR-M12-05. | SHOULD v1.x |
| FR-M23-06 | PR descriptions SHALL be generated from a template and SHALL include the fields in FR-P7-04 plus a **verification checklist** the reviewer can tick. | MUST v1 |

### M24 — Chat Participant & Editor Integration

The base spec builds a dashboard. VS Code's native surfaces are cheaper and where engineers already are.

| ID | Requirement | Priority |
|---|---|---|
| FR-M24-01 | A **`@meridian` Chat Participant** SHALL be registered, supporting slash commands: `/ingest`, `/status`, `/explain <seq>`, `/why <file:line>`, `/halt`, `/approve <gate>`. | SHOULD v1 |
| FR-M24-02 | **Hover provenance**: hovering an agent-authored line SHALL show the agent, version, confidence, and ledger sequence, with a link to the entry. | SHOULD v1 |
| FR-M24-03 | **Code actions**: "Ask Meridian to fix", "Ask Meridian to test this", "Explain this change" SHALL be available on selections. | SHOULD v1.x |
| FR-M24-04 | **Git blame decoration** SHALL distinguish agent commits visually and link to the ledger. | SHOULD v1.x |
| FR-M24-05 | Diagnostics (Problems panel) SHALL include agent-detected issues with the originating agent and a quick-fix where one exists. | COULD v2 |
| FR-M24-06 | The Terminal SHALL expose a `meridian` CLI for status, halt, and ledger queries, so the product is scriptable. | SHOULD v1.x |

### M25 — Steering, Clarification & Human-in-the-Loop Refinement

The base spec offers Approve / Rework / Escalate / Waive. Real collaboration needs finer instruments.

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

### M26 — Cost Forecasting & Economics

The base spec measures cost after the fact. Engineering managers need it before.

| ID | Requirement | Priority |
|---|---|---|
| FR-M26-01 | At ingest, the system SHALL produce a **cost and duration estimate** with a confidence interval, from story complexity tier and historical ledger data for similar stories. | SHOULD v1 |
| FR-M26-02 | Budget increases mid-story SHALL require approval from an Approver role and SHALL be ledger-recorded with justification. | MUST v1.x |
| FR-M26-03 | Cost SHALL be attributable to **team, project, client, and cost centre** via story metadata, exportable for chargeback. | MUST v1.x |
| FR-M26-04 | The Model Router SHALL support **prompt caching, context compaction, and tool-result summarisation** as configurable cost levers, with their savings reported. | MUST v1 |
| FR-M26-05 | A **model comparison harness** SHALL allow the same golden story to be run against N model configurations and the results compared on yield, cost, and latency. | SHOULD v1.x |
| FR-M26-06 | Effort reporting: per-story human time (gate decisions, steering, rework) SHALL be tracked alongside agent cost, for a true cost-per-change. | SHOULD v1.x |

### M27 — Deterministic Replay & Runtime Testing

Without this, the runtime itself cannot be tested. This is a build-enabler, not a feature.

| ID | Requirement | Priority |
|---|---|---|
| FR-M27-01 | Every model call and tool result SHALL be recordable to a **replay cassette** keyed by canonical request hash. | MUST v1 |
| FR-M27-02 | A story SHALL be **replayable deterministically** from its cassette with no model calls, producing an identical ledger. | MUST v1 |
| FR-M27-03 | A **golden story corpus** (minimum 20 stories across the supported stacks) SHALL be maintained as the runtime's regression suite, run in CI on every change to the loop runtime, agents, or policies. | MUST v1 |
| FR-M27-04 | **Fault injection**: the runtime SHALL support injected model timeouts, tool failures, sidecar kills, and corrupted ledger entries, to verify checkpoint recovery and chain verification. | MUST v1 |
| FR-M27-05 | Load test: 10 concurrent stories on a reference machine without budget or checkpoint failures. | SHOULD v1.x |

### M28 — Code Intelligence Substrate

Agents that edit code need structural understanding, not just text.

| ID | Requirement | Priority |
|---|---|---|
| FR-M28-01 | The Tool Layer SHALL consume **Language Server** diagnostics, symbol resolution, references, and rename refactoring, so agents use the same truth the editor does. | MUST v1 |
| FR-M28-02 | **Tree-sitter** parsing SHALL be available for structural edits, AST-aware diffs, and syntax validation before any file write. | MUST v1 |
| FR-M28-03 | **Semantic code search** over the repository (embedding index, incrementally updated) SHALL be a native tool. | MUST v1 |
| FR-M28-04 | **Reuse-first policy**: before writing a new function or class, the agent SHALL search for existing implementations and SHALL cite what it found or why nothing fit. Duplicate detection SHALL flag re-implementation. | MUST v1 |
| FR-M28-05 | Large-file handling: files above a configurable size SHALL be edited by targeted hunk, never regenerated whole. | MUST v1 |
| FR-M28-06 | Repository indexing SHALL be incremental and SHALL complete initial indexing of a 1M-LOC repository in under 10 minutes on a reference machine. | SHOULD v1 |
| FR-M28-07 | Binary and generated files (lockfiles, build outputs, minified assets) SHALL be excluded from agent editing by default, with an allow-list. | MUST v1 |

### M29 — Documentation & Knowledge Output

The original brief demanded "top coding **and documenting** standards". The spec has no documentation phase.

| ID | Requirement | Priority |
|---|---|---|
| FR-M29-01 | A **Documentation Agent** SHALL produce or update: API documentation, README sections, inline docs, changelog entries, and runbooks affected by the change. | MUST v1.x |
| FR-M29-02 | Documentation SHALL be a gate criterion: public API changes without updated documentation SHALL block Review. | SHOULD v1.x |
| FR-M29-03 | The story's **journey report** — spec, decisions, packets, tests, gates, cost — SHALL be exportable as Markdown, PDF, and a Confluence page. | SHOULD v1.x |
| FR-M29-04 | ADRs SHALL be enforced: a **fitness function** (ArchUnit-style) SHALL check code against ADR constraints at the Verify gate. | SHOULD v1.x |

### M30 — Runtime Operations & Lifecycle

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

## Part B — Extensions to Existing Modules

### M3 — Sidecar (Remote Development)

| ID | Requirement | Priority |
|---|---|---|
| FR-M3-11 | The extension SHALL function under **VS Code Remote — SSH, WSL, Dev Containers, and GitHub Codespaces**, with the sidecar running on the remote host where the repository lives. This is the dominant enterprise configuration and §1.4 is silent on it. | MUST v1 |
| FR-M3-12 | Sidecar resource limits (CPU, memory) SHALL be configurable and enforced via cgroups or job objects where the platform permits. | SHOULD v1.x |
| FR-M3-13 | The sidecar SHALL expose a **versioned local API** (Unix socket / named pipe, token-authenticated) so external tools and the CLI can drive it. | SHOULD v1.x |

### M7 — Memory Fabric

| ID | Requirement | Priority |
|---|---|---|
| FR-M7-09 | **Organisation-level memory**: procedural memory SHALL be layerable — organisation → team → repository — with lower layers overriding higher, so house standards propagate without duplication. | MUST v1.x |
| FR-M7-10 | Memory SHALL be **exportable and importable** as a reviewable Markdown bundle, and diffable across versions. | SHOULD v1 |
| FR-M7-11 | **Human-curated memory** SHALL be first-class: a human SHALL be able to author, edit, and pin procedural entries that agents may not modify. | MUST v1 |
| FR-M7-12 | Memory entries SHALL carry a **freshness score** and SHALL be flagged stale when the code they describe has changed since they were written. | SHOULD v1.x |
| FR-M7-13 | Context assembly SHALL be **budgeted and ranked**: each agent invocation declares a context budget and the fabric fills it by relevance, provenance trust, and freshness, logging what was included and what was cut. | MUST v1 |

### M8 — Model Router

| ID | Requirement | Priority |
|---|---|---|
| FR-M8-09 | **Multi-provider failover** with health checks and automatic rerouting, ledger-recorded. | MUST v1.x |
| FR-M8-10 | **Local model support** (Ollama, vLLM, LM Studio, or any OpenAI-compatible endpoint) for air-gapped or data-residency-constrained deployments. | MUST v1.x |
| FR-M8-11 | **PII and secret redaction** of prompts before transmission to any external provider, with a redaction log. | MUST v1 |
| FR-M8-12 | **Data residency** policy: providers SHALL be tagged by region, and policy SHALL be able to restrict which providers a workspace may use. | MUST v1.x |
| FR-M8-13 | Provider **rate-limit backpressure** SHALL pause loops gracefully at a checkpoint rather than failing them. | MUST v1 |
| FR-M8-14 | Structured output enforcement: agent outputs that must be machine-parsed SHALL use schema-constrained generation where the provider supports it, with validation and bounded retry otherwise. | MUST v1 |

### M10 — Ledger

| ID | Requirement | Priority |
|---|---|---|
| FR-M10-12 | A **ledger query API** (filter, aggregate, time-range, full-text over blobs) SHALL be exposed to the dashboard, CLI, and external tools. | MUST v1 |
| FR-M10-13 | **Natural-language ledger queries** via the chat participant: "why was the store made database-backed?" resolves to the decision record and its evidence. | SHOULD v1.x |
| FR-M10-14 | **Right-to-erasure compatibility**: personal data in ledger blobs SHALL be encrypted with per-subject keys so that erasure is achievable by key destruction (crypto-shredding) without breaking the hash chain. See T3. | MUST v1.x |
| FR-M10-15 | Ledger **compaction**: blobs older than the retention horizon MAY be archived to cold storage with their digests retained in the chain, so verification still passes. | SHOULD v1.x |
| FR-M10-16 | **Annotations and bookmarks** on entries, by humans, stored as separate signed entries referencing the original. | COULD v2 |
| FR-M10-17 | **Shareable slices**: a ledger range SHALL be exportable as a signed, self-verifying HTML bundle for review by someone without the extension. | SHOULD v1.x |

### M12 — Governance

| ID | Requirement | Priority |
|---|---|---|
| FR-M12-10 | **Regulatory policy packs** (PCI-DSS, HIPAA, SOC 2, GDPR) SHALL be installable and SHALL add gate criteria, redaction rules, and retention constraints. | SHOULD v1.x |
| FR-M12-11 | **Compliance evidence export**: an audit bundle mapped to ISO/IEC 42001 clauses and EU AI Act Article 12 record-keeping requirements. | SHOULD v1.x |
| FR-M12-12 | Policy changes SHALL be **git-backed** and reviewable via PR, with the ledger recording the commit that activated each policy version. | MUST v1.x |
| FR-M12-13 | **Emergency / hotfix fast path**: a policy-defined reduced gate set for incident response, requiring Governor activation, time-boxed, and prominently marked in the ledger and PR. | SHOULD v1.x |
| FR-M12-14 | **Kill switch per agent class**: policy SHALL be able to disable a class of agent (e.g., all Trainers) organisation-wide. | MUST v1.x |

### M13 — XAI

| ID | Requirement | Priority |
|---|---|---|
| FR-M13-08 | **Counterfactual queries**: "what would have changed if criterion 3 had been present?" via targeted replay from checkpoint. | COULD v2 |
| FR-M13-09 | Calibration SHALL be tracked **per action class** (design, code, test, review), not only per agent, since agents are systematically over-confident in some classes and not others. | SHOULD v1 |
| FR-M13-10 | Every explanation surface SHALL display the **model and model version** that produced the decision, since explanations are not portable across models. | MUST v1 |

### M14 — Trainer

| ID | Requirement | Priority |
|---|---|---|
| FR-M14-10 | **Adversarial breaker**: a Breaker Agent SHALL generate failure cases for candidate policies, and a candidate SHALL be evaluated against them before promotion. | SHOULD v1.x |
| FR-M14-11 | **Quality-diversity archive**: the Trainer SHALL maintain a behavioural archive of candidates so that policy evolution does not converge prematurely on one style. | COULD v2 |
| FR-M14-12 | **Cross-team learning** SHALL be opt-in: a team's rework signal SHALL NOT feed another team's Trainer without explicit configuration. | MUST v1.x |
| FR-M14-13 | Trainer evaluation SHALL run the **golden story corpus** (FR-M27-03) as part of every regression, so a promoted policy has been proven on real work. | MUST v1.x |

### M16 — Replicator

| ID | Requirement | Priority |
|---|---|---|
| FR-M16-08 | An **internal registry** for agent packages and skill packs, with signing, versioning, download counts, and per-package yield telemetry. | SHOULD v1.x |
| FR-M16-09 | Skill pack **upgrade** SHALL run the agents bound to it through regression before the new version becomes active. | MUST v1.x |
| FR-M16-10 | **Retirement handover**: retiring an agent SHALL offer to transfer its procedural memory to a named successor, with the transfer ledger-recorded. | COULD v2 |

### M17 — Telemetry

| ID | Requirement | Priority |
|---|---|---|
| FR-M17-07 | **Tech-debt registry**: agents SHALL record debt they encounter or introduce (with justification), and the registry SHALL be queryable and exportable to the issue tracker. | SHOULD v1.x |
| FR-M17-08 | **Agent-vs-human baseline**: for the same task class, yield, cost, and cycle time SHALL be comparable against a human baseline captured before rollout. | SHOULD v1.x |
| FR-M17-09 | **Token efficiency ratio**: useful output tokens per total tokens, per agent and per phase, to expose wasteful loops. | SHOULD v1 |

---

## Part C — New SDLC Phase Requirements

### Phase 4 — Implementation (additions)

| ID | Requirement | Priority |
|---|---|---|
| FR-P4-10 | **Database migration safety**: migrations SHALL be classified reversible / irreversible; irreversible migrations and any migration touching a table above a configurable row count SHALL be high-blast-radius. | MUST v1 |
| FR-P4-11 | **Feature flag integration**: risky changes SHALL be wrappable in a feature flag (LaunchDarkly, Unleash, or config) by policy, with the flag recorded in the packet. | SHOULD v1.x |
| FR-P4-12 | **License compliance**: agent-added dependencies SHALL be checked against an allowed-license list before the packet exit gate. | MUST v1.x |
| FR-P4-13 | **Contract-first**: for new APIs, the OpenAPI / protobuf / GraphQL contract SHALL be generated and approved before implementation begins. | SHOULD v1.x |

### Phase 5 — Verification (additions)

| ID | Requirement | Priority |
|---|---|---|
| FR-P5-07 | **Mutation testing** SHALL be run on agent-authored tests at a configurable sample rate, and a mutation score below threshold SHALL flag the tests as weak. | SHOULD v1.x |
| FR-P5-08 | **Flake quarantine**: tests failing non-deterministically across retries SHALL be quarantined and reported, never silently retried to green. | MUST v1 |
| FR-P5-09 | **Property-based and fuzz test generation** for pure functions and parsers. | COULD v2 |
| FR-P5-10 | **Ephemeral test environments** via Testcontainers or equivalent for integration tests; the agent SHALL NOT be permitted to point tests at shared environments. | MUST v1.x |
| FR-P5-11 | **Contract tests** (consumer-driven) for cross-service packets (M22). | SHOULD v1.x |
| FR-P5-12 | **Performance regression gate**: for packets touching hot paths (declared or detected), a benchmark SHALL run and a regression above threshold SHALL block. | SHOULD v1.x |
| FR-P5-13 | **Accessibility testing** (axe-core or equivalent) SHALL be a gate criterion for front-end packets. | SHOULD v1.x |

### Phase 6 — Security (additions)

| ID | Requirement | Priority |
|---|---|---|
| FR-P6-06 | **Threat model artifact** (STRIDE or equivalent) SHALL be produced for changes classified security-relevant, attached to the design gate. | SHOULD v1.x |
| FR-P6-07 | **Privacy impact**: changes touching personal-data fields (detected via schema annotations or name heuristics) SHALL raise a privacy checklist at the design gate. | SHOULD v1.x |
| FR-P6-08 | **AI-BOM**: the SBOM delta SHALL include the models, skill packs, and policies that produced the change. | SHOULD v1.x |
| FR-P6-09 | **Provenance attestation**: agent-authored commits SHALL carry an in-toto / SLSA-style attestation referencing the ledger range, verifiable in CI. | SHOULD v1.x |

### Phase 7 — Review (additions)

| ID | Requirement | Priority |
|---|---|---|
| FR-P7-07 | **Multi-reviewer consensus**: for high-blast-radius changes, N reviewer agents with different policies SHALL critique independently and disagreements SHALL be surfaced, not averaged. | SHOULD v1.x |
| FR-P7-08 | Reviewer agents SHALL check for **secrets, debug artifacts, TODO markers, and commented-out code** as explicit criteria. | MUST v1 |

### Phases 8–9 — Release & Operate (additions)

| ID | Requirement | Priority |
|---|---|---|
| FR-P8-02 | **Deployment execution** (behind a Governor-enabled flag) via the organisation's existing pipeline, never via agent-issued cloud CLI commands. | COULD v2 |
| FR-P9-03 | **Incident linkage**: incidents from the organisation's incident system (PagerDuty, ServiceNow) SHALL be linkable to the ledger range of the deployed change, and linked incidents SHALL feed the Trainer as strong negative signal. | SHOULD v1.x |
| FR-P9-04 | **Post-merge human edit tracking**: human commits that modify agent-authored lines within N days of merge SHALL be captured as delayed rework signal. | SHOULD v1.x |

### New phase-adjacent agents

| Agent | Purpose | Priority |
|---|---|---|
| **Documentation Agent** | M29 | MUST v1.x |
| **Refactoring Agent** | Structural improvement packets, distinct from feature work, with strict behaviour-preservation gates (characterisation tests before, equivalence after) | SHOULD v1.x |
| **Dependency Agent** | Scheduled dependency updates with changelog reading, breaking-change detection, and its own gate | COULD v2 |
| **Legacy Comprehension Agent** | Reverse-engineers undocumented modules into procedural memory and ADRs before change — critical for brownfield IT-services work | SHOULD v1.x |
| **Breaker Agent** | FR-M14-10 | SHOULD v1.x |
| **Performance Agent** | FR-P5-12 | SHOULD v1.x |

---

## Part D — New Non-Functional Requirements

| ID | Requirement |
|---|---|
| NFR-14 | **Time-to-first-value**: from extension install to a completed dry-run of a sample story in under 15 minutes, with no manual configuration beyond a model credential. |
| NFR-15 | **Long-running stories**: a story SHALL survive being paused for 30 days and resume with all context intact. |
| NFR-16 | **Multi-day human absence**: a gate SHALL remain open indefinitely without resource consumption; the loop is fully unloaded at the checkpoint. |
| NFR-17 | **Concurrency**: 10 concurrent stories on a reference machine (8 cores, 16 GB) with no checkpoint loss. |
| NFR-18 | **Ledger scale**: 1 million entries with verification under 30 seconds and query latency under 200 ms for indexed filters. |
| NFR-19 | **Repository scale**: initial index of 1M LOC in under 10 minutes; incremental re-index of a 500-line change in under 2 seconds. |
| NFR-20 | **Air-gapped operation**: full functionality with a local model provider and no external network, verified in CI. |
| NFR-21 | **Localisation**: all user-facing strings externalised; UI SHALL ship with English and be translatable. Agent prompts remain English by default with a per-workspace override. |
| NFR-22 | **VS Code version compatibility**: a published compatibility matrix, tested against the current stable and the two prior minor releases. |
| NFR-23 | **Upgrade safety**: an upgrade SHALL never lose a checkpoint, a ledger entry, or a memory entry; verified by the golden corpus before and after. |

---

## Part E — New Security Requirements

| ID | Requirement |
|---|---|
| SEC-15 | **Prompt-injection classifier**: a lightweight classifier SHALL screen untrusted content before it enters agent context, and detections SHALL be ledger-recorded and surfaced. This complements, and does not replace, SEC-01 to SEC-05. |
| SEC-16 | **Tool-call anomaly detection**: tool invocations statistically unusual for an agent (new hosts, new paths, unusual volume) SHALL be flagged and, above a threshold, paused for human confirmation. |
| SEC-17 | **Sandbox escape tests** SHALL be part of the security regression suite. |
| SEC-18 | **Agent identity keys** SHALL be rotatable, and rotation SHALL be ledger-recorded. |
| SEC-19 | **Skill pack revocation**: a skill pack SHALL be revocable organisation-wide, and agents bound to it SHALL be paused until rebound. |
| SEC-20 | **Model output scanning**: generated code SHALL be scanned for known-malicious patterns, obfuscation, and embedded credentials before it reaches the working tree. |
| SEC-21 | **Data classification awareness**: repositories or paths tagged confidential SHALL be restricted to approved (e.g., local or in-region) model providers. |
| SEC-22 | **Human session security**: gate actions SHALL require a recent authentication (configurable, default 8 hours) and SHALL be blocked from an unauthenticated session. |
| SEC-23 | **Tenant isolation** for IT-services deployments: client repositories, memory, ledger, and models SHALL be isolatable per client with no cross-tenant memory or training leakage. |

---

## Part F — New Acceptance Criteria (Phase 1)

| # | Criterion |
|---|---|
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

---

## Part G — Ecosystem Integration

Meridian Loom is one product in a larger programme. The base spec does not name its integration points. These are all your existing build targets, so the interfaces should be declared now even where the implementation is later.

| ID | Integration | Requirement | Priority |
|---|---|---|---|
| ECO-01 | **Knowledge Brain** | The Memory Fabric SHALL be able to federate semantic memory from the Knowledge Brain graph as a read-only tier, so agents understand systems beyond the current repository. | SHOULD v1.x |
| ECO-02 | **Veritas (evolution engine)** | The Trainer Agent SHALL be implementable as a Veritas client: propose / isolate / apply / evaluate / attribute / promote maps directly onto M14, and the Breaker (FR-M14-10), quality-diversity archive (FR-M14-11), and Shapley attribution (FR-M13-06) are Veritas capabilities. Declare the interface so M14 does not re-implement them. | SHOULD v1.x |
| ECO-03 | **CodeTwin / CodeMap** | The CodeMap Viewer SHALL consume the CodeMap JSON format as its graph source rather than defining a new one. | MUST v1 |
| ECO-04 | **Codeweb / `.cgw`** | Cross-repository graphs (M22) SHALL be addressable by `.cgw` so multi-repo stories share one code graph. | SHOULD v1.x |
| ECO-05 | **ABCD (Agent's Bitbyte Code Depot)** | Where ABCD is the forge, M18 worktrees and M23 PRs SHALL target it natively, and the ledger SHALL be linkable from ABCD's own audit surface. | SHOULD v1.x |
| ECO-06 | **Navion MCP browser** | Available to agents as an MCP tool for documentation retrieval, under the egress allow-list. | COULD v2 |
| ECO-07 | **Epic-to-story upstream** | The autonomous-SDLC ecosystem's epic decomposition produces Jira-ingestible stories; M19 SHALL accept that artifact format directly. | SHOULD v1.x |
| ECO-08 | **teamlore** | Human-curated memory (FR-M7-11) SHALL be importable from a teamlore store. | COULD v2 |

---

## Part H — Enhancements to the Vision Document

Not requirements, but things `vision.md` should say so the requirements above have a home.

1. **A "Where agents write" section** — worktree isolation is an architectural stance, not a detail.
2. **The human organisation** alongside the agent organisation — roles, separation of duties, delegation.
3. **The portfolio layer** above the story layer.
4. **The learning loop's input sources** — currently only gate decisions; should also list CI failures, PR review comments, human edits, post-merge corrections, and incidents.
5. **Explicit ecosystem diagram** placing Meridian Loom among Knowledge Brain, Veritas, CodeTwin, and ABCD.

---

## Part I — Tensions in the Current Specification That Need Decisions

These are not features. They are places where the current text is silent or self-contradictory, and where building without a decision will produce rework.

| # | Tension | Recommended resolution |
|---|---|---|
| **T1** | **Agents edit the human's working tree.** FR-M1-05 applies diffs via the workspace edit API, which targets the open workspace. Nothing prevents an agent and a human editing the same file simultaneously. | Adopt M18 as a v1 MUST. Agents never write to the primary tree. |
| **T2** | **"Human approval" has no identity model.** FR-M12-07 requires approver identity but nothing defines how it is obtained or what roles exist. | Adopt M20 at least to FR-M20-01 for v1; roles in v1.x. |
| **T3** | **Immutable ledger vs. right to erasure.** FR-M10-01 forbids deletion; FR-M10-11 sets six-month minimum retention. GDPR and similar regimes require erasure of personal data on request. Story text and PR comments contain names. | Crypto-shredding (FR-M10-14): encrypt personal-data blobs with per-subject keys; erasure destroys the key; the chain stays intact because it hashes ciphertext. |
| **T4** | **Vision promises polyglot cross-service parallelism; Requirements is single-workspace.** §1.2 and FR-M4-09 talk about parallel packets, but M22 does not exist. | Add M22 in v1.x; state explicitly in §1.3 that v1 is single-repository. |
| **T5** | **The loop ends at "PR opened", not "merged".** FR-P7-04/05 stop at the PR. CI, review comments, and merge are outside the loop, so the Trainer never sees the strongest signals. | Adopt M23 in v1.x; extend L4 Delivery loop's exit criterion to "merged and CI green". |
| **T6** | **The runtime cannot be tested as specified.** No replay, no cassette, no golden corpus. Every test would need live model calls. | Adopt M27 as v1 MUST. It is a build enabler, not a feature. |
| **T7** | **§1.4 excludes VS Code Web but is silent on Remote.** Remote SSH / WSL / containers is where enterprise development actually happens, and the sidecar model must run on the remote host. | Add FR-M3-11 as v1 MUST and state the supported remote configurations in §1.4. |
| **T8** | **Gate actions are coarse.** Approve / Rework / Escalate / Waive cannot express "mostly right, fix this one thing" without a full loop re-entry, which costs budget and time. | Adopt Steer, partial acceptance, and clarifying questions (M25) in v1. These reduce cost more than any router optimisation. |
| **T9** | **Memory has no human authorship path.** FR-M7-02 makes procedural memory reviewable but nothing says a human can write it. The most valuable procedural memory (house standards) is human-authored. | Adopt FR-M7-11 in v1. |
| **T10** | **Trainer learns only from gate decisions.** FR-M14-01 harvests approved-vs-reworked. CI failures, human edits, review comments, and incidents are richer signals. | Extend FR-M14-01 to enumerate all signal sources once M23, M25, and P9 additions exist. |
| **T11** | **Confidence thresholds exist for autonomy tiers but not for individual actions.** FR-M12-03 uses calibration for tier promotion; nothing makes an agent *ask* when unsure on a specific action. | Adopt FR-M25-03 in v1. |
| **T12** | **No time-to-first-value target.** A product this deep can fail on setup friction alone. | Adopt NFR-14. |

---

## Part J — Recommended Priority Summary

### Add to v1 (before Phase 1 acceptance)

The items that, if missing, make Phase 1 either unsafe or untestable:

1. **M18** Workspace isolation & story branching (T1)
2. **M27** Deterministic replay, golden corpus, fault injection (T6)
3. **FR-M3-11** VS Code Remote support (T7)
4. **FR-M20-01** Authenticated human identity (T2)
5. **M25** Steer, clarifying questions, uncertainty escalation, dry-run, partial acceptance (T8, T11)
6. **FR-M7-11, FR-M7-13** Human-authored memory; budgeted context assembly (T9)
7. **M28** Code intelligence: LSP, tree-sitter, semantic search, reuse-first, large-file handling
8. **FR-M8-11, FR-M8-13, FR-M8-14** Redaction, backpressure, structured output
9. **FR-M10-12** Ledger query API
10. **FR-P4-10, FR-P5-08, FR-P7-08** Migration safety, flake quarantine, reviewer hygiene checks
11. **FR-M30-01, FR-M30-03, FR-M30-08** Doctor, state migration, clean uninstall
12. **ECO-03** CodeMap JSON as the graph source
13. **NFR-14** Time-to-first-value

### Add to v1.x (before enterprise rollout)

M19, M20 (full), M21, M22, M23, M26, M29, M30 (rest), the M7/M8/M10/M12/M14/M16 extensions, regulatory policy packs, crypto-shredding, tenant isolation, and the Phase 5–9 additions.

### Defer to v2

Scheduled tasks, counterfactual XAI, quality-diversity archive, dependency agent, deployment execution, retirement handover, annotations, batch epic ingestion.

---

*End of proposed additions. Each item is written so it can be lifted into Requirements.md unchanged once accepted.*
