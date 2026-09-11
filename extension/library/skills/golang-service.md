---
kind: "skill"
id: "golang-service"
name: "Go Service"
description: "Idiomatic Go service structure, errors and concurrency."
version: "1.0.0"
tags: ["go", "golang", "backend"]
---

# Go Service

A Tier L3 Stack skill pack (`vision.md` 2.4). Bind it to the Developer or Frontend agent and that agent becomes this specialist — the identity is data, not code.

## Project layout

`cmd/<binary>/`, `internal/` for everything not meant to be imported, `pkg/` only for what genuinely is.

## Build and test

`go build ./...` · `go test ./...` · `go vet ./...` · `golangci-lint run`

## Coding standards and framework idioms

- Errors are values: wrap with `%w` and context that says what failed, and
  check with `errors.Is` / `errors.As`. Never compare error strings.
- `context.Context` is the first parameter of anything that does I/O, and it
  is honoured, not ignored.
- A goroutine without a defined exit is a leak. Every one has an owner who
  waits for it.
- Channels for ownership transfer; a mutex for shared state. Choosing the
  wrong one is the commonest source of Go deadlocks.
- Accept interfaces, return structs; define the interface where it is
  consumed, not where it is implemented.
- `defer` for cleanup, immediately after the acquire.

## Review checklist

- Does every goroutine have a path that ends it?
- Is the context threaded all the way through, or dropped at some layer?
- Does any error lose its cause on the way up?

## House rules

Add your organisation's own conventions here. This section is the reason a skill pack is editable: the rest is general practice, and this is what makes it yours.
