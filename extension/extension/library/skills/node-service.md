---
kind: "skill"
id: "node-service"
name: "Node Service"
description: "TypeScript Node services: strictness, async safety, boundaries."
version: "1.0.0"
tags: ["node", "typescript", "backend"]
---

# Node Service

A Tier L3 Stack skill pack (`vision.md` 2.4). Bind it to the Developer or Frontend agent and that agent becomes this specialist — the identity is data, not code.

## Project layout

`src/` by domain with `test/` alongside; one entry point that wires dependencies and nothing else.

## Build and test

`npm ci` · `npm run build` · `npm test` · `npm run lint`

## Coding standards and framework idioms

- `strict` is on and stays on. A new `any` needs a comment saying why.
- `unknown` at every boundary — parsed JSON, request bodies, config — narrowed
  explicitly. An `as` at a boundary is an assertion about data you do not
  control.
- `await` every promise or mark it `void` with a reason. A floating rejection
  becomes an unhandled rejection, which can take the process down.
- Every outbound call has a timeout and an abort signal.
- Validate at the edge once and trust inward; validating everywhere means
  validating nowhere consistently.
- Never block the event loop: no synchronous filesystem or crypto work in a
  request path.

## Review checklist

- Is any promise unawaited and unmarked?
- Does every outbound call have a timeout?
- Is anything CPU-bound running on the event loop?

## House rules

Add your organisation's own conventions here. This section is the reason a skill pack is editable: the rest is general practice, and this is what makes it yours.
