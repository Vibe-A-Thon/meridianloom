---
kind: "skill"
id: "api-contract-first"
name: "API Contract First"
description: "The schema is the contract; everything else is generated from it."
version: "1.0.0"
tags: ["api", "rest", "openapi", "contracts"]
---

# API Contract First

A Tier L3 Stack skill pack (`vision.md` 2.4). Bind it to the Developer or Frontend agent and that agent becomes this specialist — the identity is data, not code.

## Project layout

The schema lives in one versioned location; server stubs, clients and documentation are all generated from it.

## Build and test

Lint the schema, generate, then build — a build that can run without the generated artefacts being current is a build that hides drift.

## Coding standards and framework idioms

- The contract is the schema, not the documentation. Generate the docs so
  they cannot drift.
- Adding an optional field is compatible. Removing one, renaming one,
  narrowing a type, or making an optional field required is not.
- Clients must ignore unknown fields, and the contract must say so.
- Pagination on every collection from the first version. Adding it later
  breaks every client that assumed a full list.
- The status code carries the class; the body carries the detail. A `200` with
  an error inside forces every client to parse the body to know what happened.
- Stable, machine-readable error codes. Never leak internal detail in an error.
- Idempotency keys on anything that creates or charges.

## Review checklist

- Is this change compatible, and if not, is the version bumped?
- Were the generated clients regenerated?
- Does every collection endpoint paginate?

## House rules

Add your organisation's own conventions here. This section is the reason a skill pack is editable: the rest is general practice, and this is what makes it yours.
