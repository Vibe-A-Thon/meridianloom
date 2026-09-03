# VIGUIX — Meridian Loom Visual Interface & Experience Specification

| | |
|---|---|
| **Document** | VIGUIX.md |
| **Version** | 1.0 |
| **Author** | Ravaleedhar Reddy |
| **Scope** | Every pixel of the Meridian Loom VS Code extension |
| **Companions** | `vision.md` (architecture) · `Requirements.md` (engineering) · `viguix-implementation.md` (build order) |

---

## Table of Contents

1. [The Brief](#1-the-brief)
2. [The Core Metaphor: Warp and Weft](#2-the-core-metaphor-warp-and-weft)
3. [Design Rationale — and What Was Rejected](#3-design-rationale--and-what-was-rejected)
4. [Design Tokens](#4-design-tokens)
5. [Theme System](#5-theme-system)
6. [Typography](#6-typography)
7. [Layout & Shell Architecture](#7-layout--shell-architecture)
8. [Motion System](#8-motion-system)
9. [Component Library](#9-component-library)
10. [The Screens](#10-the-screens)
11. [Renderer Specifications](#11-renderer-specifications)
12. [Iconography & Sprite Art](#12-iconography--sprite-art)
13. [Sound](#13-sound)
14. [Accessibility](#14-accessibility)
15. [Performance Budgets](#15-performance-budgets)
16. [Technical Constraints](#16-technical-constraints)
17. [Banned Patterns](#17-banned-patterns)
18. [Open Design Decisions](#18-open-design-decisions)

---

## 1. The Brief

**Subject.** A VS Code extension in which a governed organisation of AI agents delivers software. The agents work continuously, in parallel, at machine speed, on a real codebase.

**Audience.** Senior engineers, architects and delivery managers at a Global Top 5 IT services organisation. People who read dense instrument panels for a living and distrust anything that looks like a toy — but who will be watching a system whose work they did not personally do.

**The primary job of this interface.** To make an invisible, fast-moving swarm *legible, trustworthy and stoppable*.

Everything else is secondary. A beautiful dashboard that leaves an engineer unable to answer "what is happening right now, who did that, and can I stop it" has failed regardless of how it looks.

**The tension to design into.** Two audiences want opposite things from the same product. Engineers want density, keyboard control, and no ceremony. Delivery leadership wants a picture they can read across a room in a governance meeting. Meridian Loom resolves this with **two registers of the same data**: a spatial, ambient, watchable register (the Floor, the Weave) and a dense, instrument-grade register (the Command Center, the Ledger). Every entity is reachable from both. Neither is a simplified version of the other.

---

## 2. The Core Metaphor: Warp and Weft

The product is called Meridian Loom. A loom is not decoration here — it is a structurally accurate model of what the system actually does, and it is the source of the entire visual language.

| Loom | Meridian Loom |
|---|---|
| **Warp** — the fixed vertical threads, strung before weaving begins, defining the structure of the cloth | The nine SDLC phases. Fixed, ordered, always visible, never move. |
| **Weft** — the horizontal thread carried back and forth across the warp, building the cloth row by row | Agent passes. Each agent action is one pass of the shuttle across the phases it touches. |
| **Shuttle** — the object that carries the weft | The active agent. There is a visible, moving carrier for every piece of live work. |
| **Shed** — the gap opened in the warp for the shuttle to pass through | A gate. The warp opens, the pass goes through, the warp closes. Screen transitions use this. |
| **Beat-up** — pressing each new row tight against the last | Commit to the ledger. Each row locks permanently into the cloth. |
| **Selvage** — the self-finished edge that stops the cloth unravelling | The hash chain. The edge that proves the cloth was not unpicked. |
| **Unravelling** | Rework. A rejected pass visually pulls back out of the cloth. |
| **Finished band** | A merged story. |

**Why this matters practically.** A story's progress is not a percentage bar. It is a *woven band* that literally accumulates: nine warp threads, and rows of weft building upward as agents complete passes. You can see at a glance which phases are dense with rework and which passed clean in one row. That is a real information display, not a metaphor pasted on top of one.

The second half of the name earns its keep too. A **meridian** is a reference line for navigation and the point of a body's highest ascent. Meridian Loom's telemetry axis — the KPI Observatory — uses meridian lines, sextant-style arcs and ascent markers rather than generic bar charts.

---

## 3. Design Rationale — and What Was Rejected

Design work is judged partly on what it refuses. These were considered and rejected, with reasons, so that nobody reintroduces them later.

| Rejected | Why |
|---|---|
| **Straight pixel-art-office clone** (the Munder Difflin look, adopted wholesale) | It is genuinely brilliant at making agents feel like colleagues, and the ambient watchability is worth keeping. But adopted wholesale it reads as a novelty, and this product must survive a CMMI governance review. **Kept:** spatial agent representation, character identity, ambient legibility, speech as status. **Changed:** the Floor is one register of several, art direction is woven/textile rather than cubicle-sitcom, and every spatial element is backed by a dense view holding the same truth. |
| **Cream background + high-contrast serif + terracotta accent** | The current house style of generated design. Instantly recognisable as a default rather than a decision. |
| **Near-black + one acid-green accent** | The other current default. Also: a single accent cannot carry six agent states legibly. |
| **Identical rounded cards, one radius everywhere, same soft grey shadow** | Erases hierarchy exactly where this product needs hierarchy most — a gate awaiting approval must not look like a cost tile. |
| **All-caps tracked-out eyebrow labels above every heading** | Template chrome. Appears regardless of subject. Explicitly banned in §17. |
| **Progress percentages and donut charts** | A story is not 63% done. It is at row 14 of the weave with three unravelled passes in Verification. Say that instead. |
| **Generic "AI" visual signifiers** — glowing orbs, particle swirls, gradient meshes, neural-net line art | Says nothing about this system and dates immediately. |
| **A literal blockchain visual** — chained cubes, cryptocurrency iconography | The substrate is a Merkle transparency log, not a blockchain (see `vision.md` §6.1). The UI must not imply otherwise. The Ledger is rendered as **selvage**: a woven, locked edge. |

**Where the palette comes from.** Natural dye vernacular — the actual materials of a loom. Indigo vat, undyed linen, madder root, weld, woad, verdigris, cochineal. This gives six functionally distinct hues that are historically coherent with each other, so they harmonise without being tuned, and none of them is a stock UI accent.

---

## 4. Design Tokens

All tokens are CSS custom properties on `:root`, defined per theme, consumed by every component. No component hard-codes a colour.

### 4.1 Core palette (Indigo Vat — the default dark theme)

```css
/* ——— Ground ——— */
--ml-vat-900:      #0B0E1C;   /* deepest canvas, behind everything */
--ml-vat-800:      #11152A;   /* app canvas */
--ml-vat-700:      #171D38;   /* raised surface: panels */
--ml-vat-600:      #1F2748;   /* raised surface: cards, rails */
--ml-vat-500:      #2A3358;   /* hairlines, dividers, warp threads at rest */
--ml-vat-400:      #3A4570;   /* borders on interactive surfaces */

/* ——— Linen (text and undyed thread) ——— */
--ml-linen-100:    #F2EFE6;   /* primary text, highest emphasis */
--ml-linen-300:    #D5D0C2;   /* secondary text */
--ml-linen-500:    #9C9A90;   /* tertiary text, metadata */
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

**The `--ml-halt` rule.** This colour appears on exactly one control in the entire product: Halt All. It is reserved so that in a crisis the eye finds it in under a second without reading. Any other use is a defect.

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

Every state is encoded **twice** — hue plus shape or motion. This is an accessibility requirement, not a stylistic flourish.

### 4.3 Space, radius, elevation

```css
/* 4px base, 1.5 ratio at the large end */
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

**Radius carries meaning.** Circular means *an agent*. Anywhere you see a circle, an actor is involved. 2px means *data you can trust and select*. 6px means *a container*. There is no fourth value, so nothing gets a radius by accident.

**Elevation is not a drop shadow.** The default soft grey blur under every card is the SaaS-kit tell. Meridian Loom lifts surfaces with a hairline plus a top inner highlight — the way a raised thread catches light on real cloth — and reserves an actual cast shadow for modals only.

---

## 5. Theme System

Six themes ship. All are complete token sets; switching is instant and animated (`theme-crossfade`, §8).

| Theme | Ground | Character | Use |
|---|---|---|---|
| **Indigo Vat** | `#11152A` | Default. Deep blue-violet, dye-vat depth. | Default dark |
| **Sized Linen** | `#E7E4DA` | Light. Warm undyed linen with ink-blue text. Dyes darkened ~18% for AA on light. | Default light |
| **Iron Gall** | `#07080F` | Maximum contrast, near-monochrome, dyes at full saturation. | High contrast / accessibility |
| **Madder Dusk** | `#1A1013` | Warm dark. Red-brown ground, dyes shifted warm. | Long-session comfort |
| **Weld Dawn** | `#F0EBDC` | Light, warmer, higher-key. | Presentation / screen-share |
| **Loom Ghost** | `#0B0E1C` | Dark, dyes desaturated to 35%, motion halved. Reads as a photograph of the system. | Ambient / Focus Mode |

Plus **Follow VS Code** (default on first run): derives the token set from `--vscode-*` variables, mapping editor background, foreground and the six functional dyes onto the closest theme-provided accents while preserving the state→shape mapping. When following, the Meridian identity is carried by shape, motion and typography rather than hue.

```
Theme resolution order
  1. user explicit choice (workspace setting)
  2. Follow VS Code  ← default
  3. Indigo Vat fallback
```

**High-contrast handling.** When VS Code reports a high-contrast theme, Meridian force-switches to Iron Gall and disables all decorative motion regardless of user preference. Transparency drops to zero, all hairlines go to 2px.

---

## 6. Typography

Two families. Both bundled with the extension, both variable, both loaded from `asWebviewUri` under the CSP nonce.

| Role | Family | Why |
|---|---|---|
| **Display & UI** | **Archivo** (variable, with Archivo Expanded for display) | A grotesque with industrial signage heritage and a genuinely useful width axis. Not Inter, not Helvetica, not a system stack. The width axis is used as an active design element: display type is set **expanded**, echoing threads spreading on a loom. |
| **Data, code, hashes, telemetry** | **Commit Mono** (variable) | Engineered for code legibility with distinctive letterforms and a cursor-friendly rhythm. Every number, hash, path, diff, agent id and metric in the product is set in it. |

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

**Prose line length caps at 72 characters** anywhere prose appears (agent rationale, ambiguity descriptions, empty states).

### 6.2 Typographic rules

- Sentence case everywhere. No all-caps labels, including in tables and nav. The one exception is a three-letter phase abbreviation on the warp spine where vertical space is genuinely 18px.
- Never accent a single word in a heading with a different colour or weight.
- No label above content unless the content is ambiguous without it. `4,281` above the word "Tokens" is fine. "AGENT NAME" above "Priya, Architect" is not.
- Agent names are always set in Archivo 500. Agent *identifiers* (`architect-agent@2.1.0`) always in Commit Mono. The two are never interchanged.

---

## 7. Layout & Shell Architecture

### 7.1 Surfaces the extension occupies

| Surface | Content | Notes |
|---|---|---|
| **Activity Bar icon** | Meridian mark (a shuttle crossing three warp threads) | Badge shows open gate count in weld |
| **Primary Sidebar** (`WebviewView`) | The Rail — agent roster, active stories, gate queue | Always available, narrow, ~300px |
| **Editor Panel** (`WebviewPanel`) | The full dashboard: all screens in §10 | The main product surface |
| **Status Bar** | Loom state, active pass count, live spend, Halt All | Compressed to `⟡ 4 weaving · $2.18` |
| **Editor Decorations** | Gutter thread marks on agent-authored lines, coloured by state | Click opens Ledger at that entry |
| **Notifications** | Only for gates and breaches. Nothing else. | |

### 7.2 The dashboard shell

```
┌──────────────────────────────────────────────────────────────────────────┐
│  ⟡ MERIDIAN LOOM        EDB-12345 ▾    row 14      ⌘K      ◐ theme   ⏻   │  40px  Crown
├────┬─────────────────────────────────────────────────────────┬───────────┤
│    │                                                          │           │
│ W  │                                                          │  I        │
│ A  │                                                          │  N        │
│ R  │                  ACTIVE  SCREEN                          │  S        │
│ P  │                  (§10 — one of 24)                       │  P        │
│    │                                                          │  E        │
│ S  │                                                          │  C        │
│ P  │                                                          │  T        │
│ I  │                                                          │  O        │
│ N  │                                                          │  R        │
│ E  │                                                          │           │
│    │                                                          │  320px    │
│56px│                                                          │  collapse │
├────┴──────────────────────────────────────────────────────────┴──────────┤
│  ▣ Priya  ▣ Arun  ▣ Kenji  ▣ Sofia  ▣ Marcus  ▣ Lena  … +6      ROSTER   │  72px
└──────────────────────────────────────────────────────────────────────────┘
```

**The Crown** (40px). Story selector, live weave row counter, command palette, theme toggle, Halt All. Halt All sits at the far right in `--ml-halt`, always visible, never scrolls away, requires a 400ms press-and-hold to fire (accidental-click protection, with a filling ring showing progress).

**The Warp Spine** (56px, left, permanent). The single most important element in the product. Nine vertical threads, one per SDLC phase, top to bottom. Each thread's appearance encodes that phase's state for the active story:

```
  ┌────┐
  │ IN │  ▓▓▓▓  Intake      verdigris, solid    — passed, 1 row
  │ DE │  ▓▓▓▓  Design      verdigris, solid    — passed, 1 row
  │ PL │  ▓▓▓▓  Plan        verdigris, solid    — passed, 1 row
  │ BD │  ▓▒▓▒  Build       woad, in motion     — weaving now, row 9
  │ VF │  ░╱╱░  Verify      madder, hatched     — 2 unravelled passes
  │ SC │  ┊┊┊┊  Security    iron, dotted        — not reached
  │ RV │  ┊┊┊┊  Review      iron, dotted        — not reached
  │ RL │  ┊┊┊┊  Release     iron, dotted        — not reached
  │ OP │  ┊┊┊┊  Operate     iron, dotted        — not reached
  └────┘
```

Hovering a thread expands it to 200px with the phase name, gate status, agents present and pass count. Clicking navigates the main region to that phase's detail. The spine never disappears — in every one of the 24 screens, you always know where in the lifecycle the work is.

**The Inspector** (320px, right, collapsible to 0). Context-sensitive to whatever is selected anywhere. Tabbed: **Trace · Terminal · Diff · Memory · Policy · Messages**. This is the direct descendant of the reference's right-hand agent panel, made general: it inspects agents, passes, ledger entries, work packets and gates with the same chrome.

**The Roster** (72px, bottom). Every agent as a circular portrait with a state ring, name, current activity in one line, and a live token meter. Horizontally scrollable, keyboard-navigable with `[` and `]`. Drag an agent onto a work packet to assign. This strip persists across every screen — the workforce is never out of sight.

### 7.3 Responsive behaviour

The dashboard lives in an editor tab that a user will freely resize to a third of the screen.

| Width | Behaviour |
|---|---|
| `≥1400px` | Full shell. Inspector open. Roster shows 10+ agents. |
| `1100–1400px` | Inspector collapses to a 44px icon rail, expands on click as an overlay. |
| `800–1100px` | Warp Spine collapses to 28px (thread colours only, no abbreviations). Roster shows 6. |
| `<800px` | Single-column. Warp Spine becomes a horizontal strip under the Crown. Roster becomes a count chip that opens a sheet. Spatial screens (Floor, Weave) switch to their list equivalents automatically and say so. |

---

## 8. Motion System

Motion in Meridian Loom does one job: **show what changed and who changed it.** Every named animation below is tied to a real state transition. There are no decorative entrance animations, no scroll-triggered reveals, and no hover transitions on cards that do not open something.

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
| **shuttle-pass** | An agent begins a pass | A circular agent token travels left→right across the weave region, drawing a weft thread behind it. Trailing thread fades from full to 70%. | `--ml-dur-pass`, loops while working |
| **thread-tension** | Any loading / thinking state | The relevant warp threads develop a subtle 2px sine oscillation, amplitude decaying. Replaces every spinner in the product. | 1.4s loop |
| **beat-up** | A ledger entry commits | The newest weft row compresses upward against the previous row by 3px with `--ml-ease-beat`, and a 1px verdigris highlight sweeps along it once. | `--ml-dur-base` |
| **selvage-lock** | Chain head advances | The right edge of the weave gains one locked stitch; a brief 200ms crystallise (scale 1.4→1, opacity 0→1). | 200ms |
| **unravel** | Output rejected / rework | The rejected pass's thread animates backwards out of the cloth, the row above drops to fill, and the phase thread flips to hatched madder. Deliberately the most visually disruptive animation in the product — rework should feel like something was undone. | 520ms, `--ml-ease-unravel` |
| **shed-open** | Screen-to-screen navigation | **The signature transition.** The warp threads of the spine separate vertically (odd threads up, even down) opening a shed; the outgoing screen exits *through* the gap at 0.96 scale; incoming screen enters from the opposite side; warp closes. | `--ml-dur-scene`, `--ml-ease-shed` |
| **gate-iris** | Entering/leaving the Gate Room | A horizontal band iris in weld sweeps closed then open. Only used for gates. | 380ms |
| **roster-focus** | Agent selected | The portrait scales 1→1.12, its state ring thickens 2→3px, and a woad thread draws from the portrait to wherever that agent appears on the current screen. | `--ml-dur-quick` |
| **number-roll** | Any live metric changes | Digits roll vertically, per-digit, staggered 20ms. Tabular figures prevent reflow. | 240ms |
| **graph-settle** | Graph view opens or re-layouts | Force simulation eased in; nodes arrive with staggered 12ms opacity; edges draw along their path after nodes land. | `--ml-dur-settle` |
| **halt-flash** | Halt All fired | Full-bleed 3px `--ml-halt` border pulses twice; all motion in the product freezes mid-animation and desaturates to 40%. The frozen state is the point — the system visibly stopped. | 700ms, then static |
| **theme-crossfade** | Theme switch | Token values interpolate over 300ms. No flash of unstyled content. | 300ms |
| **portrait-hire** | Agent onboarded | The new portrait draws in stitch-by-stitch (a 12-step sprite reveal, top to bottom), then joins the roster with a `beat-up`. | 800ms, one-time |

### 8.3 Choreography rules

1. **One orchestrated moment per screen entry.** `shed-open` carries the transition. Content inside the new screen does not additionally fade-and-slide-up. Sequenced section reveals are banned.
2. **Never animate more than three things simultaneously** outside the Floor and Weave renderers, which are continuous simulations and are exempt.
3. **Motion follows causality.** If an agent caused a change, the animation starts *at that agent's position* — from its roster portrait, or its position on the Floor. The eye is led from cause to effect.
4. **Live regions never move under the cursor.** Any list that can receive new rows while being read (Ledger, Messages, Trace) pins scroll position and shows a "3 new below" chip instead of pushing content.

### 8.4 Reduced motion

`prefers-reduced-motion: reduce` is respected absolutely, and is also independently settable in the Config Portal (a user may want VS Code motion but not a simulated office floor).

| Animation | Reduced-motion substitute |
|---|---|
| shuttle-pass | Thread appears at full length instantly; agent token positioned at destination |
| thread-tension | Static 40%-opacity thread with a `⋯` glyph |
| beat-up / selvage-lock | Instant, no compression |
| unravel | Row disappears; a madder strike-through marker remains |
| shed-open | 120ms crossfade |
| Floor / Weave | Continuous simulation replaced by a static positioned layout, updated on state change only, at most 1 update/sec |
| number-roll | Instant value replacement |
| halt-flash | Static border, immediate desaturation |

**Non-negotiable:** no information exists only in motion. Every state animation has a static encoding (§4.2).

---

## 9. Component Library

Primitives compose into everything. Named, versioned, in Storybook, and covered by visual regression.

### 9.1 Primitives

| Component | Notes |
|---|---|
| `Thread` | A line with state, tension, direction, thickness. The atomic visual unit. Used in the spine, weave, graphs, gutter marks, connectors. |
| `AgentToken` | Circular portrait + state ring + optional activity glyph. Sizes: 20 / 28 / 40 / 64px. Always circular (§4.3). |
| `StateRing` | Ring encoding state by colour **and** stroke pattern (solid / dashed / dotted / hatched). |
| `MetricTile` | Label, value in `--ml-t-data-lg`, delta, sparkline. Value is always tabular. |
| `Selvage` | The chain edge visual. Locked stitches, verify status, tamper indicator. |
| `PhasePill` | Two-letter phase code, state colour, gate status dot. |
| `ConfidenceBar` | Stated confidence **and** the agent's historical calibration error, overlaid. Never shows confidence alone. |
| `ProvenanceStamp` | agent · version · skill · model · ledger-seq. Set in Commit Mono. Attachable to anything. |
| `RationaleBlock` | Prose block permanently marked "Agent's own account — not verified." Distinct hatched left border in cochineal. |
| `EvidenceBlock` | Ablation result. Solid verdigris left border. Visually the opposite of `RationaleBlock` — the distinction is a core product value. |
| `CostMeter` | Live token/currency spend against ceiling. Turns weld at 75%, madder at 92%. |
| `LoopBadge` | `L2 · 3/5` — loop id and iteration against bound. Fills as iterations consume budget. |
| `GateChip` | Gate name, criterion status, blocking/passed, approver if approved. |
| `Shuttle` | The animated carrier for `shuttle-pass`. |
| `Timecode` | Monospace relative + absolute time, with a hover for both. |

### 9.2 Composites

`AgentCard` · `AgentInspector` · `WorkPacketCard` · `LedgerRow` · `GateCard` · `DiffPane` · `TracePane` · `PolicyDiff` · `SkillCard` · `CandidateCard` (trainer) · `ProbationScorecard` · `GraphCanvas` · `WeaveCanvas` · `FloorCanvas` · `Omnibar` · `SignalRail` · `EmptyState` · `BreachBanner`

### 9.3 Empty, loading and error states

Every screen specifies all three. Rules:

- **Empty is an invitation, never an apology.** "No stories in the loom. Drop a story file here, or press ⌘K and type *ingest*." Accompanied by the idle warp — nine dotted threads, no cloth. The empty state *is* the metaphor at rest.
- **Loading is `thread-tension` on the relevant threads.** There is no spinner anywhere in this product.
- **Errors state what happened and the next action, in the interface's voice.** "The sidecar stopped responding 12s ago. Loop L2 is checkpointed at row 9 and will resume. Restart core." Never "Something went wrong." Never an apology. Never a bare stack trace — that goes to the Trace tab.

---

## 10. The Screens

Twenty-four screens. Each entry gives purpose, layout, key components, interactions, motion, and the states.

---

### 10.1 Command Center

**Purpose.** The answer to "what is happening right now," readable in four seconds.

```
┌─ CROWN ──────────────────────────────────────────────────────────────┐
├──┬───────────────────────────────────────────────────────┬───────────┤
│  │ ┌─ THE WEAVE ───────────────────────────┐ ┌─ GATES ──┐│           │
│W │ │                                       │ │ ◈ Design ││  INSPECTOR│
│A │ │   the live woven band for this story  │ │   waiting││           │
│R │ │   rows accumulating upward            │ │   6m     ││  selected │
│P │ │   shuttles crossing in real time      │ │ ─────────││  entity   │
│  │ │                                       │ │ ◈ Verify ││  detail   │
│S │ └───────────────────────────────────────┘ │   blocked││           │
│P │ ┌─ PASSES (live) ───────────┐ ┌─ SPEND ─┐ └──────────┘│           │
│I │ │ Kenji   BD  L1 2/3  ▓▓░  │ │  $2.18  │ ┌─ SIGNAL ─┐│           │
│N │ │ Sofia   VF  L2 4/5  ▓▓▓  │ │  ▁▃▅▂▇  │ │ 14:22 …  ││           │
│E │ │ Arun    BD  L1 1/3  ▓░░  │ │ 218k tok│ │ 14:19 …  ││           │
│  │ └───────────────────────────┘ └─────────┘ └──────────┘│           │
├──┴───────────────────────────────────────────────────────┴───────────┤
│ ROSTER                                                                │
└───────────────────────────────────────────────────────────────────────┘
```

**Components.** `WeaveCanvas` (hero, ~46% of the region) · live `PassRow` list with `LoopBadge` and `CostMeter` · `GateCard` stack · `SignalRail` · spend `MetricTile` with sparkline.

**Interactions.** Click any weft row → Inspector opens that ledger entry. Click a gate → `gate-iris` to the Gate Room. Click a pass → follows that agent on the Floor. `Space` pauses all passes. Hover a warp thread → phase summary.

**Motion.** Continuous `shuttle-pass` per active agent; `beat-up` on each commit; `number-roll` on spend; `unravel` on any rejection, which also flashes the Signal rail.

**Empty.** Idle warp, nine dotted threads, drop target. **Error.** `BreachBanner` above the weave, weave freezes and desaturates.

---

### 10.2 The Loom Floor *(Agents Watch — spatial register)*

**Purpose.** Ambient, watchable, human-legible presence. This is the screen you leave open on a second monitor, and the one that makes an agent workforce feel like colleagues rather than log lines. It is the direct descendant of the Munder Difflin reference, re-art-directed.

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
├───────────────────────────────────────────────────────┴───────────┤
```

**The floor is the architecture.** Rooms are SDLC phases, laid out in lifecycle order. An agent's *position is its state* — sitting at a desk in Build means it is building. Walking between rooms means a handoff is in progress. Standing in the Gate Room means it is awaiting human approval. The Ledger is a physical archive room at the edge. The Dojo is a training room. This is not decoration; it is a spatial encoding of the exact same state the Command Center shows numerically.

**Art direction.** Not the sitcom-cubicle look. Top-down orthographic, 24px tile grid, hand-authored sprites in the theme palette so the floor re-tints with the theme. Rooms are separated by **warp-thread walls** — vertical thread bundles rather than drywall. Desks are looms. The visual read is a textile workshop, not an office.

**Speech.** Agents surface one-line status as speech bubbles above their heads, in their own voice, truncated to 48 characters, max 4 on screen at once, prioritised by recency and severity. Full text in the Inspector. Bubbles are how you read the floor at a glance — the reference does this brilliantly and it is worth keeping exactly.

**Interactions.** Click an agent → Inspector + `roster-focus`. Double-click → follow-cam. Click a room → filter to that phase. Drag an agent to a room → propose a reassignment (requires confirmation; agents are not furniture). Scroll → zoom (3 levels: floor / room / desk). At desk zoom you see the agent's actual live terminal output on their monitor.

**Motion.** Continuous, exempt from the three-thing rule. Pathfinding walk cycles on handoff. Idle micro-animations at 0.3Hz. `portrait-hire` when an agent is onboarded — they walk in through the entrance. Retired agents walk out; the desk stays empty and labelled for one session.

**Reduced motion / <800px.** Replaced by **Floor List**: the same rooms as collapsible sections with agent rows. A banner states the substitution and offers to switch back.

---

### 10.3 The Weave *(story progress, full screen)*

**Purpose.** The complete woven history of one story — every pass, every rework, every gate — as one continuous readable object.

Full-region `WeaveCanvas`. Warp = 9 phases across the top. Weft rows accumulate downward, newest at the bottom. Each row is one pass: agent token at its origin, thread crossing the phases it touched, terminating at a `Selvage` stitch carrying the ledger sequence. Rework passes render hatched with their `unravel` scar left visible — **the cloth remembers what was undone.**

**Interactions.** Hover a row → provenance tooltip. Click → Inspector at that ledger entry. Drag-select rows → Inspector shows aggregate cost and duration. `Shift+Scroll` compresses the row height (from 24px comfortable down to 3px, where a 400-row story becomes one readable texture — dense rework shows as visible dark banding).

**This is the screen for a governance meeting.** One image, no explanation needed: where the work went smoothly and where it fought.

---

### 10.4 Agents Watch *(dense register)*

The instrument-grade twin of the Floor. A sortable, filterable table of every agent: portrait, name, id, tier, state, current loop and iteration, queue depth, first-pass yield, calibration error, trust score, autonomy tier, tokens today, spend today, last commit sequence, heartbeat age.

Row actions inline: **Approve · Rework · Train · Pause · Retire · Export**. Multi-select for bulk. Column visibility and order persisted per workspace. Sparklines in the yield and spend columns.

Toggle in the header switches this ⟷ Floor with `shed-open`. Selection is preserved across the switch — select Kenji in the table, flip to Floor, Kenji is highlighted and centred.

---

### 10.5 Agents Dojo

**Purpose.** Where agents are trained, evaluated and promoted. Directly informed by the ML-lab reference: parameter rails, 3D experiment space, run history.

```
┌─ RAIL ─────┬──────── EXPERIMENT SPACE ──────────┬── HISTORY ────────┐
│ CANDIDATE  │                                     │ ▸ c-0091  +4.2%   │
│ policy Δ   │      ╱────╲      ╱────╲             │ ▸ c-0090  −1.1%   │
│ ▓▓▓▓▓░ .78 │     ╱ node ╲────╱ node ╲            │ ▸ c-0089  +0.3%   │
│ ▓▓▓░░░ .41 │    ╲──────╱      ╲─────╱            │ ▸ c-0088  FAILED  │
│ ▓▓▓▓░░ .62 │         ╲   ╱                       │   safety invariant│
│            │        ╱─────╲                      │ ─────────────────│
│ REGRESSION │       ╱ eval  ╲   3D perspective    │ SELECTED c-0091   │
│ ☑ suite A  │       ╲───────╱   candidate graph   │ base   .812       │
│ ☑ suite B  │                                     │ cand   .854       │
│ ☐ replay   │  ┌──────────────────────────────┐   │ Δ      +4.2%      │
│            │  │  yield over evaluation runs  │   │ safety  PASS      │
│ ▶ EVALUATE │  │  ╱‾‾‾╲___╱‾‾‾‾‾‾‾            │   │ ─────────────────│
│ ⟲ RESET    │  └──────────────────────────────┘   │ [PROMOTE] [DROP]  │
└────────────┴─────────────────────────────────────┴───────────────────┘
```

**Left rail.** Candidate policy deltas with weight sliders, regression suite selection, evaluation controls (Evaluate / Stop / Reset). Sliders are `Thread`-styled — dragging tensions the thread.

**Centre.** The candidate's decision graph in **3D perspective** (see §11.3), nodes as cards floating in space, connected by threads, rotatable by drag. Below it, the evaluation curve: candidate vs. incumbent over runs.

**Right.** Run history, newest first, each with delta badge. Failed-on-safety-invariant runs render in madder with the invariant named — **a candidate that improved a metric by weakening a control is displayed as a failure, prominently, never as a near-miss.**

**Promote is gated.** The Promote button is disabled until: evaluation complete, delta above the configured margin, safety invariants passed, and a human types the agent's name to confirm. On promotion: `beat-up`, ledger entry, and the previous version pinned to a rollback shelf that stays visible for the session.

---

### 10.6 Gate Room

**Purpose.** The human decision queue. The most consequential screen in the product.

Single-column, generously spaced — deliberately the *least* dense screen. When a person is deciding whether to accept AI-authored change, the interface gets out of the way.

Each `GateCard` shows: the gate and its criteria with pass/fail per criterion · the artifact (diff, spec, design, test results) inline · `ProvenanceStamp` · `ConfidenceBar` with calibration · `RationaleBlock` (marked unverified) · `EvidenceBlock` if ablation was run · cost and duration · the loop history that produced it, including prior rejections.

Actions: **Approve** · **Rework** (requires a reason — free text plus a taxonomy chip, and the reason becomes training signal, which the UI states) · **Escalate** · **Waive** (only for waivable criteria; requires justification; renders in weld and is permanently marked in the ledger).

**High-blast-radius gates** get a distinct treatment: madder header bar, ablation evidence mandatory and shown expanded by default, and Approve requires the same press-and-hold as Halt All.

`gate-iris` on entry and exit. Approving fires `beat-up` on the weave visible in a corner inset, so the consequence of the decision is seen immediately.

---

### 10.7 Ledger / Selvage Viewer

**Purpose.** The audit record. Not a blockchain visual — a woven, locked edge.

Left: the `Selvage` — a continuous vertical strip of locked stitches, one per entry, coloured by action type, with the verify-through marker and a prominent tamper indicator if verification fails. Right: the entry stream, filterable by story, agent, phase, loop, action type, decision, and date.

Selecting an entry shows the full record: prompt digest and expandable content, retrieved memory refs, tool calls, output, resulting diff, confidence, cost, latency, approver identity, policy and skill versions.

**Verification is always visible.** A persistent header: `Chain verified to 4,417 · signed 14:22 · anchored ✓`. If verification fails, the entire screen gains a `--ml-halt` border, the first divergent sequence is named, and everything below it renders desaturated. **A broken chain must be impossible to overlook.**

Inclusion and consistency proofs are inspectable per entry. Export produces a signed audit bundle.

---

### 10.8 CodeMap Viewer

**Purpose.** The codebase as a navigable knowledge graph. Directly informed by the Obsidian graph reference.

Force-directed graph, WebGL-rendered, over the repository's structure: modules, packages, classes, functions, contracts, tests, and their relationships. Node colour by cluster (module or domain), node size by centrality, edge weight by coupling strength.

**What makes this Meridian's and not a generic graph:**
- **Agent overlay.** Toggle to tint nodes by which agent last touched them and when. Recency renders as thread brightness. You can see the shape of the agent workforce's footprint on your architecture.
- **Blast-radius projection.** Select a work packet; the graph highlights the projected impact set and dims everything else, with a count.
- **Semantic zoom.** Three levels — system (packages) / module (classes) / detail (functions and their call edges). Level changes crossfade rather than pop.
- **Rework heat.** Toggle to colour nodes by rework density from the ledger. The parts of the codebase the agents keep getting wrong become immediately visible — this is the single most actionable view in the product for a tech lead.

Controls: search with fuzzy match and camera fly-to, cluster isolation, orphan filter, path highlight between two selected nodes, freeze layout, export PNG/SVG.

---

### 10.9 Loop Graph Viewer *(graph of loops)*

**Purpose.** The live execution topology — the six canonical loops, nested, with budgets.

Rendered in **3D perspective** like the reference's pipeline view. Each loop is a ring in depth: L1 nearest, L6 furthest. Nodes are agent invocations, edges are transitions. The active path is drawn in woad and animates; completed paths are verdigris; rework edges arc back visibly with `unravel` styling.

Each loop ring carries a `LoopBadge` showing iteration against bound, and a budget arc that fills. When a loop approaches its bound the ring tints weld; on breach, madder and the escalation edge illuminates.

Drag to orbit, scroll to dolly, click a node to inspect, `F` to frame the active path. A 2D fallback (top-down DAG) is available and is used automatically under reduced motion.

---

### 10.10 Architecture & C4 Viewer

Four levels with animated zoom between them (the C4 model's own semantics made literal):

| Level | Content |
|---|---|
| **1 · System Context** | The system, its users, and external systems |
| **2 · Container** | Applications, services, data stores, and the technology of each |
| **3 · Component** | Components inside a selected container |
| **4 · Code** | Drops into the CodeMap viewer (§10.8) at that component |

Diagrams are **generated from the repository and the Architect Agent's ADRs, not hand-drawn**, and regenerate on change. A drift indicator shows where the documented architecture and the actual code have diverged, with the divergence listed — this is the feature architects will actually use.

Level transitions use a zoom-through, not a screen swap: the selected box expands to fill and its contents resolve. ADRs attach to elements as annotations; clicking one opens it in the Inspector with its ledger provenance.

---

### 10.11 UML Studio

One screen, seven diagram types, unified chrome. All generated from code and agent artifacts, all live.

| Diagram | Source | Notable |
|---|---|---|
| **Class** | Static analysis | Filter by package; show only what changed in this story |
| **Sequence** | Runtime traces + agent call graphs | **Agent sequence mode:** the lifelines are agents, not objects, and the messages are the actual handoffs of a story |
| **State machine** | Detected state enums + the loop runtime | Shows both application states and loop states |
| **Activity** | Work packet graph | Swimlanes by agent |
| **Component** | Module boundaries | Overlaid with coupling strength from CodeMap |
| **Deployment** | IaC parsing | Environment selector |
| **ER** | Schema + migrations | Migration diffs highlighted; agent-authored migrations flagged |

Shared: layout engine selector, orthogonal/curved routing, focus+context (dim unrelated), diff mode (this story's changes against baseline, additions in verdigris, removals in madder), export to SVG/PNG/PlantUML/Mermaid.

**Agent sequence mode is the differentiator.** Nobody else can draw a sequence diagram whose lifelines are the AI agents that built the feature, with real timings and real message payloads pulled from the ledger.

---

### 10.12 Flow Diagram Viewer

Business and process flows: the story's acceptance criteria rendered as a flow, the actual implemented control flow extracted from code, and **the two overlaid to show gaps**. Uncovered branches render hatched in madder. This turns "did the agents actually implement the acceptance criteria" from a review question into a picture.

Also hosts: data-flow diagrams, the DevSecOps pipeline flow, and the escalation flow.

---

### 10.13 Config Portal

**Purpose.** Everything configurable, organised by intent rather than by which module owns it.

Left nav, right detail pane, live preview where meaningful.

| Section | Contents |
|---|---|
| **Identity & Access** | Model providers, credentials (SecretStorage-backed, never displayed), agent identities |
| **The Workforce** | Roster management, per-agent budgets, autonomy tiers and thresholds, probation criteria |
| **Capability Packs** | Installed skills, versions, digests, install/review/remove — links to Skill Forge |
| **Loops & Budgets** | Per-loop bounds, per-story ceilings, model tiering policy, escalation targets |
| **Gates & Policy** | Definition of Ready / Done criteria, gate requirements, waiver policy, blast-radius rules |
| **Security** | Egress allow-list, sandbox settings, untrusted-content handling, secret-redaction patterns |
| **The Ledger** | Retention, signing key, anchoring configuration, verification schedule |
| **Appearance** | Theme, motion, density (comfortable/compact/dense), Floor art level, sound |
| **Integrations** | MCP servers with trust status, issue tracker, SCM, CI |
| **Diagnostics** | Sidecar status, interpreter path, logs, chain verification, reset |

**Every setting that changes agent behaviour shows its blast radius before saving** — "This lowers the Verify gate threshold. 3 agents currently at approve-per-phase would be affected." Policy changes are diffed against current and written to the ledger on save. Nothing that governs agents changes silently.

---

### 10.14 Skill Forge

Browse, inspect, install, author and version capability packs.

Grid of `SkillCard`s: name, version, digest, target stack, declared tools, install source, trust status, usage count and the first-pass yield of agents while bound to it — **so you can see which capability packs actually make agents better.**

**Install flow is a security surface and is designed as one.** Selecting install opens a full review: every file, every script with its content, every external URL referenced, every tool the pack requests. Nothing installs without explicit confirmation, and the confirmation names the risk in plain language: "This pack can run scripts on your machine and requests network access to two hosts."

Authoring mode: a `SKILL.md` editor with live frontmatter validation, token-cost estimation for the discovery stage against the 3,000-token catalogue budget, and a test harness that binds the draft pack to a scratch agent on a sample task.

---

### 10.15 Onboarding Wizard *(hire an agent)*

The five-step flow that adds a new agent role without touching extension source. Modelled on the reference's character-creation modal, made consequential.

1. **Role** — name, tier, phase, responsibilities in plain language
2. **Portrait** — a grid of sprite portraits and a colour swatch row. Not cosmetic: the portrait and colour are how this agent is identified everywhere in the product for the rest of its life.
3. **Capability** — permitted skills, permitted tools, budgets
4. **Governance** — gates it owns, escalation target, probation task set
5. **Probation** — runs immediately, live, with a `ProbationScorecard` filling as tasks complete

Admission is a decision, not a formality: the scorecard shows every probation task with pass/fail and the score against threshold, and a failing agent cannot be admitted. Admitted agents enter at `suggest` tier regardless of score, and the wizard says so.

On admission: `portrait-hire` — the portrait stitches in, the agent walks onto the Floor through the entrance, and the roster makes room.

---

### 10.16 Agent Inspector *(persistent right panel, detailed here)*

Six tabs, context-sensitive to the selected entity.

| Tab | Content |
|---|---|
| **Trace** | The decision record: inputs, retrieved memory with refs, tool calls, output, `ConfidenceBar`, `RationaleBlock` (marked unverified), `EvidenceBlock` if ablation ran, and a **Run ablation** control |
| **Terminal** | Live stdout/stderr from that agent's sandbox, ANSI-rendered, searchable, with a copy-as-issue action |
| **Diff** | The change this agent produced, syntax-highlighted, with the originating prompt pinned above and open-in-editor per hunk |
| **Memory** | What this agent knows: procedural playbook entries, semantic facts, recent episodic summaries. Untrusted-tagged entries visibly marked. Entries are individually removable, with confirmation. |
| **Policy** | Current prompt/policy, version history, diff between versions, training lineage — which ledger evidence produced which change |
| **Messages** | Handoffs to and from other agents, threaded, with the ability to inject a human message into the conversation |

---

### 10.17 Diff Theater

Full-screen review of an agent-authored change. Side-by-side or unified, per-hunk accept/reject, with three columns of context the reference tools don't have: the **prompt** that produced each hunk, the **test** that covers it, and the **ledger sequence** that recorded it. Rejecting a hunk requires a reason and re-enters the loop.

---

### 10.18 Spec Studio

The clarified specification and the ambiguity register. Each ambiguity: the underspecified point, the agent's proposed resolution, its confidence, and **Accept / Amend / Escalate**. Acceptance criteria are shown with their coverage status once tests exist, so this screen becomes a live traceability matrix rather than a one-time artifact.

---

### 10.19 Work Packet Board

Kanban by phase, cards are `WorkPacketCard`s showing target paths, stack, required skill, acceptance tests, dependencies, blast radius, budget and assigned agent. Dependency arrows between cards. Overlap detection is visual — two packets targeting the same file render with a linked madder edge and cannot both be marked parallelisable.

---

### 10.20 Verification Board

Test suites, runs, coverage delta, acceptance-criteria traceability, flake detection. The headline element is a criterion-to-test matrix: any acceptance criterion without a covering test renders as an open madder cell, and the gate cannot pass while one exists.

---

### 10.21 Security Assurance

SAST, SCA, secrets and SBOM delta for the change. Findings grouped by severity with the introducing ledger sequence. A dedicated panel for **agent-specific threats**: blocked egress attempts, denied tool invocations, out-of-scope modification attempts, and injected-instruction detections — each with the full context of what was attempted and by which agent.

---

### 10.22 KPI Observatory

The measurement screen, using the meridian/navigation half of the name: arcs, ascent lines and reference meridians rather than stock bar charts.

Headline pairing, always together and never separable: **throughput and stability on one axis pair.** When throughput rises while change failure rate rises with it, the chart draws a madder divergence band and states the finding in words. That is the documented AI-adoption failure pattern and the product is built to catch it in itself.

Also: first-pass yield by agent and phase, human intervention rate, rework taxonomy, cost per merged PR, tokens per story as a distribution (never a mean), time to merge, review turnaround, escaped defect density, calibration error by agent, autonomy tier distribution over time.

Every metric links through to the ledger slice it was computed from. **No number in this product is unauditable.**

---

### 10.23 Exchange *(export / import)*

Package a tuned agent for another team, or adopt one. Export shows exactly what travels and what is stripped — credentials, episodic memory and untrusted-tagged content are excluded, and the pre-export scan result is displayed before the package is written. Import shows a full diff of what will be introduced, verifies the signature, and starts probation. The screen states plainly that an imported agent is not trusted on arrival.

---

### 10.24 Focus Mode

A chromeless, ambient full-screen view — the Floor or the Weave, no panels, no controls, slowed motion, `Loom Ghost` theme. For the second monitor, and for the wall screen in a delivery area. Gates and breaches break through as full-bleed overlays; nothing else does.

---

## 11. Renderer Specifications

### 11.1 WeaveCanvas

Canvas 2D with an offscreen buffer for committed rows (they never change, so they are drawn once and blitted). Only the live rows and shuttles redraw per frame. Target 60fps with 400+ rows; degrade row height before degrading frame rate. DPR-aware. Rows virtualise above 2,000.

### 11.2 FloorCanvas

Canvas 2D, orthographic, 24px tile grid, sprite atlas with palette swapping so sprites re-tint per theme without new assets. A* pathfinding on the tile grid for agent movement. Frame budget 8ms; when exceeded, drop idle micro-animations first, then walk-cycle frame rate, then fall back to static positions with a visible notice. Pauses entirely when the panel is hidden.

### 11.3 GraphCanvas

WebGL (regl or PixiJS) for CodeMap at scale; SVG for graphs under 300 nodes where crispness and DOM accessibility matter more than throughput. Force simulation in a Web Worker so layout never blocks the UI thread. Level-of-detail: labels appear below 150 visible nodes, edges thin below 2,000, and above 5,000 nodes the renderer switches to aggregated cluster hulls with a notice.

The 3D perspective used in the Dojo and Loop Graph is a **projected 2.5D**, not a full 3D scene — nodes are billboarded cards on a perspective grid. This keeps text crisp and legible, which a true 3D scene would not.

### 11.4 SelvageStrip

SVG. One stitch per entry, virtualised. The verification state is computed in the sidecar, never in the webview — the UI displays a verdict it did not compute, which is the correct trust boundary.

---

## 12. Iconography & Sprite Art

**Icons.** A bespoke 20px set on a 20-unit grid, 1.5px stroke, square cap, built from thread and loom vocabulary — a shuttle, a shed, a warp bundle, a selvage stitch, a heddle. Deliberately not a generic icon library. Where a concept has no loom analogue, VS Code Codicons are used so the extension feels native; the two sets are visually reconciled by matching stroke weight and grid.

**Sprites.** 32×32 agent portraits and 32×48 floor sprites, 4-direction walk cycles at 4 frames, indexed colour so the palette swaps with the theme. A minimum of 24 distinct portraits so a large workforce has visual variety. Portraits are assigned at onboarding and are permanent — an agent's face is part of its identity in the ledger and in every screen.

**Illustration.** Reserved for empty states only: line drawings of an unstrung loom, an empty shuttle, an unfinished band. Never generic "AI" imagery.

---

## 13. Sound

Off by default. When enabled, four sounds only, all under 120ms, all derived from loom mechanics: the shuttle pass (a soft wooden click), the beat-up (a low thud), the gate opening (a rising two-tone), and the breach (a single sharp strike). Nothing loops. Nothing plays for routine success. Volume follows the OS; sound never conveys information that is not also visual.

---

## 14. Accessibility

Target: **WCAG 2.1 AA**, verified, not assumed.

- Contrast ≥4.5:1 for text and ≥3:1 for UI components and graphical objects, in all six themes. Verified in CI against the token sets.
- Every state has a non-colour encoding (§4.2). This is checked at review.
- Full keyboard operation. Documented shortcuts for every action. Roving tabindex in the roster, weave and graphs. `Escape` always closes the topmost layer. No keyboard trap in any canvas — canvases expose a focusable list equivalent.
- Canvas content has a parallel accessible representation: the Floor exposes an ARIA tree of rooms and agents; the Weave exposes a table of passes; graphs expose a list of nodes and edges with relationships.
- Live regions: gates and breaches announce via `aria-live="assertive"`; routine passes via `polite`, rate-limited to one announcement per 3 seconds to avoid flooding a screen reader.
- Focus is always visible: 2px woad ring with 2px offset, never removed, never relying on colour alone (it also thickens).
- `prefers-reduced-motion` and an independent in-app motion setting (§8.4).
- Text scales to 200% without loss of function; the shell reflows rather than clipping.
- Minimum hit target 28×28px, 32×32px for anything destructive.

---

## 15. Performance Budgets

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

All budgets enforced in CI. A regression over budget fails the build.

---

## 16. Technical Constraints

Binding, from `Requirements.md` §M2:

- **CSP with nonce on every webview.** `default-src 'none'; script-src 'nonce-…'; style-src ${cspSource}; img-src ${cspSource} data:; font-src ${cspSource}`. No inline handlers, no `eval`, no CDN.
- **No `localStorage`, `sessionStorage`, or any browser storage.** All persistence via `getState()`/`setState()` and the extension host. This is absolute — the webview may be destroyed at any time.
- **All resources via `asWebviewUri`** with `localResourceRoots` declared.
- **State survives hide/reload** through `WebviewPanelSerializer` and message replay. `retainContextWhenHidden` is not used for correctness and is unavailable in the sidebar view.
- **Single typed message bus**, discriminated union, schema-versioned, with the version checked on handshake.
- **All agent-produced text is escaped.** Markdown is sanitised, HTML stripped, scripts and event handlers removed. Agent output is untrusted content and is rendered as such.
- **Theme from `--vscode-*` variables** when following VS Code; correct in light, dark and high contrast.
- **Degrades gracefully when the sidecar is down** — last-known state, visibly marked stale, never an empty or erroring view.

---

## 17. Banned Patterns

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

---

## 18. Open Design Decisions

| # | Decision | Bearing |
|---|---|---|
| V1 | Sprite art commissioned vs. generated vs. licensed — 24+ portraits and 4-direction walk cycles is real production work | Floor ships or slips |
| V2 | Whether the Floor is default-on for new users or opt-in after first story | First impression: delightful vs. serious |
| V3 | Archivo + Commit Mono licensing and subsetting for redistribution in a `.vsix` | Bundle size and legal |
| V4 | Whether the Weave replaces the Command Center hero, or stays a separate screen | Information density of the primary view |
| V5 | 2.5D vs. flat 2D for Dojo and Loop Graph — 2.5D is more compelling, flat is more legible and cheaper | Build cost and clarity |
| V6 | Whether Focus Mode should be a separate webview panel or a chrome-hiding state | Multi-monitor ergonomics |
| V7 | Density default: comfortable or compact, given the split audience | Which audience the product greets |

---

*Build order, phase by phase, is in `viguix-implementation.md`.*
