# Meridian Loom — MVP Implementation Plan

**Version 1.1 · 12 September 2026 · governs a FROZEN requirement set**
**Governs:** `mvp-req-final.md` v1.0
**Status:** the route from the `0.1.0` baseline to a package a pilot organisation can adopt. `mvp-req-final.md` is frozen at v1.1; this plan is not — task detail is refined as the work is done, scope is not.

---

## Table of Contents

- [0. About this plan](#0-about-this-plan)
- [1. How to use this document](#1-how-to-use-this-document)
- [2. Build principles — the consolidated register](#2-build-principles--the-consolidated-register)
- [3. Stack decisions](#3-stack-decisions)
- [4. Phase map](#4-phase-map)
- [MV0 — Quiesce and baseline](#mv0--quiesce-and-baseline)
- [MV1 — Truthful surfaces](#mv1--truthful-surfaces)
- [MV2 — Run initiation](#mv2--run-initiation)
- [MV3 — Supply chain and reach](#mv3--supply-chain-and-reach)
- [MV4 — Release readiness](#mv4--release-readiness)
- [MV5 — The evidence gate](#mv5--the-evidence-gate-mvp-human)
- [5. Cross-cutting workstreams](#5-cross-cutting-workstreams)
- [6. Definition of done](#6-definition-of-done)
- [7. Sequencing and interlock](#7-sequencing-and-interlock)
- [8. The retained phase register](#8-the-retained-phase-register)
- [9. Kill and stop criteria](#9-kill-and-stop-criteria)
- [10. Slip plan](#10-slip-plan)
- [11. Risk retirement schedule](#11-risk-retirement-schedule)
- [12. Decision schedule](#12-decision-schedule)
- [13. The release procedure](#13-the-release-procedure)
- [14. What this plan deliberately does not schedule](#14-what-this-plan-deliberately-does-not-schedule)
- [15. Traceability appendix](#15-traceability-appendix)
- [16. The competitive track — CP1 to CP4](#16-the-competitive-track--cp1-to-cp4--post-mvp)
- [17. Artefact register](#17-artefact-register--what-this-plan-creates)
- [18. Definition of done — the MVP as a whole](#18-definition-of-done--the-mvp-as-a-whole)

---

## 0. About this plan

### 0.1 What this plan is

`mvp-req-final.md` says **what** the MVP is and dispositions every requirement in the programme as `BUILT`, `MVP-GAP`, `MVP-HUMAN` or `POST-MVP`. This document says **in what order the `MVP-GAP` items are built, by whom the `MVP-HUMAN` items are answered, and what evidence closes each one.**

It schedules **nothing that is already `BUILT`** and **deletes nothing that is `POST-MVP`**. Every phase identifier from every predecessor plan survives in §8 with its status and its relationship to this route.

### 0.2 The six plans this one composes

| Plan | Contributed | Status under this plan |
|---|---|---|
| `Requirements-implementation.md` v2.1 | `E1`–`E14` build principles · `S0`, `C1`–`C6` phases · slip plan · risk schedule · decision schedule | Principles **in force**. Phases superseded as a *route*, retained as a *destination* (§8) |
| `viguix-implementation.md` v2.1 | `B1`–`B14` principles · `G0`–`G8` GUI phases · GUI interlock | Principles **in force**. Phases superseded by `GF*` as a route, retained (§8) |
| `gaps_implementation.md` | `G1`–`G7` principles · `F−1`, `F0`–`F4+` phases · `K1`–`K7` kill criteria | **The delivery spine.** `F0` and `F1` delivered; `F2` is `MV5` |
| `gaps_guix_implementation.md` | `H1`–`H7` principles · `GF0`–`GF4+` phases · competitor parity programme · `GK1`–`GK6` | **In force.** `GF0`/`GF1` delivered; `GF2` is `MV5` |
| `futures-implementation.md` | `J1`–`J9` principles · `N0`–`N4` phases · `NK1`–`NK7` stop criteria | **The assurance track.** `N0`–`N2` delivered; `N3` is `MV5` |
| `jit-impl.md` | `J-P1`–`J-P6` principles · `J1`–`J4` sub-phases · `JK1`–`JK6` | **Retained whole, `POST-MVP`** (§14). Renumbered to `M47` per `mvp-req-final.md` §14 |

**This plan adds two tracks: `MV0`–`MV5` for the MVP, and `CP1`–`CP4` (§16) for the competitive work that follows `MV5`.** It is deliberately short. The programme's problem is not a shortage of plans.

### 0.3 Namespace resolution

Three collisions exist across the source plans. Each is resolved once, here, and the resolution is the same one `mvp-req-final.md` §0.3 made.

| Collision | Resolution |
|---|---|
| `M41` — "Evidence Completeness and Coverage" (`futures_requirements.md`) vs. "Harness Intelligence" (`jit-requirements.md`) | **Futures wins**, because it is the meaning implemented in code (`FR-M41-08` coverage envelope). Harness intelligence is `M47`. |
| `J1`–`J9` — build principles (`futures-implementation.md`) vs. `J1`–`J4` sub-phases (`jit-impl.md`) | **Principles keep `J1`–`J9`.** Harness sub-phases are written **`J-1`…`J-4`** wherever ambiguity is possible, and their own principles keep `J-P1`–`J-P6`. Both sets survive; neither is renumbered out of existence. |
| `D24`–`D27` (`jit-impl.md`) vs. four closed decisions in `DECISIONS.md` | Harness decisions renumbered **`D44`–`D47`**. `jit-impl.md` §14 is reproduced under the new numbers in §12. |

### 0.4 The baseline this plan starts from

**Verified 12 September 2026, commit `b2c2d9c` plus the working tree, one sequential run per suite under the cross-suite lock:**

| Check | Result |
|---|---|
| Python sidecar | 1,629 passed · 0 failed · 24 m 47 s |
| Extension | 534 passed · 0 failed · 1 skipped |
| Webview | 242 passed · 0 failed |
| **Total** | **2,405 passed · 0 failed · 1 skipped** |
| Surface coverage (`FR-M46-02`) | 63/71 registry methods consumed · 18 declared · **green** |
| Package | `meridian-loom-0.1.0.vsix`, 232 files, SHA-256 published |

**Corrected at the freeze audit, 12 September 2026.** Re-running the suites found the extension suite red: `manifest.test.ts > has no nested extension/extension directory` failed because 37 tracked duplicate library files had returned (CRLF copies of `extension/library/`, the `d698161` regression).

**It then came back a second time**, because the first removal was never committed and the files were still tracked at `HEAD`. Removed for good at `3d25813`. The recurrence exposed a gap in the guard itself — it checks the filesystem, not git — and `MV0-T06` closes it. See `mvp-req-final.md` §4.3 for the full record.

**This plan does not re-derive the baseline; it extends it.** Anything in this document that contradicts a measured number is wrong and the number stands.

### 0.5 What "done" means for this plan

The MVP is delivered when a pilot organisation can, **without contacting us**: read what the software does and where its data goes · check a digest · install a VSIX · validate the install headlessly · bind an agent it already pays for · start governed work · gate a merge · export evidence · verify that evidence on a machine that has never had Meridian installed · and remove the software, leaving the evidence still verifiable.

Nine of those eleven steps are `BUILT`. This plan closes the other two — **starting governed work** (`MV2`) and **reaching the capability that exists** (`MV3`) — and closes the gap between what the surfaces say and what the code does (`MV1`) before either of them is shown to anyone.

---

## 1. How to use this document

- **A task is not started** until its requirement is `MVP-GAP` in `mvp-req-final.md` §5 — which §5.6 makes the complete list — and its predecessor task is closed.
- **A task is not closed** until §6's definition of done is fully satisfied — including the negative control (`MP2`), which is the item this project has historically skipped.
- **A phase is not exited** on a contaminated run. One tree, one sequential suite, one commit (`J9`, `MP3`).
- **A band is a band, not an estimate.** Bands are there so §9's `MK6` has something to measure against.
- Where a task names a file, the file path is where the work lands. Where it names a test, that test is the evidence.

---

## 2. Build principles — the consolidated register

All fifty-four principles from the five predecessor plans remain in force. They are listed here in one place because a principle nobody can find is a principle nobody applies.

### 2.1 Inherited, unchanged

| Set | IDs | Source | One-line summary |
|---|---|---|---|
| **Engineering** | `E1`–`E14` | `Requirements-implementation.md` §2 | Ledger before writers · isolation before autonomy · replay before reasoning · one slice all the way through · bounded loops from the first commit · untrusted-by-default · identity before approval · cost visible · signals accumulate early · fault injection per module · the Simulation Core is real · every agent goes through the adapter protocol including ours · deterministic first with a recorded `why_llm` · learning writes only to `learned/` |
| **Interface** | `B1`–`B14` | `viguix-implementation.md` §2 | Tokens → components → screens · four states per screen · accessibility built in · budgets as CI gates · dense register before spatial · motion last · visual regression from day one · nothing hard-codes the phase set · three access paths on destructive actions · every canvas ships its DOM parallel · cross-cutting systems built once · confidence never renders without calibration · every screen built against the Simulation Core · action class and provenance never hidden |
| **Repositioning** | `G1`–`G7` | `gaps_implementation.md` §2 | Nothing requires a Meridian agent to be useful · where a standard won, implement the standard · observation degrades, never goes silent · provenance survives our own uninstallation · a disabled tier leaves no scar · measure the thing the market does not trust · time-box and cut scope, never quality |
| **Interface gaps** | `H1`–`H7` | `gaps_guix_implementation.md` §2 | Build against recorded reality · vendor tag and confidence are primitive-level invariants · tier disclosure is structural · match before you exceed · inferred never looks like direct · the first screen must be complete alone · every chart states its finding in words |
| **Assurance** | `J1`–`J9` | `futures-implementation.md` §2 | Fix the number before you show it · every aggregate carries its population · no category is a residual · declare the boundary or do not claim the control · assume the vendor disappears · a computed instrument without a consumer is unfinished · delete the duplicate before extending either copy · measure before you widen · one tree, one suite, one commit |
| **Harness** | `J-P1`–`J-P6` | `jit-impl.md` §1 | Record before you generate · retrieval is the default, synthesis the exception · the registry is the trust boundary · shadow before live, per class · an unproven harness is a suspect · report the amortisation from day one |

### 2.2 Added by this plan

Each is derived from something this programme actually got wrong, or from something the market did, not from a general principle of good engineering.

| # | Principle | Consequence | Derived from |
|---|---|---|---|
| **MP1** | **The baseline is evidence, not memory.** | No task re-specifies a capability without first checking the tree for it. A plan that schedules built work burns the one resource the programme is short of. | `mvp-req-final.md` §4 exists because this happened |
| **MP2** | **Every test added must be proven to discriminate.** | A test is accepted only after it has been demonstrated **failing** against the unfixed tree. A test that passes identically before and after a fix is not evidence of the fix; it is evidence of nothing. | Two tests in this repository — a 17 MB frame case and an oversized-manifest case — passed identically before and after the defects they claimed to cover |
| **MP3** | **One tree, one suite, one commit.** | Phase exits are declared against a quiesced tree and a sequential run under the cross-suite lock (`extension/test/run-lock.ts` and `conftest` share `meridian-suite.lock`). A concurrent run is never signal, no matter what it says. | `J9`; three contaminated runs in this repository produced 65, then 18, then 47 minutes of phantom failures |
| **MP4** | **Reachable by a stranger, or not delivered.** | For the MVP, "surfaced" means an evaluator who has not read the source can reach it. `FR-M46-02` proves a method has a caller; `MP4` asks whether a person can find it. Both are required. | `registry-source.ts` — 505 lines, tested, exported, and constructed only in its own test file |
| **MP5** | **The claim ships with the control; the enforcement point ships with the claim.** | `J4` extended to prose. No sentence in a README, a security document, a demo script or a screen outlives the code that makes it true — every external claim is bound to a named test (`MV0-T03`). | The packager once promised a checksum it did not emit; a diagnostic once called a shipped subsystem unbuilt |
| **MP6** | **Nothing built is removed to simplify the MVP.** | Scope moves by **disposition**, never by deletion. A capability outside the MVP is marked `POST-MVP` and left in the tree, working, tested and shipped. | The owner's standing constraint, and the reason §8 exists |
| **MP7** | **Every task ends in the package.** | A change that is not in the VSIX, its staged documents or its checksum did not ship. Verification happens against the **installed** artefact, not the checkout. | `extension/extension/library/` shipped a duplicate library in every VSIX for four commits without a runtime symptom |
| **MP9** | **Read the rival's record before writing your own.** | Where another tool already captured an act, Meridian reads and notarises it rather than re-capturing it. Competing on capture is a treadmill against better-funded vendors; **making someone else's record tamper-evident is a position none of them holds.** | The 12 September review: cross-vendor line-level capture is now a shipped category (`CMP-01`), and `P20` was always the answer to that shape of problem |
| **MP8** | **Human-gated work is never reported as engineering progress.** | An `MVP-HUMAN` item is reported as blocked-on-people, with the people named. It is never counted toward completion, and its absence is never described as a schedule risk owned by engineering. | `F2`/`N3` has been pending since `D35` |

---

## 3. Stack decisions

Inherits `Requirements-implementation.md` §3, `gaps_implementation.md` §3, `gaps_guix_implementation.md` §3 and `futures-implementation.md` §3 in full. These rows are new or changed by this plan.

| Concern | Decision | Rationale |
|---|---|---|
| **Enforcement-point surfacing** | The declaration already computed by `core/meridian_core/governance/enforcement_points.py` (vocabulary `m42-1`) is exposed over one new RPC and rendered by **one primitive** that every control surface composes. Not a prose notice per screen. | `FR-M42-11`, `J4`, `H2`. Two screens carry honest prose notices today; prose does not compose and cannot be enforced by a type |
| **Compatibility matrix format** | A machine-readable `shared/schema/compatibility.json`, one row per claimed combination, each row naming the smoke test that backs it. The published table and the `doctor` output are both **generated** from it. | `FR-M44-08`…`10`, `MP5`. A hand-maintained table drifts silently; a generated one cannot |
| **`RunRequest` shape** | One schema in `shared/schema`, generated into `shared/ts/bus-types.ts` and `shared/py/bus_types.py` by the existing generator, consumed by every initiation path. The ledger already carries `run_id` and `origin` columns (`FR-M40-02` amendment, `core/meridian_core/ledger/schema.py:181`). | `FR-M40-01`/`02`. The storage half of `M40` is built; the contract half is not |
| **Initiation tiering** | The `run/*` methods are **absent** from the registry below Governor — not registered and refused, not registered and hidden. The existing `tiers.json` mechanism carries them. | `X-28`, `H3`, `FR-M40-11`. A disabled-but-present tier is the failure mode `G5` exists to prevent |
| **Adapter digest pinning** | Content digest computed at install, stored with the installed adapter, re-verified at load; a mismatch **refuses the load naming both digests** and writes a ledger entry. Applies to registry installs and sideloaded packages alike. | `FR-M44-03`…`05`, `SEC-24`. Registry browse without pinning is a supply-chain regression, so this ships **first** |
| **ACP registry trust posture** | The index is fetched on explicit user action only, never on activation. Its contents are **untrusted input**: parsed by the existing allow-listed parser, mapped to a manifest, installed to probation with `read`/`search`/`think` only. No claim is made that a registry entry is safe. | `FR-M34-03`, `SEC-24`, the existing import posture |
| **Evidence-gate thresholds** | Written to `docs/evidence-gate.md` and recorded in `DECISIONS.md` **before** any study data exists, with a CI check that the file predates the results file. | `FR-M46-17`, `J8`. Thresholds written after the measurement are not thresholds |
| **Claims binding** | `docs/claims.md` — one row per externally visible claim, each naming a test. A CI check fails on a row whose named test does not exist. | `MP5`, `futures.md` honest-claims constraint |

---

## 4. Phase map

| Phase | Kind | Name | Closes | Band | Exit |
|---|---|---|---|---|---|
| **MV0** | Gate | **Quiesce and baseline** | — | 4–6 days | A quiesced tree, a recorded baseline, a complete claims inventory, a green traceability check |
| **MV1** | Build | **Truthful surfaces** | `MVP-R3.1`, `MVP-R3.5`, `MVP-R3.7`, `MVP-R5.1`, `MVP-R6.1`, `MVP-R6.2`, `MVP-R7.2`, `MVP-R7.4` | 3–4 wk | No surface renders a control without its enforcement point · a generated compatibility matrix · thresholds written before the study · drift and forgery visible, never silent |
| **MV2** | Build | **Run initiation** | `MVP-R4.1`…`R4.5` | 2–3 wk | One initiation contract · mandatory preflight · role-checked launch · clean cancellation · absent below Governor |
| **MV3** | Build | **Supply chain and reach** | `MVP-R2.3`, `MVP-R2.4`, `MVP-R2.5`, `MVP-R6.3`, `MVP-R7.1` | 4–5 wk | Adapters pinned by digest · sessions bound to a verified agent identity · the registry browsable to probation · a PR evidence card |
| **MV4** | Gate | **Release readiness** | `MVP-R1.6`, `MVP-R1.7`, `MVP-R6.4`, `MVP-R6.5`, `MVP-R7.3`, `MVP-R8.1`–`8.3` | 2 wk *(the 7-day soak starts on day one and runs inside the band)* | A tested support matrix · five failure rehearsals on four configurations · zero acknowledged-entry loss · a clean soak · the assistive journeys · a cold-start evaluation timed |
| **MV5** | Gate | **The evidence gate** | `MVP-R5.2`…`R5.4` | People, not weeks | A written go / stop / pivot / kill decision with the raw ledger slice attached |

**Engineering band: 12–16 weeks from `MV0`** — the lower figure with `MV2` and `MV3` in parallel, the upper with one engineer working serially. `MK6` fires at 16.

*Two rounds widened this after it was first set, both recorded rather than absorbed: the 12 September competitive review added `MVP-R7` (about a week, mostly `MV3-T06`), and the freeze audit added `MVP-R3.7` and `MVP-R8` under `D54` (about a week, in `MV1-T13` and `MV4-T09`). A band that quietly stays the same while tasks are added is not a band.*

**Hard serial:** `MV0 → MV1 → MV4 → MV5`. **`MV2` and `MV3` are parallelisable** once `MV1` closes, by one engineer each; if there is one engineer, `MV2` precedes `MV3`, because governed initiation is the thing a pilot cannot work around and registry browse is.

**Inside `MV3`, `MV3-T01` strictly precedes `MV3-T02`.** Shipping registry install before digest pinning would add a supply-chain path weaker than the one the product already has.

---

## MV0 — Quiesce and baseline

**Gate. 3–5 days. No build task begins until this phase exits.**

`N0` did this for the assurance track and it worked. The same discipline applies here, for the same reason: every number in the rest of this plan is unreliable until the tree is quiet.

### Tasks

**`MV0-T01` — Quiesce the tree.**
One commit. One sequential run of the Python, extension and webview suites under the shared `meridian-suite.lock`. Record the three counts, the commit SHA, the platform and the wall-clock. No concurrent session, no partial run, no "fast tier".
*Evidence:* the run log committed under `docs/baselines/`, named by SHA.
*Principle:* `MP3`, `J9`.

**`MV0-T02` — Land the requirement set.**
Commit `mvp-req-final.md`, this plan, and the two untracked source documents (`jit-requirements.md`, `jit-impl.md`). Record in `DECISIONS.md` that `mvp-req-final.md` is the **normative requirement set for `0.1.x`**, that every source document is **retained and not superseded**, and that the `M41` collision is resolved per §0.3.
*Evidence:* the decision record, dated, with the collision resolution written out.
*Principle:* `MP6`.

**`MV0-T03` — The claims inventory.**
Enumerate every externally visible sentence that asserts a capability: `README.md`, `DEMO.md`, `docs/SECURITY-AND-DATA.md`, `docs/DEPLOYMENT.md`, the extension manifest description, the webview's own copy. Write each to `docs/claims.md` as a row: *claim · where it appears · the test that backs it · disposition*. A claim with no test is either given one in this phase or **removed from the text in this phase**.
*Evidence:* `docs/claims.md`, plus `scripts/check-claims.mjs` failing on a row whose named test does not exist.
*Negative control (`MP2`):* delete a test name from one row; the check must fail. Restore it; the check must pass.
*Principle:* `MP5`. *Closes the general form of the defect behind* `MVP-R3.3`.

**`MV0-T04` — Bind the plan to the requirements.**
`scripts/check-mvp-traceability.mjs`: every identifier marked `MVP-GAP` in `mvp-req-final.md` §5 must appear in this document against a task id, and every task id here must name a requirement that exists. Drift in either direction fails the build.
*Evidence:* the check, green, and demonstrated red by removing a task reference.
*Principle:* `MP1`.

**`MV0-T05` — Dependency and licence sweep.**
Re-run the licence check over the runtime dependency set. Confirm the `docs/SECURITY-AND-DATA.md` §7 statement — no copyleft runtime dependency; Apache-2.0, MIT, BSD, ISC; fonts SIL OFL-1.1 — is still true of the current lockfiles. Triage anything newly added.
*Evidence:* the sweep output, and a `docs/claims.md` row binding §7 to it.
*Principle:* `MP5`, `ECO-03`.


**`MV0-T06` — Make the packaging guards check what ships, not what is on this machine.**
The freeze audit found `extension/extension/` twice: removed once, back at the next session because the 37 files were still tracked at `HEAD` (now removed for good at `3d25813`). **The guard could not tell the difference.** `manifest.test.ts` asserts `existsSync(extension/extension) === false`, which passes the moment the folder is deleted locally and says nothing about whether the path is still in version control — yet a path tracked at `HEAD` is in the next clone and therefore in the next VSIX, which is exactly what the guard exists to prevent.

Extend the guard so a path that must never ship is asserted absent from **both** the working tree and git's index, and generalise it: for every path the packager is relied on to exclude, assert it is untracked. A guard that verifies the developer's machine verifies the wrong machine.

*Files:* `extension/test/manifest.test.ts`, `scripts/package-extension.mjs`.
*Negative control (`MP2`):* re-add one file under the forbidden path to the index without touching the working tree; the guard must fail. It passes today only because `3d25813` removed the path from `HEAD` — **verify that it fails when the path is tracked, or it is the same guard with a longer name.**
*Principle:* `MP7`, pointed at version control rather than at the checkout. *Raised under `mvp-req-final.md` §19.1 as a defect discovered during the audit; it defends the package-integrity line in §18, so it is `MV0` rather than `POST-MVP`.*

### Exit criteria

- [x] One commit, one sequential suite run, three counts recorded — `docs/baselines/6b0b36a.txt`: extension 536, core 1,629, webview 242; recorded in `56bf95b`
- [x] `mvp-req-final.md` and this plan committed and recorded in `DECISIONS.md` — decision G-2 (the freeze) and `D54` (MVP scope)
- [x] `docs/claims.md` complete, with **zero** unbacked claims remaining in any shipped text — held since by `check-claims.mjs` on every `npm test`
- [x] `check-claims.mjs` and `check-mvp-traceability.mjs` both green and both demonstrated red — recorded in `6b0b36a`
- [x] Licence sweep clean — 12 runtime dependencies, none copyleft; a gate in `npm test`
- [x] Every must-never-ship path asserted absent from the working tree **and** from git; the guard demonstrated failing on a tracked-but-locally-deleted path (`MV0-T06`) — `extension/test/manifest.test.ts` and `scripts/package-extension.mjs` both read `git ls-files`; demonstrated in `6b0b36a`


### Delivery record

Written by the MV0–MV4 audit, which found every task delivered and none of them marked. Commits and evidence were checked, not recalled.

| Task | Evidence |
|---|---|
| `MV0-T01` Quiesce the tree | `6b0b36a`; baseline `docs/baselines/6b0b36a.txt`, recorded in `56bf95b` |
| `MV0-T02` Land the requirement set | `DECISIONS.md` G-2, the freeze; `D54` |
| `MV0-T03` The claims inventory | `docs/claims.md`, `scripts/check-claims.mjs` (`6b0b36a`) |
| `MV0-T04` Bind the plan to the requirements | `scripts/check-mvp-traceability.mjs` (`6b0b36a`) |
| `MV0-T05` Dependency and licence sweep | `scripts/check-licences.mjs` (`6b0b36a`) |
| `MV0-T06` Guards check what ships | `extension/test/manifest.test.ts`, `scripts/package-extension.mjs`, both reading `git ls-files` (`6b0b36a`) |

---

## MV1 — Truthful surfaces

**Build. 2–3 weeks. `MVP-R3.1`, `MVP-R3.5`, `MVP-R5.1`.**

This phase is first because it is the cheapest, and because the risk it closes is the only one that cannot be recovered from: a buyer who finds one overstated claim re-reads every other claim as marketing. `J1` says fix the number before you show the number; `MP5` extends it to every sentence.

**What exists already:** `enforcement_points.py` computes a `ControlDeclaration` over a closed, versioned vocabulary (`m42-1`), and `bundle.py` carries an enforcement section into every export. **What does not:** any RPC exposing it, any primitive rendering it, and any structural guarantee that a control surface cannot render without it. Two screens carry honest prose notices; prose does not compose.

### Workstream A — Enforcement points (`MVP-R3.1`, `FR-M42-11`/`12`, `SEC-32`)

**`MV1-T01` — Expose the declaration.**
Add `governance/enforcementPoints` to the registry: given a control id (or the whole set), return the declaration — the point, whether the binding is configured, and the vocabulary version. Register it in `methods.json` and `tiers.json`. The surface-coverage check will fail until a consumer exists, which is the intended pressure (`J6`).
*Files:* `core/meridian_core/server.py`, `shared/schema/methods.json`, `shared/schema/tiers.json`.

**`MV1-T02` — The primitive.**
One component — `EnforcementBadge` — carrying the declared point, its assurance, and an accessible name. Every control surface composes it. The invariant is **component-level, not review-level** (`H2`, `B12`): a control component constructed without a declaration throws in development and renders a visible defect marker in production, exactly as `ConfidenceBar` refuses to render without calibration.
*Files:* `webview/src/components/`, then each control surface.
*Negative control (`MP2`):* a test that constructs a control without a declaration and asserts the throw; and a test that removes the badge from one surface and asserts the suite goes red.

**`MV1-T03` — Never render client-side as enforced.**
A control whose enforcement point is the editor renders as **editor-enforced**, with the words that say what that means — not "enforced", not a green tick. The merge gate's SCM-side claim renders as *declared, not bound* until `D37` closes with a platform team.
*Evidence:* `AC-45` extended; a test asserting no control surface contains the bare string "enforced" without a qualifying point.
*Principle:* `J4`, `G3`.

**`MV1-T04` — Carry the declaration into the export.**
Confirm — with a test proven to discriminate — that the enforcement section in the export bundle and the declaration on the surface come from **one source**. Two copies of a claim is `J7`'s failure mode.

### Workstream B — Compatibility (`MVP-R3.5`, `FR-M44-08`…`10`)

**`MV1-T05` — The machine-readable matrix.**
`shared/schema/compatibility.json`: one row per claimed combination of operating system, Python version, VS Code version and remote configuration, each row naming the smoke test that backs it and the date it last passed. A row without a named, existing test **fails the build**.
*Negative control (`MP2`):* add an unbacked row; the check must fail.

**`MV1-T06` — Generate the published table.**
The table in `docs/DEPLOYMENT.md` and the `doctor` output are generated from `compatibility.json`. Neither is hand-maintained. A drift check fails if the committed table does not match the generator's output.
*Principle:* `MP5`.

**`MV1-T07` — Close `D41`.**
Decide whether the matrix is published publicly, under agreement, or internally, and record it. The default if undecided at `MV1` exit is **under agreement**, because a private-distribution MVP (`D19`) has no public surface to publish it on.

### Workstream C — The evidence gate's own thresholds (`MVP-R5.1`, `FR-M46-17`)

**`MV1-T08` — Write the thresholds before the study.**
`docs/evidence-gate.md`: the numeric criteria under which the Orchestra tier is built, not built, or built in part — written now, with no study data in existence. Include the three arms, the sample, and the commitment that unfavourable results are published (`FR-M46-15`).
*Evidence:* a CI check asserting `docs/evidence-gate.md` exists and that no results file exists that predates it.
*Principle:* `J8`, `MP8`. *This is a writing task and it takes an afternoon. It has been outstanding since `D35` because it was never scheduled.*

### Workstream D — Contracts we do not control (`MVP-R6.1`, `MVP-R6.2`)

**`MV1-T09` — Contract drift is visible, never silent (`NFR-40`, `FR-M44-06`/`07`).**
Every ledger entry derived from an external contract already records that contract's version. Add the other half: a CI check that detects a rename or breaking revision in the OpenTelemetry semantic conventions, the ACP protocol version, the MCP specification revision and each observer adapter version — and **degrades the coverage claim visibly within one session** rather than mis-mapping silently.
*Negative control (`MP2`):* rename a field in a fixture contract; the check must fail and the coverage claim must downgrade. Prove both before the code exists.
*Principle:* `J5`, `G3`.

**`MV1-T10` — A forged signal is never promoted (`SEC-34`).**
A fabricated `Co-Authored-By` trailer, a fabricated `Meridian-Ledger:` trailer and fabricated OTel telemetry SHALL each stay at `inferred` confidence. Meridian reads them; it never treats them as `direct` evidence. This is the narrow, high-value half of the adversarial corpus; the 100-fixture corpus (`FR-M46-09`/`10`) stays `POST-MVP`.
*Evidence:* three fixtures — one per forged channel — each asserting the recorded confidence is `inferred` and the reason is recorded.
*Principle:* `P26`, `G3`. *A product whose central claim is evidence must not be fooled by a text file anyone can write.*

### Workstream E — The claim, after the competitors (`MVP-R7.2`, `MVP-R7.4`)

**`MV1-T11` — Speak the buyer's standard (`MVP-R7.2`, `FR-M50-01`…`03`).**
The bundle already maps to SSDF, ISO/IEC 42001 and AI Act Article 12. Add the **`ISO/IEC 24970` AI-system-logging information model**, the **Article 26 retention margin** stated as a number against the six-month deployer obligation, and — in the same change — the sentence saying what each mapping **is not**: supporting evidence with a version and a scope, and explicitly not a presumption of conformity, because `24970` is not harmonised.
*Evidence:* `AC-61` — an auditor reads all three from the bundle alone.
*Negative control (`MP2`):* delete the not-a-conformity sentence; a test must fail. This is `P27` enforced on our own documentation.

**`MV1-T12` — Narrow the claim (`MVP-R7.4`).**
Cross-vendor line-level provenance is now a shipped product category (`CMP-01`). The broader wording is partly false and comes out of every shipped document. The surviving claim is the one in `mvp-req-final.md` §16.2, and each of its clauses binds to a named passing test in `docs/claims.md`.
*Evidence:* `AC-63` — no shipped document contains the withdrawn wording.
*Principle:* `MP5`. **A claim that was true in July and is not true in September is a defect with a date, not a matter of tone.**


**`MV1-T13` — Make the banned-pattern claim true (`MVP-R3.7`).**
§9.3 of the requirements claimed patterns 28–32 were enforced by component tests. Two are not: **28** (an agent-attributed element rendering without its vendor tag) and **30** (an Orchestra surface rendering below Orchestra) are referenced in source comments only. The sidecar half of 30 is genuinely enforced — a real-sidecar e2e proves governor and orchestra RPCs are refused at the base tier — but RPC absence is not surface absence.
Add the two missing tests: an `AgentToken`, weft row, ledger row or hunk constructed without a vendor tag must fail; and with Orchestra disabled, no Orchestra surface may be in the route table or the command registry.
*Negative control (`MP2`):* register an Orchestra surface at the base tier; the test must fail. Strip a vendor tag from one rendered element; the test must fail.
*Principle:* `H2`, `H3`, `MP5`. *The requirements document overstated its own enforcement — the same defect as a product overstating its controls, pointed inward.*

### Exit criteria

- [x] No control surface renders without a declared enforcement point — enforced by the primitive, not by review: `EnforcementBadge` refuses to render without one (`3dfa188`). `MV3-T04` later found two surfaces handing it a still-loading `null`, which would have crashed rather than hidden the control, and fixed both
- [x] No surface describes a client-side control as enforced — `411a1e7`. This is the surface half. `AC-45` as numbered in the requirement set — a merge blocked **outside** the editor — stays open under `D37` until a platform team configures an SCM binding
- [x] `compatibility.json` green, the published table generated, `D41` recorded — `de79279`
- [x] `docs/evidence-gate.md` written, dated, and predating all study data — committed 12 September 2026 in `56bf95b`; no study data exists yet
- [x] A renamed external contract degrades coverage visibly within one session (`NFR-40`) — `dbe6950`, `core/tests/test_contract_drift.py`
- [x] A forged trailer and forged telemetry each stay at `inferred` (`SEC-34`) — `63548b7`; `D55` then capped all trailer evidence at `inferred` (`4efc1ac`)
- [x] The bundle carries the `ISO/IEC 24970` mapping, the Article 26 retention margin, and the not-a-conformity sentence (`AC-61`) — `d7bf053`
- [x] The withdrawn broader claim appears in no shipped document (`AC-63`) — `d7bf053`; `check-claims.mjs` fails if the withdrawn wording returns
- [x] Banned patterns 28 and 30 each have a named test, each demonstrated failing (`MVP-R3.7`) — `6260101`
- [x] `docs/claims.md` updated: every claim this phase touched re-bound to its test
- [x] Three suites green, sequential — **one commit per task rather than one for the phase** (`3dfa188` … `70b432b`), each verified before it landed


### Delivery record

Written by the MV0–MV4 audit, which found every task delivered and none of them marked.

| Task | Evidence |
|---|---|
| `MV1-T01`/`T02` Expose the declaration; the primitive | `3dfa188` |
| `MV1-T03` Never render client-side as enforced | `411a1e7` |
| `MV1-T04` Carry the declaration into the export | `core/tests/test_enforcement_points.py::test_bundle_carries_the_enforcement_section` |
| `MV1-T05`/`T06`/`T07` The matrix, the table, `D41` | `de79279` |
| `MV1-T08` The thresholds before the study | `docs/evidence-gate.md`, committed in `56bf95b` before any study data |
| `MV1-T09` Contract drift | `dbe6950` |
| `MV1-T10` Forged signals | `63548b7`, then `D55` in `4efc1ac` |
| `MV1-T11`/`T12` The buyer's standard; the narrowed claim | `d7bf053` |
| `MV1-T13` Banned patterns 28 and 30 | `6260101` |

---

## MV2 — Run initiation

**Build. 2–3 weeks. `MVP-R4.1`…`R4.5`. Closes the invariant behind `M40`.**

`gaps_initiation.md` found that the product had forty-four screens and no start button. The workbench dispatch path had since been built, so the product could start work — but there was **no single initiation contract**, which meant there was no single place where preflight, authority and origin were guaranteed. `M40` was absent from the code; its **storage** half was not (`run_id` and `origin` columns have been on the ledger since schema v2, `core/meridian_core/ledger/schema.py:181`).

**Delivered.** `core/meridian_core/initiation.py` is the contract and `start_run` the entry point; `run/preflight`, `run/start` and `run/cancel` are the bus half, owned by the `governor.initiation` capability. Two doors are wired — the Launch screen (`origin: ui`) and the command palette (`origin: command`) — and they differ in `origin` and nothing else, which is asserted over the ledger rows rather than over the dataclass alone.

The MVP needs the invariant, not all eleven requirements. `FR-M40-04`, `06`, `07`, `08` and `10` remain `POST-MVP` and remain specified.

### Tasks

**`MV2-T01` — One request object (`MVP-R4.1`, `FR-M40-01`/`02`).**
Define `RunRequest` in `shared/schema`; generate the TypeScript and Python types with the existing generator. Every initiation path — command palette, workbench button, agent card, and any future path — constructs one. `origin` is a required field with a closed vocabulary, recorded on the ledger entry. **`AC-38`:** runs started from five different origins produce five ledger records differing **only** in `origin`.
*Negative control (`MP2`):* an AST guard, in the style of the existing spawn guard, that fails the build on any call into the run dispatcher that does not pass a `RunRequest`. Demonstrated red by adding a private route.
*Built:* `core/meridian_core/initiation.py`, `core/tests/test_initiation.py` (31), `test_initiation_guard.py`, `test_initiation_rpc.py` (21). The guard plants its probe in a tmp dir, not in the package — planting inside raced other guards under `-n auto` and made an unrelated test fail.

**`MV2-T02` — Mandatory preflight (`MVP-R4.2`, `FR-M40-03`).**
Before any work starts, the user sees and confirms: the parsed intent · the agents that will act · the repository and branch · the cost estimate and the ceiling · the gates that will apply · and whether this is a dry run or live. Preflight is **not skippable**; there is no "don't show this again".
*Files:* sidecar preflight assembly; one webview dialog (the minimum viable form of screen 10.51).
*Evidence:* a test that dispatches without confirmation and asserts refusal.
*Built:* `run/preflight` plus `webview/src/components/PreflightDialog.tsx` and `screens/LaunchScreen.tsx`. Preflight also refuses an adapter id the worktree machinery would later reject — without that check it reported `confirmable` for a run that could not start, and the human learned about the constraint after confirming.

**`MV2-T03` — Launch authority (`MVP-R4.3`, `FR-M40-05`, `SEC-30`).**
The launching identity is resolved (`FR-M20-01`), role-checked against policy, and recorded **with its assurance level**. A git-asserted identity never satisfies a policy requiring verification (`FR-M42-04`, already built — reuse it, do not re-implement).
*Evidence:* a test asserting an under-privileged identity is refused and the refusal is recorded.
*Built:* `governance.roles.launch_modes` — a `readOnly` role may dry-run, not go live. No `start-run` permission was added to `ACTIONS`: no deployed `roles.yaml` grants a permission that did not exist when it was written, so adding one would fail every launch closed. `POST-MVP`, with a policy migration.

**`MV2-T04` — Clean cancellation (`MVP-R4.4`, `FR-M40-09`).**
A run cancelled at preflight leaves **no worktree, no branch, and no ledger entry beyond the cancellation record**. Assert all three: the filesystem, `git branch --list`, and the ledger.
*Negative control (`MP2`):* create the worktree before the cancellation path is written; prove the test fails; then write the path.
*Built and demonstrated red.* The planted eager worktree also caught a non-discriminating assertion: the original cleanup test compared only top-level directory names, and `.meridian` already existed for the policy files, so it could not see the thing it was about.

**`MV2-T05` — Absent below Governor (`MVP-R4.5`, `FR-M40-11`).**
The `run/*` methods are not registered below the Governor tier, and the initiation affordance is not in the route table or the command registry. The test asserts **absence**, not denial — a method that exists and refuses is the scar `G5` forbids.
*Evidence:* `AC-36` extended to the run namespace, and **`AC-40`** — no command, no palette entry, no context-menu item, no affordance, with Flight Recorder otherwise unaffected.
*Built:* `extension/test/initiation-absent.test.ts`, which checks every menu in the manifest rather than only `commandPalette`. The command **id** stays registered below Governor: an unregistered id turns a keybinding into a raw "command not found" rather than the X-28 disclosure, which is a worse scar than the one being avoided.

**`MV2-T06` — The initiation surface.**
Screen 10.51 at its minimum: the preflight dialog, its four states (`B2`), three access paths on the destructive confirm (`B9`), and the enforcement badge from `MV1-T02` on every control it carries. The full screen stays specified and `POST-MVP`.
*Built.* `webview/src/screens/LaunchScreen.tsx` around `PreflightDialog`, and the palette door `meridian.startRun`; the enforcement badge rides on the dialog. **The Launch screen did not reach the package until `MV3-T05`**: it was registered in a screen registry that nothing renders, so it existed in the tests and nowhere a person could reach. It is now mounted on the workbench's `launch` view.

**`MV2-T07` — Demo path extended.**
`DEMO.md` gains the initiation step, re-verified end to end from an installed VSIX (`MP7`), not from the checkout.
*Written here; verified from the package in `MV3-T05`.* `DEMO.md` §6b. Every step is checked against the built VSIX by `scripts/check-demo-package.mjs` in CI. Walking it on a clean machine is `MV4-T04`.

### Exit criteria

- [x] One `RunRequest`; the AST guard green and demonstrated red
- [x] Preflight unskippable; every field present; refusal tested
- [x] Authority role-checked, identity and assurance recorded — with the `readOnly` qualification recorded on `MVP-R4.3`
- [x] Cancellation leaves no worktree, no branch, one entry — filesystem, `git branch --list` and ledger all asserted
- [x] `run/*` **absent** below Governor, proven by absence, with Flight Recorder proven whole alongside
- [~] `DEMO.md` re-verified from the package — every step is now backed by the built VSIX and checked in CI by `scripts/check-demo-package.mjs` (`MV3-T05`), which also found the Launch screen had never reached the package and led to its fix. **Walking the demo on a clean machine is not done**; that is `MV4-T04`
- [x] Three suites green, sequential, one commit

---

## MV3 — Supply chain and reach

**Build. 3–4 weeks. `MVP-R2.3`, `MVP-R2.4`, `MVP-R2.5`.**

`futures.md` finding G-02 was that differentiating instruments were computed and invisible; the surface-coverage check closed it for RPCs. `MP4` is the next turn of the same screw: `extension/src/adapters/registry-source.ts` is 505 lines of tested, exported, working ACP Registry client, constructed **only in its own test file**. It has a caller in the type sense and no user in any other sense.

**Order is not negotiable: pinning before browsing.**

### Tasks

**`MV3-T01` — Digest pinning (`MVP-R2.4`, `FR-M44-03`…`05`, `SEC-24`).**
Compute a content digest for every installed adapter at install time; store it beside the installation; verify at load. A mismatch **refuses the load, names both digests, and writes a ledger entry**. Applies to sideloaded packages and registry installs identically — one path, not two (`J7`).
*Files:* `extension/src/adapters/manifest.ts`, `extension/src/workbench/packages.ts`.
*Negative control (`MP2`):* mutate an installed adapter by one byte; the load must refuse and the refusal must name both digests (**`SEC-33`**). Prove the test fails before the check exists.
*Built and demonstrated red.* `extension/src/adapters/pinning.ts`. Two decisions worth stating: the pin index lives beside the adapter root rather than inside the folder, because a pin file within the folder it protects can be deleted by whoever edited the folder and the tamper would then read as a legitimately unpinned adapter; and `learned/` is excluded, because pinning an adapter's own state would make it drift the moment it learned anything, and a check that always fires is a check people turn off.

**`MV3-T01b` — Agent identity, not agent name (`MVP-R6.3`, `FR-M44-01`/`02`, `AC-52`).**
Digest-pinning an adapter package is not the same as knowing which binary ran. Bind every ACP and MCP session to a **verifiable agent identity** — executable digest, resolved version, and publisher where available — never to a self-asserted name. Attribution under an unverified identity is labelled unverified in the ledger and on every surface.
*Negative control (`MP2`):* replace an agent executable with a different build carrying the same declared name; the recorded identity must change and a warning must appear. Prove the test fails first.
*Built and demonstrated red.* `extension/src/adapters/identity.ts`; the identity is resolved and recorded **before** the process is spawned, so a swap is known before the agent has done anything. **The honest limit is most of the value:** `npx`, `uvx`, `pipx run` and `bunx` fetch the agent at launch, so the file on `PATH` is the fetcher. That comes back `unverified` naming the fetcher rather than reporting the shim's digest as the agent's, which would look exactly like a check and prove nothing.
*Why it ships with `T01`:* pinning the package while trusting the binary's own name is a half-closed door, and a half-closed door is the kind of control `P27` forbids claiming.

**`MV3-T02` — The registry, reachable (`MVP-R2.3`, `FR-M34-03`).**
Wire `AcpRegistrySource` to the Adapter Bay: browse, inspect an entry, install to probation. Constraints, all of them already the product's posture and none of them new:
- The index is fetched **on explicit user action only**, never on activation. Nothing in this feature changes the "no telemetry, no phone-home" statement in `docs/SECURITY-AND-DATA.md` §2, and a test asserts activation makes no network call.
- The index is **untrusted input**: the existing allow-listed parser handles it; nothing it contains is executed.
- An installed entry enters **Learning with `read`/`search`/`think` only**, exactly like an imported agent.
- Every install goes through `MV3-T01`'s pinning.
- Offline, unreachable and malformed-index states are three visible states, not one error (`B2`).
*Evidence:* the surface-coverage check consumes the method; an end-to-end test installs from a fixture index to probation.
*Built.* `registry/browse` and `registry/install` workbench actions; `webview/src/workbench/operations/RegistryBay.tsx` in the Adapter Bay. Two fixes the wiring forced: `list()` no longer fetches, so a surface cannot reach the network by asking what it already knows; and a malformed index is its own state rather than collapsing into `unreachable`, which had been sending an operator to check their network over somebody else's bad publish.

**`MV3-T03` — Say what the registry proves.**
Document, in `docs/SECURITY-AND-DATA.md` and on the surface, what a registry listing does and does not establish — in the same register as the `.sha256` paragraph, which says what it proves and then says what it does not. No claim that a listed agent is safe or endorsed.
*Principle:* `MP5`, `G4`.
*Built.* `docs/SECURITY-AND-DATA.md` §7 and the disclaimer on the Adapter Bay itself: a listing is a publication — not a review, not a security assessment, not an endorsement — and a pin proves the bytes did not change, not that they were ever trustworthy. Both are declared limitations in `docs/claims.md`.

**`MV3-T04` — The PR evidence card (`MVP-R2.5`, `FR-M46-03`).**
One card, on the Delivery Evidence surface, for a pull request under gate: **change risk · the revision actually tested · coverage gaps · failed checks · cost · and the human action required.** It consumes `pr/ingest` and `pr/status`, and closes the `pr/conflicts` declared-unsurfaced entry in `shared/schema/unsurfaced.json`. Every figure carries its coverage envelope (`J2`); the card carries its enforcement point (`MV1-T02`); the finding is stated in words (`H7`).
*Evidence:* built against a real gated PR, not a fixture (`H1`).
*Built.* `webview/src/screens/PullRequestCard.tsx`, a fourth tab on the Evidence surface; consumes `pr/status`, `pr/conflicts` and `spend/series`, and `pr/conflicts` leaves the unsurfaced allowlist.
**The tested revision is the field that bites.** A checks-passed badge means the checks passed on *some* revision; if the head has moved since, the badge describes code that is not the code being merged, and every interface that renders a green tick beside a stale commit is asserting something it never checked. The card reports the gap and tells the reader to re-run.
Two restraints: the card offers no approve control — approving is a governed action bound to an identity in the Gate Room, and a second route to it here would be a quieter one — and an unmeasured risk renders as `unknown` with a dashed border rather than sharing the visual language of a measured low, because a gap that reads as reassurance is worse than no card.
The work also found a latent crash from `MV2`: `LaunchScreen` passed `null` to `EnforcementBadge` while the declaration was still loading, and the badge refuses to render without one. A slow enforcement fetch with a fast preflight would have crashed the dialog. Both surfaces now render no badge until they can render a true one.
*Outstanding:* `H1` asks for a real gated pull request. The card is tested against the real RPC contracts; it has not been run against a live PR, which needs a repository and a pilot.

**`MV3-T06` — Read the rival's record, and notarise it (`MVP-R7.1`, `FR-M52-01`…`03`, `SEC-42`/`43`).**
Another provenance tool in the customer's repository is not a competitor to be displaced; it is **evidence to be made tamper-evident**. Read git notes written under other tools' refs, `Co-Authored-By` and agent-session-log trailers, and any vendor blame API the organisation has licensed. Then do the thing none of them does: **put the digest of that record into the signed ledger**, so a third party can prove the rival's note has not been altered since Meridian saw it.
- The record is **untrusted input** — parsed under the existing allow-list, never executed (`SEC-42`).
- It is labelled with **that tool as the source**, never as Meridian's own observation, and never promoted above `inferred` unless Meridian independently observed the same act (`FR-M52-02`).
- **Notarising is not endorsing** (`SEC-43`): the digest is signed, the content is not vouched for, and the surface says which.

*Budget:* `NFR-47` — digesting a third-party record adds no measurable delay to a commit; the hook stays short-lived, as the existing provenance hook already is.
*Evidence:* `AC-59` — a repository carrying another tool's notes opens, the notes appear attributed to that tool at `inferred`, their digest is in the ledger, and the bundle verifies.
*Negative control (`MP2`):* alter a notarised third-party record after the fact; verification must show the digest no longer matches. Prove the test fails before the code exists.
*Principle:* `P31`, `MP9`. *This is `P20` — beneath, not against — pointed at competitors instead of at agents, and it is the cheapest genuinely differentiating thing in this plan.*
*Built and demonstrated red.* `core/meridian_core/interop.py`; `interop/records`, `interop/notarise` and `interop/verify` at **Flight Recorder** tier, because this is observation and observation is the honesty floor — a customer running Meridian purely as a recorder gets it. Surfaced in the Ledger screen (10.7).
Three decisions the work forced, each because a test caught the alternative:
- **The digest is over the note blob's exact bytes** (`git cat-file blob`), not over `git notes show` output. `show` is a presentation command and appends a newline of its own; digesting it would have meant a git upgrade that changed that formatting made every notarised record read as altered.
- **The parsed payload is not in the ledger entry.** The first version included it, and `test_the_content_is_not_copied_into_the_ledger` caught it: a map of scalars pulled out of the note is the note, rearranged, and `P31` says notarise rather than duplicate. The payload stays on the read path, where a person is looking at their own repository.
- **A notarisation entry whose blob cannot be read is counted and reported, not skipped.** Skipping would let `interop/verify` report all-clear over records it never looked at.
`inferred` is a property rather than a field on `ForeignRecord`, so no caller anywhere can construct one claiming direct observation.

**`MV3-T05` — Demo path completed.**
`DEMO.md` covers install → bind (preset **or** registry) → initiate → gate → PR card → export → independent verification, re-run from the installed package on a machine that has not built it.
*Built.* `DEMO.md` §4b, §8b and §8c, and `scripts/check-demo-package.mjs`, which checks every step against the built VSIX in CI. It found two things every unit suite called green and that were **absent from the package**: the Launch screen, registered in a registry nothing renders, and pin verification, tree-shaken out because its only caller was never wired. Both fixed. *Outstanding:* the demo has not been walked on a clean machine. (This note was written in the `MV3-T05` commit and did not survive it; restored by the MV0–MV4 audit.)

### Exit criteria

- [x] Adapter drift refused, both digests named, entry recorded, negative control proven (`SEC-33`) — the refusal runs before launch. **The ledger entry was missing until the MV0–MV4 audit found it**; it is now written, carries the digests and never the contents, and the refusal stands if it cannot be written
- [x] A binary swap under an unchanged name changes the recorded identity and warns (`AC-52`)
- [x] The registry reachable by a person, installing to probation, with no activation-time network call — asserted on both sides of the bus
- [x] `pr/conflicts` consumed; the declared-unsurfaced entry removed
- [~] The PR card built against a real gated PR, carrying coverage and enforcement point — built and tested against the real RPC contracts; **not yet run against a live gated pull request** (`H1`), which needs a repository and a pilot
- [x] A third-party provenance record is read, labelled by source, notarised, and its alteration detected (`AC-59`)
- [~] `DEMO.md` end-to-end from the package — every step backed by the built VSIX and checked in CI; **not walked on a clean machine**
- [x] Three suites green, sequential — one commit per task group (`c693a6c`, `73c31b1`, `0e8ed94`, `3b5fb5f`), each verified before it landed

---

## MV4 — Release readiness

**Gate. 2 weeks. `MVP-R1.6`, `MVP-R1.7`.**

Everything here is verified **against the installed VSIX** (`MP7`). A rehearsal run in the development checkout proves the checkout works.

### Tasks

**`MV4-T01` — The tested support matrix (`MVP-R1.6`, `FR-M46-06`).**
Run the smoke tests named in `compatibility.json` on every claimed row. A row that fails is **removed from the matrix**, not marked degraded (`MK5`). Publish with the release.
*Built.* `scripts/run-compatibility-smoke.mjs` runs each claimed row's named smoke test and counts a row verified **only on the platform and interpreter it claims** — running the macOS row's test on Windows proves nothing about macOS, and is reported `not-verified-here` rather than ticked. It runs and records a baseline in every CI matrix leg. Locally on Windows: `windows-11`, `vscode-1.95` and `python-3.11` verified; `linux-lts`, `macos` and `python-3.12` await their CI legs. No row failed, so `MK5` removed nothing.

**`MV4-T02` — The resilience rehearsal (`MVP-R1.7`, `FR-M46-07`).**
Five failures × four configurations — Windows, macOS, Linux, and one remote (SSH or WSL):
1. Upgrade interrupted mid-write
2. Disk exhaustion during append
3. Sidecar killed mid-transaction
4. Corrupted bundle presented to the verifier
5. Restore from an export after a workspace deletion

**The pass condition is `NFR-42`: zero loss of acknowledged ledger entries, and recovery within 15 minutes for the reference dataset.** An entry the product acknowledged and then lost is not a bug to triage; it is the product's central promise failing, and it blocks the release (`MK4`).
*Evidence:* one recorded run per failure per configuration, committed under `docs/baselines/resilience/`.
*Built and demonstrated red.* `core/tests/test_resilience.py` rehearses failures 1, 2, 4 and 5 against the real ledger and the shipped `verify.py`; failure 3 is the existing real-sidecar kill test, referenced rather than duplicated, guarded by a test that fails if it is renamed away. Disk exhaustion is a genuine SQLite disk-full through `PRAGMA max_page_count`, not a mock — the first version tried to monkeypatch `Connection.execute`, which is read-only. The controls proved the suite detects real loss (rows deleted between acknowledgement and check) and a verifier that always passes. `scripts/record-resilience.mjs` records one run per failure per configuration: **Windows 5/5, zero acknowledged entries lost**, in `docs/baselines/resilience/`. macOS and Linux run in their CI legs; the remote configuration has no runner and needs a person.

**`MV4-T03` — Package and validate.**
Build the VSIX. Verify from the **installed** extension: `cli doctor` exits non-zero on an induced failure · the staged verifier verifies a bundle · the staged documents are present · the checksum matches · there is no nested `extension/extension/` directory **and nothing is tracked under it** · the library seeds a fresh workspace on first open.
*Built.* `scripts/validate-package.mjs` extracts the VSIX's sidecar and runs **that copy**: ten checks, all passing on Windows, recorded in `docs/baselines/package/` and wired into the CI package job.
It found a real gap on the way. **The headless `cli doctor` could not report a broken ledger at all**: its ledger probe was never wired outside the editor, so a provisioning check against an altered chain exited `0` — while `docs/DEPLOYMENT.md` listed ledger integrity among the things it checked. Given the signing key, doctor now verifies the chain and fails the run (`core/tests/test_headless_cli.py`, demonstrated red); without a key it still says it could not look, and the deployment guide now says when it checks. Seeding the library into a workspace is an editor action: the package check proves the shipped library is byte-identical to its source, and `MV4-T04` is where a person watches it seed.

**`MV4-T04` — The cold-start rehearsal.**
One person who has not read the source and has not seen this plan goes from the VSIX file to a verified evidence bundle, using only `DEMO.md`, `docs/DEPLOYMENT.md` and `docs/SECURITY-AND-DATA.md`. **Timed.** Every question they have to ask is a defect in the documents, recorded and fixed before release.
*Feeds:* `MK1`, and `NFR-28`'s fifteen-minute first-provenance-answer target.
*Prepared, not run.* `docs/baselines/cold-start/PROTOCOL.md` fixes who qualifies, the only four documents they get, what the observer may say, the milestones to time against `NFR-28`, and the defect table every question becomes. It needs a person from outside the project, and nobody on the project can stand in for one.

**`MV4-T06` — The soak (`MVP-R6.4`, `NFR-43`, `FR-M46-08`).**
Seven days of continuous operation under explicit resource limits, with no unbounded growth in memory, disk or handle count. **This is elapsed time, not effort** — start it on the first day of `MV4` so it finishes with the phase, and record the resource curves as the evidence.
*Principle:* `MP7` — run it against the installed package, not the checkout.
*Harness built; the soak has not been run.* `scripts/soak.mjs` extracts the sidecar from the built VSIX, drives appends, queries and chain verification over stdio, samples memory, handles and disk-per-entry from outside the process, and writes the curve as it goes, so a run killed on day four leaves four days of evidence. A short smoke run on Windows is recorded as `incomplete` and says it is not the soak.
That smoke run found a harness defect first: it projected a warm-up memory slope across 168 hours and "failed" a three-minute run. A check that fires on every short run is one people learn to ignore, so projections now wait for 24 hours of data while hard limits apply from the first sample. **A hosted CI runner cannot hold a seven-day job**; this needs a dedicated machine started on the first day it is available.

**`MV4-T07` — The assistive journeys (`MVP-R6.5`, `FR-M46-05`).**
Keyboard-only and screen-reader journeys complete **launch, review and export** without a critical barrier. Three journeys, both input modes, recorded. Full WCAG 2.1 AA certification remains `POST-MVP` (`GF4+`); these three journeys are the ones an evaluator actually performs, and a product that cannot be operated without a mouse is not adoptable.
*Evidence:* a recorded pass per journey per mode, plus the measured false-alert rate and dismissal reasons.
*Principle:* `B3` — accessibility is built in, never retrofitted.
*Structural half built; the recorded journeys are not.* `webview/src/screens/assistive-journeys.test.tsx` covers launch, review and export — real controls, accessible names, the preflight as a dialog, cancel before confirm, refusals and alterations announced — demonstrated red against an unnamed button and a focusable `div`. jsdom has no accessibility tree, so these are preconditions and not results. `docs/baselines/assistive/PROTOCOL.md` defines the six recorded runs, what counts as a critical barrier, and the false-alert and dismissal measurements the evidence line asks for. The runs need a person with a screen reader.

**`MV4-T08` — The bill of materials (`MVP-R7.3`, `FR-M50-04`, `NFR-48`, `SEC-44`).**
The package ships 22 agents, a 10-pack skill catalogue, 4 instruction documents and 4 ACP runtime presets, and publishes **no bill of materials for any of it**. Generate a **CycloneDX AI-BOM** from the build — never hand-maintained — listing every shipped component with its version and digest, and publish it beside the VSIX and its checksum.
- Drift between the AI-BOM and the package **fails the build** (`NFR-48`).
- The AI-BOM discloses only what the package ships: no workspace content, no credentials, no customer identifiers (`SEC-44`).

*Evidence:* `AC-62` — every shipped component appears with a matching digest; a deliberate mismatch fails.
*Why it is in the MVP:* an enterprise that cannot enumerate what an extension installed cannot approve it, and the fix is a build step.
*Built.* `scripts/generate-bom.mjs` generates CycloneDX 1.6 **from the built VSIX, never the checkout**, and publishes `meridian-loom-<version>.cdx.json` beside it: 52 components, each with its digest. `--check` fails on drift, demonstrated against a tampered digest, ten removed skills and an invented agent; it runs in the CI package job, and the release artefact uploads the VSIX, checksum and BOM together. Agents are typed `data`, not `machine-learning-model`, because no model ships and the BOM should not send a reviewer looking for a model card. The zip reader is shared with the demo check in `scripts/lib/vsix.mjs`, so there is one of it.


**`MV4-T09` — What an organisation needs to operate it and leave (`MVP-R8.1`…`8.3`).**
Three artefacts the MVP definition implies and the repository does not have:
- **`SECURITY.md`** (`MVP-R8.1`, `SEC-49`) — vulnerability disclosure: scope, contact, and the response a reporter can expect. **Promise what one maintainer can meet.** A 24-hour commitment nobody can honour is an unbacked claim with a deadline attached (`AC-69`).
- **Third-party notices** (`MVP-R8.2`), generated from the lockfiles in the same build step as the AI-BOM (`MV4-T08`) — same machinery, different manifest. This makes `docs/SECURITY-AND-DATA.md` §7's no-copyleft statement checkable rather than asserted (`AC-70`, `NFR-48` drift rule applies).
- **Support and upgrade policy** (`MVP-R8.3`) — supported versions, breaking-change notice period, state-migration guarantee across upgrade, and the export path on exit (`AC-71`, `NFR-55`). The exit path already exists and is tested; this is the sentence that tells a buyer it does.

*Why in `MV4`:* these are release artefacts, and two of the three are generated by the release build.
*Principle:* `MP5` — each of the three is a claim, so each binds to a test or a generator, never to good intentions.
*Built.* `SECURITY.md` promises what one part-time maintainer can meet — acknowledgement within 10 working days, assessment within 20, updates at least every 30 — and no bounty. `THIRD-PARTY-NOTICES.md` is generated from the licence sweep before the VSIX is staged, and held by a drift gate in `npm test` that reports **skipped** rather than passing where a licence cannot be resolved. `docs/SUPPORT.md` states one supported line, breaking-change notice, one-way migrations and the exit path, and says plainly that no paid support exists. All three ship inside the package and are checked there.

**`MV4-T05` — Release notes and decision record.**
Release notes that agree with `DECISIONS.md`, name the tier set, state the limitations from `docs/SECURITY-AND-DATA.md` §6 without softening them, and say plainly what the MVP does **not** claim (`mvp-req-final.md` §13).
*Built.* `extension/CHANGELOG.md` `[Unreleased]` covers `MV2`–`MV4`, names the tier set and states each `§6` limitation. `scripts/check-release-notes.mjs` holds it there as a gate in `npm test`: every limitation headline must appear in its own words — paraphrase is how softening happens without anyone deciding to soften — all four outcomes `§13` disclaims must be named, and every `D<n>` cited must exist in `DECISIONS.md`. Its first run found eleven disagreements in the notes as they stood.

### Exit criteria

- [~] Every published compatibility row backed by a passing smoke test — the runner verifies a row only where it claims to run; **3 of 6 claimed rows verified (Windows)**, the other three close in their CI legs. None failed
- [~] Twenty rehearsals run; **zero** acknowledged entries lost, recovery inside 15 minutes (`NFR-42`) — **5 of 20 (Windows), zero lost**. macOS and Linux in CI; the remote configuration needs a person
- [ ] Seven-day soak complete with no unbounded resource growth (`NFR-43`) — harness built against the package; **not run**, and it cannot run on a hosted CI runner
- [~] Launch, review and export complete keyboard-only and under a screen reader (`FR-M46-05`) — structural preconditions tested and proven red; **the six recorded human runs are not done** (protocol ready)
- [x] The installed package validated, not the checkout — ten checks run from the extracted package, including an induced doctor failure
- [ ] A stranger reached a verified bundle unaided; the time is recorded — **not run**; protocol ready, needs a person from outside the project
- [x] The CycloneDX AI-BOM matches the package exactly; a deliberate mismatch fails the build (`AC-62`)
- [x] `SECURITY.md`, third-party notices and the support/upgrade policy ship with the package (`AC-69`…`AC-71`)
- [x] Release notes agree with the decision record — held by a gate, not by a reading
- [x] `docs/claims.md` green: every shipped claim bound to a passing test, and every human step not yet done declared as a limitation

---

## MV5 — The evidence gate (`MVP-HUMAN`)

**Gate. Measured in people, not weeks. `MVP-R5.2`, `R5.3`, `R5.4`.**

This is `F2` from `gaps_implementation.md`, `GF2` from `gaps_guix_implementation.md`, and `N3` from `futures-implementation.md`. They are the same gate and it has never run.

**`MP8` governs this phase absolutely.** Nothing here is engineering work, nothing here is reported as engineering progress, and no engineering phase may be declared exited on a figure this gate has not produced.

| Item | Requirement | Needs |
|---|---|---|
| Preregistered three-armed study, unfavourable results published | `FR-M46-14`/`15`, `MVP-R5.2` | Twenty real stories, a real team, and the thresholds from `MV1-T08` already written |
| Four of five users reach a first provenance answer within fifteen minutes | `FR-M46-04`, `NFR-28`, `MVP-R5.3` | Five users who have not seen the product |
| Two editors, two SCM providers, one evidence shape | `AC-50`, `FR-M43-15`, `MVP-R5.4` | A pilot customer, and first a second editor claimed in the compatibility matrix |

**Exit:** a written **go / stop / pivot / kill** decision, with the raw ledger slice attached, measured against `docs/evidence-gate.md` — which was written before the data existed. That decision closes `D21` and decides whether `F3`/`GF3`/`C2`–`C6` — the Orchestra — is ever built.

`R29` stands: *the Orchestra never earning its place is a designed, acceptable outcome.* The product is complete as a flight recorder and a governor, and this plan delivers it as one.

### Prepared, so the people can run it without an engineer

`MP8` still governs. None of this is progress through the gate, and none of it moves `MVP-R5.2`…`R5.4` off `MVP-HUMAN`. It is what the people need in hand when they exist.

**The instrument now applies the rule written in advance.** Preparing the gate found that `core/meridian_core/metrics/evidence_gate.py`, the instrument the study would be scored with, did not apply `docs/evidence-gate.md`. It predated the thresholds and applied the older F2 sketch:

- It returned GO on a single unconfirmed gate block, where `P1` needs three independently confirmed defects.
- It returned GO with change failure rate and provenance-query usage unmeasured, where §5 says an unmeasured threshold is never satisfied.
- It had no KILL path, and no `P5`, `P6`, `C1`, `C2` or `O1`.
- Against the rows the Governor actually writes, it counted nothing. It looked for gate decisions of `block`, where the ledger records `rejected`, and for an approval's subject on the row, where it lives in the encrypted detail. Its tests passed because their fixtures used the shapes it expected.

It is rebuilt:

- Ten measures, each `met`, `not_met` or `unmeasured`.
- §4 walked in order over three-valued logic, so an outcome that depends on an unmeasured threshold is never reached.
- Every reading that the words allow more than one way is written into `docs/evidence-gate.md` §6, each chosen to make GO harder.
- A digest of the thresholds and readings that a study registers before its first story, so a change after data is declared.

The tests drive a real sidecar. Twenty-four behaviours were shown red: twelve in the gate, five on its screen, and seven across the CLI, the bundle-shape comparison and the server.

**Two gaps in §4, surfaced for the owner.** No outcome applies when `P1` and `P2` both fail and everything else holds; the instrument reports `unclassified` rather than choosing. And PIVOT is tried before KILL, so a study that fails retention while nobody queries provenance returns PIVOT. Both are amendable until the first story (§5), and both are written in `docs/evidence-gate.md` §6.

**What only people can supply now has a shape.** `core/meridian_core/metrics/evidence_study.py` defines the study record: allocation, adjudications, arm A's figures, retention, `O1` and every `FR-M46-14` field. It refuses an email address wherever a person is named. `python -m meridian_core.cli evidence-gate` scores the record and writes three files: the report, the raw ledger slice as a signed bundle, and `DECISION-DRAFT.md`. The draft holds the computed half of the written decision with both files' digests, and leaves the half a person writes empty. Both new commands are checked from the extracted package, not the checkout: `scripts/validate-package.mjs` scores a study and compares two bundles with the shipped sidecar.

**The protocols:**

- `docs/baselines/evidence-gate/PROTOCOL.md` — register, allocate three arms, record, score, and publish, unfavourable results included.
- `docs/baselines/first-value/PROTOCOL.md` — `FR-M46-04`: five onboarding sessions, and ten review tasks with an answer key committed before the first session.
- `docs/baselines/two-editors/PROTOCOL.md` — `AC-50`, with `python -m meridian_core.cli compare-evidence` checking that two bundles verify and carry one evidence shape.

**`AC-50` cannot be attempted yet, and not only for want of a customer.** It needs two *supported* editors, and the compatibility matrix claims one. A second editor has to be claimed with a passing smoke test first (`MK5`). Until then the protocol can be rehearsed but not passed, and no external material may claim vendor independence across editors (`FR-M43-15`).

### Exit criteria

- [ ] The preregistered three-armed study run on twenty stories and scored (`MVP-R5.2`) — **not run**. It needs a team, twenty stories, independent reviewers and eight weeks.
- [ ] A written go / stop / pivot / kill decision, with the raw ledger slice attached, published with its unfavourable results and missing data — **not written**. The scorer drafts its computed half, and a person writes the decision.
- [ ] Four of five users reach a first provenance answer within fifteen minutes, and eight of ten review tasks find the real blocking risk (`MVP-R5.3`) — **not run**. It needs five people who have not seen the product.
- [ ] Two editors, two SCM providers, one evidence shape, verified on a clean machine (`MVP-R5.4`) — **blocked twice**: a second editor is not claimed, and it needs a pilot customer.

---

## 5. Cross-cutting workstreams

Inherits every workstream from the five predecessor plans. Active for the MVP:

| Workstream | Cadence | Source |
|---|---|---|
| **Claims binding** | Every commit that touches shipped text | `MP5`, `MV0-T03` |
| **Surface coverage** | Every commit | `FR-M46-02`, `J6` |
| **MVP traceability** | Every commit | `MV0-T04`, `MP1` |
| **Negative controls on every new test** | Every test added | `MP2` — *the one this project has historically skipped* |
| **Sequential suite discipline** | Every phase exit | `J9`, `MP3` |
| **Security regression** | Every commit | `SEC-17`; includes the scrubbed-child-environment AST guard (`SEC-27`) and the no-model-call guards |
| **Package integrity** | Every phase exit | `MP7` — no nested duplicate, library staged, verifier staged, documents staged, checksum emitted |
| **Cross-platform** | Every phase exit, incl. Remote SSH | `NFR-22`, `FR-M3-11` |
| **Coverage envelope** | Every metric function | `J2`, `FR-M41-08` — `truncated` is derived, never supplied |
| **Degrade-not-silence** | Every observer change | `G3`, `NFR-32` |
| **Tier isolation** | Every phase exit | `G5`, `X-28` — disabled tiers **absent**, never disabled-but-present |
| **Competitor parity timing** | `MV3` exit, on the Adapter Bay | `H4`, `X-31`, `gaps_guix_implementation.md` §14 |
| **Accessibility** | Every screen | `B3`, `A-09`…`A-11`, WCAG AA |

---

## 6. Definition of done

Inherits `Requirements-implementation.md` §14, `viguix-implementation.md` §6, `gaps_implementation.md` §12, `futures-implementation.md` §11 and `jit-impl.md` §9. **Any MVP task additionally:**

- [ ] Its requirement id in `mvp-req-final.md` §5 moves from `MVP-GAP` to `BUILT`, in the same commit
- [ ] Every test it adds has been **demonstrated failing** against the unfixed tree (`MP2`) — the demonstration is recorded in the commit message, not asserted
- [ ] Every claim it makes true or false is reflected in `docs/claims.md` in the same commit (`MP5`)
- [ ] Every figure it renders carries its coverage envelope; every control it renders carries its enforcement point
- [ ] Nothing it adds is reachable only from a test (`MP4`)
- [ ] It is verified against the **installed package**, not the checkout, wherever the behaviour is packaging-sensitive (`MP7`)
- [ ] It removes nothing that was built (`MP6`)
- [ ] A tier it touches stays **absent** below its floor, not disabled (`G5`)
- [ ] No `MERIDIAN_*` variable reaches any process it spawns (`SEC-27`)
- [ ] No model client is importable from any path it touches in the Flight Recorder tier (`FR-M36-07`)
- [ ] Three suites green, sequential, one tree, one commit (`MP3`)

---

## 7. Sequencing and interlock

```
0.1.0 baseline  (1,629 + 534 + 242 green · VSIX 232 files · surface coverage green)
 │
 └─→ MV0 Quiesce and baseline            [3–5 d]   gate
      │   claims inventory · traceability check · licence sweep
      │
      └─→ MV1 Truthful surfaces          [2–3 wk]
           │   enforcement points · compatibility matrix · evidence-gate thresholds
           │
           ├─→ MV2 Run initiation        [2–3 wk]   ─┐
           │     RunRequest · preflight · authority   │  parallelisable
           │     cancellation · absence below Governor│  with two engineers;
           │                                          │  MV2 first with one
           └─→ MV3 Supply chain and reach [3–4 wk]  ─┘
                 T01 pinning ──strictly before──→ T02 registry browse · T04 PR card
                 │
                 └─→ MV4 Release readiness [2 wk]   gate
                      │   support matrix · 20 rehearsals · cold start · package
                      │
                      └─→ MV5 Evidence gate          people, not weeks
                           go / stop / pivot / kill → closes D21
```

### Interlock with the predecessor tracks

| Track | Its phase | Relationship to this plan |
|---|---|---|
| **F-plan** (`gaps_implementation.md`) — the delivery spine | `F0`, `F1` delivered · `F2` pending | **`MV5` is `F2`.** `MV1`–`MV4` are what make `F1`'s exit claim defensible to a buyer rather than to ourselves |
| **N-plan** (`futures-implementation.md`) — the assurance track | `N0`–`N2` delivered · `N3` pending | **`MV5` is `N3`.** `MV1` finishes `N2`'s last two items — enforcement-point declaration on surfaces, and the compatibility matrix |
| **GF-plan** (`gaps_guix_implementation.md`) — the interface | `GF0`, `GF1` delivered · `GF2` pending | **`MV5` is `GF2`.** `MV2-T06` and `MV3-T02`/`T04` are `GF1` completions, not new scope |
| **G-plan** (`viguix-implementation.md`) | `G0`–`G8` | Superseded as a route by `GF*`; the 44 screens and their dispositions stand (`mvp-req-final.md` §9.1) |
| **C-plan** (`Requirements-implementation.md`) | `S0` delivered · `C1`–`C6` | `S0` substrate is in the tree. `C1`–`C6` are the Orchestra; `MV5` decides whether they are ever built |
| **J-plan** (`jit-impl.md`) | `J-1`…`J-4` | `POST-MVP` in full. `J-1` is the first candidate after the MVP: harness provenance pays with zero synthesis |

**The interlock rule, restated for this plan:** *the MVP may not ship a sentence that `MV5` has not yet earned, and `MV5` may not be scheduled as though it were engineering work.*

---

## 8. The retained phase register

**Nothing here is deleted.** This table exists so that a reader of any predecessor plan can find their phase and see what became of it.

| Phase | Plan | Delivers | Status |
|---|---|---|---|
| `F−1` | `gaps_implementation.md` | Legal clearance gate, `D22` | **Closed** by owner determination (`DECISIONS.md`) |
| `S0` | `Requirements-implementation.md` | Simulation Core, contracts, ledger substrate, worktrees, replay | **Delivered in substance** — the substrate modules are in the tree and under test |
| `G0`–`G8` | `viguix-implementation.md` | The 44-screen GUI against the Simulation Core | **Superseded as a route** by `GF0`–`GF4+`; screen set and dispositions retained |
| `F0` / `GF0` | gaps plans | Flight Recorder · 6 screens | **Delivered** (`f0-complete`) |
| `F1` / `GF1` | gaps plans | Governor · ACP host · gates · roles · trust analytics | **Delivered** (`f1-complete`); its last two interface items land in `MV1`/`MV3` |
| `N0` | `futures-implementation.md` | Quiesce | **Delivered**; its discipline is re-run as `MV0` |
| `N1` | `futures-implementation.md` | True and visible — coverage envelopes, three-state attribution, instruments surfaced | **Delivered** (surface coverage green, 63/71 consumed) |
| `N2` | `futures-implementation.md` | Unassailable — trailer spec, headless collector, witness seam, identity assurance | **Delivered except** enforcement-point surfacing (`MV1-A`) and the compatibility matrix (`MV1-B`) |
| **`MV0`–`MV4`** | **this plan** | **The adoptable package** | **The current route** |
| `F2` / `GF2` / `N3` / **`MV5`** | all | The evidence gate | **Pending human evidence.** `D35`, `D21`. The scorer, the study record and the protocols are prepared (`MV5`, *Prepared*); the study has not run |
| `F3` / `GF3` / `C1`–`C2` | gaps + C plans | Orchestra — loop runtime, roster, adapters, deterministic engine | **Begun** (`M33` slices 1 and 2a per `futures-implementation.md` §13); gated on `MV5` |
| `C3`–`C6` | `Requirements-implementation.md` | Quality gates · learning and portability · orchestration and compliance · differentiation | `POST-MVP`, retained |
| `F4+` / `GF4+` / `N4` | gaps + futures plans | Learning, scale, compliance, widening | `POST-MVP`, retained |
| `J-1`, `J-2` | `jit-impl.md` | Harness as artifact · archive and retrieval — **unconditional, no bet** | `POST-MVP`. **First candidate after the MVP** |
| `J-3`, `J-4` | `jit-impl.md` | Gated synthesis · evolution and promotion — **the bet** | `POST-MVP`, gated on `D44` at `J-2` exit |

---

## 9. Kill and stop criteria

**Inherits in full:** `K1`–`K7` (`gaps_implementation.md` §15), `NK1`–`NK7` (`futures-implementation.md` §15), `GK1`–`GK6` (`gaps_guix_implementation.md` §15), `JK1`–`JK6` (`jit-impl.md` §12). Every one still applies at the phase it names.

These are added, and they are the conditions under which **this plan's** work should stop.

| # | Condition | Measured at | Response |
|---|---|---|---|
| **MK1** | In `MV4-T04`, a stranger cannot get from the VSIX to a verified bundle unaided in 30 minutes | `MV4` | The package is not adoptable, whatever its test counts say. Stop feature work; fix the path. This is the MVP's whole thesis |
| **MK2** | `MVP-R4` cannot be built without leaving a scar below Governor — a registered-and-refused method, a disabled affordance | `MV2` | **Ship the Governor without initiation.** A scarred tier breaks `G5`, which is load-bearing for the tiering claim. Initiation is worth less than the claim |
| **MK3** | Digest pinning proves impossible for a class of registry entry | `MV3-T01` | Do not ship registry browse for that class. Never ship `MV3-T02` without `MV3-T01`; an unpinned install path is weaker than what the product already has |
| **MK4** | Any rehearsal loses an acknowledged ledger entry | `MV4-T02` | **Release blocked.** Durability is not a quality attribute of this product; it is the product |
| **MK5** | A claimed compatibility row cannot be backed by a passing smoke test | `MV1-T05`, `MV4-T01` | Remove the row. Never mark it degraded, supported-with-caveats, or best-effort. Withdraw the claim |
| **MK6** | The engineering band exceeds 16 weeks from `MV0` | continuous | Cut per §10. Never cut the ledger's integrity, the verifier, the coverage envelope, the enforcement declaration, or the honesty set |
| **MK7** | An MVP task is reported complete on a concurrent or partial suite run | any | The report is void. Re-run sequentially before anything is believed (`MP3`) |

| **MK8** | A competitor ships cross-vendor provenance that is **both** independently verifiable **and** bound to a merge decision | any release, via `NFR-54` | **`K6` / `NK6` fire.** Reassess honestly and in writing. The position was structural; if it closes, say so rather than re-describing it. `mvp-req-final.md` §16.2 records how close it currently is and what the two remaining clauses are |

**`MK2` and `MK5` are not failures.** Each of them is the product telling the truth about itself, which is the only durable thing it sells.

---

## 10. Slip plan

Cut in this order. Each cut leaves a coherent, honest, shippable product.

| Order | Cut | Cost |
|---|---|---|
| 1 | `MV3-T04` PR evidence card | The gate still works and still records; the reviewer assembles the picture from two surfaces instead of one |
| 2 | `MV3-T02` registry browse — **keeping `MV3-T01` pinning** | An evaluator binds from the four shipped runtime presets instead of browsing. The presets already cover the common case |
| 3 | `MV2-T06` initiation screen — keep the contract, preflight and authority behind the existing dispatch affordance | The invariant holds; the surface is plainer |
| 4 | `MV1-T07`/`D41` public matrix — publish under agreement only | Evaluation needs one more email. `D19` already means one more email |
| 5 | Remote configuration in `MV4-T02` — rehearse three desktop platforms | The remote claim is withdrawn from the matrix rather than being untested. `MK5` |
| 6 | `MV2` entirely — ship the Governor without governed initiation | The product observes, gates and proves; it does not start work. **This is a legitimate MVP** and it is what `F0`+`F1` already are |

**Never cut:** the ledger's chain integrity · the open verifier in the package · the published digest · the coverage envelope · three-state attribution · the enforcement-point declaration · tier **absence** below its floor · the scrubbed child environment · the zero-model-call guarantee in Flight Recorder · adapter digest pinning if any install path ships · the claims-to-test binding · thresholds written before the study.

Every item on that list is either the product's honesty or the reason a buyer can trust a number. Cutting any of them reintroduces a defect one of the five predecessor plans exists to close.

---

## 11. Risk retirement schedule

Inherits `R1`–`R25`, `R26`–`R30`, `R31`–`R36` and `R37`–`R40` in full. Those that bear on the MVP:

| Risk | Retired or controlled in | Control |
|---|---|---|
| `R21` Adapter supply chain | **`MV3-T01`** | Content digest pinned at install, verified at load, drift refused naming both digests |
| `R27` Observers go blind on vendor change | Controlled (`F0`) | Versioned observers, degrade-not-silence, git-trailer floor |
| `R29` Orchestra never earns its place | **`MV5`** | Designed as an acceptable outcome; the MVP is complete without it |
| `R30` Dependence on incumbent goodwill | Controlled (`F0`) | Observation only over ACP, OTel and git — surfaces no vendor can revoke without breaking their own users |
| `R32` SCM enforcement refused by platform teams | **`MV1-T03`** | The weaker boundary is declared honestly rather than hidden; `D37` stays open against a real platform team |
| `R33` No identity provider funded | Controlled | Assurance levels explicit; git identity never described as verified |
| `R36` Evidence gate returns unfavourable | **`MV5`** | Every MVP requirement supports a claim already made and holds regardless; `FR-M46-15` publishes the result either way |
| `R11` / `R18` Distribution and setup friction | **`MV4-T03`/`T04`** | Doctor, staged documents, published digest, and a timed cold start by a stranger |
| **New: the package is not what the checkout is** | **`MV4-T03`** | Every packaging-sensitive behaviour verified from the installed VSIX (`MP7`) |
| **New: a test that does not discriminate** | **every phase** | `MP2` negative controls, recorded in the commit message |

---

## 12. Decision schedule

| # | Decision | Must close by | State |
|---|---|---|---|
| ~~`D41`~~ | Compatibility-matrix publication | **Closed 13 Sept 2026 (`MV1-T07`)** | **Published with the release**, inside the VSIX via `docs/DEPLOYMENT.md` |
| ~~`D55`~~ | Git-trailer evidence caps at `inferred` — raised by `MV1-T10` | **Closed 13 Sept 2026**, owner determination | **Capped.** Applied to four observers; `telemetry` is now a reserved rung with no producer, recorded in `DECISIONS.md` |
| `D37` | SCM enforcement mechanism | **Pilot-dependent.** The refused-binding declaration (`MV1-T03`) is in force until a platform team exists | Open, not MVP-blocking |
| `D21` | Whether the Orchestra tier is built at all | **`MV5`** — this is what `MV5` decides | Open, by design |
| `D42` | Whether the deterministic-engine investment gate binds the build agent or advises the owner | Before any `M33` growth beyond the structural set | Open |
| `D19` | Licence | **Deliberately deferred** (owner determination, 10 Sept 2026). `private: true`, no `license` field, private VSIX distribution — all correct and unchanged | Closed as a deferral |
| `D22` | Employment and IP path | Closed by owner determination | Closed |
| `D35` | Evidence-gate preconditions | Superseded by `MV1-T08` writing the thresholds and `MV5` running the study | Closing |
| `D44`–`D47` | Harness adoption · generator · registry contents · trainable surface *(was `jit-impl.md` `D24`–`D27`)* | `J-2` exit · `J-3` start · `J-1` start · `J-4` | `POST-MVP`, retained |
| `D54` | **MVP scope at the freeze** — admit `MVP-R3.7` and `MVP-R8` | **Closed 12 Sept 2026**, owner determination | `mvp-req-final.md` §11.4 |
| `D52` | Whether the AI-BOM is published publicly or under agreement | **`MV4-T08`** | Open; default **with the release**, since it discloses only what the package ships |
| `D50` | Which third-party provenance formats to read first | **`MV3-T06`** | Open; recommend git notes plus `Co-Authored-By`, because both are already in the repository |
| `D48` | Whether to ship an MCP gateway at all, or stay the notary | **`CP3` start** — with a platform team in the room | Open, `POST-MVP` |
| `D49` | SPIFFE dependency — consume if present, or bundle | `CP2` | Open, `POST-MVP` |
| `D51` | Witness interoperability target; reopens `D39` against the new standards bodies | `CP4` | Open, `POST-MVP` |
| `D53` | Whether longitudinal outcomes ship before `MV5` returns | `CP4`, gated by `P29` | Open, `POST-MVP` |
| `D1`–`D3`, `D5`–`D8`, `D11`–`D17`, `V1`, `V5`, `V6`, `V9`–`V11` | Orchestra and interface decisions | Their original phases | `POST-MVP`, retained |

---

## 13. The release procedure

Run once, at `MV4` exit. Every step produces an artefact; a step with no artefact did not happen.

1. **Quiesce.** One commit. Three suites, sequential, under the shared lock. Record the counts (`MP3`).
2. **Checks.** Claims binding · MVP traceability · surface coverage · tier absence · spawn-environment AST guard · no-model-call guards · packaging guards. All green.
3. **Compatibility.** Every published row's smoke test run and passing. Failing rows removed (`MK5`).
4. **Build.** `npm run package`. Confirm file count, no nested `extension/extension/` **in the tree or the index**, verifier staged, `SECURITY-AND-DATA.md` and `DEPLOYMENT.md` staged, library staged once, icon present.
5. **Checksum and bill of materials.** Emit `meridian-loom-<version>.vsix.sha256` **and the CycloneDX AI-BOM**, and confirm the AI-BOM matches the package (`AC-62`). Confirm `docs/SECURITY-AND-DATA.md` §7 still describes exactly what it proves and what it does not.
6. **Install clean.** On a machine with no repository checkout: install the VSIX, open a fresh workspace, confirm the library seeds, run `cli doctor`, induce a failure, confirm the non-zero exit.
7. **Prove the claim.** Export a bundle; verify it with the staged `verify.py` on a machine that has never had Meridian installed; then uninstall Meridian and verify the bundle again.
8. **Cold start.** `MV4-T04` — a stranger, timed, unaided. Fix every question they had to ask.
9. **Release notes.** Agreeing with `DECISIONS.md`; limitations carried over unsoftened; the not-claimed list from `mvp-req-final.md` §13 stated plainly.
10. **Record.** Tag, and write the baseline into `docs/baselines/` with the counts, the file count, the digest and the platforms rehearsed.

---

## 14. What this plan deliberately does not schedule

**Retained, specified, tested where built, shipped where built, and not in the MVP.** Per `MP6`, none of it is removed from the tree.

| Retained | Where it is specified | Gated on |
|---|---|---|
| The Orchestra tier — loop runtime, roster, phase orchestrators, deterministic engine beyond the structural set | `Requirements_Final.md` M4–M9, M13, M21, M22, M26, M28, M33; `C1`–`C6`; `F3` | **`MV5`** / `D21` |
| Learning and portability — Trainer, distillation, adapter packages, `learned/` round-trip | M14, M15, M16; `C4` | `D21`, then `D5`, `D17` |
| The 26 deferred screens of the 44 | `VIGUIX_Final.md` §10; `gaps_guix_implementation.md` §18 | `GF3`, scoped by what `MV5` proves matters |
| Brownfield comprehension (`M38`) and the Comprehension Studio (10.48) | `gaps-requirements.md`; `V11` | `F3`/`GF4+` |
| Harness intelligence (`M47`, was `M41` in `jit-requirements.md`) — `J-1`…`J-4` | `jit-requirements.md`, `jit-impl.md`, `mvp-req-final.md` §14 | `POST-MVP`; `J-1` is the first candidate after the MVP |
| Run initiation beyond the invariant — `FR-M40-04`, `06`, `07`, `08`, `10` | `gaps_initiation.md` | `POST-MVP` |
| Witnessing, anchoring, in-toto envelope, policy simulator, signed policy distribution, retroactive backfill, trusted team analytics | `futures_requirements.md`; `futures-implementation.md` §16 | `POST-MVP`, in the slip order already written |
| Marketplace listing, licence key enforcement, open-core split | `D19` | **Deliberately deferred** |
| **Tool-call governance (`M48`), attested identity (`M49`), longitudinal outcomes (`M51`), DSSE/in-toto and C2PA envelopes (`M50-06`…`08`), provenance-tool export and conflict reporting (`M52-04`/`05`)** | `mvp-req-final.md` §17 | **The `CP1`–`CP4` track (§16), after `MV5`** |

---

## 15. Traceability appendix

### 15.1 `MVP-GAP` requirement → phase → task

| Requirement | Phase | Task |
|---|---|---|
| `MVP-R1.6` `FR-M46-06` support matrix | `MV4` | `MV4-T01` *(source: `MV1-T05`)* |
| `MVP-R1.7` `FR-M46-07` failure rehearsal | `MV4` | `MV4-T02` |
| `MVP-R2.3` `FR-M34-03` registry browsable | `MV3` | `MV3-T02` |
| `MVP-R2.4` `FR-M44-03`…`05` digest pinning | `MV3` | `MV3-T01` |
| `MVP-R2.5` `FR-M46-03` PR evidence card | `MV3` | `MV3-T04` |
| `MVP-R3.1` `FR-M42-11`/`12`, `SEC-32` enforcement point | `MV1` | `MV1-T01`…`T04` |
| `MVP-R3.5` `FR-M44-08`…`10` compatibility matrix | `MV1` | `MV1-T05`…`T07` |
| `MVP-R4.1` `FR-M40-01`/`02` one request object | `MV2` | `MV2-T01` |
| `MVP-R4.2` `FR-M40-03` mandatory preflight | `MV2` | `MV2-T02`, `MV2-T06` |
| `MVP-R4.3` `FR-M40-05`, `SEC-30` launch authority | `MV2` | `MV2-T03` |
| `MVP-R4.4` `FR-M40-09` clean cancellation | `MV2` | `MV2-T04` |
| `MVP-R4.5` `FR-M40-11` absent below Governor | `MV2` | `MV2-T05` |
| `MVP-R5.1` `FR-M46-17` thresholds before the study | `MV1` | `MV1-T08` |
| `MVP-R6.1` `NFR-40`, `FR-M44-06`/`07` contract drift visible | `MV1` | `MV1-T09` |
| `MVP-R6.2` `SEC-34` a forged signal is never promoted | `MV1` | `MV1-T10` |
| `MVP-R6.3` `AC-52`, `FR-M44-01`/`02` verified agent identity | `MV3` | `MV3-T01b` |
| `MVP-R6.4` `NFR-43`, `FR-M46-08` seven-day soak | `MV4` | `MV4-T06` |
| `MVP-R6.5` `FR-M46-05` keyboard and screen-reader journeys | `MV4` | `MV4-T07` |
| `MVP-R7.1` `FR-M52-01`…`03` read and notarise a rival's record | `MV3` | `MV3-T06` |
| `MVP-R7.2` `FR-M50-01`…`03` `ISO/IEC 24970` and Article 26 mapping | `MV1` | `MV1-T11` |
| `MVP-R7.3` `FR-M50-04` CycloneDX AI-BOM | `MV4` | `MV4-T08` |
| `MVP-R7.4` §16.2 the narrowed claim | `MV1` | `MV1-T12` |
| `MVP-R3.7` banned patterns 28 and 30 get named tests | `MV1` | `MV1-T13` |
| `MVP-R8.1`…`8.3` disclosure, notices, support policy | `MV4` | `MV4-T09` |
| `AC-38` one contract, five origins · `AC-40` no surface below Governor | `MV2` | `MV2-T01`, `MV2-T05` |
| `SEC-33` adapter refused on digest mismatch | `MV3` | `MV3-T01` |
| `NFR-42` zero acknowledged-entry loss, 15-minute recovery | `MV4` | `MV4-T02` |
| *(no requirement id)* packaging guards check git, not only the filesystem | `MV0` | `MV0-T06` — defect found by the freeze audit, raised under §19.1 |
| `MVP-R5.2`…`R5.4` the study itself | `MV5` | `MVP-HUMAN` — not engineering work |

### 15.2 Acceptance criteria touched

| AC | Phase | Note |
|---|---|---|
| `AC-36` tier disabled leaves the tiers below whole | `MV2-T05` | Extended to the `run/*` namespace |
| `AC-41` coverage stated, never silently truncated | every phase | Already `BUILT`; every new figure inherits it |
| `AC-45` enforcement boundary declared | `MV1-T01`…`T04` | The interface half of an already-built backend |
| `AC-49` bundle verifies without Meridian | `MV4-T03`, step 7 | Already `BUILT`; re-proven from the package |
| `AC-50` two editors, two SCM providers, one evidence shape | `MV5` | `MVP-HUMAN` |
| `AC-38`, `AC-40` initiation contract and tier absence | `MV2-T01`, `MV2-T05` | New |
| `AC-52` a binary swap is visible | `MV3-T01b` | New |
| `AC-59` rival's record read, labelled, notarised | `MV3-T06` | New |
| `AC-61` the bundle speaks the buyer's standard | `MV1-T11` | New |
| `AC-62` the AI-BOM matches the package | `MV4-T08` | New |
| `AC-63` the narrow claim is the only claim | `MV1-T12` | New |
| `AC-60`, `AC-64`…`AC-68` | `CP1`–`CP4` | `POST-MVP` |
| `AC-53` fresh workspace usable | `MV4-T03` | Already `BUILT` (`D43` seeding); re-proven from the installed VSIX |
| `AC-01`…`AC-29` | `F3`/`GF3` | `POST-MVP`, gated on `MV5` |
| `AC-54`…`AC-58` *(was `AC-41`…`45` in `jit-impl.md`)* | `J-1`…`J-4` | `POST-MVP` |

### 15.3 Source plan → what survives here

| Source plan | Principles | Phases | Kill criteria | Slip plan | Status |
|---|---|---|---|---|---|
| `Requirements-implementation.md` | `E1`–`E14` **in force** (§2.1) | `S0`, `C1`–`C6` retained (§8) | — | Retained (§10 inherits) | Destination, not route |
| `viguix-implementation.md` | `B1`–`B14` **in force** | `G0`–`G8` retained (§8) | — | Retained | Superseded as a route by `GF*` |
| `gaps_implementation.md` | `G1`–`G7` **in force** | `F−1`–`F4+` retained (§8) | `K1`–`K7` **in force** (§9) | Retained | **The delivery spine** |
| `gaps_guix_implementation.md` | `H1`–`H7` **in force** | `GF0`–`GF4+` retained (§8) | `GK1`–`GK6` **in force** | Retained | In force; parity programme at `MV3` |
| `futures-implementation.md` | `J1`–`J9` **in force** | `N0`–`N4` retained (§8) | `NK1`–`NK7` **in force** | Retained | The assurance track; `N3` is `MV5` |
| `jit-impl.md` | `J-P1`–`J-P6` **in force when built** | `J-1`–`J-4` retained (§8, §14) | `JK1`–`JK6` **in force when built** | Retained | `POST-MVP`, whole |
| **Competitive review, 12 Sept 2026** | `P31`–`P34` *(requirements)* | `CP1`–`CP4` (§16) | `MK8` | §10 inherits | Four items in the MVP as `MVP-R7`; the rest `POST-MVP` |
| **this plan** | `MP1`–`MP9` | `MV0`–`MV5`, then `CP1`–`CP4` | `MK1`–`MK8` | §10 | **The current route** |

### 15.4 The requirements documents this plan serves

`vision.md` · `Requirements_Final.md` · `VIGUIX_Final.md` · `gaps-requirements.md` · `gaps_guix.md` · `gaps_initiation.md` · `futures.md` · `futures_requirements.md` · `jit-requirements.md` · `sample-meridian-loom-gui.html` — all dispositioned in `mvp-req-final.md` §15, none deleted, none ignored.

---

## 16. The competitive track — `CP1` to `CP4` · `POST-MVP`

`mvp-req-final.md` §§16–18 record the 12 September 2026 competitive review and the five modules it produced. **Four of its items enter the MVP as `MVP-R7`; everything else is here, named and sequenced, and deliberately outside the MVP.**

This track does not start until `MV5` returns. `P29` — build the next thing only where evidence says it pays — governs all of it, and `MV5` is the evidence.

| Phase | Name | Modules | Band | Exit |
|---|---|---|---|---|
| **CP1** | **Notary, completed** | `M52` *(04, 05)* | 2–3 wk | Export to other tools' formats; a disagreement between two provenance tools is reported, never silently resolved (`AC-60`) |
| **CP2** | **Attested identity** | `M49` | 4–6 wk | An attested agent records a higher assurance level than a self-declared one, and the four levels are distinguishable everywhere (`AC-66`). **Closes `NK3` without an identity provider** |
| **CP3** | **The tool-call boundary** | `M48` | 6–8 wk | A refused call fails closed and traces to the human who authorised the run (`AC-64`); an organisation's existing gateway is observed, not replaced (`AC-65`) |
| **CP4** | **Outcomes and standard envelopes** | `M51`, `M50` *(05–08)* | 5–7 wk | 30/60/90-day outcomes bind to the gate decision (`AC-67`); a DSSE attestation verifies with off-the-shelf tooling (`AC-68`) |

**Order rationale.** `CP1` finishes what `MVP-R7.1` starts and is the cheapest. `CP2` before `CP3` because a gateway that cannot say *which* agent called is a log, not a control. `CP4` last because `FR-M51-01` needs ninety days of history before its own numbers mean anything — start accumulating the signal at `MV4`, report it at `CP4` (`E9`, signals cannot be back-filled).

**`CP3` is conditional on `D48`.** Shipping an MCP gateway puts Meridian in a category with funded incumbents. The alternative — consume their decision logs and stay the notary (`FR-M48-03`, `P31`) — is cheaper, more honest about what Meridian is, and may be the whole answer. **Decide it with a pilot customer's platform team in the room, not from this document.**

---

## 17. Artefact register — what this plan creates

Several tasks reference files that **do not exist yet**. That is correct — the task is what creates them — but a reader hitting a path that is not there should be able to tell "not built yet" from "broken reference". Verified absent at the freeze baseline.

| Artefact | Created by | Purpose |
|---|---|---|
| `docs/claims.md` | `MV0-T03` | One row per externally visible claim, each naming the test that backs it |
| `scripts/check-claims.mjs` | `MV0-T03` | Fails the build on a claim whose named test does not exist |
| `scripts/check-mvp-traceability.mjs` | `MV0-T04` | Fails on drift between `mvp-req-final.md` §5 and this plan |
| `scripts/check-demo-package.mjs` | `MV3-T05` | Fails when a `DEMO.md` step is not backed by something inside the built VSIX |
| `scripts/generate-bom.mjs` | `MV4-T08` | Generates the CycloneDX AI-BOM from the built VSIX; `--check` fails on drift |
| `scripts/generate-notices.mjs` | `MV4-T09` | Generates `THIRD-PARTY-NOTICES.md` from the licence sweep; `--check` fails when it is stale |
| `scripts/check-release-notes.mjs` | `MV4-T05` | Fails when the release notes soften a limitation, omit a disclaimed claim, or cite an unrecorded decision |
| `scripts/run-compatibility-smoke.mjs` | `MV4-T01` | Runs each matrix row's smoke test, counting a row verified only on the platform it claims |
| `scripts/record-resilience.mjs` | `MV4-T02` | Records one resilience rehearsal per failure for the configuration it runs on |
| `scripts/validate-package.mjs` | `MV4-T03` | Validates the installed package by executing its extracted sidecar, CLI and verifier |
| `scripts/soak.mjs` | `MV4-T06` | The seven-day soak harness, run against the packaged sidecar |
| `docs/baselines/cold-start/PROTOCOL.md` · `docs/baselines/assistive/PROTOCOL.md` | `MV4-T04` · `MV4-T07` | What a person must do, time and record for the two rehearsals no script can perform |
| `docs/baselines/` | `MV0-T01` | Suite counts, commit, platform and wall-clock per phase exit |
| `docs/evidence-gate.md` | `MV1-T08` | The Orchestra go/no-go thresholds, written before the study |
| `shared/schema/compatibility.json` | `MV1-T05` | The machine-readable support matrix; the published table and `doctor` output are generated from it |
| `core/meridian_core/initiation.py` | `MV2-T01` | The one run contract and the one entry point; depends on nothing, so the ordering is testable without a repository |
| `webview/src/screens/LaunchScreen.tsx` | `MV2-T06` | Screen 10.51 at its minimum, registered at the Governor tier so it is absent below it |
| `docs/baselines/resilience/` | `MV4-T02` | One recorded run per failure per configuration |
| `meridian-loom-<version>.cdx.json` | `MV4-T08` | The CycloneDX AI-BOM, published beside the VSIX and its checksum |
| `SECURITY.md` | `MV4-T09` | Vulnerability disclosure: scope, contact, expected response |
| `THIRD-PARTY-NOTICES.md` | `MV4-T09` | Generated from the lockfiles; backs the no-copyleft claim |
| `docs/SUPPORT.md` | `MV4-T09` | Supported versions, breaking-change notice, migration guarantee, exit path |
| `core/meridian_core/metrics/evidence_study.py` | `MV5`, prepared | The study record's schema: what only people can supply to the evidence gate |
| `core/meridian_core/metrics/evidence_decision.py` | `MV5`, prepared | Drafts the computed half of the written decision, with the attachments' digests |
| `core/meridian_core/ledger/shape.py` | `MV5`, prepared | Compares two bundles' evidence shape, for `AC-50` |
| `docs/baselines/evidence-gate/PROTOCOL.md` · `study-record.template.json` | `MV5`, prepared | How the study is registered, run, scored and published; a template that cannot be scored as a study |
| `docs/baselines/first-value/PROTOCOL.md` · `docs/baselines/two-editors/PROTOCOL.md` | `MV5`, prepared | `FR-M46-04`'s five sessions and ten review tasks; `AC-50`'s two editors and two SCM providers |

**Already present and depended on:** `docs/SECURITY-AND-DATA.md` · `docs/DEPLOYMENT.md` · `DEMO.md` · `DECISIONS.md` · `verifier/verify.py` · `docs/spec/meridian-ledger-trailer.md` · `docs/spec/evidence-portability.md` · `shared/schema/methods.json` · `shared/schema/tiers.json` · `shared/schema/unsurfaced.json` · `scripts/check-surface-coverage.mjs` · `scripts/run-tests.mjs` · `extension/test/run-lock.ts`.

---

## 18. Definition of done — the MVP as a whole

Per-phase exits are in each phase. **This is the single list that says the MVP is finished.** Every line is a passing check, a recorded measurement, or a named document — nothing here is a judgement.

### Engineering

- [ ] Every `MVP-GAP` identifier in `mvp-req-final.md` §5 reads `BUILT`, and `check-mvp-traceability.mjs` is green
- [ ] Three suites green, sequential, one tree, one commit (`MP3`)
- [ ] Every test added during `MV0`–`MV4` was demonstrated failing first, with the demonstration in its commit message (`MP2`)
- [ ] `check-claims.mjs` green: every shipped claim bound to a passing test (`MP5`)
- [ ] `check-surface-coverage.mjs` green with zero undeclared orphans
- [ ] Tier absence proven for every tier floor, including `run/*` (`AC-36`, `AC-40`)
- [ ] Spawn-environment AST guard, no-model-call guards and packaging guards all green
- [ ] Nothing added is reachable only from a test (`MP4`)

### The package

- [ ] `meridian-loom-<version>.vsix` builds; file count recorded; **no nested `extension/extension/` directory, and nothing tracked under that path** (`MV0-T06`)
- [ ] Verifier, both staged documents, the library (**once**) and the icon are all inside it
- [ ] `.sha256` and the CycloneDX AI-BOM published beside it; the AI-BOM matches the package (`AC-62`)
- [ ] Every behaviour verified from the **installed** extension, not the checkout (`MP7`)

### The evidence claim

- [ ] A bundle exported, verified by the staged `verify.py` on a machine that never had Meridian installed, then verified **again after uninstalling** (`AC-33`, `AC-49`)
- [ ] The bundle carries the `ISO/IEC 24970` mapping, the Article 26 retention margin, and the sentence saying what the mappings are not (`AC-61`)
- [ ] A third-party provenance record read, labelled by source, notarised, and its later alteration detected (`AC-59`)

### Resilience and reach

- [ ] Every published compatibility row backed by a passing smoke test; failing rows **removed, not degraded** (`MK5`)
- [ ] Twenty rehearsals across four configurations; **zero acknowledged ledger entries lost** (`NFR-42`)
- [ ] Seven-day soak with no unbounded resource growth (`NFR-43`)
- [ ] Launch, review and export complete keyboard-only and under a screen reader (`FR-M46-05`)

### Adoptability — the thesis

- [ ] A person who has not read the source went from the VSIX to a verified bundle **unaided**, and the time is recorded (`MK1`)
- [ ] Every question they had to ask is fixed in the documents
- [ ] `SECURITY.md`, third-party notices and the support/upgrade policy are in the package (`AC-69`…`AC-71`)
- [ ] Release notes agree with `DECISIONS.md`, carry the limitations unsoftened, and state what the MVP does **not** claim

### Human-gated — tracked, never counted as engineering completion (`MP8`)

- [ ] `MV5` preregistered study · first-provenance-answer timing · two editors and two SCM providers — each blocked on people: a pilot team with twenty stories and reviewers who did not run the gates; five people who have not seen the product; a pilot customer with two SCM providers, **and first a second editor claimed in the compatibility matrix**. The protocols and the scorer are ready (`MV5`, *Prepared*)

**When every engineering box above is ticked, the MVP is delivered.** The `MV5` boxes decide what comes after it, and `R29` stands: stopping there is a designed, acceptable outcome.

---

*Frozen scope, live plan: `mvp-req-final.md` v1.1 fixes what is built; this document keeps the order and the task detail, and §17 lists every artefact it creates.*

*End of plan. `MV1` protects the claim, `MV2` makes the product startable, `MV3` makes it reachable and notarises everyone else's record too, `MV4` makes it shippable, and `MV5` decides whether anything beyond it is ever built. `CP1`–`CP4` wait for that answer. Nothing already developed is removed to get there.*
