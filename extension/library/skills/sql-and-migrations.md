---
kind: skill
id: sql-and-migrations
name: SQL and Schema Migrations
description: Query and migration practice that survives production data volumes.
version: 1.0.0
tags: [sql, database, migrations]
---

# SQL and Schema Migrations

## Queries

- Parameterise. Every time. String interpolation into SQL is the oldest
  vulnerability still shipping.
- `SELECT` the columns you use. `SELECT *` breaks silently when the schema
  changes and carries data you did not intend to read.
- Know which index each query in a hot path uses. If you cannot name it, read
  the plan.
- `LIMIT` anything that could grow. A query that is fast on your machine is a
  statement about your data volume, not the query.

## Migrations

- Forwards-compatible first: add the column, backfill, switch reads, then
  remove the old one. Four deploys, no downtime, each reversible.
- Never rename or drop in the same release that stops using it. A rollback
  then has nowhere to go.
- Backfill in batches with a bound. A single `UPDATE` over a large table takes
  locks for as long as it takes.
- Every migration is tested against a copy with production-like volume.
  Migrations that are instant on an empty table are the classic outage.

## Transactions

- Keep them short, and never hold one across a network call.
- Be explicit about isolation when the default is not what you mean.
