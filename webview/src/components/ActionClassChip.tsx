import { toSafeText } from '../security/sanitize';
import styles from './action-class-chip.module.css';

/**
 * ActionClassChip (v2.1 §9.1): deterministic / assisted / generative for
 * any agent action — a shape+colour pair, never colour alone (banned
 * pattern 16), carrying the why_llm reason on hover and focus (H5). Banned
 * pattern 25 / E-IN-07: an agent result never renders without its action
 * class; TraceStep enforces that at the row level.
 */
export type ActionClass = 'deterministic' | 'assisted' | 'generative';

export const ACTION_CLASS_LABELS: Record<ActionClass, string> = {
  deterministic: 'deterministic',
  assisted: 'assisted',
  generative: 'generative',
};

export interface ActionClassChipProps {
  actionClass: ActionClass;
  /** FR-M8-16: why a model was involved. Required for generative, optional
   *  otherwise — shown on hover/focus and in the accessible name. */
  whyLlm?: string;
}

function normalize(value: unknown): ActionClass {
  return value === 'assisted' || value === 'generative' ? value : 'deterministic';
}

function shapeClass(actionClass: ActionClass): string {
  switch (actionClass) {
    case 'deterministic':
      return styles.shapeDeterministic;
    case 'assisted':
      return styles.shapeAssisted;
    default:
      return styles.shapeGenerative;
  }
}

export function ActionClassChip({ actionClass, whyLlm }: ActionClassChipProps) {
  const kind = normalize(actionClass);
  const why = toSafeText(whyLlm);
  const accessibleName = why
    ? `${ACTION_CLASS_LABELS[kind]} — ${why}`
    : ACTION_CLASS_LABELS[kind];
  return (
    <span className={styles.chip} data-testid="action-class-chip" aria-label={accessibleName}>
      <span className={`${styles.shape} ${shapeClass(kind)}`} data-shape={kind} aria-hidden="true" />
      {ACTION_CLASS_LABELS[kind]}
      {why ? (
        <span className={styles.why} data-testid="action-class-why">
          {why}
        </span>
      ) : null}
    </span>
  );
}
