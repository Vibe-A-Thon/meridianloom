# Meridian Loom

**Bring your own agents. Keep the evidence.**

Meridian Loom is a VS Code extension for running AI coding agents as a
governed team, and for keeping a verifiable record of what they did.

It is not another chat panel and not another model. It runs the agents you
already have — Claude Code, Gemini CLI, or anything that speaks the
[Agent Client Protocol](https://agentclientprotocol.com) — and adds the parts
that are missing when agents start writing production code: who did what, on
whose authority, and whether the result can be trusted.

Select **Meridian Loom** in the Activity Bar and the workbench opens. There is
no command to run first.

---

## What it does today

### Portable agents

Add an agent as a launch profile, or import one as a Markdown card, an adapter
folder in a ZIP, or a portable JSON export. Agents are **yours**: Meridian runs
the CLI you installed, under your own credentials, and an export carries the
launch profile with its skills and instructions so the same agent can be set up
somewhere else. Meridian does not wrap, host or resell the agent — uninstall
this extension and the agent still works exactly as it did.

An agent is either **Active** (takes part in deliverables) or **Learning**
(runs nothing, collects memory notes for you to review). The status says which,
in words.

### Skills, instructions and SDLC phases

A skill pack turns a role agent into a stack specialist — bind
`java-spring-gradle` and the Developer becomes a Java developer. Instruction
files (`AGENTS.md` and its kin) carry how your organisation works, ordered so
the most specific scope wins.

All of it is written into the agent's briefing on every run, and the Runs tab
shows you the exact briefing that was sent. Tag agents to the nine SDLC phases
and a dispatched deliverable convenes them phase by phase, in order.

### Tool integrations, read-only

Seventeen systems — GitLab, GitHub, Jira, Jenkins, SonarQube, Postman, Docker,
Kubernetes, OpenShift, Kafka, Slack, Datadog, Grafana, Kibana, AWS, Control-M
and Chrome.

**Every operation is a read.** Nothing creates an issue, triggers a pipeline,
posts a message or restarts a workload. A connection is proved by reaching it,
and the card reports what answered, in how many milliseconds, and when — a
green light older than thirty minutes reads *Stale*, not *Reachable*.

### Evidence you can take with you

Every recorded action lands in a hash-chained, Ed25519-signed ledger. The audit
bundle exports to JSON and **verifies without Meridian installed**:

```
python <extension>/sidecar/verify.py my-bundle.json
```

That verifier ships inside this extension. It is one file, Python standard
library only — the Ed25519 check is a pure-Python RFC 8032 implementation, so
it needs nothing installed at all. Hand it and your bundle to an auditor who
has never heard of this tool and they can check the chain, the Merkle
inclusion proofs, the tree-head signature and the bundle signature themselves.

The point is that your evidence does not depend on this tool continuing to
exist, or on you continuing to pay for it.

### Measurement that admits what it does not know

Trust score with its full decomposition, rejection-reason distribution, the
adoption J-curve, DORA's four keys, recorded spend and forecast.

Every figure carries its coverage: how many ledger rows it was computed over,
whether the query truncated, and whether attribution fell below the floor. A
figure that cannot be evidenced reads **"Insufficient evidence"** — never zero.
A truncated sample disables anything projected from it.

---

## Honest limits

This is early software and the register in `status.md` scores it openly. Some
things worth knowing before you rely on it:

- **Multi-agent orchestration, autonomous loops and cross-repository delivery
  are not built.** Deliverables dispatch agents sequentially.
- **Gate approvals and isolated launch are partial.** The Governor tier's
  policy engine works; the surrounding workflow does not cover every case.
- **Integrations read; they do not write.** That is deliberate for now.
- **Probation for new agents exists as a library, not a workflow.** Onboarding
  does not yet block an unproven agent from live work.

Where a surface is incomplete, it says so rather than showing an empty panel
that looks broken.

---

## Getting started

1. Open a workspace folder. Meridian records into `.meridian/` inside it.
2. Select **Meridian Loom** in the Activity Bar.
3. On **Agents**, add an agent — you need an ACP-speaking executable on your
   PATH — or import one.
4. Activate it, and tag it to the SDLC phases it should take part in.
5. On **Deliverables**, write a brief and dispatch it.
6. Watch it on **Runs**; read the evidence on **Evidence**.

### Requirements


- VS Code 1.95 or later
- Python 3.11+ on PATH (the sidecar that owns the ledger and policy engine)
- An OS keyring. On Linux install `gnome-keyring` or KWallet — Meridian refuses
  to start rather than storing credentials in plaintext.

---

## Where your data goes

Nowhere.

- Agents run as local subprocesses under your own credentials.
- The ledger, agents, skills and instructions live in `.meridian/` in your
  workspace, which is git-ignored by default.
- Integration credentials go to the **OS keychain** and are never written to
  the workspace, never included in an export, and never shown back to you.
- Meridian ships no model client and calls no model API of its own.

---

## Tiers

| Tier | What it adds |
| --- | --- |
| **Flight Recorder** | Always on: agents, skills, instructions, phases, runs, integrations, the ledger and signed export. |
| **Governor** | Policy gates, roles and approvals, trust measurement, recorded spend, hosted agent sessions. |
| **Orchestra** | Multi-agent orchestration and autonomous loops. Not yet built. |

Enable them in the `meridian.tiers` setting. A disabled tier's surfaces are
absent from the tab bar, not greyed out.

---

## Status

Pre-release. Not yet published to the Marketplace: the licence is an open
decision (`DECISIONS.md`, D22) and the package stays `private` until it closes.
