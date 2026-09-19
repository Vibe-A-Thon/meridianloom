# Meridian Loom — Harness Intelligence (JIT-Agent Incorporation)

| | |
|---|---|
| **Document** | jit-requirements.md |
| **Version** | 1.0 — proposed, for review |
| **Author** | Ravaleedhar Reddy |
| **Source concept** | **JIT-Agent: Scaling Harness Intelligence via Just-in-Time Harness Evolution.** Guibin Zhang, Leo Lu, Fangzhou Xie, Kang Zhu, Junhao Wang, Zhifei Xie, Zhaochen Yu, Zihang Liu, Zhongxiang Sun, Qiankun Li, Yue Liao, Heng Chang, Xiaobin Hu, Qibing Ren, Wangchunshu Zhou, Shuicheng Yan. arXiv:2608.25593, 26 Aug 2026. Repository: `github.com/bingreeky/JIT` |
| **Complements** | `Requirements_Final.md` v2.1 · `gaps-requirements.md` · `gaps_initiation.md` |
| **Answer to "can we incorporate it?"** | **Yes — but inverted. Not "generate a harness for every task." Generate once, govern it, cache it, reuse it, and let the archive drive the model-call count *down* over time.** |

---

## 0. Verification and honest caveats

I checked the paper before building on it, because the concept reached you through an AI-content reel.

**The paper is real and the numbers in the reel are accurate.** The abstract states that with JIT-Agent as a harness helper, DeepSeek-V4-Flash surpasses GPT-5.6 on DeepSearchQA (+9.1) and OdysseyBench (+4.3), and GLM-5.2 gains up to +20.2 points. It formalises the harness as a composable, machine-generatable artifact under a **fixed four-module protocol** — memory, planning, action, and tool/skill capability orchestration — and trains a compact meta-agent to customise, repair, and self-evolve harnesses from an expanding archive.

**Five caveats you must carry into any decision.**

1. **One paper, one group, two weeks old.** Not replicated. The same team's prior work (MemEvolve for memory, TodoEvolve for planning) is a coherent progression, which is encouraging, but it is still a single line of research.
2. **The benchmarks are not your domain.** DeepSearchQA is research and search; OdysseyBench is general agent tasks. **Neither is enterprise brownfield code modification** — which, per `HONEST_ASSESSMENT.md` BT-5, is where agents already gain only ~10%. Harness gains on deep research may not transfer to a Java service with 400 tests and eleven years of history.
3. **JIT-Agent is a *trained model*, not a prompting pattern.** Adopting it means depending on their released artifact or training a substitute. That is a material dependency with its own lifecycle, licence and security questions.
4. **Generated harnesses are executable.** `SEC-26` in your specification is explicit: `learned/` contains only declarative data, and the engine refuses to load executable content from it. This is a direct conflict and §3 resolves it rather than glossing it.
5. **It appears to add model calls, which contradicts `P17`.** §2 shows why it does the opposite once an archive exists — but only once an archive exists. Before that it is pure cost.

**Recommendation up front:** incorporate the *concept* now as an architectural capability, ship it behind a flag, and do not enable it by default until it is measured on your own corpus in shadow mode against your fixed harnesses.

---

## 1. Why this fits Meridian Loom better than it fits anyone else

Three of the paper's mechanisms are already in your specification under different names.

| JIT-Agent | Meridian Loom already has | Consequence |
|---|---|---|
| `GENERATE → VALIDATE → REVIEW → REPAIR → SELECT → EXECUTE` | The gate and loop model: candidate generation, regression evaluation, reviewer critique, bounded rework loops, promotion gates, rollback (`FR-M14-03`…`08`) | **The pipeline is your loop model applied to the harness instead of the code.** You do not need to build it; you need to point it at a new artifact. |
| Harness archive with distillation from performance signals; Streaming JIT retrieving and updating across tasks | Trainer distillation into `learned/rules/` so an action class moves from generative to deterministic (`FR-M14-15`, `FR-M33-06`) | **The archive is your rules cache.** Streaming JIT is your compounding learning loop with a different payload. |
| Harness determines capability more than the model does | `M33` Deterministic Engine, `P17` Python first / model last, the LLM-dependency ratio as a KPI (`FR-M17-10`) | You already believe the wrapper decides the outcome. This is the same claim, formalised. |

And one thing **only you** can offer:

> A generated, executable harness that no human reviewed, running against a production repository, is exactly what should terrify a CMMI-L5 organisation. Meridian has the sandbox, the tool-permission check, the ledger, the gates, the probation model and the blast-radius classifier. **Nobody else can ship JIT harness synthesis with an audit trail proving which harness produced which line of code.**

That is the incorporation's real value. Not the +20.2.

---

## 2. The inversion — why this *reduces* model dependency

The naive read is that JIT adds a generation call before every task, so `P17` is violated. The archive changes the arithmetic.

```
Naive JIT           task 1: generate  task 2: generate  task 3: generate   →  N generations
Meridian JIT        task 1: generate  task 2: retrieve  task 3: retrieve   →  1 generation, N−1 cache hits
                              ↓
                    distil into the archive; after k successes,
                    promote to the default harness for that action class
                              ↓
                    task k+1…: deterministic selection, zero generation calls
```

**Generate once, reuse many, then promote to deterministic.** After promotion, the action class moves from `generative` to `deterministic` in the action-class catalogue (§7.10), the LLM-dependency ratio falls, and `FR-M33-07` reports the saving.

This is exactly what `FR-M14-15` already asks the Trainer to do with rules. Harnesses are a second, richer payload for the same machinery.

**The honest condition:** this only works if task classes repeat. In an IT-services organisation working the same stacks and the same clients, they do. In a lab doing novel research every day, they do not — which is why the paper's own Streaming-vs-Static distinction matters.

---

## 3. Resolving the executable-code conflict

`SEC-26` forbids executable content in `learned/`. A generated harness is executable. The resolution is not to relax `SEC-26`; it is to constrain what a harness may be.

**A Meridian harness is a declarative composition over a whitelisted module registry, not free-form code.**

```yaml
# learned/harnesses/java-brownfield-defect-v3.yaml
harness:
  id: java-brownfield-defect
  version: 3
  protocol: jit/4-module              # memory · planning · action · capability
  generated_by: jit-synth@1.2.0       # or 'human' or 'distilled'
  digest: sha256:7f21…
  fitted_to:
    action_classes: [implement, unit_test]
    stack: java-spring-gradle
    blast_radius: [low, medium]
    signals: { brownfield: true, coverage_below: 0.4 }

  memory:
    module: registry://memory/fact-graph      # whitelisted, versioned
    params: { retain: 40, decay: none, scope: packet }
  planning:
    module: registry://planning/dependency-first
    params: { max_depth: 3, replan_on: [test_failure] }
  action:
    module: registry://action/serial-react
    params: { max_iterations: 3, repair_on: [compile_error, test_failure] }
  capability:
    module: registry://capability/delegated-subagent
    params: { delegate_to: [qa-adapter], isolate_memory: true }

  bounds: { tokens: 300000, cost_usd: 4.00, model_calls: 12 }
```

**Five properties this buys:**

1. **No arbitrary code is generated or loaded.** Synthesis selects and parameterises modules from a registry whose implementations were written, reviewed and shipped by you. This matches the paper's own position — it generates *structured executable modules*, not unconstrained agent programs.
2. **`SEC-26` survives intact.** `learned/harnesses/` holds YAML validated against a schema. The executable part lives in the module registry, which is versioned code under the same review as the rest of the product.
3. **It is diffable, reviewable and gate-able.** A human can read a harness in ten seconds and see what changed between v2 and v3.
4. **It is deterministic to execute.** The same harness id and digest produces the same composition, so `FR-M33-08` replay-identity and `FR-M27-02` cassette replay both hold.
5. **It is portable.** A harness travels in the adapter's `learned/` like everything else (`FR-M31-12`), so a harness that learned your Java conventions moves to the next team with the agent.

**The cost of this constraint:** you lose the paper's most exotic outputs — genuinely novel control structures that no registry module anticipates. **Accept that loss.** Novel control flow generated at runtime against a production repository is not a capability an IT-services organisation should want.

---

## 4. New design principle

| # | Principle | Consequence |
|---|---|---|
| **P25** | **The harness is an artifact, not an implementation detail.** | Every run records which harness produced it, at which version and digest. A harness is generated, validated, reviewed, selected, cached and promoted through the same gates as any other agent output — and a harness that has never been reviewed never executes at high blast radius. |

---

## 5. New module — M41 Harness Intelligence

*Learning.* Add to `Requirements_Final.md` §5 after M40.

### 5.1 Harness as artifact

| ID | Requirement | Priority |
|---|---|---|
| FR-M41-01 | A **harness** SHALL be a first-class, versioned, digest-pinned artifact conforming to the four-module protocol — memory, planning, action, capability — declaratively composed over a whitelisted module registry (§3). Free-form generated code SHALL NOT be a harness. | MUST v1.x |
| FR-M41-02 | Every ledger entry SHALL record the **harness id, version and digest** that produced the action, alongside the existing agent, skill, model and policy versions (`FR-M10-10` extended). | MUST v1.x |
| FR-M41-03 | Harnesses SHALL live in the adapter's `learned/harnesses/` and SHALL travel with the adapter on export (`FR-M31-12`), so learned harness intelligence is portable. | MUST v1.x |
| FR-M41-04 | A **module registry** of memory, planning, action and capability implementations SHALL be maintained as reviewed, versioned product code. Only registry modules may appear in a harness. Adding a module is a product change, not a runtime event. | MUST v1.x |
| FR-M41-05 | **Fixed harnesses are harnesses too.** Every prebuilt adapter SHALL declare its default harness in the same format, so that provenance, diffing and comparison work identically whether the harness was authored, distilled, or synthesised. | MUST v1.x |

### 5.2 Retrieval before synthesis

| ID | Requirement | Priority |
|---|---|---|
| FR-M41-06 | On every packet, the runtime SHALL **retrieve** from the harness archive before considering synthesis, matching on action class, stack, blast radius, and the fitted signals in §3. | MUST v1.x |
| FR-M41-07 | Synthesis SHALL be attempted **only** when no archived harness scores above a configurable fitness threshold, and only when policy permits synthesis for that action class. Every synthesis event and every retrieval hit SHALL be ledger-recorded with the reason. | MUST v1.x |
| FR-M41-08 | The archive SHALL report **hit rate, generation count, and amortised generation cost per reuse**, feeding `FR-M17-10` and `FR-M33-07`. The expected trend is generations falling and hit rate rising; a rising generation count is a defect signal. | MUST v1.x |

### 5.3 The synthesis pipeline, mapped to existing gates

| ID | Requirement | Priority |
|---|---|---|
| FR-M41-09 | **GENERATE.** Synthesis SHALL produce N candidate harnesses (default 3, configurable), each a valid composition under §3, bounded by a synthesis budget (tokens, calls, wall clock) that is separate from and additional to the packet budget. | MUST v1.x |
| FR-M41-10 | **VALIDATE.** Each candidate SHALL be schema-validated, module-whitelist-checked, bounds-checked, and statically analysed for tool requests outside the adapter's permitted set (`FR-M9-03`). A candidate failing validation SHALL be discarded or sent to repair, never executed. | MUST v1.x |
| FR-M41-11 | **REVIEW.** For high-blast-radius packets, a **Reviewer adapter SHALL critique the candidate harness** before selection, as it critiques code (`FR-P7-01`). Its critique is ledger-recorded. | MUST v1.x |
| FR-M41-12 | **REPAIR.** A failed candidate MAY be repaired within a bounded loop (default max 2 iterations) using the validation or review failure as feedback. The repair loop SHALL declare all eight bound fields like any other loop (`FR-M4-02`). | MUST v1.x |
| FR-M41-13 | **SELECT.** Selection SHALL be by evaluation, not by model preference: candidates are scored against the frozen harness regression suite and, where available, a replay of similar prior packets. The scoring is ledger-recorded. Ties break toward the archived harness, never toward the novel one. | MUST v1.x |
| FR-M41-14 | **EXECUTE.** The selected harness SHALL execute inside the existing sandbox with the adapter's existing tool permissions and budgets. A harness SHALL NOT be able to grant its agent a capability the adapter's manifest does not declare. | MUST v1.x |
| FR-M41-15 | **Human gate on novelty.** A harness that has never executed successfully SHALL require human approval before its first use at `medium` or `high` blast radius. At `low` blast radius, policy MAY permit first use without approval. | MUST v1.x |

### 5.4 Evolution, distillation and promotion

| ID | Requirement | Priority |
|---|---|---|
| FR-M41-16 | Execution outcomes SHALL update the harness's record in the archive: first-pass yield, rejection rate, cost, latency, and rework reasons — the same signals the Trainer already harvests (`FR-M14-01`). | MUST v1.x |
| FR-M41-17 | **Promotion to default.** When an archived harness achieves a configurable threshold of successful executions for an action class with no safety-invariant violation, the Trainer SHALL propose it as that class's default harness. Promotion follows the existing gate: regression suite, monotonic safety invariant, human approval, versioning, one-action rollback (`FR-M14-04`…`08`). | MUST v1.x |
| FR-M41-18 | **Reclassification.** Once a harness is promoted to default for an action class, that class SHALL be proposable for reclassification from `generative` to `deterministic` in the action-class catalogue — a reviewed policy change, never automatic (`FR-M33-10`). | MUST v1.x |
| FR-M41-19 | The Trainer SHALL treat harnesses as a trainable surface, declarable per adapter in `trainable:` (`FR-M31-08`). An adapter that freezes `harnesses` never has its harness modified. | MUST v1.x |
| FR-M41-20 | **Archive hygiene.** Harnesses unused beyond a retention horizon, or whose yield falls below a threshold, SHALL be retired from retrieval — retained in the ledger and archive, never silently deleted. | SHOULD v1.x |

### 5.5 Safety, comparison and control

| ID | Requirement | Priority |
|---|---|---|
| FR-M41-21 | **Shadow mode first.** Harness synthesis SHALL be runnable in shadow (`FR-M25-07`): the synthesised harness proposes, the fixed harness executes, and the two are compared on yield, cost, latency and rejection reasons. **Synthesis SHALL NOT be enabled live for an action class until shadow comparison shows it wins on that organisation's own corpus.** | MUST v1.x |
| FR-M41-22 | **Kill switch.** Policy SHALL be able to disable harness synthesis globally, per adapter, per action class, or per repository, taking effect at the next packet without restart (`FR-M12-14` extended). | MUST v1.x |
| FR-M41-23 | **Blast-radius ceiling.** Policy SHALL define the maximum blast radius at which a synthesised harness may execute. Default: `medium`. High-blast-radius packets use only human-authored or promoted harnesses. | MUST v1.x |
| FR-M41-24 | **Harness diff view.** Any two harnesses SHALL be diffable, and the diff between a packet's harness and the class default SHALL be shown at any gate where that packet's output is reviewed. | MUST v1.x |
| FR-M41-25 | **Attribution.** Where two packets in the same story used different harnesses, `FR-M13-06` contribution attribution SHALL account for the harness as a factor, so "the harness caused this" is a distinguishable finding from "the model caused this." | SHOULD v2 |
| FR-M41-26 | The synthesis generator itself — whether the JIT-Agent artifact, a substitute, or a general model under a synthesis prompt — SHALL be pinned by version and digest, recorded in every synthesis ledger entry, and swappable by configuration (`D25`). | MUST v1.x |

---

## 6. New data model — §7.12 Harness Record

```json
{
  "harness_id": "java-brownfield-defect",
  "version": 3,
  "digest": "sha256:7f21…",
  "protocol": "jit/4-module",
  "origin": "synthesised",
  "generator": { "id": "jit-synth", "version": "1.2.0", "digest": "sha256:c4a9…" },
  "created_at": "2026-09-04T10:22:11Z",

  "composition": {
    "memory":     { "module": "registry://memory/fact-graph@2.1",        "params": {} },
    "planning":   { "module": "registry://planning/dependency-first@1.4", "params": {} },
    "action":     { "module": "registry://action/serial-react@3.0",       "params": {} },
    "capability": { "module": "registry://capability/delegated-subagent@1.1", "params": {} }
  },

  "fitted_to": {
    "action_classes": ["implement", "unit_test"],
    "stack": "java-spring-gradle",
    "blast_radius": ["low", "medium"],
    "signals": { "brownfield": true, "coverage_below": 0.4 }
  },

  "lifecycle": {
    "state": "archived",
    "first_use_approved_by": "vikram@example.com",
    "executions": 41,
    "first_pass_yield": 0.83,
    "rejection_rate": 0.17,
    "safety_violations": 0,
    "promoted_to_default_for": [],
    "retired": false
  },

  "economics": {
    "synthesis_cost_usd": 0.42,
    "reuses": 40,
    "amortised_cost_per_use_usd": 0.0105,
    "vs_default_harness": { "yield_delta": 0.06, "cost_delta_usd": -0.31 }
  },

  "provenance": { "synthesis_ledger_seq": 5183, "review_ledger_seq": 5184, "selection_ledger_seq": 5185 }
}
```

**Amend `FR-M10-01`'s ledger schema** with `harness_id`, `harness_version` and `harness_digest`.

---

## 7. New non-functional requirements

| ID | Requirement | Priority |
|---|---|---|
| NFR-33 | **Retrieval latency**: archive retrieval SHALL complete in under 200 ms for an archive of 10,000 harnesses. | MUST v1.x |
| NFR-34 | **Synthesis is bounded**: the synthesis budget SHALL never exceed a configurable fraction of the packet budget (default 15%), and a breach SHALL fall back to the class default harness rather than escalating. | MUST v1.x |
| NFR-35 | **Archive growth**: the archive SHALL not grow without bound — hygiene (`FR-M41-20`) SHALL keep the retrievable set below a configurable ceiling (default 5,000) while the ledger retains everything. | SHOULD v1.x |

## 8. New security requirements

| ID | Requirement | Priority |
|---|---|---|
| SEC-31 | **A harness cannot escalate.** A harness SHALL NOT grant tools, egress, memory scope or budget beyond what the executing adapter's manifest and the workspace policy already permit. Validation SHALL reject any composition that attempts it, and the attempt SHALL be ledger-recorded. | MUST v1.x |
| SEC-32 | **Synthesis input is untrusted.** The task specification, retrieved prior harnesses, and any repository content entering the synthesis prompt SHALL pass the injection classifier (`SEC-15`). A harness synthesised from content with a detection SHALL require human approval regardless of blast radius. | MUST v1.x |
| SEC-33 | **The module registry is the trust boundary.** Only registry modules may execute. Loading a module by any other path — a filesystem reference, a URL, generated source — SHALL be refused and ledger-recorded. This preserves `SEC-26` unchanged. | MUST v1.x |

## 9. New acceptance criteria

| # | Criterion |
|---|---|
| **AC-41** | Every ledger entry for an agent-authored change names the harness id, version and digest that produced it, and the harness is retrievable and readable from the archive. |
| **AC-42** | A synthesised harness attempting to request a tool outside the adapter's permitted set is rejected at VALIDATE, never executed, and the attempt is recorded. |
| **AC-43** | Over a corpus of ≥50 packets in one action class, archive hit rate rises and synthesis count falls, and the amortised cost per use is reported and reconciles to the ledger. |
| **AC-44** | With synthesis in shadow mode, the synthesised and fixed harnesses are compared on the same packets, and the comparison is sufficient to make an enable/do-not-enable decision per action class. |
| **AC-45** | Disabling harness synthesis by policy takes effect at the next packet without restart; every subsequent packet uses the class default harness, and the change is recorded. |

## 10. New risks

| # | Risk | Impact | Mitigation |
|---|---|---|---|
| **R31** | **Harness gains do not transfer from research benchmarks to enterprise brownfield code** | High | `FR-M41-21` shadow-first, per action class, on your own corpus. Do not enable on the paper's numbers. |
| **R32** | **A synthesised harness fails in a way that is harder to diagnose than a bad prompt** | High | `FR-M41-02` harness pinned to every entry; `FR-M41-24` diff against the class default at every gate; the harness is a named suspect in every post-mortem |
| **R33** | **Dependency on an external generator artifact** (JIT-Agent model or substitute) | Medium | `FR-M41-26` pinned and swappable by configuration; the archive keeps working if the generator is removed — retrieval degrades to the class default, not to failure |
| **R34** | **Synthesis cost never amortises because task classes do not repeat** | Medium | `FR-M41-08` hit rate and amortised cost are reported from day one; `NFR-34` bounds the spend; `FR-M41-22` kill switch. If hit rate does not rise, disable. |

## 11. New decisions

| # | Decision | Owner | Needed by |
|---|---|---|---|
| **D24** | Whether to adopt harness intelligence at all, or ship fixed harnesses recorded as artifacts (`FR-M41-01`…`05`) and stop there. **The artifact half is worth doing regardless; the synthesis half is the bet.** | Product | Before J2 |
| **D25** | The generator: the released JIT-Agent artifact, a substitute trained in-house, or a general frontier model under a synthesis prompt. Licence, security review and lifecycle differ sharply. | Architecture + Legal | Before J2 |
| **D26** | The module registry's initial contents — which memory, planning, action and capability implementations ship. Too few and synthesis is pointless; too many and validation weakens. | Architecture | Before J2 |
| **D27** | Whether harnesses are a `trainable:` surface by default for prebuilt adapters, or opt-in per adapter | Governance | J3 |

---

## 12. What this changes in existing files

| File | Change | Size |
|---|---|---|
| `Requirements_Final.md` | Add M41 to §5 · §7.12 Harness Record to §7 · `P25` to §3 · `NFR-33`…`35`, `SEC-31`…`33`, `AC-41`…`45`, `R31`…`R34`, `D24`…`D27` · add `harness_id`/`version`/`digest` to the `FR-M10-01` schema · M41 in §4.3 and §17 | ~26 requirements + 1 model |
| `VIGUIX_Final.md` | One new screen, **10.52 Harness Bench** (archive browser, candidate comparison, diff, shadow results, promotion) · amend 10.5 Dojo (harness distillation alongside rule distillation), 10.16 Inspector (harness on the Trace tab), 10.31 Routing Observatory (synthesis vs retrieval accounting), 10.6 Gate Room (harness diff on the card, `FR-M41-24`) | 1 screen + 4 amendments |
| `gaps-requirements.md` | Note that harness intelligence is an Orchestra-tier capability; it does not exist in Flight Recorder or Governor | 1 line |
| Implementation plans | Per `jit-impl.md` | — |
| `vision.md` | Add a paragraph to §8 self-evolution: the harness is the third trainable surface after prompts and rules | 1 paragraph |

**Nothing is renumbered. `SEC-26` is unchanged and unweakened.**

---

## 13. The honest summary

**Take the artifact half unconditionally.** Recording which harness produced which code — even when every harness is fixed and hand-written — costs almost nothing and gives you a provenance dimension no competitor has. `FR-M41-01`…`05` are worth doing on their own merits.

**Treat the synthesis half as a funded experiment, not a feature.** One paper, two weeks old, benchmarked on tasks that are not yours, requiring an external trained model, producing executable artifacts in a product whose entire thesis is governance. Ship it behind a flag, in shadow, per action class, and let your own corpus decide.

**And note what makes it defensible if it works:** every competitor can call the JIT-Agent repository. Only Meridian can execute a synthesised harness inside a sandbox, under tool permissions, gated by blast radius, reviewed by another agent, selected by evaluation rather than preference, recorded in a signed ledger, and diffed against the default at the moment a human is asked to approve the code it produced.

That is the incorporation worth building.
