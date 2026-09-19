# Meridian Loom

**Bring your own agents. Keep the evidence.**

Meridian Loom is a VS Code extension for running AI coding agents as a
governed team, and for keeping a verifiable record of what they did.

It is not another chat panel and not another model. It runs the agents you
already have — Claude Code, Gemini CLI, or anything that speaks the
[Agent Client Protocol](https://agentclientprotocol.com) — and adds the parts
that are missing when agents start writing production code: who did what, on
whose authority, and whether the result can be trusted.

Select **Meridian Loom** in the Activity Bar and the workbench opens as an
editor tab. There is no command to run first. If you would rather it lived in
the side bar, set `meridianLoom.surface` to `sidebar`.

> **Evaluating this for an organisation?** Start with
> [`docs/SECURITY-AND-DATA.md`](docs/SECURITY-AND-DATA.md) — what data is
> stored, what leaves the machine (and what never does), how credentials are
> held, and the limitations we would rather you heard from us. Then
> [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) for rollout, central settings and
> a sensible pilot order. Both ship inside the package.

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

**A library ships in the box.** A new workspace is seeded with the twelve
Role Agents — Analyst, Solution Architect, Tech Lead, Developer, Frontend,
QA Engineer, QA Lead, Reviewer, Security, Release, SRE and Scrum Master —
covering all nine SDLC phases; the ten skill packs of the GA catalogue
(`java-spring-gradle`, `java-fullstack`, `python-service`, `golang-service`,
`react-frontend`, `node-service`, `dotnet-service`, `aws-iac`,
`sql-migration`, `api-contract-first`); and instruction documents for
engineering standards, a definition of done, a review checklist and a security
baseline. They are marked **Built-in**, and they are ordinary records: read
them, edit them, disable them, export them, or delete them. A deleted built-in
stays deleted.

Each skill pack carries what a pack is supposed to carry — project layout,
build and test invocations, framework idioms, a review checklist, and an empty
**House rules** section for your own conventions. That section is the point of
them being editable.

The instruction documents are bound to the shipped agents, so they reach every
briefing. The **skill packs are not** — binding all ten would make the
Developer ten contradictory specialists at once. Bind the one that matches
your stack, and that is the moment the Developer becomes a Go engineer or a
Java engineer. The identity is data, not code.

The shipped agents arrive in **Learning** mode with `read`, `search` and
`think`, and with no executable bound. Something that came free in the box has
not earned more trust than something you chose to install, so you bind it to an
ACP adapter and activate it deliberately — the same two steps as an import.
Your own agents, skills and instructions load the same way, as `.md` or `.zip`;
built-in and uploaded are one mechanism with two sources, not two systems.

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

```console
python <extension>/sidecar/verify.py my-bundle.json
```

That verifier ships inside this extension. It is one file, Python standard
library only — the Ed25519 check is a pure-Python RFC 8032 implementation, so
it needs nothing installed at all. Hand it and your bundle to an auditor who
has never heard of this tool and they can check the chain, the Merkle
inclusion proofs, the tree-head signature and the bundle signature themselves.

**From a commit to its evidence.** Every commit Meridian records carries a
`Meridian-Ledger: 412-418` trailer pointing into the ledger. The trailer is a
published, versioned specification with a reference parser that also ships
here, so a third party can go from `git log` to verified evidence with nothing
installed:

```console
git log -1 --format=%B <commit> | python <extension>/sidecar/meridian_trailer.py
```

See `docs/spec/meridian-ledger-trailer.md` (shipped alongside it).

**Working without the extension.** A headless collector and verifier runs the
same data with no editor and no sidecar — `paths`, `export`, `verify`, `erase`
and `uninstall`:

```console
python -m meridian_core.cli paths --workspace .
```

See `docs/spec/evidence-portability.md`. A bundle you export before
uninstalling still verifies afterwards, which is a tested property rather than
a promise.

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
2. Select **Meridian Loom** in the Activity Bar. It opens as an editor tab,
   already seeded with the built-in library.
3. **Enable the Governor tier** in the `meridian.tiers` setting. Running an
   agent from Meridian is a Governor capability, because a run is a session
   whose permission decisions get recorded. Without it you can observe agents
   you start yourself, but the Run button will tell you it is blocked.
4. On **Agents**, pick a built-in role — or add your own, or import one — and
   give it the command for an ACP-speaking executable on your PATH. Built-in
   agents ship without one deliberately.
5. Activate it, and tag it to the SDLC phases it should take part in.
6. **Widen the permission policy if your agent needs to write.** A new agent is
   on probation, and the shipped default grants probationary agents only
   `read` and `search`. An agent that edits files or runs commands will refuse
   until you say otherwise — see below.
7. On **Deliverables**, write a brief and dispatch it.
8. Watch it on **Runs**; read the evidence on **Evidence**.

### The permission floor, and why an agent may refuse

Meridian checks its own policy **before** asking you to approve anything
(`FR-M34-04`), so a tool kind that policy does not cover is denied and you are
never prompted. The shipped default is deliberately conservative:

```yaml
adapters:
  '*':
    probation: [read, search]          # a brand-new agent
    active:    [read, search, edit, execute]
```

A newly added agent is on **probation** until it is admitted, so it cannot edit
or execute. That is the intended floor, not a bug — but it means your first
dispatch may come back as a refusal. Widen it for your workspace by creating
`.meridian/policy/acp-permissions.yaml`, which is read before the shipped
default:

```yaml
version: 1
adapters:
  '*':
    probation: [read, search, edit, execute]
```

This is policy, not code: it is a file in your repository, versioned and
reviewable like anything else.

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
| **Flight Recorder** | Always on: **observing** agent sessions others start, the ledger, signed export and verification, the agent/skill/instruction/phase catalogues, integrations, and trust measurement over what was recorded. |
| **Governor** | **Running agents from Meridian**, plus policy gates, roles and approvals, and recorded spend. |
| **Orchestra** | Multi-agent orchestration and autonomous loops. Not yet built. |

Enable them in the `meridian.tiers` setting. A disabled tier's surfaces are
absent from the tab bar, not greyed out.

---

## Status

Pre-release. Not yet published to the Marketplace: the licence is an open
decision (`DECISIONS.md`, D22) and the package stays `private` until it closes.
