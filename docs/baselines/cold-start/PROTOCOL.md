# Cold-start rehearsal — protocol

`MV4-T04`. Feeds `MK1` and `NFR-28` (fifteen minutes to a first provenance
answer).

**Nobody on the project can run this.** The point is a person who has not read
the source and has not seen the plan. Everything below exists so that when such
a person is found, the run produces evidence rather than an impression.

## Who

- Has used VS Code before.
- Has **not** read this repository's source, `mvp-req-final.md`,
  `mvp-impl-plan.md`, or any conversation about them.
- Is not a member of the project.

Record their role (for example "backend engineer, 6 years"), never their name.

## What they are given

Exactly these, and nothing else:

1. `meridian-loom-<version>.vsix` and its `.sha256`, from a release build.
2. `DEMO.md`.
3. `docs/DEPLOYMENT.md`.
4. `docs/SECURITY-AND-DATA.md`.
5. A git repository with a few commits in it that they may modify.

No verbal walkthrough. No answering "what should I click". The observer's only
permitted words are "please say what you are thinking" and "use the documents".

## The task

> Starting from the VSIX, install Meridian Loom, record provenance for a change
> in the repository, export an evidence bundle, and verify that bundle with the
> verifier the package ships. Stop when the verifier reports success.

## What to time

Start the clock when they open the VSIX folder. Record the wall-clock time at
each of these, or `not reached`:

| Milestone | Time | Notes |
| --- | --- | --- |
| Checksum compared | | |
| Extension installed | | |
| Sidecar healthy (Doctor green or understood) | | |
| **First provenance answer** — any attribution shown for a real change (`NFR-28`: ≤ 15 min) | | |
| Evidence bundle exported | | |
| Bundle verified with the shipped verifier | | |

## What to record — this is the evidence

Every time they **ask a question, stop for more than 60 seconds, or go outside
the four documents**, write one row. Each row is a defect in the documents, not
in the person.

| # | Time | What they were trying to do | What they asked or did | Which document should have answered it | Fixed in commit |
| --- | --- | --- | --- | --- | --- |
| 1 | | | | | |

A run with zero rows is suspicious before it is good news: check the observer
did not help.

## Pass condition

- The bundle verified, unaided.
- First provenance answer within 15 minutes, or the overrun recorded with the
  step that consumed it.
- **Every row above fixed before release**, each with the commit that fixed it.

## Where the result goes

`docs/baselines/cold-start/<date>-<role>.md`, containing the filled tables, the
package digest used, and the operating system. Then update `MV4-T04`'s exit
criterion in `mvp-impl-plan.md` with the time.
