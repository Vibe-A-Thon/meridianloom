import { ActionClassChip, type ActionClass } from './ActionClassChip';
import { toSafeText } from '../security/sanitize';
import styles from './trace-step.module.css';

/**
 * One step of an agent trace (E-IN-07). Banned pattern 25 / B14: every
 * trace step renders with an ActionClassChip — the chip is not optional,
 * and the component test fails if a step type ever renders without one.
 * The description is agent-produced text: sanitised, rendered as text.
 */
export interface TraceStepData {
  description: string;
  actionClass: ActionClass;
  whyLlm?: string;
}

export interface TraceStepProps {
  index: number;
  step: TraceStepData;
}

export function TraceStep({ index, step }: TraceStepProps) {
  return (
    <li className={styles.step} data-testid="trace-step">
      <span className={styles.index}>{index + 1}</span>
      <span className={styles.description}>{toSafeText(step.description)}</span>
      <span className={styles.action}>
        <ActionClassChip actionClass={step.actionClass} whyLlm={step.whyLlm} />
      </span>
    </li>
  );
}

export function TraceSteps({ steps }: { steps: TraceStepData[] }) {
  return (
    <ol style={{ margin: 0, padding: 0, listStyle: 'none' }}>
      {steps.map((step, i) => (
        <TraceStep key={i} index={i} step={step} />
      ))}
    </ol>
  );
}
