import { useId, useState, type ReactNode } from 'react';
import type { ObservationConfidence } from '../../../shared/ts/bus-types';
import { toSafeText } from '../security/sanitize';
import { VendorTag } from './VendorTag';
import styles from './provenance-hover.module.css';

/**
 * X-30: one provenance card, one behaviour, every surface. Hovering OR
 * focusing any agent-attributed artifact shows the same stamp: VendorTag +
 * observation confidence + who approved. Hover-only is a banned pattern
 * (§18.22), so every wrapped row is focusable and the card opens on focus
 * as well; touch users get it from the first tap via focus.
 */

export interface ProvenanceCardData {
  /** Vendor id from the bus (FR-M35-03). */
  vendor: string;
  /** FR-M35-02 observation confidence. */
  confidence: ObservationConfidence | string;
  /** One line naming the artifact, e.g. "pass · seq 4402 · 14:05". */
  subject: string;
  /** null = "not yet gated"; undefined = approval does not apply here. */
  approvedBy?: string | null;
  /** Optional extra line, e.g. "observed via git-trailers". */
  note?: string;
}

export function ProvenanceHover({
  card,
  children,
}: {
  card: ProvenanceCardData;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const id = useId();
  return (
    <div
      className={styles.wrap}
      tabIndex={0}
      data-testid="provenance-target"
      aria-describedby={open ? id : undefined}
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      onFocus={() => setOpen(true)}
      onBlur={() => setOpen(false)}
    >
      {children}
      {open && (
        <div className={styles.card} role="tooltip" id={id} data-testid="provenance-card">
          <VendorTag vendor={card.vendor} confidence={card.confidence} />
          <p className={styles.subject}>{toSafeText(card.subject)}</p>
          {card.approvedBy !== undefined && (
            <p className={styles.line} data-testid="provenance-approval">
              {card.approvedBy
                ? `approved by ${toSafeText(card.approvedBy)}`
                : 'not yet gated — no recorded approval'}
            </p>
          )}
          {card.note ? <p className={styles.line}>{toSafeText(card.note)}</p> : null}
        </div>
      )}
    </div>
  );
}
