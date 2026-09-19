---
kind: "skill"
id: "react-frontend"
name: "React Frontend"
description: "Component structure, state and accessibility for React applications."
version: "1.0.0"
tags: ["react", "frontend", "typescript", "accessibility"]
---

# React Frontend

A Tier L3 Stack skill pack (`vision.md` 2.4). Bind it to the Developer or Frontend agent and that agent becomes this specialist — the identity is data, not code.

## Project layout

Feature folders containing their own components, hooks and tests; shared primitives in one place, not scattered.

## Build and test

`npm ci` · `npm run build` · `npm test` · `npm run lint`

## Coding standards and framework idioms

- Derive state; do not duplicate it. Two sources for one fact will disagree.
- Effects are for synchronising with something outside React, not for
  computing values. Most `useEffect` calls that set state should be a
  computation instead.
- Every list key is a stable id, never an index.
- Loading, empty, error and partial states are part of the component.
- Semantic elements before ARIA; every control has an accessible name; focus
  is visible and ordered; colour is never the only carrier of meaning.
- Never render unsanitised HTML from a source you do not control.
- Memoise when a measurement says to, not on principle.

## Review checklist

- Can every interaction be completed with the keyboard alone?
- Is any piece of state derivable from another?
- Does each async surface handle failure, or only success?

## House rules

Add your organisation's own conventions here. This section is the reason a skill pack is editable: the rest is general practice, and this is what makes it yours.
