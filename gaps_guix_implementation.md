# Meridian Loom — GUI Gaps Implementation Plan

| | |
|---|---|
| **Document** | gaps_guix_implementation.md |
| **Version** | 1.0 |
| **Author** | Ravaleedhar Reddy |
| **Governs** | The build order for `gaps_guix.md` v1.0 |
| **Supersedes** | `viguix-implementation.md` v2.1 §4 phase map and §7 sequencing. Its phase *contents* survive; the entry point and the order do not. |
| **Companions** | `gaps_guix.md` · `gaps_implementation.md` · `gaps-requirements.md` · `VIGUIX_Final.md` v2.1 · `HONEST_ASSESSMENT.md` |
| **Scale** | 5 GUI phases · 6 new screens · 5 cross-cutting systems · 5 design stances · 12 amended screens · 5 banned patterns |

---

## Table of Contents

0. [About This Plan](#0-about-this-plan)
1. [How to Use This Document](#1-how-to-use-this-document)
2. [Build Principles](#2-build-principles)
3. [Stack Decisions](#3-stack-decisions)
4. [Phase Map](#4-phase-map)
5. [GF0 — Recorder](#gf0--recorder)
6. [GF1 — Governor](#gf1--governor)
7. [GF2 — Evidence](#gf2--evidence)
8. [GF3 — Orchestra](#gf3--orchestra)
9. [GF4+ — Refinement](#gf4--refinement)
10. [Cross-Cutting Workstreams](#10-cross-cutting-workstreams)
11. [Definition of Done — Any Screen](#11-definition-of-done--any-screen)
12. [Sequencing Dependencies](#12-sequencing-dependencies)
13. [Engineering Interlock](#13-engineering-interlock)
14. [Competitor Parity Programme](#14-competitor-parity-programme)
15. [Kill and Cut Criteria](#15-kill-and-cut-criteria)
16. [Slip Plan](#16-slip-plan)
17. [Decision Schedule](#17-decision-schedule)
18. [What Happens to the 44 Existing Screens](#18-what-happens-to-the-44-existing-screens)
19. [Traceability Appendix](#19-traceability-appendix)

---

## 0. About This Plan

### 0.1 What changed

`viguix-implementation.md` v2.1 built all ten GUI phases — 44 screens — against the Simulation Core before any real agent ran. `HONEST_ASSESSMENT.md` found that to be the most expensive way to discover the thesis is wrong, and `gaps_guix.md` repositioned the interface around the trust layer.

This plan is the build order for that repositioning. Three changes:

1. **Three screens ship first, built against real external-agent sessions** — not 44 screens against a simulator.
2. **The interface tiers with the product.** Flight Recorder → Governor → Orchestra. A user never sees an empty orchestra.
3. **The `VendorTag` becomes as fundamental as the `StateRing`.** Every agent-attributed artifact anywhere in the product carries its vendor and its observation confidence.

### 0.2 The single hardest thing in this plan

**Building against real external-agent sessions is harder than building against a simulator, and it is the point.**

A Claude Code session in your workspace produces messy, partial, out-of-order telemetry. A Copilot PR arrives with no in-editor trace. Cursor gives you almost nothing but file changes. The interface has to be honest about that — three confidence levels, visibly different, never blurred — and you cannot design that honestly against clean synthetic data.

So GF0 has an unusual first task: **capture a corpus of real sessions before designing the screens that show them.**

### 0.3 What this plan does not do

It does not discard `VIGUIX_Final.md`. Its 44 screens, six themes, motion system, 26 cross-cutting systems and 27 banned patterns all survive. §18 states exactly which screens are built when. Every ID survives; only its phase moves.

---

## 1. How to Use This Document

Five phases. **GF0 and GF1 build. GF2 measures. GF3 and GF4+ are the existing plan, reached only if the evidence gate passes.**

Two rules govern everything:

- **A screen is not built until a real session exists that it can show.** The Simulation Core is not the backend for GF0 or GF1; recorded reality is. The Simulation Core arrives in GF3 as the regression harness it was always going to become.
- **A screen is not done until it is correct at every tier below it.** Disabling Orchestra must leave Governor and Recorder whole — no broken panels, no empty orchestra, no orphaned state.

---

## 2. Build Principles

`B1`–`B14` from `viguix-implementation.md` v2.1 remain in force. These are added, each from a design stance in `gaps_guix.md` §1.

| # | Principle | Consequence | From |
|---|---|---|---|
| **H1** | **Build against recorded reality, not simulation.** | GF0 and GF1 screens are developed against a corpus of real Claude Code, Copilot and Cursor sessions. A screen whose corpus scenario does not exist is not started. | §0.2 |
| **H2** | **The vendor tag and confidence glyph are primitive-level invariants.** | Like `ConfidenceBar` refusing to render without calibration: an `AgentToken`, weft row, ledger row or hunk refuses to render without `VendorTag` and observation confidence. Enforced in the component, not by review. | DS-1, X-27 |
| **H3** | **Tier disclosure is structural, not conditional rendering.** | The shell knows the tier. The command registry filters. Higher-tier screens are not in the route table. There is no `if (tier === 'orchestra')` scattered through components. | DS-3, X-28 |
| **H4** | **Match before you exceed.** | Every surface with a competitor equivalent is task-timed against it before any Meridian-only feature is added to that surface. | DS-5, X-31 |
| **H5** | **Inferred never looks like direct.** | Three confidence levels get three visually distinct treatments — weight, pattern and label — at every size. A user must never have to remember which is which. | DS-1, banned pattern 31 |
| **H6** | **The first screen must be complete alone.** | 10.45 Flight Recorder has no roster, no floor, no loops, and must not feel like a product with pieces missing. Tested with users who have never seen the specification. | DS-3 |
| **H7** | **Every chart states its finding in words.** | A one-sentence written finding beneath every Trust Observatory chart, in the same theme and the same text size as body copy. | A-10 |

---

## 3. Stack Decisions

Inherits `viguix-implementation.md` v2.1 §3. These are new or changed.

| Concern | Decision | Rationale |
|---|---|---|
| **Session corpus** | A recorded corpus of real agent sessions — captured in GF0 task 1 — stored as ledger fixtures with their original telemetry, replayable into the webview in Storybook and E2E tests | H1 |
| **`VendorTag` rendering** | A single primitive with a bespoke glyph set (`V10`), an accessible name, and the confidence mark composed in. Never two components. | X-27, H2 |
| **Vendor glyphs** | 5–7 bespoke marks, legible at 12px, mutually distinct under all three colour-vision deficiencies, trademark-cleared. **Not vendor logos** (banned pattern 29). | `V10`, banned 29 |
| **Confidence encoding** | ● direct (filled) · ◐ telemetry (half) · ○ inferred (hollow) — **plus** a weight difference and a text label on hover/focus. Three encodings, per `H5`. | DS-1, A-09 |
| **Tier gating** | Tier is a property of the route table and the command registry, resolved at shell boot. Screens above the active tier are not registered. | H3, X-28 |
| **Charts** | X-07 chart grammar, built in GF0 because the Trust Observatory in GF1 depends on it and rejection-rate sparklines appear in GF0 | X-07 |
| **Weave renderer** | The existing `WeaveCanvas` from `VIGUIX_Final.md` §12.1, extended with a vendor lane and confidence rendering per row | 10.3 amendment |
| **Editor decorations** | Gutter marks and hover provenance read **every** vendor's trailers, not only Meridian's — one decoration provider, vendor-agnostic | X-30, 10.42 amendment |
| **Storybook** | Theme, density, phase-set switchers **plus a vendor switcher and a confidence switcher**, so every component is exercised across all three confidence levels and every vendor from the first commit | H2, H5 |

---

## 4. Phase Map

| Phase | With engineering | Screens | Built against | Exit |
|---|---|---|---|---|
| **GF0** | **F0** | 10.45, 10.46, 10.7, 10.3 *(agent-agnostic)*, 10.40 *(rewritten)*, 10.50 | Real recorded sessions | `AC-30`, `AC-33`, `NFR-28` |
| **GF1** | **F1** | 10.1, 10.6, 10.27, 10.28, 10.32, 10.43 *(ACP host)*, 10.47, 10.49, 10.16 *(external-aware)* | Real gated external PRs | `AC-31`, `AC-32`, `AC-34`, `AC-36`, `AC-37`, `X-31` |
| **GF2** | **F2** | None. The Trust Observatory's numbers are the deliverable. | Real | The evidence decision |
| **GF3** | **F3** | The remainder of `VIGUIX_Final.md` §10 — but only what GF2 proved matters | Real agents; Simulation Core as harness | `AC-01`…`AC-29` |
| **GF4+** | **F4+** | 10.48 Comprehension Studio, refinement, everything in `viguix-implementation.md` G8 | Real | WCAG AA, budgets, banned-pattern sweep |

**Six new screens. Twelve amended. Twenty-six deferred to GF3 or later.**

---

## GF0 — Recorder

**Goal.** A team installs Meridian, runs the agent they already use, and sees the cloth fill with that agent's work — vendor-tagged, confidence-labelled — with a provenance answer for any line and an export that survives uninstallation.

**Screens.** 10.45 Flight Recorder · 10.46 External Agents · 10.7 Ledger · 10.3 The Weave *(agent-agnostic)* · 10.40 First-Run *(rewritten)* · 10.50 Unlock

### Workstream A — The session corpus *(before any screen)*

1. **Capture real sessions.** Run Claude Code, Copilot and Cursor against a real repository and record everything the F0 observers produce — OTel streams where available, `Co-Authored-By` trailers, PR payloads, filesystem change bursts. Minimum: 3 vendors × 5 sessions × 3 confidence levels.
2. **Store as replayable fixtures** — ledger slices plus original telemetry, loadable into Storybook and Playwright.
3. **Catalogue the mess.** Document what is genuinely missing per vendor: no in-editor trace from Copilot, no local telemetry from Cursor, no `direct` confidence for Claude Code without OTel. **This catalogue is the design brief for the confidence system.** A screen designed before this exists will be designed for data that does not arrive.

### Workstream B — Foundation, minimum

4. **Token system, six themes, three densities** — `VIGUIX_Final.md` §4–§6, but only the primitives these six screens need. Defer the rest.
5. **Shell** — Crown, Loom Bar, main region, Selvage strip. **No Warp Spine yet** if the recorder is phase-agnostic in Flight Recorder mode; add it when 10.3 lands.
6. **`X-28` tier-aware disclosure** — route table and command registry filtered at boot (`H3`). Built now so `AC-36` is testable from GF0.
7. **`X-07` chart grammar** — needed for rejection sparklines here and the Trust Observatory in GF1.
8. **`X-04` dialog/sheet/drawer**, **`X-05` destructive-action pattern** with all three access paths, **`X-06` table primitive**, **`X-12` command registry**, **`X-13` error boundaries**, **`X-14` degraded modes**.
9. **Storybook** with theme, density, **vendor and confidence** switchers.

### Workstream C — The vendor and confidence system

10. **`X-27` `VendorTag`** as a primitive-level invariant (`H2`): glyph, accessible name, confidence mark composed in. A component test that fails if an `AgentToken` ≥20px renders without one.
11. **Vendor glyph set** — close **`V10`**: 5–7 bespoke marks, 12px-legible, distinct under protanopia, deuteranopia and tritanopia, trademark-cleared. **Never a vendor logo** (banned 29).
12. **Confidence encoding** per `H5` — three visual treatments, plus label on hover and focus, plus `A-09` screen-reader announcement with meaning ("observed directly", "from telemetry", "inferred from file changes"), never a symbol name.
13. **`X-29` external-session awareness** — the Crown shows an active session within 2 seconds, with vendor and confidence.
14. **`X-30` provenance hover** — one component, one behaviour, on editor lines, hunks, weft rows and PR rows.

### Workstream D — The screens

15. **10.45 Flight Recorder.** The Weave hero (agent-agnostic), This Session, Any Line, Export, Selvage. **`H6`: it must feel complete alone.** No roster, no floor, no loops, no placeholders for them.
16. **10.46 External Agents.** Session list with observation source and confidence; per-session detail; **observer health** with degraded-to-inferred shown in weld and the upgrade action; *Treat as story* (disabled in GF0, enabled in GF1); **no control that modifies the external agent** (`FR-M35-06`).
17. **10.7 Ledger.** Selvage strip, filterable entry stream with **vendor filter**, entry detail, proof inspection, bundle export naming every vendor recorded.
18. **10.3 The Weave**, agent-agnostic: `VendorTag` and confidence per row, vendor filter, export legend with vendor glyphs, `V-01` over-under texture, `V-05` tactile selvage, `A-04` summary announcement.
19. **10.40 First-Run**, rewritten: connect repository → run your existing agent → see the Weave → export a bundle. Four steps, no credential, no Meridian agent. **Target under 15 minutes (`NFR-28`) measured with five people.**
20. **10.50 Unlock** — the honest tier screen. What Governor adds, what it costs, what evidence the current tier has produced. One action, reversible.

### Workstream E — Accessibility and quality from the first commit

21. **`A-09`** confidence announced with meaning. **`A-10`** every chart carries a written finding. **`A-11`** Unlock's cost and evidence statements are plain text in every theme.
22. **`A-01`** three access paths on every destructive action; **`A-02`** colour-blind simulation in CI across six themes **and the vendor glyph set**; **`A-03`** 28px hit targets; **`B10`** canvas DOM parallel in the same commit as the canvas.
23. **Banned patterns 28–32** added to the review checklist and, where mechanisable, to lint rules.

### GF0 exit criteria

- [ ] **`AC-30`** Fresh machine, no model credential, existing agent run → Weave shows vendor-tagged passes and any line answers the provenance question, within 15 minutes
- [ ] **`AC-33`** Meridian uninstalled → trailers remain in `git log`, bundle verifies on a clean machine
- [ ] **`NFR-28`** Fifteen-minute first value measured with five people who have not seen the specification
- [ ] **`H6`** Those five people describe 10.45 as complete, not as a product with pieces missing — asked directly, and the answers recorded
- [ ] **`H5`** In a blind test, users correctly identify direct / telemetry / inferred rows without a legend
- [ ] **`H2`** No `AgentToken` ≥20px, weft row, ledger row or hunk can render without `VendorTag` and confidence — enforced by component tests, verified in Storybook
- [ ] **`AC-36` (partial)** With Governor and Orchestra not installed, every screen is whole; no route to an unbuilt screen exists
- [ ] Six themes, three densities, all six screens; visual snapshots green; colour-blind simulation green including vendor glyphs
- [ ] axe-core clean; every canvas has its DOM parallel
- [ ] Degraded observation renders visibly differently from healthy observation, verified by breaking an observer deliberately

### GF0 duration

**5–8 weeks**, tracking F0's 6–10. The corpus (Workstream A) is week one and must not be skipped. The vendor glyph set (`V10`) is the long-lead design item — start it in week one alongside the corpus.

### Decisions to close
`V9` *(one home screen or two)* · `V10` *(vendor glyphs)*

---

## GF1 — Governor

**Goal.** The recorded work becomes governed work on screen. External PRs pass through gates. The Adapter Bay hosts an ACP agent as well as Devin Desktop does — then shows the provenance, gates and trust that Devin cannot.

**Screens.** 10.1 Command Center · 10.6 Gate Room · 10.27 Decision Stream · 10.28 Steer & Clarify · 10.32 Roles · 10.43 Adapter Bay *(ACP host)* · 10.47 Trust Observatory · 10.49 Cross-Vendor Spend · 10.16 Inspector *(external-aware)*

### Workstream A — The Governor home

1. **10.1 Command Center** as Governor's front door. **`V9` decides** whether it replaces 10.45 as home on unlock or sits beside it. Weave hero agent-agnostic (`DS-2`); gates and questions tiles include external agents' PRs; `E-CC-01`…`E-CC-10` from v2.1 as applicable.
2. **10.50 Unlock** wired for the Recorder→Governor transition, with the F0 evidence displayed (`H3`, `A-11`).

### Workstream B — Decision surfaces over other people's agents

3. **10.6 Gate Room** — gate cards for external-agent PRs showing vendor, observation confidence, and — for `inferred` observations — a **stronger warning that the artifact is what Meridian saw, not what the agent reported**. `E-GR-01`…`E-GR-06`.
4. **10.27 Decision Stream** — routine gates, keyboard-driven, seen-before-approve enforced, rubber-stamp detector (`FR-M20-06`) visible to the approver.
5. **10.28 Steer & Clarify** — steer composer and question cards for **hosted** agents. For **observed** agents, the UI states plainly that steering is unavailable rather than offering a control that does nothing.
6. **10.17 Diff Theater** amended — `VendorTag` per hunk; inter-agent conflicts as a distinct rework class (`FR-M35-07`).
7. **Rework reason taxonomy** (`E-GR-03`) in the UI — it is what makes the Trust Observatory's reason distribution possible.

### Workstream C — The Adapter Bay as ACP host

8. **10.43 Adapter Bay rebuilt as an ACP host UI**: browse and install from the ACP Registry, launch and manage sessions, permission requests shown **with Meridian's policy check already applied** (`FR-M34-04`).
9. **`X-31` parity check against Devin Desktop's Agent Command Center** — task-timed on start / watch / steer / stop / review, five engineers, before any Meridian-only feature is added to this screen (`H4`).
10. **Then exceed:** that agent's provenance, gates and trust score, inline — the thing Devin Desktop cannot show.
11. **Invalid adapters listed with plain-language errors**, never hidden.

### Workstream D — Trust and money

12. **10.47 Trust Observatory** — rejection rate per agent / action class / phase / repository on the X-07 grammar, **split greenfield/brownfield on every chart** (`FR-M37-06`); rejection reason distribution; trust score decomposition with the autonomy ladder embedded; agent-vs-agent comparison including external agents; **the J-curve** with the dip labelled as a phase; tokenmaxxing warning; module effectiveness map. **`H7`: every chart carries a written finding.**
13. **10.49 Cross-Vendor Spend** — spend by vendor, model, agent, story, team, cost centre; forecast with budget line; ceilings on hosted agents and warnings on observed; deterministic-path saving beside the vendor bill; Meridian's own spend in the same table, never hidden.
14. **10.22 KPI Observatory** amended with the M37 trust set and the greenfield/brownfield split.

### Workstream E — Identity, inspection, remaining systems

15. **10.32 Roles** — who-am-I, roles matrix, SoD explainer naming the rule and the alternative approver, N-of-M progress, delegation, approval hygiene shown privately to the approver and in aggregate to Governors.
16. **10.16 Inspector, external-aware** — Trace shows what was observed and at what confidence; Terminal shows the OTel or log stream where available; Policy and Memory tabs say "not applicable — external agent" rather than rendering empty.
17. **10.31 Routing Observatory** amended — external agents' model usage where observable, with "not observable" stated where it is not.
18. **`X-01` Omnibar**, **`X-11` notification model**, **`X-19` context menus**, **`X-22` roster scaling**, **`X-18` undo semantics**, **`X-20` drag and drop**.
19. **10.4 Agents Watch** amended — external agents listed alongside Meridian's with vendor, observation source, trust score and rejection rate columns.
20. **10.42 Editor surfaces** amended — hover provenance and blame decoration read every vendor's trailers.

### GF1 exit criteria

- [ ] **`AC-31`** An ACP Registry agent installs, enters probation, completes a packet, with every permission request policy-checked before the human sees it
- [ ] **`AC-32`** A Copilot-from-Jira PR is ingested, gated, and merged only after a recorded human approval — all in one ledger range, visible on one screen
- [ ] **`AC-34`** After 20 stories across two agents, rejection rate and reason distribution per agent, split greenfield/brownfield, reconcile to the ledger
- [ ] **`AC-36`** With Orchestra disabled, Recorder and Governor function fully — no screen errors, no empty orchestra, no route to an unbuilt screen
- [ ] **`AC-37`** A story worked by one hosted and one observed agent shows both agents' spend, reconciling to the ledger
- [ ] **`X-31`** The Adapter Bay matches Devin Desktop's Agent Command Center on the five core operations, **measured and recorded**
- [ ] **`H7`** Every Trust Observatory chart carries a written finding; verified with a reader who does not read charts
- [ ] An `inferred` gate card is visibly and verbally more cautious than a `direct` one
- [ ] Six themes, three densities, all nine screens; snapshots, axe-core, colour-blind green

### Decisions to close
`V11` *(whether 10.48 Comprehension Studio is pulled forward for a brownfield-heavy pilot)*

---

## GF2 — Evidence

**No screens. The Trust Observatory's numbers are the deliverable.**

Twenty real stories through GF0 + GF1, using the team's own agents. The interface's job in this phase is to be used and to be measured, not to grow.

### What the interface is measured on

| Question | Instrument | Why it decides GF3 |
|---|---|---|
| Are provenance queries actually run? | Ledger query telemetry, `X-30` hover counts | If nobody asks the provenance question at the moment of need, the screens are unread |
| Does the Trust Observatory change a decision? | Recorded instances of an autonomy tier, agent choice or module restriction changed after viewing it | The difference between a dashboard and an instrument |
| Do gates get read, or clicked? | `FR-M20-06` time-on-artifact and expansion rate | If approvers rubber-stamp, the decision surfaces are theatre |
| Is the confidence system understood? | Blind re-test of `H5` with the pilot team at week 8 | The honesty mechanism only works if it is legible |
| Which screens are opened, and which are not? | Route telemetry, opt-in | Tells GF3 exactly which of the 26 deferred screens to build |

### Output

A written record of which screens earned their place, which were never opened, and **which of the 26 deferred screens the pilot team actually asked for.** GF3's scope is set by that list, not by `VIGUIX_Final.md` §10.

### Exit criterion
- [ ] The GF3 screen list, derived from measured usage and explicit requests, recorded with the evidence

---

## GF3 — Orchestra

**Reached only if `gaps_implementation.md` F2 says GO.**

This is `viguix-implementation.md` v2.1's G2–G8 content, re-based, and **scoped by GF2's evidence rather than by the original specification.**

### Ordering

1. **Screens GF2's evidence named first**, in the order the pilot team asked for them.
2. **Then the Orchestra-tier core** — 10.2 Floor, 10.5 Dojo, 10.9 Loop Graph, 10.19 Work Packet Board, 10.20 Verification Board, 10.29 Replay & Time-Travel, 10.30 Memory Studio.
3. **Then the modelling surfaces** — 10.8 CodeMap, 10.10 C4, 10.11 UML Studio, 10.12 Flow.
4. **Then the organisation surfaces** — 10.26 Portfolio, 10.33 Connectors, 10.34 Delivery Pipeline, 10.35 Repositories.
5. **Then the remainder** — 10.5 Dojo extensions, 10.13 Config Portal, 10.14 Skill Forge, 10.15 Onboarding, 10.21 Security Assurance, 10.23 Exchange, 10.24 Focus Mode, 10.36 Documentation, 10.37 Calibration, 10.38 Runtime, 10.41 Keyboard Map, 10.44 Instruction Library.
6. **The Simulation Core (M32) arrives here** as the regression harness for these screens — its original purpose, at last in its right place.

**Any screen GF2 showed nobody wants is not built.** It stays in `VIGUIX_Final.md` as specified and unbuilt, which is a legitimate state for a specification to leave a screen in.

### Exit criteria
- [ ] `AC-01`…`AC-29` for the screens built
- [ ] Every Orchestra screen tier-correct: disabling Orchestra leaves Recorder and Governor whole (`AC-36`, re-verified)
- [ ] Banned patterns 1–32 audited across every built screen

---

## GF4+ — Refinement

As `viguix-implementation.md` v2.1 G8, plus:

- **10.48 Comprehension Studio** (unless pulled into GF1 per `V11`) — with engineering F3's M38
- **`X-10` localisation**, **`X-16` personalisation**, **`X-17` multi-panel**, **`X-24` print styles**
- **Motion pass**, choreography audit, reduced-motion audit
- **WCAG 2.1 AA certification** with screen-reader sign-off across every built screen
- **Performance certification** on low-spec hardware
- **Banned-pattern sweep**, all 32
- **Copy pass** against `X-09`

---

## 10. Cross-Cutting Workstreams

| Workstream | Cadence | Notes |
|---|---|---|
| **Session corpus maintenance** | Every observed-agent release | `H1`. A vendor's release can change its telemetry; the corpus must track it or the screens are designed for stale data. |
| **Vendor and confidence invariant** | Every commit | `H2`. Component tests fail on a missing `VendorTag`. |
| **Tier isolation** | Every commit | Disable each tier in CI, run the lower tiers' full suite. `AC-36`. |
| **Colour-blind verification** | Every commit | Six themes **and** the vendor glyph set, all three deficiencies. |
| **Confidence legibility** | Every phase exit | Blind re-test of `H5` with fresh users. |
| **Competitor parity** | Every phase exit from GF1 | `X-31`. Competitor surfaces move; re-time. |
| **Written findings** | Every chart added | `H7`, `A-10`. |
| **Visual regression** | Every commit | Six themes × three densities × three confidence levels × vendor set |
| **Accessibility** | Authoring time; full audit GF4 | `A-01`…`A-11` |
| **Banned patterns** | Weekly critique | 1–32 |

---

## 11. Definition of Done — Any Screen

Inherits `viguix-implementation.md` v2.1 §6. Adds:

- [ ] **Built against a real recorded session**, not a fixture invented for the screen (`H1`)
- [ ] **Every agent-attributed element carries `VendorTag` and confidence**, enforced by component test (`H2`)
- [ ] **`inferred` is visibly and verbally distinct from `direct`** at every size (`H5`, banned 31)
- [ ] **Tier-correct** — registered only in its tier; disabling higher tiers leaves it whole (`H3`)
- [ ] **No control that cannot act** — where an observed agent cannot be steered or configured, the UI says so rather than offering a dead control
- [ ] **Every chart carries a written finding** (`H7`)
- [ ] **Vendor glyphs, never logos** (banned 29)
- [ ] **No Orchestra surface rendered below Orchestra**, not even as an empty state (banned 30)
- [ ] **No first-run path requiring a model credential or a Meridian agent** (banned 32)
- [ ] Six themes, three densities, colour-blind green, axe-core clean, canvas parallel present, reduced-motion lossless

---

## 12. Sequencing Dependencies

```
[engineering F−1 legal clearance]  ◄── nothing starts before this
 │
 └─→ GF0 Recorder                                              [5–8 weeks]
      │   corpus first · tokens · X-27…X-30 · tier scaffold
      │   10.45 · 10.46 · 10.7 · 10.3 · 10.40 · 10.50
      │   built against real sessions · complete alone
      │
      └─→ GF1 Governor
           │   ACP host UI · gates over external PRs · roles
           │   Trust Observatory · Cross-Vendor Spend · Inspector
           │   parity-checked against Devin Desktop before exceeding
           │
           └─→ GF2 EVIDENCE  ◄── which screens earned their place
                │
                ├─ STOP ──→ ship Recorder + Governor
                └─ GO ────→ GF3 Orchestra (scoped by GF2) ──→ GF4+ Refinement
```

**Hard serial:** GF0 → GF1 → GF2. **The corpus (GF0 Workstream A) precedes every screen.**

**Critical path:** the corpus → `X-27` vendor and confidence system → 10.45. Everything else in GF0 is downstream of those three.

---

## 13. Engineering Interlock

Per `gaps_implementation.md` §14.

| Engineering | GUI | The contract between them |
|---|---|---|
| **F−1** | — | Nothing starts. |
| **F0** | **GF0** | Engineering delivers observers and the ledger; GUI delivers the corpus and the three screens. **The corpus is a joint artifact** — engineering's observers produce it, the GUI designs against it. |
| **F1** | **GF1** | Engineering delivers the ACP host and gates; GUI delivers the host UI and decision surfaces. Parity timing is run jointly. |
| **F2** | **GF2** | No new work either side. Both measure. |
| **F3** | **GF3** | Engineering delivers the runtime and agents; GUI builds only the screens GF2 named. |
| **F4+** | **GF4+** | As the base plans. |

**The interlock rule:** the GUI never builds a screen for state the engineering phase has not yet produced, and engineering never ships state the GUI cannot show at the correct confidence.

---

## 14. Competitor Parity Programme

`X-31` operationalised. Run at every phase exit from GF1.

| Surface | Competitor benchmark | Operations timed | Meridian must |
|---|---|---|---|
| 10.43 Adapter Bay | Devin Desktop — Agent Command Center | start · watch · steer · stop · review | Match, then add provenance, gates, trust inline |
| 10.42 Editor surfaces | Cursor — inline context and agent edits | hover provenance · jump to origin | Match immediacy, then work on a Copilot-authored line too |
| 10.46 / 10.34 | Copilot — Agent HQ, PR loop | ingest PR · review · approve | Match, then gate it and record who approved |
| 10.46 observer | Claude Code — OTel, `Co-Authored-By` | read trailers · read telemetry | Match fidelity, then put its passes in the same cloth as everyone else's |
| 10.43 host | Zed — agent panel | bring-your-own-agent | Match the "nothing leaves the machine" promise, then add the signed ledger Zed does not keep |

**Method:** five engineers, unfamiliar with both products, timed on each operation. Meridian must be within 20% on every operation before any Meridian-only feature is added to that surface (`H4`). Results recorded per phase exit.

---

## 15. Kill and Cut Criteria

Mirrors `gaps_implementation.md` §15 from the interface side.

| # | Condition | Measured at | Response |
|---|---|---|---|
| **GK1** | In blind testing, users cannot distinguish `direct` from `inferred` | GF0 exit | The honesty mechanism has failed. Redesign the confidence system before shipping — it is the product's integrity. |
| **GK2** | Fewer than 2 of 5 first-value testers describe 10.45 as complete on its own | GF0 exit | `H6` failed. The recorder is not a product yet. Fix before GF1. |
| **GK3** | Provenance hover is used fewer than once per session in the pilot | GF2 | Nobody asks the question at the moment of need. Pivot to compliance-export-only. |
| **GK4** | The Trust Observatory never changes a decision | GF2 | It is a dashboard, not an instrument. Cut it to a KPI panel and stop investing. |
| **GK5** | Parity timing shows Meridian more than 50% slower than Devin Desktop on the core five | GF1 | Do not ship the Adapter Bay. Observation-only Governor is still a product. |
| **GK6** | GF0 exceeds 12 weeks | GF0 | Cut to 10.45 + 10.7 only, one vendor, and re-time. |

---

## 16. Slip Plan

Cut in this order. Each cut leaves a usable interface.

| Order | Cut | Cost |
|---|---|---|
| 1 | 10.50 Unlock as a screen — make it a dialog | Cosmetic |
| 2 | 10.3 The Weave as a separate screen in GF0 — keep only the 10.45 hero | Loses the full-screen governance-meeting view until GF1 |
| 3 | 10.46 External Agents — fold session list into 10.45 | Loses observer health visibility; acceptable with one vendor |
| 4 | 10.49 Cross-Vendor Spend | Loses a differentiator; the ledger still holds the data |
| 5 | 10.28 Steer & Clarify | Governor becomes gates-and-analytics only |
| 6 | 10.43 Adapter Bay | Loses the "as good as Devin Desktop" claim; observation-only Governor works |
| 7 | All of GF3 | The interface is the recorder and the governor. **Acceptable outcome.** |

**Never cut:** the `VendorTag` and confidence system · the provenance hover · the Selvage and chain-integrity display · three access paths on destructive actions · canvas DOM parallels · the written finding under every chart · tier isolation. Each is either the product's honesty or its accessibility.

---

## 17. Decision Schedule

| # | Decision | Must close by |
|---|---|---|
| **`V10`** | **Vendor glyph set — 5–7 bespoke marks, 12px-legible, colour-blind-distinct, trademark-cleared** | **GF0 week 1** *(long lead)* |
| `V9` | 10.45 and 10.1 as two screens, or one with tier-aware panels. Recommend two, with 10.1 replacing 10.45 as home on unlock. | GF0 |
| `V11` | Whether 10.48 Comprehension Studio is pulled into GF1 for a brownfield-heavy pilot | GF1 planning |
| `V3` | Font licensing and subsetting | GF0 week 1 |
| `V7` | Density default | GF0 |
| `D19` | Open-core — affects whether the GUI is open-sourced with the ledger | GF1 |
| `V1`, `V5`, `V6` | Sprite art, 2.5D vs flat, Focus Mode | **GF3** — deferred, since these are Orchestra-tier concerns |
| `D8` | Phase set fixed or configurable | GF3 *(the Recorder is phase-agnostic)* |

---

## 18. What Happens to the 44 Existing Screens

| Disposition | Count | Screens |
|---|---|---|
| **Built in GF0** | 6 | 10.45, 10.46, 10.7, 10.3, 10.40, 10.50 |
| **Built in GF1** | 9 | 10.1, 10.6, 10.16, 10.17, 10.22, 10.27, 10.28, 10.32, 10.43, 10.47, 10.49 *(with 10.4, 10.31, 10.42 amended)* |
| **Deferred to GF3, scoped by evidence** | 26 | 10.2, 10.5, 10.8, 10.9, 10.10, 10.11, 10.12, 10.13, 10.14, 10.15, 10.18, 10.19, 10.20, 10.21, 10.23, 10.24, 10.26, 10.29, 10.30, 10.33, 10.34, 10.35, 10.36, 10.37, 10.38, 10.41, 10.44 |
| **Deferred to GF4+** | 1 | 10.48 *(or GF1 per `V11`)* |
| **Deleted** | 0 | — |

**No screen is deleted.** A screen GF2 shows nobody wants stays specified and unbuilt — which is a legitimate and honest state for a specification to leave a screen in.

---

## 19. Traceability Appendix

### New screens

| Screen | Phase |
|---|---|
| 10.45 Flight Recorder | **GF0** |
| 10.46 External Agents | **GF0** |
| 10.47 Trust Observatory | **GF1** |
| 10.48 Comprehension Studio | GF4+ *(or GF1 per `V11`)* |
| 10.49 Cross-Vendor Spend | **GF1** |
| 10.50 Unlock | **GF0** *(GF1 wiring)* |

### New cross-cutting systems

| ID | Phase |
|---|---|
| X-27 `VendorTag` and confidence | **GF0** |
| X-28 Tier-aware disclosure | **GF0** |
| X-29 External-session awareness | **GF0** |
| X-30 Provenance hover | **GF0** |
| X-31 Competitor parity checks | **GF1**, then every phase exit |

### Design stances

| Stance | Enforced from |
|---|---|
| DS-1 Vendor tag fundamental | GF0, component level (`H2`) |
| DS-2 Weave agent-agnostic | GF0 |
| DS-3 Tier disclosure | GF0 (`H3`) |
| DS-4 Trust is a screen | GF1 |
| DS-5 Match then exceed | GF1 (`H4`) |

### Amended screens

| Screen | Phase | Amendment |
|---|---|---|
| 10.1 Command Center | GF1 | Governor front door, agent-agnostic hero |
| 10.3 The Weave | **GF0** | Vendor tags, confidence, vendor filter, export legend |
| 10.4 Agents Watch | GF1 | Vendor, observation source, trust, rejection columns |
| 10.6 · 10.27 | GF1 | External PR gate cards with confidence warnings |
| 10.7 Ledger | **GF0** | Vendor tags, vendor filter, multi-vendor bundle |
| 10.16 Inspector | GF1 | External-aware; "not applicable" rather than empty |
| 10.17 Diff Theater | GF1 | Vendor per hunk; inter-agent conflicts |
| 10.22 KPI Observatory | GF1 | M37 trust set, greenfield/brownfield split |
| 10.31 Routing Observatory | GF1 | External model usage where observable |
| 10.40 First-Run | **GF0** | Rewritten for the Recorder |
| 10.42 Editor surfaces | GF1 | All vendors' trailers |
| 10.43 Adapter Bay | GF1 | ACP host UI, parity-checked |
| 10.2 · 10.5 · 10.9 | GF3 | Orchestra tier only; never rendered below it |

### Accessibility and banned patterns

| ID | Phase |
|---|---|
| A-09 confidence announced with meaning | **GF0** |
| A-10 written finding per chart | **GF0** *(charts)*, GF1 *(Observatory)* |
| A-11 Unlock plain text | **GF0** |
| Banned 28–32 | **GF0**, checklist and lint |

---

*End of plan. The corpus precedes the screens. GF2 decides what GF3 contains.*
