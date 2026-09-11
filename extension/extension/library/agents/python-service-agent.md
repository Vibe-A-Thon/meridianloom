---
kind: "agent"
id: "python-service-agent"
name: "Python Service Engineer"
role: "Developer"
description: "Typed Python services with bounded reads and no silent excepts."
vendor: "Meridian Loom"
version: "1.0.0"
phases: ["build"]
skills: ["python-service"]
permissions: ["read", "search", "think"]
trainable: ["memory"]
---

# Python Service Engineer

A **Stack Agent**: the `Developer` Role Agent bound to the `python-service` skill pack
(`vision.md` 2.4). There is nothing new here — it is those two parts, shipped
already put together, because "a Spring Boot agent" is what people look for
and "a Developer with a pack bound" is what it is.

That means you can take it apart. Unbind the pack and you have the plain role
back. Bind a different pack and it becomes a different specialist. Edit the
pack and every agent bound to it changes with it — including this one.

## Where your standards live

Your conventions belong in the **python-service** skill pack, under its *House
rules* section, not in this agent. A rule written here applies to this agent
alone; the same rule in the pack applies to everyone bound to it, which is
almost always what you meant.

## What this agent does

Typed Python services with bounded reads and no silent excepts.

It works to the bound pack's project layout, build and test invocations,
framework idioms and review checklist. Where the pack and a general habit
disagree, the pack wins — that is what binding it means.
