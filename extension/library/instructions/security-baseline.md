---
kind: "instruction"
id: "security-baseline"
name: "Security Baseline"
description: "The non-negotiable security rules for work in this workspace."
scope: "organisation"
---

# Security Baseline

## Secrets

- Credentials go to the OS keychain or a secret manager. Never to a file in
  the workspace, never to an export, never to a log, never into a process
  argument list — argument lists are readable by other processes.
- Never echo a secret back, not even masked. A mask still leaks the length.
- If the secure store is unavailable, refuse the operation. Do not fall back
  to something less safe because it is more convenient.
- Redact before display and before storage, not only before display.

## Input

- Everything from outside the process is untrusted: request bodies, files,
  archive members, database rows that may have come from a restored backup,
  and any text produced by a model.
- Validate against an allow-list of the shape you expect. A blacklist of known
  escapes is a list of the ones you thought of.
- Anything that becomes a filesystem path is validated for containment, after
  resolution, not before.
- Anything that becomes a query, a command line, or a template is
  parameterised, never concatenated.

## Limits

- Every external call has a timeout.
- Every read that could be large has a ceiling, and says when it hits it
  rather than silently truncating.
- Every accumulating structure has a bound and a policy for what happens at
  the bound.

## Least privilege

- Start from the smallest permission set that does anything observable, and
  widen deliberately.
- An imported or shipped agent never arrives with write, execute or delete.
