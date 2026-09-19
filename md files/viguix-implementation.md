# VIGUIX Implementation Plan

| | |
|---|---|
| **Document** | viguix-implementation.md |
| **Version** | **2.0 — updated against VIGUIX_Final.md** |
| **Supersedes** | viguix-implementation.md v1.0 |
| **Author** | Ravaleedhar Reddy |
| **Governs** | The build order for everything specified in `VIGUIX_Final.md` v2.0 |
| **Companions** | `VIGUIX_Final.md` (design system, 42 screens) · `Requirements_Final.md` (30 modules) · `vision.md` · `meridian-loom-gui.html` (working prototype) |
| **Scale** | 10 phases · 42 screens · 25 cross-cutting systems · 232 tracked interface items |

---

## 0. About This Update

### 0.1 What changed

v1.0 of this plan sequenced 24 screens across 9 phases. `VIGUIX_Final.md` v2.0 raised that to **42 screens plus 25 cross-cutting systems**, and introduced ten resolved decisions that change *how* several existing phases are built, not just what they contain.

Four substantive changes:

1. **A tenth phase.** `G6.5 — Organisation Surfaces` is inserted between Modelling and Governance, holding the five screens that only make sense once there is more than one story, more than one human, and more than one repository.
2. **G0 grew significantly.** Eleven cross-cutting systems are now foundation work, because every screen after G0 depends on them. Building the table primitive or the destructive-action pattern per-screen is how design systems rot.
3. **Every v2.0 item is assigned to a phase.** `VIGUIX_Final.md` §21 left 52 items unassigned — see §0.2. All are placed here.
4. **T1 changes the foundation.** The phase set became a policy artifact. That is a G0 data-model task with consequences in G2 and G4, not a later refinement.

### 0.2 Items §21 left unassigned — now placed

`VIGUIX_Final.md` §21 assigns items by phase but omits 52 of them. Six are **MUST v1**, which means a strict reading of §21 would ship v1 without them. Each is assigned below and marked `[§21 gap]` at its phase.

| Namespace | Unassigned in §21 | Assigned here |
|---|---|---|
| **X-** (MUST v1) | X-07 chart grammar · X-08 markdown & agent-output rendering · X-09 agent copy rules | G0, G0, G1 |
| **X-** (SHOULD v1) | X-19 context menus · X-20 drag and drop · X-23 developer mode | G1, G3, G0 + G2 |
| **P-** | P-12 font fallback · P-15 rework taxonomy · P-16 empty states | G0, G3, definition of done |
| **A-** | A-06 simplified mode · A-08 portrait announcement | G8, G7 |
| **E-** (42 items) | see the traceability appendix (§12) | G0 – G8 |
| **G-** | G-01, G-02, G-04, G-05, G-06, G-07, G-10, G-11, G-14 | G8, G8, G8, G6.5, G1, G6.5, G6.5, G8, G7 |

### 0.3 One naming note

`G6.5` is an awkward phase identifier. It is kept rather than renumbering `G7 → G8` and `G8 → G9`, because `VIGUIX_Final.md` §21 and §23 reference the later phases by their existing numbers and silent renumbering breaks those references. **Treat G6.5 as a full phase with a full exit gate**, not a half-step.

---

## 1. How to use this document

Ten phases, G0 through G8 (with G6.5). Each is independently shippable and leaves the product usable. Each has a hard exit gate — the next phase does not start until the previous one's exit criteria are met and its performance budgets are green in CI.

The GUI phases interleave with the engineering phases in `Requirements_Final.md` §12:

```
Engineering   P0 Foundation ─── P1 First Value ─── P2 Quality Gates ─── P3 Orchestration ─── P4 Portability
GUI              G0   G1            G2  G3  G4          G5   G6            G6.5   G7             G8
```

**The rule that governs the whole plan, unchanged from v1.0:** a screen is not built until the data behind it is real. No screen ships against mock data. If the sidecar cannot yet produce a live weave, the Weave is not built. This prevents the most common failure mode in dashboard projects — a beautiful UI wired to fixtures that never survives contact with real telemetry.

---

## 2. Build Principles

B1–B7 carry over from v1.0. B8–B12 are new, each derived from a v2.0 decision.

| # | Principle | Consequence |
|---|---|---|
| B1 | **Tokens before components, components before screens.** | No screen is built from ad-hoc CSS. If a screen needs something the library lacks, the library grows first. |
| B2 | **Every screen ships with all four states.** | Loading, empty, error and populated. A screen with only the happy path is not done. |
| B3 | **Accessibility is built in, never retrofitted.** | Keyboard path and non-colour encoding are part of the first commit for any component, not a later ticket. |
| B4 | **Performance budgets are CI gates, not aspirations.** | A regression over budget fails the build in the same way a failing test does. |
| B5 | **The dense register precedes the spatial one.** | The table version of Agents Watch ships before the Floor. If the Floor slips, the product still works. |
| B6 | **Motion last, within each phase.** | Build with instant transitions, then add the named animation. This guarantees the reduced-motion path is the one that actually works. |
| B7 | **Visual regression from G0.** | Every component and screen has snapshot coverage across all six themes from the day it lands. |
| **B8** | **Nothing hard-codes the phase set.** *(T1)* | Phase count, codes, names and colour roles come from policy. A component that assumes nine fails review. Banned pattern 24. |
| **B9** | **Every destructive action has three access paths.** *(A-01, X-05)* | Pointer hold, keyboard hold, and a two-step confirm. Built once as a primitive in G0, never re-implemented. |
| **B10** | **Every canvas ships with its DOM parallel in the same commit.** *(P-06, §12.5)* | The parallel is always in the tree, not generated on demand. A canvas merged without one is incomplete, not "pending accessibility work". |
| **B11** | **Cross-cutting systems are built once, in G0 or G1.** | Context menus, tables, dialogs, routing and the command registry are foundation. Twenty-five per-screen implementations is the failure this principle exists to prevent. |
| **B12** | **Confidence never renders without calibration; rationale never renders without its label.** | Two component-level invariants enforced by the primitives themselves (`ConfidenceBar`, `RationaleBlock`), so no screen can violate them by omission. |

---

## 3. Stack Decisions

Settle these in G0. Changing them later is expensive. Rows marked **new** were added or changed by v2.0.

| Concern | Decision | Rationale |
|---|---|---|
| Framework | **React 18 + TypeScript**, strict | Team familiarity; VS Code webview ecosystem is React-centric |
| Build | **Vite** with a webview-targeted config | Fast, well-trodden nonce/CSP handling for webviews |
| Styling | **CSS custom properties + CSS Modules.** No CSS-in-JS runtime. | Tokens must be inspectable and themeable at runtime; a runtime style engine fights the VS Code theme bridge and costs bundle |
| State | **Zustand** for UI state; server state via the message bus with a normalised cache | Small, no provider tree |
| Message bus | Hand-rolled typed bus over `postMessage`, discriminated union, **schema-versioned**, generated types shared with the extension host | Contract must be checkable at handshake (`FR-M3-08`) |
| Canvas 2D | **Plain Canvas 2D API** for Weave and Floor | Full control of the draw loop |
| WebGL graphs | **PixiJS** for CodeMap at scale | Mature, good text handling |
| SVG graphs | **D3 force + custom React renderer** under 300 nodes | Crisp, accessible DOM nodes where scale permits |
| Diagram layout | **ELK.js** in a Web Worker for UML and C4 orthogonal layouts | Dagre is not sufficient for C4 |
| Diff | **Monaco diff editor** (already in VS Code) | Native look, free syntax highlighting |
| Charts | **Custom SVG components** on the token system, governed by X-07 | Stock chart libraries import a foreign visual language and break §18 |
| **Command registry** *(new)* | A single typed registry: id, label, shortcut, screen scope, handler. The Omnibar, Loom Bar, keyboard map and context menus all generate from it. | X-01, X-12, X-19 and 10.41 derive from one source or they drift |
| **Routing** *(new)* | Serialisable route object `{screen, entity, filters, viewSeq}`, restored via `setState`, deep-linkable as `meridian://` | X-03, T6. Time-travel is part of the route, not a screen-local flag |
| **Phase-set consumer** *(new)* | A typed `PhaseSet` provider; renderers subscribe. No component reads a literal phase list. | B8, T1 |
| **Hold-control primitive** *(new)* | One component implementing pointer hold, keyboard hold, filling ring, and two-step fallback | B9, A-01, X-05 |
| **Fonts** *(new)* | Archivo + **Commit Mono, self-hosted and subset**. Documented fallback: `'Commit Mono','JetBrains Mono',ui-monospace,'SF Mono',Menlo,Consolas,monospace`. | P-12. **`V3` licensing must close in week 1 of G0** — it blocks the font pipeline |
| Testing | Vitest · Testing Library · **Playwright** for webview E2E · visual snapshots across six themes · **axe-core** · **colour-blind simulation** | A-02 adds the third visual check |
| Storybook | Yes, from G0, with theme, density and phase-set switcher addons | The component library is the deliverable of G0 |

---

## 4. Phase Map

| Phase | Name | Screens delivered | Depends on |
|---|---|---|---|
| **G0** | Foundation | — (design system, shell, 11 cross-cutting systems) | Engineering P0 |
| **G1** | Command Center | 10.1, 10.4, 10.16, 10.25, 10.39, 10.41 | Engineering P0 |
| **G2** | The Weave | 10.3, 10.7, 10.29 *(developer-facing)* | Engineering P1 |
| **G3** | Decision Surfaces | 10.6, 10.17, 10.18, 10.19, 10.20, 10.27, 10.28 | Engineering P1 |
| **G4** | The Floor | 10.2, 10.24 | Engineering P1 |
| **G5** | Graph Register | 10.8, 10.9 | Engineering P2 |
| **G6** | Modelling Surfaces | 10.10, 10.11, 10.12 | Engineering P2 |
| **G6.5** | Organisation Surfaces | 10.26, 10.32, 10.33, 10.34, 10.35 | Engineering P3 |
| **G7** | Governance & Learning | 10.5, 10.13, 10.14, 10.15, 10.21, 10.22, 10.23, 10.30, 10.31, 10.36, 10.37, 10.38 | Engineering P3 |
| **G8** | Refinement | 10.40, 10.42 + all polish | Engineering P4 |

**42 screens.** 10.29 is split across G2 (developer-facing) and G8 (user-facing polish).

---

## G0 — Foundation

**Goal.** Nothing user-visible except a shell. Everything downstream depends on this being right, so it is built properly once. **v2.0 made this phase materially larger** — eleven cross-cutting systems moved here because per-screen implementations of them is how the design system rots.

### Scope
Design tokens · density modes · theme engine · typography · component primitives · shell layout · message bus · **11 cross-cutting systems** · Storybook · CI gates.

### Tasks

**Tokens and theming**
1. **Token system.** All tokens from `VIGUIX_Final.md` §4 as CSS custom properties, one file per theme, plus a typed `tokens.ts` mirror.
2. **Density modes** (§4.4). Three token deltas — comfortable / compact / dense. Not per-component overrides. `E-CF-06`.
3. **Theme engine.** Six themes plus Follow VS Code. Resolution order per §5. `theme-crossfade` on switch. High-contrast force-switch to Iron Gall.
4. **Theme picker with live preview swatches** `[§21 gap — P-04]`. Six themes is past the point where a cycle control is acceptable.
5. **VS Code theme bridge.** Map `--vscode-*` onto the Meridian token set. Verify against the five most-used VS Code themes plus both high-contrast themes.

**Type**
6. **Close `V3`** — Archivo + Commit Mono licensing and subsetting for redistribution in a `.vsix`. **Week one. It blocks task 7.**
7. **Font pipeline.** Subset, bundle, load via `asWebviewUri` under nonce, `font-display: block`. Implement and visually verify the documented fallback stack `[§21 gap — P-12]`.
8. **Type scale** (§6.1) as utility classes and typed components, snapped to a **4px baseline grid** (`V-11`). Tabular numerics enforced on every data class.

**The phase set — T1**
9. **`PhaseSet` provider.** Phase set as a typed policy artifact: id, code, name, colour role, gate. Two-letter code collision checking. A Storybook addon that switches between a nine-phase and a six-phase set, so every component is exercised against both from day one.
10. **Warp Spine** driven by the provider, not a literal. Includes the >12-phase degradation (colour-only bars, codes on hover).

**Shell**
11. **Shell layout.** Crown, **Loom Bar** (`T10`, `P-01`), Warp Spine, main region, Inspector, Roster. Responsive at all four breakpoints, including the **narrow-width horizontal warp** with its tooltip and shed-direction rules `[P-02]`.
12. **Message bus.** Typed discriminated union, schema version, handshake with version check, and a **replay buffer** so a restored webview rehydrates without a round-trip storm.
13. **State persistence.** `getState`/`setState` wrapper with a typed schema and migration path. `WebviewPanelSerializer` registered. Verify: hide the panel, reload the window, state restores.

**Cross-cutting systems — the v2.0 addition to this phase**
14. **X-02 Selection model.** One shared selection across Roster, Floor, Weave, tables, graphs, Inspector. Multi-select semantics and canvas modifier behaviour defined once.
15. **X-03 Routing & restore.** Serialisable route including `viewSeq` for time-travel. Back/forward. Deep links.
16. **X-04 Dialog / sheet / drawer / panel.** Decision rules, focus trap, `Escape`, return-focus, backdrop. Every overlay in the product uses these.
17. **X-05 Destructive-action pattern + the hold primitive.** Pointer hold, keyboard hold, filling ring, two-step confirm, typed confirmation. `A-01`, `B9`.
18. **X-06 Data table primitive.** Sticky header **and sticky first column**, virtualisation, resize / reorder / pin, sort, filter, saved views, CSV export, row actions, bulk select, density modes, empty and loading states.
19. **X-07 Chart grammar** `[§21 gap]`. Axes, scales, legends, tooltips, annotations, colour rules, meridian-arc semantics, reduced-motion behaviour. **MUST v1 and unassigned in §21** — sparklines appear in G1, so this cannot wait for G7.
20. **X-08 Markdown & agent-output rendering** `[§21 gap]`. Sanitised subset, code blocks, tables, max width, external-link confirmation, mandatory "not verified" framing. **MUST v1.** Agent output renders in the G1 Inspector, so this is foundation.
21. **X-12 Command registry.** Every action registered with id, label, shortcut, scope. The Omnibar, Loom Bar, keyboard map and context menus generate from it.
22. **X-13 Error boundaries.** Per-screen, showing last-known state, error class, *Reload screen* / *Report*.
23. **X-21 Icon set enumeration.** Enumerate the 40–60 glyphs and their loom vocabulary; decide which Codicons are used where. Not "described" — listed.
24. **X-23 Developer mode, base** `[§21 gap]`. Frame-rate overlay, message-bus inspector, spec-ID overlay. Extended in G2 with the cassette panel.

**Primitives**
25. `Thread` · `AgentToken` (with the **28px padded hit area**, `A-03`) · `StateRing` · `MetricTile` · `PhasePill` · `LoopBadge` · `Timecode` · `ProvenanceStamp` (including model version) · `CostMeter` · `ConfidenceBar` · `RationaleBlock` · `EvidenceBlock` · `GateChip` · `EmptyState` · `BreachBanner` · `RiskBadge`.
26. **`ConfidenceBar` and `RationaleBlock` enforce their own invariants** (`B12`) — the components refuse to render without calibration context and without the unverified label.

**Art brief**
27. **Close `T9`.** Approve the **designed geometric token fallback** — a circular token with a unique two-colour thread pattern per agent — and build it. The product must ship with agent identity even if portraits slip.
28. **`E-OB-01` art-direction rules** `[§21 gap]`. Written and agreed *before* the commission: stylised, non-photoreal, no demographic identity signals, marketplace-policy compliant, diversity via silhouette / palette / accessory. **MUST v1 because it governs a long-lead commission (`V1`).**

**CI**
29. Storybook with theme, density and phase-set switchers.
30. **CI gates:** bundle size · axe-core on every story · visual snapshots across six themes · **colour-blind simulation across all six themes** (`A-02`) · long-task detection · contrast verification.

### Exit criteria
- [ ] All six themes render every primitive correctly; visual snapshots green
- [ ] **Colour-blind simulation passes: the six dyes remain mutually distinguishable under all three deficiencies**
- [ ] Follow VS Code correct in light, dark and both high-contrast themes
- [ ] **Every component renders correctly against both a nine-phase and a six-phase phase set**
- [ ] Shell responsive at all four breakpoints with no clipping; narrow-width warp behaves per `P-02`
- [ ] The hold primitive works by pointer, keyboard, and two-step confirm
- [ ] Panel hide → window reload → full state restoration, verified on all three platforms
- [ ] A route including `viewSeq` round-trips through serialisation
- [ ] Bundle under budget with fonts included; fallback stack visually verified
- [ ] axe-core clean across every story
- [ ] Zero long tasks over 50ms in the shell
- [ ] `V3` and `T9` closed; the art commission brief is issued

### Risks
Font licensing (`V3`) blocks task 7 — resolve in week one. The VS Code theme bridge is deceptively hard for high-contrast. **The eleven cross-cutting systems roughly double this phase against v1.0** — plan for it rather than discovering it.

---

## G1 — Command Center

**Goal.** First genuinely useful screen. An engineer can see what the agents are doing, ask them things, and stop them.

### Screens
**10.1** Command Center · **10.4** Agents Watch · **10.16** Agent Inspector · **10.25** Story Hub · **10.39** Notification Center · **10.41** Keyboard Map & Help

### Tasks

1. **Roster strip** with state rings, activity lines, token meters, keyboard nav `[` `]`, roving tabindex, and **X-22 scaling** — grouping, filter, "+N" overflow sheet, portraits-only compact mode.
2. **Agent Inspector**, seven tabs. Trace (with **`E-IN-02`** reuse-first citation and context-assembly sections), Terminal (**`E-IN-03`** follow/unfollow and send-input `[§21 gap]`), Diff, Memory, Policy, Messages (**`E-IN-04`** human message renders distinctly and lands in the ledger as a steer), **History** (**`E-IN-05`** `[§21 gap]`).
3. **`E-IN-06`** overlay Inspector gets backdrop, focus trap, `Escape`, return-focus — using X-04, not a bespoke implementation `[P-05]`.
4. **Agents Watch table** on X-06. **`E-AW-01`** sticky first column `[P-09]` · **`E-AW-02`** lifecycle column with time-in-state, retired collapsed not hidden · **`E-AW-03`** agent profile drill-down `[§21 gap — SHOULD v1]` · **`E-AW-05`** bulk actions with an affected-agent list.
5. **Story Hub (10.25).** Header, acceptance criteria with coverage, phase timeline with `SLABar`, cost with the what-if ceiling slider, linked artifacts, worktree panel, and the actions row including **Abort story** on the hold primitive.
6. **Live pass list** with loop badges and cost meters.
7. **`E-CC-02`** unanswered-questions tile beside Gates. An unanswered question stalls a loop exactly as an open gate does.
8. **`E-CC-03`** story selector — searchable, with phase, gate state and spend per row `[P-07]`.
9. **`E-CC-05`** weave hero interactions: row hover provenance, seq axis, drag-select range with cost.
10. **`E-CC-06`** signal rail filters, mark-all-read, link into 10.39 `[§21 gap]`.
11. **`E-CC-07`** per-panel "as of" freshness stamp `[P-10]`.
12. **X-14 degraded modes.** Four distinct states — sidecar down, provider down, connector down, verification failed — each with its own banner, permitted actions and recovery path. Not one generic "stale".
13. **X-01 Omnibar** on the command registry: scopes, ranking, recents, natural-language commands with a confirmation preview.
14. **X-19 context menus** `[§21 gap]`, generated from the same registry.
15. **X-09 agent copy rules** `[§21 gap]`. The webview-side validation and the sidecar contract: ≤48 chars status, sentence case, present tense, names the artifact, no emoji, no flattery.
16. **X-11 notification model** and **10.39 Notification Center** — inbox as a pull surface, inline actions, digest, snooze, channels. The interrupt rule for toasts is preserved (`T4`).
17. **10.41 Keyboard Map**, generated from the registry so it cannot drift.
18. **Halt All** with all three access paths (`A-01`, `P-03`), `halt-flash`, and the freeze-in-place behaviour (`V-04` groundwork).
19. **Status bar item** and the Activity Bar badge counting gates **and** unanswered questions.
20. **`G-06`** "what changed since I looked" `[§21 gap]` — a diff of organisation state since the user's last session.
21. **P-08** roster truncation and scaling rules; **P-11** focusable tooltips with `Escape` and touch long-press; **P-06** table-view toggles wired for any G1 canvas.

### Exit criteria
- [ ] Command Center answers "what is happening right now" in under four seconds for a first-time viewer — validated with five engineers who have not seen it
- [ ] Live state propagates sidecar → pixel in ≤1,000ms
- [ ] Halt All stops all work by pointer, keyboard and two-step; the frozen state is unmistakable
- [ ] Full keyboard operation; every action reachable from the Omnibar, a shortcut and a context menu, all from one registry
- [ ] Selection state shared correctly between Roster, table, Story Hub and Inspector
- [ ] All four states present on every element
- [ ] Sidecar down → the correct one of four degraded banners, not a generic message
- [ ] No agent-authored string renders unsanitised or without its "not verified" framing where applicable

---

## G2 — The Weave

**Goal.** The signature view. Story progress becomes a woven object, and the ledger becomes its edge.

### Screens
**10.3** The Weave · **10.7** Ledger / Selvage Viewer · **10.29** Replay & Time-Travel *(developer-facing part)*

### Tasks

1. **WeaveCanvas renderer** per §12.1: offscreen buffer for committed rows, live-only redraw, DPR-aware, virtualising above 2,000 rows.
2. **`E-WV-01`** warp generated from the `PhaseSet` provider. No literal phase list `[B8]`.
3. **`V-01` over-under weave texture**, drawn into the offscreen buffer so it costs nothing per frame.
4. **`V-05` tactile selvage** — 1px inner highlight, 1px cast shadow.
5. **`E-WV-02`** steer ticks and question markers on the rows they affected.
6. **`E-WV-03`** gate bands — height proportional to wait time `[§21 gap — SHOULD v1]`.
7. **`E-WV-07`** minimap with viewport rectangle at texture density.
8. **`E-WV-04`** PNG/SVG export at print resolution with legend and title block.
9. Row interactions: hover provenance, click to Inspector, drag-select aggregates, `Shift+Scroll` density compression 24px → 3px.
10. **Motion**, built instant-first per `B6`: `shuttle-pass`, `beat-up` (including **`V-02`** thread drawn from the causing agent's portrait), `selvage-lock`, `unravel`, `thread-tension`. Then verify the reduced-motion path.
11. **Ledger viewer.** Virtualised selvage strip, filterable entry stream, full entry detail including model version, inclusion/consistency proof inspection, signed audit bundle export.
12. **`E-LG-01`** query builder over `FR-M10-12` with saved queries.
13. **`E-LG-06`** deep links — `meridian://ledger/4417` resolving from chat, PR bodies and Jira comments.
14. **Verification banner.** Full-bleed halt border on failure, first divergent sequence named, everything below desaturated. **The verdict comes from the sidecar; the webview never computes it** (§12.4).
15. **Gutter decorations** on agent-authored lines, click-through to the ledger entry.
16. **`A-04` weave summary announcement** plus the table parallel `[B10]`.
17. **10.29 developer-facing:** the timeline scrubber, **T6 global time-travel state** (weld Crown banner, desaturated selvage beyond the viewed sequence, every action except Fork disabled), and **X-23 extended** with the cassette panel and fault-injection console `[§21 gap]`.

### Exit criteria
- [ ] 400-row weave renders at 60fps; 2,000 rows at ≥30fps with virtualisation
- [ ] A tampered ledger is impossible to overlook — verified by deliberately corrupting a test ledger
- [ ] Every visible pass traces to a real ledger sequence; no synthesised rows
- [ ] Time-travel is a route property, not a screen flag — it survives a reload
- [ ] While in the past, no action except Fork is reachable, including via the Omnibar
- [ ] Reduced-motion path fully functional and independently tested
- [ ] Density compression readable at every level from 24px to 3px
- [ ] Weave table parallel and summary announcement verified with a screen reader

### Risks
Canvas performance with high row counts on integrated graphics. Profile on a low-spec target machine in week one, not at the end.

---

## G3 — Decision Surfaces

**Goal.** The human can now govern, steer, and be asked. This phase makes the product safe to use on real work.

### Screens
**10.6** Gate Room · **10.17** Diff Theater · **10.18** Spec Studio · **10.19** Work Packet Board · **10.20** Verification Board · **10.27** Decision Stream · **10.28** Steer & Clarify

### Tasks

1. **Gate Room**, single-column, low density, with criteria, artifact, provenance, confidence-with-calibration, rationale marked unverified, evidence block, cost, and loop history.
2. **`E-GR-05`/`T3` gate routing.** Policy decides Gate Room vs Decision Stream. **The user never chooses.** Build the routing before either screen.
3. **`E-GR-02`** Steer as a fifth action. **`E-GR-03`** rework reason taxonomy — `incorrect · incomplete · out-of-scope · style · security · performance · test-quality · other`, each mapping to a Trainer signal class `[§21 gap — P-15]`. **`E-GR-04`** gate history: prior openings, prior reasons, L2 iteration count. **`E-GR-06`** hold paths on high-blast Approve.
4. **`gate-iris`** transition and the corner weave inset firing `beat-up` on approval.
5. **10.27 Decision Stream.** Keyboard-driven `J K A R E S ?`. **Approve stays disabled until the artifact has been scrolled into view.** Rubber-stamp detector (`FR-M20-06`) showing the approver their own median beside the organisation's. High-blast gates excluded and redirected.
6. **10.28 Steer & Clarify.** Steer composer with structured chips, target selector, and a preview of where the guidance enters context. Clarifying-question card with options, the agent's recommendation and per-option confidence. Uncertainty prompt with *Proceed anyway* / *Steer* / *Take over*.
7. **10.17 Diff Theater with tri-state hunks** (S29): accept / rework / **edit-in-place**, the diff-of-diffs before commit, moved-code detection, word-level intra-line diff.
8. **10.18 Spec Studio.** **`E-SS-02`** injected-instruction detections highlighted with the classifier's reason. **`E-SS-03`** ambiguity → clarifying-question link with the resolution flowing back.
9. **10.19 Work Packet Board.** Visual overlap detection blocking illegal parallelisation. **`E-WP-01`** critical path and estimate-vs-actual `[§21 gap]`. **`E-WP-02`** worktree and branch on the card `[§21 gap]`.
10. **10.20 Verification Board.** Criterion-to-test matrix with open madder cells blocking the gate. **`E-VB-01`** flake quarantine lane with retry history.
11. **X-18 undo semantics.** Which actions are reversible in-UI and which are ledger-final. **The UI must make the difference visible before the click.**
12. **X-20 drag and drop** `[§21 gap]` — roster → packet assign, queue reorder, with a keyboard equivalent for each.

### Exit criteria
- [ ] No path exists to approve without a recorded approver identity
- [ ] Rework always captures a taxonomy reason; the reason reaches the ledger
- [ ] Approve in the Decision Stream cannot fire before the artifact has been seen
- [ ] Confidence never displays without calibration anywhere in the product
- [ ] Agent rationale never displays without the unverified marking
- [ ] High-blast gates cannot be approved without ablation evidence present
- [ ] A criterion with no covering test visibly blocks its gate
- [ ] A steer injected from any surface appears in the next iteration's context and in the Weave
- [ ] An agent below its confidence threshold produces a question card, and answering resumes the loop
- [ ] Gate Room usable end-to-end by a delivery manager with no training

---

## G4 — The Floor

**Goal.** The ambient, watchable register.

**Deliberately after G3.** The product is already governable and useful without it. If art production (`V1`) slips, nothing else does — and `T9`'s geometric fallback, built in G0, means the Floor still ships.

### Screens
**10.2** The Loom Floor · **10.24** Focus Mode

### Tasks

1. **Sprite pipeline.** Atlas packing, indexed colour with runtime palette swapping. Commissioned art if `V1` resolved; the G0 geometric fallback otherwise.
2. **FloorCanvas renderer** per §12.2: orthographic, 24px grid, A* pathfinding, 8ms frame budget with the documented degradation ladder, pauses when hidden.
3. **`E-FL-01` room layout generated from the phase set**, grid computed as `ceil(sqrt(N+3))`. No drawn 4×3 `[B8]`.
4. **Position-as-state binding.** An agent's location is derived from real state, never animated independently of truth.
5. **`E-FL-02`** gate state on room doorframes using **`V-03` gate-glow** — brightness decaying over the wait, so "how long has this been waiting" is readable without a timestamp.
6. **`E-FL-06`** speech bubbles under the X-09 copy rules, enforced sidecar-side.
7. **`E-FL-07`** touch and keyboard access to room and agent selection. **`A-03`** 28px hit areas on canvas.
8. **`V-04`** Halt freezes every shuttle where it is, trailing threads still drawn, resuming from the same pixel.
9. **`V-07`** state-aware posture — three poses × four directions.
10. **`A-05`** per-canvas motion toggle, independent of global reduced motion.
11. **Floor List parallel**, always in the DOM `[B10]`, genuinely usable, with a banner explaining the substitution.
12. **10.24 Focus Mode.** Close **`V6`** first — separate panel or chrome-hiding state.
13. **Close `T8`:** Floor is default-on after the first completed story.

### Exit criteria
- [ ] 8ms frame budget held with 20 agents on a low-spec target machine
- [ ] Agent position always reflects real state — verified by driving state changes
- [ ] Room layout correct for both a nine-phase and a six-phase set
- [ ] Floor pauses fully when hidden; zero CPU when not visible
- [ ] Floor List is genuinely usable, not a stub
- [ ] Theme palette swap works on all sprites in all six themes
- [ ] Every agent is clickable at a 28px effective target; screen-reader users can enumerate rooms and agents

---

## G5 — Graph Register

**Goal.** The codebase and the execution topology become navigable.

### Screens
**10.8** CodeMap Viewer · **10.9** Loop Graph Viewer

### Tasks

1. **GraphCanvas.** PixiJS for scale; D3-force + React SVG under 300 nodes; force simulation in a Web Worker.
2. **Level of detail:** labels below 150 visible nodes, edge thinning below 2,000, cluster hulls with a notice above 5,000.
3. **`E-CM-01`** the graph source is **CodeMap JSON** (`ECO-03`), consumed not redefined; `.cgw` addressing for multi-repo (`ECO-04`).
4. **Semantic zoom**, three levels, crossfade not pop.
5. **Agent overlay** and **blast-radius projection**.
6. **`E-CM-02`** reuse-first / duplicate overlay `[§21 gap]` — nodes an agent nearly re-implemented, with the existing code it should have used.
7. **Rework heat.** Ship last within the phase and treat it as the headline feature; it is the most actionable view for a tech lead.
8. **`E-CM-05`** node detail drawer with LSP-derived references and definitions.
9. **10.9 Loop Graph** in 2.5D. **`E-LP-01`** three budget arcs — tokens, wall clock, cost. **`E-LP-02`** escalation edges terminating at the Gate Room. **`E-LP-03`** backpressure rendered as a held shuttle with the provider named `[§21 gap]`.
10. **`P-14` label-collision behaviour**, specified not improvised: below 620px labels move above the ring and abbreviate; below 420px only the active ring is labelled.
11. **2D fallback** for the Loop Graph, used automatically under reduced motion. Close **`V5`** here.
12. **Accessible parallels** — node and edge lists with relationships, keyboard traversal `[B10]`.

### Exit criteria
- [ ] 5,000-node CodeMap pans and zooms at ≥30fps
- [ ] Force simulation never blocks the UI thread — verified with long-task monitoring
- [ ] Rework heat correctly reflects ledger data, validated against a known-bad module
- [ ] Loop Graph budget arcs match real loop bounds exactly
- [ ] Labels never silently disappear — each collision mode is a specified behaviour
- [ ] Keyboard traversal reaches every node; no canvas keyboard trap

---

## G6 — Modelling Surfaces

**Goal.** Architecture and design documentation that regenerates itself and shows where reality has drifted.

### Screens
**10.10** Architecture & C4 · **10.11** UML Studio · **10.12** Flow Diagram Viewer

### Tasks

1. **ELK.js worker** for layered and orthogonal layouts.
2. **C4 four levels** with zoom-through transitions rather than screen swaps.
3. **Generation from source** — repository analysis plus Architect Agent ADRs, regenerating on change.
4. **Drift indicator.** Where documented architecture and actual code diverge, each divergence listed. The phase's headline feature.
5. **ADR annotations** opening in the Inspector with ledger provenance.
6. **UML Studio shell** — layout engine selector, routing options, focus+context dimming, diff mode, export to SVG/PNG/PlantUML/Mermaid.
7. **Seven diagram types in value order:** Sequence (including **agent sequence mode**) → Class → ER → Component → State → Activity → Deployment. **Agent sequence mode is the differentiator; build it first and well.**
8. **`E-AR-01`** contract artifacts on container edges with contract-test status. **`E-AR-02`** threat-model overlay with trust boundaries and STRIDE. **`E-AR-03`** diagram-as-gate mode with diff on by default.
9. **10.12 Flow viewer** with the criteria-vs-implemented overlay, uncovered branches hatched in madder.

### Exit criteria
- [ ] Every diagram regenerates from source; none is hand-maintained
- [ ] Drift indicator correctly identifies a deliberately introduced divergence
- [ ] Agent sequence diagram timings match ledger timestamps exactly
- [ ] Flow overlay correctly identifies a deliberately uncovered acceptance criterion
- [ ] Exports open correctly in external tools

---

## G6.5 — Organisation Surfaces *(new in v2.0)*

**Goal.** The product stops being about one story, one human and one repository. These five screens are what turn a tool into a delivery capability.

**Why its own phase.** Each depends on an engineering module that does not exist before P3 — M21 portfolio, M20 roles, M19 connectors, M23 CI, M22 multi-repo. Attaching them to G7 would make that phase unshippable as a unit.

### Screens
**10.26** Portfolio · **10.32** Human Roles & Approvals · **10.33** Connectors & Write-back · **10.34** Delivery Pipeline · **10.35** Repositories & Worktrees

### Tasks

1. **10.26 Portfolio.** Rows as **mini-weaves** — 3px-row fabric samples, so the portfolio reads as cloth. Queue lane with WIP limit and drag-to-reprioritise (X-20). Contention panel showing arbitration decisions. Filters by team, client, cost centre, tier, SLA-at-risk.
2. **10.32 Human Roles.** Who-am-I, roles matrix, delegation composer with expiry, **N-of-M `ApprovalProgress`**, **separation-of-duties explainer** naming the rule, the conflicting act and who can approve instead, and **approval hygiene** shown privately to the approver and in aggregate to Governors.
3. **`E-GR-01`** N-of-M progress and SoD block explanation inline on the Gate Room card `[§21 gap]`. Retro-fits into G3's screen.
4. **10.33 Connectors.** Cards, field-mapping editor with live preview, write-back rules with a preview of the comment and transition, Done-transition approval prerequisite shown as a locked rule, story templates, complexity-tier heuristics, batch import queue.
5. **`E-SS-01`** template conformance and complexity tier in Spec Studio `[§21 gap]`.
6. **10.34 Delivery Pipeline.** The L4 loop extended to merged-and-green. CI runs inline with re-entry rendered as a Weave rework row. Review-comment ingestion with agent and hunk attribution. CODEOWNERS assignment, merge-queue position. Multi-repo linked PRs with warp threads between repos.
7. **10.35 Repositories & Worktrees.** Per-story repo, branches, worktree path, disk, signed-commit indicator, retention countdown. **Conflict surface** listing human uncommitted changes overlapping a pending packet, with *Stash / Commit / Skip packet*. Workspace manifest editor for multi-repo.
8. **`E-FL-03`** multi-story floors — a floor per story, selector or stacked building view.
9. **X-15 Presence.** Who is viewing what, who holds a gate, avatars in the Crown, soft lock on a gate someone is deciding.
10. **X-25 Tenant switch.** Selector in the Crown, hard visual separation via a tenant colour band, warning on any cross-tenant action.
11. **`G-05`** approval batching by risk class `[§21 gap]`. **`G-07`** Story Gantt over calendar time alongside the Weave over ledger sequence `[§21 gap]`. **`G-10`** "why this gate" linking each criterion to the policy line and activating commit `[§21 gap]`.

### Exit criteria
- [ ] Ten concurrent stories render in the Portfolio without frame loss
- [ ] SoD blocks are explained, never silent — the rule and the alternative approver are always named
- [ ] A write-back cannot move a story to Done without a recorded human approval
- [ ] A CI failure appears as a rework row in the Weave with the failing job as its reason
- [ ] A human uncommitted change overlapping a pending packet is surfaced before the packet starts
- [ ] Cross-tenant action is impossible without an explicit warning and confirmation

---

## G7 — Governance & Learning

**Goal.** The organisation becomes configurable, extensible, curatable and self-improving through the interface.

### Screens
**10.5** Dojo · **10.13** Config Portal · **10.14** Skill Forge · **10.15** Onboarding · **10.21** Security Assurance · **10.22** KPI Observatory · **10.23** Exchange · **10.30** Memory Studio · **10.31** Routing Observatory · **10.36** Documentation · **10.37** Calibration & Trust · **10.38** Runtime & Operations

### Tasks

1. **Blast-radius preview mechanism first**, before any individual Config section. Every setting that changes agent behaviour shows what it affects before saving.
2. **10.13 Config Portal**, all sections. **`E-CF-01`** new sections (Roles, Phases, Routing, Connectors, Notifications, Tenants, Regulatory). **`E-CF-02`** git-backed policy with *Open PR* rather than *Save*. **`E-CF-03`** settings search. **`E-CF-04`** emergency fast path with countdown and Crown banner. **`E-CF-05`** kill switch per agent class with the affected list.
3. **10.30 Memory Studio.** Three layers with override arrows, tier tabs, `FreshnessBadge`, human-pinned entries agents cannot edit, **contradiction queue**, **untrusted holding area** with promote-requires-reason, **context assembly preview**, Markdown import/export with diff.
4. **10.31 Routing Observatory.** Routing matrix, live call stream, failover and backpressure timeline, provider health and residency compliance, redaction log, model comparison small-multiples.
5. **10.5 Dojo.** **`E-DJ-01`** six signal sources with counts. **`E-DJ-02`** Breaker results pane `[§21 gap]`. **`E-DJ-03`** policy diff with the ledger evidence motivating each change. **`E-DJ-04`** thread-styled sliders `[§21 gap]`. **`E-DJ-05`** rollback shelf persistent across sessions `[§21 gap]`. Promote gated on typed confirmation.
6. **10.14 Skill Forge.** **`E-SF-01`** upgrade flow with per-agent regression and hold. **`E-SF-02`** revocation with paused-agent list and rebind assistant. **`E-SF-03`** internal registry browser `[§21 gap]`. Install review treated and reviewed as a security surface.
7. **10.15 Onboarding.** Five steps, live probation scorecard, admission blocked on a failing score, `portrait-hire`. **`E-OB-02`** import path merges at the Probation step `[§21 gap]`. **`E-OB-03`** probation task-set editor `[§21 gap]`. **`A-08`** name and id always announced, portraits never the sole identifier `[§21 gap]`.
8. **10.37 Calibration & Trust.** `ReliabilityDiagram` per action class, `AutonomyLadder` with thresholds and promotion/demotion markers, trust-score decomposition.
9. **10.22 KPI Observatory** on X-07. **`E-KP-01`** the concrete chart set and annotation events. **`E-KP-02`** agent-vs-human baseline and token efficiency `[§21 gap]`. **`E-KP-03`** chargeback view. **`E-KP-04`** tech-debt registry with issue-tracker export `[§21 gap]`. **`E-KP-05`** alert thresholds feeding 10.39 `[§21 gap]`. **`G-14`** human-time tracking alongside agent cost `[§21 gap]`.
10. **10.21 Security Assurance.** **`E-SA-01`** tool permission matrix with denial heat cells. **`E-SA-02`** anomaly feed `[§21 gap]`. **`E-SA-03`** AI-BOM and attestation verification `[§21 gap]`. **`E-SA-04`** output-scan results `[§21 gap]`.
11. **10.7 extensions.** **`E-LG-02`** natural-language query with the resolved structured query shown. **`E-LG-03`** erasure UI confirming the chain still verifies. **`E-LG-04`** cold-storage indicator. **`E-LG-05`** shareable signed HTML slice. All `[§21 gap]`.
12. **10.8 extensions.** **`E-CM-03`** freshness overlay. **`E-CM-04`** time-scrub integration. Both `[§21 gap]`.
13. **10.20 extensions.** **`E-VB-02`** mutation score, performance regression, accessibility and contract-test rows. **`E-VB-03`** ephemeral environment status. Both `[§21 gap]`.
14. **10.19 extension.** **`E-WP-03`** feature-flag badge and license-check result `[§21 gap]`.
15. **10.23 Exchange.** **`E-EX-01`** tenant boundary warning, blocked by policy where configured `[§21 gap]`.
16. **10.36 Documentation & Journey Report** with the print stylesheet.
17. **10.38 Runtime & Operations.** Sidecar state including remote host, Doctor with fix-it actions, backup/restore, migration status, update channel, OTel status, uninstall with ledger-preservation confirmation.

### Exit criteria
- [ ] No agent-governing setting changes without a blast-radius preview and a ledger entry
- [ ] Skill install cannot complete without explicit confirmation following full disclosure
- [ ] A failing probation agent cannot be admitted
- [ ] A candidate that improved a metric by weakening a control renders as a failure, prominently
- [ ] Promote requires typed confirmation; rollback is one action and survives a restart
- [ ] Every KPI links through to the ledger slice it was computed from
- [ ] Export cannot include credentials, episodic memory or untrusted content — verified by attempting it
- [ ] A memory contradiction cannot be resolved without a recorded human choice

---

## G8 — Refinement

**Goal.** Ship quality. Not optional polish — this is where the product becomes something people trust.

### Screens
**10.40** First-Run & Guided Setup · **10.42** Editor-Resident Surfaces

### Tasks

1. **10.40 First-Run.** Five steps ending in a **real dry-run against a bundled sample repository** — a real Weave, a real ledger entry, a real gate, one real approval. Not a video. Uses **`V-08` warp-string** loading and **`V-09`** the illustration that gains threads as steps complete. Target: `NFR-14`, 15 minutes install-to-value.
2. **10.42 Editor-Resident Surfaces.** **`G-01`** agent cursors in the story worktree. **`G-02`** minimap overlay of agent-touched regions. **`G-03`** explain-this-line from the gutter to the decision record to the ablation. Hover provenance, blame decoration, code actions. `@meridian` chat participant — gated on **`D11`**.
3. **§11.1 global overlays**, built once: **`G-12`** confidence-weighted colouring, **`G-13`** cost overlay, **`G-04`** explicit feedback on artifacts, **`G-11`** comparison pinboard.
4. **X-17 Multi-panel** and the dependent **`E-IN-01`** Inspector pop-out and pin `[§21 gap]`. Closes **`T5`**.
5. **X-16 Personalisation** and the dependent **`E-CC-04`** draggable Command Center layout `[§21 gap]`, **`E-AW-04`** agent comparison `[§21 gap]`.
6. **X-10 Localisation & formats.** Externalised strings, **workspace currency** with rate and date on hover (`T7`), number and date formats, time zones on every `Timecode`, RTL readiness.
7. **X-24 Print styles** for Weave, Journey Report, Ledger slice and KPI pages.
8. **Motion pass.** Every named animation implemented, timed and reviewed together in one sitting. **`V-02`** cause-to-effect threads, **`V-10`** Observatory arcs sharing warp positions, **`V-12`** the hover-agent signature interaction, **`V-11`** baseline grid audit. Cut anything that does not show what changed.
9. **`shed-open` consistent across all navigation.**
10. **Choreography audit** against §8.3's four rules on every screen. Remove violations.
11. **Reduced-motion audit.** Walk every screen with motion disabled and confirm nothing is lost. **`A-05`** per-canvas toggles verified.
12. **`A-06` simplified mode** for the Command Center `[§21 gap]` — one weave, one gate list, one halt button, for new users and incident conditions.
13. **Theme completion.** Six themes verified across all 42 screens; contrast and colour-blind checks green in CI.
14. **Accessibility certification.** Full WCAG 2.1 AA audit with NVDA, JAWS and VoiceOver. Every canvas parallel verified. 200% text scaling verified.
15. **Performance certification.** All §16 budgets green on low-spec hardware, not a developer workstation.
16. **Banned-pattern sweep.** All 24 items in §18 audited screen by screen with a checklist. This is a real review, not a glance.
17. **Copy pass.** Every string against §6.2 and X-09: sentence case, active voice, consistent action vocabulary, errors stating cause and next action, empty states that invite `[P-16]`.
18. **Sprite and icon completion**; **`E-FL-04`** walk-path trails and **`E-FL-05`** human presence on the Floor `[§21 gap]`.
19. **Focus Mode polish:** **`E-FM-01`** portfolio cycling, **`E-FM-02`** burn-in protection `[§21 gap]`.
20. **`E-WV-05`** weave compare mode `[§21 gap]`.
21. **Sound** implemented, off by default, four sounds. **`V-06`** shuttle-click panning — see §9.
22. **`P-13`** the animation implementation debt from the prototype, closed.
23. **Cross-platform verification** on Windows, macOS and Linux, and across the five most-used VS Code themes.

### Exit criteria
- [ ] Install-to-completed-dry-run under 15 minutes, tested with five people who have never seen the product
- [ ] WCAG 2.1 AA certified with screen-reader sign-off
- [ ] Every performance budget green on low-spec hardware
- [ ] Banned-pattern audit complete with zero findings across all 24 items
- [ ] All six themes complete across all 42 screens
- [ ] Reduced-motion path loses no information on any screen
- [ ] Cost renders in the workspace currency everywhere, never hard-coded USD

---

## 5. Cross-Cutting Workstreams

Run continuously from G0. Never scheduled as a phase.

| Workstream | Cadence | Owner |
|---|---|---|
| **Design system maintenance** | Every phase. New component → library first, screen second (`B1`). | Design lead |
| **Visual regression** | Every commit. Six themes × three densities × two phase sets. | CI |
| **Accessibility** | Every component at authoring time (`B3`); full audit in G8. | All engineers |
| **Colour-blind verification** | Every commit, alongside contrast (`A-02`). | CI |
| **Phase-set conformance** | Every commit. Components exercised against nine-phase and six-phase sets (`B8`). | CI |
| **Canvas parallel conformance** | Every canvas PR. A canvas without a DOM parallel does not merge (`B10`). | Review |
| **Performance** | Budgets in CI from G0; low-spec profiling at each phase exit. | CI + phase owner |
| **Copy** | Written with each screen against X-09; reviewed wholesale in G8. | Design lead |
| **Design critique** | Weekly, against §18 banned patterns and the §3 rationale. | Team |

---

## 6. Definition of Done — Any Screen

Items marked **new** were added by v2.0.

- [ ] Built from library components; no ad-hoc CSS
- [ ] All four states: loading (`thread-tension`, no spinner), empty (an invitation), error (cause and next action), populated
- [ ] Correct in all six themes plus Follow VS Code, including both high-contrast themes
- [ ] **new** Correct in all three density modes
- [ ] **new** Correct against both a nine-phase and a six-phase phase set, if it renders phases
- [ ] Responsive at all four breakpoints
- [ ] Fully keyboard operable; shortcuts registered in the command registry; focus always visible
- [ ] **new** Every action reachable from the Omnibar and a context menu, generated from the same registry
- [ ] Non-colour encoding for every state
- [ ] **new** Colour-blind simulation passes for all three deficiencies
- [ ] **new** Any canvas has its DOM parallel in the same commit, always in the tree
- [ ] **new** Any destructive action uses the hold primitive with all three access paths
- [ ] **new** Any confidence renders with calibration; any rationale renders with its unverified label
- [ ] Reduced-motion path verified to lose no information
- [ ] Performance budgets met on low-spec hardware
- [ ] Visual snapshots committed across all themes
- [ ] axe-core clean
- [ ] Copy reviewed against §6.2 and X-09
- [ ] Banned-pattern check passed against all 24 items
- [ ] Degrades correctly when the sidecar is unavailable, using the correct one of four degraded states
- [ ] Every displayed metric traces to ledger evidence

---

## 7. Sequencing Dependencies

```
G0 Foundation  (tokens · 11 cross-cutting systems · phase-set provider · hold primitive)
 ├─→ G1 Command Center
 │    ├─→ G2 The Weave ──→ G3 Decision Surfaces
 │    │                     └─→ G6.5 Organisation Surfaces ──→ G7 Governance & Learning
 │    └─→ G4 The Floor ────────→ (Focus Mode)                        ↑
 ├─→ G5 Graph Register ───────→ G6 Modelling Surfaces ───────────────┘
 └─→ (art production for G4 — commissioned in G0, long lead)

G8 Refinement depends on all of the above.
```

**Parallelisable:** G4 and G5 are independent of each other and of G3, and can run concurrently with separate engineers once G1 lands. G6 can run alongside G6.5.

**The critical path is unchanged:** `G0 → G1 → G2 → G3`. That sequence is what makes the product governable and therefore usable on real work. Everything else improves a product that already functions. Protect this path; let the others slip if they must.

---

## 8. Slip Plan

Cut in this order. Each cut leaves a working product.

| Order | Cut | Cost of cutting |
|---|---|---|
| 1 | Sound, and `V-06` panning with it | None. It is off by default. |
| 2 | 10.24 Focus Mode and `E-FM-01/02` | Loses the second-monitor and wall-screen use case. |
| 3 | UML types beyond Sequence and Class | The differentiator (agent sequence) is retained. |
| 4 | 2.5D in Dojo and Loop Graph — ship the 2D fallback (`V5`) | Less compelling, equally legible. Genuinely acceptable. |
| 5 | §11.1 global overlays (`G-12`, `G-13`, `G-04`, `G-11`) | Loses analysis affordances, not core function. |
| 6 | 10.42 Editor-resident surfaces | Loses reach to engineers who never open the dashboard. |
| 7 | The Floor, shipping Floor List only | Significant. Loses the ambient register and much of the product's character. Only under real pressure. |
| 8 | CodeMap rework heat | Loses the most actionable view for tech leads. |

**Never cut:** the Ledger viewer · the Gate Room · Halt All and its three access paths · the confidence-with-calibration pairing · the evidence-versus-narrative distinction · the Steer and clarifying-question surfaces · canvas DOM parallels · any accessibility work. These are what make an autonomous agent system safe to run.

---

## 9. Notes on Two Inconsistencies

**`V-06` sound panning.** `VIGUIX_Final.md` §8.5 marks it `COULD v2`; §21 places it in G8. Resolved here as **G8, first item on the slip list** — it is trivial once sound exists, and sound does ship (off by default, §14). If sound is cut, `V-06` goes with it.

**`E-WV-03` gate bands.** Marked `SHOULD v1` in §10.3 but absent from §21's G2 line. Assigned to **G2**, where the WeaveCanvas is built. Building it later would mean touching the offscreen buffer twice.

---

## 10. Prototype Status

`meridian-loom-gui.html` is a working single-file prototype built against this specification. It is a **visual and interaction reference for G0–G3**, not a substitute for any phase.

**What it validates:** the token system and six themes · three density modes · the phase-set provider switching nine ⇄ six across warp, weave and floor · the hold primitive with all three access paths · the theme picker · focus trap and backdrop · focusable tooltips · canvas DOM parallels with Table view toggles · the Omnibar · global time-travel state · weave texture, gate bands, steer ticks, minimap and export · the rework taxonomy · the Decision Stream's seen-before-approve rule and rubber-stamp detector · sticky first column · three budget arcs and label-collision modes · 17 of the 42 screens.

**What it does not validate, and cannot:** it is a browser page, not a webview. No CSP nonce, no `asWebviewUri`, no message bus, no `WebviewPanelSerializer` state restoration, no sidecar. It uses zero browser storage, which is the constraint most likely to bite on the port — but the port is still real work, and G0 tasks 11–13 are not shortened by it.

**Use it for:** design review, stakeholder demonstration, and as the reference implementation when building the real components in G0 and G1.

---

## 11. Changes from v1.0

| Area | Change |
|---|---|
| **Phases** | 9 → 10. `G6.5 Organisation Surfaces` inserted, holding the five screens that require more than one story, human or repository. |
| **Screens** | 24 → 42, assigned across the phases in §4. |
| **G0** | Roughly doubled. Eleven cross-cutting systems, the phase-set provider, the hold primitive, density tokens, the theme picker, the art-direction brief and colour-blind CI all moved in. |
| **Build principles** | B8–B12 added: no hard-coded phase set, three access paths, canvas parallel in the same commit, cross-cutting systems built once, component-enforced invariants. |
| **Stack decisions** | Five rows added: command registry, routing, phase-set consumer, hold-control primitive, font strategy with fallback. |
| **Definition of done** | Eight new items, including density modes, phase-set conformance, canvas parallel, hold paths and the confidence/rationale invariants. |
| **Cross-cutting workstreams** | Three added: colour-blind verification, phase-set conformance, canvas-parallel conformance. |
| **Slip plan** | Extended from six to eight steps; the never-cut list gained hold access paths and canvas parallels. |
| **Assignment** | **52 items unassigned in `VIGUIX_Final.md` §21 are now placed**, including six MUST-v1 cross-cutting systems. Marked `[§21 gap]` at each phase and listed in §0.2 and §12. |
| **New sections** | §9 inconsistency notes · §10 prototype status · §12 traceability appendix. |

---

## 12. Traceability Appendix — Every ID to a Phase

Bold marks an item `VIGUIX_Final.md` §21 left unassigned.

### Screens

| Phase | Screens |
|---|---|
| G1 | 10.1, 10.4, 10.16, 10.25, 10.39, 10.41 |
| G2 | 10.3, 10.7, 10.29 *(dev-facing)* |
| G3 | 10.6, 10.17, 10.18, 10.19, 10.20, 10.27, 10.28 |
| G4 | 10.2, 10.24 |
| G5 | 10.8, 10.9 |
| G6 | 10.10, 10.11, 10.12 |
| G6.5 | 10.26, 10.32, 10.33, 10.34, 10.35 |
| G7 | 10.5, 10.13, 10.14, 10.15, 10.21, 10.22, 10.23, 10.30, 10.31, 10.36, 10.37, 10.38 |
| G8 | 10.40, 10.42, 10.29 *(user-facing polish)* |

### Cross-cutting systems

| Phase | Systems |
|---|---|
| G0 | X-02, X-03, X-04, X-05, X-06, **X-07**, **X-08**, X-12, X-13, X-21, **X-23** *(base)* |
| G1 | X-01, **X-09**, X-11, X-14, **X-19**, X-22 |
| G2 | X-23 *(cassette panel)* |
| G3 | X-18, **X-20** |
| G6.5 | X-15, X-25 |
| G8 | X-10, X-16, X-17, X-24 |

### Enhancements

| Phase | Items |
|---|---|
| G0 | **E-OB-01**, E-CF-06 *(tokens)* |
| G1 | E-CC-01, E-CC-02, E-CC-03, E-CC-05, **E-CC-06**, E-CC-07, E-AW-01, E-AW-02, **E-AW-03**, E-AW-05, E-IN-02, **E-IN-03**, E-IN-04, **E-IN-05**, E-IN-06 |
| G2 | E-WV-01, E-WV-02, **E-WV-03**, E-WV-04, E-WV-07, E-LG-01, E-LG-06 |
| G3 | E-GR-02, E-GR-03, E-GR-04, E-GR-05, E-GR-06, E-SS-02, E-SS-03, E-VB-01, **E-WP-01**, **E-WP-02** |
| G4 | E-FL-01, E-FL-02, E-FL-06, E-FL-07 |
| G5 | E-CM-01, **E-CM-02**, E-CM-05, E-LP-01, E-LP-02, **E-LP-03** |
| G6 | E-AR-01, E-AR-02, **E-AR-03** |
| G6.5 | E-FL-03, **E-GR-01**, **E-SS-01** |
| G7 | E-DJ-01, **E-DJ-02**, E-DJ-03, **E-DJ-04**, **E-DJ-05**, E-CF-01…E-CF-05, E-SF-01, E-SF-02, **E-SF-03**, E-SA-01, **E-SA-02**, **E-SA-03**, **E-SA-04**, E-KP-01, **E-KP-02**, E-KP-03, **E-KP-04**, **E-KP-05**, **E-LG-02**, **E-LG-03**, **E-LG-04**, **E-LG-05**, **E-CM-03**, **E-CM-04**, **E-OB-02**, **E-OB-03**, **E-VB-02**, **E-VB-03**, **E-WP-03**, **E-EX-01** |
| G8 | **E-CC-04**, **E-AW-04**, **E-IN-01**, **E-FL-04**, **E-FL-05**, **E-FM-01**, **E-FM-02**, **E-WV-05** |
| v2 backlog | E-WV-06, E-EX-02 |

### Prototype gaps, accessibility, refinements, features

| Phase | Items |
|---|---|
| G0 | **P-12**, P-04, A-02, T9, V-11 |
| G1 | P-01, P-02, P-03, P-05, P-06, P-07, P-08, P-09, P-10, P-11, A-01, A-03, **G-06** |
| G2 | A-04, V-01, V-05, V-02 *(groundwork)* |
| G3 | **P-15** |
| G4 | A-05, V-03, V-04, V-07, T8 |
| G5 | P-14 |
| G6.5 | **G-05**, **G-07**, **G-10** |
| G7 | **A-08**, **G-14** |
| G8 | P-13, **P-16**, **A-06**, V-02, V-06, V-08, V-09, V-10, V-12, **G-01**, **G-02**, G-03, **G-04**, **G-11**, G-12, G-13 |
| v2 backlog | A-07, G-08, G-09, G-15, G-16 |

### Decisions

| Decision | Closed in |
|---|---|
| `V1` sprite art commission | G0 brief issued; art delivered by G4 |
| `V2` Floor opt-in | **Closed by T8** — default-on after first story |
| `V3` font licensing | G0, week 1 |
| `V4` Weave as Command Center hero | G2 |
| `V5` 2.5D vs flat | G5 |
| `V6` Focus Mode as panel or state | G4 |
| `V7` density default | G1 |
| `D8` phase set fixed or configurable | G0 — **this plan assumes configurable** |
| `D11` chat participant in v1 | G1 |
| `T1`–`T10` | Resolved in `VIGUIX_Final.md` §20; implemented across G0–G8 |

---

*End of plan. This document supersedes viguix-implementation.md v1.0 and governs the build of `VIGUIX_Final.md` v2.0.*
