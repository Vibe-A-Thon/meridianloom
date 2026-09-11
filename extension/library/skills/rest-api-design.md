---
kind: skill
id: rest-api-design
name: REST API Design
description: Contract, compatibility and error practice for HTTP APIs.
version: 1.0.0
tags: [api, rest, http, contracts]
---

# REST API Design

## Contract

- The contract is the schema, not the documentation. Generate the docs from
  it, so they cannot drift.
- Resources are nouns; the verb is the method. `POST /orders/cancel` is a
  procedure call wearing REST clothing — sometimes right, but call it what it
  is.
- Pagination on every collection, from the first version. Adding it later is
  a breaking change for every client that assumed a full list.

## Compatibility

- Adding an optional field is compatible. Removing one, renaming one,
  narrowing a type, or making an optional field required is not.
- Clients must ignore unknown fields. Say so in the contract so they do.
- Version when you break. Support the old version for a stated period, and
  state it.

## Errors

- The status code carries the class; the body carries the detail. A `200` with
  an error inside forces every client to parse the body to know what happened.
- Error bodies have a stable shape and a machine-readable code. A human string
  alone means clients match on prose.
- Never return internal detail — stack traces, SQL, internal hostnames.

## Operational

- Idempotency keys on anything that creates or charges.
- Rate limits communicated in headers, not discovered by being cut off.
