# VIGUIX — Meridian Loom Visual Interface & Experience Specification

| | |
|---|---|
| **Document** | VIGUIX_Final.md |
| **Version** | **2.0 — merged and reconciled** |
| **Supersedes** | `VIGUIX.md` v1.0 · `VIGUIX_GAPS.md` v1.0 |
| **Author** | Ravaleedhar Reddy |
| **Scope** | Every pixel of the Meridian Loom VS Code extension |
| **Companions** | `vision.md` (architecture) · `Requirements_Final.md` (engineering, 30 modules) · `viguix-implementation.md` (build order) |
| **Scale** | 42 screens · 25 cross-cutting systems · ~200 numbered interface requirements |

---

## Table of Contents

0. [About This Merge](#0-about-this-merge)
1. [The Brief](#1-the-brief)
2. [The Core Metaphor: Warp and Weft](#2-the-core-metaphor-warp-and-weft)
3. [Design Rationale — and What Was Rejected](#3-design-rationale--and-what-was-rejected)
4. [Design Tokens](#4-design-tokens)
5. [Theme System](#5-theme-system)
6. [Typography](#6-typography)
7. [Layout & Shell Architecture](#7-layout--shell-architecture)
8. [Motion System](#8-motion-system)
9. [Component Library](#9-component-library)
10. [The Screens — 10.1 to 10.42](#10-the-screens)
11. [Cross-Cutting Interface Systems](#11-cross-cutting-interface-systems)
12. [Renderer Specifications](#12-renderer-specifications)
13. [Iconography & Sprite Art](#13-iconography--sprite-art)
14. [Sound](#14-sound)
15. [Accessibility](#15-accessibility)
16. [Performance Budgets](#16-performance-budgets)
17. [Technical Constraints](#17-technical-constraints)
18. [Banned Patterns](#18-banned-patterns)
19. [Open Design Decisions](#19-open-design-decisions)
20. [Resolved Decisions](#20-resolved-decisions)
21. [Implementation Impact](#21-implementation-impact)
22. [Changes from v1.0](#22-changes-from-v10)
23. [Coverage Matrix & Index](#23-coverage-matrix--index)

---

## 0. About This Merge

### 0.1 What was merged

`VIGUIX.md` v1.0 specified 24 screens and the design system beneath them. `VIGUIX_GAPS.md` v1.0 traced every module in `Requirements_Final.md` to a screen, found 18 screens missing, 94 enhancements needed on the existing 24, and 25 cross-cutting systems that were named but never specified.

Four things were done beyond concatenation:

1. **The 18 new screens were numbered into §10** as 10.25–10.42 and now sit alongside the original 24 in one sequence. Their `S`-numbers are retained as aliases so gap-document cross-references still resolve.
2. **Each of the 94 enhancements was folded into its parent screen**, not left in a separate list. A reader of 10.1 Command Center now sees the whole Command Center.
3. **The 10 decisions were resolved and applied to the base text.** Where a base specification was wrong in light of a gap finding, the base text was amended in place and marked `[AMENDED]`. This is the substantive difference between this document and two stapled files.
4. **Priorities were assigned to the original 24 screens.** The base document ranked nothing; the gaps document used MUST/SHOULD/COULD with v1/v1.x/v2 targets. All 42 screens now carry both.

### 0.2 ID stability — and one hazard

**Every ID from both source documents is preserved unchanged.** 18 `S`, 94 `E-`, 25 `X-`, 16 `P-`, 8 `A-`, 12 `V-`, 16 `G-`, 10 `T`, and the base `V1`–`V7`. §23 gives the full index.

> **Namespace hazard.** The base document used **`V1`–`V7`** for *open design decisions*. The gaps document used **`V-01`–`V-12`** for *visual refinements*. These are different namespaces distinguished only by a hyphen, and they will be confused by anyone grepping this file.
>
> Both are preserved here because renaming would break external cross-references. **In this document, `V1`…`V7` without a hyphen always means a decision; `V-01`…`V-12` with a hyphen always means a visual refinement.** A future revision should rename decisions to `VD1`–`VD7`. Do not do it silently.

### 0.3 Priority vocabulary

Matches `Requirements_Final.md` §0.3.

| Target | Meaning |
|---|---|
| **v1** | Required before Phase 1 acceptance. Without it the product is unusable or unsafe. |
| **v1.x** | Required before enterprise rollout beyond the first pilot team. |
| **v2** | Differentiating. Not blocking. |

### 0.4 The one editorial judgment applied

The base document's 24 screens carried no priority. Targets were derived from `viguix-implementation.md` build phases and from the release target of the module each screen serves in `Requirements_Final.md`:

- Screens built in **G0–G4** and serving a v1 module → **v1**
- Screens built in **G5–G7**, or serving a v1.x module → **v1.x**
- Screens the base document itself marked as later or optional → **v2**

Where this derivation contradicts either source, the source wins. Any target a reviewer disagrees with can be changed without touching the specification text.

### 0.5 Conflict resolution log

| Conflict | Resolution |
|---|---|
| §7.2 Warp Spine hard-codes nine phases vs. an organisation with a different lifecycle (T1) | §7.2, §10.2, §10.3 amended: the phase set is a policy artifact; all renderers consume it. |
| §7.1 "notifications only for gates and breaches" vs. S40 Notification Center (T4) | The interrupt rule survives for toasts and OS notifications. The inbox is a *pull* surface and does not violate it. Both specified. |
| §10.6 Gate Room as the only decision surface vs. S27 Decision Stream (T3) | Policy routes gates: high blast radius → Gate Room, routine → Decision Stream. The user never chooses. |
| §10.1 Command Center is single-story vs. M21 portfolio (T2) | Command Center stays single-story by design. 10.26 Portfolio is the many-story view. Stated explicitly in both. |
| §18 `V2` (Floor opt-in?) vs. gaps `T8` | Resolved: Floor is default-on after the first story. `V2` closed. |
| §18 `V1` (sprite art) vs. gaps `T9` | Partially resolved: a *designed* geometric-token fallback is approved so the product ships with identity if art slips. The commission decision stays open. |
| Base has no navigation element; prototype invented a tab row (P-01, T10) | Adopted into §7.2 as **the Loom Bar**. |
| Base costs shown in USD throughout vs. a globally billing organisation (T7) | Workspace currency setting; §11 X-10. |

---

## 1. The Brief

**Subject.** A VS Code extension in which a governed organisation of AI agents delivers software. The agents work continuously, in parallel, at machine speed, on a real codebase.

**Audience.** Senior engineers, architects and delivery managers at a Global Top 5 IT services organisation. People who read dense instrument panels for a living and distrust anything that looks like a toy — but who will be watching a system whose work they did not personally do.

**The primary job of this interface.** To make an invisible, fast-moving swarm *legible, trustworthy and stoppable.*

Everything else is secondary. A beautiful dashboard that leaves an engineer unable to answer "what is happening right now, who did that, and can I stop it" has failed regardless of how it looks.

**The tension to design into.** Two audiences want opposite things from the same product. Engineers want density, keyboard control, and no ceremony. Delivery leadership wants a picture they can read across a room in a governance meeting. Meridian Loom resolves this with **two registers of the same data**: a spatial, ambient, watchable register (the Floor, the Weave) and a dense, instrument-grade register (the Command Center, the Ledger, Agents Watch). Every entity is reachable from both. Neither is a simplified version of the other.

**A third audience, added in v2.0.** The **approver at scale** — someone with twenty gates waiting who is neither watching ambiently nor analysing deeply. 10.27 Decision Stream exists for them, and its design constraint is that speed must not become rubber-stamping.

---

## 2. The Core Metaphor: Warp and Weft

The product is called Meridian Loom. A loom is not decoration here — it is a structurally accurate model of what the system does, and the source of the entire visual language.

| Loom | Meridian Loom |
|---|---|
| **Warp** — the fixed vertical threads, strung before weaving begins, defining the structure of the cloth | The SDLC phases. Fixed for a given policy, ordered, always visible, never move. |
| **Weft** — the horizontal thread carried back and forth across the warp, building the cloth row by row | Agent passes. Each agent action is one pass of the shuttle across the phases it touches. |
| **Shuttle** — the object that carries the weft | The active agent. There is a visible, moving carrier for every piece of live work. |
| **Shed** — the gap opened in the warp for the shuttle to pass through | A gate. The warp opens, the pass goes through, the warp closes. Screen transitions use this. |
| **Beat-up** — pressing each new row tight against the last | Commit to the ledger. Each row locks permanently into the cloth. |
| **Selvage** — the self-finished edge that stops the cloth unravelling | The hash chain. The edge that proves the cloth was not unpicked. |
| **Unravelling** | Rework. A rejected pass visually pulls back out of the cloth. |
| **Finished band** | A merged story. |

**Why this matters practically.** A story's progress is not a percentage bar. It is a *woven band* that accumulates: one warp thread per phase, and rows of weft building upward as agents complete passes. You can see at a glance which phases are dense with rework and which passed clean in one row. That is a real information display, not a metaphor pasted on top of one.

The second half of the name earns its keep too. A **meridian** is a reference line for navigation and the point of a body's highest ascent. The KPI Observatory (10.22) uses meridian lines, sextant-style arcs and ascent markers rather than generic bar charts.

**[AMENDED — T1]** The base document assumed nine warp threads. **The phase set is a policy artifact** (`Requirements_Final.md` §7.8): id, code, name, colour role, gate. Every renderer consumes it. Nine is the default, not the architecture.

---

## 3. Design Rationale — and What Was Rejected

Design work is judged partly on what it refuses. These were considered and rejected, with reasons, so nobody reintroduces them.

| Rejected | Why |
|---|---|
| **Straight pixel-art-office clone** (the Munder Difflin look, adopted wholesale) | Genuinely brilliant at making agents feel like colleagues, and the ambient watchability is worth keeping. Adopted wholesale it reads as a novelty, and this product must survive a CMMI governance review. **Kept:** spatial agent representation, character identity, ambient legibility, speech as status. **Changed:** the Floor is one register of several, art direction is woven/textile rather than cubicle-sitcom, and every spatial element is backed by a dense view holding the same truth. |
| **Cream background + high-contrast serif + terracotta accent** | The current house style of generated design. Instantly recognisable as a default rather than a decision. |
| **Near-black + one acid-green accent** | The other current default. Also: a single accent cannot carry six agent states legibly. |
| **Identical rounded cards, one radius everywhere, same soft grey shadow** | Erases hierarchy exactly where this product needs it most — a gate awaiting approval must not look like a cost tile. |
| **All-caps tracked-out eyebrow labels above every heading** | Template chrome. Appears regardless of subject. Banned in §18. |
| **Progress percentages and donut charts** | A story is not 63% done. It is at row 14 of the weave with three unravelled passes in Verification. Say that instead. |
| **Generic "AI" visual signifiers** — glowing orbs, particle swirls, gradient meshes, neural-net line art | Says nothing about this system and dates immediately. |
| **A literal blockchain visual** — chained cubes, cryptocurrency iconography | The substrate is a Merkle transparency log, not a blockchain (`vision.md` §6.1, `FR-M10-06`). The Ledger is rendered as **selvage**: a woven, locked edge. |
| **A swipe-based approval interface** *(added v2.0)* | Considered for 10.27 Decision Stream and rejected. Swipe optimises for speed at the cost of attention, and `FR-M20-06` exists precisely because rubber-stamping is a known failure mode. The Stream is keyboard-driven and counts time-on-artifact. |

**Where the palette comes from.** Natural dye vernacular — the actual materials of a loom. Indigo vat, undyed linen, madder root, weld, woad, verdigris, cochineal. Six functionally distinct hues, historically coherent with each other so they harmonise without tuning, and none of them a stock UI accent.

---

## 4. Design Tokens

All tokens are CSS custom properties on `:root`, defined per theme, consumed by every component. No component hard-codes a colour.

### 4.1 Core palette (Indigo Vat — default dark)

```css
/* ——— Ground ——— */
--ml-vat-900:      #0B0E1C;   /* deepest canvas */
--ml-vat-800:      #11152A;   /* app canvas */
--ml-vat-700:      #171D38;   /* raised: panels */
--ml-vat-600:      #1F2748;   /* raised: cards, rails */
--ml-vat-500:      #2A3358;   /* hairlines, warp threads at rest */
--ml-vat-400:      #3A4570;   /* borders on interactive surfaces */

/* ——— Linen (text and undyed thread) ——— */
--ml-linen-100:    #F2EFE6;   /* primary text */
--ml-linen-300:    #D5D0C2;   /* secondary text */
--ml-linen-500:    #9C9A90;   /* tertiary, metadata */
--ml-linen-700:    #6B6C68;   /* disabled */

/* ——— Functional dyes: one hue per agent/work state ——— */
--ml-woad:         #4A83C4;   /* WORKING — active pass in motion */
--ml-woad-dim:     #2C5686;
--ml-weld:         #E0A828;   /* ATTENTION — gate open, awaiting human */
--ml-weld-dim:     #8A6614;
--ml-madder:       #C8483A;   /* REWORK / REJECTED / breach */
--ml-madder-dim:   #7C2C23;
--ml-verdigris:    #2FA592;   /* APPROVED / passed / merged */
--ml-verdigris-dim:#1A6459;
--ml-cochineal:    #9B3F6C;   /* META — trainer, governance, evolution */
--ml-cochineal-dim:#5E2542;
--ml-iron:         #5B6480;   /* IDLE — agent at rest, warp unpassed */

/* ——— Signal ——— */
--ml-halt:         #FF4D3D;   /* Halt All. Used nowhere else. Ever. */
```

**The `--ml-halt` rule.** This colour appears on exactly one control: Halt All. It is reserved so that in a crisis the eye finds it in under a second without reading. Any other use is a defect.

### 4.2 State → colour mapping (normative)

| State | Token | Also encoded by | Rationale |
|---|---|---|---|
| Idle | `--ml-iron` | flat thread, no animation | Colour alone is never the signal |
| Working | `--ml-woad` | shuttle in motion, thread tension | Motion carries it for colourblind users |
| Attention / gate open | `--ml-weld` | pulsing shed gap, badge count | Weld is the only hue that pulses |
| Rework | `--ml-madder` | unravel animation, hatched fill | Hatching distinguishes from halt |
| Approved | `--ml-verdigris` | beat-up animation, solid weave | |
| Meta / training | `--ml-cochineal` | dotted thread | Visually "not delivery work" |
| Halted / breach | `--ml-halt` | full-bleed edge glow | Impossible to miss |

Every state is encoded **twice** — hue plus shape or motion. Accessibility requirement, not stylistic flourish. **[v2.0 — A-02]** The six dyes must remain mutually distinguishable under protanopia, deuteranopia and tritanopia simulation, verified in CI alongside contrast ratio.

### 4.3 Space, radius, elevation

```css
--ml-space-1: 4px;   --ml-space-2: 8px;   --ml-space-3: 12px;
--ml-space-4: 16px;  --ml-space-5: 24px;  --ml-space-6: 32px;
--ml-space-7: 48px;  --ml-space-8: 64px;

/* Radius encodes KIND, not decoration — three values only */
--ml-r-thread: 2px;    /* data surfaces: tiles, rows, cells, graph nodes */
--ml-r-panel:  6px;    /* containers: panels, modals, cards */
--ml-r-actor:  50%;    /* anything representing an agent — always circular */

/* Elevation is a border + inner light, never a grey blur */
--ml-elev-0: none;
--ml-elev-1: inset 0 1px 0 rgba(242,239,230,.06), 0 0 0 1px var(--ml-vat-500);
--ml-elev-2: inset 0 1px 0 rgba(242,239,230,.09), 0 0 0 1px var(--ml-vat-400),
             0 8px 24px -12px rgba(0,0,0,.7);
--ml-elev-3: inset 0 1px 0 rgba(242,239,230,.12), 0 0 0 1px var(--ml-woad-dim),
             0 18px 48px -18px rgba(0,0,0,.85);
```

**Radius carries meaning.** Circular means *an agent*. 2px means *data you can trust and select*. 6px means *a container*. There is no fourth value, so nothing gets a radius by accident.

**Elevation is not a drop shadow.** The default soft grey blur under every card is the SaaS-kit tell. Meridian Loom lifts surfaces with a hairline plus a top inner highlight — the way a raised thread catches light on real cloth — and reserves a cast shadow for modals only.

### 4.4 Density modes **[v2.0 — E-CF-06]**

Three modes, selectable in Config › Appearance. Each is a token delta, not per-component overrides, so consistency is structural.

| Token group | Comfortable | Compact | Dense |
|---|---|---|---|
| Row height | 32px | 26px | 22px |
| Panel padding | `--ml-space-4` | `--ml-space-3` | `--ml-space-2` |
| Weave row height | 22px | 15px | 9px |
| Roster card width | 168px | 150px | portraits only |
| Body size | 13px | 13px | 12px |
| Table cell padding | 7px 10px | 5px 8px | 3px 6px |

Default is **decided in `V7`** (§19, still open).

---

## 5. Theme System

Six themes ship. All are complete token sets; switching is instant and animated (`theme-crossfade`, §8).

| Theme | Ground | Character | Use |
|---|---|---|---|
| **Indigo Vat** | `#11152A` | Default. Deep blue-violet, dye-vat depth. | Default dark |
| **Sized Linen** | `#E7E4DA` | Light. Warm undyed linen with ink-blue text. Dyes darkened ~18% for AA on light. | Default light |
| **Iron Gall** | `#07080F` | Maximum contrast, near-monochrome, dyes at full saturation. | High contrast |
| **Madder Dusk** | `#1A1013` | Warm dark. Red-brown ground, dyes shifted warm. | Long-session comfort |
| **Weld Dawn** | `#F0EBDC` | Light, warmer, higher-key. | Presentation / screen-share |
| **Loom Ghost** | `#0B0E1C` | Dark, dyes desaturated to 35%, motion halved. Reads as a photograph of the system. | Ambient / Focus Mode |

Plus **Follow VS Code** (default on first run): derives the token set from `--vscode-*` variables, mapping editor background, foreground and the six functional dyes onto the closest theme-provided accents while preserving the state→shape mapping. When following, Meridian identity is carried by shape, motion and typography rather than hue.

```
Theme resolution order
  1. user explicit choice (workspace setting)
  2. Follow VS Code  ← default
  3. Indigo Vat fallback
```

**High-contrast handling.** When VS Code reports a high-contrast theme, Meridian force-switches to Iron Gall and disables decorative motion regardless of user preference. Transparency drops to zero, hairlines go to 2px.

**[v2.0 — P-04]** Theme selection is a **picker with live preview swatches**, not a cycle button. It appears in Config › Appearance and as a compact popover from the Crown chip. A cycle button was acceptable in the prototype and is not acceptable with six themes.

---

## 6. Typography

Two families. Both bundled with the extension, both variable, both loaded from `asWebviewUri` under the CSP nonce.

| Role | Family | Why |
|---|---|---|
| **Display & UI** | **Archivo** (variable, with Archivo Expanded for display) | A grotesque with industrial signage heritage and a genuinely useful width axis. Not Inter, not Helvetica, not a system stack. The width axis is an active design element: display type is set **expanded**, echoing threads spreading on a loom. |
| **Data, code, hashes, telemetry** | **Commit Mono** (variable) | Engineered for code legibility with distinctive letterforms. Every number, hash, path, diff, agent id and metric in the product is set in it. |

**[v2.0 — P-12]** Commit Mono is not available from Google Fonts. The licensing and subsetting decision (`V3`) must be closed in G0 before the font pipeline is built. **Documented fallback stack** for any environment where the bundled font fails to load: `'Commit Mono', 'JetBrains Mono', ui-monospace, 'SF Mono', Menlo, Consolas, monospace` and `'Archivo', 'Helvetica Neue', Helvetica, Arial, sans-serif`. The fallback must be visually checked, not assumed.

### 6.1 Scale

Modular, 1.25 ratio from a 13px base (VS Code's density, not the web's).

```
--ml-t-display   34px / 1.05 / Archivo Expanded 600 / -0.02em   Screen titles, hero metrics
--ml-t-h1        24px / 1.15 / Archivo Expanded 600 / -0.01em   Section heads
--ml-t-h2        18px / 1.25 / Archivo 600                      Panel heads
--ml-t-h3        15px / 1.3  / Archivo 600                      Card heads
--ml-t-body      13px / 1.55 / Archivo 400                      Prose, descriptions
--ml-t-ui        13px / 1.2  / Archivo 500                      Controls, labels, nav
--ml-t-small     11px / 1.4  / Archivo 400                      Metadata, timestamps
--ml-t-data      13px / 1.45 / Commit Mono 400                  Numbers, ids, paths
--ml-t-data-lg   28px / 1.0  / Commit Mono 500 / tnum           Hero metrics
--ml-t-code      12px / 1.6  / Commit Mono 400                  Diffs, logs, terminal
```

All numeric displays use `font-variant-numeric: tabular-nums`. Metrics that change live must not reflow.

**Prose line length caps at 72 characters** anywhere prose appears.

**[v2.0 — V-11]** All text snaps to a **4px baseline grid**. Screen titles use exactly one display size; two display sizes never appear on the same screen.

### 6.2 Typographic rules

- Sentence case everywhere. No all-caps labels, including in tables and nav. The one exception is a short phase abbreviation on the warp spine where vertical space is genuinely 18px.
- Never accent a single word in a heading with a different colour or weight.
- No label above content unless the content is ambiguous without it. `4,281` above the word "Tokens" is fine. "AGENT NAME" above "Priya, Architect" is not.
- Agent names are always Archivo 500. Agent *identifiers* (`architect-agent@2.1.0`) are always Commit Mono. The two are never interchanged.

---

## 7. Layout & Shell Architecture

### 7.1 Surfaces the extension occupies

| Surface | Content | Notes |
|---|---|---|
| **Activity Bar icon** | Meridian mark (a shuttle crossing three warp threads) | Badge shows open gate **and unanswered-question** count in weld |
| **Primary Sidebar** (`WebviewView`) | The Rail — agent roster, active stories, gate queue | Always available, narrow, ~300px |
| **Editor Panel** (`WebviewPanel`) | The full dashboard: all screens in §10 | The main product surface |
| **Status Bar** | Loom state, active pass count, live spend, Halt All | Compressed to `⟡ 4 weaving · $2.18` |
| **Editor Decorations** | Gutter thread marks on agent-authored lines, coloured by state | Click opens Ledger at that entry |
| **Editor-resident surfaces** *(v2.0)* | Agent cursors, minimap overlay, explain-this-line — see 10.42 | `FR-M24-02`, `FR-M24-04` |
| **Chat participant** *(v2.0)* | `@meridian` with slash commands | `FR-M24-01` |
| **Notifications** | Interrupting: gates and breaches only. Everything else goes to the inbox (10.39). | **[AMENDED — T4]** |

### 7.2 The dashboard shell

```
┌──────────────────────────────────────────────────────────────────────────┐
│  ⟡ MERIDIAN LOOM     EDB-12345 ▾    row 14    ⌘K   ◐ theme   ⏻ Halt      │  44px  Crown
├──────────────────────────────────────────────────────────────────────────┤
│  Command · Weave · Floor · Agents · Gates · Ledger · Map · Loops · …  ›   │  34px  Loom Bar
├────┬─────────────────────────────────────────────────────────┬───────────┤
│ W  │                                                          │  I        │
│ A  │                                                          │  N        │
│ R  │                  ACTIVE  SCREEN                          │  S        │
│ P  │                  (§10 — one of 42)                       │  P        │
│    │                                                          │  E        │
│ S  │                                                          │  C        │
│ P  │                                                          │  T        │
│ I  │                                                          │  O        │
│ N  │                                                          │  R        │
│ E  │                                                          │           │
│52px│                                                          │  310px    │
├────┴──────────────────────────────────────────────────────────┴──────────┤
│  ▣ Priya  ▣ Arun  ▣ Kenji  ▣ Sofia  ▣ Marcus  ▣ Lena  … +6      ROSTER   │  66px
└──────────────────────────────────────────────────────────────────────────┘
```

**The Crown** (44px). Story selector, live weave row counter, command palette, theme picker, Halt All. Halt All sits at the far right in `--ml-halt`, always visible, never scrolls away, requires a 400 ms press-and-hold with a filling ring.

**[v2.0 — A-01, P-03, E-GR-06]** Press-and-hold has a **keyboard path**: `Space` held for 400 ms with the same ring. It also has an **accessible alternative** for assistive-tech users who cannot hold a key: a two-step confirm. Every press-and-hold control in the product carries all three paths. This applies to Halt All, high-blast-radius Approve, and Abort Story.

**The Loom Bar** (34px) **[NEW — T10, P-01]**. Screen navigation. A scrollable horizontal tab row with overflow into a menu. Badges appear only for gates and unanswered questions. Generated from the command registry (X-12) so it cannot drift from the actual screen set.

**The Warp Spine** (52px, left, permanent). The most important element in the product. One vertical thread per SDLC phase, top to bottom, **generated from the policy phase set [AMENDED — T1]**, not hard-coded. Each thread's appearance encodes that phase's state for the active story:

```
  ┌────┐
  │ IN │  ▓▓▓▓  Intake      verdigris, solid    — passed, 1 row
  │ DE │  ▓▓▓▓  Design      verdigris, solid    — passed, 2 rows
  │ PL │  ▓▓▓▓  Plan        verdigris, solid    — passed, 1 row
  │ BD │  ▓▒▓▒  Build       woad, in motion     — weaving now, row 9
  │ VF │  ░╱╱░  Verify      madder, hatched     — 2 unravelled passes
  │ SC │  ┊┊┊┊  Security    iron, dotted        — not reached
  │ RV │  ┊┊┊┊  Review      iron, dotted        — not reached
  │ RL │  ┊┊┊┊  Release     iron, dotted        — not reached
  │ OP │  ┊┊┊┊  Operate     iron, dotted        — not reached
  └────┘
```

Hovering expands a thread to 200px with the phase name, gate status, agents present and pass count. Clicking navigates to that phase's detail. The spine never disappears — in every screen you always know where in the lifecycle the work is.

**[v2.0 — P-11]** Warp tooltips are **not hover-only**. Threads are focusable, tooltips open on focus and dismiss on `Escape`, and touch uses long-press. This applies to every tooltip in the product (X-04).

**[v2.0 — T1]** Two-letter phase codes are assigned by policy with collision checking. Where a policy defines more than twelve phases the spine switches to colour-only bars with codes on hover.

**The Inspector** (310px, right, collapsible). Context-sensitive to whatever is selected anywhere. Tabbed: **Trace · Terminal · Diff · Memory · Policy · Messages · History**. Inspects agents, passes, ledger entries, work packets and gates with the same chrome. **[v2.0 — X-17, T5]** Poppable to its own editor tab and pinnable to a specific entity, so two agents can be compared side by side.

**The Roster** (66px, bottom). Every agent as a circular portrait with a state ring, name, current activity in one line, and a live token meter. Horizontally scrollable, keyboard-navigable with `[` and `]`. Drag an agent onto a work packet to assign. Persists across every screen — the workforce is never out of sight.

**[v2.0 — X-22]** At 30+ agents the Roster groups by phase or tier, offers a filter, collapses overflow into a "+N" chip that opens a sheet, and supports a portraits-only compact mode.

### 7.3 Responsive behaviour

The dashboard lives in an editor tab a user will freely resize to a third of the screen.

| Width | Behaviour |
|---|---|
| `≥1400px` | Full shell. Inspector open. Roster shows 10+ agents. |
| `1100–1400px` | Inspector collapses to a 44px icon rail, expands on click as an overlay. |
| `800–1100px` | Warp Spine collapses to 28px (thread colours only). Roster shows 6. |
| `<800px` | Single-column. Warp Spine becomes a horizontal strip under the Loom Bar. Roster becomes a count chip that opens a sheet. Spatial screens (Floor, Weave) switch to their list equivalents automatically and say so. |

**[v2.0 — P-02]** The narrow-width warp is specified, not implied: threads render **horizontally**, left to right in phase order; tooltips open **below** the strip, centred on the thread; the `shed-open` transition separates threads **horizontally** (odd left, even right).

**[v2.0 — P-05, X-04]** Any overlay Inspector or sheet carries a **backdrop, a focus trap, `Escape` to close, and return-focus** to the trigger. The prototype had none of these; they are not optional.

---

## 8. Motion System

Motion does one job: **show what changed and who changed it.** Every named animation below is tied to a real state transition. No decorative entrance animations, no scroll-triggered reveals, no hover transitions on cards that do not open something.

### 8.1 Timing tokens

```css
--ml-dur-instant: 90ms;    /* state flip: toggle, select, focus */
--ml-dur-quick:  160ms;    /* reveal: tooltip, menu, inspector tab */
--ml-dur-base:   260ms;    /* transform: panel open, card expand */
--ml-dur-pass:   420ms;    /* a shuttle pass — the signature duration */
--ml-dur-scene:  560ms;    /* screen-to-screen */
--ml-dur-settle: 900ms;    /* graph force simulation settling */

--ml-ease-shuttle: cubic-bezier(.22,.61,.36,1);    /* fast out, glide in */
--ml-ease-beat:    cubic-bezier(.34,1.42,.64,1);   /* slight overshoot — the beat-up */
--ml-ease-shed:    cubic-bezier(.65,0,.35,1);      /* symmetric — the warp opening */
--ml-ease-unravel: cubic-bezier(.55,.06,.68,.19);  /* accelerating out — rework */
```

### 8.2 Named animations

| Name | Trigger | Behaviour | Duration |
|---|---|---|---|
| **shuttle-pass** | An agent begins a pass | A circular agent token travels across the weave region, drawing a weft thread behind it. Trailing thread fades to 70%. | `--ml-dur-pass`, loops while working |
| **thread-tension** | Any loading / thinking state | Relevant warp threads develop a subtle 2px sine oscillation, amplitude decaying. Replaces every spinner in the product. | 1.4s loop |
| **beat-up** | A ledger entry commits | The newest weft row compresses upward against the previous by 3px with `--ml-ease-beat`, and a 1px verdigris highlight sweeps along it once. **[v2.0 — V-02]** A brief thread draws from the causing agent's roster portrait to the row. | `--ml-dur-base` |
| **selvage-lock** | Chain head advances | The right edge gains one locked stitch; 200ms crystallise (scale 1.4→1, opacity 0→1). | 200ms |
| **unravel** | Output rejected / rework | The rejected pass's thread animates backwards out of the cloth, the row above drops to fill, and the phase thread flips to hatched madder. Deliberately the most visually disruptive animation in the product — rework should feel like something was undone. | 520ms, `--ml-ease-unravel` |
| **shed-open** | Screen-to-screen navigation | **The signature transition.** Warp threads separate (odd up, even down) opening a shed; the outgoing screen exits *through* the gap at 0.96 scale; incoming screen enters from the opposite side; warp closes. | `--ml-dur-scene`, `--ml-ease-shed` |
| **gate-iris** | Entering/leaving the Gate Room | A horizontal band iris in weld sweeps closed then open. Gates only. | 380ms |
| **roster-focus** | Agent selected | The portrait scales 1→1.12, its ring thickens 2→3px, and a woad thread draws from the portrait to wherever that agent appears on the current screen. | `--ml-dur-quick` |
| **number-roll** | Any live metric changes | Digits roll vertically, per-digit, staggered 20ms. Tabular figures prevent reflow. | 240ms |
| **graph-settle** | Graph view opens or re-layouts | Force simulation eased in; nodes arrive with staggered 12ms opacity; edges draw after nodes land. | `--ml-dur-settle` |
| **halt-flash** | Halt All fired | Full-bleed 3px `--ml-halt` border pulses twice; all motion freezes mid-animation and desaturates to 40%. **[v2.0 — V-04]** Every shuttle stops *where it is* with its trailing thread still drawn. Nothing resets. Resume continues from the same pixel. | 700ms, then static |
| **theme-crossfade** | Theme switch | Token values interpolate over 300ms. No flash of unstyled content. | 300ms |
| **portrait-hire** | Agent onboarded | The new portrait draws in stitch-by-stitch (12-step sprite reveal, top to bottom), then joins the roster with a `beat-up`. | 800ms, one-time |
| **gate-glow** *(v2.0 — V-03)* | A gate opens | The Gate Room on the Floor and the gate band on the Weave gain a weld glow whose **brightness decays over the wait**, so "how long has this been waiting" is readable without a timestamp. | continuous, 30-min decay |
| **warp-string** *(v2.0 — V-08)* | First run, long initial load | The warp is strung thread by thread, left to right, then the first row is woven. Replaces every progress bar in setup. | variable |

### 8.3 Choreography rules

1. **One orchestrated moment per screen entry.** `shed-open` carries the transition. Content inside the new screen does not additionally fade-and-slide-up. Sequenced section reveals are banned.
2. **Never animate more than three things simultaneously** outside the Floor and Weave renderers, which are continuous simulations and are exempt.
3. **Motion follows causality.** If an agent caused a change, the animation starts *at that agent's position* — its roster portrait, or its position on the Floor. **[v2.0 — V-02]** This is literal, not aspirational: a thread is drawn from cause to effect.
4. **Live regions never move under the cursor.** Any list that can receive new rows while being read (Ledger, Messages, Trace) pins scroll position and shows a "3 new below" chip instead of pushing content.

### 8.4 Reduced motion

`prefers-reduced-motion: reduce` is respected absolutely, and is independently settable in Config. **[v2.0 — A-05]** The Floor and the Loop Graph additionally carry a **per-canvas motion toggle**, because a user may accept UI motion but not a continuously simulated office or an orbiting 3D graph.

| Animation | Reduced-motion substitute |
|---|---|
| shuttle-pass | Thread appears at full length instantly; agent token at destination |
| thread-tension | Static 40%-opacity thread with a `⋯` glyph |
| beat-up / selvage-lock | Instant, no compression |
| unravel | Row disappears; a madder strike-through marker remains |
| shed-open | 120ms crossfade |
| gate-glow | Static weld band with an elapsed-time label |
| Floor / Weave | Continuous simulation replaced by static positioned layout, updated on state change only, at most 1 update/sec |
| number-roll | Instant value replacement |
| halt-flash | Static border, immediate desaturation |

**Non-negotiable:** no information exists only in motion. Every state animation has a static encoding (§4.2).

### 8.5 Visual refinements **[v2.0 — V-01, V-05…V-12]**

Not gaps in coverage; refinements that lift the product from correct to memorable.

| ID | Refinement | Priority |
|---|---|---|
| V-01 | **The Weave as real texture.** Committed rows render with a subtle over-under weave pattern (weft over odd warps, under even), so the cloth reads as cloth at every density. Cheap on the offscreen buffer; enormous for identity. | SHOULD v1 |
| V-05 | **The selvage is tactile.** Locked stitches render with a 1px inner highlight and cast a 1px shadow onto the cloth, so the edge reads as raised. | SHOULD v1 |
| V-06 | **Ambient sound as thread.** If sound is on, the shuttle click pans left-to-right with the pass. | COULD v2 |
| V-07 | **State-aware posture.** An agent in rework sits back, an agent at a gate stands, an agent working leans in. Three poses × four directions. | SHOULD v1.x |
| V-09 | **Empty is an unstrung loom.** The empty-state illustration set (§13) is one continuous drawing that gains threads as the user completes setup steps in 10.40. | SHOULD v1 |
| V-10 | **Observatory rhymes with Weave.** Meridian arcs plotting per-phase metrics share the Weave's warp positions, so the two screens are visibly the same organisation. | SHOULD v1.x |
| V-12 | **Signature micro-interaction.** Hovering any agent token anywhere draws its thread to wherever else it appears on screen for 400 ms — the "where is Kenji" gesture. | SHOULD v1 |

*(V-02, V-03, V-04, V-08, V-11 are folded into §8.2, §8.3 and §6.1 above.)*

---

## 9. Component Library

Primitives compose into everything. Named, versioned, in Storybook, covered by visual regression.

### 9.1 Primitives

| Component | Notes |
|---|---|
| `Thread` | A line with state, tension, direction, thickness. The atomic visual unit. Used in the spine, weave, graphs, gutter marks, connectors. |
| `AgentToken` | Circular portrait + state ring + optional activity glyph. Sizes: 20 / 28 / 40 / 64px. Always circular (§4.3). **[A-03]** Hit area is padded to a 28px minimum regardless of visual size, including on canvas. |
| `StateRing` | Ring encoding state by colour **and** stroke pattern (solid / dashed / dotted / hatched). |
| `MetricTile` | Label, value in `--ml-t-data-lg`, delta, sparkline. Value always tabular. |
| `Selvage` | The chain edge visual. Locked stitches, verify status, tamper indicator. |
| `PhasePill` | Phase code, state colour, gate status dot. Code comes from the policy phase set. |
| `ConfidenceBar` | Stated confidence **and** the agent's historical calibration error, overlaid. Never shows confidence alone. |
| `ProvenanceStamp` | agent · version · skill · **model · model-version** · ledger-seq. Commit Mono. Attachable to anything. **[E-... / FR-M13-10]** model version is mandatory. |
| `RationaleBlock` | Prose permanently marked "Agent's own account — not verified." Hatched left border in cochineal. |
| `EvidenceBlock` | Ablation result. Solid verdigris left border. Visually the opposite of `RationaleBlock` — the distinction is a core product value. |
| `CostMeter` | Live token/currency spend against ceiling. Weld at 75%, madder at 92%. Currency from workspace setting (X-10). |
| `LoopBadge` | `L2 · 3/5` — loop id and iteration against bound. Fills as iterations consume budget. |
| `GateChip` | Gate name, criterion status, blocking/passed, approver if approved. |
| `Shuttle` | The animated carrier for `shuttle-pass`. |
| `Timecode` | Monospace relative + absolute time, with hover for both. **[X-10]** Always carries a time zone. |

**New primitives required by v2.0 screens:**

| Component | Serves |
|---|---|
| `SteerChip` | Structured steer chips: `prefer` / `avoid` / `constraint` / `example` (10.28) |
| `QuestionCard` | Agent clarifying question with options, recommendation, per-option confidence (10.28) |
| `ApprovalProgress` | N-of-M approver state, SoD block explanation (10.32) |
| `FreshnessBadge` | Memory staleness with the change that invalidated it (10.30) |
| `WorktreeChip` | Repo · branch · worktree · commit-signed indicator (10.35) |
| `SLABar` | Due date, predicted completion, slip risk (10.25, 10.26) |
| `CassetteRow` | Replay entry: hit/miss, provider, tokens, latency (10.29) |
| `TimeTravelBanner` | Global weld banner while viewing the past (X-03, T6) |
| `RiskBadge` | Blast radius as a shape+colour pair, never colour alone |
| `DiffTriState` | Per-hunk accept / rework / edit-in-place control (10.17) |

### 9.2 Composites

`AgentCard` · `AgentInspector` · `AgentProfile` · `WorkPacketCard` · `LedgerRow` · `GateCard` · `DiffPane` · `TracePane` · `PolicyDiff` · `SkillCard` · `CandidateCard` · `ProbationScorecard` · `GraphCanvas` · `WeaveCanvas` · `FloorCanvas` · `Omnibar` · `SignalRail` · `EmptyState` · `BreachBanner` · `StoryCard` · `ConnectorCard` · `NotificationItem` · `ReliabilityDiagram` · `AutonomyLadder`

### 9.3 Empty, loading and error states

Every screen specifies all three.

- **Empty is an invitation, never an apology.** "No stories in the loom. Drop a story file here, or press ⌘K and type *ingest*." Accompanied by the idle warp — dotted threads, no cloth. The empty state *is* the metaphor at rest.
- **Loading is `thread-tension`** on the relevant threads. There is no spinner anywhere in this product.
- **Errors state what happened and the next action, in the interface's voice.** "The sidecar stopped responding 12s ago. Loop L2 is checkpointed at row 9 and will resume. Restart core." Never "Something went wrong." Never an apology. Never a bare stack trace — that goes to the Trace tab.

**[v2.0 — X-14]** "Stale" is not one state. Sidecar down, model provider down, connector down, and ledger-verification-failed each have their own banner, their own permitted actions, and their own recovery path.

---

## 10. The Screens

Forty-two screens. Each gives purpose, layout, key components, interactions, motion, states, priority — and, where v2.0 added to it, an additions table with IDs preserved.

---

### 10.1 Command Center · **MUST v1**

**Purpose.** The answer to "what is happening right now," readable in four seconds.

**[AMENDED — T2]** The Command Center is **single-story by design**. Many-story work lives in 10.26 Portfolio. The Crown story selector switches between them. This is a decision, not a limitation.

```
┌─ CROWN ──────────────────────────────────────────────────────────────┐
├─ LOOM BAR ───────────────────────────────────────────────────────────┤
├──┬───────────────────────────────────────────────────────┬───────────┤
│  │ ┌─ THE WEAVE ───────────────────────────┐ ┌─ GATES ──┐│           │
│W │ │                                       │ │ ◈ Design ││  INSPECTOR│
│A │ │   the live woven band for this story  │ │   waiting││           │
│R │ │   rows accumulating upward            │ │   6m     ││  selected │
│P │ │   shuttles crossing in real time      │ ├──────────┤│  entity   │
│  │ │                                       │ │ ? Kenji  ││  detail   │
│S │ └───────────────────────────────────────┘ │ asks…    ││           │
│P │ ┌─ PASSES (live) ───────────┐ ┌─ SPEND ─┐ └──────────┘│           │
│I │ │ Kenji   BD  L1 2/3  ▓▓░  │ │  $2.18  │ ┌─ SIGNAL ─┐│           │
│N │ │ Sofia   VF  L2 4/5  ▓▓▓  │ │  ▁▃▅▂▇  │ │ 14:22 …  ││           │
│E │ │ Arun    BD  L1 1/3  ▓░░  │ │ 218k tok│ │ 14:19 …  ││           │
├──┴───────────────────────────────────────────────────────┴───────────┤
│ ROSTER                                                                │
└───────────────────────────────────────────────────────────────────────┘
```

**Components.** `WeaveCanvas` (hero, ~46% of the region) · live `PassRow` list with `LoopBadge` and `CostMeter` · `GateCard` stack · **`QuestionCard` stack** · `SignalRail` · spend `MetricTile` with sparkline.

**Interactions.** Click any weft row → Inspector opens that ledger entry. Click a gate → `gate-iris` to the Gate Room. Click a pass → follows that agent on the Floor. `Space` pauses all passes. Hover a warp thread → phase summary.

**Motion.** Continuous `shuttle-pass` per active agent; `beat-up` on each commit; `number-roll` on spend; `unravel` on any rejection, which also flashes the Signal rail.

**Empty.** Idle warp, dotted threads, drop target. **Error.** `BreachBanner` above the weave; weave freezes and desaturates.

| v2.0 additions | | |
|---|---|---|
| E-CC-01 | Add the **Story Hub link** and an acceptance-criteria coverage summary. The base Command Center never showed what the story *is*. | MUST v1 |
| E-CC-02 | **Unanswered clarifying questions** as a first-class tile beside Gates — an unanswered question stalls a loop exactly as an open gate does. | MUST v1 |
| E-CC-03 | **Story selector** for many stories: searchable dropdown with phase, gate state and spend per row; recently viewed; pinned. Replaces the static chip (P-07). | MUST v1 |
| E-CC-04 | **Customisable layout:** panels draggable and resizable within the region, persisted per user, with *Reset*. | SHOULD v1.x |
| E-CC-05 | Weave hero: **row hover** shows agent, phase, seq, cost; **seq axis** on the selvage side; click-drag selects a range and the spend tile shows that range's cost. | MUST v1 |
| E-CC-06 | Signal rail: **filters** (mine / gates / breaches / all), **mark-all-read**, and a link into 10.39. | SHOULD v1 |
| E-CC-07 | An **"as of" freshness stamp per panel** when the sidecar is stale, not only a global banner (P-10). | MUST v1 |
| G-06 | **"What changed since I looked"** — on returning, a diff of the organisation's state since the user's last session. | SHOULD v1 |
| G-13 | **Cost overlay** toggle — every element rendered with its token cost, making the expensive parts of a story spatially visible. | SHOULD v1 |

---

### 10.2 The Loom Floor *(Agents Watch — spatial register)* · **MUST v1**

**Purpose.** Ambient, watchable, human-legible presence. The screen you leave open on a second monitor, and the one that makes an agent workforce feel like colleagues rather than log lines.

```
┌───────────────────────────────────────────────────────┬───────────┐
│  ╔═══════════════════════════════════════════════╗    │           │
│  ║  ┌────── INTAKE ──────┬─── DESIGN ────┐        ║    │  INSPECTOR│
│  ║  │  ▣ Priya           │   ▣ Arun      │        ║    │           │
│  ║  │  ░ desk  ░ desk    │   ░ desk      │        ║    │  Kenji    │
│  ║  ├──── BUILD ─────────┴───────────────┤ ┌────┐ ║    │  Developer│
│  ║  │  ▣Kenji ▣Sofia  ░ ░ ░ ░ ░ ░        │ │GATE│ ║    │  ──────── │
│  ║  │  "pinning the idempotency key…"    │ │ROOM│ ║    │  Trace    │
│  ║  ├──── VERIFY ────────┬─ SECURITY ────┤ └────┘ ║    │  Terminal │
│  ║  │  ▣ Lena  ░ ░ ░     │  ▣ Marcus     │        ║    │  Diff     │
│  ║  ├────────────────────┴───────────────┤ ┌────┐ ║    │  Memory   │
│  ║  │  ░ ░  THE DOJO   ░ ░               │ │LEDG│ ║    │  Policy   │
│  ║  ╚════════════════════════════════════╧═┴────┴═╝    │  Messages │
└───────────────────────────────────────────────────────┴───────────┘
```

**The floor is the architecture.** Rooms are SDLC phases, laid out in lifecycle order. An agent's *position is its state* — sitting at a desk in Build means it is building. Walking between rooms means a handoff is in progress. Standing in the Gate Room means it is awaiting human approval. The Ledger is a physical archive room at the edge. The Dojo is a training room. This is not decoration; it is a spatial encoding of the same state the Command Center shows numerically.

**Art direction.** Not the sitcom-cubicle look. Top-down orthographic, 24px tile grid, hand-authored sprites in the theme palette so the floor re-tints with the theme. Rooms are separated by **warp-thread walls** — vertical thread bundles rather than drywall. Desks are looms. The read is a textile workshop, not an office.

**Speech.** Agents surface one-line status as speech bubbles, in their own voice, truncated to 48 characters, max 4 on screen, prioritised by recency and severity. Full text in the Inspector. Bubbles are how you read the floor at a glance.

**Interactions.** Click an agent → Inspector + `roster-focus`. Double-click → follow-cam. Click a room → filter to that phase. Drag an agent to a room → propose a reassignment (requires confirmation; agents are not furniture). Scroll → zoom (floor / room / desk). At desk zoom you see the agent's live terminal output on their monitor.

**Motion.** Continuous, exempt from the three-thing rule. Pathfinding walk cycles on handoff. Idle micro-animations at 0.3Hz. `portrait-hire` walk-in; retirement walk-out with the desk left labelled for one session.

**Reduced motion / <800px.** Replaced by **Floor List**: the same rooms as collapsible sections with agent rows. A banner states the substitution and offers a way back.

| v2.0 additions | | |
|---|---|---|
| E-FL-01 | **[AMENDED — T1]** Room layout is **generated from the policy phase set**, not drawn. Grid is computed as `ceil(sqrt(N+3))` to accommodate the phases plus Gate Room, Ledger and Dojo. | MUST v1 |
| E-FL-02 | Rooms show **gate state on their doorframe** (weld pulse when open, madder when blocked) so the Floor carries gate information without text. Uses `gate-glow` (§8.2). | SHOULD v1 |
| E-FL-03 | **Multi-story floors:** each active story is a floor; a floor selector, or a stacked "building" view with one floor per story. | MUST v1.x |
| E-FL-04 | **Walk paths** visible as fading thread trails, so handoff patterns are legible after the fact. | SHOULD v1.x |
| E-FL-05 | **Human presence:** when a human is viewing or acting, a distinct linen-coloured figure appears in the Gate Room or at the relevant desk. The human is part of the organisation too. | SHOULD v1.x |
| E-FL-06 | **Speech copy rules** — enforced sidecar-side before display: ≤48 chars, sentence case, no emoji, no first-person flattery ("Great news!"), present tense, must name the artifact. See X-09. | MUST v1 |
| E-FL-07 | **Touch and keyboard** access to room and agent selection. The prototype was mouse-only. | MUST v1 |
| A-03 | Agent hit targets padded to a 28px minimum despite a 13px visual radius. | MUST v1 |

**[T8 — RESOLVED]** The Floor is **default-on after the first completed story**, not opt-in. New users meet the Command Center first; the Floor is revealed once there is cloth to watch. Simplified mode (A-06) hides it.

---

### 10.3 The Weave *(story progress, full screen)* · **MUST v1**

**Purpose.** The complete woven history of one story — every pass, every rework, every gate — as one continuous readable object.

Full-region `WeaveCanvas`. Warp = phases across the top. Weft rows accumulate downward, newest at the bottom. Each row is one pass: agent token at its origin, thread crossing the phases it touched, terminating at a `Selvage` stitch carrying the ledger sequence. Rework passes render hatched with their `unravel` scar left visible — **the cloth remembers what was undone.**

**Interactions.** Hover a row → provenance tooltip. Click → Inspector at that ledger entry. Drag-select rows → Inspector shows aggregate cost and duration. `Shift+Scroll` compresses row height (24px comfortable down to 3px, where a 400-row story becomes one readable texture — dense rework shows as visible dark banding).

**This is the screen for a governance meeting.** One image, no explanation needed: where the work went smoothly and where it fought.

| v2.0 additions | | |
|---|---|---|
| E-WV-01 | **[AMENDED — T1]** Configurable warp — N phases from policy, with codes and colour roles from the phase definition. | MUST v1 |
| E-WV-02 | **Steer ticks and question markers** on the rows they affected (10.28). | MUST v1 |
| E-WV-03 | **Gate bands:** a horizontal band across the warp where a gate was open, its height proportional to wait time, so approval latency is visible in the cloth. | SHOULD v1 |
| E-WV-04 | **Export** as PNG and SVG at print resolution with a legend and title block, for the governance meeting this screen promises. | MUST v1 |
| E-WV-05 | **Compare mode:** two stories' weaves side by side with shared warp, for "why did story B take three times longer." | SHOULD v1.x |
| E-WV-06 | **Annotations:** a human can pin a note to a row (`FR-M10-16`); notes render as a small linen tag. | COULD v2 |
| E-WV-07 | At texture density (3px rows) show a **minimap** with the viewport rectangle. | SHOULD v1 |
| V-01 | Committed rows render with a real over-under weave texture. | SHOULD v1 |
| A-04 | Screen readers get a **summary announcement** — "Story at row 14 of 26, Build weaving, Verify has 3 unravelled passes" — so the shape of the cloth is available without reading 26 rows. | MUST v1 |

---

### 10.4 Agents Watch *(dense register)* · **MUST v1**

The instrument-grade twin of the Floor. A sortable, filterable table of every agent: portrait, name, id, tier, state, current loop and iteration, queue depth, first-pass yield, calibration error, trust score, autonomy tier, tokens today, spend today, last commit sequence, heartbeat age.

Row actions inline: **Approve · Rework · Steer · Train · Pause · Retire · Export**. Multi-select for bulk. Column visibility and order persisted per workspace. Sparklines in the yield and spend columns.

A header toggle switches this ⟷ Floor with `shed-open`. Selection is preserved across the switch — select Kenji in the table, flip to Floor, Kenji is highlighted and centred (X-02).

| v2.0 additions | | |
|---|---|---|
| E-AW-01 | **Sticky first column** plus column resize / reorder / pin, CSV export, saved views. The prototype scrolled the agent name off-screen at narrow widths (P-09). Uses X-06. | MUST v1 |
| E-AW-02 | **Lifecycle column** — probation / active / paused / retired with time-in-state. Retired agents in a collapsed section, never hidden. | MUST v1 |
| E-AW-03 | **Agent profile** drill-down (a "CV"): history, yield over time, policy lineage, skills bound, stories worked, incidents linked, export/import ancestry. Trust is built by history, and nothing in v1.0 showed an agent's history. | SHOULD v1 |
| E-AW-04 | **Compare two agents** side by side on the same metrics. | SHOULD v1.x |
| E-AW-05 | Bulk actions with a confirmation listing every agent affected. | MUST v1 |

---

### 10.5 Agents Dojo · **MUST v1.x**

**Purpose.** Where agents are trained, evaluated and promoted. Informed by the ML-lab reference: parameter rails, 3D experiment space, run history.

```
┌─ RAIL ─────┬──────── EXPERIMENT SPACE ──────────┬── HISTORY ────────┐
│ CANDIDATE  │                                     │ ▸ c-0091  +4.2%   │
│ policy Δ   │      ╱────╲      ╱────╲             │ ▸ c-0090  −1.1%   │
│ ▓▓▓▓▓░ .78 │     ╱ node ╲────╱ node ╲            │ ▸ c-0089  +0.3%   │
│ ▓▓▓░░░ .41 │    ╲──────╱      ╲─────╱            │ ▸ c-0088  FAILED  │
│ ▓▓▓▓░░ .62 │         ╲   ╱                       │   safety invariant│
│            │        ╱─────╲                      │ ─────────────────│
│ SIGNALS    │       ╱ eval  ╲   2.5D candidate    │ SELECTED c-0091   │
│ gates   41 │       ╲───────╱   graph             │ base   .812       │
│ CI       9 │                                     │ cand   .854       │
│ review  17 │  ┌──────────────────────────────┐   │ Δ      +4.2%      │
│ edits    6 │  │  yield over evaluation runs  │   │ safety  PASS      │
│ incid.   1 │  │  ╱‾‾‾╲___╱‾‾‾‾‾‾‾            │   │ ─────────────────│
│ ▶ EVALUATE │  └──────────────────────────────┘   │ [PROMOTE] [DROP]  │
└────────────┴─────────────────────────────────────┴───────────────────┘
```

**Left rail.** Candidate policy deltas with weight sliders, regression suite selection, evaluation controls. Sliders are `Thread`-styled — dragging tensions the thread.

**Centre.** The candidate's decision graph in 2.5D perspective (§12.3), nodes as cards floating in space, rotatable by drag. Below it, the evaluation curve: candidate vs. incumbent over runs.

**Right.** Run history, newest first, each with a delta badge. Failed-on-safety-invariant runs render in madder with the invariant named — **a candidate that improved a metric by weakening a control is displayed as a failure, prominently, never as a near-miss.**

**Promote is gated.** Disabled until evaluation completes, delta clears the margin, safety invariants pass, and a human types the agent's name to confirm (X-05). On promotion: `beat-up`, ledger entry, and the previous version pinned to a rollback shelf.

| v2.0 additions | | |
|---|---|---|
| E-DJ-01 | **Signal sources panel** — which evidence fed this candidate: gate decisions, CI failures, review comments, human edits, post-merge corrections, incidents, with counts. Mirrors the six sources in `FR-M14-01`. | MUST v1.x |
| E-DJ-02 | **Breaker results** (`FR-M14-10`) as a distinct pane: failure cases generated and whether the candidate survived each. | SHOULD v1.x |
| E-DJ-03 | **Policy diff viewer** (`FR-M12-12`): the candidate's prompt/playbook delta against the incumbent, word-level, with the ledger evidence motivating each change linked inline. | MUST v1 |
| E-DJ-04 | Sliders **thread-styled** as specified. The prototype used stock range inputs. | SHOULD v1 |
| E-DJ-05 | **Rollback shelf persistent across sessions**, not only for the session, with one-click restore and a preview of the ledger entry it creates. | SHOULD v1 |

---

### 10.6 Gate Room · **MUST v1**

**Purpose.** The human decision queue for consequential decisions. The most important screen in the product.

**[AMENDED — T3]** The Gate Room is now the home of **high-blast-radius and non-routine gates only**. Routine gates route to 10.27 Decision Stream. **Policy decides which gate goes where; the user never chooses.**

Single-column, generously spaced — deliberately the *least* dense screen. When a person is deciding whether to accept AI-authored change, the interface gets out of the way.

Each `GateCard` shows: the gate and its criteria with pass/fail per criterion · the artifact (diff, spec, design, test results) inline · `ProvenanceStamp` · `ConfidenceBar` with calibration · `RationaleBlock` (marked unverified) · `EvidenceBlock` if ablation was run · cost and duration · the loop history that produced it, including prior rejections.

Actions: **Approve · Rework · Steer · Escalate · Waive**.

**High-blast-radius gates** get a distinct treatment: madder header bar, ablation evidence mandatory and expanded by default, and Approve requires press-and-hold with all three access paths (§7.2).

`gate-iris` on entry and exit. Approving fires `beat-up` on a corner weave inset, so the consequence of the decision is seen immediately.

| v2.0 additions | | |
|---|---|---|
| E-GR-01 | **N-of-M approval progress** and **SoD block explanation** inline on the card (10.32). When SoD blocks, name the rule, the conflicting act, and who can approve instead. | MUST v1.x |
| E-GR-02 | **Steer** as a fifth action beside Approve / Rework / Escalate / Waive. | MUST v1 |
| E-GR-03 | **Rework reason taxonomy**, specified rather than implied: `incorrect · incomplete · out-of-scope · style · security · performance · test-quality · other`, each mapping to a Trainer signal class (P-15). | MUST v1 |
| E-GR-04 | Show the **gate's history**: prior openings, prior rework reasons, and how many L2 iterations produced the current artifact. | MUST v1 |
| E-GR-05 | Link to the Decision Stream for routine gates; make the Gate Room the explicit home of high-blast-radius decisions. | MUST v1 |
| E-GR-06 | **Keyboard and accessible paths for press-and-hold** (§7.2, A-01, P-03). | MUST v1 |
| G-10 | **Contextual "why this gate"** — every criterion links to the policy line that created it and the commit that activated the policy. | MUST v1.x |

---

### 10.7 Ledger / Selvage Viewer · **MUST v1**

**Purpose.** The audit record. Not a blockchain visual — a woven, locked edge.

Left: the `Selvage` — a continuous vertical strip of locked stitches, one per entry, coloured by action type, with a verify-through marker and a prominent tamper indicator if verification fails. Right: the entry stream, filterable by story, agent, phase, loop, action type, decision, and date.

Selecting an entry shows the full record: prompt digest and expandable content, retrieved memory refs, tool calls, output, resulting diff, confidence, cost, latency, approver identity, policy and skill versions, **model and model version**.

**Verification is always visible.** A persistent header: `Chain verified to 4,417 · signed 14:22 · anchored ✓`. If verification fails, the entire screen gains a `--ml-halt` border, the first divergent sequence is named, and everything below renders desaturated. **A broken chain must be impossible to overlook.** The verdict is computed sidecar-side; the UI displays a verdict it did not compute (§12.4).

| v2.0 additions | | |
|---|---|---|
| E-LG-01 | **Query builder** over `FR-M10-12`: filters, aggregates, time range, full-text, saved queries. | MUST v1 |
| E-LG-02 | **Natural-language query** box (`FR-M10-13`) with the resolved structured query shown, so the user learns the query language. | SHOULD v1.x |
| E-LG-03 | **Erasure UI** (`FR-M10-14`): a subject-scoped erasure request showing which blobs will be crypto-shredded, confirming the chain remains verifiable, and recording the erasure itself. | MUST v1.x |
| E-LG-04 | **Cold-storage indicator** for compacted entries (`FR-M10-15`) — digest retained, blob archived, fetch on demand. | SHOULD v1.x |
| E-LG-05 | **Shareable slice** (`FR-M10-17`): select a range → signed self-verifying HTML bundle → copy link / download. | SHOULD v1.x |
| E-LG-06 | **Deep links:** `meridian://ledger/4417` and equivalents for every entity, resolvable from chat, PR descriptions and Jira comments (X-03). | MUST v1 |
| V-05 | Selvage stitches render tactile — 1px inner highlight, 1px cast shadow onto the cloth. | SHOULD v1 |

---

### 10.8 CodeMap Viewer · **MUST v1**

**Purpose.** The codebase as a navigable knowledge graph.

Force-directed graph, WebGL-rendered, over the repository's structure: modules, packages, classes, functions, contracts, tests and their relationships. Node colour by cluster, node size by centrality, edge weight by coupling strength.

**What makes this Meridian's rather than a generic graph:**

- **Agent overlay.** Tint nodes by which agent last touched them and when. Recency renders as thread brightness.
- **Blast-radius projection.** Select a work packet; the graph highlights the projected impact set, dims everything else, and shows a count.
- **Semantic zoom.** Three levels — system (packages) / module (classes) / detail (functions and call edges). Level changes crossfade rather than pop.
- **Rework heat.** Colour nodes by rework density from the ledger. The parts of the codebase the agents keep getting wrong become immediately visible — the single most actionable view in the product for a tech lead.

Controls: fuzzy search with camera fly-to, cluster isolation, orphan filter, path highlight between two nodes, freeze layout, PNG/SVG export.

| v2.0 additions | | |
|---|---|---|
| E-CM-01 | **[AMENDED — ECO-03]** The graph source is the **CodeMap JSON format**, consumed not redefined; `.cgw` addressing for multi-repo graphs (ECO-04). | MUST v1 |
| E-CM-02 | **Duplicate / reuse-first overlay** (`FR-M28-04`): nodes an agent nearly re-implemented, with the existing implementation it should have used. | SHOULD v1 |
| E-CM-03 | **Freshness overlay:** nodes whose procedural memory is stale (`FR-M7-12`). | SHOULD v1.x |
| E-CM-04 | **Time scrub** integration with 10.29 — the graph at any ledger sequence. | SHOULD v1.x |
| E-CM-05 | Node **detail drawer** with LSP-derived references and definitions (`FR-M28-01`), not only the graph edge. | MUST v1 |

---

### 10.9 Loop Graph Viewer *(graph of loops)* · **MUST v1**

**Purpose.** The live execution topology — the six canonical loops, nested, with budgets.

Rendered in 2.5D perspective. Each loop is a ring in depth: L1 nearest, L6 furthest. Nodes are agent invocations, edges are transitions. The active path is drawn in woad and animates; completed paths are verdigris; rework edges arc back visibly with `unravel` styling.

Each ring carries a `LoopBadge` showing iteration against bound and a budget arc that fills. As a loop approaches its bound the ring tints weld; on breach, madder.

Drag to orbit, scroll to dolly, click a node to inspect, `F` to frame the active path. A 2D top-down DAG fallback is available and is used automatically under reduced motion.

| v2.0 additions | | |
|---|---|---|
| E-LP-01 | **Budget breakdown per loop** — tokens, wall clock and cost as three arcs, not one. | SHOULD v1 |
| E-LP-02 | **Escalation edges** drawn to the human when a bound is breached, terminating at the Gate Room. | MUST v1 |
| E-LP-03 | **Backpressure state** (`FR-M8-13`): a paused loop rendered as a held shuttle with the provider named. | SHOULD v1 |
| P-14 | **Label-collision behaviour specified**: below 620px width, ring labels move above the ring and abbreviate; below 420px, only the active ring is labelled. Hiding labels silently is not acceptable. | MUST v1 |

---

### 10.10 Architecture & C4 Viewer · **SHOULD v1.x**

Four levels with animated zoom between them:

| Level | Content |
|---|---|
| **1 · System Context** | The system, its users, and external systems |
| **2 · Container** | Applications, services, data stores, and the technology of each |
| **3 · Component** | Components inside a selected container |
| **4 · Code** | Drops into the CodeMap viewer at that component |

Diagrams are **generated from the repository and the Architect Agent's ADRs, not hand-drawn**, and regenerate on change. A **drift indicator** shows where the documented architecture and the actual code have diverged, with each divergence listed — the feature architects will actually use.

Level transitions use a zoom-through, not a screen swap: the selected box expands to fill and its contents resolve. ADRs attach to elements as annotations; clicking one opens it in the Inspector with its ledger provenance.

| v2.0 additions | | |
|---|---|---|
| E-AR-01 | **Contract artifacts** (`FR-M22-02`, `FR-P4-13`) rendered on the container edges they govern, with contract-test status (`FR-P5-11`). | SHOULD v1.x |
| E-AR-02 | **Threat model overlay** (`FR-P6-06`) on the container view: trust boundaries and STRIDE annotations. | SHOULD v1.x |

---

### 10.11 UML Studio · **SHOULD v1.x**

One screen, seven diagram types, unified chrome. All generated from code and agent artifacts, all live.

| Diagram | Source | Notable |
|---|---|---|
| **Sequence** | Runtime traces + agent call graphs | **Agent sequence mode:** lifelines are agents, messages are the actual handoffs of a story, with real timings from the ledger |
| **Class** | Static analysis | Filter by package; show only what changed in this story |
| **ER** | Schema + migrations | Migration diffs highlighted; agent-authored migrations flagged |
| **Component** | Module boundaries | Overlaid with coupling strength from CodeMap |
| **State machine** | Detected state enums + the loop runtime | Shows both application states and loop states |
| **Activity** | Work packet graph | Swimlanes by agent |
| **Deployment** | IaC parsing | Environment selector |

Shared: layout engine selector, orthogonal/curved routing, focus+context dimming, diff mode (this story's changes against baseline, additions verdigris, removals madder), export to SVG/PNG/PlantUML/Mermaid.

**Agent sequence mode is the differentiator.** Nobody else can draw a sequence diagram whose lifelines are the AI agents that built the feature, with real timings and real message payloads pulled from the ledger.

| v2.0 additions | | |
|---|---|---|
| E-AR-03 | **Diagram-as-gate mode**: a diagram is the artifact under approval, with diff mode on by default. | SHOULD v1.x |

---

### 10.12 Flow Diagram Viewer · **SHOULD v1.x**

Business and process flows: the story's acceptance criteria rendered as a flow, the actual implemented control flow extracted from code, and **the two overlaid to show gaps**. Uncovered branches render hatched in madder. This turns "did the agents actually implement the acceptance criteria" from a review question into a picture.

Also hosts: data-flow diagrams, the DevSecOps pipeline flow, and the escalation flow.

---

### 10.13 Config Portal · **MUST v1**

**Purpose.** Everything configurable, organised by intent rather than by which module owns it.

Left nav, right detail pane, live preview where meaningful.

| Section | Contents |
|---|---|
| **Identity & Access** | Model providers, credentials (SecretStorage-backed, never displayed), agent identities |
| **Roles** *(v2.0)* | Human roles, permitted actions, SoD rules, delegation — 10.32 |
| **The Workforce** | Roster management, per-agent budgets, autonomy tiers and thresholds, probation criteria |
| **Phases** *(v2.0, T1)* | The policy phase set: id, code, name, colour role, gate. The source of every warp thread in the product. |
| **Capability Packs** | Installed skills, versions, digests, install/review/remove — links to Skill Forge |
| **Routing** *(v2.0)* | Model routing matrix, tiering, residency — 10.31 |
| **Loops & Budgets** | Per-loop bounds, per-story ceilings, escalation targets |
| **Gates & Policy** | DoR/DoD criteria, gate requirements, waiver policy, blast-radius rules, gate routing (Gate Room vs Decision Stream) |
| **Security** | Egress allow-list, sandbox settings, untrusted-content handling, secret-redaction patterns |
| **The Ledger** | Retention, signing key, anchoring, verification schedule, erasure |
| **Connectors** *(v2.0)* | Issue trackers, CI, SCM forge — 10.33 |
| **Notifications** *(v2.0)* | Classes, channels, digest, out-of-hours — 10.39 |
| **Tenants** *(v2.0, SEC-23)* | Client isolation boundaries |
| **Regulatory packs** *(v2.0)* | PCI-DSS, HIPAA, SOC 2, GDPR (`FR-M12-10`) |
| **Appearance** | Theme picker, motion, density (§4.4), Floor art level, sound, currency and time zone |
| **Integrations** | MCP servers with trust status |
| **Diagnostics** | Links to 10.38 Runtime & Operations |

**Every setting that changes agent behaviour shows its blast radius before saving** — "This lowers the Verify gate threshold. 3 agents currently at approve-per-phase would be affected." Policy changes are diffed against current and written to the ledger on save. Nothing that governs agents changes silently.

| v2.0 additions | | |
|---|---|---|
| E-CF-01 | New sections as listed above. | MUST v1.x |
| E-CF-02 | **Git-backed policy** (`FR-M12-12`): show the policy file path, the commit that activated it, and *Open PR* rather than *Save* for governed sections. | MUST v1.x |
| E-CF-03 | **Search across all settings.** They are already many and will double. | MUST v1 |
| E-CF-04 | **Emergency fast path** toggle (`FR-M12-13`) with Governor authentication, a visible countdown, and a Crown banner while active. | SHOULD v1.x |
| E-CF-05 | **Kill switch per agent class** (`FR-M12-14`) with the affected agents listed before confirmation. | MUST v1.x |
| E-CF-06 | Density modes specified as token deltas (§4.4), not per-component overrides. | MUST v1 |

---

### 10.14 Skill Forge · **MUST v1**

Browse, inspect, install, author and version capability packs.

Grid of `SkillCard`s: name, version, digest, target stack, declared tools, install source, trust status, usage count and the first-pass yield of agents while bound to it — **so you can see which capability packs actually make agents better.**

**Install flow is a security surface and is designed as one.** Selecting install opens a full review: every file, every script with its content, every external URL referenced, every tool the pack requests. Nothing installs without explicit confirmation, and the confirmation names the risk in plain language: "This pack can run scripts on your machine and requests network access to two hosts."

Authoring mode: a `SKILL.md` editor with live frontmatter validation, token-cost estimation for the discovery stage against the 3,000-token catalogue budget, and a test harness that binds the draft pack to a scratch agent on a sample task.

| v2.0 additions | | |
|---|---|---|
| E-SF-01 | **Upgrade flow** (`FR-M16-09`): regression status per bound agent before the new version activates, with a per-agent hold. | MUST v1.x |
| E-SF-02 | **Revocation** (SEC-19) with the paused-agent list and a rebind assistant. | MUST v1.x |
| E-SF-03 | **Registry browser** (`FR-M16-08`): internal catalogue with signing status, yield telemetry and organisation-wide usage. | SHOULD v1.x |

---

### 10.15 Onboarding Wizard *(hire an agent)* · **MUST v1.x**

Five steps that add a new agent role without touching extension source.

1. **Role** — name, tier, phase, responsibilities in plain language
2. **Portrait** — a grid of sprite portraits and a colour swatch row. Not cosmetic: the portrait and colour identify this agent everywhere for the rest of its life.
3. **Capability** — permitted skills, permitted tools, budgets, per-action confidence thresholds
4. **Governance** — gates it owns, escalation target, probation task set
5. **Probation** — runs immediately, live, with a `ProbationScorecard` filling as tasks complete

Admission is a decision, not a formality: the scorecard shows every probation task with pass/fail and the score against threshold, and a failing agent cannot be admitted. Admitted agents enter at `suggest` tier regardless of score, and the wizard says so.

On admission: `portrait-hire` — the portrait stitches in, the agent walks onto the Floor through the entrance, and the roster makes room.

| v2.0 additions | | |
|---|---|---|
| E-OB-01 | **Portrait art-direction rules:** the sprite set must be stylised and non-photoreal, must not encode ethnicity, gender or age as identity signals, and must pass VS Code Marketplace content policy. Diversity comes from silhouette, palette and accessory, not demographic cues. | MUST v1 |
| E-OB-02 | **Import path merges with onboarding**: an imported agent (`FR-M16-05`) enters at the Probation step of this same wizard. | MUST v1.x |
| E-OB-03 | **Probation task set editor** with expected outcomes visible, so a Governor can author probation for a new role. | SHOULD v1.x |
| A-08 | Sprite portraits are never the *only* identifier: name and id are always announced to screen readers. | MUST v1 |

---

### 10.16 Agent Inspector · **MUST v1**

Seven tabs, context-sensitive to the selected entity.

| Tab | Content |
|---|---|
| **Trace** | The decision record: inputs, retrieved memory with refs, tool calls, output, `ConfidenceBar`, `RationaleBlock` (marked unverified), `EvidenceBlock` if ablation ran, and a **Run ablation** control |
| **Terminal** | Live stdout/stderr from that agent's sandbox, ANSI-rendered, searchable, copy-as-issue |
| **Diff** | The change this agent produced, syntax-highlighted, with the originating prompt pinned above and open-in-editor per hunk |
| **Memory** | What this agent knows: procedural, semantic, recent episodic. Untrusted-tagged entries visibly marked. Individually removable with confirmation. |
| **Policy** | Current prompt/policy, version history, diff between versions, training lineage — which ledger evidence produced which change |
| **Messages** | Handoffs to and from other agents, threaded, with the ability to inject a human message |
| **History** *(v2.0)* | This agent's last N ledger entries, with the same row chrome as the Ledger |

| v2.0 additions | | |
|---|---|---|
| E-IN-01 | **Pop-out** to an editor tab and **pin** so two agents can be inspected side by side (X-17, T5). | SHOULD v1 |
| E-IN-02 | Trace tab: **reuse-first citation** (`FR-M28-04`) and **context assembly** (what was included and cut, `FR-M7-13`) as collapsible sections. | MUST v1 |
| E-IN-03 | Terminal tab: **follow / unfollow** output and a **send input** field for sandboxes that prompt. | SHOULD v1 |
| E-IN-04 | Messages tab: a human's injected message renders distinctly (linen border) and appears in the ledger as a steer. | MUST v1 |
| E-IN-05 | **History** tab as above. | SHOULD v1 |
| E-IN-06 | On narrow widths the slide-over gets a **backdrop, focus trap and `Escape`** (P-05, X-04). | MUST v1 |

---

### 10.17 Diff Theater · **MUST v1**

Full-screen review of an agent-authored change. Side-by-side or unified, with three columns of context the reference tools don't have: the **prompt** that produced each hunk, the **test** that covers it, and the **ledger sequence** that recorded it.

**[EXPANDED — S29]** Per-hunk control is **tri-state**: **accept / rework / edit-in-place**.

- **Edit-in-place** opens the hunk in Monaco. The human's change is captured as a "human corrected" rework signal (`FR-M25-05`), with a diff-of-diffs shown before commit so the human sees exactly what they are teaching the Trainer.
- A summary bar reads `12 accepted · 2 reworked · 1 edited` with a single commit action.
- **Moved-code detection** and **word-level intra-line diff**, so a reviewer is not re-reading a relocated block.
- Rejecting a hunk requires a reason from the E-GR-03 taxonomy and re-enters the loop.

---

### 10.18 Spec Studio · **MUST v1**

The clarified specification and the ambiguity register. Each ambiguity: the underspecified point, the agent's proposed resolution, its confidence, and **Accept / Amend / Escalate**. Acceptance criteria are shown with their coverage status once tests exist, so this becomes a live traceability matrix rather than a one-time artifact.

| v2.0 additions | | |
|---|---|---|
| E-SS-01 | **Story template conformance** and complexity tier shown at the top (10.33). | SHOULD v1.x |
| E-SS-02 | **Injected-instruction detections** (SEC-15) highlighted in the story text with the classifier's reason, so the human sees what was neutralised. | MUST v1 |
| E-SS-03 | **Ambiguity → question link**: an escalated ambiguity becomes a clarifying-question card (10.28), and the resolution flows back here. | MUST v1 |

---

### 10.19 Work Packet Board · **MUST v1**

Kanban by phase. Cards are `WorkPacketCard`s showing target paths, stack, required skill, acceptance tests, dependencies, blast radius, budget and assigned agent. Dependency arrows between cards. Overlap detection is visual — two packets targeting the same file render with a linked madder edge and cannot both be marked parallelisable.

| v2.0 additions | | |
|---|---|---|
| E-WP-01 | **Critical path** highlighted (`FR-P3-04`) and per-packet cost estimate vs actual. | SHOULD v1 |
| E-WP-02 | **Worktree and branch** visible on the card (10.35). | SHOULD v1 |
| E-WP-03 | **Feature flag** badge (`FR-P4-11`) and **license check** result (`FR-P4-12`) per packet. | SHOULD v1.x |

---

### 10.20 Verification Board · **MUST v1**

Test suites, runs, coverage delta, acceptance-criteria traceability, flake detection. The headline element is a **criterion-to-test matrix**: any acceptance criterion without a covering test renders as an open madder cell, and the gate cannot pass while one exists.

| v2.0 additions | | |
|---|---|---|
| E-VB-01 | **Flake quarantine** (`FR-P5-08`) as its own lane, with retry history and a *Release from quarantine* action. | MUST v1 |
| E-VB-02 | **Mutation score** (`FR-P5-07`), **performance regression** (`FR-P5-12`), **accessibility** (`FR-P5-13`) and **contract tests** (`FR-P5-11`) as additional gate rows with their own evidence drawers. | SHOULD v1.x |
| E-VB-03 | **Ephemeral environment** status (`FR-P5-10`): what was provisioned, its lifetime, and its cost. | SHOULD v1.x |

---

### 10.21 Security Assurance · **MUST v1**

SAST, SCA, secrets and SBOM delta for the change. Findings grouped by severity with the introducing ledger sequence. A dedicated panel for **agent-specific threats**: blocked egress attempts, denied tool invocations, out-of-scope modification attempts, and injected-instruction detections — each with the full context of what was attempted and by which agent.

| v2.0 additions | | |
|---|---|---|
| E-SA-01 | **Tool permission matrix**: agent × tool, with the policy source of each permission and every denial in the last N days as a heat cell. | MUST v1 |
| E-SA-02 | **Anomaly feed** (SEC-16): unusual tool calls awaiting confirmation, with the baseline they deviated from. | SHOULD v1.x |
| E-SA-03 | **AI-BOM and attestation** (`FR-P6-08`/`09`): the models, skills and policies that produced the change, and the in-toto attestation verification result. | SHOULD v1.x |
| E-SA-04 | **Output scan** results (SEC-20) — what was caught before code reached the working tree. | MUST v1.x |

---

### 10.22 KPI Observatory · **MUST v1**

The measurement screen, using the meridian/navigation half of the name: arcs, ascent lines and reference meridians rather than stock bar charts.

**Headline pairing, always together and never separable: throughput and stability on one axis pair.** When throughput rises while change failure rate rises with it, the chart draws a madder divergence band and states the finding in words. That is the documented AI-adoption failure pattern and the product is built to catch it in itself.

Also: first-pass yield by agent and phase, human intervention rate, rework taxonomy, cost per merged PR, tokens per story as a distribution (never a mean), time to merge, review turnaround, escaped defect density, calibration error by agent, autonomy tier distribution over time.

Every metric links through to the ledger slice it was computed from. **No number in this product is unauditable.**

| v2.0 additions | | |
|---|---|---|
| E-KP-01 | **Define the chart grammar**: axis rules, meridian-arc semantics, tooltip content, annotation events (policy promotion, tier change, incident), and the divergence band. The base named the visual language without specifying it. See X-07. | MUST v1 |
| E-KP-02 | **Agent-vs-human baseline** (`FR-M17-08`) and **token efficiency ratio** (`FR-M17-09`) panels. | SHOULD v1.x |
| E-KP-03 | **Chargeback view** (`FR-M26-03`): cost by team / client / cost centre with export. | MUST v1.x |
| E-KP-04 | **Tech-debt registry** (`FR-M17-07`) panel with export to the issue tracker. | SHOULD v1.x |
| E-KP-05 | **Alert thresholds** on any KPI, feeding 10.39. | SHOULD v1.x |
| G-08 | **Activity calendar heatmap** per agent and per repository. | COULD v2 |
| G-14 | **Human-time tracking** (`FR-M26-06`) alongside agent cost, for a true cost per change. | SHOULD v1.x |
| V-10 | Meridian arcs share the Weave's warp positions when plotting per-phase metrics. | SHOULD v1.x |

---

### 10.23 Exchange *(export / import)* · **MUST v1.x**

Package a tuned agent for another team, or adopt one. Export shows exactly what travels and what is stripped — credentials, episodic memory and untrusted-tagged content are excluded, and the pre-export scan result is displayed before the package is written. Import shows a full diff of what will be introduced, verifies the signature, and starts probation. The screen states plainly that an imported agent is not trusted on arrival.

| v2.0 additions | | |
|---|---|---|
| E-EX-01 | **Tenant boundary warning** (SEC-23) when exporting across clients; blocked by policy where configured. | MUST v1.x |
| E-EX-02 | **Retirement handover** (`FR-M16-10`): choose a successor and preview the procedural memory that transfers. | COULD v2 |

---

### 10.24 Focus Mode · **SHOULD v1.x**

A chromeless, ambient full-screen view — the Floor or the Weave, no panels, no controls, slowed motion, `Loom Ghost` theme. For the second monitor and the wall screen in a delivery area. Gates and breaches break through as full-bleed overlays; nothing else does.

| v2.0 additions | | |
|---|---|---|
| E-FM-01 | **Portfolio focus:** cycle through active stories' floors on a timer, for the wall screen. | SHOULD v1.x |
| E-FM-02 | **Burn-in protection** for OLED wall displays: slow drift of the whole composition by a few pixels per minute. | SHOULD v1.x |
| G-16 | **Wall mode QR** opening the same story on a phone as a read-only signed ledger slice. | COULD v2 |

---

### 10.25 Story Hub *(S25)* · **MUST v1**

**Serves:** M19, M21, M25, M26.

The screen the product most lacked. Previously the story was a chip in the Crown and its facts were scattered across Spec Studio, Weave and Gate Room.

- **Header:** story id, title, source (Jira / Rally / file), complexity tier, autonomy profile, branch and worktree, base branch.
- **Acceptance criteria** with live coverage status.
- **Phase timeline:** entry and exit timestamps per phase, gate durations, `SLABar` with predicted completion and slip warning (`FR-M21-06`).
- **Cost:** estimate at ingest with interval, actual to date, ceiling, and a **What-if** slider — move the ceiling and see which packets would be cut (`FR-M26-01`).
- **Linked artifacts:** PR(s), CI runs, ADRs, journey report.
- **Actions:** Dry-run · **Abort story** (press-and-hold; shows what will be removed and confirms the primary tree is untouched, `FR-M18-04`) · Open worktree in new window · Pause.
- **Steer composer** (10.28) docked at the bottom.

| v2.0 additions | | |
|---|---|---|
| G-07 | **Story Gantt** — phases and gates over *calendar* time with the SLA line, alongside the Weave (which is over *ledger sequence*). Two axes, two questions. | SHOULD v1.x |

---

### 10.26 Portfolio *(S26)* · **MUST v1.x**

**Serves:** M21.

Every active story. Columns: story, phase, gate state, agents assigned, spend vs ceiling, SLA status, predicted completion. **Rows are mini-weaves** — a 3px-row texture of each story's cloth, so the whole portfolio reads as fabric samples.

- **Queue lane** above the table: prioritised backlog with WIP limit indicator and drag-to-reprioritise (X-20).
- **Contention panel:** which stories are waiting on model rate limits, sandbox slots or overlapping files (`FR-M21-05`), with the arbitration decision shown.
- Filters: team, client, cost centre, tier, SLA-at-risk.

---

### 10.27 Decision Stream *(S27)* · **MUST v1**

**Serves:** M12, M20, M25.

The Gate Room is designed for deliberate, one-at-a-time decisions. Approvers with twenty low-risk gates need a faster instrument — without losing rigour.

- One gate at a time, full-height, keyboard-driven: `J`/`K` next/previous, `A` approve, `R` rework (opens reason), `E` escalate, `S` steer, `?` expand evidence.
- **Not a swipe interface** (§3). Approve requires the artifact to have been scrolled into view; the rubber-stamp detector (`FR-M20-06`) counts time-on-artifact and shows the approver their own median beside the organisation's.
- **High-blast-radius gates are excluded** and redirect to the Gate Room (T3).
- Batch approve for gates the policy marks batchable, with an explicit list of what is being approved and a single press-and-hold.

| v2.0 additions | | |
|---|---|---|
| G-05 | **Approval batching by risk class** with a policy-defined batch size. | SHOULD v1.x |

---

### 10.28 Steer & Clarify *(S28)* · **MUST v1**

**Serves:** M25. Two components, docked wherever an agent is in context — Story Hub, Inspector, Gate Room, Floor.

**Steer composer.** Free text plus structured `SteerChip`s (`prefer`, `avoid`, `constraint`, `example`), a target selector (this packet / this agent / this story), and a preview of exactly where the guidance will enter the next iteration's context. Sent steers appear in the Weave as a cochineal-dotted tick on the row they influenced (E-WV-02).

**Clarifying-question card.** The agent's question, its proposed options with its own recommendation marked, confidence for each, and a free-text answer. Answering resumes the loop; the card shows the resume with a `beat-up`. Unanswered questions surface in the Signal rail, the Command Center tile (E-CC-02), and the Crown badge.

**Uncertainty prompt.** When an agent stops because confidence fell below the action-class threshold (`FR-M25-03`), the card states the threshold, the stated confidence, the calibration context, and offers *Proceed anyway* (ledger-recorded as a human override), *Steer*, or *Take over*.

---

### 10.29 Replay & Time-Travel *(S30)* · **MUST v1** *(developer-facing)* · **SHOULD v1.x** *(user-facing)*

**Serves:** M4 (`FR-M4-07`), M27.

- A **timeline scrubber** across the story: ledger sequence on the x-axis, phases as bands, gates as markers, rework as madder ticks. Drag to any point; every other view (Weave, Floor, Inspector, Loop Graph) re-renders to that moment.
- **[T6 — global time-travel state]** While viewing the past: a weld `TimeTravelBanner` in the Crown reading `viewing seq 4402 · live is 4417`, the selvage beyond the viewed sequence renders desaturated, and **every action except Fork is disabled**. Time-travel is a global state, not a per-screen mode.
- **Fork from here:** with a cassette present, re-run from a checkpoint with modified state for ablation or debugging. Forks render as a branch off the timeline and are ledger-tagged as replays, never as live work.
- **Cassette panel** (developer mode, X-23): recorded calls, hit/miss, and a **fault-injection console** (`FR-M27-04`) to kill the sidecar, time out a model, or corrupt an entry — with the resulting recovery shown live.
- This is also the screen that makes a governance-meeting narrative possible: play a story from ingest to merge at 20× speed.

| v2.0 additions | | |
|---|---|---|
| G-09 | **Playback export** — an MP4 or animated SVG of a story's Weave building, for demos and retrospectives. Comes almost free from this screen. | COULD v2 |

---

### 10.30 Memory Studio *(S31)* · **MUST v1**

**Serves:** M7 (`FR-M7-05`, `07`, `09`, `11`, `12`, `13`).

The Inspector's Memory tab shows one agent's memory. Nothing previously let a human curate the organisation's.

- **Three layers as columns:** Organisation › Team › Repository, with override arrows showing which entry wins (`FR-M7-09`).
- **Tiers as tabs:** procedural, semantic, episodic.
- **Entry cards** with provenance, `FreshnessBadge` (stale entries dimmed with a "code changed since" note), trust tag and pin state. Human-pinned entries (`FR-M7-11`) render with a linen border and cannot be edited by agents; the UI says so.
- **Contradiction queue** (`FR-M7-05`): pairs of conflicting entries side by side with the ledger evidence for each, and *Keep left / Keep right / Merge / Ask agent*.
- **Untrusted holding area** (`FR-M7-07`): content awaiting promotion, source marked, *Promote* requiring a reason.
- **Context assembly preview** (`FR-M7-13`): pick an agent and a task; see what would be included, what would be cut, and why, with token cost per entry.
- Import / export as a Markdown bundle with a diff view (`FR-M7-10`).

---

### 10.31 Model Routing Observatory *(S32)* · **SHOULD v1** · **MUST v1.x**

**Serves:** M8.

- **Routing policy as a matrix:** phase × task class → model, editable inline, with the Config blast-radius preview.
- **Live call stream:** model, tokens in/out, latency, cost, cache hit, structured-output validation result, and the agent and ledger sequence that made the call.
- **Failover and backpressure events** (`FR-M8-09`, `13`) as a timeline with the loops that were paused.
- **Provider health**, rate-limit headroom, region tags and data-residency compliance (`FR-M8-12`) — a provider outside policy renders in madder and is unselectable.
- **Redaction log** (`FR-M8-11`): what was redacted, from which prompt, before transmission.
- **Model comparison** (`FR-M26-05`): run a golden story against N configurations, compare yield / cost / latency in a small-multiples grid.

---

### 10.32 Human Roles & Approvals *(S33)* · **MUST v1.x**

**Serves:** M20.

- **Who am I:** identity source, role, permitted gate actions, active delegations, session age with re-authentication prompt (SEC-22).
- **Roles matrix:** role × gate action, editable by Governor only.
- **Separation-of-duties explainer:** when SoD blocks an action, name the rule, the conflicting act ("you ingested this story at 14:02"), and who can approve instead.
- **N-of-M progress** on high-blast gates via `ApprovalProgress`: who has signed, who remains, and *Request approval*.
- **Delegation composer** with expiry; active delegations visible to both parties.
- **Approval hygiene** (`FR-M20-06`): per-approver median time-on-artifact, expansion rate, and the rubber-stamp warning — shown privately to the approver and in aggregate to Governors.

| v2.0 additions | | |
|---|---|---|
| G-15 | **Session handoff** — "I'm off; here is what needs deciding" generates a summary and assigns delegation. | COULD v2 |

---

### 10.33 Connectors & Write-back *(S34)* · **MUST v1** *(Jira)* · **v1.x** *(rest)*

**Serves:** M19.

- **Connector cards:** Jira Cloud, Jira DC, Rally, ADO, GitHub Issues — status, auth, last sync, field mapping.
- **Field mapping editor** with a live preview of a real story rendered through the mapping.
- **Write-back rules:** per transition, on/off, with a preview of the comment that will be posted and the transition that will fire. Done transitions show the human-approval prerequisite as a locked rule (`FR-M19-03`).
- **Story templates** (`FR-M19-05`) and **complexity-tier heuristics** (`FR-M19-06`), each editable with an example story classified live.
- **Import queue** for batch and epic ingestion (`FR-M19-07`).

---

### 10.34 Delivery Pipeline *(S35)* · **MUST v1.x**

**Serves:** M23.

- The L4 Delivery loop extended visually to its true end: PR opened → CI → review → merge queue → merged.
- **CI runs inline** with job status, logs on demand, and re-entry into L2 shown as a rework row in the Weave with the failing job as its reason (`FR-M23-02`).
- **Review comment ingestion** (`FR-M23-03`): human PR comments listed with the agent and hunk they target, their classification as rework signal, and the Trainer attribution.
- **CODEOWNERS-derived** reviewer assignment (`FR-M23-04`) and merge-queue position (`FR-M23-05`).
- **Multi-repo:** linked PRs in dependency order, with merge blocking shown as warp threads between repos (`FR-M22-03`).

---

### 10.35 Repositories & Worktrees *(S36)* · **MUST v1** *(single repo)* · **v1.x** *(multi)*

**Serves:** M18, M22.

- **Per story:** repository, base branch, story branch, worktree path, disk usage, commits (agent-signed indicator, `FR-M18-06`), and retention countdown after merge or abort (`FR-M18-09`).
- **Conflict surface** (`FR-M18-03`): human uncommitted changes overlapping a pending packet's target paths, listed before the packet starts, with *Stash / Commit / Skip packet*.
- **Workspace manifest editor** for multi-repo stories (`FR-M22-01`) with contract artifacts (`FR-M22-02`) attached to the cross-repo edges.

---

### 10.36 Documentation & Journey Report *(S37)* · **SHOULD v1.x**

**Serves:** M29.

- Documentation Agent output as a **diff against existing docs**, with the public-API-change gate criterion (`FR-M29-02`) shown.
- **Journey report builder:** choose sections (spec, decisions, packets, tests, gates, cost, ledger slice) and export to Markdown / PDF / Confluence, with a **print stylesheet** designed for it (X-24) — the Weave rendered as a static image at print resolution.
- **ADR fitness-function results** (`FR-M29-04`) as a checklist.

---

### 10.37 Calibration & Trust *(S38)* · **SHOULD v1**

**Serves:** M13 (`FR-M13-03`, `09`), M12 autonomy tiers.

- Per agent and per action class: stated confidence vs observed outcome as a **`ReliabilityDiagram`**, with the calibration error trend.
- **`AutonomyLadder`:** the four tiers as rungs, each agent as a token on its rung per task class, thresholds drawn, and the distance to promotion or demotion shown. Promotion and demotion events as ledger-linked markers.
- **Trust score decomposition:** yield, calibration, tenure, incident linkage.

---

### 10.38 Runtime & Operations *(S39)* · **MUST v1**

**Serves:** M3, M30. Extends what was previously a Config subsection into a real screen.

- **Sidecar:** state, PID, interpreter path and how it was resolved (`FR-M3-05`), **remote host when under VS Code Remote** (`FR-M3-11`), resource use, restart count, log tail with level filter, *Restart*, *Collect diagnostics bundle*.
- **Doctor** (`FR-M30-01`): each check with pass / fail / fix-it action.
- **Backup and restore** (`FR-M30-02`) with integrity result; **state migration** status (`FR-M30-03`); update channel and rollback (`FR-M30-04`).
- **OpenTelemetry export** status (`FR-M30-06`).
- **Uninstall** (`FR-M30-08`) with the ledger-preservation confirmation.

---

### 10.39 Notification Center *(S40)* · **MUST v1**

**[T4 — RESOLVED]** §7.1's interrupt rule survives for toasts and OS notifications: **gates and breaches only.** This inbox is a *pull* surface and does not violate it.

- An inbox reachable from the Crown badge: gates, clarifying questions, breaches, budget warnings, CI failures, SLA slips, trainer candidates ready, imports awaiting probation review.
- Each item **actionable inline** where the action is one click (approve a batchable gate, answer a question, acknowledge a warning).
- **Digest mode** and out-of-hours queueing (`FR-M25-08`). Snooze with a reason.
- **Delivery channels per class:** in-app, VS Code toast, OS notification, Slack / Teams / email via connector — configured in Config. Full model in X-11.

---

### 10.40 First-Run & Guided Setup *(S41)* · **MUST v1**

**Serves:** `NFR-14` — 15-minute time-to-first-value. Named in the implementation plan, never designed.

Five steps: connect a model credential → point at a repository → pick a first stack skill → run the bundled sample story as a dry-run → watch the Weave build. Each step shows the Doctor check it satisfies.

**The sample story's dry-run is a real run** against a bundled sample repository, not a video. The user sees a real Weave, a real ledger entry, a real gate, and approves one real thing.

Skippable, resumable, re-launchable from Config. Loading uses `warp-string` (§8.2, V-08) and the empty-state illustration gains threads as steps complete (V-09).

---

### 10.41 Keyboard Map & Help *(S42)* · **SHOULD v1**

- A `?` overlay listing every shortcut for the current screen, **generated from the command registry** (X-12) so it cannot drift.
- Contextual help affordance per panel ("what is the selvage?") opening a short in-product explainer with the vision's metaphor table.
- Guided tours per screen, launchable once and dismissible forever.

---

### 10.42 Editor-Resident Surfaces · **SHOULD v1.x**

**Serves:** M24. Not a dashboard screen — the editor itself as a Meridian surface. This is where an engineer who never opens the dashboard still meets the product.

| ID | Surface | Priority |
|---|---|---|
| G-01 | **Agent cursors in the editor.** Live, named cursors showing where agents are editing in the story worktree, like multiplayer editing. The most visceral possible answer to "what is happening right now." | SHOULD v1.x |
| G-02 | **Minimap overlay** of agent-touched regions, coloured by state. | SHOULD v1.x |
| G-03 | **Explain-this-line** from the gutter → the decision record → the ablation, in one hover-and-click. Makes XAI reachable without opening the dashboard. | SHOULD v1 |
| — | **Hover provenance** (`FR-M24-02`) and **git blame decoration** (`FR-M24-04`) per §7.1. | SHOULD v1 |
| — | **Code actions** (`FR-M24-03`): "Ask Meridian to fix", "Ask Meridian to test this", "Explain this change". | SHOULD v1.x |
| — | **`@meridian` chat participant** (`FR-M24-01`) with `/ingest`, `/status`, `/explain`, `/why`, `/halt`, `/approve`, `/steer`. Gated on `D11` (§19). | SHOULD v1 |

---

## 11. Cross-Cutting Interface Systems

Systems that span every screen. Named or implied in v1.0, specified here. Each needs its own design work; none belongs to a single screen.

| ID | System | What must be specified | Priority |
|---|---|---|---|
| X-01 | **Omnibar (⌘K)** | Scopes (commands / agents / stories / packets / ledger / settings), ranking, recents, natural-language commands ("halt Kenji", "approve the design gate") with a confirmation preview, and the result card anatomy. | MUST v1 |
| X-02 | **Selection model** | One shared selection across Roster, Floor, Weave, tables, graphs, Inspector. Multi-select semantics, `Shift`/`Ctrl` behaviour on canvases, and what "selected" looks like in each renderer. | MUST v1 |
| X-03 | **Routing & restore** | Screen state as a serialisable route (`screen / entity / filters / time-travel seq`), back/forward navigation, restore-on-reload to the last route, and deep links (`meridian://`). | MUST v1 |
| X-04 | **Dialog, sheet, drawer, panel** | When each is used; modal only for destructive confirmation; sheet at mobile width; drawer for detail; every one with focus trap, `Escape`, and return-focus. | MUST v1 |
| X-05 | **Destructive-action pattern** | Press-and-hold (Halt, high-blast approve, abort), typed confirmation (promote), two-step confirm (accessible alternative). Which actions get which, and all three access paths for each. | MUST v1 |
| X-06 | **Data table primitive** | Sticky header and first column, virtualisation, resize / reorder / pin, sort, filter, saved views, CSV export, row actions, bulk select, density modes, empty and loading states. | MUST v1 |
| X-07 | **Chart grammar** | Axes, scales, legends, tooltips, annotations, colour use (state dyes only where state is meant), meridian-arc semantics, and reduced-motion behaviour. | MUST v1 |
| X-08 | **Markdown & agent-output rendering** | Sanitised markdown subset, code block styling, tables, max width, link policy (external links require confirmation — egress), and the "not verified" framing on any rationale. | MUST v1 |
| X-09 | **Agent copy rules** | Voice for agent-written strings: sentence case, present tense, names the artifact, no emoji, no flattery, no apology, ≤48 chars for status, ≤72 chars per line for prose. Enforced sidecar-side, not in the webview. | MUST v1 |
| X-10 | **Localisation & formats** | Externalised strings (`NFR-21`); **currency** — cost in the workspace's currency, not only USD, with the conversion rate and its date on hover (T7); number and date formats; time zones (every `Timecode` carries a zone; the Crown shows the active zone); RTL readiness. | MUST v1.x |
| X-11 | **Notification model** | Classes, severity, interrupt vs inbox, channels, digest, snooze, out-of-hours. The model behind 10.39. | MUST v1 |
| X-12 | **Keyboard command registry** | Every action registered with an id, label, shortcut and screen scope. The Omnibar, the Loom Bar and the keyboard map all generate from it. | MUST v1 |
| X-13 | **Error boundaries** | Per-screen boundaries so one crashed renderer does not take down the shell; the boundary shows last-known state, the error class, and *Reload screen* / *Report*. | MUST v1 |
| X-14 | **Offline & degraded modes** | Sidecar down, model provider down, connector down, ledger verification failed — each with its own banner, permitted actions and recovery path, not one generic "stale". | MUST v1 |
| X-15 | **Presence** | When multiple humans share a workspace: who is viewing what, who holds a gate, avatars in the Crown, and a soft lock on a gate someone is deciding. | SHOULD v1.x |
| X-16 | **Personalisation** | Per-user layout, density, theme, pinned panels, saved views, default screen, roster grouping. Stored via the extension host, never in the webview. | SHOULD v1 |
| X-17 | **Multi-panel** | Pop-out any screen to its own editor tab; two dashboards side by side; the Inspector pinned to a specific entity (T5). | SHOULD v1 |
| X-18 | **Undo semantics** | Which human actions are reversible in-UI (steer edits before send, rework reason edits within N minutes, filters, layout) and which are ledger-final (approve, promote, abort). **The UI must make the difference visible before the click.** | MUST v1 |
| X-19 | **Context menus** | Right-click on every entity with the same actions the Omnibar exposes, generated from the command registry. | SHOULD v1 |
| X-20 | **Drag and drop** | Roster → packet (assign), Floor agent → room (reassign), queue reorder, panel layout. Drop targets, ghost images, and a keyboard equivalent for each. | SHOULD v1 |
| X-21 | **Icon set enumeration** | The bespoke set is described in §13 but never listed. Enumerate the 40–60 glyphs, their loom vocabulary, and which Codicons are used where. | MUST v1 |
| X-22 | **Roster scaling** | 30+ agents: grouping by phase or tier, filter, overflow "+N" opening a sheet, and a portraits-only compact mode. | MUST v1 |
| X-23 | **Developer mode** | Frame-rate overlay, message-bus inspector, cassette panel, fault injection, token-cost overlay per panel. Hidden behind a setting. | SHOULD v1 |
| X-24 | **Print styles** | Weave, Journey Report, Ledger slice and KPI pages each get a print stylesheet. | SHOULD v1.x |
| X-25 | **Tenant switch** | For IT-services deployments (SEC-23): a tenant selector in the Crown, hard visual separation (a tenant colour band), and a warning on any cross-tenant action. | MUST v1.x |

### 11.1 Global overlays

Two toggles that apply across every screen rather than belonging to one, folded here so they are implemented once:

| ID | Overlay | Priority |
|---|---|---|
| G-12 | **Confidence-weighted colouring** — every agent-produced element rendered at opacity proportional to its calibrated confidence. Low-confidence work literally looks tentative. | SHOULD v1.x |
| G-13 | **Cost overlay** — every element rendered with its token cost, making the expensive parts of a story spatially visible. | SHOULD v1 |
| G-04 | **Explicit feedback** — a thumbs signal on any artifact with a reason chip, feeding the Trainer as weak signal distinct from gate decisions. Humans have opinions between gates. | SHOULD v1.x |
| G-11 | **Comparison pinboard** — pin any two entities (agents, stories, candidates, weaves) and compare, without leaving the product. | SHOULD v1.x |

---

## 12. Renderer Specifications

*(was §11 in v1.0)*

### 12.1 WeaveCanvas

Canvas 2D with an offscreen buffer for committed rows (they never change, so they are drawn once and blitted). Only live rows and shuttles redraw per frame. Target 60fps with 400+ rows; degrade row height before degrading frame rate. DPR-aware. Rows virtualise above 2,000. **[V-01]** The over-under weave texture is drawn into the offscreen buffer, so it costs nothing per frame.

### 12.2 FloorCanvas

Canvas 2D, orthographic, 24px tile grid, sprite atlas with palette swapping so sprites re-tint per theme without new assets. A* pathfinding on the tile grid. Frame budget 8ms; when exceeded, drop idle micro-animations first, then walk-cycle frame rate, then fall back to static positions with a visible notice. Pauses entirely when the panel is hidden. **[E-FL-01]** Room grid is computed from the policy phase count, not hard-coded.

### 12.3 GraphCanvas

WebGL (PixiJS) for CodeMap at scale; SVG for graphs under 300 nodes where crispness and DOM accessibility matter more than throughput. Force simulation in a Web Worker so layout never blocks the UI thread. Level-of-detail: labels below 150 visible nodes, edges thin below 2,000, and above 5,000 nodes the renderer switches to aggregated cluster hulls with a notice.

The 3D perspective in the Dojo and Loop Graph is a **projected 2.5D**, not a full 3D scene — nodes are billboarded cards on a perspective grid. This keeps text crisp, which a true 3D scene would not. **[P-14]** Label-collision behaviour is specified per §10.9.

### 12.4 SelvageStrip

SVG. One stitch per entry, virtualised. **Verification state is computed in the sidecar, never in the webview** — the UI displays a verdict it did not compute, which is the correct trust boundary.

### 12.5 Canvas accessibility parallels **[P-06]**

Every canvas exposes a parallel accessible representation. **The parallel is always present in the DOM**, visually hidden, and reachable by a per-canvas **"Table view"** toggle as well as by tab order. It is not generated on demand. The Floor exposes an ARIA tree of rooms and agents; the Weave exposes a table of passes plus the A-04 summary; graphs expose lists of nodes and edges with their relationships.

---

## 13. Iconography & Sprite Art

**Icons.** A bespoke 20px set on a 20-unit grid, 1.5px stroke, square cap, built from thread and loom vocabulary — a shuttle, a shed, a warp bundle, a selvage stitch, a heddle. Deliberately not a generic icon library. Where a concept has no loom analogue, VS Code Codicons are used so the extension feels native; the two sets are reconciled by matching stroke weight and grid. **[X-21]** The full 40–60 glyph set must be enumerated, not merely described.

**Sprites.** 32×32 agent portraits and 32×48 floor sprites, 4-direction walk cycles at 4 frames, indexed colour so the palette swaps with the theme. Minimum 24 distinct portraits. Portraits are assigned at onboarding and are permanent — an agent's face is part of its identity in the ledger and on every screen. Art-direction rules in E-OB-01.

**[T9 — RESOLVED]** A **designed geometric fallback is approved**, not a placeholder: a circular token bearing a unique two-colour thread pattern per agent. The product ships with visual identity even if the portrait commission slips. The commission decision itself (`V1`) remains open.

**Illustration.** Reserved for empty states only: line drawings of an unstrung loom, an empty shuttle, an unfinished band. **[V-09]** One continuous drawing that gains threads as first-run steps complete. Never generic "AI" imagery.

---

## 14. Sound

Off by default. When enabled, four sounds only, all under 120ms, all derived from loom mechanics: the shuttle pass (a soft wooden click), the beat-up (a low thud), the gate opening (a rising two-tone), and the breach (a single sharp strike). Nothing loops. Nothing plays for routine success. Volume follows the OS; sound never conveys information that is not also visual. **[V-06]** If enabled, the shuttle click pans left-to-right with the pass.

---

## 15. Accessibility

Target: **WCAG 2.1 AA**, verified, not assumed.

- Contrast ≥4.5:1 for text and ≥3:1 for UI components and graphical objects, in all six themes. Verified in CI against the token sets.
- Every state has a non-colour encoding (§4.2). Checked at review.
- Full keyboard operation. Documented shortcuts for every action, generated from X-12. Roving tabindex in the roster, weave and graphs. `Escape` always closes the topmost layer. No keyboard trap in any canvas — canvases expose a focusable list equivalent (§12.5).
- Canvas content has a parallel accessible representation, always in the DOM (§12.5).
- Live regions: gates and breaches announce via `aria-live="assertive"`; routine passes via `polite`, rate-limited to one announcement per 3 seconds to avoid flooding a screen reader.
- Focus is always visible: 2px woad ring with 2px offset, never removed, never relying on colour alone (it also thickens).
- `prefers-reduced-motion` respected, plus an independent in-app motion setting and per-canvas toggles (§8.4).
- Text scales to 200% without loss of function; the shell reflows rather than clipping.
- Minimum hit target 28×28px, 32×32px for anything destructive.

### 15.1 v2.0 additions

| ID | Requirement | Priority |
|---|---|---|
| A-01 | **Press-and-hold has an accessible alternative everywhere** — keyboard hold plus a two-step confirm. Previously it existed nowhere. | MUST v1 |
| A-02 | **Colour-blind simulation in CI** (protanopia, deuteranopia, tritanopia) across all six themes, not only contrast ratio. The six dyes must remain mutually distinguishable under all three. | MUST v1 |
| A-03 | **Canvas hit targets** padded to the 28px minimum despite smaller visual radii. Floor agents at 13px violated this. | MUST v1 |
| A-04 | **Weave summary announcement** for screen readers, so the shape of the cloth is available without reading every row. | MUST v1 |
| A-05 | **Per-canvas motion toggle** for the Floor and Loop Graph, independent of global reduced motion — motion sickness is not the same concern as motion preference. | SHOULD v1 |
| A-06 | **Simplified mode** for the Command Center — one weave, one gate list, one halt button — for new users and for incident conditions. | SHOULD v1 |
| A-07 | **Dyslexia-friendly option**: letter-spacing and line-height presets in Appearance. | COULD v2 |
| A-08 | Sprite portraits are never the *only* identifier of an agent; name and id are always announced. | MUST v1 |

---

## 16. Performance Budgets

| Metric | Budget |
|---|---|
| Webview first paint | ≤600ms |
| Interactive shell | ≤1,200ms |
| Screen transition | ≤560ms total, no frame over 32ms |
| Interaction response | ≤100ms |
| Live state propagation (sidecar → pixel) | ≤1,000ms |
| Floor / Weave frame budget | 8ms; 60fps target, 30fps floor |
| CodeMap, 5,000 nodes | Interactive pan/zoom at ≥30fps |
| Webview idle memory | ≤180MB |
| Bundle, gzipped | ≤900KB JS, ≤120KB CSS, fonts ≤240KB subset |
| Long tasks | None over 50ms on the UI thread |

All budgets enforced in CI, **profiled on a low-spec target machine, not a developer workstation.** A regression over budget fails the build.

---

## 17. Technical Constraints

Binding, from `Requirements_Final.md` §M2:

- **CSP with nonce on every webview.** `default-src 'none'; script-src 'nonce-…'; style-src ${cspSource}; img-src ${cspSource} data:; font-src ${cspSource}`. No inline handlers, no `eval`, no CDN.
- **No `localStorage`, `sessionStorage`, or any browser storage.** All persistence via `getState()`/`setState()` and the extension host. Absolute — the webview may be destroyed at any time.
- **All resources via `asWebviewUri`** with `localResourceRoots` declared.
- **State survives hide/reload** through `WebviewPanelSerializer` and message replay. `retainContextWhenHidden` is not used for correctness and is unavailable in the sidebar view.
- **Single typed message bus**, discriminated union, schema-versioned, version checked on handshake.
- **All agent-produced text is escaped.** Markdown sanitised, HTML stripped, scripts and event handlers removed. Agent output is untrusted content and is rendered as such (X-08).
- **Theme from `--vscode-*` variables** when following VS Code; correct in light, dark and high contrast.
- **Degrades gracefully when the sidecar is down** — last-known state, visibly marked stale, never an empty or erroring view (X-14).
- **[v2.0] Works under VS Code Remote** (`FR-M3-11`) — the dashboard must not assume the sidecar or the repository is local.

---

## 18. Banned Patterns

Enforced at design review. Each has a reason; none is arbitrary.

1. All-caps tracked-out eyebrow labels above headings.
2. A different colour or weight on one word of a heading for emphasis.
3. Middle-dot-joined meta strings (`A · B · C`) as a layout device. Permitted only inside `ProvenanceStamp`, where the parts are genuinely a tuple.
4. `→` appended to button or link labels.
5. Identical border-radius on every element. Three values exist and each means something (§4.3).
6. Soft grey drop shadows under cards. Elevation is a hairline plus inner highlight.
7. Spinners. `thread-tension` replaces every one.
8. Progress percentages for story completion. Rows and passes instead.
9. Fade-and-slide-up entrances on sections, and scroll-triggered reveals.
10. Hover transitions on cards that do not open something.
11. Gradient washes as decoration.
12. Generic "AI" iconography: glowing orbs, particle fields, neural-net line art, brain glyphs.
13. Blockchain iconography of any kind. The substrate is a transparency log and the UI must not misrepresent it.
14. `--ml-halt` on anything except Halt All.
15. Toast notifications for routine success. Success is shown by the weave advancing.
16. Any state communicated by colour alone.
17. Any metric displayed without a path back to the ledger evidence.
18. Confidence displayed without its calibration context.
19. Agent rationale displayed without the "not verified" marking.
20. Apologetic error copy, and "Something went wrong."
21. **[v2.0]** Swipe-to-approve, or any approval gesture that does not require the artifact to have been seen.
22. **[v2.0]** Hover-only affordances. Anything reachable by hover is reachable by focus and by touch.
23. **[v2.0]** A canvas without a DOM parallel.
24. **[v2.0]** Any hard-coded phase count, phase name or phase colour outside the policy phase set.

---

## 19. Open Design Decisions

Decisions that remain genuinely open. Six of the ten gap-document decisions are resolved and recorded in §20.

> **Namespace reminder (§0.2):** `V1`…`V7` without a hyphen are decisions. `V-01`…`V-12` with a hyphen are visual refinements (§8.5). They are different things.

| # | Decision | Bearing | Needed by |
|---|---|---|---|
| `V1` | Sprite art: commissioned, generated, or licensed. 24+ portraits with 4-direction walk cycles is real production work. **Narrowed by T9** — a designed geometric fallback is approved, so this no longer blocks ship, only fidelity. | Floor character | Start of G0 (long lead) |
| `V3` | Archivo + Commit Mono licensing and subsetting for redistribution in a `.vsix`. Blocks the font pipeline. | Bundle size and legal | Week 1 of G0 |
| `V4` | Whether the Weave replaces the Command Center hero or stays a separate screen. | Density of the primary view | G2 |
| `V5` | 2.5D vs. flat 2D for Dojo and Loop Graph. 2.5D is more compelling; flat is more legible and cheaper. | Build cost and clarity | G5 |
| `V6` | Whether Focus Mode is a separate webview panel or a chrome-hiding state. | Multi-monitor ergonomics | G4 |
| `V7` | Density default: comfortable or compact, given the split audience. Token deltas are now specified (§4.4); only the default is open. | Which audience the product greets | G1 |
| **`D11`** | Whether v1 ships the `@meridian` chat participant (10.42). Chat is cheap and where engineers are; it also widens the prompt-injection surface. Mirrors `Requirements_Final.md` `D11`. | Reach vs. attack surface | G1 |
| **`D8`** | Whether the SDLC phase set is fixed at nine or configurable. **This document assumes configurable** (T1) and every renderer is specified accordingly. If the answer is "fixed", several specifications simplify. Mirrors `Requirements_Final.md` `D8`. | Warp Spine, Weave, Floor | Start of G0 |

*(`V2` is closed by T8; see §20.)*

---

## 20. Resolved Decisions

The ten decisions from `VIGUIX_GAPS.md` Part H, and how each is resolved in this document. Each resolution is applied to the specification text, not merely noted.

| # | Tension | Resolution |
|---|---|---|
| T1 | Nine phases hard-coded into the Warp Spine, Weave, Floor grid and phase codes | **The phase set is a policy artifact.** All renderers consume it. Floor grid computed as `ceil(sqrt(N+3))`. Two-letter codes assigned by policy with collision checking. §2, §7.2, §10.2, §10.3, §12.2 amended; banned pattern 24 added. |
| T2 | Command Center spec'd for one story; the product runs many | **Command Center stays single-story by design.** 10.26 Portfolio is the many-story view; the Crown selector (E-CC-03) switches. Stated explicitly in 10.1. |
| T3 | Gate Room vs. Decision Stream could split the mental model | **Policy routes gates.** Gate Room = deliberate, high blast radius, one at a time, low density. Decision Stream = routine, keyboard-driven, batchable. **The user never chooses.** 10.6 and 10.27 amended. |
| T4 | Notifications: interrupt-only rule vs. the need for an inbox | **The interrupt rule survives for toasts and OS notifications.** The inbox (10.39) is a *pull* surface and does not violate it. §7.1 amended. |
| T5 | Inspector is a sidebar; new features need it pinnable and comparative | **X-17 adopted.** The Inspector hosts in the side panel, an editor tab, or a split. §7.2 and E-IN-01 amended. |
| T6 | Time-travel changes the meaning of every screen; nothing said how | **Global time-travel state.** Weld Crown banner, desaturated selvage beyond the viewed sequence, and every action except Fork disabled. 10.29 and X-03 amended. |
| T7 | Cost shown in USD throughout; the organisation bills globally | **Workspace currency setting** with conversion rate and its date on hover. X-10 and `CostMeter` amended. |
| T8 | Floor described as possibly opt-in, but it hosts speech and human presence | **RESOLVED: Floor is default-on after the first completed story.** New users meet the Command Center first. Simplified mode (A-06) hides it. **Closes `V2`.** |
| T9 | Sprite art is the G4 schedule risk and agent identity depends on it | **A designed geometric fallback is approved** — a circular token with a unique two-colour thread pattern per agent. Ships with identity even if art slips. §13 amended. **Narrows `V1`.** |
| T10 | The prototype invented tab navigation; the base spec was silent | **The Loom Bar adopted into §7.2** — a scrollable tab row under the Crown with overflow, generated from the command registry, badges only for gates and questions. |

### 20.1 Prototype-exposed gaps, resolved

The sixteen items in `VIGUIX_GAPS.md` Part D, and where each is now specified.

| ID | Now specified in |
|---|---|
| P-01 Navigation | §7.2 The Loom Bar (T10) |
| P-02 Narrow-width warp | §7.3 |
| P-03 Halt All keyboard path | §7.2, A-01, E-GR-06 |
| P-04 Theme picker | §5 |
| P-05 Slide-over backdrop, focus trap, Escape | §7.3, X-04, E-IN-06 |
| P-06 Canvas accessibility parallels | §12.5 |
| P-07 Story selector | E-CC-03 |
| P-08 Roster truncation and scaling | X-09, X-22 |
| P-09 Table at narrow width | E-AW-01, X-06 |
| P-10 Per-panel "as of" stamp | E-CC-07, X-14 |
| P-11 Tooltips reachable by focus and touch | §7.2 |
| P-12 Font licensing and fallback stack | §6, `V3` |
| P-13 Animation implementation debt | §21, G8 |
| P-14 Label collision in 2.5D renderers | §10.9, §12.3 |
| P-15 Rework reason taxonomy | E-GR-03 |
| P-16 Empty states | §9.3, per-screen definition of done |

---

## 21. Implementation Impact

Where the v2.0 additions land in the `viguix-implementation.md` build phases. **One new phase is introduced: G6.5.**

| Phase | v2.0 additions |
|---|---|
| **G0 Foundation** | X-02 selection · X-03 routing · X-04 dialogs · X-05 destructive pattern · X-06 table primitive · X-12 command registry · X-13 error boundaries · X-21 icon enumeration · **T1 phase-set as data** · **T9 designed token fallback** · A-02 colour-blind CI · §4.4 density tokens · `V3` font decision |
| **G1 Command Center** | 10.25 Story Hub · 10.39 Notification Center · 10.41 Keyboard Map · X-01 Omnibar · X-11 notification model · X-14 degraded modes · X-22 roster scaling · E-CC-01/02/03/05/07 · E-AW-01/02/05 · E-IN-02/04/06 · A-01 · A-03 · P-01…P-11 |
| **G2 Weave / Ledger** | E-WV-01/02/04/07 · E-LG-01/06 · 10.29 (developer-facing) · V-01 · V-05 · A-04 |
| **G3 Decision Surfaces** | 10.27 Decision Stream · 10.28 Steer & Clarify · 10.17 tri-state diff (S29) · E-GR-02/03/04/05/06 · E-SS-02/03 · E-VB-01 · X-18 undo semantics |
| **G4 Floor** | E-FL-01/02/06/07 · V-03 · V-04 · V-07 · T8 · A-05 |
| **G5 Graphs** | E-CM-01/05 · E-LP-01/02 · P-14 |
| **G6 Modelling** | E-AR-01/02/03 |
| **G6.5 Organisation Surfaces** *(new)* | 10.26 Portfolio · 10.32 Roles · 10.33 Connectors · 10.34 Delivery Pipeline · 10.35 Repositories · X-15 presence · X-25 tenant switch · E-FL-03 |
| **G7 Governance & Learning** | 10.30 Memory Studio · 10.31 Routing Observatory · 10.36 Documentation · 10.37 Calibration & Trust · 10.38 Runtime · E-DJ-01/03 · E-CF-01…06 · E-SF-01/02 · E-SA-01 · E-KP-01/03 |
| **G8 Refinement** | 10.40 First-run (now designed) · 10.42 Editor surfaces · X-10 localisation · X-16 personalisation · X-17 multi-panel · X-24 print · §11.1 global overlays · V-02/06/08…12 · G-03/06/12/13 · P-13 |
| **v2 backlog** | G-08/09/15/16 · E-WV-06 · E-EX-02 · A-07 · V-06 |

**The critical path is unchanged:** G0 → G1 → G2 → G3. That sequence makes the product governable and therefore usable on real work. Everything else improves a product that already functions.

**Slip plan, revised.** Cut in this order, each leaving a working product: sound → Focus Mode → UML types beyond Sequence and Class → 2.5D (`V5`, ship flat) → the Floor (ship Floor List) → CodeMap rework heat.

**Never cut:** the Ledger viewer, the Gate Room, Halt All, the confidence-with-calibration pairing, the evidence-versus-narrative distinction, the Steer and clarifying-question surfaces, or any accessibility work. These are the features that make an autonomous agent system safe to run.

---

## 22. Changes from v1.0

### 22.1 Section renumbering

Five sections moved to make room for §11 Cross-Cutting Interface Systems. Update any external cross-reference.

| v1.0 | v2.0 |
|---|---|
| §11 Renderer Specifications | **§12** |
| §12 Iconography & Sprite Art | **§13** |
| §13 Sound | **§14** |
| §14 Accessibility | **§15** |
| §15 Performance Budgets | **§16** |
| §16 Technical Constraints | **§17** |
| §17 Banned Patterns | **§18** |
| §18 Open Design Decisions | **§19** |

§1–§10 keep their numbers, which is where nearly all cross-references point.

### 22.2 Amended base text

| Location | Change | Driver |
|---|---|---|
| §2 metaphor table | Phase set is a policy artifact, not nine fixed threads | T1 |
| §3 rationale | Swipe-to-approve added to the rejected list | 10.27 |
| §4.2 | Colour-blind CI verification added | A-02 |
| §4.4 | Density modes specified as token deltas (new) | E-CF-06 |
| §5 | Theme picker with preview replaces the cycle control | P-04 |
| §6 | Commit Mono fallback stack documented | P-12 |
| §6.1 | 4px baseline grid | V-11 |
| §7.1 | Notification rule scoped to interrupting notifications; editor surfaces and chat added | T4 |
| §7.2 | **Loom Bar added**; warp spine generated from policy; press-and-hold gets three access paths; Inspector poppable | T10, T1, A-01, T5 |
| §7.3 | Narrow-width warp specified; overlay focus-trap requirements | P-02, P-05 |
| §8.2 | `gate-glow` and `warp-string` added; `beat-up` and `halt-flash` amended | V-03, V-08, V-02, V-04 |
| §8.4 | Per-canvas motion toggles | A-05 |
| §8.5 | Visual refinements section (new) | V-01…V-12 |
| §9.1 | Ten new primitives; `AgentToken` hit-area rule; `ProvenanceStamp` gains model version | v2.0 screens, A-03, `FR-M13-10` |
| §9.3 | Degraded modes are four distinct states, not one "stale" | X-14 |
| §10.1 | Single-story by design, stated | T2 |
| §10.2 | Floor default-on; room grid generated | T8, E-FL-01 |
| §10.6 | Gate Room scoped to high blast radius | T3 |
| §10.17 | Tri-state per-hunk control, human-edit capture | S29 |
| §12.5 | Canvas parallels always in the DOM (new) | P-06 |
| §13 | Geometric fallback approved | T9 |
| §18 | Banned patterns 21–24 added | v2.0 |

### 22.3 Added unchanged

17 new screens (10.25–10.41) plus 10.42 · 94 enhancements folded into their parent screens · 25 cross-cutting systems · 16 prototype resolutions · 8 accessibility items · 12 visual refinements · 16 candidate features. Every ID preserved.

### 22.4 Not carried forward

`VIGUIX_GAPS.md` §0 (the coverage matrix) is retained as §23.1 rather than dropped, updated to show v2.0 status. Part I (priority summary) became §21.

---

## 23. Coverage Matrix & Index

### 23.1 Module → screen coverage, after merge

| Module | VIGUIX v2.0 screen(s) | Status |
|---|---|---|
| M1 Extension Host | §7.1, 10.42 | Covered |
| M2 Webview Dashboard | all | Covered |
| M3 Sidecar & IPC | 10.38 | Covered |
| M4 Loop Runtime | 10.9, 10.29 | Covered |
| M5 Agent Registry | 10.4, 10.15 | Covered |
| M6 Skill Loader | 10.14 | Covered |
| M7 Memory Fabric | 10.30, 10.16 | Covered |
| M8 Model Router | 10.31 | Covered |
| M9 Tool Layer | 10.21 | Covered |
| M10–11 Ledger & Chain Viewer | 10.7 | Covered |
| M12 Governance | 10.13, 10.6, 10.27, 10.37 | Covered |
| M13 XAI | 10.16, 10.37 | Covered |
| M14 Trainer | 10.5 | Covered |
| M15 Onboarding | 10.15 | Covered |
| M16 Replicator | 10.23, 10.14 | Covered |
| M17 Telemetry | 10.22 | Covered |
| M18 Workspace Isolation | 10.35, 10.25 | Covered |
| M19 Connectors | 10.33, 10.25 | Covered |
| M20 Human Identity | 10.32, 10.27 | Covered |
| M21 Portfolio | 10.26, 10.25 | Covered |
| M22 Multi-Repository | 10.35, 10.34, 10.10 | Covered |
| M23 CI/CD & Merge | 10.34 | Covered |
| M24 Chat & Editor | 10.42, §7.1 | Covered |
| M25 Steering & HITL | 10.28, 10.17, 10.25 | Covered |
| M26 Cost & Economics | 10.25, 10.31, 10.22 | Covered |
| M27 Replay & Testing | 10.29 | Covered |
| M28 Code Intelligence | 10.8, 10.16 | Covered |
| M29 Documentation | 10.36 | Covered |
| M30 Runtime Operations | 10.38 | Covered |

**Every module in `Requirements_Final.md` now has an owning screen.**

### 23.2 Index

| Namespace | Range | Count | Meaning |
|---|---|---|---|
| Screens | 10.1 … 10.42 | 42 | 24 from v1.0, 18 added (S25–S42; S29 folded into 10.17) |
| `E-` | E-AR-01 … E-WV-07 | 94 | Enhancements, folded into parent screens |
| `X-` | X-01 … X-25 | 25 | Cross-cutting systems (§11) |
| `P-` | P-01 … P-16 | 16 | Prototype-exposed gaps, all resolved (§20.1) |
| `A-` | A-01 … A-08 | 8 | Accessibility (§15.1) |
| `V-` | V-01 … V-12 | 12 | **Visual refinements** (§8.5) — hyphenated |
| `G-` | G-01 … G-16 | 16 | Candidate features, distributed to screens and §11.1 |
| `T` | T1 … T10 | 10 | Decisions, all resolved (§20) |
| `V` | V1 … V7 | 7 | **Open design decisions** (§19) — not hyphenated |
| `D` | D8, D11 | 2 | Decisions shared with `Requirements_Final.md` |
| **Total numbered items** | | **232** | |

---

*End of specification. This document supersedes `VIGUIX.md` v1.0 and `VIGUIX_GAPS.md` v1.0. Both remain valid as the record of how this specification was arrived at.*
