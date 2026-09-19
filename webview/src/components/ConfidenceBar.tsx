import { toSafeFraction } from '../security/sanitize';
import styles from './confidence-bar.module.css';

/**
 * §9.1 ConfidenceBar: stated confidence AND the agent's historical
 * calibration error, overlaid. Banned pattern 18 — never confidence alone.
 *
 * Invariant (component-tested): whenever this component renders, the
 * calibration caption renders too. When the agent has no calibration
 * history the caption says so explicitly; the claim is never shown bare.
 */
export interface ConfidenceBarProps {
  /** Stated confidence, 0..1. */
  confidence: number;
  /** Mean absolute calibration error over history, 0..1; null/absent when
   *  there is no history yet. */
  calibrationError?: number | null;
  /** History size behind calibrationError; shown for honesty about thin data. */
  calibrationSamples?: number;
}

export function ConfidenceBar({
  confidence,
  calibrationError,
  calibrationSamples,
}: ConfidenceBarProps) {
  const stated = toSafeFraction(confidence);
  const hasCalibration = typeof calibrationError === 'number' && Number.isFinite(calibrationError);
  const error = hasCalibration ? toSafeFraction(calibrationError as number) : 0;
  // The hatched band spans the claim ± its historical error, clamped.
  const bandLeft = Math.max(0, stated - error);
  const bandWidth = hasCalibration
    ? Math.min(1, stated + error) - bandLeft
    : 0;

  return (
    <div className={styles.wrap} data-testid="confidence-bar">
      <div
        className={styles.track}
        role="meter"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(stated * 100)}
        aria-label="Stated confidence with historical calibration error"
      >
        <div className={styles.stated} style={{ width: `${stated * 100}%` }} />
        {hasCalibration && (
          <div
            className={styles.calibration}
            data-testid="calibration-band"
            style={{ left: `${bandLeft * 100}%`, width: `${bandWidth * 100}%` }}
          />
        )}
      </div>
      <div className={styles.caption}>
        <span data-testid="confidence-stated">{`stated ${Math.round(stated * 100)}%`}</span>
        {hasCalibration ? (
          <span data-testid="confidence-calibration">
            {`calibration error ±${Math.round(error * 100)}%`}
            {typeof calibrationSamples === 'number' ? ` over ${calibrationSamples}` : ''}
          </span>
        ) : (
          <span className={styles.noCalibration} data-testid="confidence-no-calibration">
            no calibration history yet
          </span>
        )}
      </div>
    </div>
  );
}
