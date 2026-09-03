# Meridian Loom — Requirement Gaps from the Honest Assessment

| | |
|---|---|
| **Document** | gaps-requirements.md |
| **Version** | 1.0 — proposed, for review |
| **Author** | Ravaleedhar Reddy |
| **Derived from** | `HONEST_ASSESSMENT.md` (September 2026) |
| **Complements** | `Requirements_Final.md` v2.1 · `Requirements-implementation.md` v2.0 |
| **Purpose** | The requirements that turn Meridian Loom from a competitor of Cursor, Copilot and Devin into the layer every one of them lacks |

---

## 0. Read this first — what "best of the best" has to mean

The assessment established three facts that cannot be engineered around:

1. **Head-on feature parity with the incumbents is not winnable.** Cursor has ~$2B ARR and 70% of the Fortune 500. Copilot has 4.7M paid seats and 90% of the Fortune 100. Ticket-to-PR shipped from GitHub in March 2026. No single-person programme out-features that.
2. **The adapter protocol already exists.** ACP won: JetBrains, Zed 1.0, Devin Desktop, a public registry, 25+ agents. Re-implementing it is waste.
3. **The market's unsolved problem is trust.** 84–90% adoption, 3% high trust, 46% of agent fixes rejected, and the 2026 buying decision has moved to governance and pricing predictability.

So "best of the best" is not "the best agent orchestra in VS Code." It is **the best governance, provenance and trust layer beneath every agent a team already uses** — one that works whether the agent is Meridian's own, Claude Code, Cursor, Copilot, Devin, or something an organisation built itself.

Every gap below serves that repositioning. Each cites the assessment finding it answers (`BT-n` for brutal truths, `S-n` for suggestions).

The existing 533 requirements are not discarded. They are re-sequenced (§9) so the trust layer ships first and the orchestra becomes an optional tier on top.

---

## 1. New Design Principles

| # | Principle | Consequence | Answers |
|---|---|---|---|
| **P20** | **Beneath, not against.** | Meridian Loom is a layer under the agents a team already runs. It never requires a team to abandon Claude Code, Cursor, Copilot or Devin to get value. | BT-2, BT-3, S-1 |
| **P21** | **Adopt the standard; own the gap.** | Where an open standard has won — ACP for editor↔agent, MCP for agent↔tool, A2A for agent↔agent — Meridian implements it rather than a bespoke equivalent, and builds only what the standard's ecosystem lacks. | BT-1, S-3 |
| **P22** | **Trust is the product; the orchestra is a tier.** | The ledger, gates, provenance and trust instruments are the base product and ship first. Multi-agent orchestration is an optional tier that a team enables after the base has earned its place. | BT-5, S-1, S-2 |
| **P23** | **First value in weeks, not phases.** | A real story, through a real agent, to a real PR, with a real ledger, before any screen beyond the minimum exists. The interface is built for the data that proved itself. | BT-4, S-2 |
| **P24** | **Vendor-independent by construction.** | Provenance lives in git and in a local signed ledger, never only in a vendor's retention window. Model, agent and editor are all substitutable. | S-1 |

---

## 2. New Modules

### M34 — ACP Host and Registry *(replaces M31's bespoke protocol)*

*The agent organisation.* **Answers BT-1 and S-3.** VS Code has no first-class ACP host. Meridian Loom becomes one — and the `AgentAdapter` protocol of M31 is re-based on ACP rather than invented alongside it.

| ID | Requirement | Priority |
|---|---|---|
| FR-M34-01 | Meridian Loom SHALL implement an **ACP client (host)** inside the VS Code extension host, per the Agent Client Protocol specification, so that any ACP-conformant agent can be launched as a subprocess and driven with sessions, streaming updates, permission-gated tool execution, and client-provided file-system and terminal access. | MUST v1 |
| FR-M34-02 | The `AgentAdapter` protocol (`FR-M31-01`) SHALL be **re-based on ACP**: an adapter is an ACP agent plus a Meridian governance manifest. Meridian SHALL NOT maintain a parallel bespoke protocol. Bridges (`FR-M31-05`) reduce to: ACP-native agents need no bridge; non-ACP agents get the community ACP adapters (e.g., Claude Code via Zed's bridge, Codex via `codex-acp`) or a thin Meridian shim. | MUST v1 |
| FR-M34-03 | Meridian SHALL integrate the **ACP Registry** as an installable source in the Adapter Bay, so any registered agent is one click from probation. | MUST v1 |
| FR-M34-04 | Meridian SHALL wrap every ACP permission request in its own governance: the permission the agent asks for is checked against the Meridian policy allow-list and the agent's tier **before** the ACP prompt reaches the human, and the decision is ledger-recorded. | MUST v1 |
| FR-M34-05 | Meridian SHALL contribute its ACP host implementation upstream under Apache 2.0 where the VS Code ACP integration is concerned, and SHALL track the open VS Code issue so that if Microsoft ships native ACP, Meridian layers on it rather than duplicating it. | SHOULD v1 |
| FR-M34-06 | Where VS Code standardises agent mode on MCP, Meridian SHALL expose its governed agents **as MCP servers** too, so a team using VS Code's native agent mode still gets Meridian's ledger and gates. | MUST v1.x |
| FR-M34-07 | An ACP agent that Meridian hosts SHALL be able to read, but never write, the Meridian ledger through a scoped ACP tool, so that agents can cite provenance in their own output. | SHOULD v1.x |

### M35 — External Agent Governance Proxy

*Record & assurance.* **Answers BT-2, S-1, P20.** The incumbents' agents produce PRs with no portable provenance. Meridian records and gates their work without replacing them.

| ID | Requirement | Priority |
|---|---|---|
| FR-M35-01 | Meridian SHALL operate as a **governance proxy for agents it does not own**: Claude Code, Cursor, Copilot, Codex, Devin, and any ACP or MCP agent. Their file writes, tool calls, and commits in the workspace SHALL be observed, ledger-recorded, and gate-checked with the same fidelity as Meridian's own agents. | MUST v1 |
| FR-M35-02 | Observation SHALL use, in order of preference: the agent's ACP session (if hosted by Meridian); the agent's OpenTelemetry export (e.g., Claude Code's OTel); the agent's git commit trailers (e.g., `Co-Authored-By`); and, as a fallback, file-system and git-hook observation of the story worktree. Each observed action SHALL record its **observation confidence** (`direct` / `telemetry` / `inferred`). | MUST v1 |
| FR-M35-03 | An external agent's pass SHALL appear in the Weave, the Ledger, and Agents Watch with a **vendor tag** and the observation confidence, never indistinguishable from a Meridian-native pass. | MUST v1 |
| FR-M35-04 | Gates SHALL apply to external-agent output: a PR opened by Copilot's coding agent or Devin SHALL be routable through Meridian's Verify, Security and Review gates before merge, with the human approval recorded in Meridian's ledger. | MUST v1 |
| FR-M35-05 | Meridian SHALL **ingest PRs from external agents** (via the CI/SCM connectors of M23) as stories, so that a ticket-to-PR flow run by Copilot's Jira integration still ends with a Meridian provenance record and a Meridian gate. | MUST v1.x |
| FR-M35-06 | Meridian SHALL never require an external agent to be modified, configured through Meridian, or routed through Meridian's model router. The proxy is observational and gating, not intercepting. | MUST v1 |
| FR-M35-07 | When multiple agents (Meridian-native and external) touch the same story, Meridian SHALL attribute each hunk to its agent and SHALL surface conflicts between agents as a distinct class of rework. | MUST v1.x |
| FR-M35-08 | Meridian SHALL maintain **observer adapters** per supported external agent, versioned against that agent's release, and SHALL degrade to `inferred` observation with a visible warning when an agent's telemetry format changes. | MUST v1.x |

### M36 — Flight Recorder Mode

*Record & assurance.* **Answers S-1, S-2, P22, P23.** The base product. The ledger, provenance and one gate — shippable in weeks, valuable with zero Meridian agents.

| ID | Requirement | Priority |
|---|---|---|
| FR-M36-01 | Meridian Loom SHALL be installable and useful in **Flight Recorder mode**: no Meridian agents, no orchestration, no loop runtime — only the ledger (M10, M11), worktree isolation (M18), the external-agent proxy (M35), human identity (M20-01), one configurable merge gate (`FR-M12-05`), and the Weave/Selvage interface. | MUST v1 |
| FR-M36-02 | Flight Recorder mode SHALL reach **first value in a single session**: install → point at a repository → run the team's existing agent → see the Weave and a provenance answer for any changed line. Target: under 15 minutes (`NFR-14`), with no Meridian agent configured. | MUST v1 |
| FR-M36-03 | Every commit touched in Flight Recorder mode SHALL carry a **git trailer** (`Meridian-Ledger: <seq range>`, and `Co-Authored-By` for the agent identity) so that provenance survives in git history outside any vendor's retention window and outside Meridian itself. | MUST v1 |
| FR-M36-04 | Flight Recorder mode SHALL export a **signed audit bundle** mapped to NIST SSDF's AI provenance recommendations and ISO/IEC 42001 record-keeping, and SHALL produce it for any date range, agent, or story without the orchestration tier installed. | MUST v1 |
| FR-M36-05 | The product SHALL be **tiered**: Flight Recorder (base) → Governor (adds gates, autonomy tiers, steer, questions, Decision Stream) → Orchestra (adds Meridian's own agents, loops, phase orchestrators, Trainer). Each tier SHALL be enableable without reinstalling and SHALL leave the tiers below fully functional if disabled. | MUST v1 |
| FR-M36-06 | The ledger schema SHALL be published as an **open specification** with a reference verifier, so that a third party can validate a Meridian audit bundle without Meridian installed. | SHOULD v1.x |
| FR-M36-07 | Flight Recorder mode SHALL run with **zero model calls** and zero model credentials. Its deterministic core (M33) handles attribution, diff, verification and export. | MUST v1 |

### M37 — Trust and Rejection Analytics

*Measurement.* **Answers BT-5.** 46% of agent fixes are rejected and 3% of developers report high trust. The product that makes those numbers visible, explainable and improvable is the product that sells.

| ID | Requirement | Priority |
|---|---|---|
| FR-M37-01 | Meridian SHALL compute **rejection rate** per agent (native and external), per action class, per phase, per story, and per repository — the proportion of proposed changes reworked, rejected in review, or reverted post-merge. | MUST v1 |
| FR-M37-02 | Every rejection SHALL carry a reason from the taxonomy (`E-GR-03`) and Meridian SHALL report the **rejection reason distribution** per agent, so a team sees *why* an agent's work is rejected, not only how often. | MUST v1 |
| FR-M37-03 | Meridian SHALL maintain a **trust score per agent per task class** (`FR-M17-01` trust score, extended) derived from first-pass yield, rejection rate, calibration error, post-merge revert rate, and incident linkage — and SHALL expose the decomposition. | MUST v1 |
| FR-M37-04 | Meridian SHALL support an **agent-vs-agent comparison** on the same story or packet (shadow mode, `FR-M25-07`, extended to external agents): the same task run by two agents, with yield, rejection reasons, cost and LLM ratio side by side. | SHOULD v1.x |
| FR-M37-05 | Meridian SHALL measure and report the **J-curve**: team-level throughput and stability before and after adoption, so the initial productivity dip DORA documents is visible as a phase rather than mistaken for failure. | SHOULD v1.x |
| FR-M37-06 | Meridian SHALL distinguish **greenfield from brownfield** work per story (by ratio of new files to modified files and by repository age of touched code) and SHALL report every trust metric split by that distinction, because the evidence shows the two behave differently by a factor of three or more. | MUST v1 |
| FR-M37-07 | Meridian SHALL detect and warn on **tokenmaxxing** — rising token spend without rising first-pass yield — per agent and per team. | SHOULD v1.x |
| FR-M37-08 | Trust metrics SHALL be exportable to the team's existing engineering-intelligence tooling (DORA-compatible metrics endpoint, OpenTelemetry) so Meridian's numbers land where leadership already looks. | SHOULD v1.x |

### M38 — Brownfield Comprehension

*Code & tools.* **Answers BT-5 (the 10% problem).** Agents gain 35–40% on greenfield and often ≤10% on complex legacy code. Enterprise IT services work is overwhelmingly the latter. This module is where Meridian can be genuinely better than agents built for greenfield demos.

| ID | Requirement | Priority |
|---|---|---|
| FR-M38-01 | Before any agent modifies a module in a repository, Meridian SHALL be able to produce a **comprehension record** for that module: dependency graph, callers and callees (LSP), test coverage, change frequency and authorship from git history, known incidents linked, and detected conventions — deterministically, with no model call. | MUST v1.x |
| FR-M38-02 | The comprehension record SHALL feed context assembly (`FR-M7-13`) with **precedence over skill-pack defaults**, formalising `FR-P4-03` — repository reality outranks skill defaults. | MUST v1.x |
| FR-M38-03 | Meridian SHALL compute a **brownfield risk score** per packet from module age, coupling, coverage, and change-failure history, and SHALL raise gate strictness and the blast-radius classification for high-risk packets automatically. | MUST v1.x |
| FR-M38-04 | The Legacy Comprehension Agent (roster, §6.10) SHALL be able to **generate characterisation tests** for an uncovered module before change, and Meridian SHALL block modification of an uncovered high-risk module until characterisation tests exist. | MUST v1.x |
| FR-M38-05 | Meridian SHALL maintain a per-repository **comprehension memory** — the accumulated comprehension records — as procedural memory that improves with every story, so the second change to a module is cheaper and safer than the first. | SHOULD v1.x |
| FR-M38-06 | Meridian SHALL report **agent effectiveness by module age and complexity** so a team can see where agents genuinely help and where they should not be used — and policy SHALL be able to restrict agent autonomy tier by module risk score. | MUST v1.x |

### M39 — Cost Predictability and Cross-Vendor Spend

*Intelligence & economics.* **Answers the 2026 buying decision.** Fixed-fee subscriptions are giving way to usage pricing and teams report surprise 3–10× bills. Meridian sees every agent's spend in one place.

| ID | Requirement | Priority |
|---|---|---|
| FR-M39-01 | Meridian SHALL record and report spend **across every agent it observes**, native and external, by vendor, model, agent, story, team and cost centre — the cross-vendor bill a team cannot otherwise see. | MUST v1.x |
| FR-M39-02 | Meridian SHALL enforce **spend ceilings** on external agents it hosts via ACP (by pausing the session at a checkpoint) and SHALL warn on external agents it only observes. | MUST v1.x |
| FR-M39-03 | Meridian SHALL forecast **monthly spend per team** from the trailing ledger and SHALL alert when the forecast crosses a configured budget, before the bill arrives. | SHOULD v1.x |
| FR-M39-04 | Meridian's own pricing model SHALL be **predictable by design**: the Flight Recorder tier makes no model calls and has no usage-based cost; the Governor and Orchestra tiers report their own model spend in the same ledger as everyone else's. | MUST v1 |
| FR-M39-05 | Meridian SHALL report **cost per merged change with and without Meridian's deterministic paths**, so the Deterministic Engine's saving (`FR-M33-07`) is visible against the vendor bill. | SHOULD v1.x |

---

## 3. Amendments to Existing Modules

| ID | Amendment | Answers |
|---|---|---|
| **M31** | The Agent Adapter Framework SHALL be re-based on ACP per `FR-M34-02`. `FR-M31-01` (bespoke protocol), `FR-M31-05` (six bridges) and `FR-M31-11` (SDK conformance suite) are **superseded** by ACP conformance plus a Meridian governance manifest. Retain `FR-M31-02`…`04`, `06`…`10`, `12`…`15` unchanged — discovery, validation, hot plug, probation, trainable surfaces, portability and governance are Meridian's, not ACP's. | BT-1 |
| **M12** | `FR-M12-11` compliance export SHALL map to **NIST SSDF AI provenance recommendations** in addition to ISO/IEC 42001 and EU AI Act Article 12, because enterprise procurement grounds audit requirements in SSDF first. | Assessment §3 |
| **M17** | Add rejection rate, trust score decomposition, greenfield/brownfield split and J-curve to `FR-M17-01`'s KPI set (from M37). | BT-5 |
| **M24** | `FR-M24-04` git-blame decoration SHALL read Meridian-Ledger trailers and `Co-Authored-By` trailers from **any** agent, not only Meridian's. | S-1 |
| **M25** | `FR-M25-07` shadow mode SHALL support external agents as the comparison, not only Meridian adapters. | BT-5 |
| **M32** | The Simulation Core SHALL ship scenarios for **external-agent observation** (a Claude Code session, a Copilot PR, a Devin run) so the proxy's interface is built against realistic traces. | BT-4 |
| **§1.3 Out of scope** | Add: "Competing on agent capability with Claude Code, Cursor, Copilot or Devin. Meridian's own agents exist to prove the governance layer and to fill roles a team has no other agent for — not to out-code the incumbents." | BT-2, BT-3 |
| **§6.10 Roster** | The prebuilt roster is **demoted to the Orchestra tier**. Flight Recorder and Governor tiers ship with zero Meridian agents and are complete without them. | P22 |

---

## 4. New Non-Functional Requirements

| ID | Requirement | Priority |
|---|---|---|
| NFR-28 | **Flight Recorder first value**: install to a provenance answer for a changed line, using the team's existing agent, in under 15 minutes with no model credential. | MUST v1 |
| NFR-29 | **Observation overhead**: the external-agent proxy SHALL add no more than 5% latency to an observed agent's session and SHALL never block an agent it does not host. | MUST v1 |
| NFR-30 | **Standards conformance**: Meridian's ACP host SHALL pass the ACP conformance suite; its MCP server exposure SHALL pass MCP validation. Both in CI. | MUST v1 |
| NFR-31 | **Portable verification**: a Meridian audit bundle SHALL verify with the open reference verifier (`FR-M36-06`) on a machine with no Meridian installed. | SHOULD v1.x |
| NFR-32 | **Vendor drift resilience**: an external agent's telemetry format change SHALL degrade observation to `inferred` with a warning within one session, never to silence. | MUST v1.x |

---

## 5. New Security Requirements

| ID | Requirement | Priority |
|---|---|---|
| SEC-27 | External agents observed by the proxy SHALL never gain access to Meridian's credentials, policy, or ledger signing key. Observation is one-way. | MUST v1 |
| SEC-28 | ACP permission requests from a hosted agent SHALL be governed by Meridian policy before the human sees them (`FR-M34-04`); an agent SHALL NOT be able to escalate a permission by re-requesting it. | MUST v1 |
| SEC-29 | The audit bundle's signature SHALL be verifiable without trusting Meridian's servers or the vendor of any agent whose work it records. | MUST v1 |

---

## 6. New Acceptance Criteria

| # | Criterion |
|---|---|
| AC-30 | **Flight Recorder first value.** On a fresh machine with no model credential, Meridian is installed, pointed at a repository, and the team's existing Claude Code (or Cursor, or Copilot) session is run. Within 15 minutes the Weave shows that session's passes with a vendor tag, and any changed line answers "which agent, what was it told, who approved it." |
| AC-31 | **ACP host.** An agent from the ACP Registry is installed via the Adapter Bay, enters probation, and completes a packet under Meridian governance, with every ACP permission request policy-checked before the human sees it. |
| AC-32 | **External PR gating.** A PR opened by Copilot's coding agent from a Jira ticket is ingested, routed through Meridian's Security and Review gates, and merged only after a recorded human approval — with the Copilot pass, the gates, and the approver all in one ledger range. |
| AC-33 | **Provenance survives the vendor.** Meridian is uninstalled. `git log` still shows the Meridian-Ledger and Co-Authored-By trailers on every agent-authored commit, and the exported audit bundle verifies with the reference verifier. |
| AC-34 | **Rejection analytics.** After 20 stories across two agents, the Trust Observatory shows rejection rate and reason distribution per agent, split greenfield/brownfield, and the numbers reconcile to the ledger. |
| AC-35 | **Brownfield gate.** A packet targeting an uncovered, high-risk legacy module is blocked until characterisation tests exist, and the block is explained with the module's comprehension record. |
| AC-36 | **Tiering.** The Orchestra tier is disabled. Flight Recorder and Governor continue to function fully; every screen that depended on Orchestra data shows its empty state, not an error. |
| AC-37 | **Cross-vendor spend.** A story worked by one Meridian agent and one external agent shows both agents' spend, by vendor and model, in one view that reconciles to the ledger. |

---

## 7. New Risks

| # | Risk | Impact | Mitigation |
|---|---|---|---|
| **R26** | **Microsoft ships native ACP in VS Code and Meridian's host is obsolete** | Medium | `FR-M34-05` — contribute upstream, layer governance on whatever host exists; the value is the ledger and gates, not the host |
| **R27** | **External agents change telemetry and the proxy goes blind** | High | `FR-M35-08` observer adapters versioned per agent release; `NFR-32` degrade to `inferred` with a warning, never silence; git-trailer fallback |
| **R28** | **Incumbents ship portable provenance themselves** (Claude Code already has `Co-Authored-By`) | High | Meridian's differentiator is *cross-vendor* provenance in one signed ledger with gates — a single vendor's trailer does not give a team a view across the three agents they actually run |
| **R29** | **The orchestra tier never earns its place and the product is "just" a flight recorder** | Low-impact, high-probability | That is an acceptable outcome. The flight recorder alone is a viable product. Design so that this outcome is a success, not a failure. |
| **R30** | **Repositioning as a layer beneath the incumbents makes Meridian dependent on their goodwill** | Medium | Observation via open surfaces (ACP, OTel, git) that no vendor can revoke without breaking their own users; `FR-M36-06` open ledger spec |

---

## 8. New Decisions

| # | Decision | Owner | Needed by |
|---|---|---|---|
| **D19** | Whether to open-source the ledger core and the ACP host (Apache 2.0) and sell the Governor and Orchestra tiers — the open-core model that ACP's own success suggests | Founder | Before first release |
| **D20** | Which external agents get first-class observer adapters in v1: Claude Code (OTel + trailers) and Copilot (SCM) are certain; Cursor, Codex, Devin depend on their available surfaces | Architecture | Flight Recorder release |
| **D21** | Whether Meridian's prebuilt agents ship at all in v1, or the Orchestra tier waits until the Governor tier has 20 real stories of evidence | Product | Before C2 |
| **D22** | The employment and IP question raised in the assessment (BT-6): sanctioned internal initiative, clean-room independent build, or open-source contribution — **must be resolved before any further code is written** | Founder + legal | **Now** |

---

## 9. Re-sequenced Delivery — the trust layer first

This supersedes the S0 → GUI → C1 → C2 order in `Requirements-implementation.md` v2.0, which the assessment found to be the most expensive way to discover the thesis is wrong (BT-4).

| Phase | Name | Contents | Exit |
|---|---|---|---|
| **F0** | **Flight Recorder** | M10, M11, M18, M20-01, M33 (attribution/diff/verify subset), M35 (Claude Code + Copilot observers), M36, the Weave + Selvage screens only, git trailers, audit bundle | **AC-30, AC-33**. A team's existing agent is recorded and provenance survives uninstall. **Target: weeks.** |
| **F1** | **Governor** | M12 (v1 subset), M25 (steer, questions), M20 (roles), M37 (trust analytics), M39 (spend), Gate Room + Decision Stream + Trust Observatory screens, M34 (ACP host) | **AC-31, AC-32, AC-34, AC-37**. External agents are gated and their trust measured. |
| **F2** | **Evidence gate** | Twenty real stories through F0+F1 with the team's own agents | §10.2 quality bar — **but measured on external agents.** If the governance layer does not demonstrably improve rejection rate or catch defects the agents missed, stop here and ship the Flight Recorder as the product. |
| **F3** | **Orchestra** | M4, M31 (re-based on ACP), M6, M7, M8, M9, M28, M38, the prebuilt roster as ACP agents, the full GUI | The v2.0 C2 gate (AC-01…AC-29). Only reached if F2 proved the layer earns the tier. |
| **F4+** | As `Requirements-implementation.md` C3–C6 | Learning, portability, scale, compliance, differentiation | Unchanged |

**The GUI is built for what F0–F2 proved, not for what the specification imagined.** The Simulation Core (M32) still exists — as the test harness it was always going to become — but 44 screens are no longer built against it before a single real story runs.

---

## 10. Competitive Position After These Gaps

| Capability | Cursor | Copilot | Claude Code | Devin Desktop | **Meridian Loom (after gaps)** |
|---|---|---|---|---|---|
| Writes code | ★★★ | ★★★ | ★★★ | ★★★ | ★ (Orchestra tier, optional) — *not the point* |
| Ticket → PR | ★★ | ★★★ | ★★ | ★★★ | Via any of them, **gated and recorded** |
| Hosts third-party agents | — | — | — | ★★ (ACP) | ★★★ (ACP host **in VS Code**, plus governance) |
| Cross-vendor provenance in one ledger | — | — | — | — | **★★★ — no one else** |
| Tamper-evident, signed, exportable audit | — | partial (enterprise) | partial (OTel, cloud only) | — | **★★★** |
| Provenance that survives the vendor (git trailers) | — | — | ★ (Co-Authored-By) | — | ★★★ (cross-vendor, ledger-linked) |
| Gates external agents' PRs before merge | — | own only | own only | own only | **★★★ — any agent** |
| Rejection and trust analytics per agent | — | — | — | — | **★★★** |
| Brownfield risk scoring and characterisation gates | — | — | — | — | **★★★** |
| Cross-vendor spend and forecast | — | — | — | — | **★★★** |
| Model call must justify itself (`why_llm`) | — | — | — | — | **★★★** |
| Works with zero model credentials | — | — | — | — | **★★★ (Flight Recorder)** |
| Compliance evidence (SSDF, 42001, AI Act) | partial | partial | partial | — | **★★★** |

Every row where Meridian scores ★★★ alone is a row the incumbents structurally cannot fill, because each of them is one vendor and the value is in seeing across all of them.

That is what "best of the best" means for this product.

---

*Every item above is written to be lifted into `Requirements_Final.md` v2.2 once accepted. `D22` must close first.*
