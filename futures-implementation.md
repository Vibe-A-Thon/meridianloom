# Meridian Loom — Futures Implementation Plan

| | |
|---|---|
| **Document** | futures-implementation.md |
| **Version** | 1.0 |
| **Author** | Ravaleedhar Reddy |
| **Governs** | The build order for everything specified in `futures_requirements.md` v1.0 |
| **Does not supersede** | `gaps_implementation.md` v1.0. That plan's F-phases remain the delivery spine; this plan is the hardening and assurance track that runs from the F1 exit through the F2 evidence gate. §13 states the interlock. |
| **Companions** | `futures.md` · `futures_requirements.md` · `status.md` (9 September re-audit) · `gaps_implementation.md` · `DECISIONS.md` |
| **Scale** | 5 phases (N0–N4) · 6 modules · 84 functional requirements · 13 acceptance criteria · 69 numbered tasks |
| **Baseline** | Commit `4b79bef`, branch `dev_local`; F0 tagged `f0-complete`, F1 tagged `f1-complete`, F2 pending-human-evidence (D35), F3 begun at M33 slice 2a |

---

## Table of Contents

0. [About This Plan](#0-about-this-plan)
1. [How to Use This Document](#1-how-to-use-this-document)
2. [Build Principles](#2-build-principles)
3. [Stack Decisions](#3-stack-decisions)
4. [Phase Map](#4-phase-map)
5. [N0 — Quiesce](#n0--quiesce)
6. [N1 — True and Visible](#n1--true-and-visible)
7. [N2 — Unassailable](#n2--unassailable)
8. [N3 — Evidence Gate](#n3--evidence-gate)
9. [N4 — Widen the Moat](#n4--widen-the-moat)
10. [Cross-Cutting Workstreams](#10-cross-cutting-workstreams)
11. [Definition of Done](#11-definition-of-done)
12. [Sequencing Dependencies](#12-sequencing-dependencies)
13. [Interlock with the F-Plan](#13-interlock-with-the-f-plan)
14. [Interface Interlock](#14-interface-interlock)
15. [Stop Criteria](#15-stop-criteria)
16. [Slip Plan](#16-slip-plan)
17. [Risk Retirement Schedule](#17-risk-retirement-schedule)
18. [Decision Schedule](#18-decision-schedule)
19. [Traceability Appendix](#19-traceability-appendix)

---

## 0. About This Plan

### 0.1 Why this plan exists and what changed

`gaps_implementation.md` sequenced the product as F0 Flight Recorder → F1 Governor → F2 evidence gate → F3 Orchestra. F0 and F1 are engineering-complete and tagged. The 9 September re-audit found that reaching that milestone exposed a different class of work than the plan anticipated:

- **The Governor computes correctly and shows almost nothing.** Seven of ten trust methods and all five spend methods have no interface consumer.
- **Every analytic silently truncates at 1,000 ledger rows.** Six modules request exactly that with no pagination and no disclosure.
- **The identity under every approval is self-asserted.** Every other link in the approval chain is strong.

None of these is a missing feature. All three are reasons a competent buyer or auditor would reject a product that is otherwise substantially built. **This plan is the hardening track that makes the existing product true, visible and defensible, and it runs before the evidence gate rather than after it** — because a gate measured on partial numbers measures nothing.

### 0.2 The three shapes of a phase here

- **N0 and N3 are gates, not build phases.** N0 is a hygiene gate that costs days and makes every later measurement meaningful. N3 is the evidence gate `gaps_implementation.md` §F2 already defines, extended per `FR-M46-14`. Neither produces features.
- **N1 and N2 are build phases** with hard exit criteria and named acceptance tests.
- **N4 is conditional** and its contents are chosen by what N3 measured, not by this document.

### 0.3 What this plan does not do

It does not pause F3. `gaps_implementation.md` F3 Orchestra work may continue in parallel with N1 and N2 **except** where `FR-M46-16` gates it — the deterministic engine may not grow beyond its structural capability set until its per-class value is measured. §13 states the interlock precisely.

It does not re-plan the GUI. GF1 remains partially delivered; N1 Workstream E is the specific interface work the orphaned-instrument defect requires, and nothing more.

---

## 1. How to Use This Document

**N0 comes first and costs days, not weeks.** Three test suites are currently red and two sessions are committing to the same tree. Every number in this plan's exit criteria is unmeasurable until that stops. It is the cheapest phase in the plan and the one most likely to be skipped.

**N1 is ordered, not parallel.** Correctness precedes visibility, because surfacing a wrong number is worse than surfacing none. The task order inside N1 is binding.

**N3 is a real gate with stop conditions.** §15 states them. If the governance layer does not demonstrably improve rejection rate or catch defects the agents missed, N4 does not start and the product ships as Flight Recorder plus Governor. That outcome is a success, and this plan is written so that it is.

**Every exit criterion is a passing test or a measured number.** Where a criterion is a measurement, the method is named. Where it needs a human, it is marked human-gated and is never claimed as engineering completion.

---

## 2. Build Principles

`E1`–`E14` (`Requirements-implementation.md`) and `G1`–`G7` (`gaps_implementation.md`) remain in force. These are added, each derived from a principle in `futures_requirements.md` §1.

| # | Principle | Consequence | From |
|---|---|---|---|
| **J1** | **Fix the number before you show the number.** | No surfacing task begins for a metric whose correctness task is incomplete. A visible wrong figure costs more trust than an invisible right one. | P25 |
| **J2** | **Every aggregate carries its population.** | A function that returns a figure without `rowsConsidered`, `rowsAvailable` and `truncated` does not compile past review. Coverage is computed in the same operation as the value, never bolted on. | P25, NFR-34 |
| **J3** | **No category is a residual.** | Any classifier that computes one class as `total − others` is a defect. Attribution, cost provenance, approval class and observation confidence each carry an explicit unknown that is reported. | P26 |
| **J4** | **Declare the boundary or do not claim the control.** | Every control ships with its enforcement point in the same change that ships the control. A control whose boundary is undeclared is advisory until proven otherwise. | P27 |
| **J5** | **Assume the vendor disappears.** | Every capability that depends on an external surface ships with its retention window recorded, its expiry marked and its fallback tested. Two products in the September review window were archived or renamed. | P28 |
| **J6** | **A computed instrument without a consumer is unfinished work.** | An RPC lands with its interface path or with a reviewed `unsurfaced` declaration naming the phase that will surface it. Never neither. | G-02, FR-M46-01 |
| **J7** | **Delete the duplicate before extending either copy.** | Where two implementations of one capability exist, the plan retires one before adding to the other. Two ledger shapes for one act is a provenance defect, not a code-tidiness issue. | G-03 |
| **J8** | **Measure before you widen.** | Investment beyond the current tier is gated on a published measurement, with thresholds written before the measurement runs. | P29 |
| **J9** | **One tree, one suite, one commit.** | Concurrent sessions on a shared tree make test results unattributable. Phase exits are declared against a quiesced tree and a sequential run. | N0, finding F-09 |

---

## 3. Stack Decisions

Rows are new to this plan; the rest inherit from `gaps_implementation.md` §3.

| Concern | Decision | Rationale |
|---|---|---|
| **Fresh-workspace policy** | **`D43` — open.** Ship-and-copy on first run, guided scaffolding, or fail-closed with a remedy. Whichever is chosen applies uniformly to all seven sidecar-loaded packs; a new pack may not introduce an eighth behaviour. | Two loaders currently fail closed and four carry embedded defaults, so an installed extension is half-inert in any repository but this one. `AC-53`, `N0-T09`. |
| **Full-history aggregation** | **`D36` — open.** Cursor pagination with in-process aggregation, an incremental materialised summary, or a read model rebuilt on append. Must close before N1 task 1. | `NFR-33` sets a performance budget; the shape determines whether it is reachable without a second store. |
| **Coverage envelope** | A single typed result wrapper carrying `value`, `rowsConsidered`, `rowsAvailable`, `truncated`, `sequenceRange` and `coverage`, returned by every metric function. Not an optional field on each result shape. | `J2`. One wrapper is enforceable by type; six conventions are not. |
| **Approval classification** | **`D40` — open.** Closed vocabulary owned by Meridian, or extensible and owned by policy. | A closed vocabulary is testable; an open one survives vendors inventing new approval paths. |
| **SCM enforcement point** | **`D37` — open.** Required status check, merge-queue gate, server-side hook, or policy-as-code. Must close before N2 task 1. | Determines both the engineering shape and the platform-team conversation. |
| **Identity provider** | **`D38` — open.** Revisits `D9` for enterprise deployments only; git identity remains a supported assurance level, never described as verified. | `FR-M42-04`. |
| **Witness topology** | **`D39` — open.** Customer-operated receipt store, third-party transparency service, or both. Interacts with the deferred `D3` anchoring decision. | `FR-M43-01`. |
| **Attribution states** | A three-valued enum in the core attribution types with no default and no derivation; the unknown reason vocabulary is closed and versioned. | `J3`, `FR-M41-04`, `FR-M41-05`. |
| **Volatile capture scheduler** | An observer-owned capture budget derived from each vendor's documented retention window, with achieved margin recorded per capture. | `NFR-37`, `FR-M44-12`. |
| **Backfill** | Git-history-only, deterministic, no daemon, no installation-forward requirement; output is content-addressed so two runs are byte-identical. | `NFR-35`, and the documented blind spot of the nearest competing approach. |
| **Orphan check** | A CI script over `shared/schema/methods.json` cross-referenced against `webview/src` and `extension/src`, with an allowlist file of reviewed `unsurfaced` declarations. | `FR-M46-02`. |

---

## 4. Phase Map

| Phase | Kind | Name | Requirements | Exit |
|---|---|---|---|---|
| **N0** | Gate | Quiesce | — | One commit, one sequential suite run, an accurate build state, a triaged dependency list |
| **N1** | Build | True and Visible | M41 *(v1 subset)*, FR-M42-07/08, FR-M44-11…13, M46-01/02, AMD-M25, AMD-M37 | `AC-41`…`AC-44`, `AC-47`, `NFR-33`, `NFR-34` |
| **N2** | Build | Unassailable | M42 *(rest)*, M43, M44 *(rest)*, M45, FR-M46-03…10 | `AC-45`, `AC-46`, `AC-48`…`AC-52`, `NFR-36`…`NFR-43` |
| **N3** | Gate | Evidence | FR-M46-14, 15, 17 | A written go / stop / pivot / kill decision with the raw ledger slice attached |
| **N4** | Build | Widen the moat | Conditional on N3 | Set by N3, not by this document |

---

## N0 — Quiesce

**This is not optional and it is not last.** Every exit criterion in N1 and N2 is a measured number. None of them can be measured on a tree where two sessions commit concurrently and three suites are red.

**Goal.** A single commit, a single sequential full-suite run with a green result or a named defect list, and a build state that matches reality.

### Measured state at the baseline

| Suite | Result | Detail |
|---|---|---|
| Python core | **999 passed, 2 failed** | `test_ledger_verify.py::TestVerifyPerformance::test_verify_100k_under_budget` and `test_observer_rpc.py::TestObserveSessionsRpc::test_sessions_after_handicap_come_from_the_monitor` |
| Webview | **176 passed, 1 failed** | `operations.test.tsx > agent operations > keeps inactive profiles in the Learning room and provides a list alternative` |
| Extension | **345 passed, 2 failed, 1 skipped** in a low-contention run | `test/workbench.test.ts`; real-sidecar end-to-end tests additionally time out under parallel load |
| Dependency audit | **5 findings** | 1 critical, 1 high, 3 moderate — all development toolchain, unremediated since 7 September |

### Tasks

1. **N0-T01 — Quiesce the tree.** One session commits at a time. Record the commit at which the tree went quiet.
2. **N0-T02 — Run each suite sequentially, not concurrently.** Publish the result per suite with the commit and the machine.
3. **N0-T03 — Resolve `test_verify_100k_under_budget`.** Three permitted outcomes: meet the 5-second target and keep the claim; restate `FR-M10-09` against the measured figure on named reference hardware; or mark the test an unreliable floor and remove the claim from every document that cites it. **Silently leaving it red is not one of them** — `AMD-M10` requires the disposition.
4. **N0-T04 — Resolve `test_sessions_after_handicap_come_from_the_monitor`.** Determine whether it is load-sensitive or a real observer-cache defect. An observer defect blocks N1 Workstream C.
5. **N0-T05 — Resolve the workbench independent-run test and the webview operations test.** Both sit on the delivery path a user exercises.
6. **N0-T06 — Stabilise or quarantine the real-sidecar end-to-end tests.** Give them a contention-tolerant budget or a serial lane. A suite that only passes when nothing else runs is not a regression gate.
7. **N0-T07 — Reconcile `BUILD_STATE.md` with the git log.** Its F1 workstream table lists C through H as not started; the log shows C through G complete. The build state is the resumption contract.
8. **N0-T08 — Triage the five dependency findings.** Upgrade, or record an accepted-risk note with a date and an owner.
9. **N0-T09 — Reconcile the fresh-workspace policy behaviour.** Surfaced by a clean-tree build on 9 September: the policy loaders disagree with each other about what an unconfigured workspace gets, and two of them leave the Governor inert. **Close `D43`**, then make the behaviour uniform and prove it on an empty workspace. Evidence below.

#### N0-T09 evidence — measured on an empty workspace at commit `8cede03`

Policy packs resolve **workspace-relative** (`<ws>/.meridian/policy/…`, then `<ws>/policy/…`), not from the extension. That is correct and deliberate: policy is team-owned, git-backed and PR-reviewable (`FR-M12-01`, `FR-M12-12`), and packaging it into the VSIX would undermine that. The defect is not the resolution rule — it is that the loaders behave in three different ways when the file is absent, and nothing ships or scaffolds a starting pack.

| Pack | Loader shape | Behaviour with no file present |
|---|---|---|
| `governance.yaml` | `load_policy_pack(paths[])` | **Fail-closed** — every gate evaluation blocks with "no policy file found" |
| `action-classes.yaml` | `load_catalogue(paths[])` | **Fail-closed** — the deterministic engine refuses every action class |
| `roles.yaml` | `load_role_pack(paths[])` | Embedded default; works silently |
| `pricing.yaml` | tolerant | Works; unpriced models report unknown |
| `stories.yaml` | tolerant | Works; unmapped stories land in unknown |
| `rework-reasons.yaml` | embedded default | Works |
| `licenses.yaml` | `load_license_map(path)` — **single path, no override chain** | Records an error and returns an empty map. Its own header documents a `.meridian/policy/` override "the same convention as the other packs" — **the loader does not implement one** |
| `acp-permissions.yaml` | extension-host read | The only pack packaged into the VSIX, because the TypeScript host reads it from the extension directory |

**Consequence.** Install the VSIX into any repository other than this one and the Governor is half-alive: gates and the deterministic engine fail closed with a path-not-found message, while roles, pricing, story metadata and rework reasons quietly work from embedded defaults. A user cannot tell from the interface which half is misconfigured and which is working as designed.

**Tasks.**

- **T09a** — Close `D43`: ship defaults, scaffold on first run, or fail closed with a guided remedy. The three are not equivalent — see `D43`.
- **T09b** — Make the absent-file behaviour uniform across all seven sidecar-loaded packs, and state it once in the loader documentation.
- **T09c** — Give `load_license_map` the same override chain as its own header already documents, or correct the header. Documentation and code must agree.
- **T09d** — Add a fresh-workspace test that asserts the agreed behaviour for **every** pack, so a new pack cannot land with a fourth behaviour.
- **T09e** — Whatever `D43` decides, a fail-closed pack's error must name the remedy, not just the paths it tried (`NFR-10`).

### Exit criteria

- [ ] A named commit at which the tree was quiet, with one sequential run recorded per suite
- [ ] Zero unexplained reds: every remaining failure has a disposition — fixed, quarantined with a reason, or a restated requirement
- [ ] `BUILD_STATE.md` matches the git log
- [ ] Each dependency finding is upgraded or has a dated accepted-risk note
- [ ] **`AC-53`** A fresh workspace produces one agreed, documented policy state across all seven sidecar-loaded packs, and any fail-closed pack names its remedy
- [ ] `J9` holds for the remainder of the plan

**Duration: days.** If N0 exceeds two weeks, the concurrency problem is organisational rather than technical and needs an owner decision, not more engineering.

---

## N1 — True and Visible

**Goal.** Every number a user can see is computed over the full history, declares its coverage, distinguishes what it does not know, and is reachable from the interface. One steering implementation.

**Requirements.** M41 v1 subset · `FR-M42-07`, `FR-M42-08` · `FR-M44-11`…`13` · `FR-M46-01`, `FR-M46-02` · `AMD-M25`, `AMD-M37` · `NFR-33`, `NFR-34`, `SEC-31` *(partial)*

**The order below is binding (`J1`).** Correctness first, then classification, then visibility.

### Workstream A — Full-history correctness

1. **N1-T01** — **Close `D36`.** Choose the aggregation shape and prove the `NFR-33` budget against a 50,000-entry fixture before writing consumers.
2. **N1-T02** — Cursor pagination in `ledger.query` across the full history; remove the fixed clamp as the only bound (`FR-M41-07`).
3. **N1-T03** — Introduce the coverage envelope as a single typed wrapper returned by every metric function: `value`, `rowsConsidered`, `rowsAvailable`, `truncated`, `sequenceRange`, `coverage` (`FR-M41-08`, `J2`).
4. **N1-T04** — Migrate all six analytic modules — rejection rate, reason distribution, trust score, agent comparison, J-curve, DORA export — onto pagination and the envelope. Each keeps its existing reconciliation oracle and gains a full-scan equality assertion at 50,000 entries (`AC-41`).
5. **N1-T05** — Extend the same treatment to the spend feed and the budget forecast, and to the Cross-Vendor Spend panel's own ledger query, which currently implements the honest behaviour locally and should consume it instead.
6. **N1-T06** — Any surface showing a truncated figure states it in text and disables derived projections (`FR-M41-09`).

### Workstream B — Attribution truth

7. **N1-T07** — Three-state attribution with no derivation by subtraction: `agent`, `human`, `unattributed` (`FR-M41-04`, `J3`).
8. **N1-T08** — Closed, versioned unknown-reason vocabulary: `no_signal`, `formatter_rewrite`, `squashed_history`, `pre_installation`, `unsupported_vendor`, `excluded_path` (`FR-M41-05`).
9. **N1-T09** — Attribution coverage on every trust metric, with a configurable floor below which the metric reads `insufficient_coverage` and shows no value (`FR-M41-06`, `AMD-M37`).
10. **N1-T10** — Per-field provenance on every provenance answer: source, capture method, contract version, capture timestamp, and one of `observed` / `inferred` / `unknown` / `redacted`. Signing never promotes `inferred` to `observed` (`FR-M41-01`, `FR-M41-02`).
11. **N1-T11** — Labelled corpus of at least 200 mixed spans; publish the three-way confusion matrix and the precision figure for `observed` claims (`FR-M41-03`, `AC-42`).
12. **N1-T12** — Extend the greenfield/brownfield split to the trust score and the DORA export, which do not currently carry it (`AMD-M37`).

### Workstream C — Statistical honesty and ingestion

13. **N1-T13** — Version the measurement definitions — proposed-change unit, rejection taxonomy, observation window, late-rejection treatment, censoring, cost allocation, greenfield boundary — and record the version that produced each figure (`FR-M41-13`).
14. **N1-T14** — Sample count, confidence interval where the statistic admits one, and missing-data share on every figure. Empty sample reads `insufficient_evidence` (`FR-M41-14`).
15. **N1-T15** — Suppress agent rankings where cohorts or coverage are not comparable, and show the suppression reason (`FR-M41-15`).
16. **N1-T16** — Ingestion keys, offsets, ingest time and replay status; the 100,000-event reconciliation fixture across duplicate, reordered, skewed, restarted, partial, paginated, queued and disk-exhausted conditions (`FR-M41-10`, `FR-M41-11`).
17. **N1-T17** — Intentionally dropped or unrecoverable data surfaces as a named coverage gap (`FR-M41-12`).

### Workstream D — Approval classification and volatile capture

18. **N1-T18** — **Close `D40`.** Then add the `approvedBy` class to every approval and permission decision (`FR-M42-07`).
19. **N1-T19** — Enforce that a non-human class never satisfies a human-approval policy and never counts as a human approval in a metric. Tests cover a classifier verdict, a policy allow-rule, an agent code-review approval and a ruleset bypass actor (`FR-M42-08`, `AC-44`).
20. **N1-T20** — Record each supported vendor's documented evidence retention window (`FR-M44-11`).
21. **N1-T21** — Capture within that window, recording capture latency, achieved margin and what was unavailable (`FR-M44-12`, `NFR-37`).
22. **N1-T22** — Emit an explicit `evidence_expired` marker naming the closed window; a closed window never presents as absence of activity (`FR-M44-13`, `AC-47`).

### Workstream E — Visibility and de-duplication

23. **N1-T23** — Orphan check in CI over the method registry with a reviewed `unsurfaced` allowlist (`FR-M46-02`).
24. **N1-T24** — Surface the trust instruments: trust score with its decomposition, reason distribution, agent-vs-agent comparison, the J-curve with its dip labelled as a phase, and the tokenmaxxing warning. Every chart carries a written finding (`FR-M46-01`, `A-10`).
25. **N1-T25** — Surface the spend instruments: move the Cross-Vendor Spend panel onto `spend/series`, `spend/pricing` and `spend/forecast`; add the team and cost-centre dimensions the sidecar already computes.
26. **N1-T26** — Declare or surface every remaining orphan; enable the check as a blocking gate (`AC-43`).
27. **N1-T27** — **Retire the duplicate steer path (`AMD-M25`, `J7`).** Keep the implementation carrying the clarifying-question protocol, uncertainty escalation and partial acceptance; move the interface onto it; delete the other. One act, one ledger shape.

### Exit criteria

- [ ] **`AC-41`** 50,000-entry ledger; every trust and spend metric equals a full-scan recomputation and carries its coverage envelope; a truncated query displays its truncation and disables its forecast
- [ ] **`AC-42`** Three-state attribution survives formatter rewrites, a squash merge and pre-installation history; no state derived by subtraction; below-floor metrics read `insufficient_coverage`
- [ ] **`AC-43`** Orphan check green and blocking, with zero undeclared orphans
- [ ] **`AC-44`** No non-human approval class satisfies a human-approval policy or appears in a human-approval metric
- [ ] **`AC-47`** A lapsed vendor window produces an `evidence_expired` marker and a coverage downgrade within one session
- [ ] **`NFR-33`**, **`NFR-34`** met on reference hardware, with the figures published
- [ ] Exactly one steering implementation exists in the tree
- [ ] Every N1 requirement's acceptance test names a passing test file

### Decisions to close

`D36` *(aggregation shape)* · `D40` *(approval vocabulary)*

### Risks retired or controlled

`R31` *(controlled — the budget is proven before consumers are migrated)* · `G-01`, `G-02`, `G-03` *(the three re-audit defects)*

---

## N2 — Unassailable

**Goal.** An auditor with no access to Meridian's systems can verify a bundle, state for every recorded decision what could have bypassed it and who could have done so, and read evidence older than any vendor would have retained.

**Requirements.** M42 *(rest)* · M43 *(all)* · M44 *(rest)* · M45 *(all)* · `FR-M46-03`…`10` · `NFR-35`…`43` · `SEC-32`…`38`

Workstreams A, B, C and D are independently sequenceable; E depends on B.

### Workstream A — Enforcement at a real boundary

1. **N2-T01** — **Close `D37`.** Choose the SCM enforcement mechanism with the pilot customer's platform team in the room.
2. **N2-T02** — Bind merge authorisation to repository, PR identity, base and head commits, diff digest, policy version, evidence and expiry (`FR-M42-01`).
3. **N2-T03** — Prove invalidation by test for force-push, rebase, changed base, changed policy, expired identity, replayed webhook and missing evidence; prove an unchanged valid PR still merges (`FR-M42-02`).
4. **N2-T04** — Enforce at the SCM so a developer without Meridian cannot merge a governed change (`FR-M42-03`, `AC-45`).
5. **N2-T05** — Declare the enforcement point of every control from the closed vocabulary; refuse to render a client-side control as enforced; record the effective enforcement point per decision in the audit bundle (`FR-M42-11`, `FR-M42-12`, `SEC-32`, `J4`).

### Workstream B — Identity assurance

6. **N2-T06** — **Close `D38`.** Distinguish locally asserted from verified identity and record which was used (`FR-M42-04`).
7. **N2-T07** — Refuse a git name and email as a verified approver wherever policy requires verification (`FR-M42-05`).
8. **N2-T08** — Bind verified identity to session and decision; re-check at gate execution; revocation blocks new approvals within five minutes (`FR-M42-06`, `NFR-36`, `SEC-31`, `AC-46`).

### Workstream C — Bypass detection and policy distribution

9. **N2-T09** — Detect the five named circumventions: ruleset bypass actor, client-edited tool allow-list, content exclusion not applying in agent mode, removed or disabled provenance hook, telemetry disabled after being enabled (`FR-M42-09`).
10. **N2-T10** — Each detection produces a ledger entry and downgrades the affected coverage claim within one session (`FR-M42-10`, `AC-48`).
11. **N2-T11** — Signed policy bundles with activation, expiry and precedence; emergency revocation within five minutes online; offline hosted runs stop at lease expiry (`FR-M42-13`, `FR-M42-14`, `SEC-35`).
12. **N2-T12** — Policy simulator explaining which historical verdicts a proposed change would have altered (`FR-M42-15`).

### Workstream D — Durability, portability and privacy

13. **N2-T13** — **Close `D39`.** Customer-controlled receipt storage for signed roots, signer enrolment, key rotation and revocation (`FR-M43-01`, `SEC-36`).
14. **N2-T14** — Independent verifier detects changed entries and rollback or truncation against a witnessed root, with three separate verdicts: valid signature, trusted signer, evidence coverage (`FR-M43-02`).
15. **N2-T15** — State the unwitnessed limitation in documentation and interface; claim no detection of wholesale replacement without a witness (`FR-M43-03`).
16. **N2-T16** — Multi-year retention with a compaction and archival path; prove archive, restore and re-verification; publish storage growth and restore time (`FR-M43-04`, `FR-M43-05`, `NFR-38`).
17. **N2-T17** — Privacy lifecycle: collection profiles, consent, redaction, recipient-specific export filtering, retention, erasure, backup-key behaviour; seeded-secret tests across every path; erasure survives restore while verification holds (`FR-M43-06`…`08`, `SEC-37`).
18. **N2-T18** — Publish the `Meridian-Ledger:` trailer specification with a reference parser; prove third-party parse-and-verify from `git log` alone (`FR-M43-11`, `NFR-39`, `AC-49`).
19. **N2-T19** — Headless collector and verifier with documented export, erase and uninstall paths; exports retain schema version, source identifiers and redaction labels; opt-in export to existing observability systems without ceding the record of authority (`FR-M43-12`…`14`).
20. **N2-T20** — Versioned attestation linking commit, policy decision, reviewer assurance, evidence, dependency digests and ledger root; in-toto-compatible envelope preserving source identifiers; build provenance and agent activity remain distinct predicates (`FR-M43-09`, `FR-M43-10`).

### Workstream E — Vendor surface and supply chain

21. **N2-T21** — Bind ACP and MCP sessions to a verifiable agent identity: executable digest, resolved version, publisher where available (`FR-M44-01`).
22. **N2-T22** — Label attribution to an unverified identity as unverified everywhere; a changed binary under an unchanged name produces a different recorded identity and a visible warning (`FR-M44-02`, `AC-52`).
23. **N2-T23** — Pin every adapter by content digest and record the exact artefact executed; refuse unpinned execution entries without a recorded acknowledgement; refuse silent drift naming both digests (`FR-M44-03`…`05`, `SEC-33`, `AMD-M31`).
24. **N2-T24** — Record the external contract version on every derived ledger entry; detect renames and breaking revisions in CI; degrade coverage visibly (`FR-M44-06`, `FR-M44-07`, `NFR-40`).
25. **N2-T25** — Publish the machine-readable compatibility matrix by product, version and platform; back every "supported" claim with a shipped recipe and a real smoke test; exercise pinned plus one previous release in CI; qualify each evidence channel separately (`FR-M44-08`…`10`). **Close `D41`.**

### Workstream F — Economics

26. **N2-T26** — Bind cost to the gate decision and the merged commit; separate merged from abandoned attempts; reconcile 20 merged changes to the ledger and the vendor total within tolerance, reporting residue (`FR-M45-01`, `FR-M45-02`, `AC-51`).
27. **N2-T27** — Cost provenance on every figure from the closed vocabulary; never sum across provenance classes without a breakdown (`FR-M45-03`, `FR-M45-04`, `J3`).
28. **N2-T28** — Extend accepted-change economics to provider charges, allocated subscriptions, compute and storage, failed attempts, human review and rework, and follow-up fixes; preserve measured, estimated and unknown separately; reconcile to within 1% where billing permits; hosted budgets stop before the ceiling and unhosted agents get a warning labelled unenforced (`FR-M45-05`…`07`, `NFR-41`).

### Workstream G — Product assurance

29. **N2-T29** — Pull-request evidence card: change risk, exact tested revision, coverage gaps, failed checks, cost, required human action, links to raw evidence (`FR-M46-03`).
30. **N2-T30** — Onboarding and review measurement: five sessions with at least four reaching first provenance in 15 minutes; ten review tasks with at least eight identifying the real blocking risk; keyboard and screen-reader journeys complete; false-alert rate measured (`FR-M46-04`, `FR-M46-05`). **Human-gated.**
31. **N2-T31** — Support matrix, signed artefacts, dependency inventory, recovery procedure and downgrade limits; rehearse upgrade failure, disk exhaustion, sidecar crash, corrupted bundle and restore on three platforms plus one remote configuration (`FR-M46-06`, `FR-M46-07`, `NFR-42`).
32. **N2-T32** — Seven-day soak with explicit resource limits (`FR-M46-08`, `NFR-43`).
33. **N2-T33** — Adversarial regression corpus of at least 100 fixtures; hosted execution and passive observation tested separately; no known critical escape; every block produces a usable evidence record; coverage limits documented and no general-resistance claim made (`FR-M46-09`, `FR-M46-10`, `SEC-34`).

### Exit criteria

- [ ] **`AC-45`** A developer without Meridian is blocked at the SCM for a missing approval and for a stale approval after force-push, both with readable reasons
- [ ] **`AC-46`** Revocation blocks new approvals within five minutes and stops an in-flight merge authorisation
- [ ] **`AC-48`** A ruleset bypass actor and a removed hook are both detected, recorded and self-reported as a coverage downgrade
- [ ] **`AC-49`** An archived, compacted and restored entry still verifies; a third party parses the trailer and verifies the bundle on a clean machine using only the published specification
- [ ] **`AC-50`** Two editors, two SCM providers, one evidence shape, both bundles verifying with no Orchestra tier — **human-gated, needs a customer**
- [ ] **`AC-51`** 20 merged changes reconcile within tolerance with residue reported; no total blends provenance classes
- [ ] **`AC-52`** A binary swap under an unchanged name changes the recorded identity and warns
- [ ] **`NFR-35`**…**`NFR-43`** each measured and published
- [ ] `SEC-32`…`SEC-38` each covered by a named test
- [ ] An independent reviewer, given only an audit bundle, can state for every decision what could have bypassed it

### Decisions to close

`D37` *(SCM enforcement)* · `D38` *(identity provider)* · `D39` *(witness topology)* · `D41` *(matrix publication)*

### Risks retired or controlled

`R32` *(controlled — enforcement point declared honestly if SCM binding is refused)* · `R33` *(controlled — assurance levels stay explicit)* · `R34` *(controlled — margin reporting makes coverage loss measurable)* · `R35` *(controlled — witnessing optional, limitation stated)*

---

## N3 — Evidence Gate

**Not a build phase. A decision phase with stop conditions.** This is `gaps_implementation.md` §F2, extended by `FR-M46-14` and `FR-M46-15`, and it runs **after** N1 because a gate measured on truncated numbers measures nothing.

### Preconditions

- N1 exit criteria met — every reported figure is full-history and coverage-declared
- **`FR-M46-17` satisfied: the Orchestra go/no-go thresholds are written down before the study starts**, while nobody has a stake in the answer
- Ideally N2 Workstream A complete, so the gate being measured is one a developer cannot walk around

### Design

Preregistered, three arms: baseline tools under their own native controls; the same tools plus the recorder; the same tools plus the Governor. Existing SCM branch protection and security tooling appear in **both** control and treatment arms, so only the additional benefit is attributed to Meridian.

### What is measured

| Measure | Source | Why it decides |
|---|---|---|
| Rejection rate before and after gating, split greenfield/brownfield | `FR-M37-01` with N1 coverage envelope | If gates do not reduce rejection, the governance layer is ceremony |
| Defects uniquely caught that the agent's own process missed | Gate outcomes against the counterfactual PR | The core value claim, as a number |
| False blocks | Gate outcomes with reviewer adjudication | The cost side of the same claim |
| Change failure rate for gated merges against the team baseline | `FR-M17-02` proxies, declared as proxies | The stability question on this team's data |
| Approval hygiene | `FR-M20-06` | If approvers rubber-stamp, the gates are theatre |
| Human review and rework time | `FR-M45-05` | The tax the layer imposes |
| Provenance queries actually run | Ledger query telemetry, hover counts | Whether anyone asks the question at the moment of need |
| Accepted-change cost | `FR-M45-01`, `FR-M45-02` | Whether the economics work |
| 30-day regressions | Post-merge revert and incident linkage | The lagging truth |
| First-value retention at week 8 | Are the onboarding testers still using it | The honest adoption signal |

### Statistical discipline

Twenty stories is a **feasibility pilot**, not a superiority test. Determine the sample required from observed variance before making any comparative claim. Freeze the corpus and the evaluator before testing. Blind reviewers where practical, counterbalance assignment, publish confidence intervals and exclusions. **Publish unfavourable results and missing data** (`FR-M46-15`).

### Exit criterion

- [ ] A written go / stop / pivot / kill decision recording the measurements and the chosen path, with the raw ledger slice attached

---

## N4 — Widen the Moat

**Reached only where N3's evidence supports the specific work.** Contents are chosen by measurement, not by this document.

| Condition measured in N3 | Work it unlocks |
|---|---|
| Provenance queries are actually run at the moment of need | Retroactive backfill (`FR-M41-16`, `FR-M41-17`, `NFR-35`) · second-editor and second-SCM proof (`FR-M43-15`, `AC-50`) if not already done |
| Gates demonstrably catch defects or reduce rejection | Trusted team analytics (`FR-M46-11`…`13`, `SEC-38`) · deeper policy distribution and simulation |
| Hosted agents are actually used at volume | Remaining supply-chain and identity hardening · concurrent-adapter selection policy |
| The pilot estate is brownfield-heavy | `AMD-M38` — change-specific contract and mutation tests, versioned context manifest, staleness invalidation, held-out legacy corpus with regression-escape and review-cost gates |
| N3 said **GO** on the Orchestra tier, and `FR-M46-16` is satisfied | `gaps_implementation.md` F3 continues beyond the M33 structural set |
| N3 said **STOP** | Ship Flight Recorder plus Governor. This is `R29` and `R36`, and it is an acceptable outcome, not a failure |

**Do a short integration spike before accepting any L or XL estimate. Assign one owner and a release target to each accepted requirement.**

---

## 10. Cross-Cutting Workstreams

| Workstream | Cadence | Notes |
|---|---|---|
| **Coverage envelope conformance** | Every commit from N1 | A metric function returning a bare value fails review. `J2`. |
| **Orphan check** | Every commit from N1-T26 | `FR-M46-02`. A new RPC lands with a consumer or a declaration. |
| **Residual-classification audit** | Every commit | Grep-level check that no classifier computes a category as `total − others`. `J3`. |
| **Enforcement-point declaration** | Every control added | A control ships with its boundary declared in the same change. `J4`. |
| **Vendor surface watch** | Every release of every observed agent | Retention windows, telemetry shapes and protocol versions all move. `FR-M44-08`, `NFR-40`. |
| **Contract version pinning** | Every commit from N2-T24 | External renames must break CI, not attribution. |
| **Provenance survival** | Every phase exit | Uninstall Meridian, verify trailers and bundle on a clean machine. `G4`, `AC-49`. |
| **Tier isolation** | Every commit | Inherited from `gaps_implementation.md`. Disabling a tier leaves lower tiers whole. |
| **Reconciliation** | Weekly | Every published number recomputed from the ledger and compared. |
| **Adversarial corpus** | Every commit from N2-T33 | `FR-M46-09`. |
| **Sequential suite run** | Every phase exit | `J9`. Phase exits are declared against a quiesced tree. |

---

## 11. Definition of Done

Inherits `Requirements-implementation.md` §14 and `gaps_implementation.md` §12. Adds:

- [ ] **Every figure the change produces carries its coverage envelope** — `rowsConsidered`, `rowsAvailable`, `truncated`, sequence range (`J2`)
- [ ] **No category is computed as a residual** (`J3`)
- [ ] **Every control declares its enforcement point** and is never rendered as enforced where it is not (`J4`)
- [ ] **Every external dependency records its retention window and marks expiry** (`J5`)
- [ ] **Every new RPC has an interface consumer or a reviewed `unsurfaced` declaration** (`J6`)
- [ ] **No second implementation of an existing capability** without the first being retired in the same change (`J7`)
- [ ] **Unknown is representable and reported** for every classification the change introduces
- [ ] **The acceptance test is named**, exists, and passes on a quiesced tree
- [ ] **Human-gated criteria are marked as such** and never claimed as engineering completion

---

## 12. Sequencing Dependencies

```
N0  Quiesce                                                    [days]
 │   one tree · one sequential run · reds dispositioned
 │   build state accurate · dependencies triaged
 │
 └─→ N1  True and Visible
      │   A full-history correctness ──┐
      │   B attribution truth ─────────┤
      │   C statistics + ingestion ────┼─→ E visibility + de-duplication
      │   D approval class + capture ──┘   (E depends on A and B: J1)
      │
      ├─────────────────────────────────────────┐
      │                                         │
      └─→ N2  Unassailable                      └─→ N3  EVIDENCE GATE
           │   A enforcement boundary                 │   preconditions: N1 exit
           │   B identity assurance                   │   + FR-M46-17 thresholds written
           │   C bypass + policy distribution         │   + ideally N2-A complete
           │   D durability + portability + privacy   │
           │   E vendor surface + supply chain        ├─ STOP ──→ ship Recorder + Governor
           │   F economics                            ├─ PIVOT ─→ narrow to what was used
           │   G product assurance                    ├─ KILL ──→ §15
           │                                          └─ GO ────→ N4, and F3 continues
           └──────────────────────────────────────────┘
```

**Hard serial:** `N0 → N1`. **N1 internal order is binding:** A and B before E (`J1`).
**Parallelisable:** N2 workstreams A, C, D, E, F, G are independent of each other; B gates C's identity-dependent tasks. N2 and N3 can overlap once N1 has exited, and N2 Workstream A ideally lands before N3 so the gate being measured is one a developer cannot walk around.

**The critical path is `N0 → N1 → N3`.** N2 widens the moat and is required before an enterprise claim, but the evidence gate does not wait for all of it.

---

## 13. Interlock with the F-Plan

`gaps_implementation.md` remains the delivery spine. This plan is the assurance track over it.

| F-plan phase | Status | Relationship to this plan |
|---|---|---|
| **F0 Flight Recorder** | Tagged `f0-complete` | N1 Workstream B and Workstream D task 20–22 harden its attribution and observation |
| **F1 Governor** | Tagged `f1-complete` | **N1 and N2 are the work that makes F1's exit claim defensible.** F1 is engineering-complete; it is not yet buyer-complete |
| **F2 Evidence Gate** | Pending-human-evidence (D35) | **N3 is F2**, extended by `FR-M46-14`/`15` and preconditioned on N1 |
| **F3 Orchestra** | Begun — M33 slices 1 and 2a | May continue in parallel with N1 and N2, **except** that `FR-M46-16` gates M33 growth beyond the structural capability set until per-class value is measured. `D42` decides whether that gate binds the build agent or advises the owner |
| **F4+** | Not started | Unchanged. `AMD-M38` refines its brownfield content |

**The interlock rule:** F-plan phases add capability; N-plan phases make capability defensible. **An F-phase may not be declared exited on a figure that has not passed N1's coverage requirements**, because such a figure is not evidence.

---

## 14. Interface Interlock

Per `gaps_guix_implementation.md`, GF1 is partially delivered: ten Governor surfaces are routed, gates and roles call real methods, and the trust and spend instruments are largely unsurfaced.

| Phase | Interface work | Built against |
|---|---|---|
| **N0** | None | — |
| **N1** | The trust and spend surfacing of Workstream E: trust-score decomposition, reason distribution, agent-vs-agent, J-curve, tokenmaxxing, and the spend panel moved onto the spend methods. **Every chart carries a written finding (`A-10`), and every figure carries its coverage envelope in the visible text.** | Real ledger data at 50,000 entries, not fixtures |
| **N2** | The pull-request evidence card (`FR-M46-03`), the enforcement-point declaration on every control surface (`FR-M42-11`), and the unverified-identity labelling of `FR-M44-02` | Real gated PRs |
| **N3** | None. The instruments are the deliverable, and their use is what is measured | Real |
| **N4** | Chosen by N3 | Real |

**The interlock rule, restated for this plan:** the interface never displays a figure that has not passed N1 Workstream A, and never displays a control without its enforcement point.

---

## 15. Stop Criteria

Inherits `gaps_implementation.md` §15 `K1`–`K7`. These are added, and they are the conditions under which this plan's own work should stop.

| # | Condition | Measured at | Response |
|---|---|---|---|
| **NK1** | Full-history analytics cannot meet `NFR-33` on reference hardware without a second store, and a second store is unacceptable | N1-T01 | Reopen `D36`. If no shape works, ship a declared bound — the figure stays honest even if it stays partial. Do not restore a silent clamp. |
| **NK2** | The pilot customer's platform team refuses SCM-side enforcement | N2-T01 | Do not fake it. Declare the editor boundary honestly per `FR-M42-11` and re-scope the enforcement claim. |
| **NK3** | No identity provider is available and the buyer will not fund one | N2-T06 | Ship git identity as an explicitly named assurance level. Never describe it as verified. Withdraw the verified-approver claim from external material. |
| **NK4** | After N1, provenance queries are still never run in the pilot | N3 | The product solves a problem nobody has at the moment of need. Pivot to compliance-export-only, or stop. |
| **NK5** | The gates measurably increase cycle time without reducing rejection or catching defects | N3 | Drop gating; keep the recorder and the analytics. `K4` in the base plan. |
| **NK6** | An incumbent ships cross-vendor, independently verifiable, retention-independent provenance bound to a merge decision | any | Reassess honestly. The differentiator was structural; if it closes, the position is gone. |
| **NK7** | N0 cannot be achieved in two weeks because concurrent sessions cannot be stopped | N0 | Escalate as an organisational decision. Every measurement in this plan is unreliable until it is resolved. |

**Stopping at NK4 or NK5 is not failure.** Each costs weeks and saves quarters.

---

## 16. Slip Plan

Cut in this order. Each cut leaves a coherent, honest product.

| Order | Cut | Cost |
|---|---|---|
| 1 | The in-toto attestation envelope (`FR-M43-09`, `10`) | The bundle still maps to SSDF, ISO 42001 and AI Act Article 12; only the machine-verifiable envelope waits |
| 2 | The policy simulator (`FR-M42-15`) | Policy changes ship without a preview of their historical effect |
| 3 | Trusted team analytics (`FR-M46-11`…`13`) | Person-level views stay unavailable; team aggregates still work |
| 4 | The headless collector (`FR-M43-12`) | CI-only deployment waits; the extension path still produces verifiable evidence |
| 5 | Signed policy distribution (`FR-M42-13`…`15`) | Policy stays git-backed and reviewable, which is already better than most |
| 6 | Retroactive backfill (`FR-M41-16`, `17`) | History before installation stays unattributed — which `FR-M41-05` already reports honestly |
| 7 | Witnessing (`FR-M43-01`…`03`) | The strongest verification claim waits; `FR-M43-03` requires the limitation to be stated, so nothing becomes dishonest |
| 8 | Cross-vendor economics beyond provenance labelling (`FR-M45-05`…`07`) | Cost stays labelled and unblended, but not fully loaded |

**Never cut:** the coverage envelope · three-state attribution · the `approvedBy` classification · the orphan check · volatile-capture expiry marking · enforcement-point declaration · the trailer specification · the unwitnessed-limitation statement. Each is either the product's honesty or the reason a buyer can trust a number. Cutting any of them reintroduces a defect this plan exists to close.

---

## 17. Risk Retirement Schedule

| Risk | Retired or controlled in | Primary control |
|---|---|---|
| **R31** Full-history analytics too slow | **N1** | `NFR-33` budget proven at N1-T01 before consumers migrate; `FR-M41-08` makes any residual bound visible |
| **R32** SCM enforcement refused by platform teams | **N2** | `FR-M42-11` declares the weaker boundary honestly; opt-in status check before required |
| **R33** No identity provider funded | **N2** | `FR-M42-04` keeps assurance levels explicit; git identity stays usable and never described as verified |
| **R34** Vendor windows shrink faster than capture | **N1 controlled, N2 measured** | `FR-M44-11`…`13` windows and expiry markers; `NFR-37` margin reporting; `FR-M44-08` matrix |
| **R35** Witnessing declined by customers | **N2** | `FR-M43-01` optional and customer-controlled; `FR-M43-03` states the limitation |
| **R36** Evidence gate unfavourable, requirements sunk | **N3** | Every P0 requirement supports a claim already made about F0 and F1 and holds regardless; `FR-M46-17` fixes thresholds in advance |
| R27 Observers go blind on vendor change | N1, N2 | `FR-M44-11`…`13`, `NFR-40`, versioned observers |
| R28 Incumbents ship portable provenance | N2 | `FR-M43-11` trailer specification and `FR-M43-15` two-editor proof make the cross-vendor claim testable rather than asserted |
| R17 Rubber-stamping | N1, measured N3 | `FR-M42-07` approval classification plus `FR-M20-06` hygiene |

---

## 18. Decision Schedule

| # | Decision | Must close by |
|---|---|---|
| **`D43`** | **Fresh-workspace policy strategy** — ship default packs inside the extension and copy them on first run, scaffold them through a guided setup step, or fail closed with a remedy the interface can act on. Ship-and-copy is fastest but puts a Meridian-authored policy in a customer repository without review; scaffolding keeps authorship with the team but adds a first-run step; fail-closed-with-remedy is the most honest and the least usable. Also decides whether `licenses.yaml` gains the override chain its header documents. | **N0-T09a** |
| **`D36`** | Full-history aggregation shape | **N1-T01 — before any consumer migrates** |
| **`D40`** | `approvedBy` vocabulary: closed or policy-extensible | **N1-T18** |
| **`D42`** | Whether the deterministic-engine investment gate binds the build agent or advises the owner | **Before any M33 slice beyond the structural set** |
| **`D37`** | SCM enforcement mechanism | **N2-T01** |
| **`D38`** | Identity provider of record; whether git identity stays a production mode | **N2-T06** |
| **`D39`** | Witness topology; interaction with the deferred `D3` anchoring decision | **N2-T13** |
| **`D41`** | Compatibility-matrix publication: public, under agreement, or internal | **N2-T25** |
| `D22` | Employment and IP path — **still open, still gates everything** | Owner, outstanding since F−1 |
| `D3` | Ledger anchoring — reopened by `D39` | N2 |
| `D21` | Whether the Orchestra tier is built at all | **N3** — this is what N3 decides, against thresholds written at `FR-M46-17` |

---

## 19. Traceability Appendix

### Requirements to phases

| Module | N1 | N2 | N4 |
|---|---|---|---|
| **M41 Evidence Completeness** | 01–15 | — | 16, 17 |
| **M42 Enforcement Assurance** | 07, 08 | 01–06, 09–15 | — |
| **M43 Evidence Durability** | — | 01–14 | 15 *(or N2 with a customer)* |
| **M44 Vendor Surface** | 11, 12, 13 | 01–10 | — |
| **M45 Change Economics** | — | 01–07 | — |
| **M46 Product Assurance** | 01, 02 | 03–10 | 11–13, 14–17 *(14, 15, 17 are N3)* |

### Amendments to phases

| Amendment | Phase |
|---|---|
| AMD-M10 *(query pagination, restated performance claim)* | N0 task 3, N1 Workstream A |
| AMD-M12 *(SCM enforcement, approval class, enforcement point)* | N1 Workstream D, N2 Workstreams A and C |
| AMD-M17 *(KPI coverage and proxy disclosure)* | N1 Workstream C |
| AMD-M20 *(verified identity, hygiene depth)* | N2 Workstream B |
| AMD-M25 *(retire the duplicate steer path)* | **N1-T27** |
| AMD-M31 *(adapter digest pinning)* | N2-T23 |
| AMD-M33 *(per-class reporting as investment gate)* | Before further F3 M33 slices |
| AMD-M35 *(retention windows, matrix feed)* | N1 Workstream D, N2-T25 |
| AMD-M37 *(coverage on every trust metric, full greenfield split)* | N1 Workstreams A and B |
| AMD-M38 *(brownfield contract and mutation tests)* | N4, conditional |
| AMD-M39 *(cost provenance, merge binding)* | N2 Workstream F |

### Acceptance criteria to phases

| Phase | Acceptance criteria |
|---|---|
| **N0** | AC-53 |
| **N1** | AC-41, AC-42, AC-43, AC-44, AC-47 |
| **N2** | AC-45, AC-46, AC-48, AC-49, AC-51, AC-52; AC-50 *(human-gated, needs a customer)* |
| **N3** | None — the deliverable is a written decision with its ledger slice |

### Non-functional and security to phases

| Phase | NFR | SEC |
|---|---|---|
| **N1** | 33, 34, 37 | 31 *(partial)* |
| **N2** | 35, 36, 38, 39, 40, 41, 42, 43 | 31 *(complete)*, 32, 33, 34, 35, 36, 37 |
| **N4** | — | 38 |

### Principles to phases

| Principle | Enforced from |
|---|---|
| J1 Fix the number before you show it | N1, task ordering |
| J2 Every aggregate carries its population | N1-T03, every commit thereafter |
| J3 No category is a residual | N1-T07, every commit thereafter |
| J4 Declare the boundary or drop the claim | N2-T05, every control thereafter |
| J5 Assume the vendor disappears | N1-T20, N2 Workstreams D and E |
| J6 No instrument without a consumer | N1-T23, every commit thereafter |
| J7 Delete the duplicate first | N1-T27 |
| J8 Measure before you widen | N3, and `FR-M46-16` for M33 |
| J9 One tree, one suite, one commit | N0, every phase exit |

---

*End of plan. N0 costs days and makes everything after it measurable. N1 makes the existing product true. N3 decides whether anything more is built. `D22` remains open and gates all of it.*
