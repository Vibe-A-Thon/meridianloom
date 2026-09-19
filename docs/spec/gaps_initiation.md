# Meridian Loom — Run Initiation Gap

| | |
|---|---|
| **Document** | gaps_initiation.md |
| **Version** | 1.0 — proposed, for review |
| **Author** | Ravaleedhar Reddy |
| **Question answered** | "To trigger work directly from the Meridian Loom UI or a VS Code command, do we need to change the existing files?" |
| **Answer** | **Yes — three files, additively. One new module (11 requirements), one new screen, one data model, two acceptance criteria, one security requirement.** |

---

## 1. What is already covered

The plumbing exists. This is not a rewrite.

| Capability | Where | Status |
|---|---|---|
| `meridian.ingestStory` command registered | `FR-M1-03` | ✅ Exists |
| Intake accepts **direct text entry**, not only a file or connector | `FR-M1-01`… specifically `FR-P1-01` | ✅ Exists |
| Omnibar with a commands scope and natural-language commands | `X-01` | ✅ Exists |
| Chat participant with `/ingest` | `FR-M24-01` | ✅ Exists *(gated on `D11`)* |
| Dry-run / plan-only mode | `FR-M25-06` | ✅ Exists |
| Story Hub with Dry-run, Pause, Abort | 10.25 | ✅ Exists — **but only for a story that already exists** |
| Cost estimate at ingest | `FR-M26-01` | ✅ Exists |

---

## 2. What is missing

Six gaps. None is large; together they are the difference between a system you can *observe* and a system you can *start*.

| # | Gap | Why it matters |
|---|---|---|
| **1** | **No launch surface anywhere.** There is no screen, panel or view where a human composes a request, chooses what will run it, and presses go. 10.25 Story Hub is post-hoc — it shows a story that already exists. | The product has 44 screens and no start button. |
| **2** | **No launch configuration model.** Which adapter fills which role for *this* run? What budget ceiling? Which base branch? Dry-run or live? Autonomy override for this run only? | Without it, every run uses global defaults, which is wrong the moment two runs differ. |
| **3** | **No preflight.** Nothing between "press go" and an autonomous system spending money and writing code. | You are asking a human to authorise something they cannot see. |
| **4** | **No single intake contract.** Chat `/ingest`, the command palette, the UI and a dropped file could each shape the ledger's origin record differently. | Four doors, four provenance shapes, and "how did this run start?" becomes unanswerable. |
| **5** | **No editor-context trigger.** Right-click a file, a selection or a diagnostic → start a run about *that*. `FR-M24-03` has code actions but they are P4-tier and not wired to a run. | The cheapest, most natural trigger point is unused. |
| **6** | **No tiering answer.** In Flight Recorder there is no Meridian agent to trigger. Nothing says at which tier initiation becomes available. | A user in the base tier will look for a start button that should not exist. |

---

## 3. The one design decision

**One intake contract. Many doors.**

Every path — UI, command palette, Omnibar, chat participant, editor context menu, dropped file, connector webhook — produces the *same* `RunRequest` object and hands it to the same `IntakeOrchestrator` entry point. The door is recorded as an `origin` field; nothing else about the run differs by door.

```
UI Launch screen ─┐
Command palette ──┤
Omnibar ──────────┤
@meridian /ingest ┼──→  RunRequest (§5)  ──→  Preflight  ──→  IntakeOrchestrator
Editor context ───┤                              │                    │
Dropped file ─────┤                              │                    └─→ ledger: origin recorded
Connector ────────┘                              └─→ human authorises or cancels
```

This is the whole design. Everything below implements it.

---

## 4. New module — M40 Run Initiation

*Work & delivery.* Add to `Requirements_Final.md` §5 after M39.

| ID | Requirement | Priority |
|---|---|---|
| FR-M40-01 | All initiation paths SHALL construct a single **`RunRequest`** (§5 below) and SHALL invoke one `IntakeOrchestrator` entry point. No path SHALL have a private route into the runtime. | MUST v1 |
| FR-M40-02 | The `RunRequest` SHALL record its **`origin`** — `ui` · `command` · `omnibar` · `chat` · `editor` · `file` · `connector` · `api` — and the origin SHALL be written to the ledger with the run's first entry. | MUST v1 |
| FR-M40-03 | **Preflight is mandatory.** No run SHALL start without the human being shown, and confirming: the parsed intent echoed back in Meridian's words; the adapters that will fill each role; the repository, base branch and worktree path that will be created; the cost estimate with its interval and the ceiling that will apply; the gates the run will stop at; and whether this is a dry-run or a live run. | MUST v1 |
| FR-M40-04 | **Dry-run is the default** for the first run in a workspace, and for any run whose estimated cost exceeds a configurable threshold. Live runs require an explicit change from the default, per run. | MUST v1 |
| FR-M40-05 | **Launch authority** SHALL be role-checked (`FR-M20-02`): policy defines which roles may start a dry-run and which may start a live run. The authorising identity SHALL be recorded in the ledger with the run's first entry. | MUST v1 |
| FR-M40-06 | The `RunRequest` SHALL carry a **per-run override set** — adapter selection per role, autonomy tier, budget ceiling, model-call ceiling, base branch, gate profile — each defaulting to policy and each recorded in the ledger when overridden. | MUST v1 |
| FR-M40-07 | **Content provenance in the composer.** Text in a `RunRequest` SHALL be tagged by how it arrived — `typed` · `pasted` · `file` · `selection` · `connector`. Pasted content above a configurable length, and all `file`, `selection` and `connector` content, SHALL pass the injection classifier (`SEC-15`) before entering agent context, and detections SHALL be surfaced in preflight. | MUST v1 |
| FR-M40-08 | **Editor-context initiation** SHALL be available: on a file, a selection, a diagnostic, or a set of changed files, producing a `RunRequest` pre-populated with that context and its `selection` provenance tag. | SHOULD v1 |
| FR-M40-09 | A run SHALL be **cancellable at preflight without side effects** — no worktree, no branch, no ledger entry beyond a `run_cancelled_at_preflight` record. | MUST v1 |
| FR-M40-10 | **Run templates** SHALL be savable: a named `RunRequest` skeleton (adapters, tier, budget, gate profile) reusable across stories, stored in policy and version-controlled. | SHOULD v1.x |
| FR-M40-11 | Initiation SHALL be available only at the **Governor tier and above** (`FR-M36-05`). In Flight Recorder the initiation surfaces are not registered — not disabled, not present (`X-28`, banned pattern 30). | MUST v1 |

---

## 5. New data model — §7.11 RunRequest

Add to `Requirements_Final.md` §7.

```json
{
  "run_id": "run_01J8X…",
  "origin": "ui",
  "origin_detail": { "screen": "10.51", "user": "vikram@example.com" },
  "created_at": "2026-09-03T09:14:02Z",
  "authorised_by": "vikram@example.com",
  "authority_check": { "role": "Approver", "permitted": ["dry_run", "live_run"] },

  "intent": {
    "text": "Add an idempotency key to the payment submission endpoint",
    "provenance": "typed",
    "attachments": [
      { "kind": "file", "path": "EDB-12345.txt", "provenance": "file",
        "injection_scan": { "run": true, "detections": 0 } }
    ],
    "editor_context": null
  },

  "target": {
    "repos": ["payments-service"],
    "base_branch": "main",
    "branch": "meridian/run_01J8X",
    "worktree": ".meridian/worktrees/run_01J8X/"
  },

  "execution": {
    "mode": "dry_run",
    "adapters": { "Analyst": "analyst@2.1.0", "Developer": "acme-java-dev@2.3.0" },
    "autonomy_override": null,
    "gate_profile": "default",
    "budget": { "cost_usd_ceiling": 6.00, "model_call_ceiling": 40 },
    "phase_set": "default-nine"
  },

  "preflight": {
    "shown_at": "2026-09-03T09:14:19Z",
    "estimate": { "cost_usd": 3.10, "interval": [2.10, 5.40], "duration_min": 42 },
    "gates_expected": ["DoR", "Design", "DoD", "Security", "Review"],
    "confirmed": true
  }
}
```

**Amend `FR-M10-01`'s ledger schema** with `run_id` and `origin` on the run's first entry, so every story traces to how it was started.

---

## 6. New screen — 10.51 Launch

Add to `VIGUIX_Final.md` §10. **MUST v1 · Governor tier.**

```
┌ LAUNCH ─────────────────────────────────────────────────────────────────┐
│ ┌─ WHAT ────────────────────────────────────────────────────────────┐   │
│ │ Add an idempotency key to the payment submission endpoint.        │   │
│ │ Duplicate submissions with the same key return the original.      │   │
│ │                                              ⌨ typed · 142 chars  │   │
│ │ [+ Attach story file]  [+ Use editor selection]  [+ From Jira]    │   │
│ └───────────────────────────────────────────────────────────────────┘   │
│ ┌─ WHO ──────────────────────┐ ┌─ WHERE ───────────────────────────┐   │
│ │ Analyst    analyst@2.1.0 ● │ │ payments-service                   │   │
│ │ Architect  architect@2.1 ● │ │ base  main                         │   │
│ │ Developer  acme-java ◐ br. │ │ branch meridian/run_01J8X (new)    │   │
│ │ QA         qa@2.1.0      ● │ │ worktree .meridian/worktrees/…     │   │
│ │            [change roles]  │ │ your working tree is untouched     │   │
│ └────────────────────────────┘ └────────────────────────────────────┘   │
│ ┌─ HOW MUCH ─────────────────┐ ┌─ WHERE IT WILL STOP ──────────────┐   │
│ │ est. $3.10  (2.10 – 5.40)  │ │ ◈ Definition of Ready              │   │
│ │ ceiling $6.00   40 calls   │ │ ◈ Design approved                  │   │
│ │ est. 42 min                │ │ ◈ Definition of Done               │   │
│ │ [adjust]                   │ │ ◈ Security · ◈ Review · merge      │   │
│ └────────────────────────────┘ └────────────────────────────────────┘   │
│                                                                          │
│  ◉ Dry-run — plan and cost only, writes nothing   ○ Live run             │
│                                                                          │
│  Starting as Vikram (Approver) · recorded in the ledger                  │
│                                        [Cancel]  [Start dry-run ⏎]       │
└──────────────────────────────────────────────────────────────────────────┘
```

**Four questions, answered before the button:** *what*, *who*, *where*, *how much* — plus *where it will stop*. That is the preflight of `FR-M40-03`, and it is the whole screen.

**Design notes:**

- **The composer is one field, not a form.** Attachments and editor selections are additive chips with their provenance tag visible (`FR-M40-07`). Pasted content over the threshold shows the injection-scan result inline before it can be submitted.
- **`WHO` shows adapters, not roles in the abstract** — with `ProvenanceTag` (● prebuilt · ◐ bridged · ○ custom) so the user sees whose agent will do the work.
- **`WHERE` states the worktree promise explicitly**: "your working tree is untouched." That sentence is the product's core safety claim and it belongs on the launch screen, not buried in documentation.
- **Dry-run is pre-selected** (`FR-M40-04`). Switching to Live is one deliberate click, and above the cost threshold it requires the hold pattern (`X-05`).
- **The authorising identity is stated on the screen**, not just recorded. "Starting as Vikram (Approver)" makes `FR-M40-05` visible rather than silent.
- **Cancel is free** (`FR-M40-09`) — nothing is created until Start.
- **Empty state:** "Nothing running. Describe what you want, or press ⌘K and type *launch*."

---

## 7. Surfaces that reach the Launch screen

| Surface | Behaviour | Requirement |
|---|---|---|
| **Command palette** | `Meridian: Start a run` → opens 10.51 empty. `Meridian: Dry-run from file…` → opens 10.51 with the file attached. | `FR-M1-03` extended |
| **Omnibar (⌘K)** | Typing intent text directly, then `⏎`, opens 10.51 with that text as `typed` intent. | `X-01` extended |
| **Editor context menu** | Right-click a file, selection or diagnostic → *Meridian: Start a run about this* → 10.51 with `selection` provenance. | `FR-M40-08` |
| **Command Center** | A primary **Start a run** action in the Crown, present only at Governor+. | 10.1 amendment |
| **Story Hub** | *Re-run*, *Run a follow-up* — 10.51 pre-populated from an existing story. | 10.25 amendment |
| **Notification Center** | An unanswered clarifying question or a failed gate offers *Re-run with a steer*. | 10.39 amendment |
| **Chat participant** | `@meridian /ingest <text>` builds the same `RunRequest`. **Preflight still applies** — the chat reply is the preflight card, and the run does not start until confirmed. | `FR-M24-01` amendment |
| **Dropped file** | Dropping a story file onto the Command Center or Story Hub opens 10.51 with it attached. | 10.1 amendment |

**All eight produce the same `RunRequest` and all eight go through preflight.** No door skips it — including chat, which is the one most likely to be argued as an exception and is exactly where an unconfirmed run is most dangerous.

---

## 8. New security requirement

Add to `Requirements_Final.md` §9.

| ID | Requirement | Priority |
|---|---|---|
| SEC-30 | **Initiation is an authenticated, authorised, recorded act.** A run SHALL NOT start without an authenticated identity (`FR-M20-01`), a policy-permitted role for the run mode (`FR-M40-05`), and a ledger entry recording who authorised it, from which origin, with which overrides. An unauthenticated session SHALL be unable to start a run, including via the chat participant or the command palette. | MUST v1 |

---

## 9. New acceptance criteria

Add to `Requirements_Final.md` §10.1.

| # | Criterion |
|---|---|
| **AC-38** | A run started from the Launch screen, the command palette, the Omnibar, the editor context menu and `@meridian /ingest` produces five ledger records that differ **only** in their `origin` field. Preflight is shown and confirmed in all five cases. |
| **AC-39** | A run cancelled at preflight leaves no worktree, no branch and no ledger entry other than `run_cancelled_at_preflight`. Verified on the filesystem and in git. |
| **AC-40** | With the Governor tier disabled, no initiation surface is registered — no command, no Omnibar entry, no context-menu item, no Crown action — and the Flight Recorder tier is otherwise unaffected. |

---

## 10. Where it lands in the phases

| Phase | What | Why there |
|---|---|---|
| **F0 / GF0** | Nothing. Flight Recorder observes; it does not initiate (`FR-M40-11`). | There is no Meridian agent to start. |
| **F1 / GF1** | **All of M40**, screen 10.51, the eight surfaces, `SEC-30`, `AC-38`…`AC-40`. | The Governor tier is where hosted agents first exist, so it is the first tier at which "start" means anything. |
| **F3 / GF3** | `FR-M40-10` run templates; the Story Hub and Notification Center re-run paths. | Templates only pay off once there are enough runs to have patterns. |

In the pre-repositioning plan (`Requirements-implementation.md` v2.0), this is **C2 Workstream E**, alongside the connectors and the chat participant.

---

## 11. Precisely which files change

| File | Change | Size |
|---|---|---|
| **`Requirements_Final.md`** | Add M40 to §5 · §7.11 `RunRequest` to §7 · `SEC-30` to §9 · `AC-38`…`AC-40` to §10.1 · extend `FR-M1-03`'s command list · add `run_id` and `origin` to the `FR-M10-01` schema · add M40 to the §4.3 module map and the §17 index | **~11 requirements + 1 model.** Additive; nothing renumbered. |
| **`VIGUIX_Final.md`** | Add 10.51 Launch to §10 · amend 10.1 (Crown action, drop target), 10.25 (re-run), 10.39 (re-run with steer), 10.43 (adapter selection reachable from Launch) · extend `X-01` Omnibar with intent-to-launch · add 10.51 to §23 coverage and index | **1 screen + 4 amendments.** |
| **`gaps_guix.md`** | Add 10.51 to the GF1 screen list; note that initiation is Governor-tier and absent from Flight Recorder (`X-28`, banned 30) | **2 lines.** |
| **`Requirements-implementation.md`** | Add M40 to C2 Workstream E and the §21 traceability table | **2 lines.** |
| **`gaps_implementation.md`** | Add M40 to F1 Workstream A and the §20 traceability table | **2 lines.** |
| **`gaps_guix_implementation.md`** | Add 10.51 to GF1 Workstream A and the §19 appendix | **2 lines.** |
| **`vision.md`** | No change. The metaphor and architecture already accommodate it. | — |
| **`meridian-loom-gui.html`** | Optional — add a Launch screen to the prototype to test the preflight layout | Worth doing; it is the screen most likely to need iteration. |

**Nothing is renumbered. Nothing is superseded. No existing ID changes.**

---

## 12. The two things worth arguing about

**Dry-run as the default (`FR-M40-04`).** It adds a click to every live run. The argument for it: the first time a team starts a run, they do not yet know what the system will do, and a plan-and-cost output is a far better first experience than an unexpected branch and a bill. After the first successful live run in a workspace, a setting can flip the default. I would ship it defaulted-on and let teams turn it off deliberately.

**Preflight on the chat path.** It is tempting to let `@meridian /ingest fix the flaky test` just go, because that is what chat feels like. Do not. Chat is the path where intent is least specified, where pasted content is most likely, and where the human is least likely to be looking at cost. The preflight card in the chat reply costs one confirmation and prevents the class of incident that ends pilots.

---

*Every item above is written to be lifted into the named file unchanged once accepted.*
