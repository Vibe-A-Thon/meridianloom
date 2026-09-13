# First value — protocol

`MV5`, `MVP-R5.3` (`FR-M46-04`, `NFR-28`).

> In five independent onboarding sessions, at least four users SHALL obtain a
> first provenance answer within 15 minutes. In ten review tasks, at least eight
> users SHALL correctly identify the real blocking risk.

This extends [`../cold-start/PROTOCOL.md`](../cold-start/PROTOCOL.md), which is
one stranger timed once. This is five strangers timed on the first answer, and
ten review tasks with an answer key fixed in advance. **Nobody on the project can
be a participant.**

## Participants

- Five people, each of whom has used VS Code, has not read this repository or its
  plans, and is not a member of the project.
- Record each by role and a pseudonym (`p-1` … `p-5`), never by name. The study
  record refuses an `@`.
- Sessions are independent: one participant at a time, no sharing of notes
  between sessions.

## Part 1 — five onboarding sessions

**Given**, and nothing else: the VSIX and its `.sha256`, `DEMO.md`,
`docs/DEPLOYMENT.md`, `docs/SECURITY-AND-DATA.md`, and a git repository with a
few commits, some of them made by an AI agent the participant already uses.

**No model credential is provided or needed** (`NFR-28`).

**Task.** "Install Meridian Loom and find out which agent changed a line you
choose in this repository."

**Timing.** Start when they open the VSIX folder. Stop at the **first provenance
answer**: attribution shown for a real changed line. Record minutes, or `null` if
they did not reach it. The observer may say only "please say what you are
thinking" and "use the documents". Every question asked goes in the cold-start
protocol's defect table and is fixed before release.

## Part 2 — ten review tasks

**Prepare before any session**, and commit the answer key before the first one:

- Ten pull requests from the pilot repository or a prepared corpus. Each has
  **exactly one real blocking risk** known to the preparer and written in the
  answer key, plus plausible distractions that are not blocking.
- The preparer does not observe the sessions.

**Task.** "Using Meridian, decide whether this change should merge. If not, what
is the blocking risk?" The participant uses the pull-request evidence card and
the governance surfaces.

**Scoring.** An observer compares the participant's answer with the committed key.
Record `identifiedRealBlockingRisk: true` only if they named the risk in the key.
A correct refusal to merge for the wrong reason is `false`.

## Recording

Record both parts in a study record's `firstValue` section:

```json
"firstValue": {
  "sessions": [{ "participant": "p-1", "minutesToFirstAnswer": 11.5 }],
  "reviewTasks": [{ "participant": "p-2", "identifiedRealBlockingRisk": true }]
}
```

If this runs before the three-arm study, use a record of its own, registered in
the same way with an empty `allocation`, and score it:

```console
python -m meridian_core.cli evidence-gate --workspace <any workspace> \
    --study first-value.json --signing-key-file ledger.key --out <dir>
```

The report's `firstValue` section applies the requirement exactly. Anything other
than five sessions or ten tasks is `unmeasured`, not a smaller pass. The gate's
own outcome will be `insufficient_evidence`, because no study was run, and that
is correct.

## Where the result goes

`docs/baselines/first-value/<date>/`, containing the record, the report, the
answer key's commit hash and the defect table. Then update `MVP-R5.3` in
`mvp-req-final.md` and `MV5` in `mvp-impl-plan.md`.
