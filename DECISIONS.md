# MERIDIAN LOOM — Decisions

> Every decision made autonomously during the build, with reasoning. Conflicts between the six spec files are resolved by the precedence order in the kickoff message and recorded here.

## Pre-decided (from the kickoff message — do not revisit)

- **D1** Loop runtime: LangGraph (Python) with a SQLite checkpointer. Wrap it behind an interface so it stays substitutable.
- **D2** Model routing: deterministic first (always). Assisted classes → smallest model that satisfies the schema, local provider if configured, else cheapest cloud tier. Generative classes → the configured frontier model. All provider names and tiers come from config, never hard-coded.
- **D3** Ledger anchoring: local signing only in v1. Define the anchoring interface; ship a no-op anchor with a clear TODO.
- **D4** Python distribution: use the workspace interpreter via the resolution chain in FR-M3-05. Do not bundle a runtime in v1.
- **D5** Trainer scope: prompts, playbooks, checklists and learned/rules only. Never skill packs, never code.
- **D6** Autonomy tier promotion: first-pass yield ≥ 0.85 over ≥ 20 samples AND calibration error ≤ 0.12 for the task class. Demote on either falling below for 10 consecutive samples.
- **D7** Release/Operate: plans only. No deployment execution.
- **D8** SDLC phase set: configurable from policy; default nine phases exactly as Requirements_Final.md §6.
- **D9** Human identity: git user.name/user.email in v1, with an IdentityProvider interface and an OIDC stub for later.
- **D10** Golden corpus: `/golden/<story-id>/` with the story, cassette and expected ledger root. Admission by adding a folder. Refresh cassettes with `meridian corpus refresh`.
- **D11** Chat participant: YES, ship `@meridian` in C2.
- **D12** Currency: USD default, configurable per workspace with rate and date.
- **D13** Tenant isolation: Meridian owns it (SEC-23), implemented in C5.
- **D14** Security phase IS in the first-value chain. **AC-02 amendment: AC-02 reads Intake → Design → Plan → Build → Verify → Security → Review.**
- **D15** Bridges in v1: plain-Python and MCP (C2). LangGraph, CrewAI, A2A, OpenAI Agents in C4.
- **D16** Action-class catalogue: a policy YAML file (§7.10). Reclassification is a reviewed change to that file; the Routing Observatory shows it and links to it but edits go through a policy PR.
- **D17** Bridged agents' own learning mechanism: SHADOW — it may run, its outputs are recorded, Meridian's Trainer is authoritative for `learned/`.
- **D18** `learned/` persistence: committed to the repository under `.meridian/adapters/<id>/learned/`.
- **V1** Sprite art: designed geometric token fallback (VIGUIX_Final.md §13, T9). No commissioned art.
- **V3** Fonts: Archivo and JetBrains Mono, self-hosted and subset under their open licences. Commit Mono only if its licence permits redistribution; either way, implement the documented fallback stack.
- **V4** The Weave is both the Command Center hero and its own full screen.
- **V5** 2.5D projected for Dojo and Loop Graph, with the flat 2D fallback under reduced motion.
- **V6** Focus Mode is a chrome-hiding state of the main panel.
- **V7** Density default: comfortable.
- **V8** The simulation band (X-26) DOES appear in Focus Mode.

## Decisions made during the build

_(none yet)_

## Spec conflicts found and resolved

_(none yet)_

## Deferred with reason

_(none yet)_
