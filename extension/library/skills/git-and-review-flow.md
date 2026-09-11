---
kind: skill
id: git-and-review-flow
name: Git and Review Flow
description: Commit, branch and pull request practice that keeps history readable.
version: 1.0.0
tags: [git, workflow, review]
---

# Git and Review Flow

## Commits

- One logical change per commit. A commit that does two things cannot be
  reverted for one of them.
- The subject line says what changed and why it matters, in the imperative.
  Not "fixes" — what was broken.
- The body says why, and what you considered and rejected. The diff already
  says what.
- Never mix a refactor and a behaviour change. The reviewer cannot see the
  behaviour change inside the noise, so they will not.

## Branches

- Branch from the default branch, short-lived. A long branch is a merge
  conflict compounding daily.
- Rebase your own unpushed work to keep history linear; never rebase what
  others have pulled.

## Pull requests

- Small enough to be read properly. A 2000-line PR gets approved, not
  reviewed.
- The description says what changed, why, what you tested, and what you did
  not test.
- Reply to every review comment — including to disagree, with a reason.
- Never merge with a failing check by explaining why the failure is unrelated.
  Make it pass or make it not run.
