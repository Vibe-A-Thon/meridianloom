import { useState } from 'react';
import { EnforcementBadge, type ControlDeclaration } from './EnforcementBadge';
import styles from './preflight-dialog.module.css';

/**
 * Screen 10.51 Launch, at its minimum — FR-M40-03, MV2-T06.
 *
 * Four questions answered before the button: *what*, *who*, *where*, *how
 * much* — plus *where it will stop*. That is the whole screen, and it is
 * the whole of preflight.
 *
 * The property that matters: **the confirm is disabled unless every answer
 * is present.** An incomplete preflight that still offers "Start" is a
 * consent dialog with a hole in it — the human confirms a cost they were
 * never shown. `missing` comes from the sidecar rather than being computed
 * here, so the surface and the contract cannot disagree about what counts
 * as answered.
 *
 * B9: the live run is destructive and carries a two-step confirm. The
 * dry run does not, because it writes nothing.
 */

export interface Preflight {
  runId: string;
  origin: string;
  intent: string;
  adapters: Record<string, string>;
  repo: string;
  baseBranch: string;
  branch: string;
  worktree: string;
  estimateUsd: number | null;
  costCeilingUsd: number | null;
  gates: string[];
  mode: 'dry_run' | 'live';
  confirmable: boolean;
  missing: string[];
}

export interface PreflightDialogProps {
  /** `undefined` while loading; the four states of B2 are below. */
  preflight?: Preflight;
  error?: string;
  busy?: boolean;
  /** The launch control's enforcement point, from the sidecar. */
  declaration?: ControlDeclaration | null;
  onConfirm(preflight: Preflight): void;
  onCancel(preflight?: Preflight): void;
}

const MISSING_LABEL: Record<string, string> = {
  intent: 'what this run is for',
  adapters: 'which agents will act',
  target: 'the repository and base branch',
  estimate: 'the cost estimate and ceiling',
  gates: 'where the run will stop',
  mode: 'dry run or live',
};

function money(value: number | null): string {
  // `null` is unknown, not zero. Rendering a missing estimate as "$0.00"
  // would tell a human the run is free (P26).
  return value === null ? 'not estimated' : `$${value.toFixed(2)}`;
}

export function PreflightDialog({
  preflight,
  error,
  busy,
  declaration,
  onConfirm,
  onCancel,
}: PreflightDialogProps) {
  const [armed, setArmed] = useState(false);

  if (error) {
    return (
      <div className={styles.dialog} role="alertdialog" aria-label="Preflight failed">
        <p className={styles.error} role="alert">
          {error}
        </p>
        <button onClick={() => onCancel()}>Close</button>
      </div>
    );
  }

  if (!preflight) {
    return (
      <div className={styles.dialog} role="dialog" aria-label="Preparing preflight">
        <p className={styles.muted} data-testid="preflight-loading">
          Working out what this run would do. Nothing has been created yet.
        </p>
      </div>
    );
  }

  const live = preflight.mode === 'live';
  const blocked = !preflight.confirmable;

  return (
    <div className={styles.dialog} role="dialog" aria-label="Confirm this run">
      <header className={styles.header}>
        <h2>Start a run</h2>
        <span className={styles.muted} data-testid="preflight-origin">
          via {preflight.origin}
        </span>
      </header>

      {declaration !== undefined && (
        <EnforcementBadge declaration={declaration} />
      )}

      <section className={styles.block} aria-label="What">
        <h3>What</h3>
        <p data-testid="preflight-intent">{preflight.intent}</p>
      </section>

      <section className={styles.block} aria-label="Who">
        <h3>Who</h3>
        <ul data-testid="preflight-adapters">
          {Object.entries(preflight.adapters).map(([role, adapter]) => (
            <li key={role}>
              <strong>{role}</strong> {adapter}
            </li>
          ))}
        </ul>
      </section>

      <section className={styles.block} aria-label="Where">
        <h3>Where</h3>
        <p data-testid="preflight-target">
          {preflight.repo} · base {preflight.baseBranch} · branch {preflight.branch}
        </p>
        {/*
          The worktree promise, on the screen rather than in documentation.
          It is the product's core safety claim and the moment a human is
          deciding whether to trust it is exactly when they should read it.
        */}
        <p className={styles.muted} data-testid="preflight-worktree">
          {preflight.worktree} — your working tree is untouched.
        </p>
      </section>

      <section className={styles.block} aria-label="How much">
        <h3>How much</h3>
        <p data-testid="preflight-estimate">
          estimated {money(preflight.estimateUsd)} · ceiling{' '}
          {money(preflight.costCeilingUsd)}
        </p>
      </section>

      <section className={styles.block} aria-label="Where it will stop">
        <h3>Where it will stop</h3>
        <ul data-testid="preflight-gates">
          {preflight.gates.map((gate) => (
            <li key={gate}>{gate}</li>
          ))}
        </ul>
      </section>

      {blocked && (
        <p className={styles.blocked} role="alert" data-testid="preflight-missing">
          This run cannot start yet — {preflight.missing
            .map((key) => MISSING_LABEL[key] ?? key)
            .join(', ')}{' '}
          {preflight.missing.length === 1 ? 'is' : 'are'} not settled.
        </p>
      )}

      <footer className={styles.actions}>
        <button onClick={() => onCancel(preflight)} data-testid="preflight-cancel">
          Cancel
        </button>
        {live && !armed ? (
          // B9 step one. A live run writes to a real repository and spends
          // real money, so it takes two deliberate actions rather than one.
          <button
            className={styles.primary}
            disabled={blocked || busy}
            data-testid="preflight-arm"
            onClick={() => setArmed(true)}
          >
            Start live run…
          </button>
        ) : (
          <button
            className={styles.primary}
            disabled={blocked || busy}
            data-testid="preflight-confirm"
            onClick={() => onConfirm(preflight)}
          >
            {live ? 'Confirm live run' : 'Start dry run'}
          </button>
        )}
      </footer>

      <p className={styles.muted} data-testid="preflight-footnote">
        Cancelling creates nothing. Nothing exists until you confirm.
      </p>
    </div>
  );
}
