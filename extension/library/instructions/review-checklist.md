---
kind: instruction
id: review-checklist
name: Review Checklist
description: What a reviewer checks, in the order that finds the most defects soonest.
scope: workspace
---

# Review Checklist

In this order. Most defects are found in the first two sections; style
comments on an incorrect change waste everyone's time.

## Correctness

- Boundaries: empty, one, many, maximum, one past maximum.
- Failure paths: what happens when the call fails, times out, or returns
  partial data?
- Concurrency: can two of these run at once? What breaks if they do?
- Resources: is everything opened also closed, on every path including the
  error path?
- Growth: does anything accumulate without a bound?

## Scope

- Does the diff contain anything the description does not mention?
- Is a behaviour change hidden inside a refactor?
- Are all the call sites updated?

## Tests

- Would these fail without the change?
- Do they test behaviour or implementation detail?
- What is still untested, and is that stated?

## Fit

- Does it read like the code around it?
- Does it add a second way to do something that already exists here?

## Then, and only then

Naming, comments, formatting.
