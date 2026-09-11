---
kind: skill
id: typescript-service
name: TypeScript Service Conventions
description: Strictness, error handling and module boundaries for TypeScript services.
version: 1.0.0
tags: [typescript, node, backend]
---

# TypeScript Service Conventions

## Types

- `strict` is on and stays on. A new `any` needs a comment saying why.
- Prefer `unknown` at every boundary — parsed JSON, RPC params, config — and
  narrow explicitly. `as` at a boundary is a type assertion about data you do
  not control, which is a lie the compiler cannot catch.
- Model absence with a union (`T | undefined`), not with a sentinel.
- Discriminated unions over optional-field grab bags.

## Errors

- Throw `Error` subclasses with a message that names the thing that failed and
  what the caller can do. "Invalid input" helps nobody.
- Never swallow. If you catch and continue, the catch block says why in a
  comment.
- `await` every promise or explicitly mark it `void` with a reason. A floating
  rejection becomes an unhandled rejection, and in a host process that can
  take the process down.

## Boundaries

- A module exports the smallest surface that its callers need.
- Validate at the edge, once, and trust inward. Validating everywhere means
  validating nowhere consistently.
- No I/O in a module that is otherwise pure — it makes the pure part
  untestable along with it.

## Async

- Cancellation is a parameter, not an afterthought: pass the signal.
- Anything with a network or a subprocess at the end of it gets a timeout.
