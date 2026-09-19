import styles from './enforcement-badge.module.css';

/**
 * FR-M42-11/12, SEC-32: a control's honest enforcement point.
 *
 * Every control surface composes this. The invariant is component-level,
 * not review-level (`H2`, `B12`): a control rendered without a declaration
 * throws in development and renders a visible defect marker in production,
 * exactly as `ConfidenceBar` refuses to render a claim without calibration.
 *
 * The reason it is a component and not a prose notice: two screens used to
 * carry hand-written sentences about their own boundaries. Prose does not
 * compose, cannot be enforced by a type, and drifts from the code silently
 * — which is how a client-side control ends up described as "enforced".
 *
 * **The word "enforced" never appears unqualified.** `SEC-32` forbids
 * presenting a control as enforced at a boundary where it is not, and an
 * unqualified badge is exactly that presentation.
 */

/** The closed FR-M42-11 vocabulary. Mirrors `VOCABULARY` in the sidecar. */
export type EnforcementPoint =
  | 'editor'
  | 'extension_host'
  | 'sidecar'
  | 'scm'
  | 'ci'
  | 'advisory_only';

export interface ControlDeclaration {
  control: string;
  enforcementPoint: EnforcementPoint;
  /** false = advisory: it observes, records and warns. It does not intercept. */
  enforced: boolean;
  vocabularyVersion: string;
  /** What could bypass this control, and who could do so. */
  boundaryNote: string;
}

/**
 * How each point is named to a human. Every label states the boundary, so
 * the reader learns *where* it binds rather than *whether* we say it does.
 */
const POINT_LABEL: Record<EnforcementPoint, string> = {
  editor: 'Enforced in the editor',
  extension_host: 'Enforced in the extension host',
  sidecar: 'Enforced in Meridian',
  scm: 'Enforced at the SCM',
  ci: 'Enforced in CI',
  advisory_only: 'Advisory only',
};

/**
 * The one-line consequence, in the words that matter to someone deciding
 * whether to rely on it. A boundary a developer can step around is said to
 * be one, here, not in a footnote.
 */
const POINT_MEANING: Record<EnforcementPoint, string> = {
  editor: 'someone not using Meridian is not stopped by it',
  extension_host: 'someone not using Meridian is not stopped by it',
  sidecar: 'it binds in Meridian; the SCM does not enforce it',
  scm: 'it binds at the SCM, so it holds without Meridian installed',
  ci: 'it binds in CI, so it holds without Meridian installed',
  advisory_only: 'it observes, records and warns; it does not intercept',
};

export interface EnforcementBadgeProps {
  /**
   * The control's declaration, from `governance/enforcementPoints`.
   * Required. A control whose boundary is unknown is advisory until proven
   * otherwise (`J4`), and rendering it silently would be the overclaim this
   * component exists to prevent.
   */
  declaration: ControlDeclaration | null | undefined;
  /** Show the full boundary note rather than the one-line consequence. */
  verbose?: boolean;
}

export function EnforcementBadge({ declaration, verbose }: EnforcementBadgeProps) {
  if (!declaration) {
    // Loud in development, visible in production. A missing declaration is
    // a defect in the calling surface, and a badge that quietly renders
    // nothing would let that surface ship looking complete.
    if (import.meta.env?.DEV) {
      throw new Error(
        'EnforcementBadge: no declaration. Every control declares its enforcement ' +
          'point (FR-M42-11). Fetch it from governance/enforcementPoints, or do not ' +
          'render the control.',
      );
    }
    return (
      <span
        className={`${styles.badge} ${styles.undeclared}`}
        data-testid="enforcement-badge"
        data-enforcement-point="undeclared"
        role="status"
      >
        Enforcement point not declared — treat as advisory
      </span>
    );
  }

  const { enforcementPoint, enforced, boundaryNote } = declaration;
  const label = POINT_LABEL[enforcementPoint] ?? 'Enforcement point unrecognised';
  const meaning = POINT_MEANING[enforcementPoint] ?? 'treat as advisory';

  return (
    <span
      className={`${styles.badge} ${enforced ? styles.enforced : styles.advisory}`}
      data-testid="enforcement-badge"
      data-enforcement-point={enforcementPoint}
      data-enforced={enforced ? 'true' : 'false'}
      title={boundaryNote}
      // The accessible name carries the boundary, not just the word. A
      // screen-reader user must not get a bare "enforced" either (A-09's
      // rule, applied to this primitive).
      aria-label={`${label}. ${meaning}.`}
    >
      <span className={styles.point} data-testid="enforcement-point">
        {label}
      </span>
      <span className={styles.meaning} data-testid="enforcement-meaning">
        {verbose ? boundaryNote : meaning}
      </span>
    </span>
  );
}
