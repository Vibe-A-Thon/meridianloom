# Meridian Loom — Interface Gaps from the Honest Assessment

| | |
|---|---|
| **Document** | gaps_guix.md |
| **Version** | 1.0 — proposed, for review |
| **Author** | Ravaleedhar Reddy |
| **Derived from** | `HONEST_ASSESSMENT.md` (September 2026) · `gaps-requirements.md` v1.0 |
| **Complements** | `VIGUIX_Final.md` v2.1 · `viguix-implementation.md` v2.1 |
| **Purpose** | The screens, systems and sequencing that make the interface serve the trust layer first — and beat every competitor's agent-management surface at the one thing none of them do |

---

## 0. Read this first — what the interface must now be best at

`VIGUIX_Final.md` was designed for a product whose centre was the agent orchestra. The assessment moved the centre to **trust, provenance and governance across every agent a team already runs**. The interface has to move with it.

Three consequences:

1. **The first screen a user sees must work with zero Meridian agents.** The Weave and the Selvage, showing a Claude Code session or a Copilot PR the team ran this morning, with a vendor tag on every pass. If the interface only comes alive once the Orchestra tier is installed, it fails the repositioning.
2. **Every competitor's agent surface is now the benchmark.** Devin Desktop's Agent Command Center manages local agents, cloud agents, PRs and shared context, and runs third-party agents over ACP. Cursor's cloud agents run async. Copilot's Agent HQ lives inside the PR loop. Meridian must be at least as good at *hosting* an agent as Devin Desktop, and then do what none of them do: show all of them, together, gated and recorded.
3. **Forty-four screens before first value was the wrong sequence.** The interface is now built in tiers that match the product tiers — Flight Recorder, Governor, Orchestra — and each tier's screens are built after that tier's data has proved itself.

Every gap below cites the assessment finding it answers.

---

## 1. New Design Stances

| # | Stance | Consequence | Answers |
|---|---|---|---|
| **DS-1** | **The vendor tag is as fundamental as the state ring.** | Every agent token, pass, ledger row and hunk carries a `VendorTag` — Meridian, Claude Code, Cursor, Copilot, Codex, Devin, or the ACP agent's name — and an **observation-confidence glyph** (direct / telemetry / inferred). Never hidden, never colour-only. | BT-2, S-1 |
| **DS-2** | **The Weave is agent-agnostic.** | A row is a row whether Meridian's Developer or a Copilot cloud agent wove it. The cloth shows the whole team's agents, not Meridian's roster. | S-1, P20 |
| **DS-3** | **Progressive disclosure follows the product tiers.** | Flight Recorder shows three screens. Governor unlocks decision surfaces. Orchestra unlocks the Floor, Dojo, loops. A user never sees an empty orchestra. | P22, BT-4 |
| **DS-4** | **Trust is a first-class screen, not a KPI panel.** | Rejection rate, trust score, agent-vs-agent, greenfield/brownfield — the numbers that answer "should I trust this agent with this module" get their own surface. | BT-5 |
| **DS-5** | **Match the best competitor surface, then exceed it in one dimension.** | The Adapter Bay must host an ACP agent at least as well as Devin Desktop's Agent Command Center — and then show that agent's provenance, gates and trust, which Devin cannot. | BT-1, BT-2 |

---

## 2. New Cross-Cutting Systems

| ID | System | What must be specified | Priority | Answers |
|---|---|---|---|---|
| **X-27** | **`VendorTag` and observation confidence** | A primitive on par with `StateRing`: vendor name, a bespoke glyph per vendor (never their logo — trademark), and the observation-confidence mark (● direct · ◐ telemetry · ○ inferred). Appears on every `AgentToken` ≥ 20px, every weft row, every ledger row, every hunk. Component-level invariant like B14. | MUST v1 | DS-1 |
| **X-28** | **Tier-aware disclosure** | The shell knows which tier is active. Loom Bar, Omnibar, context menus and the command registry expose only that tier's screens; higher-tier entries appear as a single "Unlock Governor / Unlock Orchestra" affordance with a one-line statement of what it adds and what it costs. Empty states for higher tiers never render. | MUST v1 | DS-3 |
| **X-29** | **External-session awareness** | The shell detects an external agent session in the workspace (ACP session, OTel stream, or worktree activity) and surfaces it in the Crown within 2 seconds — "Claude Code is active · 4 files · recording ●" — so the recorder is visibly on before the user asks. | MUST v1 | S-1 |
| **X-30** | **Provenance hover, everywhere** | Hovering or focusing any agent-authored artifact — a line in the editor, a hunk, a weft row, a PR in the pipeline — shows the same `ProvenanceStamp` + `VendorTag` + confidence + "who approved" card. One component, one behaviour, every surface. | MUST v1 | S-1 |
| **X-31** | **Competitor-surface parity checks** | A design-review checklist: for each competitor surface (Devin Desktop Agent Command Center, Cursor cloud agent panel, Copilot Agent HQ, Zed's agent panel), Meridian's equivalent must match on the operations a user performs most (start, watch, steer, stop, review, approve) before adding anything. Parity is verified with task-timing on five engineers. | MUST v1.x | DS-5 |

---

## 3. New Screens

Numbered to continue `VIGUIX_Final.md` §10.

### 10.45 Flight Recorder *(the first screen)* · **MUST v1**

**Serves:** M36, M35. **Tier:** Flight Recorder. **Answers S-1, S-2.**

The product's front door. Zero Meridian agents required. If a team installs Meridian and runs the agent they already use, this is what they see.

```
┌ CROWN   ● Recording · Claude Code active · 4 files · 0 model calls by Meridian ┐
├──────────────────────────────────────────────────────────────────────────────┤
│ ┌─ THE WEAVE ─────────────────────────────────────┐ ┌─ THIS SESSION ───────┐ │
│ │  IN  DE  PL  BD  VF  SC  RV                     │ │ ◐ Claude Code        │ │
│ │  ────────────▓▓▓▓▓───────────  ◐ Claude 14:02   │ │   telemetry (OTel)   │ │
│ │  ────────────▓▓▓▓▓▓▓─────────  ◐ Claude 14:05   │ │   12 files · 3 cmds  │ │
│ │  ─────────────────▓▓▓────────  ○ inferred 14:09 │ │   $0.84 (vendor est.)│ │
│ │  ─────────────────────▓▓▓▓───  ● Copilot PR#4821│ │ ● Copilot PR #4821   │ │
│ │                                                  │ │   direct (SCM)       │ │
│ └──────────────────────────────────────────────────┘ └──────────────────────┘ │
│ ┌─ ANY LINE ──────────────────────────────────────┐ ┌─ EXPORT ─────────────┐ │
│ │ PaymentController.java:47                        │ │ Audit bundle         │ │
│ │ ◐ Claude Code · 14:05 · seq 4402                 │ │ signed · SSDF/42001  │ │
│ │ told: "add idempotency key to submit"            │ │ [Export range]       │ │
│ │ approved: — (not yet gated)                      │ │ Verifies without     │ │
│ │ git trailer: Meridian-Ledger: 4398-4402 ✓        │ │ Meridian installed   │ │
│ └──────────────────────────────────────────────────┘ └──────────────────────┘ │
├──────────────────────────────────────────────────────────────────────────────┤
│ ◧ Selvage · verified to 4402 · signed 14:09 · [Unlock Governor → gate this PR]│
└──────────────────────────────────────────────────────────────────────────────┘
```

- **The Weave**, agent-agnostic: every pass with its `VendorTag` and confidence glyph. Meridian-native rows, if any, look the same as external rows except for the tag.
- **This session**: live external sessions with observation source, files touched, commands run, and vendor-estimated spend.
- **Any line**: the provenance answer — pick a line in the editor or the diff and see agent, time, sequence, what it was told, who approved (or "not yet gated"), and the git trailer that will outlive Meridian.
- **Export**: signed audit bundle for a range, with the compliance mapping named and the "verifies without Meridian" promise stated.
- **Selvage strip** along the bottom with verify status, and the single tier-unlock affordance (X-28).

**What it deliberately does not have:** a roster of Meridian agents, a Floor, loops, a Dojo. The screen must feel complete on its own.

**Empty state:** "Nothing recorded yet. Run the agent you already use — Claude Code, Cursor, Copilot — in this workspace and the cloth will start." The unstrung loom, plus three vendor glyphs.

### 10.46 External Agents *(proxy view)* · **MUST v1**

**Serves:** M35. **Tier:** Flight Recorder. **Answers BT-2, S-1.**

Every non-Meridian agent seen in the workspace, as a first-class citizen.

- **Session list**: agent, vendor, observation source and confidence, start time, files, commands, spend estimate, and whether Meridian is *hosting* it (ACP) or *observing* it.
- **Per-session detail**: the passes it produced (Weave slice), the PR if any, the gates it has or has not been through, and its trust score to date.
- **Observer health**: per vendor, whether the observer adapter is current for that agent's release; degraded-to-inferred shown in weld with the reason and the upgrade action (`FR-M35-08`, `NFR-32`).
- **Ingest PR**: for an external PR (e.g., Copilot from Jira), a one-click *Treat as story* that creates a story, attributes the hunks, and routes it to the gates (`FR-M35-05`).
- **Never** a control to modify or reconfigure the external agent (`FR-M35-06`). The screen watches and gates; it does not drive.

### 10.47 Trust Observatory · **MUST v1** *(Governor tier)*

**Serves:** M37. **Answers BT-5.** The 46% / 3% problem, made visible.

- **Rejection rate** per agent, per action class, per phase, per repository — as meridian arcs on the X-07 grammar, split **greenfield / brownfield** on every chart (`FR-M37-06`).
- **Rejection reasons**: the `E-GR-03` taxonomy as a distribution per agent, so the user sees *why*, not only how often.
- **Trust score decomposition** per agent per task class: yield, rejection, calibration, post-merge revert, incidents — with the autonomy ladder (10.37) embedded.
- **Agent vs. agent**: two agents on the same story or packet side by side — yield, rejection reasons, cost, LLM ratio — with the shadow-run control (`FR-M37-04`). External agents are valid comparators.
- **The J-curve**: team throughput and stability before and after adoption on one chart, with the dip labelled as a phase (`FR-M37-05`). This is the chart that stops a pilot being cancelled in month two.
- **Tokenmaxxing warning**: spend rising without yield rising, per agent (`FR-M37-07`).
- **Module effectiveness map**: agent effectiveness by module age and complexity (`FR-M38-06`) — the picture of where agents help and where they should not be used.

### 10.48 Comprehension Studio · **MUST v1.x** *(Governor tier)*

**Serves:** M38. **Answers BT-5 (the 10% problem).**

The brownfield screen. Before an agent touches a legacy module, this is what a human and an agent both see.

- **Module comprehension record**: dependency graph slice (from CodeMap), callers and callees, coverage, change frequency, authorship, linked incidents, detected conventions — all deterministic, all with provenance.
- **Brownfield risk score** with its decomposition, and the gate strictness it triggers.
- **Characterisation gate**: uncovered high-risk modules show the block and the *Generate characterisation tests* action; the tests appear here with their coverage delta before any change is allowed.
- **Comprehension memory**: what the repository has already taught Meridian about this module from prior stories, with freshness.
- **Recommend / restrict**: the policy view of which autonomy tier is allowed on this module and why.

### 10.49 Cross-Vendor Spend · **MUST v1.x** *(Governor tier)*

**Serves:** M39. **Answers the 2026 buying decision.**

- Spend by vendor, model, agent, story, team, cost centre — native and external in one view.
- Monthly forecast with the budget line and the breach alert.
- Ceilings on hosted external agents (pause at checkpoint) and warnings on observed ones.
- **With and without deterministic paths** (`FR-M39-05`): the Deterministic Engine's saving as a bar beside the vendor bill.
- Meridian's own spend in the same table, never hidden.

### 10.50 Unlock *(tier transition)* · **MUST v1**

**Serves:** `FR-M36-05`, X-28.

Not a settings page — a single, honest screen for moving from Flight Recorder to Governor, or Governor to Orchestra. It states in plain language what the next tier adds, what it costs (including that Orchestra makes model calls and Flight Recorder never does), what evidence the current tier has produced (twenty stories, the trust numbers), and what the assessment's own evidence says about the tier's likely value. Then one action. It must be possible to unlock, use, and disable a tier without losing any lower-tier data.

---

## 4. Amendments to Existing Screens

| Screen | Amendment | Answers |
|---|---|---|
| **10.1 Command Center** | Becomes the **Governor tier's** front door. Flight Recorder users land on 10.45. The Weave hero is agent-agnostic (DS-2). Gates and questions tiles include external agents' PRs. | P22 |
| **10.3 The Weave** | Rows carry `VendorTag` + confidence glyph. **Filter by vendor.** Export legend includes vendor glyphs. Compare mode (`E-WV-05`) supports "same story, two agents." | DS-1, DS-2 |
| **10.4 Agents Watch** | Lists external agents alongside Meridian's, with `VendorTag`, observation source, trust score and rejection rate columns. Row action: *Open in External Agents* / *Open in Trust Observatory*. | S-1 |
| **10.6 Gate Room · 10.27 Decision Stream** | Gate cards for external-agent PRs show the vendor, the observation confidence, and — where the observation is `inferred` — a stronger warning that the artifact is what Meridian *saw*, not what the agent *reported*. | `FR-M35-04` |
| **10.7 Ledger** | Entries from external agents carry `VendorTag` and confidence. Filter by vendor. Audit-bundle export names every vendor whose work the bundle records (`SEC-29`). | S-1 |
| **10.16 Inspector** | Works for external agents: Trace shows what was observed and at what confidence; Terminal shows the OTel/log stream where available; Diff, History and Messages work as for native agents. Policy and Memory tabs show "not applicable — external agent" rather than empty. | `FR-M35-03` |
| **10.17 Diff Theater** | Each hunk carries `VendorTag`; multi-agent stories show inter-agent conflicts as a distinct rework class (`FR-M35-07`). | |
| **10.22 KPI Observatory** | Gains the trust set from M37 and the greenfield/brownfield split on every chart. | BT-5 |
| **10.31 Routing Observatory** | Adds the external agents' model usage where observable, so `why_llm` and the LLM ratio are shown for the whole team's agents, with "not observable" stated where it is not. | |
| **10.42 Editor surfaces** | Hover provenance and blame decoration read every vendor's trailers, not only Meridian's (`M24` amendment). | S-1 |
| **10.43 Adapter Bay** | Becomes the **ACP host UI**: browse and install from the ACP Registry, launch and manage ACP sessions, see permission requests with Meridian's policy check applied before the prompt (`FR-M34-04`). Benchmark: at least as fast to start, watch, steer and stop an agent as Devin Desktop's Agent Command Center (X-31). Then the one thing it cannot do: that agent's provenance, gates and trust, inline. | BT-1, DS-5 |
| **10.40 First-Run** | Rewritten for Flight Recorder: connect to a repository → run your existing agent → see the Weave → export a bundle. Four steps, no model credential, no Meridian agent. Under 15 minutes (`NFR-28`). | S-2 |
| **10.2 Floor · 10.5 Dojo · 10.9 Loops** | Orchestra tier only. Never rendered — not even as empty states — below that tier (X-28). | DS-3 |

---

## 5. Re-sequenced GUI Build

This supersedes `viguix-implementation.md` v2.1's "all ten phases against the Simulation Core before C1." It follows `gaps-requirements.md` §9.

| GUI phase | With engineering | Screens | Built against |
|---|---|---|---|
| **GF0 — Recorder** | F0 | Tokens, shell, X-27, X-28, X-29, X-30 · **10.45 Flight Recorder** · 10.46 External Agents · 10.7 Ledger · 10.3 Weave (agent-agnostic) · 10.40 First-Run (rewritten) · 10.50 Unlock | **Real external-agent sessions** — a Claude Code run, a Copilot PR — recorded live. The Simulation Core supplies scenarios only where a vendor's surface is unavailable in the dev environment. |
| **GF1 — Governor** | F1 | 10.1 Command Center · 10.6 Gate Room · 10.27 Decision Stream · 10.28 Steer & Clarify · 10.32 Roles · **10.47 Trust Observatory** · 10.49 Cross-Vendor Spend · 10.43 Adapter Bay as ACP host · 10.16 Inspector (external-aware) | Real gated external-agent PRs |
| **GF2 — Evidence** | F2 | No new screens. Twenty real stories. The Trust Observatory's numbers decide whether GF3 is built. | Real |
| **GF3 — Orchestra** | F3 | The remainder of `VIGUIX_Final.md` §10 — Floor, Dojo, Loops, Portfolio, Memory Studio, modelling surfaces, the roster — **only for the data F2 proved matters** | Real Meridian agents, with the Simulation Core as the regression harness |
| **GF4+** | F4+ | 10.48 Comprehension Studio (if not pulled into GF1 for a brownfield-heavy pilot), refinement, everything in `viguix-implementation.md` G8 | Real |

**What changed and why:** first value is now GF0, in weeks. The Simulation Core remains the regression harness it was always meant to become, but no longer stands in for reality across forty-four screens (BT-4).

---

## 6. Competitor Surface Benchmarks

What Meridian's surfaces must match before they may exceed (X-31). Derived from the 2026 product landscape in the assessment.

| Competitor surface | What it does well | Meridian must match | Meridian then exceeds with |
|---|---|---|---|
| **Devin Desktop — Agent Command Center** | One place to manage local agents, cloud agents, PRs and shared context; runs third-party agents over ACP | Start / watch / steer / stop an ACP agent as fast, in 10.43 | Provenance, gates and trust score for that agent, inline; ledger that survives the vendor |
| **Cursor — cloud agents** | Async agents that open PRs; deep in-editor integration | Hover provenance in the editor as immediate as Cursor's inline context (X-30) | Cross-vendor: the same hover works on a Copilot-authored line |
| **Copilot — Agent HQ + Jira → PR** | Lives inside the GitHub PR loop; ticket becomes PR without opening the editor | Ingest that PR as a story in one click (10.46) | Gate it, record who approved it, export the evidence |
| **Claude Code — terminal harness, OTel, Co-Authored-By** | Programmable, scriptable, has the most durable single-vendor authorship signal | Read its trailers and OTel natively (10.46 observer) | Put its passes in the same cloth as everyone else's, gated by the same policy |
| **Zed — agent panel** | Clean ACP host, bring-your-own-agent, nothing touches their servers | The same "nothing leaves the machine" promise, stated in the UI | A signed, exportable ledger of what the agent did — Zed records nothing |

---

## 7. New Banned Patterns

Appended to `VIGUIX_Final.md` §18.

28. Rendering an agent's pass, hunk or ledger row without its `VendorTag` and observation-confidence glyph.
29. Using a vendor's logo or trademark as its glyph. Bespoke glyphs only.
30. Rendering any Orchestra-tier surface — Floor, Dojo, Loops, roster — below the Orchestra tier, including as an empty state.
31. Presenting an `inferred` observation with the same visual weight as a `direct` one.
32. Any first-run flow that requires a model credential or a Meridian agent before the user sees their first provenance answer.

---

## 8. New Accessibility and Trust Items

| ID | Requirement | Priority |
|---|---|---|
| A-09 | The observation-confidence glyph is announced by screen readers with its meaning ("observed directly", "from telemetry", "inferred from file changes"), never as a symbol name. | MUST v1 |
| A-10 | The Trust Observatory's every chart has a one-sentence written finding beneath it, so the shape of the data is available without reading the chart. | MUST v1 |
| A-11 | The Unlock screen's cost and evidence statements are plain text, not iconography, and are the same in every theme. | MUST v1 |

---

## 9. Decisions

| # | Decision | Bearing | Needed by |
|---|---|---|---|
| **V9** | Whether 10.45 Flight Recorder and 10.1 Command Center are two screens or one screen with tier-aware panels. Two screens keeps the recorder uncluttered; one screen avoids a "which home?" question at Governor. Recommend two, with 10.1 replacing 10.45 as home on unlock. | The product's front door | GF0 |
| **V10** | Vendor glyph design — five to seven bespoke marks that are recognisable at 12px, distinct from each other under all three colour-vision deficiencies, and safely distinct from any vendor's trademark. Needs a design pass and a trademark check. | X-27 | GF0 week 1 |
| **V11** | Whether the Comprehension Studio (10.48) is pulled into GF1 for a pilot whose repositories are mostly legacy — which, for an IT-services organisation, is most of them. | Brownfield value at first value | F1 planning |

---

## 10. What This Changes About "Best of the Best"

After these gaps, the interface is no longer trying to be a better Cursor. It is the surface that a team opens *alongside* Cursor, Claude Code, Copilot and Devin — and sees, for the first time, all of them in one cloth: what each one did, what it was told, how often its work is rejected, what it costs, and whether a human approved it. That is a screen no competitor can build, because each of them is one vendor and the value is in the view across all of them.

The Floor, the Dojo, the loop graph and the roster are still in the specification. They are the Orchestra tier, and they are earned — built after the trust layer has twenty real stories of evidence that it deserves them.

---

*Every item above is written to be lifted into `VIGUIX_Final.md` v2.2 and `viguix-implementation.md` v2.2 once accepted. `D22` in `gaps-requirements.md` must close first.*
