---
kind: "skill"
id: "aws-iac"
name: "AWS Infrastructure as Code"
description: "Declarative AWS infrastructure with reviewable, reversible changes."
version: "1.0.0"
tags: ["aws", "terraform", "iac", "cloud"]
---

# AWS Infrastructure as Code

A Tier L3 Stack skill pack (`vision.md` 2.4). Bind it to the Developer or Frontend agent and that agent becomes this specialist — the identity is data, not code.

## Project layout

One stack per deployable unit; environments as variable sets, never as copied directories.

## Build and test

`terraform fmt -check` · `terraform validate` · `terraform plan` · `terraform apply`

## Coding standards and framework idioms

- Remote state with locking. Local state is a single point of loss and a
  race between two engineers.
- The plan is the review artefact. A change nobody read a plan for is a change
  nobody reviewed.
- Least privilege on every role, and no wildcard actions on wildcard
  resources. `*` in both halves of a policy is not a policy.
- Encrypt at rest and in transit by default; make the exception argue for
  itself.
- Tag everything with owner, environment and cost centre — untagged spend is
  unattributable spend.
- No secrets in variables or state. Use a secret manager and reference it.
- Pin provider and module versions.

## Review checklist

- Does the plan show anything being destroyed that should not be?
- Does any policy grant `*` on `*`?
- Is any secret materialised into state?

## House rules

Add your organisation's own conventions here. This section is the reason a skill pack is editable: the rest is general practice, and this is what makes it yours.
