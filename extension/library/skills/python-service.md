---
kind: skill
id: python-service
name: Python Service Conventions
description: Typing, error discipline and resource handling for Python services.
version: 1.0.0
tags: [python, backend]
---

# Python Service Conventions

## Typing

- `from __future__ import annotations` at the top of every module.
- Annotate public functions fully. Internal helpers where it clarifies.
- Prefer a dataclass over a dict for anything with a fixed shape. A dict with
  known keys is a class that has not been written yet.

## Errors

- Define module-level exception types; do not raise bare `Exception`.
- Catch narrowly. `except Exception:` needs a comment explaining what is being
  absorbed and why continuing is correct.
- Never `except: pass`. If the failure genuinely does not matter, say so in a
  comment — the reader cannot tell the difference between deliberate and
  forgotten.

## Resources

- Context managers for files, connections, locks, subprocesses. Always.
- Every `subprocess` call gets a timeout and an explicit `stdin`. A process
  that inherits stdin can block forever waiting for a human who is not there.
- Bound anything that reads until exhaustion: query results, file reads,
  accumulating lists. "It will not get that big" is a prediction, not a limit.

## Standard library first

Reach for a dependency when the standard library genuinely cannot do it. Each
dependency is a supply chain, a licence, and an upgrade you will owe later.
