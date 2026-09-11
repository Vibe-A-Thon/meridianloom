---
kind: "skill"
id: "java-fullstack"
name: "Java Full Stack"
description: "A Java backend and its browser client, kept in one contract."
version: "1.0.0"
tags: ["java", "fullstack", "spring", "frontend"]
---

# Java Full Stack

A Tier L3 Stack skill pack (`vision.md` 2.4). Bind it to the Developer or Frontend agent and that agent becomes this specialist — the identity is data, not code.

## Project layout

`backend/` and `frontend/` as sibling modules with a single generated API client; the contract lives in one place, not two.

## Build and test

`./gradlew build` · `npm --prefix frontend ci && npm --prefix frontend run build` · `./gradlew test` · `npm --prefix frontend test`

## Coding standards and framework idioms

- Generate the client from the API schema. A hand-written client is a
  second contract that silently drifts from the first.
- The backend owns validation. Client-side validation is a convenience for the
  user, never a control.
- Version the contract, and treat adding a required field as breaking.
- Keep error shapes stable and machine-readable; the client must not match on
  prose.
- Serve the built frontend as static assets or from a CDN — never compile it
  inside the request path.

## Review checklist

- Was the client regenerated after the schema changed?
- Does a validation rule exist only on the client?
- Does the error path render something a user can act on?

## House rules

Add your organisation's own conventions here. This section is the reason a skill pack is editable: the rest is general practice, and this is what makes it yours.
