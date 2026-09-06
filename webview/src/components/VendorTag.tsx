import type { ObservationConfidence } from '../../../shared/ts/bus-types';
import {
  CONFIDENCE_META,
  normalizeConfidence,
  vendorGlyphPath,
  vendorLabel,
} from './vendors';
import styles from './vendor-tag.module.css';

/**
 * X-27 / DS-1: the VendorTag is a primitive on par with StateRing — vendor
 * name, bespoke geometric glyph (never a logo), and the observation-
 * confidence mark, composed in and never hidden. Every agent-attributed
 * artifact renders one of these; the component tests fail if any of the
 * three parts goes missing.
 */
export interface VendorTagProps {
  /** Vendor id from the bus (FR-M35-03); unknown ids render honestly as
   *  "Unknown vendor" rather than being dropped. */
  vendor: string;
  confidence: ObservationConfidence | string;
}

function confidenceClass(confidence: ObservationConfidence): string {
  switch (confidence) {
    case 'direct':
      return styles.confidenceDirect;
    case 'telemetry':
      return styles.confidenceTelemetry;
    default:
      return styles.confidenceInferred;
  }
}

/** ● direct — full disc. */
const DIRECT_DISC = 'M12 12m-8 0a8 8 0 1 0 16 0a8 8 0 1 0-16 0';
/** ◐ telemetry — left half. */
const TELEMETRY_HALF = 'M12 4a8 8 0 0 1 0 16z';
/** ○ inferred — ring. */
const INFERRED_RING = 'M12 4a8 8 0 1 0 8 8';

function confidencePath(confidence: ObservationConfidence): string {
  switch (confidence) {
    case 'direct':
      return DIRECT_DISC;
    case 'telemetry':
      return TELEMETRY_HALF;
    default:
      return INFERRED_RING;
  }
}

export function VendorTag({ vendor, confidence }: VendorTagProps) {
  const level = normalizeConfidence(confidence);
  const meta = CONFIDENCE_META[level];
  const accessibleName = `${vendorLabel(vendor)}, ${meta.meaning}`;
  return (
    <span className={styles.tag} data-testid="vendor-tag" aria-label={accessibleName}>
      <span className={styles.glyph} data-glyph aria-hidden="true">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d={vendorGlyphPath(vendor)} strokeLinejoin="round" />
        </svg>
      </span>
      <span className={styles.name}>{vendorLabel(vendor)}</span>
      <span
        className={`${styles.confidence} ${confidenceClass(level)}`}
        data-confidence={level}
        aria-hidden="true"
      >
        <svg viewBox="0 0 24 24" fill="currentColor" stroke="none">
          <path d={confidencePath(level)} />
        </svg>
      </span>
      <span className={styles.meaning}>{meta.shortLabel}</span>
    </span>
  );
}
