# Meridian Loom — Harness Intelligence Implementation Plan

| | |
|---|---|
| **Document** | jit-impl.md |
| **Version** | 1.0 |
| **Author** | Ravaleedhar Reddy |
| **Governs** | The build order for `jit-requirements.md` v1.0 (module M41) |
| **Slots into** | `gaps_implementation.md` phases **F3** and **F4** · equivalently `Requirements-implementation.md` **C3**/**C4** |
| **Scale** | 4 sub-phases · 26 requirements · 1 screen · 3 NFR · 3 SEC · 5 AC · 4 risks · 4 decisions |

---

## Table of Contents

0. [About This Plan](#0-about-this-plan)
1. [Build Principles](#1-build-principles)
2. [Stack Decisions](#2-stack-decisions)
3. [Phase Map](#3-phase-map)
4. [J1 — Harness as Artifact](#j1--harness-as-artifact)
5. [J2 — Archive and Retrieval](#j2--archive-and-retrieval)
6. [J3 — Gated Synthesis](#j3--gated-synthesis)
7. [J4 — Evolution, Promotion and Decision](#j4--evolution-promotion-and-decision)
8. [Cross-Cutting Workstreams](#8-cross-cutting-workstreams)
9. [Definition of Done](#9-definition-of-done)
10. [Sequencing and Host-Phase Interlock](#10-sequencing-and-host-phase-interlock)
11. [GUI Interlock](#11-gui-interlock)
12. [Kill Criteria](#12-kill-criteria)
13. [Slip Plan](#13-slip-plan)
14. [Decision Schedule](#14-decision-schedule)
15. [Traceability Appendix](#15-traceability-appendix)

---

## 0. About This Plan

### 0.1 The shape of this build

`jit-requirements.md` §13 states the position plainly: **the artifact half is unconditional, the synthesis half is an experiment.** This plan is built to honour that split.

- **J1 and J2 are unconditional.** Harnesses become named, versioned, ledger-recorded artifacts, and an archive with retrieval exists. Both are valuable with zero synthesis, zero external dependency and zero new model calls. Neither is a bet.
- **J3 and J4 are the bet.** Synthesis, evolution and promotion. Gated behind `D24`, shipped behind a flag, run in shadow, decided on your own corpus.

If `D24` says no, J1 and J2 still ship and still pay. That is deliberate.

### 0.2 Where it slots

Harness intelligence is an **Orchestra-tier** capability. It has no meaning in Flight Recorder (no Meridian agents) or Governor (external agents bring their own harnesses, which Meridian can *record* but not compose).

| Sub-phase | Host phase | Why there |
|---|---|---|
| **J1** Harness as artifact | **F3** *(C3)* | Needs the loop runtime and the roster to exist; every agent's harness becomes recordable the moment agents exist |
| **J2** Archive and retrieval | **F3** late *(C3)* | Needs J1 plus enough packets to populate an archive |
| **J3** Gated synthesis | **F4** *(C4)* | Needs the Trainer's evaluation machinery and the shadow-mode comparator |
| **J4** Evolution and promotion | **F4** *(C4)* | Needs J3 plus the Trainer's promotion gate and rollback shelf |

### 0.3 What is reused rather than built

Most of this module is existing machinery pointed at a new artifact. Building it fresh would be waste.

| Need | Reuse |
|---|---|
| Candidate generation, evaluation, promotion, rollback | Trainer pipeline `FR-M14-03`…`08` |
| Bounded repair loop | Loop runtime `FR-M4-02`…`08` — the repair loop declares all eight bound fields like any other |
| Reviewer critique on a candidate | Reviewer adapter `FR-P7-01` |
| Sandbox and tool permissions | `FR-M9-03`, `FR-M9-05` — a harness executes inside them, never around them |
| Blast-radius classification | `FR-P2-03` |
| Shadow comparison | `FR-M25-07` |
| Kill switch | `FR-M12-14` |
| Portability | `FR-M31-12` — a harness travels in the adapter's `learned/` |
| Distillation and reclassification | `FR-M14-15`, `FR-M33-06`, `FR-M33-10` |

**New code is confined to:** the harness schema and validator, the module registry, the retrieval index, the synthesis adapter, and one screen.

---

## 1. Build Principles

`E1`–`E14` and `G1`–`G7` remain in force. These are added.

| # | Principle | Consequence |
|---|---|---|
| **J-P1** | **Record before you generate.** Harness provenance ships before harness synthesis. If synthesis is never built, provenance still pays. | J1 precedes J3, always |
| **J-P2** | **Retrieval is the default path; synthesis is the exception.** The archive is consulted first, every time, and a synthesis event is a recorded exception with a reason. | `FR-M41-06`, `FR-M41-07` |
| **J-P3** | **The registry is the trust boundary, not the validator.** Validation checks a composition; the registry decides what can exist. Nothing outside it executes, ever. | `SEC-33`, preserves `SEC-26` |
| **J-P4** | **Shadow before live, per action class.** No class is switched to live synthesis on the paper's numbers. It is switched on your corpus, or not at all. | `FR-M41-21`, `AC-44` |
| **J-P5** | **A harness that has never succeeded is a suspect, not a tool.** First use at medium or high blast radius needs a human. Ties in selection break toward the archived harness. | `FR-M41-13`, `FR-M41-15` |
| **J-P6** | **Report the amortisation from day one.** Hit rate, generation count and cost-per-reuse are instrumented in J2, before synthesis exists, so J3's economics are measurable against a baseline rather than asserted. | `FR-M41-08` |

---

## 2. Stack Decisions

| Concern | Decision | Rationale |
|---|---|---|
| **Harness representation** | YAML, schema-validated, digest-pinned. Declarative composition over the module registry. **Never generated source.** | §3 of the requirements; `SEC-26` unchanged |
| **Module registry** | Reviewed product code under `core/harness/registry/`, versioned per module, with a manifest listing every module and its parameters. Adding a module is a release, not a runtime event. | `FR-M41-04`, `SEC-33` |
| **Initial registry contents** | **`D26` — open.** Recommend starting minimal: 2 memory · 2 planning · 2 action · 2 capability. Sixteen compositions is enough to be interesting and small enough to validate rigorously. | `D26` |
| **Archive store** | SQLite table alongside the ledger, plus the YAML files in `learned/harnesses/`. Retrieval index on action class, stack, blast radius and fitted signals. | `NFR-33` |
| **Retrieval scoring** | Deterministic — exact match on action class and stack, then signal distance, then yield. **No model call in the retrieval path.** | `P17`, `J-P2` |
| **Generator** | **`D25` — open.** Options: the released JIT-Agent artifact; an in-house substitute; a frontier model under a constrained synthesis prompt. **Recommend starting with option 3** — it has no external dependency, no licence question, and tests the concept before committing to an artifact. Swap later; `FR-M41-26` makes it configuration. | `D25`, `R33` |
| **Synthesis output** | Constrained decoding or schema-validated JSON against the harness schema, with bounded retry (`FR-M8-14`). A synthesis that will not validate after retry falls back to the class default. | `NFR-34` |
| **Evaluation** | The Trainer's frozen regression suite plus a replay set of prior packets in the same action class, via the Simulation Core. | `FR-M41-13`, reuses `FR-M32-07` |
| **Shadow comparator** | The existing `FR-M25-07` mechanism, extended to compare harnesses rather than agents. | `FR-M41-21` |

---

## 3. Phase Map

| Sub-phase | Name | Requirements | Host | Bet? | Exit |
|---|---|---|---|---|---|
| **J1** | Harness as Artifact | `FR-M41-01`…`05`, `SEC-33` | F3 | No | `AC-41` |
| **J2** | Archive and Retrieval | `FR-M41-06`…`08`, `FR-M41-20`, `NFR-33`, `NFR-35` | F3 late | No | `AC-43` *(baseline)* |
| **J3** | Gated Synthesis | `FR-M41-09`…`15`, `FR-M41-22`…`24`, `FR-M41-26`, `NFR-34`, `SEC-31`, `SEC-32` | F4 | **Yes** | `AC-42`, `AC-44`, `AC-45` |
| **J4** | Evolution, Promotion, Decision | `FR-M41-16`…`19`, `FR-M41-25` | F4 | **Yes** | `AC-43` *(rising hit rate)*, the enable/disable decision per class |

---

## J1 — Harness as Artifact

**Unconditional. Build this even if `D24` says no to synthesis.**

**Goal.** Every agent action in the ledger names the harness that produced it. Every harness — including every hand-written default — is a named, versioned, diffable artifact.

### Tasks

1. **Harness schema** (§3 of the requirements): four modules, fitted-to signals, bounds, digest. JSON Schema plus a Python validator.
2. **Module registry, minimal** (`FR-M41-04`, `D26`): the memory, planning, action and capability implementations that the prebuilt roster already uses, refactored behind a registry interface and versioned. **This is mostly a refactor, not new capability** — the modules exist inside the agents today; J1 gives them names and versions.
3. **Express every prebuilt adapter's default harness in the format** (`FR-M41-05`). Twelve roster adapters, twelve harness files. If an adapter's behaviour cannot be expressed as a four-module composition, that is a finding worth having early.
4. **Harness resolution at packet start** — the runtime resolves the adapter's declared harness, pins its id, version and digest for the packet.
5. **Ledger extension** (`FR-M41-02`): `harness_id`, `harness_version`, `harness_digest` on every entry. Schema migration under `FR-M30-03`.
6. **Storage in `learned/harnesses/`** (`FR-M41-03`) so harnesses travel on export with everything else.
7. **`SEC-33` registry-only loading** — a test that attempts to load a module by filesystem path, URL and inline source, and asserts all three are refused and recorded.
8. **Inspector Trace tab** shows the harness for the selected action, with a link to the harness file.

### Exit criteria
- [ ] **`AC-41`** Every ledger entry for an agent-authored change names a harness id, version and digest, and the harness is retrievable and readable
- [ ] All twelve prebuilt adapters have a declared harness in the schema, and any that could not be expressed are documented as findings
- [ ] `SEC-33` refusal test passes for all three non-registry load paths
- [ ] Exporting an adapter includes its harnesses; importing reconstitutes them
- [ ] Zero new model calls introduced by this sub-phase — asserted in CI

**Duration:** 2–3 weeks, mostly refactoring. **Value if J3 never happens:** a provenance dimension no competitor has.

---

## J2 — Archive and Retrieval

**Still unconditional. The archive is useful with hand-written harnesses alone.**

**Goal.** A packet finds the right existing harness rather than always using the adapter default — and the economics of doing so are instrumented before any synthesis exists.

### Tasks

9. **Archive store** — SQLite table plus the YAML files, with the retrieval index on action class, stack, blast radius and fitted signals.
10. **Deterministic retrieval and scoring** (`FR-M41-06`): exact match, then signal distance, then observed yield. **No model call in this path** (`J-P2`, `P17`).
11. **Fitness threshold and fallback**: below threshold, use the adapter default and record the miss with its reason. In J2 a miss is simply a miss; in J3 it becomes the synthesis trigger.
12. **Archive telemetry** (`FR-M41-08`): hit rate, miss reasons, per-harness yield, and — with no synthesis yet — the **baseline against which J3's amortisation will be measured** (`J-P6`).
13. **Archive hygiene** (`FR-M41-20`): retire from retrieval on retention horizon or yield threshold; never delete; the ledger keeps everything.
14. **Human-authored harness variants**: let an engineer write a second harness for an action class and have retrieval pick between them. **This proves the archive works without any generation at all**, and is the strongest evidence for or against `D24`.
15. **`NFR-33`** retrieval under 200 ms at 10,000 harnesses; **`NFR-35`** retrievable set bounded.

### Exit criteria
- [ ] **`AC-43` baseline** Over ≥50 packets in one action class, hit rate, miss reasons and per-harness yield are reported and reconcile to the ledger
- [ ] A hand-written second harness for one action class is retrieved in preference to the default where it fits, and the choice is recorded
- [ ] `NFR-33` retrieval latency met at 10,000 synthetic harnesses
- [ ] Still zero new model calls — asserted in CI

**Duration:** 2–3 weeks.

**The decision point.** At J2 exit you have real evidence about your own workload: **do task classes repeat often enough for an archive to pay?** If hit rate is low because every packet is genuinely novel, `D24` should say no and J3 should not be built. That answer costs five weeks instead of a quarter.

---

## J3 — Gated Synthesis

**The bet. Gated on `D24`. Shipped behind a flag. Shadow-first.**

**Goal.** When no archived harness fits, a candidate is generated, validated, reviewed, repaired, selected by evaluation and executed inside the existing sandbox — with every step recorded.

### Workstream A — Generator

16. **Close `D25`.** Recommend starting with a frontier model under a constrained synthesis prompt: no external artifact, no licence question, swappable later by configuration (`FR-M41-26`).
17. **Synthesis adapter** — the generator wrapped as an adapter under the existing framework, so it is discovered, validated, tool-scoped, probation-tested and revocable like any other. **The thing that writes harnesses is itself governed by the harness system's own rules.**
18. **Constrained output** — schema-validated JSON, bounded retry, fallback to class default on repeated failure.
19. **Separate synthesis budget** (`FR-M41-09`, `NFR-34`): tokens, calls and wall clock, capped at a configurable fraction of the packet budget (default 15%). Breach falls back; it never escalates.

### Workstream B — The pipeline

20. **GENERATE** — N candidates (default 3) (`FR-M41-09`).
21. **VALIDATE** (`FR-M41-10`) — schema, module whitelist, bounds, and **static analysis for tool requests outside the adapter's permitted set**. This is where `SEC-31` is enforced: a harness cannot escalate.
22. **REVIEW** (`FR-M41-11`) — the Reviewer adapter critiques the candidate harness at high blast radius, critique ledger-recorded.
23. **REPAIR** (`FR-M41-12`) — bounded loop, max 2 iterations, all eight bound fields declared (`FR-M4-02`).
24. **SELECT** (`FR-M41-13`) — scored against the frozen harness regression suite and a replay of similar prior packets via the Simulation Core. **Ties break toward the archived harness** (`J-P5`).
25. **EXECUTE** (`FR-M41-14`) — inside the existing sandbox, with the adapter's existing permissions and budgets.

### Workstream C — Safety

26. **`FR-M41-15` novelty gate** — first use of a never-succeeded harness at medium or high blast radius needs human approval. The Gate Room card shows the harness diff against the class default (`FR-M41-24`).
27. **`FR-M41-23` blast-radius ceiling** — default `medium`. High-blast packets use only human-authored or promoted harnesses.
28. **`FR-M41-22` kill switch** — global, per adapter, per action class, per repository; effective next packet, no restart.
29. **`SEC-32`** — task spec, retrieved harnesses and repository content entering the synthesis prompt pass the injection classifier; a detection forces human approval regardless of blast radius.
30. **`FR-M41-21` shadow mode** — the comparator, extended from `FR-M25-07` to compare harnesses: synthesised proposes, fixed executes, both scored on yield, cost, latency and rejection reasons.

### Exit criteria
- [ ] **`AC-42`** A synthesised harness requesting a tool outside the adapter's permitted set is rejected at VALIDATE, never executed, and recorded
- [ ] **`AC-44`** Shadow comparison runs on the same packets and produces a per-action-class enable/do-not-enable recommendation
- [ ] **`AC-45`** Disabling synthesis by policy takes effect at the next packet without restart
- [ ] Synthesis budget breach falls back to the class default and never escalates (`NFR-34`)
- [ ] An injection detection in synthesis input forces human approval (`SEC-32`)
- [ ] The synthesis adapter itself passes probation and can be revoked
- [ ] **Live synthesis is enabled for zero action classes at J3 exit.** J3 ships the capability; J4 decides whether to use it.

**Duration:** 4–6 weeks. **The pipeline is mostly wiring existing gates to a new artifact; the generator and the validator are the new code.**

---

## J4 — Evolution, Promotion and Decision

**Goal.** Harnesses that work enter the archive, compound, and eventually become the deterministic default — and each action class gets a decision, on evidence.

### Tasks

31. **Outcome feedback into the archive** (`FR-M41-16`) — first-pass yield, rejection rate, cost, latency and rework reasons per harness, from the signals the Trainer already harvests.
32. **Promotion to default** (`FR-M41-17`) — threshold of successful executions with no safety-invariant violation, then the existing Trainer gate: regression suite, monotonic safety invariant, human approval, versioning, one-action rollback.
33. **Reclassification proposal** (`FR-M41-18`) — a promoted default makes its action class proposable for `generative → deterministic`, as a reviewed policy change (`FR-M33-10`).
34. **`trainable: harnesses`** (`FR-M41-19`, `D27`) — declarable per adapter; a frozen adapter never has its harness modified.
35. **Attribution** (`FR-M41-25`, v2) — the harness as a distinguishable factor in `FR-M13-06`.
36. **The per-class decision.** For each action class, using the shadow evidence from J3 and the archive economics from J2: enable live synthesis, keep shadow, or disable.

### Exit criteria
- [ ] **`AC-43` full** Over ≥50 packets in one action class, **hit rate rises and synthesis count falls**, and amortised cost per use is reported and reconciles to the ledger
- [ ] At least one harness is promoted to a class default through the full gate, and rollback is exercised for real
- [ ] At least one action class has a recorded enable / shadow / disable decision backed by its own corpus evidence
- [ ] The LLM-dependency ratio (`FR-M17-10`) for classes with a promoted harness is **lower** than the pre-J3 baseline — or the decision for those classes is disable

**Duration:** 3–4 weeks, plus the corpus time to accumulate 50 packets per class.

---

## 8. Cross-Cutting Workstreams

| Workstream | Cadence | Notes |
|---|---|---|
| **Zero-model-call assertion on the retrieval path** | Every commit from J2 | Retrieval must never call a model (`J-P2`, `P17`) |
| **Registry review** | Every module addition | A registry module is product code under full review (`SEC-33`). Adding one is a release. |
| **Amortisation reporting** | Weekly from J2 | Hit rate, generation count, cost per reuse — the numbers that decide `D24` and each class's fate |
| **Shadow comparison** | Continuous from J3 | Per action class, until a decision is recorded |
| **Harness regression suite** | Every J3+ change | Frozen; a change to it is a reviewed change |
| **Injection testing on synthesis input** | Every commit from J3 | `SEC-32` with adversarial task specs and poisoned archive entries |
| **Escalation testing** | Every commit from J3 | `SEC-31` — candidates that attempt tool, egress, memory-scope or budget escalation, all rejected |

---

## 9. Definition of Done

Inherits the base plans. Adds:

- [ ] **Harness pinned** — anything the capability produces names its harness id, version and digest
- [ ] **Registry-only** — no path exists to execute a module outside the registry (`SEC-33`)
- [ ] **No escalation** — the capability cannot grant a tool, egress, memory scope or budget beyond the adapter manifest (`SEC-31`)
- [ ] **Retrieval-first** — the archive is consulted before synthesis, and the miss reason is recorded
- [ ] **Bounded** — any synthesis declares its own budget and falls back rather than escalating
- [ ] **Diffable** — the harness diff against the class default is available at any gate reviewing that packet's output
- [ ] **Shadow-capable** — the capability can run in shadow against the fixed harness on the same packet
- [ ] **Killable** — policy disables it at the next packet without restart

---

## 10. Sequencing and Host-Phase Interlock

```
F3 (Orchestra)                                    F4 (Learning & portability)
├─ … loop runtime, roster, deterministic engine ─┤
│                                                 │
├─→ J1 Harness as artifact      [2–3 wk] ─────────┤
│      unconditional · provenance value alone     │
│                                                 │
└─→ J2 Archive and retrieval    [2–3 wk] ─────────┤
       unconditional · answers D24 with evidence  │
                                                  │
                          ══ D24 DECISION ══      │
                                                  │
                                                  ├─→ J3 Gated synthesis   [4–6 wk]
                                                  │      the bet · flag · shadow only
                                                  │
                                                  └─→ J4 Evolution & decision [3–4 wk]
                                                         per-class enable / shadow / disable
```

**Hard serial:** J1 → J2 → `D24` → J3 → J4.

**J2's exit is the decision point**, and it arrives roughly five weeks in. That is the cheapest possible place to learn whether your workload repeats enough for any of this to pay.

---

## 11. GUI Interlock

| Sub-phase | Screen work |
|---|---|
| **J1** | 10.16 Inspector — harness on the Trace tab with a link to the file. 10.7 Ledger — harness column and filter. |
| **J2** | **10.52 Harness Bench** *(new)* — archive browser, per-harness yield and economics, hit-rate chart, hand-authored variants, retirement. |
| **J3** | 10.52 extended — candidate comparison, validate/review/repair/select trace, shadow results per action class. 10.6 Gate Room — harness diff against the class default on the card (`FR-M41-24`). |
| **J4** | 10.5 Dojo — harness distillation alongside rule distillation, promotion through the same shelf. 10.31 Routing Observatory — synthesis vs retrieval accounting, and the reclassification proposal. |

**10.52 Harness Bench** is the one new screen. It is Orchestra-tier and follows every rule in `VIGUIX_Final.md` §18 — including banned pattern 30: it does not render below Orchestra, not even as an empty state.

---

## 12. Kill Criteria

| # | Condition | Measured at | Response |
|---|---|---|---|
| **JK1** | Archive hit rate stays below 30% across ≥50 packets in every action class | **J2 exit** | Your workload does not repeat. **`D24` = no.** Ship J1 and J2, stop. Five weeks spent, a quarter saved. |
| **JK2** | More than one prebuilt adapter's behaviour cannot be expressed as a four-module composition | J1 | The protocol does not fit your agents. Stop at provenance-only; do not build the registry out. |
| **JK3** | Shadow comparison shows no action class where synthesis beats the fixed harness | J4 | Do not enable live anywhere. Keep the archive; retire the generator. |
| **JK4** | Synthesis cost never amortises — cost per use is not falling by 50 packets | J4 | Disable. `NFR-34` bounded the damage. |
| **JK5** | A synthesised harness causes a production incident traceable to composition rather than model output | any | Immediate kill switch, blast-radius ceiling to `low`, full post-mortem before re-enabling |
| **JK6** | The generator dependency (`D25`) becomes unavailable, unlicensable or unsafe | any | Retrieval degrades to the class default, not to failure (`R33`). The archive keeps working. |

---

## 13. Slip Plan

| Order | Cut | Cost |
|---|---|---|
| 1 | `FR-M41-25` harness attribution (v2 anyway) | None |
| 2 | J4 promotion and reclassification — keep the archive, drop the automatic default-promotion | Harnesses stop compounding into determinism; hand-promote instead |
| 3 | J3 entirely | **The `D24` = no outcome. J1 and J2 still ship and still pay.** |
| 4 | J2 archive — keep J1 provenance only | Loses retrieval, keeps "which harness produced this line" |
| 5 | Nothing further | J1 is the floor; below it there is no reason to have started |

**Never cut:** `SEC-31` no-escalation · `SEC-33` registry-only · `FR-M41-15` novelty gate · `FR-M41-22` kill switch · `FR-M41-23` blast-radius ceiling · `FR-M41-21` shadow-first. Every one is what makes generated harnesses safe enough to exist in this product.

---

## 14. Decision Schedule

| # | Decision | Must close by |
|---|---|---|
| **`D26`** | Module registry initial contents — recommend 2 memory · 2 planning · 2 action · 2 capability | **J1 start** |
| **`D24`** | **Adopt synthesis, or stop at artifact and archive** — decided on J2's own-corpus hit-rate evidence, not on the paper | **J2 exit** |
| **`D25`** | The generator — released artifact, in-house substitute, or frontier model under a constrained prompt. Recommend the third to start. | **J3 start** |
| **`D27`** | Whether harnesses are a `trainable:` surface by default for prebuilt adapters | **J4** |

---

## 15. Traceability Appendix

### Requirements to sub-phases

| Sub-phase | Requirements |
|---|---|
| **J1** | FR-M41-01, 02, 03, 04, 05 · SEC-33 |
| **J2** | FR-M41-06, 07, 08, 20 · NFR-33, NFR-35 |
| **J3** | FR-M41-09, 10, 11, 12, 13, 14, 15, 21, 22, 23, 24, 26 · NFR-34 · SEC-31, SEC-32 |
| **J4** | FR-M41-16, 17, 18, 19 · FR-M41-25 *(v2)* |

### Acceptance criteria

| AC | Sub-phase |
|---|---|
| AC-41 harness pinned to every entry | **J1** |
| AC-42 escalation rejected at VALIDATE | **J3** |
| AC-43 hit rate rises, synthesis falls, cost amortises | **J2** baseline · **J4** full |
| AC-44 shadow comparison supports a per-class decision | **J3** |
| AC-45 kill switch effective next packet | **J3** |

### Risks

| Risk | Retired or controlled in |
|---|---|
| R31 gains do not transfer to brownfield | **J4** — shadow evidence on your own corpus |
| R32 harness failure hard to diagnose | **J1** — harness pinned to every entry; **J3** — diff at every gate |
| R33 generator dependency | **J3** — pinned, swappable; archive survives its removal |
| R34 cost never amortises | **J2** — baseline instrumented before synthesis exists; **J4** — decision |

### Host-phase placement

| Sub-phase | `gaps_implementation.md` | `Requirements-implementation.md` |
|---|---|---|
| J1, J2 | **F3** | **C3** |
| J3, J4 | **F4** | **C4** |

---

*End of plan. J2's exit is the decision point. Build to reach it in five weeks, not to reach synthesis.*
