# The evidence gate: thresholds, written in advance

**Status: thresholds fixed 12 September 2026. No study data exists at the time of writing, and that is the point.**

This document satisfies `FR-M46-17` (`MVP-R5.1`). It records the numeric criteria under which Meridian's own agent workforce — the Orchestra tier — is built, not built, or built in part, **together with an explicit commitment not to build it if the criteria are not met**.

It is written now because `P29` says investment beyond the current tier is gated on a published measurement *with the thresholds written before the measurement runs*. Deciding the bar after seeing the data is not a gate; it is a negotiation with oneself. `futures.md` `FUT-035` puts it plainly: write it down "while nobody has a stake in the answer".

This gate is `F2` in `gaps_implementation.md`, `GF2` in `gaps_guix_implementation.md`, `N3` in `futures-implementation.md`, and `MV5` in `mvp-impl-plan.md`. **They are the same gate.** It has never run.

---

## 1. What is being decided

**Not** whether Meridian works. The Flight Recorder and the Governor are built, tested and shipping; their value stands on its own, and `R29` already records that stopping there is a **designed, acceptable outcome**, not a failure.

What is being decided is whether to build **Meridian's own agents** — the Orchestra tier: loop runtime, phase orchestrators, the twelve-role workforce, the Trainer, harness intelligence. That is the largest remaining investment in the programme, and `D21` has been open since the repositioning.

**The null hypothesis is that we should not build it.** The burden of evidence is on the tier, not on the decision to stop.

## 2. Design

Preregistered. Three arms, because two cannot separate *recording* from *governing*:

| Arm | What the team uses |
|---|---|
| **A — baseline** | The team's own agents under their own native controls, plus whatever SCM branch protection and security tooling they already run |
| **B — recorder** | Arm A **plus** Meridian's Flight Recorder |
| **C — governor** | Arm B **plus** the Governor: gates, roles, approval binding, trust analytics |

Existing SCM protection and security tooling appear in **every** arm, so only the additional benefit is attributed to Meridian. Anything else inflates the result by counting controls the team already had.

**Sample.** Twenty stories is a **feasibility pilot, not a superiority test** (`FR-M46-15`). Twenty is enough to discover whether the instruments are usable, whether the gates fire, and whether anyone runs a provenance query. It is not enough to claim an effect size. The sample required for any comparative claim is determined **from the variance observed in the pilot**, before that claim is made.

**Discipline.** Corpus and evaluator frozen before testing. Blinded review where practical. Task assignment counterbalanced. Confidence intervals and exclusions published. No training on the evaluation set.

## 3. The thresholds

Measured across arms B and C against arm A, on the pilot team's own repositories.

### 3.1 Primary — the gates must do something

| # | Measure | Threshold for GO |
|---|---|---|
| **P1** | **Defects uniquely caught.** Defects the gates caught that the agent's own process did not | **At least 3 across 20 stories**, each independently confirmed as a real defect by a reviewer who did not run the gate |
| **P2** | **Rejection rate**, split greenfield/brownfield, arm C against arm A | **A reduction, or `P1` satisfied.** Either is sufficient; neither alone is necessary if the other holds |
| **P3** | **Change failure rate** for gated merges against the team's own baseline | **No worse.** A governance layer that raises change failure rate has failed regardless of every other number |

### 3.2 Primary — the instruments must be used

| # | Measure | Threshold for GO |
|---|---|---|
| **P4** | **Provenance queries actually run**, at the moment of need | **At least 1 per engineer per week**, sustained. Below this the product answers a question nobody asks — `K5` and `NK4` both fire |
| **P5** | **The Trust Observatory changes a decision** | **At least 1 recorded instance** of an autonomy tier, agent choice or module restriction changed after viewing it. Zero means it is a dashboard, not an instrument (`GK4`) |
| **P6** | **First-value retention** at week 8 | **At least 2 of 5** original testers still using it. Below this, `K2` fires |

### 3.3 Cost side — the tax must be bearable

| # | Measure | Threshold for GO |
|---|---|---|
| **C1** | **False blocks** — gates that stopped a change that was in fact fine | **No more than 15% of gate stops**, reviewer-adjudicated |
| **C2** | **Median human review time per gated PR** | **No more than 20% above** arm A. `K4` fires if cycle time rises without `P1` or `P2` |
| **C3** | **Approval hygiene** — expansion rate and time-on-artifact before approval | **No evidence of systematic rubber-stamping.** If approvers are not reading, the gates are theatre and the measurement is of nothing |

### 3.4 The Orchestra-specific bar

`P1`–`C3` decide whether the **governance layer** earns its place. Building Meridian's own agents needs one more thing, and it is the hardest:

| # | Measure | Threshold |
|---|---|---|
| **O1** | A demonstrated task class where the team's **existing agents underperform** and a Meridian agent would plausibly do better — named, with evidence, **before** any agent is built | **Required.** Without it the Orchestra is a solution looking for a problem, and §1.3 already forbids competing on agent capability |

## 4. The decision rule

Applied in order. **No threshold is renegotiated after the data exists** — that is what §5 is for.

| Outcome | Condition |
|---|---|
| **GO** — build the Orchestra | All of `P3`, `P4`, `P6` hold · **and** `P1` or `P2` holds · **and** all of `C1`–`C3` hold · **and** `O1` is satisfied |
| **STOP** — ship Flight Recorder + Governor as the product | The governance thresholds hold but `O1` is not satisfied. **This is a success**, per `R29` |
| **PIVOT** — narrow to the analytics product | `P4` fails (nobody queries provenance) but `P5` holds (the trust instruments are used). Drop the gating, keep the measurement |
| **KILL** | `P6` fails, or `P3` fails, or `C2` fails while both `P1` and `P2` fail. The layer costs more than it returns |

**Any outcome is published**, including an unfavourable one, together with missing data and exclusions (`FR-M46-15`). A gate that can only return one answer is not a gate.

## 5. Changing this document

**Before the study runs:** amendable. It is a preregistration, and refining a threshold nobody has tested against is legitimate. Amend in place, date it, and say what changed.

**Once the first story is measured:** frozen. A threshold changed after data exists is not a threshold, and any such change invalidates the preregistration and must be declared as such in the published result.

**If a threshold proves unmeasurable** — the instrument does not exist, or the pilot cannot supply the data — that is recorded as **unmeasured**, never as satisfied. `P25` and `P26` apply to this document as much as to the product: unknown is a state, not a residual.

---

## Provenance of these numbers

Stated so a reader can weigh them.

- **`P1` at least 3, `C1` 15%, `C2` 20%** are judgement, set to be *achievable but not trivially so*. They have no empirical basis and are not presented as having one.
- **`P6` 2 of 5** comes directly from `K2` in `gaps_implementation.md`, written before any of this was built.
- **`P3` no-worse** comes from the DORA finding in `vision.md` §1.1 that AI adoption correlates with reduced delivery stability. Raising throughput and change failure rate together is the failure mode the product exists to detect; shipping it would be indefensible.
- **`P4` 1 per engineer per week** is the weakest number here. It is a floor for "used at all", not a target. If the pilot shows the natural rate is lower but the queries that do happen are decisive, that is a finding to record **against** this threshold, not a reason to have set it differently after the fact.

**None of these figures may be quoted externally as a measurement.** They are the bar, not the result. §18 of `mvp-req-final.md` and `MP5` both apply.
