import { toSafeText } from '../security/sanitize';
import styles from './rationale-block.module.css';

/**
 * §9.1 RationaleBlock: an agent's own account of why it did something.
 * Banned pattern 19 / B12 — agent rationale is never rendered without its
 * permanent "not verified" marking. The text is untrusted (X-08) and goes
 * through toSafeText before it reaches the DOM.
 */
export interface RationaleBlockProps {
  /** The agent's prose — rendered as escaped text, never as HTML. */
  text: string;
}

export const NOT_VERIFIED_MARKING = "Agent's own account — not verified.";

export function RationaleBlock({ text }: RationaleBlockProps) {
  const safe = toSafeText(text);
  return (
    <figure className={styles.block} data-testid="rationale-block">
      <figcaption className={styles.marking} data-testid="rationale-marking">
        {NOT_VERIFIED_MARKING}
      </figcaption>
      <blockquote className={styles.body}>{safe || '—'}</blockquote>
    </figure>
  );
}
