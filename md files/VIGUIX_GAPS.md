# VIGUIX Gaps — What the GUI Specification Does Not Yet Cover

| | |
|---|---|
| **Document** | VIGUIX_GAPS.md |
| **Version** | 1.0 — proposed, for review |
| **Author** | Ravaleedhar Reddy |
| **Inputs read** | `vision.md` · `Requirements.md` (M1–M17) · `Requirements-Additions.md` (M18–M30, Parts A–J) · `VIGUIX.md` (24 screens) · `Sample_meridian-loom-gui.html` (9-screen prototype) |
| **Output** | New screens, enhancements to existing screens, cross-cutting GUI systems, and decisions — each liftable into `VIGUIX.md` and `viguix-implementation.md` |

---

## Method

Three passes, in order:

1. **Coverage.** Every module M1–M30 and every phase requirement was traced to a VIGUIX screen. Where no screen owns the human interaction a requirement implies, that is a gap.
2. **Depth.** Every VIGUIX screen was re-read against the requirement it serves, asking what a senior engineer would need on their third day of use that the current spec does not give them.
3. **Reality.** The prototype was built from the spec. Wherever building it forced a decision the spec was silent on, that silence is recorded here.

The headline finding: **Requirements-Additions.md introduced thirteen modules and VIGUIX.md has screens for none of them.** The base spec's coverage is strong; the additions have no GUI at all. Part A is mostly that.

The second finding is structural: the **Warp Spine, the Weave and the Floor all hard-code nine phases.** Any organisation with a different lifecycle breaks the product's signature visual. That is a decision (T1 in Part H), not a feature.

---

## 0. Coverage Matrix

| Module | Requirement | VIGUIX screen(s) | Prototype | Status |
|---|---|---|---|---|
| M1 | Extension host, decorations, status bar | §7.1 | — | **Partial** — gutter marks named, decorations unspecified |
| M2 | Webview dashboard | all | 9 of 24 | Covered |
| M3 | Sidecar lifecycle, remote | Config › Diagnostics | — | **Partial** — no restart / logs / remote-host UI |
| M4 | Loop runtime, time-travel (FR-M4-07) | 10.9 Loop Graph | Loops | **Missing** — no time-travel or replay surface |
| M5 | Agent registry, states | 10.4, 10.15 | Agents | **Partial** — probation / paused / retired lifecycle not visualised |
| M6 | Skill loader | 10.14 Skill Forge | — | Covered |
| M7 | Memory fabric, contradictions (FR-M7-05) | 10.16 Inspector › Memory | Inspector | **Missing** — no memory studio, no contradiction-resolution UI |
| M8 | Model router, budgets, failover | Config › Identity | — | **Missing** — no routing observatory |
| M9 | Tool layer, permissions, denials | 10.21 Security | — | **Partial** — denials shown, no permission matrix |
| M10–11 | Ledger, chain viewer | 10.7 | Ledger | Covered |
| M12 | Governance, tiers, policy diff (FR-M12-12) | 10.13 Config | — | **Partial** — no autonomy ladder, no policy diff viewer |
| M13 | XAI, calibration | 10.16 › Trace | Inspector | **Partial** — no calibration dashboard |
| M14 | Trainer | 10.5 Dojo | Dojo | Covered |
| M15 | Onboarding | 10.15 | — | Covered |
| M16 | Export / import | 10.23 Exchange | — | Covered |
| M17 | KPIs | 10.22 Observatory | — | Covered |
| **M18** | Worktrees, branches, abort, conflicts | — | — | **Missing** |
| **M19** | Work item connectors, write-back, templates, tiers | — | — | **Missing** |
| **M20** | Human identity, roles, SoD, N-of-M, delegation | — | — | **Missing** |
| **M21** | Story queue, WIP, contention, SLA slip | — | — | **Missing** |
| **M22** | Multi-repo, linked PRs | — | — | **Missing** |
| **M23** | CI in the loop, review comments, merge queue | — | — | **Missing** |
| **M24** | Chat participant, hover, code actions, blame | §7.1 mentions | — | **Partial** |
| **M25** | Steer, clarifying questions, dry-run, shadow, partial accept | — | — | **Missing** |
| **M26** | Cost forecast, budget approval, chargeback | — | — | **Missing** |
| **M27** | Replay cassettes, fault injection | — | — | **Missing** |
| **M28** | Reuse-first citations, duplicate warnings | — | — | **Missing** |
| **M29** | Documentation agent, journey report | — | — | **Missing** |
| **M30** | Doctor, backup, migration, updates | Config › Diagnostics | — | **Partial** |
| vision §7 | "Story Board" and "Training Queue" named as Command Center views | — | — | **Missing** — named in vision, absent from VIGUIX §10 |
| vision §7.2 | Warp thread click → "phase detail" | — | — | **Missing** — no Phase Detail screen exists |

---

## Part A — New Screens

Numbered to continue VIGUIX §10. Each names the module it serves.

### S25 — Story Hub *(vision's "Story Board")*

**Serves:** M19, M21, M25, M26. **Priority:** MUST v1.

The screen the product currently lacks most: one place that *is* the story. Today the story is a chip in the Crown and its facts are scattered across Spec Studio, Weave, and Gate Room.

- Header: story id, title, source (Jira / Rally / file), complexity tier, autonomy profile, branch and worktree, base branch.
- Acceptance criteria with live coverage status (lifted from Spec Studio).
- Phase timeline: entry and exit timestamps per phase, gate durations, SLA line with predicted completion and slip warning (FR-M21-06).
- Cost: estimate at ingest with interval, actual to date, ceiling, and a **What-if** slider — move the ceiling and see which packets would be cut (FR-M26-01).
- Linked artifacts: PR(s), CI runs, ADRs, journey report.
- Actions: **Dry-run**, **Abort story** (press-and-hold; shows what will be removed and confirms the primary tree is untouched — FR-M18-04), **Open worktree in new window**, **Pause**.
- Steer composer (S28) docked at the bottom.

### S26 — Portfolio

**Serves:** M21. **Priority:** MUST v1.x.

Every active story. Columns: story, phase, gate state, agents assigned, spend vs ceiling, SLA status, predicted completion. Rows are mini-weaves — a 3px-row texture of each story's cloth, so the whole portfolio reads as fabric samples.

- **Queue lane** above the table: prioritised backlog with WIP limit indicator and drag-to-reprioritise.
- **Contention panel:** which stories are waiting on model rate limits, sandbox slots, or overlapping files (FR-M21-05), with the arbitration decision shown.
- Filters: team, client, cost centre, tier, SLA-at-risk.

### S27 — Decision Stream

**Serves:** M12, M20, M25. **Priority:** MUST v1.

The Gate Room is designed for deliberate, one-at-a-time decisions. Approvers with twenty low-risk gates need a faster instrument — without losing rigour.

- One gate at a time, full-height, keyboard-driven: `J`/`K` next/previous, `A` approve, `R` rework (opens reason), `E` escalate, `S` steer, `?` expand evidence.
- **Not a swipe interface.** Approve still requires the artifact to have been scrolled into view; the rubber-stamp detector (FR-M20-06) counts time-on-artifact and shows the approver their own median beside the org's.
- High-blast-radius gates are **excluded** from the stream and redirect to the Gate Room. The stream is for the routine.
- Batch approve for gates the policy marks batchable, with an explicit list of what is being approved and a single press-and-hold.

### S28 — Steer & Clarify *(composer and card)*

**Serves:** M25. **Priority:** MUST v1.

Two components, docked wherever an agent is in context (Story Hub, Inspector, Gate Room, Floor).

- **Steer composer:** free text plus structured chips (`prefer`, `avoid`, `constraint`, `example`), a target selector (this packet / this agent / this story), and a preview of exactly where the guidance will enter the next iteration's context. Sent steers appear in the Weave as a cochineal-dotted tick on the row they influenced.
- **Clarifying-question card:** the agent's question, its proposed options with its own recommendation marked, confidence for each, and a free-text answer. Answering resumes the loop; the card shows the resume with a `beat-up`. Unanswered questions surface in the Signal rail and the Crown badge.
- **Uncertainty prompt:** when an agent stops because confidence fell below the action-class threshold (FR-M25-03), the card states the threshold, the stated confidence, the calibration context, and offers *Proceed anyway* (ledger-recorded as a human override), *Steer*, or *Take over*.

### S29 — Diff Theater: Partial Acceptance & Human-Edit Capture

**Serves:** M25 (FR-M25-04/05). **Priority:** MUST v1.

Extends 10.17 rather than a new screen, but the interaction is substantial enough to specify on its own.

- Per-hunk tri-state: **accept / rework / edit-in-place.** Edit-in-place opens the hunk in Monaco; the human's change is captured as a "human corrected" rework signal with a diff-of-diffs shown before commit.
- A summary bar: `12 accepted · 2 reworked · 1 edited` with a single commit action.
- Moved-code detection and word-level intra-line diff, so a reviewer is not re-reading a relocated block.

### S30 — Replay & Time-Travel

**Serves:** M4 (FR-M4-07), M27. **Priority:** MUST v1 (developer-facing), SHOULD v1.x (user-facing).

- A **timeline scrubber** across the story: ledger sequence on the x-axis, phases as bands, gates as markers, rework as madder ticks. Drag to any point; every other view (Weave, Floor, Inspector, Loop Graph) re-renders to that moment. The Crown shows `viewing seq 4402 · live is 4417` in weld while time-travelling.
- **Fork from here:** with a cassette present, re-run from a checkpoint with modified state for ablation or debugging (FR-M4-07, FR-M13-08). Forks render as a branch off the timeline and are ledger-tagged as replays, never as live work.
- **Cassette panel** (developer mode): recorded calls, hit/miss, and a fault-injection console (FR-M27-04) to kill the sidecar, time out a model, or corrupt an entry — with the resulting recovery shown live.
- This is also the screen that makes a governance-meeting narrative possible: play a story from ingest to merge at 20× speed.

### S31 — Memory Studio

**Serves:** M7 (FR-M7-05, 07, 09, 11, 12, 13). **Priority:** MUST v1.

The Inspector's Memory tab shows one agent's memory. Nothing lets a human curate the organisation's.

- Three layers as columns: **Organisation › Team › Repository**, with override arrows showing which entry wins (FR-M7-09).
- Tiers as tabs: procedural, semantic, episodic.
- Entry cards with provenance, freshness score (FR-M7-12, stale entries dimmed with a "code changed since" note), trust tag, and pin state. Human-pinned entries (FR-M7-11) render with a linen border and cannot be edited by agents; the UI says so.
- **Contradiction queue** (FR-M7-05): pairs of conflicting entries side by side, with the ledger evidence for each, and *Keep left / Keep right / Merge / Ask agent*.
- **Untrusted holding area** (FR-M7-07): content awaiting promotion, with the source marked and a *Promote* action requiring a reason.
- **Context assembly preview** (FR-M7-13): pick an agent and a task; see what would be included, what would be cut, and why, with token cost per entry.
- Import / export as a Markdown bundle with a diff view (FR-M7-10).

### S32 — Model Routing Observatory

**Serves:** M8. **Priority:** SHOULD v1, MUST v1.x.

- Routing policy as a matrix: phase × task class → model, editable inline, with the blast-radius preview from Config.
- Live call stream: model, tokens in/out, latency, cost, cache hit, structured-output validation result, and the agent and ledger seq that made it.
- **Failover and backpressure events** (FR-M8-09, 13) as a timeline with the loops that were paused.
- Provider health, rate-limit headroom, region tags and data-residency policy compliance (FR-M8-12) — a provider outside policy renders in madder and is unselectable.
- Redaction log (FR-M8-11): what was redacted, from which prompt, before transmission.
- **Model comparison** (FR-M26-05): run a golden story against N configurations, compare yield / cost / latency in a small-multiples grid.

### S33 — Human Roles & Approvals

**Serves:** M20. **Priority:** MUST v1.x.

- **Who am I:** identity source, role, permitted gate actions, active delegations, session age with re-authentication prompt (SEC-22).
- Roles matrix: role × gate action, editable by Governor only.
- **Separation-of-duties explainer:** when SoD blocks an action, the UI names the rule, the conflicting act (e.g., "you ingested this story at 14:02"), and who can approve instead.
- **N-of-M progress** on high-blast gates: approvers who have signed, who remain, and a *Request approval* action that notifies.
- Delegation composer with expiry; active delegations visible to both parties.
- **Approval hygiene** (FR-M20-06): per-approver median time-on-artifact, expansion rate, and the rubber-stamp warning — shown to the approver privately and to Governors in aggregate.

### S34 — Connectors & Write-back

**Serves:** M19. **Priority:** MUST v1 (Jira), v1.x (rest).

- Connector cards: Jira Cloud, Jira DC, Rally, ADO, GitHub Issues — status, auth, last sync, field mapping.
- **Field mapping editor** with a live preview of a real story rendered through the mapping.
- **Write-back rules:** per transition, on/off, with a preview of the comment that will be posted and the transition that will fire. Done transitions show the human-approval prerequisite as a locked rule.
- Story templates (FR-M19-05) and complexity-tier heuristics (FR-M19-06), each editable with an example story classified live.
- Import queue for batch and epic ingestion (FR-M19-07).

### S35 — Delivery Pipeline *(CI & merge)*

**Serves:** M23. **Priority:** MUST v1.x.

- The L4 Delivery loop extended visually to its true end: PR opened → CI → review → merge queue → merged.
- CI runs inline with job status, logs on demand, and the re-entry into L2 shown as a rework row in the Weave with the failing job as its reason (FR-M23-02).
- **Review comment ingestion** (FR-M23-03): human PR comments listed with the agent and hunk they target, their classification as rework signal, and the Trainer attribution.
- CODEOWNERS-derived reviewer assignment (FR-M23-04) and merge queue position (FR-M23-05).
- Multi-repo: linked PRs in dependency order with merge blocking shown as warp threads between repos (M22, FR-M22-03).

### S36 — Repositories & Worktrees

**Serves:** M18, M22. **Priority:** MUST v1 (single repo), v1.x (multi).

- Per story: repository, base branch, story branch, worktree path, disk usage, commits (agent-signed indicator, FR-M18-06), and retention countdown after merge or abort (FR-M18-09).
- **Conflict surface** (FR-M18-03): human uncommitted changes that overlap a pending packet's target paths, listed before the packet starts, with *Stash / Commit / Skip packet*.
- Workspace manifest editor for multi-repo stories (FR-M22-01) with contract artifacts (FR-M22-02) attached to the cross-repo edges.

### S37 — Documentation & Journey Report

**Serves:** M29. **Priority:** SHOULD v1.x.

- Documentation Agent output as a diff against the existing docs, with the public-API-change gate criterion (FR-M29-02) shown.
- **Journey report** builder: choose sections (spec, decisions, packets, tests, gates, cost, ledger slice) and export to Markdown / PDF / Confluence, with a print stylesheet designed for it — the Weave rendered as a static image at print resolution.
- ADR fitness-function results (FR-M29-04) as a checklist.

### S38 — Calibration & Trust

**Serves:** M13 (FR-M13-03, 09), M12 (autonomy tiers). **Priority:** SHOULD v1.

- Per agent and per action class: stated confidence vs observed outcome as a reliability diagram, with the calibration error trend.
- **Autonomy ladder:** the four tiers as rungs, each agent as a token on its rung per task class, with the thresholds drawn and the distance to promotion or demotion shown. Promotion and demotion events as ledger-linked markers.
- Trust score decomposition: yield, calibration, tenure, incident linkage.

### S39 — Runtime & Operations

**Serves:** M3, M30. **Priority:** MUST v1.

Extends Config › Diagnostics into a real screen.

- Sidecar: state, PID, interpreter path and how it was resolved (FR-M3-05), remote host when under VS Code Remote (FR-M3-11), resource use, restart count, log tail with level filter, *Restart* and *Collect diagnostics bundle*.
- **Doctor** (FR-M30-01): each check with pass / fail / fix-it action.
- Backup and restore (FR-M30-02) with integrity result; state migration status (FR-M30-03); update channel and rollback (FR-M30-04).
- OpenTelemetry export status (FR-M30-06).
- Uninstall (FR-M30-08) with the ledger-preservation confirmation.

### S40 — Notification Center

**Serves:** all. **Priority:** MUST v1.

VIGUIX §7.1 says notifications are only for gates and breaches. That is right for *interrupting* notifications. It leaves no home for everything else.

- An inbox reachable from the Crown badge: gates, clarifying questions, breaches, budget warnings, CI failures, SLA slips, trainer candidates ready, imports awaiting probation review.
- Each item is actionable inline where the action is one click (approve a batchable gate, answer a question, acknowledge a warning).
- **Digest mode** and out-of-hours queueing (FR-M25-08). Snooze with a reason.
- Delivery channels per class: in-app, VS Code toast, OS notification, Slack / Teams / email via connector — configured in Config.

### S41 — First-Run & Guided Setup

**Serves:** NFR-14 (15-minute time-to-first-value). **Priority:** MUST v1.

Named in `viguix-implementation.md` G8 task 12, never designed.

- Five steps: connect a model credential → point at a repository → pick a first stack skill → run the bundled sample story as a dry-run → watch the Weave build. Each step shows the Doctor check it satisfies.
- The sample story's dry-run is a **real** run against a bundled sample repository, not a video. The user sees a real Weave, a real ledger entry, a real gate, and approves one real thing.
- Skippable, resumable, re-launchable from Config.

### S42 — Keyboard Map & Help

**Serves:** VIGUIX §14. **Priority:** SHOULD v1.

- A `?` overlay listing every shortcut for the current screen, generated from the command registry so it cannot drift.
- Contextual help affordance per panel ("what is the selvage?") opening a short in-product explainer with the vision's metaphor table.
- Guided tours per screen, launchable once and dismissible forever.

---

## Part B — Enhancements to Existing Screens

### 10.1 Command Center

| ID | Enhancement | Priority |
|---|---|---|
| E-CC-01 | Add the **Story Hub link** and the acceptance-criteria coverage summary; today the Command Center never shows what the story *is*. | MUST v1 |
| E-CC-02 | **Unanswered clarifying questions** as a first-class tile beside Gates, since an unanswered question stalls a loop exactly as an open gate does. | MUST v1 |
| E-CC-03 | **Story selector** for many stories: searchable dropdown with phase, gate state, and spend per row; recently viewed; pinned. | MUST v1 |
| E-CC-04 | **Customisable layout:** panels draggable and resizable within the region, layout persisted per user, with a *Reset* action. | SHOULD v1.x |
| E-CC-05 | Weave hero: **row hover** shows agent, phase, seq, cost; **seq axis** on the selvage side; click-drag selects a range and the spend tile shows the range's cost. | MUST v1 |
| E-CC-06 | Signal rail: **filters** (mine / gates / breaches / all), a **"3 new below"** chip is spec'd — add a **mark-all-read** and a link into S40. | SHOULD v1 |
| E-CC-07 | Add an **"as of"** freshness stamp to every panel when the sidecar is stale, not only a global banner. | MUST v1 |

### 10.2 Loom Floor

| ID | Enhancement | Priority |
|---|---|---|
| E-FL-01 | **Configurable room layout** driven by the phase set (see T1). The 4×3 grid must be generated, not drawn. | MUST v1 |
| E-FL-02 | Rooms show **gate state on their doorframe** (weld pulse when open, madder when blocked) so the Floor carries gate information without reading text. | SHOULD v1 |
| E-FL-03 | **Multi-story floors:** when several stories are active, each story is a floor; a floor selector or a stacked "building" view with one floor per story. | MUST v1.x |
| E-FL-04 | Agent **walk paths** are visible as fading thread trails, so a handoff pattern is legible after the fact. | SHOULD v1.x |
| E-FL-05 | **Human presence:** when a human is viewing or acting, a distinct linen-coloured figure appears in the Gate Room or at the relevant desk — the human is part of the organisation too. | SHOULD v1.x |
| E-FL-06 | Speech bubble **copy rules**: agent-written status must be ≤48 chars, sentence case, no emoji, no first-person flattery ("Great news!"), present tense, and must name the artifact. Enforced by the sidecar before display. | MUST v1 |
| E-FL-07 | **Touch and keyboard** access to room and agent selection; the prototype is mouse-only. | MUST v1 |

### 10.3 The Weave

| ID | Enhancement | Priority |
|---|---|---|
| E-WV-01 | **Configurable warp** — N phases from policy, with the phase codes and colours coming from the phase definition (T1). | MUST v1 |
| E-WV-02 | **Steer ticks and question markers** on the rows they affected (S28). | MUST v1 |
| E-WV-03 | **Gate bands:** a horizontal band across the warp where a gate was open, its height proportional to wait time, so approval latency is visible in the cloth. | SHOULD v1 |
| E-WV-04 | **Export** as PNG and SVG at print resolution, with a legend and title block, for the governance meeting VIGUIX promises. | MUST v1 |
| E-WV-05 | **Compare mode:** two stories' weaves side by side with shared warp, for "why did story B take three times longer." | SHOULD v1.x |
| E-WV-06 | **Annotations:** a human can pin a note to a row (FR-M10-16); notes render as a small linen tag. | COULD v2 |
| E-WV-07 | Texture density (3px rows) should show a **minimap** with the viewport rectangle for long stories. | SHOULD v1 |

### 10.4 Agents Watch

| ID | Enhancement | Priority |
|---|---|---|
| E-AW-01 | **Sticky first column** and column resize / reorder / pin, CSV export, saved views. The prototype scrolls the agent name off-screen on narrow widths. | MUST v1 |
| E-AW-02 | **Lifecycle column** with probation / active / paused / retired and time-in-state; retired agents in a collapsed section rather than hidden. | MUST v1 |
| E-AW-03 | **Agent profile** drill-down (a "CV"): history, yield over time, policy lineage, skills bound, stories worked, incidents linked, export/import ancestry. Trust is built by history, and no screen shows an agent's history today. | SHOULD v1 |
| E-AW-04 | **Compare two agents** side by side on the same metrics. | SHOULD v1.x |
| E-AW-05 | Bulk actions with a confirmation that lists every agent affected. | MUST v1 |

### 10.5 Agents Dojo

| ID | Enhancement | Priority |
|---|---|---|
| E-DJ-01 | **Signal sources panel:** which evidence fed this candidate — gate decisions, CI failures, review comments, human edits, incidents — with counts (T10 in Requirements-Additions). | MUST v1.x |
| E-DJ-02 | **Breaker results** (FR-M14-10) as a distinct pane: the failure cases generated and whether the candidate survived each. | SHOULD v1.x |
| E-DJ-03 | **Policy diff viewer** (FR-M12-12): the candidate's prompt/playbook delta against the incumbent, word-level, with the ledger evidence that motivated each change linked inline. | MUST v1 |
| E-DJ-04 | The sliders should be **thread-styled** as VIGUIX §10.5 specifies; the prototype uses stock range inputs. | SHOULD v1 |
| E-DJ-05 | **Rollback shelf** persistent across sessions (not only "for the session"), with one-click restore and the ledger entry it creates previewed. | SHOULD v1 |

### 10.6 Gate Room

| ID | Enhancement | Priority |
|---|---|---|
| E-GR-01 | **N-of-M approval progress** and **SoD block explanation** (S33) inline on the card. | MUST v1.x |
| E-GR-02 | **Steer** as a fifth action beside Approve / Rework / Escalate / Waive. | MUST v1 |
| E-GR-03 | **Rework reason taxonomy** is mentioned; specify it: `incorrect · incomplete · out-of-scope · style · security · performance · test-quality · other`, each mapping to a Trainer signal class. | MUST v1 |
| E-GR-04 | Show the **gate's history**: prior openings, prior rework reasons, and how many iterations of L2 produced the current artifact. | MUST v1 |
| E-GR-05 | Link to the **Decision Stream** for the routine gates and make the Gate Room the explicit home of high-blast-radius decisions. | MUST v1 |
| E-GR-06 | **Keyboard path for press-and-hold** (also applies to Halt All): `Space` held for 400 ms, with the same filling ring, and an accessible alternative — a two-step confirm for assistive-tech users who cannot hold a key. | MUST v1 |

### 10.7 Ledger

| ID | Enhancement | Priority |
|---|---|---|
| E-LG-01 | **Query builder** UI over FR-M10-12: filters, aggregates, time range, full-text, saved queries. | MUST v1 |
| E-LG-02 | **Natural-language query** box (FR-M10-13) with the resolved structured query shown, so the user learns the query language. | SHOULD v1.x |
| E-LG-03 | **Erasure UI** (FR-M10-14): a subject-scoped erasure request that shows which blobs will be crypto-shredded, confirms the chain remains verifiable, and records the erasure itself. | MUST v1.x |
| E-LG-04 | **Cold-storage indicator** for compacted entries (FR-M10-15) — digest retained, blob archived, fetch on demand. | SHOULD v1.x |
| E-LG-05 | **Shareable slice** (FR-M10-17): select a range → signed self-verifying HTML bundle → copy link / download. | SHOULD v1.x |
| E-LG-06 | **Deep links:** `meridian://ledger/4417` and equivalents for every entity, resolvable from chat, PR descriptions, and Jira comments. | MUST v1 |

### 10.8 CodeMap

| ID | Enhancement | Priority |
|---|---|---|
| E-CM-01 | **Source is CodeMap JSON** (ECO-03); the viewer must render that schema, and the `.cgw` cross-repo address (ECO-04) for multi-repo graphs. | MUST v1 |
| E-CM-02 | **Duplicate / reuse-first overlay** (FR-M28-04): nodes an agent nearly re-implemented, with the existing implementation it should have used. | SHOULD v1 |
| E-CM-03 | **Freshness overlay:** nodes whose procedural memory is stale (FR-M7-12). | SHOULD v1.x |
| E-CM-04 | **Time scrub** integration with S30: the graph at any ledger seq. | SHOULD v1.x |
| E-CM-05 | Node **detail drawer** with LSP-derived references and definitions (FR-M28-01), not only the graph edge. | MUST v1 |

### 10.9 Loop Graph

| ID | Enhancement | Priority |
|---|---|---|
| E-LP-01 | **Budget breakdown per loop**: tokens, wall clock, cost — three arcs, not one. | SHOULD v1 |
| E-LP-02 | **Escalation edges** drawn to the human when a bound is breached, terminating at the Gate Room. | MUST v1 |
| E-LP-03 | **Backpressure state** (FR-M8-13): a paused loop rendered as a held shuttle with the provider named. | SHOULD v1 |

### 10.10 – 10.12 Architecture, UML, Flow

| ID | Enhancement | Priority |
|---|---|---|
| E-AR-01 | **Contract artifacts** (FR-M22-02, FR-P4-13) rendered on the container edges they govern, with contract-test status (FR-P5-11). | SHOULD v1.x |
| E-AR-02 | **Threat model** (FR-P6-06) as an overlay on the C4 container view: trust boundaries and STRIDE annotations. | SHOULD v1.x |
| E-AR-03 | UML Studio: a **diagram-as-gate** mode where a diagram is the artifact under approval, with diff mode on by default. | SHOULD v1.x |

### 10.13 Config Portal

| ID | Enhancement | Priority |
|---|---|---|
| E-CF-01 | New sections: **Connectors** (S34), **Roles** (S33), **Routing** (S32), **Notifications** (S40), **Phases** (T1), **Tenants** (SEC-23), **Regulatory packs** (FR-M12-10). | MUST v1.x |
| E-CF-02 | **Git-backed policy** (FR-M12-12): show the policy file path, the commit that activated it, and *Open PR* rather than *Save* for governed sections. | MUST v1.x |
| E-CF-03 | **Search** across all settings; settings are already many, and will double. | MUST v1 |
| E-CF-04 | **Emergency fast path** toggle (FR-M12-13) with Governor authentication, a visible countdown, and a Crown banner while active. | SHOULD v1.x |
| E-CF-05 | **Kill switch per agent class** (FR-M12-14) with the affected agents listed before confirmation. | MUST v1.x |
| E-CF-06 | Density modes (comfortable / compact / dense) are named in Appearance; **specify the token deltas** per mode so components implement them consistently. | MUST v1 |

### 10.14 Skill Forge

| ID | Enhancement | Priority |
|---|---|---|
| E-SF-01 | **Upgrade flow** (FR-M16-09): regression status per bound agent before the new version activates, with a per-agent hold. | MUST v1.x |
| E-SF-02 | **Revocation** (SEC-19) with the paused-agent list and rebind assistant. | MUST v1.x |
| E-SF-03 | **Registry browser** (FR-M16-08): internal catalogue with signing status, yield telemetry, and organisation-wide usage. | SHOULD v1.x |

### 10.15 Onboarding Wizard

| ID | Enhancement | Priority |
|---|---|---|
| E-OB-01 | **Portrait art direction rules:** the sprite set must be stylised and non-photoreal, must not encode ethnicity, gender or age as identity signals, and must pass VS Code Marketplace content policy. Diversity comes from silhouette, palette and accessory, not demographic cues. | MUST v1 |
| E-OB-02 | **Import path** merges with onboarding: an imported agent (FR-M16-05) enters at the Probation step of the same wizard. | MUST v1.x |
| E-OB-03 | **Probation task set editor** with the expected outcomes visible, so a Governor can author probation for a new role. | SHOULD v1.x |

### 10.16 Agent Inspector

| ID | Enhancement | Priority |
|---|---|---|
| E-IN-01 | **Pop-out** to an editor tab and **pin** so two agents can be inspected side by side. | SHOULD v1 |
| E-IN-02 | Trace tab: **reuse-first citation** (FR-M28-04) and **context assembly** (what was included / cut, FR-M7-13) as collapsible sections. | MUST v1 |
| E-IN-03 | Terminal tab: **search, copy-as-issue** are spec'd; add **follow / unfollow** output and a **send input** field for agent sandboxes that prompt. | SHOULD v1 |
| E-IN-04 | Messages tab: the human's injected message must render distinctly (linen border) and appear in the ledger as a steer. | MUST v1 |
| E-IN-05 | A **History** tab: this agent's last N ledger entries, with the same row chrome as the Ledger. | SHOULD v1 |
| E-IN-06 | On narrow widths the slide-over needs a **backdrop, focus trap, and `Escape` to close** — the prototype has none. | MUST v1 |

### 10.17 Diff Theater — see S29.

### 10.18 Spec Studio

| ID | Enhancement | Priority |
|---|---|---|
| E-SS-01 | **Story template** conformance and complexity tier shown at the top (S34). | SHOULD v1.x |
| E-SS-02 | **Injected-instruction detections** (SEC-15) highlighted in the story text with the classifier's reason, so the human sees what was neutralised. | MUST v1 |
| E-SS-03 | **Ambiguity → question** link: an escalated ambiguity becomes a clarifying-question card (S28) and the resolution flows back here. | MUST v1 |

### 10.19 Work Packet Board

| ID | Enhancement | Priority |
|---|---|---|
| E-WP-01 | **Critical path** highlighted (FR-P3-04) and per-packet cost estimate vs actual. | SHOULD v1 |
| E-WP-02 | **Worktree and branch** per packet's story visible on the card (S36). | SHOULD v1 |
| E-WP-03 | **Feature flag** badge (FR-P4-11) and **license check** result (FR-P4-12) per packet. | SHOULD v1.x |

### 10.20 Verification Board

| ID | Enhancement | Priority |
|---|---|---|
| E-VB-01 | **Flake quarantine** (FR-P5-08) as its own lane, with the retry history and a *Release from quarantine* action. | MUST v1 |
| E-VB-02 | **Mutation score** (FR-P5-07), **performance regression** (FR-P5-12), **accessibility** (FR-P5-13), and **contract tests** (FR-P5-11) as additional gate rows with their own evidence drawers. | SHOULD v1.x |
| E-VB-03 | **Ephemeral environment** status (FR-P5-10): what was provisioned, its lifetime, and cost. | SHOULD v1.x |

### 10.21 Security Assurance

| ID | Enhancement | Priority |
|---|---|---|
| E-SA-01 | **Tool permission matrix:** agent × tool, with the policy source of each permission and every denial in the last N days as a heat cell. | MUST v1 |
| E-SA-02 | **Anomaly feed** (SEC-16): unusual tool calls awaiting confirmation, with the baseline they deviated from. | SHOULD v1.x |
| E-SA-03 | **AI-BOM and attestation** (FR-P6-08/09): the models, skills, and policies that produced the change, and the in-toto attestation verification result. | SHOULD v1.x |
| E-SA-04 | **Output scan** results (SEC-20) before code reached the working tree. | MUST v1.x |

### 10.22 KPI Observatory

| ID | Enhancement | Priority |
|---|---|---|
| E-KP-01 | Define the **chart grammar**: axis rules, meridian-arc semantics, tooltip content, annotation events (policy promotion, tier change, incident), and the divergence band. The spec names the visual language without specifying it. | MUST v1 |
| E-KP-02 | **Agent-vs-human baseline** (FR-M17-08) and **token efficiency ratio** (FR-M17-09) panels. | SHOULD v1.x |
| E-KP-03 | **Chargeback view** (FR-M26-03): cost by team / client / cost centre with export. | MUST v1.x |
| E-KP-04 | **Tech-debt registry** (FR-M17-07) panel with export to the issue tracker. | SHOULD v1.x |
| E-KP-05 | **Alert thresholds** on any KPI, feeding S40. | SHOULD v1.x |

### 10.23 Exchange

| ID | Enhancement | Priority |
|---|---|---|
| E-EX-01 | **Tenant boundary** warning (SEC-23) when exporting across clients; blocked by policy where configured. | MUST v1.x |
| E-EX-02 | **Retirement handover** (FR-M16-10): choose a successor and preview the procedural memory that transfers. | COULD v2 |

### 10.24 Focus Mode

| ID | Enhancement | Priority |
|---|---|---|
| E-FM-01 | **Portfolio focus:** cycle through active stories' floors on a timer, for the wall screen. | SHOULD v1.x |
| E-FM-02 | **Burn-in protection** for OLED wall displays: slow drift of the whole composition by a few pixels per minute. | SHOULD v1.x |

---

## Part C — Cross-Cutting GUI Systems Not Yet Specified

These are named or implied in VIGUIX but have no specification. Each needs a section of its own.

| ID | System | What must be specified | Priority |
|---|---|---|---|
| X-01 | **Omnibar (⌘K)** | Scopes (commands / agents / stories / packets / ledger / settings), ranking, recent, natural-language commands ("halt Kenji", "approve the design gate") with a confirmation preview, and the result card anatomy. | MUST v1 |
| X-02 | **Selection model** | One shared selection across Roster, Floor, Weave, tables, graphs, Inspector. Multi-select semantics, `Shift`/`Ctrl` behaviour on canvases, and what "selected" looks like in each renderer. | MUST v1 |
| X-03 | **Routing & restore** | Screen state as a serialisable route (`screen / entity / filters / time-travel seq`), back/forward navigation, restore-on-reload to the last route, and deep links (`meridian://`). | MUST v1 |
| X-04 | **Dialog, sheet, drawer, panel — decision rules** | When each is used; modal only for destructive confirmation; sheet for mobile-width; drawer for detail; every one with focus trap, `Escape`, and return-focus. | MUST v1 |
| X-05 | **Destructive-action pattern** | Press-and-hold (Halt, high-blast approve, abort), typed confirmation (promote), two-step confirm (accessible alternative). Which actions get which. | MUST v1 |
| X-06 | **Data table primitive** | Sticky header and first column, virtualisation, resize / reorder / pin, sort, filter, saved views, CSV export, row actions, bulk select, density modes, empty and loading states. | MUST v1 |
| X-07 | **Chart grammar** | Axes, scales, legends, tooltips, annotations, colour use (state dyes only where state is meant), the meridian-arc semantics, and reduced-motion behaviour. | MUST v1 |
| X-08 | **Markdown & agent-output rendering** | Sanitised markdown subset, code block styling, tables, max width, link policy (external links require confirmation — egress), and the "not verified" framing on any rationale. | MUST v1 |
| X-09 | **Agent copy rules** | Voice for agent-written strings (status, speech, questions, rationale): sentence case, present tense, names the artifact, no emoji, no flattery, no apology, ≤48 chars for status, ≤72 chars per line for prose. Enforced sidecar-side. | MUST v1 |
| X-10 | **Localisation** | Externalised strings (NFR-21), currency (cost in the workspace's currency, not only USD — the organisation bills globally), number and date formats, time zones (every `Timecode` carries a zone; the Crown shows the active zone), RTL readiness. | MUST v1.x |
| X-11 | **Notification model** | Classes, severity, interrupt vs inbox, channels, digest, snooze, out-of-hours — the full model behind S40. | MUST v1 |
| X-12 | **Keyboard command registry** | Every action registered with an id, label, shortcut, and screen scope; the omnibar and the keyboard map generate from it. | MUST v1 |
| X-13 | **Error boundaries** | Per-screen boundaries so one crashed renderer does not take down the shell; the boundary shows the last-known state, the error class, and *Reload screen* / *Report*. | MUST v1 |
| X-14 | **Offline & degraded modes** | Sidecar down, model provider down, connector down, ledger verification failed — each with its own banner, permitted actions, and recovery path, not one generic "stale". | MUST v1 |
| X-15 | **Presence** | When multiple humans share a workspace (M20, M21): who is viewing what, who holds a gate, avatars in the Crown, and a soft lock on a gate someone is deciding. | SHOULD v1.x |
| X-16 | **Personalisation** | Per-user: layout, density, theme, pinned panels, saved views, default screen, roster grouping. Stored via the extension host, never in the webview. | SHOULD v1 |
| X-17 | **Multi-panel** | Pop-out any screen to its own editor tab; two dashboards side by side; the Inspector pinned to a specific entity. | SHOULD v1 |
| X-18 | **Undo** | Which human actions are reversible in-UI (steer edits before send, rework reason edits within N minutes, filters, layout) and which are ledger-final (approve, promote, abort). The UI must make the difference visible before the click. | MUST v1 |
| X-19 | **Context menus** | Right-click on every entity with the same actions the omnibar exposes, generated from the command registry. | SHOULD v1 |
| X-20 | **Drag and drop** | Roster → packet (assign), Floor agent → room (reassign), queue reorder, panel layout. Drop targets, ghost images, keyboard equivalents for each. | SHOULD v1 |
| X-21 | **Icon set enumeration** | The bespoke set is described, never listed. Enumerate the 40–60 glyphs, their loom vocabulary, and which Codicons are used where. | MUST v1 |
| X-22 | **Roster scaling** | 30+ agents: grouping by phase or tier, filter, overflow "+N" opens a sheet, and a compact mode showing portraits only. | MUST v1 |
| X-23 | **Developer mode** | Frame-rate overlay, message-bus inspector, cassette panel, fault injection, token-cost overlay per panel. Hidden behind a setting. | SHOULD v1 |
| X-24 | **Print styles** | Weave, Journey Report, Ledger slice, KPI pages — each with a print stylesheet. | SHOULD v1.x |
| X-25 | **Tenant switch** | For IT-services deployments (SEC-23): a tenant selector in the Crown, hard visual separation (a tenant colour band), and a warning on any cross-tenant action. | MUST v1.x |

---

## Part D — Gaps the Prototype Exposed

Building `Sample_meridian-loom-gui.html` from the spec forced decisions the spec did not make. Each is now a spec gap.

| # | What the prototype had to invent | Spec resolution needed |
|---|---|---|
| P-01 | **Screen navigation** — VIGUIX has no nav element; the prototype added a tab row under the Crown. | Specify the nav: tabs vs. a screen switcher in the Crown vs. omnibar-only. Recommend a scrollable tab row with overflow into a menu, badges only for gates and questions. |
| P-02 | **Warp on narrow width** — the spec says "horizontal strip"; the prototype had to decide thread orientation, tooltip placement, and shed direction. | Add a narrow-width warp spec with those three decisions. |
| P-03 | **Halt All has no keyboard path** — press-and-hold is mouse/touch only. Violates §14. | E-GR-06. |
| P-04 | **Theme switching** is a cycle button; five themes need a picker with preview swatches. | Specify the theme picker (Config › Appearance and the Crown chip). |
| P-05 | **Inspector slide-over** has no backdrop, focus trap, or `Escape`. | E-IN-06, X-04. |
| P-06 | **Canvas accessibility parallels** are specified but there is no spec for *how* a user switches to them or whether they are always in the DOM. | Specify: always in the DOM, visually hidden, focusable via a "Table view" toggle per canvas. |
| P-07 | **Story selector** is a static chip. | E-CC-03. |
| P-08 | **Roster activity line** truncation, width, and what happens at 12+ agents were guessed. | X-22 and X-09. |
| P-09 | **Table on narrow width** scrolls the agent name off-screen. | E-AW-01, X-06. |
| P-10 | **No "as of" on panels** when data is stale; only a global concept. | E-CC-07, X-14. |
| P-11 | **Warp hover tooltips** are hover-only; unreachable by keyboard and touch. | Tooltip system: focusable triggers, `Escape` dismiss, touch long-press. |
| P-12 | **Fonts** — Commit Mono is not on Google Fonts; the prototype substituted JetBrains Mono. | Resolve V3 (licensing/subsetting) in G0 as `viguix-implementation.md` already requires; document the fallback stack. |
| P-13 | **Number-roll, shuttle-pass, beat-up, unravel** were approximated; `shed-open` was implemented. | No spec gap; implementation debt for G8. Listed for completeness. |
| P-14 | The **Dojo's 2.5D cards** and **Loop Graph's rings** were built flat-projected; label collision on narrow widths was solved by hiding labels. | Specify label-collision behaviour for both renderers (hide, abbreviate, or leader lines). |
| P-15 | **Rework reason taxonomy** did not exist to build against. | E-GR-03. |
| P-16 | **Empty states** were not built; the prototype is always populated. | No spec gap; G1 definition-of-done covers. |

---

## Part E — Accessibility & Inclusion Gaps

| ID | Gap | Priority |
|---|---|---|
| A-01 | **Press-and-hold** has no accessible alternative anywhere. | MUST v1 |
| A-02 | **Colour-blind simulation** (protanopia, deuteranopia, tritanopia) should be a CI check on the six themes, not only contrast ratio; the six dyes must remain distinguishable under all three. | MUST v1 |
| A-03 | **Canvas hit targets** — agents on the Floor are 13px circles; the spec's 28px minimum is violated. Specify an invisible enlarged hit area. | MUST v1 |
| A-04 | **Screen-reader narration for the Weave** — a table parallel is specified; add a **summary announcement** ("Story at row 14 of 26, Build phase weaving, Verify has 3 unravelled passes") so the shape of the cloth is available without reading 26 rows. | MUST v1 |
| A-05 | **Motion sickness** — the Floor's continuous bob and the Loop Graph's orbit need a per-canvas motion toggle independent of global reduced motion. | SHOULD v1 |
| A-06 | **Cognitive load** — the Command Center's four-second target needs a **simplified mode** (one weave, one gate list, one halt button) for new users and for incident conditions. | SHOULD v1 |
| A-07 | **Dyslexia-friendly option** — letter spacing and line height presets in Appearance. | COULD v2 |
| A-08 | **Sprite portraits** must not become the *only* identifier of an agent for screen-reader users; the name and id are always announced. | MUST v1 |

---

## Part F — Visual & Motion Refinements to Make It "Much More Better"

Not gaps in coverage; refinements that lift the product from correct to memorable.

| ID | Refinement |
|---|---|
| V-01 | **The Weave as a real texture.** Committed rows should render with a subtle over-under weave pattern (weft passing over odd warps, under even), so the cloth reads as cloth at every density. Cheap on the offscreen buffer; enormous for identity. |
| V-02 | **Agent-caused animations start at the agent.** VIGUIX §8.3 rule 3 is stated; make it literal — a `beat-up` on the Weave draws a brief thread from the roster portrait to the row. |
| V-03 | **Gate opening as light.** When a gate opens, the Gate Room on the Floor and the gate band on the Weave both gain a weld glow that decays over the wait — so "how long has this been waiting" is visible as brightness. |
| V-04 | **Halt is theatre, deliberately.** On Halt All, every shuttle stops *where it is* and the trailing thread stays drawn; nothing resets. Resume continues from the same pixel. The user should be able to see exactly what was mid-flight. |
| V-05 | **The selvage is tactile.** Locked stitches render with a 1px inner highlight and cast a 1px shadow onto the cloth, so the edge reads as raised. |
| V-06 | **Ambient sound as thread.** If sound is on, the shuttle click pans left-to-right with the pass. |
| V-07 | **Theme-aware sprites** are specified; add **state-aware posture** — an agent in rework sits back, an agent at a gate stands, an agent working leans in. Three poses × four directions. |
| V-08 | **Loading is weaving.** The first-run and any long initial load show the warp being strung thread by thread, left to right, and the first row woven. No progress bar. |
| V-09 | **Empty is an unstrung loom.** The empty-state illustration set (§12) should be one continuous drawing that gains threads as the user completes setup steps in S41. |
| V-10 | **The Observatory's meridian arcs** should share the Weave's warp positions when plotting per-phase metrics, so the two screens rhyme. |
| V-11 | **Typographic rhythm.** Set a 4px baseline grid and snap all text to it; Archivo Expanded for screen titles at exactly one size; never two display sizes on one screen. |
| V-12 | **Signature micro-interaction.** Hovering any agent token anywhere draws its thread to wherever else it appears on screen for 400 ms — the "where is Kenji" gesture. |

---

## Part G — Additional Features Worth Considering

Beyond gaps: capabilities that would make this the best GUI in the category.

| ID | Feature | Rationale | Priority |
|---|---|---|---|
| G-01 | **Agent cursors in the editor.** Live, named cursors showing where agents are editing in the story worktree, like multiplayer editing. The most visceral possible answer to "what is happening right now." | Presence for agents, not only humans | SHOULD v1.x |
| G-02 | **Minimap overlay** of agent-touched regions in the editor, coloured by state. | Orientation in large files | SHOULD v1.x |
| G-03 | **Explain-this-line** from the editor gutter → the decision record → the ablation, in one hover-and-click. | Makes XAI reachable without opening the dashboard | SHOULD v1 |
| G-04 | **Explicit feedback on outputs** — a thumbs signal on any artifact, with a reason chip, feeding the Trainer as weak signal distinct from gate decisions. | Humans have opinions between gates | SHOULD v1.x |
| G-05 | **Approval batching by risk class** with a policy-defined batch size. | Throughput without rubber-stamping | SHOULD v1.x |
| G-06 | **"What changed since I looked"** — on returning to the dashboard, a diff of the organisation's state since the user's last session. | Multi-day stories, part-time approvers | SHOULD v1 |
| G-07 | **Story Gantt** — phases and gates over calendar time with the SLA line, alongside the Weave (which is over ledger sequence, not time). | Two axes, two questions | SHOULD v1.x |
| G-08 | **Activity calendar heatmap** per agent and per repository. | Rhythm of the organisation | COULD v2 |
| G-09 | **Playback export** — an MP4 or animated SVG of a story's Weave building, for demos and retrospectives. | Comes almost free from S30 | COULD v2 |
| G-10 | **Contextual "why this gate"** — every gate criterion links to the policy line that created it and the commit that activated the policy. | Governance traceability | MUST v1.x |
| G-11 | **Comparison pinboard** — pin any two entities (agents, stories, candidates, weaves) and compare. | Analysis without leaving the product | SHOULD v1.x |
| G-12 | **Confidence-weighted colouring** — a toggle that renders every agent-produced element at opacity proportional to its calibrated confidence. Low-confidence work literally looks tentative. | Honest visual epistemics | SHOULD v1.x |
| G-13 | **Cost overlay** — a toggle that renders every element with its token cost, so the expensive parts of a story are visible. | Economics made spatial | SHOULD v1 |
| G-14 | **Human-time tracking** — the human's own time on gates, steers, and rework shown alongside agent cost (FR-M26-06). | True cost per change | SHOULD v1.x |
| G-15 | **Session handoff** — "I'm off; here is what needs deciding" generates a summary and assigns delegation. | Multi-day, multi-person | COULD v2 |
| G-16 | **Wall mode QR** — Focus Mode shows a QR that opens the same story on a phone's browser view of the ledger slice (read-only, signed bundle). | Governance meetings | COULD v2 |

---

## Part H — Decisions Required

| # | Tension | Recommended resolution |
|---|---|---|
| **T1** | **Nine phases are hard-coded** into the Warp Spine, the Weave, the Floor's 4×3 grid, and the phase-code abbreviations. Requirements §6 defines nine; nothing lets an organisation define six or twelve. | Make the phase set a policy artifact (id, code, name, colour role, gate). All renderers consume it. The Floor grid is computed from `ceil(sqrt(N+3))`. Two-letter codes are assigned by policy with collision checking. |
| **T2** | **The Command Center is spec'd for one story** but the product runs many (M21). | Command Center stays single-story by design; S26 Portfolio is the many-story view; the Crown story selector (E-CC-03) switches. State this explicitly. |
| **T3** | **Gate Room vs. Decision Stream** — two decision surfaces could split the mental model. | Gate Room = deliberate, high-blast-radius, one at a time, low density. Decision Stream = routine, keyboard-driven, batchable. Policy decides which gates go where; the user never chooses. |
| **T4** | **Notifications: interrupt-only vs. inbox.** VIGUIX §7.1 forbids notifications for anything but gates and breaches. S40 needs an inbox. | Keep the interrupt rule for toasts and OS notifications. The inbox is a *pull* surface and does not violate the rule. |
| **T5** | **Inspector is a sidebar; several new features need it to be pinnable, poppable, and comparative.** | Adopt X-17; the Inspector becomes a component that can host in the side panel, an editor tab, or a split. |
| **T6** | **Time-travel changes the meaning of every screen.** Nothing in VIGUIX says how a screen looks when it is showing the past. | Global time-travel state (S30) with a weld Crown banner, a desaturated selvage beyond the viewed seq, and every action except *Fork* disabled while viewing the past. |
| **T7** | **Currency.** Cost is shown in USD throughout. The organisation is Indian and bills globally. | Workspace currency setting with provider costs converted at a stored rate; the rate and its date are shown on hover. |
| **T8** | **The Floor is described as opt-in-able (V2 in VIGUIX §18) but the Floor is where speech bubbles and human presence live.** | Decide V2 now: Floor is default-on after first story; simplified mode (A-06) hides it. |
| **T9** | **Sprite art** — identity of agents depends on it, and it is the G4 schedule risk. | Approve a geometric-token fallback that is *designed*, not a placeholder: a circular token with a unique two-colour thread pattern per agent, so the product ships with identity even if portraits slip. |
| **T10** | **The prototype's tab navigation vs. the spec's silence on navigation.** | Adopt P-01's recommendation into VIGUIX §7.2 as "the Loom Bar": a scrollable tab row under the Crown with overflow. |

---

## Part I — Priority Summary and Implementation-Plan Impact

### Add to G0 (Foundation)
X-02 selection model · X-03 routing · X-04 dialogs · X-05 destructive pattern · X-06 table primitive · X-12 command registry · X-13 error boundaries · X-21 icon enumeration · T1 phase-set as data · T9 designed token fallback · A-02 colour-blind CI check.

### Add to G1 (Command Center)
S25 Story Hub · S40 Notification Center · S42 Keyboard Map · X-01 Omnibar · X-11 notification model · X-14 degraded modes · X-22 roster scaling · E-CC-01/02/03/05/07 · E-AW-01/02/05 · E-IN-02/04/06 · A-01 · A-03 · P-01…P-11.

### Add to G2 (Weave / Ledger)
E-WV-01/02/04/07 · E-LG-01/06 · S30 (developer-facing part) · V-01 · V-05.

### Add to G3 (Decision Surfaces)
S27 Decision Stream · S28 Steer & Clarify · S29 Partial acceptance · E-GR-02/03/04/05/06 · E-SS-02/03 · E-VB-01 · X-18 undo semantics.

### Add to G4 (Floor)
E-FL-01/02/06/07 · V-03 · V-04 · V-07 · T8.

### Add to G5 (Graphs)
E-CM-01/05 · E-LP-02 · P-14.

### New phase — G6.5 (Organisation Surfaces), before G7
S26 Portfolio · S33 Roles · S34 Connectors · S35 Delivery Pipeline · S36 Repositories · X-15 presence · X-25 tenant switch · E-FL-03.

### Add to G7 (Governance & Learning)
S31 Memory Studio · S32 Routing Observatory · S37 Documentation · S38 Calibration & Trust · S39 Runtime · E-DJ-01/03 · E-CF-01…06 · E-SF-01/02 · E-SA-01 · E-KP-01/03.

### Add to G8 (Refinement)
S41 First-run (already there; now designed) · X-10 localisation · X-16 personalisation · X-17 multi-panel · X-24 print · V-02/06/08…12 · G-03/06/12/13 · P-13.

### Defer to v2
G-08/09/15/16 · E-WV-06 · E-EX-02 · A-07.

---

*Every item above is written to be lifted into `VIGUIX.md` or `viguix-implementation.md` unchanged once accepted.*
