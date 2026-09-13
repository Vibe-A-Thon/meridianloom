# The evidence gate study — protocol

`MV5`, `MVP-R5.2` (`FR-M46-14`, `FR-M46-15`). Scored against
[`docs/evidence-gate.md`](../../evidence-gate.md).

**No build agent can run this, and nobody can run it alone.** It needs a real
team, twenty real stories from that team's backlog, reviewers who did not run the
gates, and eight weeks. Everything below exists so that when those people exist,
the study produces a result that could come out against the product, and is
published if it does.

## 1. Before the first story: register

1. Read `docs/evidence-gate.md` in full, including §6. Settle the two gaps §6
   names. **Amend anything you want to amend now.** Once the first story is
   measured the document is frozen (§5).
2. Print what you are registering:

   ```console
   python -m meridian_core.cli evidence-gate --print-preregistration
   ```

   `thresholdsDigest` covers the thresholds and the readings together. If either
   changes later, every scoring run reports it.
3. Copy [`study-record.template.json`](study-record.template.json) to
   `docs/baselines/evidence-gate/<date>-<study>/study-record.json`. Fill in
   `studyId`, `preregistration.registeredAt` (now) and
   `preregistration.thresholdsDigest` (from step 2). The template cannot be
   scored as it stands, deliberately.
4. In the same commit, freeze the corpus (the twenty story ids) and the evaluator
   (who adjudicates, and by what method). **Commit before the first story
   starts.** The commit date is the public evidence that registration came
   first. `python -m meridian_core.cli evidence-gate --print-schema` prints
   everything a record may carry.

## 2. Allocation: three arms

| Arm | The team uses | Where its evidence lives |
|---|---|---|
| **A**, baseline | Their own agents under native controls, plus their existing SCM protection and security tooling | The team's own tracker and delivery metrics. No Meridian |
| **B**, recorder | Arm A plus the Flight Recorder tier | A workspace with the Governor disabled; export its slice separately with `cli export` and attach it |
| **C**, governor | Arm B plus the Governor: gates, roles, approval binding, trust analytics | The workspace this protocol scores |

- Existing SCM protection and security tooling are in **every** arm, so only
  the benefit Meridian adds is attributed to Meridian.
- Counterbalance assignment across arms and across greenfield and brownfield
  work. Record each story in `allocation` with its arm and `kind`.
- Record every agent and model version per arm in `configuration`.
- Set `preregistration.firstStoryMeasuredAt` when measurement of the first story
  begins. A registration dated after it invalidates the study.

## 3. During the study: what to record, and who records it

People are recorded **by role or pseudonym**. The record refuses an `@` wherever
a person is named.

| Measure | Section of the record | Recorded by | How |
|---|---|---|---|
| `P1`, `C1` | `adjudications` | A reviewer who **did not run the gate**; blind where practical | One entry per arm C gate stop. `gateSequence` is the gate entry's ledger sequence (Governance Studio, or `cli export`). Was it a real defect? Had the agent's own process already caught it? |
| `P2` | `armA` | The team | Arm A's rejection rate from the team's own tracker, split greenfield/brownfield, counted the way `FR-M37-01` counts it: a proposed change later rejected or reworked. Arm C's figure comes from the ledger |
| `P3` | `baselineChangeFailureRate` | The team | The team's change failure rate before Meridian, with the method. The gated rate comes from the ledger: approved merges later reverted |
| `P4` | `provenanceQueries` | The team, weekly | **Meridian does not count what people read**, by design. Survey or observe queries per engineer per week |
| `P5` | `trustDecisionChanges` | Whoever made the change | An autonomy tier, agent choice or module restriction changed after viewing the Trust Observatory. Give `ledgerSequence` if the change was recorded |
| `P6` | `retention` | Ask them | Of the original five testers, who still uses it at week 8 |
| `C2` | `reviewTime` | An observer | Minutes of human review per gated pull request, **the same method in arms A and C**. Ledger timings appear beside C2 as context and never decide it |
| `C3` | `hygieneDetermination` | A reviewer | Is there systematic rubber-stamping? The ledger's `FR-M20-06` signals are attached to the report as evidence |
| `O1` | `orchestraCase` | The owner, with evidence | A named task class where the team's existing agents underperform, **before** any agent is built |
| — | `acceptedChangeCost`, `regressions30Day` | The team | Required by `FR-M46-14` and published. The rule does not decide on them |
| — | `exclusions` | Whoever excludes | Every excluded story, with the reason. Published |
| `FR-M46-04` | `firstValue` | See [`../first-value/PROTOCOL.md`](../first-value/PROTOCOL.md) | Scored beside the rule, not by it |

## 4. After the twentieth story: score

```console
python -m meridian_core.cli evidence-gate --workspace <arm C workspace> \
    --study docs/baselines/evidence-gate/<date>-<study>/study-record.json \
    --signing-key-file ledger.key \
    --out docs/baselines/evidence-gate/<date>-<study>/ \
    [--from-sequence N --to-sequence M]
```

This writes three files and no decision:

- `evidence-gate-report.json` — every measure as `met`, `not_met` or
  `unmeasured`, with its threshold, source, note, confidence intervals, and the
  outcome §4 returns. An unmeasured threshold is never satisfied, and an outcome
  that depends on one is not reached.
- `ledger-slice.json` — the raw ledger slice as a signed bundle. It verifies
  without Meridian: `python verify.py ledger-slice.json`.
- `DECISION-DRAFT.md` — the computed half of the decision, with both files'
  sha256 digests. The half a person must write is left empty.

Possible outcomes are `go`, `stop`, `pivot`, `kill`, `insufficient_evidence`
(too few stories, no valid record, or an outcome that depends on an unmeasured
threshold) and `unclassified` (a combination §4 names no outcome for).

## 5. Decide, and publish

1. Copy `DECISION-DRAFT.md` to `DECISION.md` and write the decision: the path
   chosen, and **if it departs from the computed outcome, why**. A departure is
   published as a departure, never as a re-reading of the thresholds.
2. Publish the directory as it stands: record, report, slice and decision.
   **Unfavourable results, missing data and exclusions are published with it**
   (`FR-M46-15`). A preregistration reported as not intact is published as
   invalidated.
3. Twenty stories is a feasibility pilot, not a superiority test. Before any
   comparative claim, work out the sample it needs from the variance this pilot
   observed, and write that number in the decision.
4. Record the outcome against `D21` in `DECISIONS.md` and tick `MV5`'s exit in
   `mvp-impl-plan.md`, linking the directory.

**None of the thresholds may be quoted externally as a measurement.** They are
the bar, not the result.
