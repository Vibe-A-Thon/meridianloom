---
kind: "skill"
id: "sql-migration"
name: "SQL Migrations"
description: "Schema change that survives production data volumes."
version: "1.0.0"
tags: ["sql", "database", "migrations"]
---

# SQL Migrations

A Tier L3 Stack skill pack (`vision.md` 2.4). Bind it to the Developer or Frontend agent and that agent becomes this specialist — the identity is data, not code.

## Project layout

Sequentially numbered, immutable migration files; never edit one that has been applied anywhere.

## Build and test

The project's migration runner, applied forward in CI against a production-shaped copy.

## Coding standards and framework idioms

- Forwards-compatible first: add the column, backfill, switch reads, then
  remove the old one. Four deploys, no downtime, each reversible.
- Never rename or drop in the same release that stops using it — a rollback
  then has nowhere to go.
- Backfill in bounded batches. A single `UPDATE` over a large table holds
  locks for as long as it takes.
- Add indexes concurrently where the engine supports it.
- Parameterise every query; know which index each hot-path query uses, and
  read the plan if you cannot name it.
- `SELECT` the columns you use — `SELECT *` breaks silently when the schema
  changes.
- Keep transactions short, and never hold one across a network call.

## Review checklist

- Was this tested against production-like volume, or an empty table?
- Is there a way back from this migration?
- Does any statement lock a large table for an unbounded time?

## House rules

Add your organisation's own conventions here. This section is the reason a skill pack is editable: the rest is general practice, and this is what makes it yours.
