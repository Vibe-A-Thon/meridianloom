# Meridian Loom — Futures Requirements

| | |
|---|---|
| **Document** | futures_requirements.md |
| **Version** | 1.0 — proposed, for review |
| **Author** | Ravaleedhar Reddy |
| **Derived from** | `futures.md` (9 September 2026), which is itself derived from the `status.md` re-audit at commit `4b79bef` and from vendor documentation accessed 6–9 September 2026 |
| **Complements** | `Requirements_Final.md` v2.1 · `gaps-requirements.md` v1.0 · `gaps_initiation.md` v1.0 |
| **Governed by** | `futures-implementation.md` — the phase-by-phase build order for everything specified here |
| **Purpose** | To turn the 36 `FUT-nnn` proposals in `futures.md` into normative, testable requirements that slot into the existing specification family without renumbering anything |
| **Scale** | 6 new modules · 84 functional requirements · 11 NFRs · 8 security requirements · 12 acceptance criteria · 5 principles · 6 risks · 7 decisions |

---

## 0. Read this first — what this document is and is not

`futures.md` is an assessment. It recommends, it does not specify. This document is the specification: every proposal in it is decomposed into clauses that can pass or fail, with the `FUT-nnn` identifier retained on every row so the provenance of each requirement stays visible.

**Three constraints govern everything below.**

1. **Nothing here renumbers or supersedes an existing requirement.** New modules start at `M41`, non-functional requirements at `NFR-33`, security requirements at `SEC-31`, acceptance criteria at `AC-41`, risks at `R31`, decisions at `D36`, principles at `P25`. Where a proposal refines existing scope, it appears in §8 as an amendment to the module that owns it, not as a new module.
2. **This is not accepted scope.** Accepting it is an owner decision. `futures-implementation.md` §1 states which requirements block a claim already being made and which are optional.
3. **The three findings that motivated this document are defects, not features.** `status.md` findings G-01 (silent 1,000-row truncation), G-02 (twelve computed instruments with no interface consumer) and G-03 (two parallel steering implementations) are correctness problems in shipped code. They are specified here as `M41`, `FR-M46-01`/`02` and `AMD-M25` respectively so they are tracked, but they should be read as a bug list with acceptance tests, not as a roadmap.

### 0.1 What changed in the product that made these requirements necessary

The F1 Governor is engineering-complete and tagged. That is the reason this document exists: a governance layer that computes the right numbers but shows none of them, over a window that silently truncates, on an identity anyone can assert, is not yet a product a regulated buyer can rely on. Every requirement below closes one of those gaps, or protects the evidence chain from a dependency Meridian does not control.

### 0.2 Priority and release target

| Priority | Meaning | Release target |
|---|---|---|
| **P0** | The product makes a claim today that this requirement is needed to support. Shipping without it means the claim is unsupported. | **MUST v1** |
| **P1** | Closes a gap a competent buyer or auditor will find. Not blocking the current claim; blocking the next one. | **MUST v1.x** |
| **P2** | Widens the advantage, or governs an investment decision. Conditional on evidence. | **SHOULD v1.x** unless stated |

---

## 1. New design principles

Continuing `P1`–`P19` (`Requirements_Final.md` §3) and `P20`–`P24` (`gaps-requirements.md` §1).

| # | Principle | Consequence | Source |
|---|---|---|---|
| **P25** | **A number that cannot state its coverage is not evidence.** | Every computed figure carries the population it was computed over, what was excluded and why. A metric over an unknown or partial window reads `insufficient_coverage`, never a plausible number. Silence about truncation is a defect of the same class as a wrong value. | G-01, FUT-008, FUT-019, FUT-020 |
| **P26** | **Unknown is a state, never a residual.** | No classification derives one category by subtracting the others. Attribution, cost provenance, approval class and observation confidence each carry an explicit unknown value that is reported rather than absorbed into the nearest confident answer. | FUT-019, FUT-031, FUT-023 |
| **P27** | **A control is only as strong as the boundary it binds at.** | Every control declares where it actually enforces and what could bypass it. A control that binds in the editor is never described as enforced. Meridian states the limitations of its own controls at least as plainly as the vendors it reviews state theirs. | FUT-023, FUT-024, FUT-025 |
| **P28** | **Evidence outlives the tool that produced it.** | No evidence claim may depend on a vendor's retention window, a vendor's servers, a vendor's continued existence, or on Meridian's own continued installation. Where a dependency is unavoidable, its window is recorded and its expiry is marked. | FUT-005, FUT-022, FUT-027, FUT-032, FUT-033 |
| **P29** | **Build the next thing only where evidence says it pays.** | Investment beyond the current tier is gated on measured outcome, with the thresholds written down before the measurement runs. A capability that cannot demonstrate its value is retired, not extended. | FUT-009, FUT-034, FUT-035 |

---

## 2. M41 — Evidence Completeness and Coverage

*Record and assurance.* **Answers `status.md` G-01, and FUT-001, FUT-004, FUT-008, FUT-019, FUT-020, FUT-026.**

The module that makes every reported number true, or honestly says it is not. This is the highest-priority work in the specification because the Governor already reports figures that are silently partial.

| ID | Requirement | FUT | Priority |
|---|---|---|---|
| FR-M41-01 | Every provenance answer SHALL carry, per field, its **source**, its **capture method**, the **version of the contract it was derived from**, and its **capture timestamp**. | FUT-001 | MUST v1 |
| FR-M41-02 | Every provenance field SHALL carry one of exactly four states: `observed`, `inferred`, `unknown`, or `redacted`. Signing an artefact SHALL NOT promote an `inferred` field to `observed`. | FUT-001 | MUST v1 |
| FR-M41-03 | On a labelled corpus of at least 200 mixed human and agent edits, Meridian SHALL publish precision, recall and unknown-coverage figures. Fields labelled `observed` SHALL achieve at least 95% precision, and no prompt or approver field SHALL ever be populated by invention. | FUT-001 | MUST v1 |
| FR-M41-04 | Attribution SHALL report three mutually exclusive states — `agent`, `human`, `unattributed` — and SHALL NEVER derive any state by subtracting the others from a total. | FUT-019 | MUST v1 |
| FR-M41-05 | Every `unattributed` span SHALL carry the reason it could not be resolved, from a closed vocabulary: `no_signal`, `formatter_rewrite`, `squashed_history`, `pre_installation`, `unsupported_vendor`, `excluded_path`. | FUT-019 | MUST v1 |
| FR-M41-06 | Every trust metric SHALL be reported alongside the attribution coverage of its population. A metric whose coverage falls below a configurable floor SHALL read `insufficient_coverage` and SHALL NOT display a value. | FUT-019 | MUST v1 |
| FR-M41-07 | `ledger.query` SHALL support cursor pagination across the full history, and SHALL NOT clamp a caller to a fixed maximum row count without reporting that it did so. | FUT-020 | MUST v1 |
| FR-M41-08 | Every analytic result SHALL carry `rowsConsidered`, `rowsAvailable`, `truncated` and the inclusive sequence range it covered. | FUT-020 | MUST v1 |
| FR-M41-09 | Any surface displaying a figure computed over a truncated population SHALL state that in text at the point of display, and SHALL disable any projection or forecast derived from it. | FUT-020 | MUST v1 |
| FR-M41-10 | Every imported source event SHALL carry a stable deduplication key, a source offset, an ingest timestamp and a replay status. | FUT-004 | MUST v1 |
| FR-M41-11 | Ingestion SHALL be correct under duplicate delivery, out-of-order arrival, clock skew, process restart, partial files, API pagination, offline queueing and disk exhaustion. A 100,000-event fixture SHALL reconcile exactly after replay, with no silent loss and no double counting. | FUT-004 | MUST v1 |
| FR-M41-12 | Data that is intentionally dropped or is unrecoverable SHALL surface as a named coverage gap, never as an absence. | FUT-004 | MUST v1 |
| FR-M41-13 | Meridian SHALL version the definition of the proposed-change unit, the rejection taxonomy, the observation window, the treatment of late rejections, censoring rules, cost allocation and the greenfield/brownfield boundary, and SHALL record which version produced each reported figure. | FUT-008 | MUST v1 |
| FR-M41-14 | Every reported figure SHALL carry its sample count, a confidence interval where the statistic admits one, and the proportion of missing data. An empty sample SHALL read `insufficient_evidence`, never zero. | FUT-008 | MUST v1 |
| FR-M41-15 | Agent rankings SHALL be suppressed where cohorts or evidence coverage are not comparable, and the suppression reason SHALL be shown. | FUT-008 | MUST v1 |
| FR-M41-16 | Meridian SHALL attribute repository history predating its own installation from git history alone, at `inferred` confidence, and SHALL never label a backfilled attribution `observed`. | FUT-026 | MUST v1.x |
| FR-M41-17 | Backfill SHALL be deterministic and reproducible over a repository of at least 5,000 commits, and SHALL publish a coverage report naming every span it could not resolve and why. | FUT-026 | MUST v1.x |

---

## 3. M42 — Enforcement Assurance

*Governance.* **Answers FUT-002, FUT-003, FUT-015, FUT-023, FUT-024, FUT-025.**

The module that makes a control mean what a buyer will assume it means. Three reviewed vendors document approval paths that look human in telemetry and are not; two state in their own documentation that their client-side policy is not a security boundary. Meridian must be measurably more honest than that, and enforce at a boundary a developer cannot walk around.

| ID | Requirement | FUT | Priority |
|---|---|---|---|
| FR-M42-01 | A merge authorisation SHALL bind repository, pull-request identity, base and head commit identifiers, diff digest, policy version, test and security evidence, authenticated approver identity, and an expiry. | FUT-002 | MUST v1 |
| FR-M42-02 | Any change to a bound element SHALL invalidate the authorisation. Force-push, rebase, changed base, changed policy version, expired identity, replayed webhook and missing evidence SHALL each be proven to block a merge by test. An unchanged, valid pull request SHALL merge normally. | FUT-002 | MUST v1 |
| FR-M42-03 | Merge authorisation SHALL be enforced **outside the editor** through a protected-branch or merge-queue check, such that a developer who has never installed Meridian cannot merge a governed change without it. | FUT-002 | MUST v1 |
| FR-M42-04 | Meridian SHALL distinguish a locally asserted git identity from a verified OIDC or SCM identity, and SHALL record which was used for every human action. | FUT-003 | MUST v1 |
| FR-M42-05 | A git name and email SHALL NEVER satisfy a policy requiring a verified approver. | FUT-003 | MUST v1 |
| FR-M42-06 | Verified identity SHALL be bound to the session and to the decision, and SHALL be re-checked at gate execution rather than only at session start. Revoking a user SHALL prevent new approvals within a documented target of five minutes. | FUT-003 | MUST v1 |
| FR-M42-07 | Every approval and every permission decision SHALL carry an `approvedBy` class from a closed vocabulary: `human_verified`, `human_asserted`, `policy_rule`, `model_classifier`, `bypass_actor`, `unknown`. | FUT-023 | MUST v1 |
| FR-M42-08 | A non-human `approvedBy` class SHALL NEVER satisfy a policy requiring human approval, and SHALL NEVER be counted as a human approval in any metric. Tests SHALL cover an auto-mode classifier verdict, a policy allow-rule, an agent code-review approval satisfying a required-approval rule, and a repository ruleset bypass actor. | FUT-023 | MUST v1 |
| FR-M42-09 | Meridian SHALL detect and record circumvention of any control it reports as in force. The named detections are: a repository ruleset bypass actor, a client-edited tool allow-list, content exclusion that does not apply in agent mode, a removed or disabled provenance hook, and telemetry disabled after having been enabled. | FUT-024 | MUST v1.x |
| FR-M42-10 | Each bypass detection SHALL produce a ledger entry and SHALL downgrade the affected coverage claim within one session. Meridian SHALL weaken its own claim rather than remain silent. | FUT-024 | MUST v1.x |
| FR-M42-11 | Every control Meridian displays SHALL declare its enforcement point from a closed vocabulary: `editor`, `extension_host`, `sidecar`, `scm`, `ci`, `advisory_only`; and SHALL declare whether it is enforced or advisory. | FUT-025 | MUST v1.x |
| FR-M42-12 | No surface SHALL render a client-side control as "enforced". The audit bundle SHALL record the effective enforcement point for every decision, such that an independent reviewer given only the bundle can state, for each decision, what could have bypassed it and who could have done so. | FUT-025 | MUST v1.x |
| FR-M42-13 | Organisation policy SHALL be distributable as a signed bundle carrying an activation time, an expiry and explicit precedence over local policy. | FUT-015 | SHOULD v1.x |
| FR-M42-14 | An online client SHALL apply an emergency policy revocation within five minutes. An offline hosted run SHALL stop when its policy lease expires. | FUT-015 | SHOULD v1.x |
| FR-M42-15 | A policy simulator SHALL explain which historical verdicts a proposed policy change would have altered, before that change is activated. | FUT-015 | SHOULD v1.x |

---

## 4. M43 — Evidence Durability and Portability

*Record and assurance.* **Answers FUT-005, FUT-006, FUT-011, FUT-016, FUT-027, FUT-032, FUT-033.**

The module that is the actual moat. Of the adjacent products reviewed, one documents audit logs as "immutable" with no verification mechanism, and another caps retention at 180 days against a multi-year regulatory obligation. This module is the difference between "immutable because we operate it correctly" and "verifiable by a third party with no access to our systems".

| ID | Requirement | FUT | Priority |
|---|---|---|---|
| FR-M43-01 | Meridian SHALL support optional customer-controlled receipt storage for signed ledger roots, with signer enrolment and signing-key rotation and revocation. | FUT-005 | MUST v1.x |
| FR-M43-02 | An independent verifier SHALL detect a changed entry, and SHALL detect rollback or truncation relative to a previously witnessed root. It SHALL distinguish three separate verdicts: valid signature, trusted signer, and evidence coverage. | FUT-005 | MUST v1.x |
| FR-M43-03 | Without a witness, Meridian SHALL NOT claim to detect wholesale ledger replacement by a machine administrator, and the documentation and interface SHALL say so. | FUT-005 | MUST v1.x |
| FR-M43-04 | The ledger SHALL support a configurable multi-year retention target with a documented compaction and archival path. | FUT-027 | MUST v1.x |
| FR-M43-05 | An entry archived, compacted and restored SHALL still verify against its signed tree head and its inclusion proof. Meridian SHALL publish measured storage growth per 10,000 entries and the restore time for a three-year archive. | FUT-027 | MUST v1.x |
| FR-M43-06 | Meridian SHALL define collection profiles, raw-content consent, field and path redaction, recipient-specific export filtering, retention, erasure and backup-key behaviour. | FUT-006 | MUST v1.x |
| FR-M43-07 | Seeded secrets and identifiers SHALL be tested across ingestion, error logs, bundle export, archives and restore. The default metadata-only profile SHALL persist none of them. | FUT-006 | MUST v1.x |
| FR-M43-08 | An erased subject SHALL remain unreadable after a backup restore, while ciphertext-chain verification continues to succeed. Redaction and erasure SHALL be visible as coverage gaps in provenance answers. | FUT-006 | MUST v1.x |
| FR-M43-09 | Meridian SHALL produce a versioned attestation linking the commit or build artefact, the policy decision, the reviewer identity assurance, the test and security evidence, dependency and SBOM digests, and the ledger root. | FUT-011 | SHOULD v1.x |
| FR-M43-10 | Exporting to an in-toto-compatible envelope SHALL preserve source evidence identifiers. Build provenance and agent activity SHALL remain distinct predicates, and no supply-chain level SHALL be claimed from the existence of a signature. | FUT-011 | SHOULD v1.x |
| FR-M43-11 | The `Meridian-Ledger:` commit trailer SHALL be published as a stable, versioned specification with a reference parser, such that a third party can parse it from `git log` alone, resolve it to a bundle range and verify that range using only the published specification. | FUT-032 | MUST v1.x |
| FR-M43-12 | Meridian SHALL ship a headless collector and verifier usable without the extension, with documented export, erase and uninstall paths. | FUT-016 | SHOULD v1.x |
| FR-M43-13 | Exported evidence SHALL retain its schema version, source identifiers and redaction labels, such that departure from Meridian leaves the customer with readable records. | FUT-016 | SHOULD v1.x |
| FR-M43-14 | Meridian SHALL provide opt-in export to existing OTLP and evaluation systems without those systems becoming the record of authority. | FUT-016 | SHOULD v1.x |
| FR-M43-15 | One customer SHALL reproduce the same signed change evidence from two supported editors and two SCM providers with no Orchestra tier installed, and SHALL verify both bundles with the open verifier on a clean machine. This SHALL be performed **before** any external material makes the vendor-independence claim. | FUT-033 | SHOULD v1.x |

---

## 5. M44 — Vendor Surface and Supply-Chain Integrity

*Code and tools.* **Answers FUT-007, FUT-022, FUT-028, FUT-029, FUT-036.**

The module that governs everything Meridian depends on but does not control: another vendor's telemetry, another vendor's retention window, another publisher's binary, another body's protocol version. Both interoperability protocols currently leave agent identity optional or unsolved, and neither registry treats namespace ownership as a trust signal.

| ID | Requirement | FUT | Priority |
|---|---|---|---|
| FR-M44-01 | An ACP or MCP session SHALL be bound to a verifiable agent identity — executable digest, resolved version, and publisher where available — never to a self-asserted name alone. | FUT-028 | MUST v1.x |
| FR-M44-02 | Attribution to an unverified agent identity SHALL be labelled as unverified in the ledger and on every surface. Changing an agent binary without changing its declared name SHALL produce a different recorded identity and a visible warning. | FUT-028 | MUST v1.x |
| FR-M44-03 | Every installed adapter SHALL be pinned by content digest, and Meridian SHALL record the exact artefact executed. | FUT-029 | MUST v1.x |
| FR-M44-04 | Installation from a registry SHALL resolve and pin a concrete version, and SHALL refuse an unpinned execution entry unless explicitly overridden with a recorded acknowledgement. | FUT-029 | MUST v1.x |
| FR-M44-05 | Silent drift of a pinned adapter on a later launch SHALL be refused, and the refusal SHALL name the expected and the observed digest. | FUT-029 | MUST v1.x |
| FR-M44-06 | Every ledger entry derived from an external contract SHALL record that contract's version: the telemetry semantic-convention version, the agent-protocol version, the tool-protocol revision, and the observer adapter version. | FUT-036 | SHOULD v1.x |
| FR-M44-07 | A rename or breaking revision in an external contract SHALL be detected in CI and SHALL degrade coverage visibly, never mis-map silently. | FUT-036 | SHOULD v1.x |
| FR-M44-08 | Meridian SHALL publish a machine-readable compatibility matrix by product, version and platform, describing which of sessions, edits, prompts, tools, costs, approval evidence and enforcement are supported. | FUT-007 | MUST v1.x |
| FR-M44-09 | Every "supported" claim in that matrix SHALL be backed by a shipped exporter recipe and a real smoke test. CI SHALL exercise the pinned version plus one previous supported release. | FUT-007 | MUST v1.x |
| FR-M44-10 | Synthetic format drift SHALL downgrade the coverage claim visibly within one session. Agent-protocol, telemetry-trace, telemetry-log, telemetry-metric, hook and SCM evidence SHALL each be qualified separately. | FUT-007 | MUST v1.x |
| FR-M44-11 | For each supported vendor, Meridian SHALL record the documented retention window of every evidence source it depends on. | FUT-022 | MUST v1 |
| FR-M44-12 | Meridian SHALL capture volatile evidence within that window, and SHALL record capture latency and what was unavailable at capture time. | FUT-022 | MUST v1 |
| FR-M44-13 | Expiry SHALL produce an explicit `evidence_expired` marker naming the window that closed. A closed window SHALL NEVER present as an absence of activity. | FUT-022 | MUST v1 |

---

## 6. M45 — Change Economics

*Intelligence and economics.* **Answers FUT-012, FUT-030, FUT-031.**

Cross-vendor agent spend is a shipped product category from at least three vendors. Meridian's differentiator is not the chart: it is binding a cost to the decision that authorised it and to the change that actually merged, and never blending a reconciled figure with an estimated one.

| ID | Requirement | FUT | Priority |
|---|---|---|---|
| FR-M45-01 | Cost SHALL be attributable to the gate decision and to the merged commit it justified, not only to a time bucket, an agent or a user. | FUT-030 | MUST v1.x |
| FR-M45-02 | A story SHALL report the fully loaded cost of the change that merged, separated from the cost of abandoned attempts. For a sample of 20 merged changes, the per-change figure SHALL reconcile to the ledger and to the vendor-reported total within a stated tolerance, with unreconciled residue reported rather than absorbed. | FUT-030 | MUST v1.x |
| FR-M45-03 | Every cost figure SHALL carry its provenance from a closed vocabulary: `invoice_reconciled`, `vendor_api`, `locally_inferred`, `unknown`. | FUT-031 | MUST v1.x |
| FR-M45-04 | Figures of differing provenance SHALL NOT be summed into a single displayed or exported number without an accompanying breakdown by provenance class. | FUT-031 | MUST v1.x |
| FR-M45-05 | Accepted-change economics SHALL extend beyond token spend to provider charges, subscriptions allocated by disclosed rules, compute and storage, failed attempts, human review and rework time, and follow-up fixes. | FUT-012 | MUST v1.x |
| FR-M45-06 | Measured, estimated and unknown cost SHALL be preserved separately at every level of aggregation. A sample vendor bill SHALL reconcile to within 1% where detailed billing permits it, and every excluded charge category SHALL be documented. | FUT-012 | MUST v1.x |
| FR-M45-07 | Hosted budgets SHALL stop scheduling before a configured ceiling. Unhosted agents SHALL receive an advisory warning explicitly labelled as unenforced. | FUT-012 | MUST v1.x |

---

## 7. M46 — Product Assurance and Evidence-Based Investment

*Measurement and release.* **Answers `status.md` G-02, and FUT-009, FUT-010, FUT-013, FUT-014, FUT-018, FUT-021, FUT-034, FUT-035.**

The module that keeps the product honest about itself: no instrument computed and hidden, no release without a rehearsed recovery, no expansion without measured value, and no claim of superiority without a study designed to be capable of failing.

| ID | Requirement | FUT | Priority |
|---|---|---|---|
| FR-M46-01 | Every RPC method the sidecar exposes SHALL have at least one interface consumer, or an explicit reviewed `unsurfaced` declaration naming the phase that will surface it. | FUT-021 | MUST v1 |
| FR-M46-02 | A CI check SHALL enumerate the method registry, cross-reference the interface sources and fail on an undeclared orphan. Existing orphans SHALL be surfaced or declared before that check is enabled. | FUT-021 | MUST v1 |
| FR-M46-03 | Meridian SHALL provide a concise pull-request evidence card showing change risk, the exact tested revision, coverage gaps, failed checks, cost, and the human action required, with links to the raw evidence. | FUT-013 | MUST v1.x |
| FR-M46-04 | In five independent onboarding sessions, at least four users SHALL obtain a first provenance answer within 15 minutes. In ten review tasks, at least eight users SHALL correctly identify the real blocking risk. | FUT-013 | MUST v1.x |
| FR-M46-05 | Keyboard and screen-reader journeys SHALL complete launch, review and export without a critical barrier. False-alert rate and dismissal reasons SHALL be measured. | FUT-013 | MUST v1.x |
| FR-M46-06 | Meridian SHALL publish a tested support matrix of operating system, remote configuration, Python version and editor version, together with signed release artefacts and a dependency inventory. | FUT-014 | MUST v1.x |
| FR-M46-07 | Upgrade failure, disk exhaustion, sidecar crash, corrupted bundle and restore SHALL be rehearsed on all three desktop platforms plus one remote configuration, with zero loss of acknowledged local ledger entries and recovery within 15 minutes for the reference dataset. | FUT-014 | MUST v1.x |
| FR-M46-08 | A seven-day soak test with explicit resource limits SHALL be run before any release claim. | FUT-014 | MUST v1.x |
| FR-M46-09 | Meridian SHALL maintain an adversarial regression corpus of at least 100 fixtures spanning malicious repository and issue instructions, forged telemetry and trailers, poisoned tool responses, archive and path traversal, policy modification, credential theft and permission retries. Hosted execution and passive observation SHALL be tested separately. | FUT-010 | MUST v1.x |
| FR-M46-10 | No known critical escape may remain in the release corpus, and every blocked operation SHALL produce a usable evidence record. Coverage limits SHALL be documented, and passing the corpus SHALL NOT be presented as a general injection-resistance guarantee. | FUT-010 | MUST v1.x |
| FR-M46-11 | Team and task-class aggregates SHALL be the default view. Recorded metadata and its access list SHALL be disclosed to the people it describes. | FUT-018 | SHOULD v1.x |
| FR-M46-12 | A developer SHALL be able to dispute an attribution through an append-only correction carrying a reason and a reviewer identity. Correction history SHALL remain intact and inspectable. | FUT-018 | SHOULD v1.x |
| FR-M46-13 | A minimum cohort size of five SHALL apply to person-related aggregate views, with auditor access preserved separately. A denied role SHALL NOT be able to enumerate another tenant's people or runs. | FUT-018 | SHOULD v1.x |
| FR-M46-14 | The governance-effectiveness study SHALL be preregistered and SHALL compare three arms: baseline tools, tools plus recorder, and tools plus Governor. It SHALL record task allocation, agent and model configuration versions, independent review, human time, defects caught, false blocks, accepted-change cost and 30-day regressions. | FUT-009 | MUST v1.x |
| FR-M46-15 | The existing twenty-story target SHALL be treated as a feasibility pilot. The sample size required for any superiority claim SHALL be determined from observed variance, and unfavourable results and missing data SHALL be published. | FUT-009 | MUST v1.x |
| FR-M46-16 | Before any deterministic-engine capability beyond the structural set is built, Meridian SHALL publish per-action-class deterministic hit rate, latency and measured cost avoided on a real corpus, and SHALL retire any class whose deterministic path is not measurably cheaper or better. | FUT-034 | SHOULD v1.x |
| FR-M46-17 | The numeric criteria under which Meridian's own agent workforce is built SHALL be recorded **before** the evidence gate runs, together with an explicit commitment not to build it if those criteria are not met. | FUT-035 | MUST v1.x |

---

## 8. Amendments to existing modules

Each amendment refines scope that an existing module already owns. No identifier is renumbered.

| ID | Module | Amendment | FUT |
|---|---|---|---|
| **AMD-M10** | Ledger | `FR-M10-12`'s query API SHALL satisfy `FR-M41-07` pagination and `FR-M41-08` coverage reporting. `FR-M10-09`'s performance target SHALL be restated against a measured figure on named reference hardware, or the claim withdrawn — it is currently unmet under load. | FUT-020 |
| **AMD-M12** | Governance | `FR-M12-05` merge enforcement SHALL be extended to the SCM boundary per `FR-M42-03`. `FR-M12-07` approver identity SHALL carry the `approvedBy` class of `FR-M42-07`. `FR-M12-11` compliance export SHALL carry the enforcement point of `FR-M42-12`. | FUT-002, FUT-023, FUT-025 |
| **AMD-M17** | Measurement | Every KPI SHALL carry the coverage and sample disclosures of `FR-M41-08` and `FR-M41-14`. The DORA four keys SHALL continue to declare that they are ledger proxies, not deployment events, wherever they are displayed or exported. | FUT-008, FUT-020 |
| **AMD-M20** | Human roles | `FR-M20-01` SHALL be satisfied by a verified identity per `FR-M42-04`; the git-identity implementation is an interim assurance level, not the requirement. `FR-M20-06` approval hygiene SHALL capture whether the artefact was expanded before approval, which requires an interface signal that does not yet exist. | FUT-003 |
| **AMD-M25** | Human-in-the-loop | The two parallel steering implementations SHALL be reduced to one — `status.md` finding G-03. The retained path SHALL be the one carrying the clarifying-question protocol, uncertainty escalation and partial acceptance, and the interface SHALL use it. | G-03 |
| **AMD-M31** | Adapters | Adapter governance SHALL satisfy the digest pinning of `FR-M44-03`…`05`. `FR-M31-10` install review SHALL include signature verification for external sources. | FUT-029 |
| **AMD-M33** | Deterministic engine | `FR-M33-07` per-class reporting SHALL be delivered **before** further capability slices, and SHALL act as the investment gate of `FR-M46-16`. | FUT-034 |
| **AMD-M35** | External-agent proxy | `FR-M35-02`'s preference chain SHALL carry the retention windows of `FR-M44-11` and the expiry markers of `FR-M44-13`. `FR-M35-08` observer versioning SHALL feed the compatibility matrix of `FR-M44-08`. | FUT-007, FUT-022 |
| **AMD-M37** | Trust analytics | Every M37 metric SHALL satisfy `FR-M41-06` coverage reporting and `FR-M41-08` truncation disclosure. `FR-M37-06`'s greenfield/brownfield split SHALL apply to **every** trust metric, including the trust score and the DORA export, which it currently does not. | FUT-019, FUT-020 |
| **AMD-M38** | Brownfield comprehension | Characterisation gates SHALL be extended with change-specific contract and mutation tests, and with a versioned context manifest recording dependency, symbol, incident and memory sources. Stale records SHALL invalidate before reuse when code or dependencies change. A stack SHALL be promoted only after no worse regression escape and an agreed review-cost improvement on a held-out legacy corpus. | FUT-017 |
| **AMD-M39** | Cross-vendor spend | Every spend figure SHALL carry the provenance class of `FR-M45-03`. Spend SHALL be bound to the merge decision per `FR-M45-01`. | FUT-030, FUT-031 |
| **§1.3 Out of scope** | — | Add: "Competing on the cross-vendor agent-spend dashboard, on AI-aware git blame within a single vendor's surfaces, or on agent-activity analytics. All three are shipped product categories. Meridian competes on evidence that binds to a decision and verifies without us." | Competitive review |

---

## 9. New non-functional requirements

| ID | Requirement | FUT | Priority |
|---|---|---|---|
| NFR-33 | **Full-history analytic performance.** Every trust and spend metric SHALL complete over a 50,000-entry ledger within a documented budget on reference hardware, and SHALL equal an independent full-scan recomputation. | FUT-020 | MUST v1 |
| NFR-34 | **Coverage disclosure latency.** A coverage or truncation disclosure SHALL be computed in the same operation as the figure it qualifies, never as a later or optional call. | FUT-020 | MUST v1 |
| NFR-35 | **Backfill determinism.** Two backfill runs over the same repository at the same revision SHALL produce byte-identical output. | FUT-026 | MUST v1.x |
| NFR-36 | **Revocation propagation.** An identity or policy revocation SHALL take effect for new authorisations within five minutes for online clients. | FUT-003, FUT-015 | MUST v1 |
| NFR-37 | **Volatile capture margin.** Evidence with a documented vendor retention window SHALL be captured within 50% of that window under normal operation, and the achieved margin SHALL be reported. | FUT-022 | MUST v1 |
| NFR-38 | **Archive restore.** A three-year archive SHALL restore and re-verify within a documented budget, and storage growth SHALL be published per 10,000 entries. | FUT-027 | MUST v1.x |
| NFR-39 | **Portable verification without Meridian.** A bundle SHALL verify on a clean machine with no Meridian installation, using only the published specification and reference verifier. | FUT-016, FUT-032 | MUST v1.x |
| NFR-40 | **Contract-drift visibility.** An external contract rename or breaking revision SHALL surface as a visible coverage downgrade within one session, never as a silent mis-mapping. | FUT-036 | SHOULD v1.x |
| NFR-41 | **Reconciliation tolerance.** Cost reconciliation against detailed vendor billing SHALL fall within 1% where such billing is available, and every excluded charge category SHALL be named. | FUT-012 | MUST v1.x |
| NFR-42 | **Recovery objective.** Zero acknowledged local ledger entries SHALL be lost across upgrade failure, disk exhaustion, sidecar crash or restore, with recovery within 15 minutes for the reference dataset. | FUT-014 | MUST v1.x |
| NFR-43 | **Soak stability.** A seven-day continuous run under explicit resource limits SHALL complete without unbounded growth in memory, disk or handle count. | FUT-014 | MUST v1.x |

---

## 10. New security requirements

| ID | Requirement | FUT | Priority |
|---|---|---|---|
| SEC-31 | A verified identity SHALL be re-checked at gate execution. A session that was valid at issue SHALL NOT authorise a merge after its identity has been revoked. | FUT-003 | MUST v1 |
| SEC-32 | Meridian SHALL NOT present any control as enforced at a boundary where it is not. Where enforcement is client-side, the interface and the audit bundle SHALL say so explicitly. | FUT-025 | MUST v1.x |
| SEC-33 | An adapter or agent binary SHALL be refused if its content digest differs from its pinned value, and the refusal SHALL name both digests. | FUT-029 | MUST v1.x |
| SEC-34 | The adversarial regression corpus SHALL cover forged telemetry and forged commit trailers, and Meridian SHALL NOT elevate a forged signal above `inferred` confidence. | FUT-010 | MUST v1.x |
| SEC-35 | Policy bundle signatures SHALL be verified before activation, and an unverifiable bundle SHALL fail closed. | FUT-015 | SHOULD v1.x |
| SEC-36 | Witness receipts SHALL be verifiable without trusting Meridian's servers, the witness operator's servers, or any observed agent's vendor. | FUT-005 | MUST v1.x |
| SEC-37 | An erasure request SHALL render the subject unreadable across live storage, exports, archives and restored backups, while leaving chain verification intact. | FUT-006 | MUST v1.x |
| SEC-38 | A dispute correction SHALL be append-only and SHALL NOT permit deletion or silent alteration of the original attribution. | FUT-018 | SHOULD v1.x |

---

## 11. New acceptance criteria

| # | Criterion | FUT |
|---|---|---|
| **AC-41** | **No silent truncation.** A ledger of 50,000 entries is built. Every trust and spend metric is computed and each result equals an independent full-scan recomputation, carries `rowsConsidered`, `rowsAvailable`, `truncated` and its sequence range. A deliberately truncated query is displayed with a visible truncation statement and its forecast disabled. | FUT-020 |
| **AC-42** | **Unattributed survives the round trip.** On a repository containing formatter rewrites, a squash merge and commits predating installation, attribution reports three states, no state is derived by subtraction, every unattributed span carries a reason, and a trust metric below the coverage floor reads `insufficient_coverage` rather than a number. | FUT-019 |
| **AC-43** | **Every instrument is reachable.** The orphan check runs in CI over the full method registry and passes with zero undeclared orphans. Each of the previously orphaned trust and spend methods is either reachable from a documented interface path or carries a reviewed `unsurfaced` declaration naming its phase. | FUT-021 |
| **AC-44** | **A non-human approval never counts as human.** A policy allow-rule, an auto-mode classifier verdict, an agent code-review approval and a ruleset bypass actor are each recorded with the correct `approvedBy` class, none satisfies a human-approval policy, and none appears in any human-approval metric. | FUT-023 |
| **AC-45** | **Merge is blocked outside the editor.** On a repository configured with the SCM check, a developer with no Meridian installation attempts to merge a governed change with a missing approval, and with a stale approval after a force-push. Both are blocked at the SCM, and both blocks carry a readable reason. | FUT-002 |
| **AC-46** | **Revocation is fast and binding.** A verified approver is revoked at the identity provider. Within five minutes no new approval by that identity is accepted, and an in-flight session cannot complete a merge authorisation. | FUT-003 |
| **AC-47** | **Expiry is marked, not silent.** A vendor evidence source is allowed to pass its retention window. Meridian records an `evidence_expired` marker naming the window, the affected coverage claim is downgraded within one session, and no surface presents the gap as absence of activity. | FUT-022 |
| **AC-48** | **A bypass is detected and self-reported.** A repository ruleset bypass actor is enabled and a provenance hook is removed. Both are detected, both produce ledger entries, and Meridian downgrades its own coverage claim within one session. | FUT-024 |
| **AC-49** | **Evidence outlives the vendor and the tool.** A bundle is exported, the ledger is compacted and archived, the archive is restored, and the entry still verifies against its signed tree head. A third party parses the `Meridian-Ledger:` trailer from `git log` alone on a clean machine, resolves the bundle range and verifies it using only the published specification. | FUT-027, FUT-032 |
| **AC-50** | **Two editors, two SCMs, one evidence shape.** The same change is worked in two supported editors and merged through two SCM providers with no Orchestra tier installed. Both produce signed bundles that verify with the open verifier on a clean machine and carry the same evidence schema. | FUT-033 |
| **AC-51** | **Cost binds to the decision.** For 20 merged changes, the per-change cost reconciles to the ledger and to the vendor-reported total within the stated tolerance, separates merged from abandoned attempts, and reports unreconciled residue rather than absorbing it. No displayed or exported total blends provenance classes without a breakdown. | FUT-030, FUT-031 |
| **AC-52** | **A binary swap is visible.** An agent executable is replaced with a different build carrying the same declared name. The recorded agent identity changes, a warning is visible, and any attribution made under the unverified identity is labelled as such. | FUT-028, FUT-029 |

---

## 12. New risks

| # | Risk | Impact | Mitigation |
|---|---|---|---|
| **R31** | **Full-history analytics are too slow to be usable, and the 1,000-row clamp returns as a performance fix.** | High | `NFR-33` sets a budget rather than a row cap; pagination plus incremental aggregation, with `FR-M41-08` making any residual bound visible instead of silent. |
| **R32** | **SCM-side enforcement is rejected by platform teams as too invasive**, leaving the merge gate editor-only. | High | `FR-M42-11` makes the weaker enforcement point honest rather than hidden; the check is offered as an opt-in status check before it is required. |
| **R33** | **Verified identity requires an identity-provider integration the pilot customer will not fund.** | Medium | `FR-M42-04` keeps assurance levels explicit, so a git-identity deployment remains usable and is never described as verified. |
| **R34** | **Vendor evidence windows shrink faster than capture can be built**, and volatile capture becomes a treadmill. | Medium | `FR-M44-08` compatibility matrix plus `NFR-37` margin reporting make coverage loss measurable; `FR-M44-13` makes it visible rather than silent. |
| **R35** | **Witnessing adds an operational dependency customers decline**, leaving the strongest verification claim unavailable. | Medium | `FR-M43-01` makes witnessing optional and customer-controlled; `FR-M43-03` requires the unwitnessed limitation to be stated rather than glossed. |
| **R36** | **The evidence gate returns an unfavourable result and the requirements here become sunk cost.** | Low-impact, high-probability | Every P0 requirement supports a claim already being made about the Flight Recorder and Governor, and holds regardless of whether the Orchestra tier is ever built. `FR-M46-17` fixes the thresholds in advance so the decision is not renegotiated afterwards. |

---

## 13. New decisions

| # | Decision | Owner | Needed by |
|---|---|---|---|
| **D36** | Pagination strategy for full-history analytics: cursor pagination with in-process aggregation, an incremental materialised summary, or a read-model rebuilt on append. Determines whether `NFR-33` is achievable without a second store. | Architecture | Start of N1 |
| **D37** | Enforcement point for merge authorisation: a required SCM status check, a merge-queue gate, a server-side hook, or a policy-as-code integration. Determines the shape of `FR-M42-03` and the platform-team conversation. | Architecture + pilot customer | Start of N2 |
| **D38** | Identity provider of record for the verified assurance level, and whether git identity remains a supported production mode or becomes evaluation-only. Revisits `D9` for enterprise deployments only. | Founder + pilot customer | Start of N2 |
| **D39** | Witness topology: customer-operated receipt store, a third-party transparency service, or both. Interacts with `D3` anchoring, which was deferred in v1. | Architecture | N2 |
| **D40** | Whether the `approvedBy` taxonomy is a closed vocabulary owned by Meridian or an extensible one owned by policy. A closed vocabulary is testable; an open one survives vendors inventing new approval paths. | Architecture | Start of N1 |
| **D41** | Whether the compatibility matrix is published publicly, shared under agreement, or kept internal. A public matrix is the strongest honesty signal and the fastest to become wrong. | Founder | N2 |
| **D42** | Whether the deterministic-engine investment gate (`FR-M46-16`) is binding on the build agent or advisory to the owner. Determines whether M33 work can proceed without the measurement. | Founder | Before further M33 slices |

---

## 14. Release targets

| Target | Requirements |
|---|---|
| **v1** — needed to support claims already being made | FR-M41-01…15 · FR-M42-01…08 · FR-M44-11…13 · FR-M46-01, 02 · NFR-33, 34, 36 · SEC-31 · AC-41…47 |
| **v1.x** — needed before the next claim | FR-M41-16, 17 · FR-M42-09…15 · FR-M43-01…15 · FR-M44-01…10 · FR-M45-01…07 · FR-M46-03…17 · NFR-35, 37…43 · SEC-32…38 · AC-48…52 |
| **Conditional** — gated on evidence, per `FR-M46-16` and `FR-M46-17` | AMD-M33 · AMD-M38 · any Orchestra-tier scope |

---

## 15. Traceability — FUT proposal to requirement

| FUT | Title | Requirements |
|---|---|---|
| FUT-001 | Evidence completeness | FR-M41-01, 02, 03 |
| FUT-002 | Approvals bound to reviewed code | FR-M42-01, 02, 03 · AMD-M12 · AC-45 |
| FUT-003 | Identity assurance | FR-M42-04, 05, 06 · AMD-M20 · NFR-36 · SEC-31 · AC-46 · D38 |
| FUT-004 | Reliable evidence ingestion | FR-M41-10, 11, 12 |
| FUT-005 | Independent ledger witnessing | FR-M43-01, 02, 03 · SEC-36 · D39 |
| FUT-006 | Privacy lifecycle | FR-M43-06, 07, 08 · SEC-37 |
| FUT-007 | Agent compatibility contract | FR-M44-08, 09, 10 · AMD-M35 · D41 |
| FUT-008 | Statistically honest outcomes | FR-M41-13, 14, 15 · AMD-M17 |
| FUT-009 | Governance effectiveness experiment | FR-M46-14, 15 |
| FUT-010 | Threat regression suite | FR-M46-09, 10 · SEC-34 |
| FUT-011 | Machine-verifiable attestation | FR-M43-09, 10 |
| FUT-012 | Total accepted-change economics | FR-M45-05, 06, 07 · NFR-41 |
| FUT-013 | Low-friction review and adoption | FR-M46-03, 04, 05 |
| FUT-014 | Recovery and platform release | FR-M46-06, 07, 08 · NFR-42, 43 |
| FUT-015 | Enforceable policy distribution | FR-M42-13, 14, 15 · NFR-36 · SEC-35 · D37 |
| FUT-016 | Evidence portability and ownership | FR-M43-12, 13, 14 · NFR-39 |
| FUT-017 | Long-term brownfield safety | AMD-M38 |
| FUT-018 | Trusted team analytics | FR-M46-11, 12, 13 · SEC-38 |
| FUT-019 | Unattributed is a first-class state | FR-M41-04, 05, 06 · AMD-M37 · AC-42 |
| FUT-020 | Full-history analytics with declared coverage | FR-M41-07, 08, 09 · AMD-M10, AMD-M17, AMD-M37 · NFR-33, 34 · AC-41 · D36 |
| FUT-021 | No computed instrument without a consumer | FR-M46-01, 02 · AC-43 |
| FUT-022 | Capture volatile vendor evidence | FR-M44-11, 12, 13 · AMD-M35 · NFR-37 · AC-47 |
| FUT-023 | Classify what approved | FR-M42-07, 08 · AMD-M12 · AC-44 · D40 |
| FUT-024 | Governance-bypass detection | FR-M42-09, 10 · AC-48 |
| FUT-025 | Declare the enforcement point | FR-M42-11, 12 · AMD-M12 · SEC-32 |
| FUT-026 | Retroactive attribution backfill | FR-M41-16, 17 · NFR-35 |
| FUT-027 | Evidence lifecycle independence | FR-M43-04, 05 · NFR-38 · AC-49 |
| FUT-028 | Verified agent identity | FR-M44-01, 02 · AC-52 |
| FUT-029 | Adapter supply-chain pinning | FR-M44-03, 04, 05 · AMD-M31 · SEC-33 · AC-52 |
| FUT-030 | Bind spend to the merge decision | FR-M45-01, 02 · AMD-M39 · AC-51 |
| FUT-031 | Cost provenance never blended | FR-M45-03, 04 · AMD-M39 · AC-51 |
| FUT-032 | Emit the metadata signal | FR-M43-11 · NFR-39 · AC-49 |
| FUT-033 | Second-editor, second-SCM proof | FR-M43-15 · AC-50 |
| FUT-034 | Prove the deterministic engine pays | FR-M46-16 · AMD-M33 · D42 |
| FUT-035 | Orchestra go/no-go in advance | FR-M46-17 |
| FUT-036 | Pin external contract versions | FR-M44-06, 07 · NFR-40 |
| G-01 | Silent truncation *(defect)* | FR-M41-07, 08, 09 · AC-41 |
| G-02 | Orphaned instruments *(defect)* | FR-M46-01, 02 · AC-43 |
| G-03 | Duplicate steer path *(defect)* | AMD-M25 |

---

## 16. What this document deliberately does not require

Recording these keeps the scope honest and stops them being re-argued.

- **A better cross-vendor spend dashboard.** At least three vendors ship one. `M45` requires binding cost to a decision, which none of them documents, and nothing more.
- **Better AI-aware blame within one vendor's surfaces.** A major IDE vendor ships that. `M41` requires vendor-neutral, confidence-labelled, three-state attribution instead.
- **Competing on agent capability.** Unchanged from `gaps-requirements.md` §3.
- **A cryptographic distributed ledger.** Unchanged from `vision.md` §6.1. `M43` strengthens the transparency-log design; it does not replace it.
- **Any claim of regulatory compliance.** `M43`'s attestations and mappings are supporting evidence with a version, a scope and a stated limitation. They are not certifications, and they do not determine that a law applies.

---

*Every item above is written to be lifted into `Requirements_Final.md` v2.2 once accepted. `futures-implementation.md` governs the order in which it is built. `D22` remains open and gates all of it.*
