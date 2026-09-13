/**
 * X-27 vendor and confidence primitives.
 *
 * The vendor glyph set (V10) is a long-lead design item — bespoke marks,
 * 12px-legible, distinct under all three colour-vision deficiencies,
 * trademark-cleared, never a vendor logo (banned pattern 29 of
 * gaps_guix.md). Until that design pass lands, GF0 ships geometric marks:
 * every vendor gets a distinct *shape*, so identification never depends on
 * hue (A-02) and the swap to final art is a data change, not a component
 * change. TODO(gf0/v10): replace GLYPHS with the commissioned set.
 */

import type { ObservationConfidence } from '../../../shared/ts/bus-types';

export const VENDOR_IDS = [
  'meridian',
  'claude-code',
  'copilot',
  'cursor',
  'codex',
  'devin',
  'gemini',
  // M52 (MV3-T06): other provenance tools whose records Meridian reads and
  // notarises. They are vendors here in exactly the sense the ledger means —
  // the party an observation is attributed to — and leaving them out made
  // every foreign record render as "Unknown vendor", which loses the
  // attribution FR-M52-02 exists to preserve.
  'aider',
  'continue',
  'gitbutler',
  'codeium',
  'sourcegraph',
  'git-notes',
  'unknown-tool',
  'unknown',
] as const;
export type VendorId = (typeof VENDOR_IDS)[number];

export function isVendorId(value: unknown): value is VendorId {
  return typeof value === 'string' && (VENDOR_IDS as readonly string[]).includes(value);
}

/** Display name per vendor id — sentence case (§6.2), never a logo file. */
export const VENDOR_LABELS: Record<VendorId, string> = {
  meridian: 'Meridian',
  'claude-code': 'Claude Code',
  copilot: 'Copilot',
  cursor: 'Cursor',
  codex: 'Codex',
  devin: 'Devin',
  gemini: 'Gemini',
  aider: 'Aider',
  continue: 'Continue',
  gitbutler: 'GitButler',
  codeium: 'Codeium',
  sourcegraph: 'Sourcegraph',
  'git-notes': 'Git notes',
  // Distinct from `unknown`: Meridian knows a tool wrote this and does not
  // recognise which. Collapsing the two would lose the fact that the record
  // has an author at all.
  'unknown-tool': 'Unrecognised tool',
  unknown: 'Unknown vendor',
};

/**
 * Geometric marks, 24×24 viewBox, stroke-based so they render in the
 * surrounding text colour. Each is a genuinely different topology.
 */
const GLYPHS: Record<VendorId, string> = {
  /* warp threads with one pass through them — the loom */
  meridian: 'M6 3v18M12 3v18M18 3v18M3 12h18',
  /* nested open chevrons */
  'claude-code': 'M7 5l7 7-7 7M13 5l7 7-7 7',
  /* twin overlapping diamonds */
  copilot: 'M12 3l6 9-6 9-6-9zM6 6l6 6M18 6l-6 6',
  /* pointer caret, rising */
  cursor: 'M5 3l14 8-6 2-2 6z',
  /* codex: two-page spread */
  codex: 'M12 5c-2-1.5-4.5-2-8-2v16c3.5 0 6 .5 8 2 2-1.5 4.5-2 8-2V3c-3.5 0-6 .5-8 2zM12 5v16',
  /* orbit: circle with offset body */
  devin: 'M12 12m-8 0a8 8 0 1 0 16 0a8 8 0 1 0-16 0M17 7m-2.5 0a2.5 2.5 0 1 0 5 0a2.5 2.5 0 1 0-5 0',
  /* twin parallel bars */
  gemini: 'M8 4v16M16 4v16',
  /* a nested arrow pair — editing in place */
  aider: 'M5 12h14M12 5l7 7-7 7M8 5L1 12l7 7',
  /* an unbroken onward line with a step */
  continue: 'M3 16h6l3-8h9',
  /* stacked branch lozenges */
  gitbutler: 'M6 4v16M6 8h8a4 4 0 0 1 0 8H6',
  /* a rising stack of three bars */
  codeium: 'M5 19V13M12 19V8M19 19V4',
  /* a search ring crossed by a bar */
  sourcegraph: 'M10 10m-6 0a6 6 0 1 0 12 0a6 6 0 1 0-12 0M14 14l6 6',
  /* a page corner with a fold — the note */
  'git-notes': 'M6 3h9l4 4v14H6zM15 3v4h4',
  /* a solid ring with a question of a gap — authored, by whom we cannot say */
  'unknown-tool': 'M12 4a8 8 0 1 1-6 13M12 8v4',
  /* dashed ring — nothing claimed */
  unknown: 'M12 4a8 8 0 1 0 8 8',
};

export function vendorGlyphPath(vendor: string): string {
  return GLYPHS[isVendorId(vendor) ? vendor : 'unknown'] ?? GLYPHS.unknown;
}

export function vendorLabel(vendor: string): string {
  return VENDOR_LABELS[isVendorId(vendor) ? vendor : 'unknown'];
}

/**
 * FR-M35-02 confidence levels with their A-09 meanings. The meaning is the
 * accessible name — a screen reader never hears a bare symbol name; it hears
 * "observed directly", "from telemetry" or "inferred from file changes".
 */
export const CONFIDENCE_META: Record<
  ObservationConfidence,
  { shortLabel: string; meaning: string }
> = {
  direct: { shortLabel: 'direct', meaning: 'observed directly' },
  telemetry: { shortLabel: 'telemetry', meaning: 'from telemetry' },
  inferred: { shortLabel: 'inferred', meaning: 'inferred from file changes' },
};

export function normalizeConfidence(value: unknown): ObservationConfidence {
  return value === 'direct' || value === 'telemetry' ? value : 'inferred';
}
