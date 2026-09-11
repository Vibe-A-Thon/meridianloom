---
kind: "skill"
id: "python-service"
name: "Python Service"
description: "Typing, error discipline and resource handling for Python services."
version: "1.0.0"
tags: ["python", "backend", "fastapi"]
---

# Python Service

A Tier L3 Stack skill pack (`vision.md` 2.4). Bind it to the Developer or Frontend agent and that agent becomes this specialist — the identity is data, not code.

## Project layout

`src/<package>/` with `tests/` alongside; modules by domain, not by technical layer.

## Build and test

`python -m pytest` · `ruff check .` · `mypy src` · `pip install -e '.[dev]'`

## Coding standards and framework idioms

- `from __future__ import annotations` at the top of every module; annotate
  every public function.
- A dataclass over a dict for anything with a fixed shape. A dict with known
  keys is a class that has not been written yet.
- Module-level exception types; never raise bare `Exception`. `except
  Exception:` needs a comment saying what is absorbed and why continuing is
  correct, and `except: pass` never appears.
- Context managers for files, connections, locks and subprocesses — always.
- Every `subprocess` call gets a timeout and an explicit `stdin`. A process
  that inherits stdin can block forever on a prompt nobody will answer.
- Bound anything that reads until exhaustion. "It will not get that big" is a
  prediction, not a limit.
- Standard library first; every dependency is a supply chain and an upgrade
  you will owe.

## Review checklist

- Does every external call have a timeout?
- Is any accumulating structure unbounded?
- Does any `except` silently continue without saying why?

## House rules

Add your organisation's own conventions here. This section is the reason a skill pack is editable: the rest is general practice, and this is what makes it yours.
