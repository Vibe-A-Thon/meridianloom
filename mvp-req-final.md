# Meridian Loom — MVP Requirements, Final

| | |
|---|---|
| **Document** | mvp-req-final.md |
| **Version** | **1.1 — FROZEN 12 September 2026.** The consolidated, normative MVP requirement set. Change control: §19 |
| **Author** | Ravaleedhar Reddy |
| **Composed from** | `vision.md` v1.1 · `Requirements_Final.md` v2.1 · `Requirements-implementation.md` v2.0 · `VIGUIX_Final.md` v2.1 · `viguix-implementation.md` v2.1 · `gaps-requirements.md` v1.0 · `gaps_implementation.md` v1.0 · `gaps_guix.md` v1.0 · `gaps_guix_implementation.md` v1.0 · `gaps_initiation.md` v1.0 · `futures.md` · `futures_requirements.md` v1.0 · `futures-implementation.md` v1.0 · `jit-requirements.md` v1.0 · `jit-impl.md` v1.0 · `status.md` · `DECISIONS.md` · `BUILD_STATE.md` · `sample-meridian-loom-gui.html` |
| **Governed by** | `mvp-impl-plan.md` |
| **Baseline** | Commit `b2c2d9c` + working tree, release `0.1.0`. Verified 12 September 2026: Python 1629 passed / 0 failed · extension 534 passed / 0 failed · webview 242 passed / 0 failed · VSIX 232 files |
| **Scale** | 52 modules · ~700 functional requirements (incl. 67 SDLC phase requirements) · 55 NFRs · 49 security requirements · 71 acceptance criteria · 8 ecosystem requirements · 11 module amendments · 34 principles · 55 screens · 33 cross-cutting systems · 10 competitive findings |

---

## 0. Read this first

### 0.1 What this document is

Sixteen specification documents describe Meridian Loom. They were written at different times, under three different strategic framings, and they disagree with each other in places — including two that claim the same module number. This document is the single normative requirement set that reconciles them, states what the MVP is, and gives **every requirement in every source document a disposition**.

**Nothing is discarded.** Every identifier from every source survives here with a disposition. A requirement that is not in the MVP is marked `POST-MVP` and keeps its ID, its text and its source. That is a legitimate state for a specification to leave a requirement in, and it is the honest alternative to either pretending everything ships or quietly deleting what does not.

### 0.2 The three framings, reconciled

The source documents were written under three successive strategies. All three survive in this document, layered rather than replaced:

| Framing | Documents | What it contributes to the MVP |
|---|---|---|
| **The orchestra** — Meridian runs its own agent workforce | `vision.md`, `Requirements_Final.md`, `Requirements-implementation.md`, `VIGUIX_Final.md`, `viguix-implementation.md` | The domain model, the ledger schema, the loop model, the agent taxonomy, the 44 screens, the security posture. **The substrate of everything else.** |
| **The layer beneath** — Meridian governs agents a team already runs | `gaps-requirements.md`, `gaps_implementation.md`, `gaps_guix.md`, `gaps_guix_implementation.md`, `gaps_initiation.md` | The tiering, the external-agent proxy, the ACP host, trust analytics, cross-vendor spend, and the insight that **the orchestra is a tier, not the product**. |
| **The assurance track** — make the built thing defensible | `futures.md`, `futures_requirements.md`, `futures-implementation.md` | Coverage envelopes, three-state attribution, approval classification, enforcement-point declaration, evidence durability and portability. **The work that makes a buyer able to rely on a number.** |

A fourth document set, `jit-requirements.md` and `jit-impl.md`, proposes harness intelligence. It is fully retained (§14) and is `POST-MVP` by its own reasoning: its authors call the synthesis half "a funded experiment, not a feature".

### 0.3 The identifier collision, and how it is resolved

**`jit-requirements.md` and `futures_requirements.md` both claim `M41`, `NFR-33`–`35`, `SEC-31`–`33`, `AC-41`–`45`, `R31`–`34` and `P25`.** `jit-requirements.md` additionally claims `D24`–`D27`, which `DECISIONS.md` already closed for four unrelated decisions in September.

This is not a documentation nicety. `FR-M41-08` (the coverage envelope) and `FR-M43-11` (the trailer specification) are **implemented in the shipped code** under the `futures_requirements.md` meaning. A reader resolving `M41` to Harness Intelligence would be reading the wrong specification for code that exists.

**Resolution — `futures_requirements.md` numbering is authoritative. The JIT module is renumbered.**

| Was (in `jit-requirements.md`) | Becomes | Reason |
|---|---|---|
| `M41` Harness Intelligence | **`M47`** Harness Intelligence | `M41` Evidence Completeness is implemented and referenced by `BUILD_STATE.md`, `futures-implementation.md` and the test suite |
| `FR-M41-01`…`26` | **`FR-M47-01`…`26`** | Same |
| `NFR-33`, `34`, `35` | **`NFR-44`, `45`, `46`** | `NFR-33`…`43` are taken by `futures_requirements.md` |
| `SEC-31`, `32`, `33` | **`SEC-39`, `40`, `41`** | `SEC-31`…`38` are taken |
| `AC-41`…`45` | **`AC-54`…`58`** | `AC-41`…`53` are taken |
| `R31`…`R34` | **`R37`…`R40`** | `R31`…`R36` are taken |
| `D24`…`D27` | **`D44`…`D47`** | `D24`…`D27` closed in `DECISIONS.md`; `D36`…`D43` taken |
| `P25` (harness is an artifact) | **`P30`** | `P25`…`P29` are taken |

The JIT content is otherwise unchanged. §14 carries it in full under the new identifiers.

### 0.4 What the MVP is

`DECISIONS.md` `D19` (owner determination, 10 September 2026) sets the market entry path: **private distribution of a sideloaded VSIX to pilot organisations**, with the licence question deliberately deferred. The MVP follows from that decision.

> **The MVP is a package an IT organisation can evaluate, install, configure, roll out, operate and leave — without talking to us — that records what AI agents do in their repositories, governs what those agents may do, and produces evidence a third party can verify without Meridian installed.**

It is **not** the Marketplace listing, **not** the agent orchestra, and **not** a claim that the product improves delivery outcomes. That last claim is gated on `F2`/`N3`, which has not run.

### 0.5 Disposition vocabulary

Every requirement in this document carries exactly one:

| Disposition | Meaning |
|---|---|
| **`BUILT`** | Implemented, tested, and in the `0.1.0` package. The test is named or the module is named. |
| **`MVP-GAP`** | In the MVP and **not yet built**. These are the only requirements `mvp-impl-plan.md` schedules for the MVP. |
| **`MVP-HUMAN`** | In the MVP, engineering-complete, and blocked on a measurement only people can perform. Never claimed as engineering completion. |
| **`POST-MVP`** | Specified, retained, deliberately not in the MVP. Carries the phase that would build it. |

**A requirement's disposition is a statement about this release, never about its value.**

### 0.6 The freeze

**This document is frozen at v1.1 on 12 September 2026.** From this point the programme is implementation, not specification: `mvp-impl-plan.md` governs the order, and §19 governs the only ways this document may change.

| What is frozen | What is not |
|---|---|
| The MVP definition (§0.4), the tier model (§1.2) and the exact claim (§13, §16.2) | **The measured baseline (§4)** — it is re-measured at every phase exit and the measurement always wins (`MP1`) |
| Every disposition in §§3, 5–10 — changing one is a scope change through the slip plan, not an edit | **The competitive position (§16)** — re-verified every release (`NFR-54`), new findings land as `CMP-nn` |
| The identifier resolution of §0.3 — code depends on it | **Wording that turns out to be ambiguous** — §19.1 amends it in place, narrowly |
| The `MVP-R1`…`R7` set as the complete MVP scope | **What is discovered during build** — `POST-MVP` by default (§19.1) |

**The freeze is a commitment to build what is written, not a claim that what is written is perfect.** §4.3 records a correction made during the freeze audit itself.

---

## 1. The product

### 1.1 One paragraph

Meridian Loom is a VS Code extension and a local Python sidecar that records what AI coding agents do in a repository, applies permission policy to them, and writes a tamper-evident, independently verifiable log of the result. It contains no AI model and makes no model calls; it governs agents a team already runs and pays for.

### 1.2 Tiers (`FR-M36-05`) — `BUILT`

| Tier | Contents | Model calls |
|---|---|---|
| **Flight Recorder** (base) | Observation, ledger, attribution, evidence export, provenance trailers | **Zero, structurally enforced** |
| **Governor** | Gates, approvals, roles, steer, trust analytics, spend, ACP host, run initiation | Only those the hosted agent makes |
| **Orchestra** | Meridian's own agent workforce, loops, phase orchestrators, Trainer, harness intelligence | Yes |

A disabled tier is **absent**, not greyed out (`X-28`, banned pattern 30). Flight Recorder alone is a viable product and a legitimate deployment (`R29`).

### 1.3 What the MVP deliberately does not do

Consolidated from `Requirements_Final.md` §1.3, `gaps-requirements.md` §3 and `futures_requirements.md` §16. **These are scope decisions, recorded so they are not re-argued.**

- **Compete on agent capability** with Claude Code, Cursor, Copilot or Devin.
- **Compete on the cross-vendor spend dashboard** — at least three vendors ship one. Meridian binds cost to a decision (`FR-M45-01`); it does not chase the chart.
- **Compete on AI-aware git blame within one vendor's surfaces** — a major IDE vendor ships that. Meridian does vendor-neutral, confidence-labelled, three-state attribution instead.
- **Claim regulatory compliance.** Mappings are supporting evidence with a version, a scope and a stated limitation. They are not certifications and do not determine that a law applies.
- **Claim a productivity, quality or ROI improvement.** `futures.md` warns that the market and productivity figures in the earlier documents "should not become marketing claims without their original studies, dates, definitions and populations". No such figure appears in any MVP-shipped material.
- **Build a distributed ledger.** The substrate is a transparency log — tamper-evident, not tamper-proof (`vision.md` §6.1).
- **Self-replicating or self-evolving agents.** Bounded, gated, human-approved evolution only (`vision.md` §1.2).

---

## 2. Design principles — P1 to P34

`P1`–`P19` from `Requirements_Final.md` §3 are carried unchanged. Those added by later documents are restated here because they govern MVP decisions directly.

| # | Principle | Source | MVP force |
|---|---|---|---|
| `P1`–`P19` | The original nineteen — ledger-before-action, bounded loops, untrusted-by-default, least privilege, deterministic-first, evidence-over-narrative, and the rest | `Requirements_Final.md` | **In force** |
| **P17** | **Python first, model last.** A model call must justify itself and record `why_llm`. | `Requirements_Final.md` | **In force**; structurally enforced in Flight Recorder |
| **P20** | **Beneath, not against.** Meridian never requires a team to abandon the agent it already runs. | `gaps-requirements.md` | **In force — the MVP's founding constraint** |
| **P21** | **Adopt the standard; own the gap.** ACP, MCP, git trailers, OTel, SSDF. No bespoke equivalents. | `gaps-requirements.md` | In force |
| **P22** | **Trust is the product; the orchestra is a tier.** | `gaps-requirements.md` | **In force — defines the MVP boundary** |
| **P23** | **First value in weeks, not phases.** | `gaps-requirements.md` | In force (`NFR-28`) |
| **P24** | **Vendor-independent by construction.** Provenance lives in git and a local signed ledger. | `gaps-requirements.md` | In force |
| **P25** | **A number that cannot state its coverage is not evidence.** | `futures_requirements.md` | **In force — `BUILT` via the coverage envelope** |
| **P26** | **Unknown is a state, never a residual.** No classification derives a category by subtraction. | `futures_requirements.md` | **In force** |
| **P27** | **A control is only as strong as the boundary it binds at.** | `futures_requirements.md` | **In force** |
| **P28** | **Evidence outlives the tool that produced it.** | `futures_requirements.md` | **In force — the MVP's central claim** |
| **P29** | **Build the next thing only where evidence says it pays.** | `futures_requirements.md` | **In force — gates everything post-MVP** |
| **P30** | **The harness is an artifact, not an implementation detail.** *(was `P25` in `jit-requirements.md`)* | `jit-requirements.md` | `POST-MVP` |
| **P31** | **Notarise, do not duplicate.** Where another tool already records an act, read its record and make it tamper-evident; do not compete on capture. | §16 review | **In force — `MVP-R7.1`** |
| **P32** | **The tool call is a governance boundary, and so is the merge.** A control at one and not the other is a half-closed door, and `P27` forbids describing a half-closed door as a door. | §16 review | `POST-MVP` (`M48`) |
| **P33** | **Identity is attested, never asserted.** Where attestation is available it outranks any name a process gives itself. | §16 review | `POST-MVP` (`M49`); assurance levels `BUILT` |
| **P34** | **Map to the standard, and state what the mapping does not buy.** A mapping to a standard that is not harmonised is evidence, never a presumption of conformity. | §16 review | **In force — `MVP-R7.2`** |

---

## 3. Module register — M1 to M52

Every module from every source, with its MVP disposition. **Requirement counts are from the source documents.**

### 3.1 The original thirty-three (`Requirements_Final.md` v2.1)

| Module | Name | MVP disposition | Note |
|---|---|---|---|
| **M1** | Extension Host | **`BUILT`** | Activation, commands, tier context keys, editor surfaces |
| **M2** | Webview Dashboard | **`BUILT`** | 12-tab workbench, 7 studios, 6 screens, editor-area surface |
| **M3** | Sidecar and IPC | **`BUILT`** | Framed JSON-RPC, dual teardown, remote, 30 s handshake budget |
| **M4** | Loop Runtime | `POST-MVP` (Orchestra) | `core/meridian_core/runtime/` exists as substrate |
| **M5** | Agent Registry and Manifests | **`BUILT`** | Workbench catalogue + adapter registry |
| **M6** | Skill Loader | **`BUILT`** (10-pack catalogue shipped) | `FR-M6-08` full catalogue satisfied by the shipped library |
| **M7** | Memory Fabric | **Partly `BUILT`** | Reviewable memory notes and instruction library; tiers `POST-MVP` |
| **M8** | Model Router | `POST-MVP` (Orchestra) | `core/meridian_core/router/` exists |
| **M9** | Tool Layer | **Partly `BUILT`** | Permission gate and sandbox posture built; MCP client built |
| **M10** | Ledger Service | **`BUILT`** | Hash chain, Merkle, signed heads, encrypted blobs, schema v4 |
| **M11** | Chain Viewer | **`BUILT`** | Integrity verdict, entry stream, proofs, bundle export |
| **M12** | Governance and Policy Engine | **`BUILT`** (v1 subset + packs) | Seven policy packs, ship-and-copy (`D43`) |
| **M13** | XAI Service | **Partly `BUILT`** | Decision records, unverified-narrative labelling |
| **M14** | Trainer Agent | `POST-MVP` (Orchestra) | Learning surfaces declared, not exercised |
| **M15** | Onboarding Agent | **Partly `BUILT`** | Import/probation path built; wizard `POST-MVP` |
| **M16** | Replicator (Export / Import) | **`BUILT`** | `.md` and `.zip` import, portable export, exclusion scan |
| **M17** | Telemetry and KPI Service | **`BUILT`** | Ledger-derived, local by default, DORA proxies declared as proxies |
| **M18** | Workspace Isolation | **`BUILT`** | Worktrees, agent identity, trailer hook, abort |
| **M19** | Work Item Connectors | **Partly `BUILT`** | Read-only integrations built; write-back out of scope |
| **M20** | Human Identity, Roles, SoD | **`BUILT`** | Roles, SoD, N-of-M, delegation, approval hygiene |
| **M21** | Multi-Story / Portfolio | `POST-MVP` | |
| **M22** | Multi-Repository | `POST-MVP` | |
| **M23** | CI/CD and Merge Integration | **Partly `BUILT`** | PR ingest, status, conflicts built |
| **M24** | Chat Participant and Editor Integration | **Partly `BUILT`** | Hover provenance, blame decoration built |
| **M25** | Steering and Human-in-the-Loop | **`BUILT`** | One implementation (`AMD-M25` closed) |
| **M26** | Cost Forecasting and Economics | **Partly `BUILT`** | Estimate and levers built |
| **M27** | Deterministic Replay | **`BUILT`** | Cassettes, replay, golden corpus |
| **M28** | Code Intelligence Substrate | **Partly `BUILT`** | tree-sitter and LSP bridge built |
| **M29** | Documentation Agent | `POST-MVP` | |
| **M30** | Runtime Operations | **`BUILT`** | Doctor (now headless too), migration, clean uninstall |
| **M31** | Agent Adapter Framework | **`BUILT`** (re-based on ACP per `FR-M34-02`) | Discovery, validation, probation, portability |
| **M32** | Simulation Core | **Partly `BUILT`** | `core/meridian_core/simulation/`; harness role `POST-MVP` |
| **M33** | Deterministic Engine | **Partly `BUILT`** | Structural set built; growth gated by `FR-M46-16` |

### 3.2 The repositioning six (`gaps-requirements.md`)

| Module | Name | MVP disposition |
|---|---|---|
| **M34** | ACP Host and Registry | **`BUILT`** — host, permission gating, conformance. Registry browse is `MVP-GAP` (§5.2) |
| **M35** | External Agent Governance Proxy | **`BUILT`** — five observers, confidence rungs, health |
| **M36** | Flight Recorder Mode | **`BUILT`** — tiering, trailers, bundle, zero model calls |
| **M37** | Trust and Rejection Analytics | **`BUILT`** — all ten instruments surfaced (`N1-T24`) |
| **M38** | Brownfield Comprehension | **`POST-MVP`** — **absent from the code.** `futures.md` calls it "entirely unbuilt" |
| **M39** | Cross-Vendor Spend | **`BUILT`** — series, pricing, forecast, ceilings |

### 3.3 Run initiation (`gaps_initiation.md`)

| Module | Name | MVP disposition |
|---|---|---|
| **M40** | Run Initiation | **`POST-MVP`** — **absent from the code.** See §5.4: the MVP has a different, narrower start path |

### 3.4 The assurance six (`futures_requirements.md`)

| Module | Name | MVP disposition |
|---|---|---|
| **M41** | Evidence Completeness and Coverage | **`BUILT`** (`FR-M41-01`…`15`) · `16`, `17` backfill `POST-MVP` |
| **M42** | Enforcement Assurance | **Mostly `BUILT`** — `04`/`05` asserted versus verified identity (`D38`), `06` revocation, `07`/`08` approval class, and `11`/`12` enforcement-point declarations (`MV1-T01`…`T04`) are built; `01`–`03` SCM-native enforcement is `MVP-GAP` under `D37`; `09`, `10`, `13`–`15` `POST-MVP` |
| **M43** | Evidence Durability and Portability | **Mostly `BUILT`** — receipts, verdicts, archive, privacy, trailer spec, headless collector. `09`, `10` in-toto `POST-MVP` (§5.6); `15` `MVP-HUMAN` |
| **M44** | Vendor Surface and Supply-Chain Integrity | **Mostly `BUILT`** — `01`/`02` verifiable agent identity (`MV3-T01b`), `03`–`05` digest pinning (`MV3-T01`), `06`/`07` contract drift (`MV1-T09`), `08`–`10` the compatibility matrix (`MV1-T05`…`T07`) and `11`–`13` retention windows are built. Signature verification on external install (`AMD-M31`) is not: the ACP Registry publishes no signatures to verify |
| **M45** | Change Economics | **Partly `BUILT`** — provenance separation built (`D32`); merge binding `POST-MVP` |
| **M46** | Product Assurance | **Partly `BUILT`** — `01`/`02` the orphan check and `03` the pull-request evidence card (`MV3-T04`) are built; `05`–`07` are `MVP-GAP`, narrowed — the assistive, compatibility and resilience harnesses are built and the remaining runs need people or other platforms (`MV4`); `08` the soak harness is built and the seven-day run is not; `04` is `MVP-HUMAN`; `09`/`10`, the adversarial corpus, has its forged-signal slice built (`SEC-34`, narrow form) and the 100-fixture corpus `POST-MVP`; `11`–`17` `POST-MVP`/`MVP-HUMAN` |

### 3.5 Harness intelligence (`jit-requirements.md`, renumbered)

| Module | Name | MVP disposition |
|---|---|---|
| **M47** | Harness Intelligence *(was `M41`)* | **`POST-MVP`** — absent from the code. `FR-M47-01`…`05` (the artifact half) are the first candidates after the MVP; `FR-M47-09`…`26` (synthesis) are gated on `D44` and on `J2` hit-rate evidence |

### 3.6 SDLC phase requirements — `FR-P1` to `FR-P9`

`Requirements_Final.md` §6 specifies **67 requirements across the nine SDLC phases**. They describe Meridian's own agents doing delivery work, so the bulk of them are **Orchestra-tier and `POST-MVP`** — consistent with `gaps_implementation.md` §19, which moves ~230 requirements to `F3`.

**The exception matters and is stated separately:** `gaps_implementation.md` F1 reuses the *gate criteria* of phases 5, 6 and 7 by applying them to **external agents' work**. Those criteria are `BUILT` as gates over other people's pull requests, even though the phases that would produce that work are not.

| Phase | Count | MVP disposition |
|---|---|---|
| `FR-P1-01`…`07` Intake and Analysis | 7 | `POST-MVP` (`F3`) |
| `FR-P2-01`…`06` Architecture and Design | 6 | `POST-MVP` (`F3`) |
| `FR-P3-01`…`05` Planning and Decomposition | 5 | `POST-MVP` (`F3`) |
| `FR-P4-01`…`13` Implementation | 13 | `POST-MVP` (`F3`; `11`–`13` `F4+`) |
| `FR-P5-01`…`13` Verification | 13 | **Gate criteria applied to external work: `BUILT`.** Agent-authored verification: `POST-MVP` |
| `FR-P6-01`…`09` Security and Compliance | 9 | **Gate criteria applied to external work: `BUILT`.** Rest `POST-MVP` (`D14` still open) |
| `FR-P7-01`…`08` Review and Integration | 8 | **Human approval before merge, recorded: `BUILT`** (`FR-M12-05`/`07`). Adversarial critique by a Meridian agent: `POST-MVP` |
| `FR-P8-01`…`02` Release | 2 | `POST-MVP` (`F4+`; `02` behind a Governor flag, `D7`) |
| `FR-P9-01`…`04` Operate and Maintain | 4 | `POST-MVP` (`F4+`) |

**No SDLC phase requirement is deleted.** The MVP governs delivery work; it does not perform it.

### 3.7 Ecosystem requirements — `ECO-01` to `ECO-08`

| ID | Subject | MVP disposition |
|---|---|---|
| `ECO-01`, `ECO-02` | Private distribution channel and internal registry | **Partly `BUILT`** — sideloaded VSIX with a published digest is the `D19` channel; a registry is `POST-MVP` |
| `ECO-03` | Dependency and licence hygiene | **`BUILT`** — no copyleft runtime dependency; stated in `docs/SECURITY-AND-DATA.md` §7 |
| `ECO-04`, `ECO-05`, `ECO-07` | Cross-team adoption, shared catalogues, org-level interfaces | `POST-MVP` (`C5`) |
| `ECO-06` | Navion MCP browser as a documentation tool | `POST-MVP` (`C6`) |
| `ECO-08` | teamlore import | `POST-MVP` (`C6`) |

### 3.8 Amendments to existing modules — `AMD-M10` to `AMD-M39`

`futures_requirements.md` §8 refines eleven existing modules without renumbering anything. Each is dispositioned here so none is lost behind the module it amends.

| Amendment | Subject | MVP disposition |
|---|---|---|
| `AMD-M10` | Query pagination; restate the `FR-M10-09` performance claim against a measured figure | **`BUILT`** — pagination and the coverage envelope shipped; the claim is stated against the measured number |
| `AMD-M12` | SCM enforcement, approval class, enforcement point, fresh-workspace policy behaviour | **Partly `BUILT`** — approval class and `D43` seeding built; SCM boundary is `MVP-GAP` (`MVP-R3.1`, `D37`) |
| `AMD-M17` | Coverage and sample disclosure on every KPI; DORA keys declared as proxies | **`BUILT`** |
| `AMD-M20` | Verified identity supersedes git identity; approval-hygiene expansion signal | **Partly `BUILT`** — assurance levels built; expansion signal `POST-MVP` |
| `AMD-M25` | Retire the duplicate steer path | **`BUILT`** — one implementation (`G-03` closed) |
| `AMD-M31` | Adapter digest pinning; signature verification on external install | **`MVP-GAP`**, narrowed (`MV3-T01`) — digest pinning is built, and a registry archive's published sha256 is verified on install. **Signature verification on external install is not built**, because the ACP Registry publishes no signatures to verify |
| `AMD-M33` | Per-class reporting as the investment gate before further slices | **`BUILT` as a gate** — `FR-M46-16` in force; `D42` open |
| `AMD-M35` | Retention windows and expiry markers in the observer preference chain; matrix feed | **`BUILT`** — windows and expiry built; the matrix feed built with `MVP-R3.5` (`MV1-T05`…`T07`) |
| `AMD-M37` | Coverage on every trust metric; greenfield/brownfield split on all of them | **`BUILT`** |
| `AMD-M38` | Brownfield contract and mutation tests, versioned context manifest | `POST-MVP` — `M38` is absent from the code |
| `AMD-M39` | Cost provenance class on every figure; spend bound to the merge decision | **Partly `BUILT`** — provenance separation built (`D32`); merge binding `POST-MVP` |

---

### 3.9 Families carried from the source documents' own internal registers

Four identifier families live inside source documents rather than in a requirement table. Each is dispositioned here so the register is complete.

| Family | Count | Source | MVP disposition |
|---|---|---|---|
| **`BT-1`…`BT-6`** — the brutal truths | 6 | `HONEST_ASSESSMENT.md`, via `gaps-requirements.md` | **All six are premises, not requirements, and all six still hold.** `BT-1` ACP won → `P21`. `BT-2`/`BT-3` parity unwinnable → `P20`, §1.3. `BT-4` cost of discovering the thesis is wrong → the `MV5` gate. `BT-5` trust is the unsolved problem → `M37`, the reason the product exists. `BT-6` employment and IP → **closed** by owner determination (`D22`) |
| **`DS-1`…`DS-5`** — interface design stances | 5 | `gaps_guix.md` §1 | `DS-1` vendor tag fundamental **`BUILT`** (`X-27`) · `DS-2` Weave agent-agnostic **`BUILT`** · `DS-3` tier-driven disclosure **`BUILT`** (`X-28`) · `DS-4` trust is a screen, not a KPI panel **`BUILT`** (10.47) · `DS-5` match then exceed **`MVP-HUMAN`** (`X-31` needs the timing study) |
| **`L1`…`L6`** — the six canonical loops | 6 | `vision.md` §4.1 | `POST-MVP` (Orchestra). The runtime substrate exists in `core/meridian_core/runtime/`; the loops themselves are `F3`. **The bound-declaration rule (`E5`, `FR-M4-02`) is in force now** for anything that loops |
| **`E-xx-nn`** — per-screen event contracts | 115 | `VIGUIX_Final.md` §10 | **Follows its screen.** An event belongs to exactly one screen, so §9.1's disposition governs it. The events of the 15 `BUILT` screens are `BUILT`; the rest follow their screen's disposition. `E-GR-03` (the rework-reason taxonomy) is called out separately because `FR-M37-02` depends on it: **`BUILT`** |

---

### 3.10 Competitive-review modules (`M48` to `M52`)

Specified in full at **§17**, after the competitive review that produced them.

| Module | Name | MVP disposition |
|---|---|---|
| **M48** | Tool-Call Governance and Lineage | `POST-MVP` — the agent-gateway control point (`CMP-03`, `CMP-05`) |
| **M49** | Attested Agent and Workload Identity | `POST-MVP` — closes `NK3` without a human identity provider (`CMP-04`) |
| **M50** | Standards Conformance and Interoperable Evidence | **Partly `MVP`** — `01`…`04` are `MVP-R7.2`/`R7.3`; `05`…`08` `POST-MVP` |
| **M51** | Longitudinal Outcome Evidence | `POST-MVP` — 30/60/90-day outcomes bound to the gate decision (`CMP-01`) |
| **M52** | Interoperability with Other Provenance Tools | **Partly `MVP`** — `01`…`03` are `MVP-R7.1`; `04`, `05` `POST-MVP` |

---

## 4. What is already true — the `BUILT` baseline

**Verified 12 September 2026 against commit `b2c2d9c` plus the working tree.** This section exists because an MVP plan that re-specifies built capability wastes the reader's time.

### 4.1 Measured

**Re-measured at the `MV0` phase exit: one quiesced sequential run of all three suites, `scripts/run-tests.mjs`, at commit `6b0b36a`, Windows 11 / Node 22.20.0 / Python 3.11.9, 33 m 15 s wall-clock.** The run log is committed at `docs/baselines/6b0b36a.txt`. Not carried forward from a prior run — that is what §4.3 records going wrong.

| Check | Result |
|---|---|
| Python sidecar suite | **1,629 passed · 0 failed** · 27 m 53 s |
| Extension suite | **536 passed · 0 failed · 1 skipped** (50 files, incl. real-sidecar e2e and ACP conformance) |
| Webview suite | **242 passed · 0 failed** (26 files) |
| **Total** | **2,407 passed · 0 failed · 1 skipped** |
| Document gates (`MV0`) | traceability, claims and licences all green **before** the suites run |
| Type checking | Clean, both projects |
| Contract freshness | Generated bus types verified against the schema before the suites ran (`FR-M32-09`) |
| Package | `dist/meridian-loom-0.1.0.vsix`, 232 files, verifier staged, library staged **once** (37 files), both review documents staged |

**The one skipped test is recorded rather than rounded away.** A count that quietly drops a skip is the same class of imprecision as a metric without its coverage envelope (`P25`).

### 4.2 Shipped capability

- **The record.** Hash-chained, Ed25519-signed ledger with Merkle inclusion proofs, signed tree heads, encrypted content-addressed blobs, schema v4, WAL + `synchronous=FULL`.
- **Independent verification.** `verify.py` — one file, standard library only, pure-Python RFC 8032 — ships inside the VSIX and verifies a bundle on a machine that has never had Meridian installed. Three verdicts: valid signature, trusted signer, evidence coverage.
- **Portable provenance.** The `Meridian-Ledger:` trailer, now a **published versioned specification with a reference parser** (`FR-M43-11`), proven end to end by `AC-49`.
- **Headless operation.** `python -m meridian_core.cli` — `paths`, `export`, `verify`, `doctor`, `erase`, `uninstall` — with no extension, editor or sidecar (`FR-M43-12`/`13`).
- **Five observers** with structural confidence ceilings and degrade-not-silence behaviour.
- **The Governor**: policy gates, merge approval bound to a head-commit digest, halt, external PR ingest, roles with SoD and N-of-M, steer, approval classification.
- **Ten trust instruments and five spend instruments**, all surfaced, every figure carrying its coverage envelope, every chart carrying a written finding.
- **The shipped library**: 12 Role Agents, 10 Stack Agents, the 10-pack GA skill catalogue, 4 instruction documents, 4 ACP runtime presets — seeded on first open, marked Built-in, editable and deletable.
- **The interface**: 44 screens specified, the Governor set delivered, rendered in the **editor area** at full width.
- **Security posture**: `SEC-01`…`SEC-31` in force, including one-way isolation, credential handling, and — closed this month — scrubbed child-process environments across every spawn site.

---

### 4.3 Corrections made at the freeze audit

**The freeze audit re-ran the suites rather than trusting §4.1, and §4.1 was wrong.**

| Finding | Detail | Resolution |
|---|---|---|
| **The extension suite was not green** | `manifest.test.ts > has no nested extension/extension directory` failed. 533 passed, 1 failed, 1 skipped — not the 534/0 recorded | The guard was correct. `extension/extension/` had returned: 37 files, **tracked in git**, byte-identical to `extension/library/` apart from CRLF line endings — the `d698161` regression re-created by running the library generator from the wrong working directory on Windows. **Removed.** §4.1 re-measured after removal |
| **The recorded baseline outlived its evidence** | §4.1 was written from a prior run and carried forward | `MP1` exists for exactly this. §4 is now explicitly **not frozen** (§0.6) and is re-measured at every phase exit |

**Why this matters more than the bug.** A duplicate library is silent bloat. A requirements document asserting a green suite that is not green is the failure mode this project names as its characteristic defect: *verifying parts and recording conclusions about wholes.* The guard test caught the bloat. Nothing but re-running caught the false claim.

#### The duplicate came back a second time, and the reason is a gap in the guard

Removed during the audit; present again at the next session. Cause established, not guessed: **the 37 files are tracked at `HEAD`.** Commit `86af90b` landed the requirement documents but not the staged deletion, so the next checkout restored them.

**The guard checks the filesystem, not git.** `manifest.test.ts` asserts `existsSync(extension/extension) === false`, which passes the moment the directory is deleted locally and says nothing about whether the path is still tracked. A file tracked at `HEAD` **will** be in the next clone and therefore in the next VSIX, which is precisely what the guard exists to prevent.

| | |
|---|---|
| **Immediate** | `git rm -r extension/extension` — **the deletion must be committed.** Deleting the working copy alone lets it return on the next checkout, which is how it returned this time. **Done: `3d25813`**, verified absent from `HEAD` and the working tree |
| **Scheduled** | Strengthen the guard to assert that git tracks nothing under that path, so "deleted locally, still at `HEAD`" fails instead of passing. Deferred while the deletion was uncommitted — applying it then would have turned the suite red for a reason the guard was right about. **The deletion landed at `3d25813`, so the blocker is gone** and it is scheduled as **`MV0-T06`**, not deferred to `POST-MVP`: it defends the package-integrity line in the MVP's definition of done |

**The general lesson, recorded because it will recur in another form:** a guard that checks the working tree verifies the *developer's* state, not the *shipped* state. `MP7` already says verification happens against the installed artefact; this is the same rule pointed at version control.

---

## 5. The MVP requirement set

**This is the only list `mvp-impl-plan.md` schedules, and §5.6 makes it complete.** Everything else in this document is `BUILT`, `MVP-HUMAN` or `POST-MVP`. No identifier anywhere in §§6–10 carries `MVP-GAP` without appearing in one of `MVP-R1`…`MVP-R6`.

### 5.1 MVP-R1 — The package is adoptable · `MVP-GAP`

An organisation must be able to evaluate, install and validate without contacting us.

| ID | Requirement | Status |
|---|---|---|
| **MVP-R1.1** | The package SHALL carry an identifying icon, a real version and release notes that agree with `DECISIONS.md`. | **`BUILT`** (0.1.0) |
| **MVP-R1.2** | The package SHALL carry a security and data-handling statement written for a reviewer, stating what is stored, what leaves the machine, how credentials are held, and the limitations. | **`BUILT`** (`docs/SECURITY-AND-DATA.md`) |
| **MVP-R1.3** | The package SHALL carry a deployment guide covering install, central settings, tiering, policy, rollout order and removal. | **`BUILT`** (`docs/DEPLOYMENT.md`) |
| **MVP-R1.4** | Installation SHALL be validatable headlessly with a non-zero exit on failure. | **`BUILT`** (`cli doctor`) |
| **MVP-R1.5** | A published digest SHALL accompany the artefact, and the documentation SHALL state what it does and does not prove. | **`BUILT`** |
| **MVP-R1.6** | `FR-M46-06` — a tested support matrix of operating system, remote configuration, Python version and editor version SHALL be published with the release. | **`MVP-GAP`**, narrowed (`MV4-T01`) — `scripts/run-compatibility-smoke.mjs` runs each row's named smoke test and counts a row **verified only on the platform and interpreter it claims**, so running the macOS row's test on Windows proves nothing and is reported as `not-verified-here`. Wired into every CI matrix leg with baselines uploaded. Verified so far: `windows-11`, `vscode-1.95`, `python-3.11` (`docs/baselines/compatibility/`). Open until a CI run records them: `linux-lts`, `macos`, `python-3.12`. Remote stays unclaimed |
| **MVP-R1.7** | `FR-M46-07` — upgrade failure, disk exhaustion, sidecar crash, corrupted bundle and restore SHALL be rehearsed on three desktop platforms plus one remote configuration, with zero loss of acknowledged ledger entries. | **`MVP-GAP`**, narrowed (`MV4-T02`) — `core/tests/test_resilience.py` and `scripts/record-resilience.mjs` rehearse all five failures against the real ledger and the shipped verifier, each demonstrated red first; disk exhaustion is a genuine SQLite disk-full, not a mock. **5 of 20 recorded: Windows.** macOS and Linux run in their CI matrix legs; the remote configuration has no runner and needs a person |

**The initial claimed rows** — so `MV1-T05` has a defined starting set rather than a judgement call. These are the combinations `0.1.0` claims and must therefore smoke-test:

| Dimension | Claimed at `0.1.0` |
|---|---|
| Operating system | Windows 11 · macOS (current and one prior major) · Linux (one current LTS) |
| Editor | VS Code `^1.95.0`, per `extension/package.json` `engines.vscode` |
| Python | 3.11 and 3.12, per `core/pyproject.toml` `requires-python = ">=3.11"` |
| Remote | one of Remote-SSH or WSL — **whichever is rehearsed in `MV4-T02`; the other is not claimed until it is** |

**A combination not in this table is not claimed.** Adding a row requires a passing smoke test in the same change (`MK5`).


### 5.2 MVP-R2 — The demo path works unaided · `BUILT`

`futures.md` finding G-02 was that the product's differentiating instruments were computed and invisible. The MVP's equivalent risk is capability that exists and cannot be reached.

| ID | Requirement | Status |
|---|---|---|
| **MVP-R2.1** | Every shipped agent SHALL be bindable to a real ACP runtime without the user knowing an executable name. | **`BUILT`** (4 presets) |
| **MVP-R2.2** | A documented end-to-end demonstration SHALL exist, covering install → bind → dispatch → gate → export → independent verification. | **`BUILT`** (`DEMO.md`) |
| **MVP-R2.3** | `FR-M34-03` — the ACP Registry SHALL be browsable from the Adapter Bay so a registered agent is one click from probation. | **`BUILT`** (`MV3-T02`) — `registry/browse` and `registry/install` workbench actions, `RegistryBay` in the Adapter Bay. The index is fetched on explicit action only; opening the workbench reaches no network, asserted on both sides of the bus. Five states, not one error: `idle`, `fresh`, `cached-stale`, `unreachable` and `malformed` — a registry that answers with an unreadable index is a registry fault, not a network one |
| **MVP-R2.4** | `FR-M44-03`…`05` — an installed adapter SHALL be pinned by content digest, and silent drift SHALL be refused naming both digests. | **`BUILT`** (`MV3-T01`, corrected in `MV3-T05`) — `adapters/pinning.ts`; the pin index lives beside the root, not inside the folder it protects, so removing a pin is an edit to a different file. Five verdicts, because `unpinned` (placed by hand) is neither a pass nor a failure. `learned/` is excluded and the docstring says why. **The verify half was initially unreachable:** it lived only in `discoverAdapters`, which the shipped extension never calls, so it was tree-shaken out of the bundle entirely and pinning wrote a digest nothing read back. The package check found it. Verification now runs where an adapter actually loads — immediately before its agent is launched |
| **MVP-R2.5** | `FR-M46-03` — a pull-request evidence card SHALL show change risk, tested revision, coverage gaps, failed checks, cost and the human action required. | **`BUILT`** (`MV3-T04`) — `webview/src/screens/PullRequestCard.tsx`, on the Evidence surface; consumes `pr/status`, `pr/conflicts` and `spend/series`, closing `pr/conflicts`' unsurfaced entry. **The tested revision is the field that bites:** a passed gate recorded against a head the branch has moved past is shown as stale rather than as a pass. The card reads the record and offers no approve control — approving is a governed action bound to an identity in the Gate Room, and a second route to it here would be a quieter one. **Qualified:** `H1` asks for evidence from a real gated PR; the card is tested against the real RPC contracts and has not yet been run against a live pull request |

### 5.3 MVP-R3 — Claims match reality · partly `MVP-GAP`

The single most valuable property of this product is that its statements are true. Every item here closes a gap between what a surface says and what the code does.

| ID | Requirement | Status |
|---|---|---|
| **MVP-R3.1** | `FR-M42-11`/`12`, `SEC-32` — every control SHALL declare its enforcement point, and no surface SHALL render a client-side control as "enforced". | **`BUILT`** (`MV1-T01`…`T04`) — `governance/enforcementPoints`, the `EnforcementBadge` invariant, and `AC-45` asserted over surface source |
| **MVP-R3.2** | `FR-M43-03` — the unwitnessed limitation SHALL be stated in documentation and interface. | **`BUILT`** |
| **MVP-R3.3** | No diagnostic SHALL describe a shipped subsystem as unbuilt. | **`BUILT`** (fixed and test-guarded this month) |
| **MVP-R3.4** | `FR-M42-04`/`05` — locally asserted identity SHALL be distinguished from verified identity, and a git identity SHALL never satisfy a policy requiring verification. | **`BUILT`** (`D38`, assurance levels) |
| **MVP-R3.5** | `FR-M44-08`…`10` — a machine-readable compatibility matrix SHALL be published, every "supported" claim backed by a smoke test. | **`BUILT`** (`MV1-T05`…`T07`) — `shared/schema/compatibility.json`, table generated into `docs/DEPLOYMENT.md`, `D41` closed |
| **MVP-R3.6** | `NFR-39` — a bundle SHALL verify on a clean machine using only the published specification and reference verifier. | **`BUILT`** (`AC-49`) |
| **MVP-R3.7** | Every banned pattern this document claims is test-enforced SHALL have a named test. | **`BUILT`** (`MV1-T13`) — 28 and 30 were the two that did not; see §9.3 |

### 5.4 MVP-R4 — Starting work is possible and governed · `BUILT` (`MV2`)

`gaps_initiation.md` identified that the product had 44 screens and no start button, and specified `M40` Run Initiation to fix it. `M40` was absent from the code; `MV2` built **the invariant behind it**, not all eleven of its requirements. One contract (`initiation.py`), one entry point (`start_run`), and eight doors that differ in `origin` and nothing else.

| ID | Requirement | Status |
|---|---|---|
| **MVP-R4.1** | `FR-M40-01`/`02` — every initiation path SHALL construct one request object and record its `origin`. No path SHALL have a private route into the runtime. | **`BUILT`** (`MV2-T01`) — `core/meridian_core/initiation.py` is the one contract and `start_run` the one entry point; an AST guard fails the build on a call that starts a run without a `RunRequest`, demonstrated red on a planted route. `AC-38` is asserted twice: over the dataclass, and over the ledger rows five doors actually write |
| **MVP-R4.2** | `FR-M40-03` — preflight SHALL be mandatory: the parsed intent, the agents, the repository and branch, the cost estimate and ceiling, the gates, and dry-run or live. | **`BUILT`** (`MV2-T02`/`T06`) — `run/preflight`, screen 10.51 at its minimum, and the palette's modal. An unanswered question comes back as `confirmable: false` naming what is missing, never as an exception: a dialog that will not open cannot show a human what is incomplete. Preflight also refuses an adapter the worktree machinery would later reject, so a confirmable preflight is always startable |
| **MVP-R4.3** | `FR-M40-05`, `SEC-30` — launch authority SHALL be role-checked and the authorising identity recorded. | **`BUILT`** (`MV2-T03`) — `governance.roles.launch_modes` over the existing role vocabulary: a `readOnly` role may dry-run and may not go live. The identity and its assurance are recorded, and the refusal is recorded too. **Qualified:** there is no dedicated `start-run` permission — adding one to `ACTIONS` would make every deployed `roles.yaml` fail closed on launch, which is an outage rather than a check. A launch permission is `POST-MVP` and needs a policy migration |
| **MVP-R4.4** | `FR-M40-09` — a run cancelled at preflight SHALL leave no worktree, no branch and no ledger entry beyond the cancellation record. | **`BUILT`** (`MV2-T04`) — asserted against all three: the filesystem, `git branch --list`, and the ledger. Structural rather than janitorial — nothing is created before confirmation, so there is nothing to tidy and the promise survives a crash. Demonstrated red against a planted eager worktree, which also caught one non-discriminating assertion |
| **MVP-R4.5** | `FR-M40-11` — initiation SHALL be absent, not disabled, below the Governor tier. | **`BUILT`** (`MV2-T05`) — `governor.initiation` owns `run/*`; the Launch screen is filtered out of the Loom Bar by tier and the palette entry by a `when` clause. Tested as absence, with the discriminating half — Flight Recorder otherwise whole — asserted alongside, and both halves demonstrated red |
| `FR-M40-04` dry-run default · `FR-M40-06` per-run overrides · `FR-M40-07` content provenance · `FR-M40-08` editor-context · `FR-M40-10` templates | | **`POST-MVP`** |

### 5.5 MVP-R5 — The evidence gate can run · `MVP-HUMAN`

The MVP's purpose is to reach `F2`/`N3`. These are engineering-complete and blocked only on people.

| ID | Requirement | Status |
|---|---|---|
| **MVP-R5.1** | `FR-M46-17` — the numeric criteria for building the Orchestra tier SHALL be recorded **before** the study runs. | **`BUILT`** (`MV1-T08`) — `docs/evidence-gate.md`, written with no study data in existence |
| **MVP-R5.2** | `FR-M46-14`/`15` — the study SHALL be preregistered, three-armed, and SHALL publish unfavourable results. | **`MVP-HUMAN`** |
| **MVP-R5.3** | `FR-M46-04` — four of five users SHALL reach a first provenance answer within 15 minutes (`NFR-28`). | **`MVP-HUMAN`** |
| **MVP-R5.4** | `AC-50`, `FR-M43-15` — two editors, two SCM providers, one evidence shape, verified on a clean machine. | **`MVP-HUMAN`** — needs a customer |

### 5.6 MVP-R6 — The stragglers, reconciled

§§6–10 disposition individual identifiers, and a first pass left thirteen of them marked `MVP-GAP` outside `MVP-R1`…`R5`. A requirement that is in the MVP but in no MVP requirement group is a requirement nobody builds. **Each is resolved here, and §5 is now the complete `MVP-GAP` list that `mvp-impl-plan.md` schedules.**

| ID | Subject | Resolution |
|---|---|---|
| **MVP-R6.1** `NFR-40`, `FR-M44-06`/`07` | An external contract rename degrades coverage visibly, never mis-maps silently | **`BUILT`** (`MV1-T09`) — contracts pinned in `shared/schema/external-contracts.json`, drift fails in either direction. **Stated limit:** it cannot detect an upstream rename nobody has noticed; it makes drift a reviewed event |
| **MVP-R6.2** `SEC-34` | A forged trailer or forged telemetry SHALL never be elevated above `inferred` confidence | **`BUILT`** (`MV1-T10`, `D55`) in the **strong** reading: forgery never raises confidence, and trailer evidence is capped at `inferred` across all four trailer-reading observers. `D55` closed 13 Sept 2026. The 100-fixture corpus stays `POST-MVP` |
| **MVP-R6.3** `AC-52`, `FR-M44-01`/`02` | A binary swap under an unchanged name changes the recorded identity and warns | **`BUILT`** (`MV3-T01b`) — `adapters/identity.ts`; the identity is taken before the process is spawned, and the ledger entry carries `direct` when Meridian digested the file and `inferred` when it could not. **Qualified:** the common launch command is a run-time package fetcher (`npx`, `uvx`, `pipx run`), where the file on `PATH` is the fetcher and not the agent. That is reported as `unverified` naming the fetcher, rather than passing the shim's digest off as the agent's |
| **MVP-R6.4** `NFR-43`, `FR-M46-08` | Seven-day soak under explicit resource limits before any release claim | **`MVP-GAP`** — elapsed time, not effort. `scripts/soak.mjs` is built: it runs the sidecar **extracted from the built VSIX** under a steady workload, samples memory, handles and disk-per-entry from outside the process, writes the curve as it goes, and projects trends against explicit limits. A short run is recorded as `incomplete` and says it is not the soak. The 168 hours have not been run |
| **MVP-R6.5** `FR-M46-05` | Keyboard and screen-reader journeys complete launch, review and export without a critical barrier | **`MVP-GAP`**, narrowed (`MV4-T07`) — the half a machine can check honestly is built: `webview/src/screens/assistive-journeys.test.tsx` asserts that launch, review and export use real controls with accessible names, that the preflight is a dialog, that cancel precedes confirm in document order, and that refusals and alterations are announced — demonstrated red against an unnamed button and a focusable `div`. **The recorded pass per journey per input mode, by a person with a screen reader, is not done**; jsdom has no accessibility tree to stand in for it. Full WCAG 2.1 AA stays `POST-MVP` |
| `NFR-36`, `SEC-31`, `AC-46` | Identity revocation propagates within five minutes and binds at gate execution | **Re-dispositioned `POST-MVP`.** `D38` keeps git identity as the supported production mode; with no identity provider there is nothing to revoke *at*. The MVP ships `asserted` assurance and never describes it as verified (`NK3`). Building a revocation path against a provider that does not exist would be the kind of unbacked control `P27` forbids |
| `FR-M43-09`, `FR-M43-10` | in-toto attestation envelope | **Re-dispositioned `POST-MVP`.** `futures-implementation.md` §16 cuts it **first** in its own slip plan; the bundle already maps to SSDF, ISO 42001 and AI Act Article 12 without it |
| `AC-38`, `AC-40` | One contract across every origin; no initiation surface below Governor | **`BUILT`** — `MV2-T01` and `MV2-T05` respectively |
| `SEC-33` | Adapter refused on digest mismatch, naming both digests | **`BUILT`** (`MV3-T01`, completed by the MV0–MV4 audit) — drift refuses the launch, names both digests, and writes a `direct` ledger entry carrying the digests and never the contents; the refusal stands if the entry cannot be written |
| `NFR-42` | Zero acknowledged entries lost; recovery within 15 minutes | **`MVP-GAP`**, narrowed (`MV4-T02`) — five of the twenty rehearsals recorded (Windows), zero acknowledged entries lost; macOS and Linux run in CI, the remote configuration needs a person |

---

### 5.7 MVP-R7 — The claim survives the competitors · partly `MVP-GAP`

From the 12 September competitive review (§16). Four items, each small, each defending a claim the MVP already makes. **The other five new modules (`M48`–`M52`) stay `POST-MVP`** — §18 records why.

| ID | Requirement | Status |
|---|---|---|
| **MVP-R7.1** | `FR-M52-01`…`03` — Meridian SHALL read another provenance tool's records (git notes under its own ref, `Co-Authored-By`, agent-session-log trailers), label that tool as the source, never promote them above `inferred`, and **notarise their digest into the signed ledger**. | **`BUILT`** (`MV3-T06`) — `core/meridian_core/interop.py`, `interop/records`·`notarise`·`verify` at Flight Recorder tier, surfaced in the Ledger screen. `inferred` is a property rather than a field, so no caller anywhere can construct a foreign record claiming direct observation. The digest is over the note blob's exact bytes via `cat-file`, not `notes show`, whose trailing-newline formatting would have made a git upgrade read as tampering |
| **MVP-R7.2** | `FR-M50-01`…`03` — the evidence bundle SHALL map to the `ISO/IEC 24970` logging information model, state what each mapping is **not**, and state the retention available against the Article 26 six-month deployer obligation. | **`BUILT`** (`MV1-T11`) — margin computed rather than written down, and a shortfall reports negative rather than clamping to zero |
| **MVP-R7.3** | `FR-M50-04` — a CycloneDX **AI-BOM** for everything the package ships SHALL be published beside the VSIX and its checksum. | **`BUILT`** (`MV4-T08`) — `scripts/generate-bom.mjs` generates CycloneDX 1.6 **from the built VSIX, not the checkout**, and publishes it beside the package and its checksum: 52 components — 22 agents, 10 skills, 4 instruction documents, 4 runtime presets, 12 runtime dependencies — each with its digest. `--check` fails the build on drift, demonstrated against a tampered digest, a removed component and an invented one. Agents are typed `data`, not `machine-learning-model`: no model weights and no inference code ship, and the BOM says so |
| **MVP-R7.4** | §16.2 — the differentiator SHALL be restated in its narrower, still-true form in every shipped document, and the broader wording withdrawn. | **`BUILT`** (`MV1-T12`) — verified absent from shipped text, and `check-claims.mjs` now fails if a withdrawn claim returns |

### 5.8 MVP-R8 — The organisation can operate it and leave · `MVP-GAP`

§0.4 says the MVP is a package an organisation can **evaluate, install, configure, roll out, operate and leave — without talking to us**. The final freeze audit checked that sentence against the repository and found *operate* unserved: three artefacts an enterprise security review and a procurement desk ask for as a matter of routine are absent, and nothing in the plan created them.

| ID | Requirement | Status |
|---|---|---|
| **MVP-R8.1** | A **vulnerability disclosure process** SHALL ship with the package: where to report, what is in scope, what response the reporter can expect, and the disclosure posture. The commitment SHALL be one a single maintainer can actually meet — **an unmeetable response-time promise is the same defect class as an unbacked claim** (`MP5`). | **`BUILT`** (`MV4-T09`) — `SECURITY.md`, shipped inside the package. Response times sized for one part-time maintainer: acknowledgement within 10 working days, first assessment within 20, status updates at least every 30 days. No bounty, because there is no budget for one and saying otherwise would be an unbacked promise |
| **MVP-R8.2** | **Third-party notices** SHALL be generated from the lockfiles and shipped in the package, enumerating every runtime dependency with its licence. This turns `docs/SECURITY-AND-DATA.md` §7 — which asserts no copyleft runtime dependency — from an assertion into something a reviewer can check. | **`BUILT`** (`MV4-T09`) — `THIRD-PARTY-NOTICES.md` generated from the same licence sweep that backs §7, shipped in the package, and held by a drift gate in `npm test`. Where a licence cannot be resolved on the machine running the gate it reports **skipped** with the reason rather than passing |
| **MVP-R8.3** | A **support and upgrade policy** SHALL state which versions are supported, what notice a breaking change carries, how state migrates across an upgrade, and the export path on the way out. `futures.md` names "a supported upgrade policy" as part of the commercial test. | **`BUILT`** (`MV4-T09`) — `docs/SUPPORT.md`, shipped in the package: one supported line with a 90-day security-only tail, the notice a breaking change carries, what survives an upgrade, one-way migrations, and the exit path. It states plainly that **no paid support offering exists** |

**Why these are `MVP` and not `POST-MVP`.** Each one blocks the MVP's own definition rather than extending it: a security review that finds no disclosure process stops the evaluation, and a procurement desk that cannot enumerate dependencies stops the install. None of them is a feature; all three are the difference between a package an organisation can adopt and one it must ask about.

---

---

## 6. Non-functional requirements — NFR-01 to NFR-55

| Range | Source | MVP disposition |
|---|---|---|
| `NFR-01`…`NFR-27` | `Requirements_Final.md` | **In force.** Performance budgets, recovery, cross-platform, accessibility. `NFR-25` (LLM ratio) applies to Orchestra only |
| `NFR-28` First value < 15 min | `gaps-requirements.md` | **`MVP-HUMAN`** |
| `NFR-29` Observation overhead ≤ 5% | `gaps-requirements.md` | **`BUILT`** — measured ~0.0 ms |
| `NFR-30` Standards conformance (ACP, MCP) | `gaps-requirements.md` | **`BUILT`** — in CI |
| `NFR-31` Portable verification | `gaps-requirements.md` | **`BUILT`** |
| `NFR-32` Vendor drift resilience | `gaps-requirements.md` | **`BUILT`** |
| `NFR-33` Full-history analytic performance | `futures_requirements.md` | **`BUILT`** — re-measured, all metrics inside the 5 s budget at 50k |
| `NFR-34` Coverage disclosure latency | `futures_requirements.md` | **`BUILT`** |
| `NFR-35` Backfill determinism | `futures_requirements.md` | `POST-MVP` |
| `NFR-36` Revocation propagation ≤ 5 min | `futures_requirements.md` | `POST-MVP` — see §5.6; no identity provider to revoke at |
| `NFR-37` Volatile capture margin | `futures_requirements.md` | **`BUILT`** |
| `NFR-38` Archive restore | `futures_requirements.md` | **`BUILT`** |
| `NFR-39` Verification without Meridian | `futures_requirements.md` | **`BUILT`** |
| `NFR-40` Contract-drift visibility | `futures_requirements.md` | **`BUILT`** (`MV1-T09`) — `core/tests/test_contract_drift.py`: an external contract Meridian cannot parse degrades visibly within one session, never to silence |
| `NFR-41` Reconciliation tolerance | `futures_requirements.md` | `POST-MVP` |
| `NFR-42` Recovery objective | `futures_requirements.md` | **`MVP-GAP`**, narrowed (`MV4-T02`) — five of the twenty rehearsals recorded (Windows), zero acknowledged entries lost; macOS and Linux run in CI, the remote configuration needs a person |
| `NFR-43` Soak stability, 7 days | `futures_requirements.md` | **`MVP-GAP`** (`MVP-R6.4`) — harness built, 168-hour run not performed |
| `NFR-44`…`46` Harness retrieval, synthesis bound, archive growth *(was `NFR-33`…`35`)* | `jit-requirements.md` | `POST-MVP` |
| `NFR-47` **Notarisation overhead** — digesting a third-party provenance record adds no measurable delay to a commit | §16 (`M52`) | **`BUILT`** (MV0–MV4 audit) — notarisation is unreachable from the commit-msg hook, proven by an import-closure guard with a negative control (`core/tests/test_notarisation_off_commit_path.py`). It adds nothing to a commit by construction, which a timing assertion measured on one machine could not establish |
| `NFR-48` **AI-BOM freshness** — the published bill of materials is generated by the build, never hand-maintained, and drift fails the build | §16 (`M50`) | **`BUILT`** (`MV4-T08`) — generated from the artefact; drift between the BOM and the package fails the CI package job |
| `NFR-49` **Gateway latency** — tool-call governance adds no more than 50 ms at p95 to a governed call | §16 (`M48`) | `POST-MVP` |
| `NFR-50` **Attestation freshness** — an agent credential is short-lived and re-attested per session, never cached across runs | §16 (`M49`) | `POST-MVP` |
| `NFR-51` **Longitudinal windows** — 30/60/90-day outcomes are computed over the full history with the coverage envelope, never sampled | §16 (`M51`) | `POST-MVP` |
| `NFR-52` **Interoperable verification** — a DSSE-enveloped attestation verifies with standard tooling, not only with Meridian's verifier | §16 (`M50`) | `POST-MVP` |
| `NFR-53` **Conflict reporting** — a disagreement between two provenance tools is reported within one session, never silently resolved | §16 (`M52`) | `POST-MVP` |
| `NFR-54` **Review cadence** — the competitive position (§16) is re-verified against primary sources at every release | §16 | **In force** |
| `NFR-55` **Support window** — the supported version set, the breaking-change notice period and the state-migration guarantee are published and honoured | §5.8 | **`BUILT`** (`MV4-T09`) — published; *honoured* is a property of future releases and is held by `docs/SUPPORT.md` being a shipped, dated statement |

---

## 7. Security requirements — SEC-01 to SEC-49

| Range | Source | MVP disposition |
|---|---|---|
| `SEC-01`…`SEC-26` | `Requirements_Final.md` | **In force.** Untrusted-by-default, trifecta decomposition, egress allow-list, sandbox, keychain credentials, redaction, pinning, `SEC-26` declarative-only `learned/` |
| `SEC-27` One-way observation isolation | `gaps-requirements.md` | **`BUILT`** — extended this month to every child process, AST-guarded |
| `SEC-28` ACP permission non-escalation | `gaps-requirements.md` | **`BUILT`** |
| `SEC-29` Bundle signature verifiable without trusting Meridian | `gaps-requirements.md` | **`BUILT`** |
| `SEC-30` Initiation is authenticated, authorised, recorded | `gaps_initiation.md` | **`BUILT`** (`MV2`) — launch is role-checked before anything is created; the authorising identity and its assurance are recorded, and so is a refusal |
| `SEC-31` Identity re-checked at gate execution | `futures_requirements.md` | `POST-MVP` — see §5.6 |
| `SEC-32` Never present a control as enforced where it is not | `futures_requirements.md` | **`BUILT`** (`MV1-T01`…`T04`) — every control declares where it binds, and `v1` claims no SCM enforcement |
| `SEC-33` Adapter digest refusal | `futures_requirements.md` | **`BUILT`** (`MV3-T01`, completed by the MV0–MV4 audit) — drift refuses the launch, names both digests, and writes a `direct` ledger entry carrying the digests and never the contents; the refusal stands if the entry cannot be written |
| `SEC-34` Adversarial corpus covers forged telemetry and trailers | `futures_requirements.md` | **`BUILT`** in its narrow form (`MV1-T10`, `D55`) — forged trailers and forged telemetry never rise above `inferred`; the 100-fixture corpus stays `POST-MVP` |
| `SEC-35` Policy bundle signature fail-closed | `futures_requirements.md` | **`BUILT`** |
| `SEC-36` Witness receipts verifiable independently | `futures_requirements.md` | **`BUILT`** |
| `SEC-37` Erasure survives restore | `futures_requirements.md` | **`BUILT`** |
| `SEC-38` Append-only dispute corrections | `futures_requirements.md` | `POST-MVP` |
| `SEC-39`…`41` Harness no-escalation, untrusted synthesis input, registry-only *(was `SEC-31`…`33`)* | `jit-requirements.md` | `POST-MVP` |
| `SEC-42` A third-party provenance record is **untrusted input**: parsed under the existing allow-list, never executed, never promoted above `inferred` | §16 (`M52`) | **`BUILT`** (`MV3-T06`) — with an AST guard asserting the module calls no evaluator |
| `SEC-43` Notarising a third-party record SHALL NOT import that tool's trust: the digest is signed, the content is not vouched for | §16 (`M52`) | **`BUILT`** (`MV3-T06`) — the sentence rides on every record and every entry, so it cannot be lost between the ledger and a surface |
| `SEC-44` The AI-BOM SHALL NOT disclose workspace content, credentials or customer identifiers — only what the package itself ships | §16 (`M50`) | **`BUILT`** (`MV4-T08`) — inputs are the VSIX's own members and the declared runtime dependencies; member names are package-relative and no build-machine path, workspace content or identifier appears |
| `SEC-45` A tool call refused by the gateway SHALL fail closed, and the refusal SHALL be recorded before the caller is told | §16 (`M48`) | `POST-MVP` |
| `SEC-46` An agent SHALL NOT be able to obtain a credential attested to a different workload | §16 (`M49`) | `POST-MVP` |
| `SEC-47` Attestation material SHALL never leave the machine, and SHALL never enter an export | §16 (`M49`) | `POST-MVP` |
| `SEC-48` A C2PA content credential SHALL be emitted only for content Meridian observed being produced, never inferred | §16 (`M50`) | `POST-MVP` |
| `SEC-49` A vulnerability disclosure process ships with the package, naming scope, contact and the response a reporter can expect — **and promising only what one maintainer can meet** | §5.8 | **`BUILT`** (`MV4-T09`) |

---

## 8. Acceptance criteria — AC-01 to AC-71

| Range | Source | MVP disposition |
|---|---|---|
| `AC-01`…`AC-29` | `Requirements_Final.md` | `POST-MVP` — these are the **Orchestra** gate, reached only if `N3` says GO |
| `AC-30` Flight Recorder first value | `gaps-requirements.md` | **`MVP-HUMAN`** |
| `AC-31` ACP host | `gaps-requirements.md` | **`BUILT`** |
| `AC-32` External PR gating | `gaps-requirements.md` | **`BUILT`** |
| `AC-33` Provenance survives uninstall | `gaps-requirements.md` | **`BUILT`** — tested, including bundle verification after removal |
| `AC-34` Rejection analytics | `gaps-requirements.md` | **`BUILT`** (engineering half); ≥20-story half `MVP-HUMAN` |
| `AC-35` Brownfield gate | `gaps-requirements.md` | `POST-MVP` (`M38`) |
| `AC-36` Tiering leaves no scar | `gaps-requirements.md` | **`BUILT`** |
| `AC-37` Cross-vendor spend | `gaps-requirements.md` | **`BUILT`** |
| `AC-38`…`AC-40` Initiation: one contract, free cancel, tier absence | `gaps_initiation.md` | **`BUILT`** (with `MVP-R4`, `MV2`) |
| `AC-41` No silent truncation | `futures_requirements.md` | **`BUILT`** |
| `AC-42` Unattributed survives the round trip | `futures_requirements.md` | **`BUILT`** — corpus precision 1.0000 |
| `AC-43` Every instrument reachable | `futures_requirements.md` | **`BUILT`** — orphan check green and blocking |
| `AC-44` A non-human approval never counts as human | `futures_requirements.md` | **`BUILT`** |
| `AC-45` Merge blocked outside the editor | `futures_requirements.md` | **`MVP-GAP`** — `D37` refused pending a platform team |
| `AC-46` Revocation is fast and binding | `futures_requirements.md` | `POST-MVP` — see §5.6 |
| `AC-47` Expiry is marked, not silent | `futures_requirements.md` | **`BUILT`** |
| `AC-48` A bypass is detected and self-reported | `futures_requirements.md` | **`BUILT`** |
| `AC-49` Evidence outlives the vendor and the tool | `futures_requirements.md` | **`BUILT`** — proven end to end this month |
| `AC-50` Two editors, two SCMs | `futures_requirements.md` | **`MVP-HUMAN`** |
| `AC-51` Cost binds to the decision | `futures_requirements.md` | `POST-MVP` |
| `AC-52` A binary swap is visible | `futures_requirements.md` | **`BUILT`** (`MV3-T01b`) |
| `AC-53` A fresh workspace has one policy behaviour | `futures_requirements.md` | **`BUILT`** (`D43`) |
| `AC-54`…`AC-58` Harness criteria *(was `AC-41`…`45`)* | `jit-requirements.md` | `POST-MVP` |
| `AC-59` **A rival's record is read, labelled and notarised.** A repository carrying another tool's provenance notes is opened; the notes appear in the Weave attributed to that tool at `inferred`, their digest appears in the signed ledger, and the bundle verifies | §16 (`M52`) | **`BUILT`** (`MV3-T06`) — surfaced in the Ledger screen (10.7) rather than the Weave; 10.54 remains `POST-MVP` |
| `AC-60` **Two tools disagree, and Meridian says so.** Two provenance records claim the same span with different authorship; the disagreement is reported, and neither is silently preferred | §16 (`M52`) | `POST-MVP` |
| `AC-61` **The bundle speaks the buyer's standard.** An auditor reads the `ISO/IEC 24970` mapping, the Article 26 retention margin, and the sentence stating the mapping is not a presumption of conformity | §16 (`M50`) | **`BUILT`** (`MV1-T11`) — `core/tests/test_compliance_mapping.py` |
| `AC-62` **The AI-BOM matches the package.** Every agent, skill, instruction document and runtime preset in the VSIX appears in the published CycloneDX AI-BOM with a matching digest; a deliberate mismatch fails the build | §16 (`M50`) | **`BUILT`** (`MV4-T08`) — every shipped component appears with a matching digest; a deliberate mismatch fails |
| `AC-63` **The narrow claim is the only claim.** No shipped document contains the withdrawn broader wording; every surviving claim is bound to a passing test in `docs/claims.md` | §16 | **`BUILT`** (`MV1-T12`) — `check-claims.mjs` fails if the withdrawn wording returns to shipped text |
| `AC-64` **A tool call is governed and traced.** A call refused by the gateway fails closed, is recorded before the caller is told, and traces to the human who authorised the run | §16 (`M48`) | `POST-MVP` |
| `AC-65` **An existing gateway is kept, not replaced.** An organisation with its own agent gateway has its decision log observed by Meridian with no change to that gateway | §16 (`M48`) | `POST-MVP` |
| `AC-66` **Attested beats asserted.** An agent whose binary is attested records a different, higher assurance level than one that only declares a name, and both are distinguishable on every surface | §16 (`M49`) | `POST-MVP` |
| `AC-67` **Outcomes bind to the decision.** A merged change's 30-day revert and incident record resolves to the gate decision that allowed it, with the censoring rule stated | §16 (`M51`) | `POST-MVP` |
| `AC-69` **A reporter knows where to go.** The package carries a disclosure process naming scope, contact and expected response; the response commitment is one the maintainer can meet | §5.8 | **`BUILT`** (`MV4-T09`) — `SECURITY.md` in the package, checked by `scripts/check-demo-package.mjs` |
| `AC-70` **The dependency claim is checkable.** Third-party notices generated from the lockfiles enumerate every runtime dependency and its licence, and back the no-copyleft statement in `docs/SECURITY-AND-DATA.md` §7 | §5.8 | **`BUILT`** (`MV4-T09`) |
| `AC-71` **An organisation can plan around us.** The published policy states the supported versions, the breaking-change notice period, the migration guarantee and the exit path | §5.8 | **`BUILT`** (`MV4-T09`) |
| `AC-68` **Standard tooling verifies the attestation.** A DSSE-enveloped in-toto attestation verifies with off-the-shelf tooling on a machine with no Meridian installed | §16 (`M50`) | `POST-MVP` |

---

## 9. Interface requirements

### 9.1 Disposition of the 55 screens

`VIGUIX_Final.md` specifies 44 screens; `gaps_guix.md` adds six (10.45–10.50); `gaps_initiation.md` adds one (10.51); `jit-requirements.md` adds one (10.52 Harness Bench, `POST-MVP`). **No screen is deleted.**

| Disposition | Screens |
|---|---|
| **`BUILT`** | 10.45 Flight Recorder · 10.46 External Agents · 10.7 Ledger · 10.3 Weave · 10.40 First-Run · 10.50 Unlock · 10.1 Command Center · 10.6 Gate Room · 10.27 Decision Stream · 10.28 Steer & Clarify · 10.32 Roles · 10.43 Adapter Bay · 10.47 Trust Observatory · 10.49 Cross-Vendor Spend · 10.16 Inspector · plus the 12-tab workbench and 7 studios |
| **Partly `BUILT`** — delivered as amendments inside the Governor set, not as standalone screens | 10.4 Agents Watch *(catalogue)* · 10.22 KPI Observatory *(Analytics)* · 10.39 Notification Center *(shell notifications)* · 10.42 Editor surfaces *(hover provenance, blame decoration)* |
| **`MVP-GAP`** | **10.51 Launch** (with `MVP-R4`) |
| **`POST-MVP`** | 10.2 Floor · 10.5 Dojo · 10.8 CodeMap · 10.9 Loops · 10.10 C4 · 10.11 UML · 10.12 Flow · 10.13 Config · 10.14 Skill Forge · 10.15 Onboarding · 10.17 Diff Theater · 10.18 · 10.19 · 10.20 · 10.21 · 10.23 · 10.24 · 10.25 Story Hub · 10.26 · 10.29 · 10.30 · 10.31 Routing Observatory · 10.33 · 10.34 · 10.35 · 10.36 · 10.37 · 10.38 · 10.41 · 10.44 · 10.48 Comprehension Studio · **10.52 Harness Bench** |

| **`POST-MVP`** — added by the §16 competitive review | **10.53 Tool-Call Ledger** (`M48`) · **10.54 Provenance Reconciliation** — third-party records, notarisation status and disagreements (`M52`) · **10.55 Outcome Horizon** — 30/60/90-day outcomes per agent and per gate decision (`M51`) |

**All 55 screens are dispositioned: 15 `BUILT` · 4 partly `BUILT` · 1 `MVP-GAP` · 35 `POST-MVP` · 0 deleted.** `MVP-R7.1`'s notarisation surfaces inside the existing Ledger screen (10.7); 10.54 is the fuller view and is `POST-MVP`.


**Correction from the final freeze audit — routed shells are not the same as unbuilt.** §9.1 originally dispositioned every modelling and organisation screen as flat `POST-MVP`. The repository disagrees:

| Surface | What actually exists | Correct reading |
|---|---|---|
| `webview/src/workbench/modeling/` | `ModelingStudio` routes **eight views** — codemap, comprehension, diff, replay, architecture, uml, flows, loops — each a **20–62 line shell**, reachable today | **Routed shell present; the specified screen is not.** Dispositioned `POST-MVP` as *capability*, but the shells are built and **must not be deleted** (`MP6`) |
| `webview/src/workbench/organization/` | `OrganizationStudio` 934 lines, `DocumentEditor` 657, `DocumentDetail` 451, `ExchangeStudio` 424, with real `document/save` and `document/remove` RPCs and a 626-line test | **Substantially `BUILT`.** Calling this `POST-MVP` risked a developer rebuilding or removing working, tested code |

**One distinction worth stating so it is never misread.** The modelling tab's `loops` view is `DiagramStudio kind="loop"` — a **loop-diagram authoring surface** alongside architecture, UML and flow. It is **not** screen 10.9 Loop Graph, which shows *live running loops* and is Orchestra-tier. The two must not be conflated: rendering 10.9 below Orchestra would be banned pattern 30, and rendering a loop *diagram* editor is not.

**A screen nobody asked for is not built.** `GF2`/`N3` sets the post-MVP screen list from measured usage, not from the specification.

### 9.2 Cross-cutting systems

`X-01`…`X-26` (`VIGUIX_Final.md`) plus `X-27`…`X-31` (`gaps_guix.md`). `X-27` VendorTag, `X-28` tier-aware disclosure, `X-29` external-session awareness and `X-30` provenance hover are **`BUILT`** as component-level invariants. `X-31` competitor parity is **`MVP-HUMAN`** — it requires five engineers and a timing study. Added by §16: **`X-32` third-party provenance source tag** — a record read from another tool carries that tool's name wherever it renders, distinct from `X-27`'s vendor tag, which names the *agent* rather than the *recorder* (**`MVP-GAP`**, `MVP-R7.1`); **`X-33` assurance-level rendering** — attested, verified, asserted and unknown are four visually distinct states, never three (`POST-MVP`, `M49`).

### 9.3 Banned patterns

All 32 (`VIGUIX_Final.md` §18 plus `gaps_guix.md` §7) remain in force.

**Corrected at the final freeze audit.** This section previously stated that patterns 28–32 are "enforced by component tests, not by review". Checked against the tree, that is true of some and not of others:

| Pattern | Enforcement actually found |
|---|---|
| **29** vendor logos as glyphs · **31** `inferred` rendered as `direct` · **32** first-run needing a credential | Enforced in components with named tests (`vendors.ts`, `AnyLinePanel.tsx`, `first-run.test.tsx`) |
| **28** missing vendor tag · **30** Orchestra surfaces below Orchestra | **Enforced as of `MV1-T13`** (`webview/src/workbench/banned-patterns.test.ts`). 28: `AgentToken` and `VendorTag` cannot be constructed without a vendor, and the token composes the tag rather than reimplementing it. 30: no governor or orchestra tab is registered at the base tier, enabling Governor does not carry Orchestra, and a gated tab is **absent rather than locked**. The sidecar half of 30 was already enforced by a real-sidecar e2e — that is RPC absence; this is surface absence, and a screen can be routed while every call it makes is refused |

**`MVP-R3.7` is closed by `MV1-T13`.** All five of patterns 28–32 now have named tests, so §9.3 claims what the tests prove — which is what it said before the freeze audit checked, and did not. *A document that overstates its own enforcement is the same defect as a product that overstates its own controls (`P27`) — it is simply pointed inward.*

### 9.4 Accessibility

`A-01`…`A-08` (`VIGUIX_Final.md`) plus `A-09`…`A-11` (`gaps_guix.md`). `A-09` (confidence announced with meaning), `A-10` (a written finding under every chart) and `A-11` (plain-text Unlock) are **`BUILT`**. The three journeys of `FR-M46-05` — launch, review and export, completing without a critical barrier — are **`MVP-GAP`** (`MVP-R6.5`). Full WCAG 2.1 AA certification with screen-reader sign-off is `POST-MVP` (`GF4+`).

### 9.5 The HTML prototype

`sample-meridian-loom-gui.html` is retained as the design reference it has always been. It is **not** a build target and no requirement depends on it.

---

## 10. Data models

All models from `Requirements_Final.md` §7 are retained. Additions:

| Model | Source | Disposition |
|---|---|---|
| `§7.2` Ledger entry, extended with `vendor`, `observation_confidence`, `external_session_id`, `run_id`, `origin` | `Requirements_Final.md` + `gaps_implementation.md` + `gaps_initiation.md` | **`BUILT`** at schema v4 (`run_id`/`origin` pending `MVP-R4`) |
| `§7.11` RunRequest | `gaps_initiation.md` | **`BUILT`** (`MV2-T01`) |
| `§7.12` Harness Record *(with `harness_id`/`version`/`digest` on the ledger)* | `jit-requirements.md` | `POST-MVP` |
| Coverage envelope | `futures_requirements.md` | **`BUILT`** |
| Bundle, extended with `schemaVersion` and `redaction` | This release | **`BUILT`** (`FR-M43-13`) |

---

## 11. Decisions

### 11.1 Closed and binding on the MVP

`D4`, `D9`, `D10`, `D18`, `D19` *(licence — deliberate deferral, private distribution)*, `D20`, `D22` *(owner determination)*, `D23`, `D24`–`D35`, `D36`, `D38`, `D39`, `D40`, `D43`, **`D54`** *(MVP scope at the freeze — §11.4)*. Each is recorded in `DECISIONS.md` with its reasoning.

### 11.2 Open and gating the MVP

| # | Decision | Needed by |
|---|---|---|
| `D37` | SCM enforcement mechanism — **refused-binding declaration in force**; requires a pilot customer's platform team | `MVP-R3.1` / `AC-45` |
| ~~`D41`~~ | **Closed 13 Sept 2026 (MV1-T07): published with the release**, inside the VSIX via `docs/DEPLOYMENT.md`. It discloses only what has been tested, and withholding it would make an evaluator email us to learn whether their OS is supported — which §0.4 forbids | — |
| `D21` | Whether the Orchestra tier is built at all | **`N3` decides** |
| `D42` | Whether the deterministic-engine investment gate binds the build agent | Before further `M33` growth |

### 11.3 Open and post-MVP

`D1`, `D2`, `D3`, `D5`, `D6`, `D7`, `D8`, `D11`, `D12`, `D13`, `D14`, `D15`, `D16`, `D17`, `V1`, `V5`, `V6`, `V9`, `V10`, `V11`, **`D48`** *(whether to ship an MCP gateway at all, or stay a notary — `M48`)*, **`D49`** *(SPIFFE dependency: consume-if-present or bundle — `M49`)*, **`D50`** *(which third-party provenance formats to read first — `M52`)*, **`D51`** *(witness interoperability target, reopening `D39` against the new standards bodies)*, **`D52`** *(whether the AI-BOM is published publicly or under agreement, alongside `D41`)*, **`D53`** *(whether longitudinal outcomes are offered before `MV5` returns, given `P29`)*, and **`D44`–`D47`** (harness adoption, generator, registry contents, trainable surface — renumbered from `jit-requirements.md`'s `D24`–`D27`).


### 11.4 `D54` — MVP scope determination at the freeze · **closed**

**Owner determination, 12 September 2026.** The final freeze audit found four requirements that were not in the MVP and argued they should be. Widening MVP scope is explicitly the owner's call under §19.1, not the author's, so it was put to the owner and confirmed.

| Admitted | Why it qualifies under §19.1 |
|---|---|
| `MVP-R3.7` — banned patterns 28 and 30 get named tests | **Defends a claim already made.** §9.3 asserted those patterns were test-enforced; two were not. The choice was to build the tests or withdraw the claim, and withdrawing it weakens `X-27` and `X-28`, which the tiering and vendor-tag claims rest on |
| `MVP-R8.1` vulnerability disclosure · `MVP-R8.2` third-party notices · `MVP-R8.3` support and upgrade policy | **Defend the MVP definition itself.** §0.4 promises an organisation can *operate and leave* without talking to us. A security review that cannot find a disclosure process, and a procurement desk that cannot enumerate dependencies, both stop the adoption the MVP exists to enable |

**No trade-out was required.** §19.1 asks what moves out only when scope widens for a new capability; all four defend claims already made, which is the same test `MVP-R7` passed. Cost: roughly one week, in `MV1-T13` and `MV4-T09`.

**This closes the scope question for the freeze.** Further additions follow §19.1 from here, and the default for anything discovered during build is `POST-MVP`.

---

## 12. Risks

`R1`–`R25` (`Requirements_Final.md`), `R26`–`R30` (`gaps-requirements.md`), `R31`–`R36` (`futures_requirements.md`) and **`R37`–`R40`** (harness, renumbered) are all retained. The four that bear hardest on the MVP:

| # | Risk | MVP control |
|---|---|---|
| `R29` | The Orchestra tier never earns its place and the product is "just" a flight recorder | **Designed as an acceptable outcome.** The MVP is complete without it |
| `R32` | SCM enforcement refused by platform teams | `FR-M42-11` declares the weaker boundary honestly rather than hiding it |
| `R36` | The evidence gate returns an unfavourable result | Every MVP requirement supports a claim already made and holds regardless |
| `R30` | Dependence on incumbent goodwill | Observation uses only open surfaces — ACP, OTel, git — no vendor can revoke them without breaking their own users |

**Added by the §16 review:**

| # | Risk | Impact | Control |
|---|---|---|---|
| **R41** | **A rival closes the remaining two clauses** — adds signing and a merge binding to cross-vendor line-level provenance | **High** | `MK8` fires; the position is reassessed honestly, as `NK6` already requires. Meridian's head start is the *verifier* and the *gate binding*, both shipped and tested |
| **R42** | **The nearest competitor is bundled into the SCM** the customer already buys (`CMP-02`) | High | Do not contest bundling (`P20`). Compete where a bundle cannot go: evidence that verifies without **any** vendor, including the SCM vendor |
| **R43** | **The agent gateway becomes the buyer's mandatory control point** and Meridian is not in it | Medium | `FR-M48-03` — consume the gateway's log rather than replace it. Meridian is the notary, not the seventh gateway (`P31`) |
| **R44** | **A logging standard is harmonised and Meridian's information model diverges** | Medium | `FR-M50-01` maps rather than invents; `NFR-54` re-verifies each release; `prEN ISO/IEC 24970` is tracked from draft |
| **R45** | **Notarising a third-party record is read as endorsing it** | Medium | `SEC-43` — the digest is signed, the content is not vouched for, and the interface says which |
| **R46** | **The competitive review itself becomes a marketing claim** | Medium | §18 forbids it; `NFR-54` re-verifies; `MP5` binds every shipped claim to a test |

---

## 13. What the MVP claims, exactly

Written so it can be lifted into external material without a lawyer or a caveat.

**Meridian Loom records what AI coding agents do in your repositories, applies your permission policy to them, and produces evidence that a third party can verify on a machine that has never had Meridian installed.**

Supporting claims, each backed by a named test:

- It works with the agents you already run, and requires no change to them (`AC-30`, `FR-M35-06`).
- Its record survives its own uninstallation (`AC-33`, `AC-49`).
- Its numbers state their own coverage and never silently truncate (`AC-41`).
- It reports what it does not know rather than inferring it (`AC-42`).
- A non-human approval never counts as a human one (`AC-44`).
- Disabling a tier leaves the tiers below whole (`AC-36`).
- The base tier makes no model calls at all (`FR-M36-07`).

**Claims the MVP does not make:** that it improves delivery outcomes, reduces defects, saves cost or raises productivity. Those require `N3`, which has not run, and `FR-M46-15` requires unfavourable results to be published when it does.

---

## 14. `M47` Harness Intelligence — retained in full

`jit-requirements.md` is carried here under renumbered identifiers so that nothing is lost and nothing collides. Its own conclusion governs its disposition: **the artifact half is unconditional, the synthesis half is a funded experiment.**

| New ID | Was | Requirement summary | Disposition |
|---|---|---|---|
| `FR-M47-01`…`05` | `FR-M41-01`…`05` | Harness as a first-class, versioned, digest-pinned declarative artifact over a whitelisted module registry; recorded on every ledger entry; travels in `learned/`; fixed harnesses expressed in the same format | **`POST-MVP` — first candidate after the MVP.** Provenance value with zero synthesis |
| `FR-M47-06`…`08`, `20` | `FR-M41-06`…`08`, `20` | Archive, deterministic retrieval before synthesis, amortisation telemetry, hygiene | `POST-MVP` |
| `FR-M47-09`…`15` | `FR-M41-09`…`15` | GENERATE → VALIDATE → REVIEW → REPAIR → SELECT → EXECUTE, with the novelty gate | `POST-MVP`, gated on `D44` |
| `FR-M47-16`…`19` | `FR-M41-16`…`19` | Outcome feedback, promotion to default, reclassification, trainable surface | `POST-MVP` |
| `FR-M47-21`…`26` | `FR-M41-21`…`26` | Shadow-first, kill switch, blast-radius ceiling, diff view, attribution, pinned generator | `POST-MVP` |
| `NFR-44`…`46` · `SEC-39`…`41` · `AC-54`…`58` · `R37`…`40` · `D44`…`47` · `P30` | `NFR-33`…`35` · `SEC-31`…`33` · `AC-41`…`45` · `R31`…`34` · `D24`…`27` · `P25` | As specified in `jit-requirements.md` | `POST-MVP` |

**`SEC-26` is unchanged and unweakened by this module**: a harness is declarative YAML over a registry of reviewed product code. Free-form generated code is never a harness.

---

## 15. Traceability — source document to disposition

| Source document | Contribution | Fully retained? |
|---|---|---|
| `vision.md` | Domain model, agent taxonomy, loop model, ledger design, KPI set, honest-limits stance | **Yes.** Orchestra content is `POST-MVP` |
| `Requirements_Final.md` | M1–M33 (§3.1), 311 module FRs, **67 SDLC phase FRs `FR-P1`…`FR-P9` (§3.6)**, NFR-01…27 (§6), SEC-01…26 (§7), AC-01…29 (§8), **ECO-01…08 (§3.7)**, P1–P19 (§2), D1–D18 (§11) | **Yes.** Every ID dispositioned |
| `Requirements-implementation.md` | E1–E14 build principles, S0/C1–C6 phases, slip plan, risk schedule | **Yes.** Phases superseded by `gaps_implementation.md`; principles in force |
| `VIGUIX_Final.md` | 44 screens, X-01…26, 27 banned patterns, 6 themes, motion, accessibility | **Yes.** All 52 screens (44 + 6 + 10.51 + 10.52) dispositioned in §9.1 |
| `viguix-implementation.md` | B1–B14 principles, G0–G8 phases | **Yes.** Phases superseded by `gaps_guix_implementation.md` |
| `gaps-requirements.md` | P20–P24, M34–M39, NFR-28…32, SEC-27…29, AC-30…37, R26–R30, D19–D22 | **Yes.** The star-ranking table in §10 is **withdrawn from external use** per `futures.md` |
| `gaps_implementation.md` | G1–G7 principles, F−1…F4+ phases, kill criteria, slip plan | **Yes.** The delivery spine |
| `gaps_guix.md` | DS-1…5, X-27…31, screens 10.45–10.50, banned 28–32, A-09…11 | **Yes** |
| `gaps_guix_implementation.md` | H1–H7 principles, GF0–GF4+ phases, competitor parity programme | **Yes** |
| `gaps_initiation.md` | M40, §7.11 RunRequest, screen 10.51, SEC-30, AC-38…40 | **Yes.** `MVP-R4` carries the invariant; the rest is `POST-MVP` |
| `futures.md` | Competitive review, FUT-001…036, the honest-claims constraint | **Yes.** The claims constraint is binding on all MVP material |
| `futures_requirements.md` | P25–P29, M41–M46, **AMD-M10…AMD-M39 (§3.8)**, NFR-33…43, SEC-31…38, AC-41…53, R31–R36, D36–D43 | **Yes.** Numbering authoritative |
| `futures-implementation.md` | J1–J9 principles, N0–N4 phases | **Yes.** The assurance track |
| `jit-requirements.md` | Harness intelligence | **Yes**, renumbered to `M47` (§14) |
| `jit-impl.md` | J1–J4 sub-phases, J-P1…J-P6, JK1–JK6 | **Yes**, `POST-MVP` (§14) |
| `status.md` | The audit that produced findings G-01, G-02, G-03 | **Yes.** All three closed |
| `DECISIONS.md` | D1–D43 with reasoning | **Yes.** §11 |
| `sample-meridian-loom-gui.html` | Design reference | **Yes.** §9.5 — reference, not a build target |
| **Competitive review, 12 Sept 2026** | `CMP-01`…`CMP-10`, modules `M48`–`M52`, `P31`–`P34`, `NFR-47`…`54`, `SEC-42`…`48`, `AC-59`…`68`, `R41`–`R46`, `D48`–`D53`, screens 10.53–10.55, `X-32`/`33` | **Yes.** §§16–18. Four items enter the MVP as `MVP-R7`; the rest is `POST-MVP` |

---

## 16. Competitive position — reviewed 12 September 2026

`futures.md` reviewed the landscape on 9 September 2026 and told the truth about it, including the instruction to **withdraw the star-ranking table in `gaps-requirements.md` §10 from external use**. That instruction stands and is reinforced by this review.

**Method and its limits.** Searched September 2026; vendor documentation and vendor blogs are read as *claims by that vendor*, not as verified capability. No competing product was installed or tested. A capability recorded as absent means **not established in this review**, never proven absent. Every row below is usable internally; **none of it may be lifted into external material without re-verification against primary sources on the day it is used** (`MP5`).

### 16.1 What changed since 9 September

| # | Finding | Why it matters to Meridian |
|---|---|---|
| **CMP-01** | **Cross-vendor, on-machine, line-level AI provenance is now a shipped product category.** Exceeds Ink is documented as capturing authorship across Claude Code, Cursor, Codex, Copilot and Windsurf at line level, writing a structured attestation as a **Git Note at `refs/notes/exceeds-ink` at commit finalisation** via `prepare-commit-msg` / `post-commit` / `post-rewrite` hooks, each line carrying tool, model, session, interaction mode and timestamp — and with unattributable lines recorded as **`unknown_lines` rather than assigned to human** | **The closest any product has come to Meridian's core claim, and it independently arrives at Meridian's own three-state discipline (`P26`).** It narrows the moat. It does not close it: nothing in the reviewed material documents a hash chain, a signature, inclusion proofs, an independent verifier, or a binding to a merge decision — and a git note is editable by anyone with push access, the same limitation Meridian already states about its own trailer (`docs/SECURITY-AND-DATA.md` §6) |
| **CMP-02** | **DX was acquired by Atlassian for about one billion dollars** and is being folded into Jira, Bitbucket and Rovo Dev | The nearest attribution competitor now ships **inside the SCM the customer already pays for**. Meridian cannot win a bundling contest and must not try (`P20`) |
| **CMP-03** | **A category that did not exist in `futures.md` now does: the agent gateway.** Pomerium, Aembit, Snowflake, Google's Agent Gateway with an Agent Registry, and the **Enterprise-Managed Authorization extension to MCP (June 2026)** place an enforcement point **at the tool call** | Meridian governs at the **merge**; these govern at the **call**. A buyer with an agent gateway will ask why Meridian does not sit there too. `M48` answers it |
| **CMP-04** | **Attested agent identity has a consensus answer: SPIFFE/SPIRE**, CNCF-graduated, short-lived attestation-based credentials; **ATTP** (draft, 1 May 2026) adds five hierarchical trust levels with tamper-evident audit | Meridian's weakest link is a self-asserted identity (`D38`, `NK3`). **Workload attestation closes it without a human identity provider** — exactly the funding objection `R33` anticipated. `M49` |
| **CMP-05** | **The published enterprise reference architecture is three layers** — an LLM gateway, an MCP gateway with a registry, and an agent identity system carrying **cryptographically attested lineage on every tool call** | The shape Meridian will be compared against in a 2026 architecture review. Meridian has the ledger and the permission check; it does not have the gateway shape |
| **CMP-06** | **`prEN ISO/IEC 24970` / `ISO/IEC DIS 24970` — AI system logging** — defines a common information model for AI event logs, last updated April 2026. **It is not a harmonised standard, so it grants no presumption of conformity** | The information model Article 12 logging will be read against. Mapping to it is cheap and is what a buyer asks for; claiming conformity from it would be the overreach `P27` forbids |
| **CMP-07** | **EU AI Act: Article 26 obliges deployers to retain logs for at least six months**; Annex III obligations from 2 August 2026, with differentiated timelines running to December 2027 and August 2028; **Article 50 requires cryptographic provenance marking for AI-generated content** | Retention is now an obligation with a number. Meridian's multi-year retention (`FR-M43-04`) exceeds it, and the export should say so in the buyer's own vocabulary |
| **CMP-08** | **Supply-chain attestation has settled**: SLSA for what to claim, **in-toto for the claim format, DSSE for the envelope**, Sigstore for signing. **CycloneDX now covers AI components (AI-BOM)**, and an **Agent Skill Bill of Materials** pattern has appeared | Meridian **ships 22 agents and a 10-pack skill catalogue** and publishes no bill of materials for them. A procurement blocker with a cheap fix |
| **CMP-09** | **Vendor-neutral verifiable-audit standards bodies have appeared** — VeritasChain's VCP, the LedgerProof receipt standard, and C2PA's 2026 conformance programme for content credentials | `P21` says implement the standard where one has won. None has won yet, but Meridian's witness seam (`FR-M43-01`) should be shaped to interoperate rather than to be bespoke |
| **CMP-10** | Vendor-side governance keeps moving: enterprise-managed default models and content exclusions added to Copilot in early September 2026; Claude Code Enterprise carries SCIM, audit logs and MCP-server access control; **Cursor's and Claude Code's native logging are repeatedly described as thinner than Copilot's** | `R27` remains live and `FR-M44-11`…`13` remain the control. Observers must be re-qualified per vendor release, not per year |

### 16.2 The honest reassessment against `K6` / `NK6`

`gaps_implementation.md` `K6` and `futures-implementation.md` `NK6` both say: **if an incumbent ships cross-vendor, independently verifiable, retention-independent provenance bound to a merge decision, the position is gone.**

**It has not happened, and it is closer than it was.** `CMP-01` delivers cross-vendor and retention-independent. On the reviewed evidence it does not deliver *independently verifiable* — no signature, chain, proof or third-party verifier is documented — and it does not deliver *bound to a merge decision*.

**The differentiator is therefore narrower than the old wording and must be stated more precisely.** Not "cross-vendor provenance", which is no longer unique. The claim is:

> **A signed, hash-chained, independently verifiable record of what an agent did, bound to the human decision that let it merge, that a third party can verify on a machine that has never had Meridian installed — and that keeps verifying after Meridian is uninstalled.**

Every clause is `BUILT` and test-backed (`AC-49`, `AC-33`, `AC-44`, `FR-M42-01`). **`MVP-R7.4` makes restating it a release task**, because the older, broader wording is now partly false.

**Cadence:** re-verified at every release. `MK8` in `mvp-impl-plan.md` fires if a competitor closes the remaining two clauses.

---

## 17. New modules from the competitive review — M48 to M52

All five are **`POST-MVP`** except where a specific requirement is pulled into `MVP-R7`. They are specified now so the ambition is recorded and the MVP is not quietly widened to meet it.

### 17.1 `M48` — Tool-Call Governance and Lineage · `POST-MVP`

*Governance.* **Answers `CMP-03`, `CMP-05`.** Meridian governs the merge. The 2026 enterprise pattern also governs the call.

| ID | Requirement | Priority |
|---|---|---|
| `FR-M48-01` | Meridian SHALL be deployable as an **MCP gateway** between a hosted agent and its tool servers, applying the existing policy engine to each call **before** it reaches the server, and recording the decision in the ledger. | MUST v1.x |
| `FR-M48-02` | Every governed tool call SHALL record an **attested lineage chain** — which agent identity, under which policy version, on whose authority, for which run — so a call can be traced to the human who authorised the run that produced it. | MUST v1.x |
| `FR-M48-03` | The gateway SHALL be **optional and additive**: an organisation that already operates an agent gateway SHALL keep it, and Meridian SHALL consume that gateway's decision log as an observer rather than requiring replacement (`P20`). | MUST v1.x |
| `FR-M48-04` | Gateway enforcement SHALL declare its enforcement point per `FR-M42-11`, and SHALL NEVER be described as enforced for calls that bypass it. | MUST v1.x |
| `FR-M48-05` | Tool-call lineage SHALL appear in the evidence bundle as a predicate distinct from build provenance and from agent activity (`FR-M43-10`). | SHOULD v1.x |

### 17.2 `M49` — Attested Agent and Workload Identity · `POST-MVP`

*Identity.* **Answers `CMP-04`, and `R33` / `NK3` head-on.**

| ID | Requirement | Priority |
|---|---|---|
| `FR-M49-01` | An agent identity SHALL be derivable from **runtime attestation** — executable digest, resolved version, publisher, platform attestation where available — rather than from a self-asserted name, satisfying `FR-M44-01` by a mechanism that needs no human identity provider. | MUST v1.x |
| `FR-M49-02` | Meridian SHALL support **SPIFFE-compatible workload identity** for the sidecar and for hosted agents, consuming an existing SPIRE deployment where the organisation has one and never requiring one where it does not. | SHOULD v1.x |
| `FR-M49-03` | Identity assurance SHALL remain a **declared level**, never a binary. Attested, verified, asserted and unknown SHALL each be distinguishable in the ledger and on every surface (`FR-M42-04` extended). | MUST v1.x |
| `FR-M49-04` | Credentials issued to agents SHALL be **short-lived and non-exportable**, and SHALL never be placed in process arguments or environment (`SEC-27`, existing posture). | MUST v1.x |
| `FR-M49-05` | Where a trust-level vocabulary such as ATTP's is in use at a customer, Meridian SHALL be able to **record** the level asserted per session without adopting that vocabulary as its own. | SHOULD v2 |

### 17.3 `M50` — Standards Conformance and Interoperable Evidence · partly MVP

*Record and assurance.* **Answers `CMP-06`, `CMP-07`, `CMP-08`, `CMP-09`.**

| ID | Requirement | Priority |
|---|---|---|
| `FR-M50-01` | The evidence bundle SHALL carry a mapping to the **`ISO/IEC 24970` AI system logging information model**, alongside its existing SSDF, ISO/IEC 42001 and AI Act Article 12 mappings. | **MVP** (`MVP-R7.2`) |
| `FR-M50-02` | Every mapping SHALL state, in the bundle and in the documentation, **what it is and what it is not** — supporting evidence with a version and a scope, never a certification, and explicitly **not a presumption of conformity** where the standard is not harmonised. | **MVP** (`MVP-R7.2`) |
| `FR-M50-03` | The bundle SHALL state the **retention actually available** against the deployer obligation of AI Act Article 26 (at least six months), so a reader sees the margin rather than computing it. | **MVP** (`MVP-R7.2`) |
| `FR-M50-04` | Meridian SHALL publish a **CycloneDX AI-BOM** for what it ships — every bundled agent, skill pack, instruction document and runtime preset, with versions and digests — as a release artefact beside the VSIX and its checksum. | **MVP** (`MVP-R7.3`) |
| `FR-M50-05` | An organisation SHALL be able to generate an **AI-BOM for its own installed set**, including adapters it imported, from the headless CLI. | MUST v1.x |
| `FR-M50-06` | Attestation export SHALL use **in-toto predicates in a DSSE envelope** (`FR-M43-09` / `10`), verifiable with standard tooling rather than only with Meridian's verifier. | `POST-MVP` |
| `FR-M50-07` | The witness seam (`FR-M43-01`) SHALL be shaped to interoperate with an external verifiable-audit or transparency service rather than with a bespoke protocol, and the choice SHALL remain the customer's (`D51`). | `POST-MVP` |
| `FR-M50-08` | Where Meridian records agent-produced **content** rather than code, it SHALL be able to emit a C2PA-compatible content credential, and SHALL NOT claim Article 50 marking for anything else. | `POST-MVP` |

### 17.4 `M51` — Longitudinal Outcome Evidence · `POST-MVP`

*Measurement.* **Answers `CMP-01`'s strongest non-provenance feature.**

| ID | Requirement | Priority |
|---|---|---|
| `FR-M51-01` | Meridian SHALL report, per agent and per attribution state, the **30-, 60- and 90-day post-merge outcome** of changes: revert rate, follow-on edit rate, linked incidents, and test-coverage change. | MUST v1.x |
| `FR-M51-02` | Every longitudinal figure SHALL carry the coverage envelope (`FR-M41-08`) and the censoring rule applied to changes younger than the window (`FR-M41-13`). | MUST v1.x |
| `FR-M51-03` | Outcomes SHALL be attributable to **the gate decision that allowed the merge**, not only to the agent — the binding no reviewed competitor documents (`FR-M45-01`). | MUST v1.x |
| `FR-M51-04` | A correlation SHALL NEVER be presented as a causal claim, and comparison across agents SHALL be suppressed where cohorts are not comparable (`FR-M41-15`). | MUST v1.x |

### 17.5 `M52` — Interoperability with Other Provenance Tools · partly MVP

*Record.* **Answers `CMP-01`, `CMP-02`, and `P20` applied to competitors rather than to agents.**

The strategic point, stated once: **where another tool already records, read its record and notarise it. Do not compete on capture.**

| ID | Requirement | Priority |
|---|---|---|
| `FR-M52-01` | Meridian SHALL read provenance records written by other tools into the Weave and the ledger as observed evidence at their documented confidence — **git notes under other tools' refs**, `Co-Authored-By` trailers, agent-session-log trailers, and any vendor blame API the organisation has licensed. | **MVP** (`MVP-R7.1`) |
| `FR-M52-02` | A record written by another tool SHALL be labelled with **that tool as its source** and SHALL never be presented as Meridian's own observation. Reading a third-party note SHALL NOT raise confidence above `inferred` unless Meridian independently observed the same act. | **MVP** (`MVP-R7.1`) |
| `FR-M52-03` | Meridian SHALL be able to **notarise** a third-party provenance record: include its digest in the signed ledger so that the third-party record becomes tamper-evident **without Meridian having captured it**. This is the capability no reviewed competitor offers, and it costs almost nothing to provide. | **MVP** (`MVP-R7.1`) |
| `FR-M52-04` | Export SHALL be possible **to** the formats other tools consume, so adopting Meridian does not strand a team's existing tooling (`P24`). | MUST v1.x |
| `FR-M52-05` | Meridian SHALL NOT require removal of any other provenance tool, and SHALL report a conflict between two tools' attributions of the same span as a distinct, reportable disagreement rather than silently preferring one. | MUST v1.x |

---

## 18. What the competitive review does not change

Recorded so it is not re-argued at the next review.

- **The MVP definition (§0.4) is unchanged.** None of `CMP-01`…`CMP-10` alters what a pilot organisation needs in order to adopt this package.
- **`M48`…`M52` do not enter the MVP** except through the four `MVP-R7` items. A competitive review that rewrites the release scope is a roadmap, not a review.
- **Feature parity remains unwinnable and remains out of scope** (§1.3). `CMP-02` is the proof: the nearest competitor now ships inside Jira and Bitbucket.
- **No claim in §13 is widened.** `MVP-R7.4` makes one of them *narrower*, because the broader version is now partly false.
- **No figure from this review becomes a marketing claim.** Every finding is a vendor's own documentation, read once, on one day.

---

## 19. Change control after the freeze

**This document is frozen at v1.1. From here the work is implementation, not specification.** A frozen requirement set that has no way to change is not disciplined, it is brittle — so the way to change it is written down rather than left to judgement in the moment.

### 19.1 What a change costs

| Change | Route | Who decides |
|---|---|---|
| **A `MVP-GAP` requirement turns out to be wrong, ambiguous or unbuildable as written** | Raise it against the requirement ID, state the ambiguity in one sentence, and propose the narrowest wording that removes it. Amend in place, bump the document version, record the reason in `DECISIONS.md` | Owner |
| **A requirement's disposition needs to change** — `MVP-GAP` to `POST-MVP`, or the reverse | **This is a scope change and it goes through the slip plan** (`mvp-impl-plan.md` §10), not through an edit. Moving something *into* the MVP requires naming what moves out | Owner, in writing |
| **A new requirement is discovered during build** | It is `POST-MVP` by default. It enters the MVP only if it defends a claim the MVP already makes — the same test `MVP-R7` had to pass | Owner |
| **A competitor or standard changes the picture** | §16 is re-verified at every release (`NFR-54`). Findings land as new `CMP-nn` rows and, if they bear on a claim, as `MP5` work | Owner |
| **A measured number in §4 changes** | **The number wins, always.** §4 is re-measured at each phase exit and corrected in place. A document that disagrees with a measurement is wrong by definition (`MP1`) | Nobody — it is mechanical |

### 19.2 What may not change without the whole document being re-opened

These are load-bearing. Changing any of them changes what the product *is*, not what it does:

- **The MVP definition** (§0.4) and the tier model (§1.2)
- **The exact claim** (§13, §16.2) and the list of claims the MVP does not make
- **The `M41` collision resolution** (§0.3) — code depends on it
- **The never-cut list** (`mvp-impl-plan.md` §10)
- **`P20`, `P22`, `P25`–`P28`, `P31`** — the principles the product's honesty rests on

### 19.3 The freeze does not freeze the truth

Nothing here prevents recording that a statement in this document turned out to be false. **It requires it.** A frozen specification that is known to be wrong and left standing is worse than no specification, and §4's own history is the example: it claimed a green suite that was not green, and the correction is recorded in §4.3 rather than quietly applied.

---

## 20. Glossary

Written for whoever implements this, including the author in six months. Domain terms first, then the vocabulary the code enforces.

### 20.1 The loom metaphor

| Term | Means |
|---|---|
| **The Weave** | The main visualisation: every agent pass across a story, one row per pass, read left to right through the SDLC phases |
| **Weft row** | A single agent pass in the Weave — one agent, one phase, one time window |
| **Warp Spine** | The vertical phase structure the weft crosses. Comes from policy, never hard-coded (`B8`) |
| **Selvage** | The chain-integrity strip along the edge: verified to sequence N, or the first divergent sequence named |
| **Crown** | The status bar at the top of the shell — active sessions, recording state, tier |
| **Loom Bar** | The primary navigation |
| **The cloth** | Everything recorded, collectively. "A gap in the cloth" means observation went silent, which `G3` forbids |
| **The Floor** | The spatial agent view (Orchestra tier, `POST-MVP`) |
| **The Dojo** | The training and promotion surface (Orchestra tier, `POST-MVP`) |

### 20.2 Units of work

| Term | Means |
|---|---|
| **Story** | A unit of delivery work, usually from a tracker. The thing a run is about |
| **Run** | One governed execution against a story. Carries a `run_id` and an `origin` (`MVP-R4.1`) |
| **Packet** | A contracted unit of work inside a run, with its own acceptance tests (Orchestra tier) |
| **Pass** | One agent's contribution to a story in one phase — what a weft row shows |
| **Blast radius** | The classified reach of a change: `low`, `medium`, `high`. Raises gate strictness |

### 20.3 Agents and what they are made of

| Term | Means |
|---|---|
| **Adapter** | Any agent, packaged. An ACP agent plus a Meridian governance manifest (`FR-M34-02`) |
| **Role Agent** | One of the twelve delivery roles (`vision.md` §2.3) |
| **Stack Agent** | A Role Agent bound to a **Skill Pack** at runtime. Identity is data, not code |
| **Skill Pack** | A `SKILL.md` folder: standards, layout, build invocations, idioms, checklist |
| **Instruction file** | `AGENTS.md`, `CONVENTIONS.md` and similar — how this organisation works, versioned and reviewed like code |
| **Harness** | The four-module composition (memory, planning, action, capability) a run executes under. `M47`, `POST-MVP` |
| **Probation** | The state every newly added agent enters: `read`, `search`, `think` only, until policy widens it |
| **Learning room** | The interface state for an agent in probation |

### 20.4 The vocabulary the code enforces

**These are closed vocabularies. A value outside them is a defect, not a variation.**

| Vocabulary | Values | Rule |
|---|---|---|
| **Observation confidence** | `direct` · `telemetry` · `inferred` | Each has a structural ceiling per observer. `inferred` never renders like `direct` (`H5`, banned 31) |
| **Attribution state** | `agent` · `human` · `unattributed` | Never derived by subtraction (`P26`, `FR-M41-04`) |
| **Unattributed reason** | `no_signal` · `formatter_rewrite` · `squashed_history` · `pre_installation` · `unsupported_vendor` · `excluded_path` | Every `unattributed` span carries one (`FR-M41-05`) |
| **Approval class** | `human_verified` · `human_asserted` · `policy_rule` · `model_classifier` · `bypass_actor` · `unknown` | A non-human class never satisfies a human-approval policy (`FR-M42-08`) |
| **Enforcement point** | `editor` · `extension_host` · `sidecar` · `scm` · `ci` · `advisory_only` | Declared by every control. Client-side is never rendered as "enforced" (`FR-M42-11`/`12`) |
| **Identity assurance** | `attested` · `verified` · `asserted` · `unknown` | `attested` arrives with `M49`; the MVP ships `asserted` and says so |
| **Cost provenance** | `invoice_reconciled` · `vendor_api` · `locally_inferred` · `unknown` | Never summed across classes without a breakdown (`FR-M45-04`) |
| **Run origin** | `ui` · `command` · `omnibar` · `chat` · `editor` · `file` · `connector` · `api` | Recorded on the run's first ledger entry (`FR-M40-02`) |
| **Action class mode** | `deterministic` · `assisted` · `generative` | Dispatch is deterministic-first; a model call records `why_llm` (`P17`, `E13`) |

### 20.5 Evidence terms

| Term | Means |
|---|---|
| **Ledger** | The local append-only hash-chained store. **A transparency log, not a blockchain** — tamper-evident, not tamper-proof |
| **Tree head** | A signed Merkle root covering the chain to a given sequence |
| **Inclusion proof** | The Merkle path proving one entry is in a given tree head |
| **Bundle** | A signed export: entries, proofs, tree head, public key, schema version, collection profile, redaction section, compliance mappings |
| **Trailer** | The `Meridian-Ledger:` git commit trailer — a published, versioned pointer into the record. **Editable; it is a pointer, not a proof** |
| **Notarise** | To put a *third party's* provenance record's digest into the signed ledger, making their record tamper-evident without having captured it (`FR-M52-03`). **Signing the digest is not vouching for the content** (`SEC-43`) |
| **Coverage envelope** | The wrapper every metric returns: `value`, `rowsConsidered`, `rowsAvailable`, `truncated`, `sequenceRange`, `coverage`. `truncated` is **derived, never supplied** |
| **Collection profile** | `metadata_only` (default) · `content_redacted` · `content_full` (requires recorded consent) |
| **Crypto-shredding** | Erasure by destroying the subject's key. Content becomes unreadable; the chain still verifies |
| **Witness** | An external holder of signed tree heads. Optional, customer-controlled, **not yet built** — and the absence is stated (`FR-M43-03`) |

### 20.6 Dispositions and phases

| Term | Means |
|---|---|
| **`BUILT` / `MVP-GAP` / `MVP-HUMAN` / `POST-MVP`** | §0.5. A statement about this release, never about value |
| **`MV0`–`MV5`** | The MVP route (`mvp-impl-plan.md`) |
| **`CP1`–`CP4`** | The competitive track, after `MV5` |
| **`F0`–`F4+` / `GF0`–`GF4+` / `N0`–`N4` / `S0`, `C1`–`C6` / `G0`–`G8` / `J-1`–`J-4`** | The predecessor tracks, retained in `mvp-impl-plan.md` §8 |
| **Tier** | Flight Recorder → Governor → Orchestra. A disabled tier is **absent**, never greyed out |

---

*End of requirements, frozen at v1.1. `mvp-impl-plan.md` governs the order in which the `MVP-GAP` items are built; §19 governs how this document may change. No identifier in any source document has been deleted, the `M41` collision is resolved in favour of the implemented meaning, and the one false statement the freeze audit found is corrected in §4.3 rather than quietly removed.*
