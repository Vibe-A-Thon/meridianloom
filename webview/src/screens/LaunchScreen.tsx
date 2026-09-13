import { useState } from 'react';
import type { RunPreflight } from '../../../shared/ts/bus-types';
import { PreflightDialog, type Preflight } from '../components/PreflightDialog';
import { useEnforcementPoints } from '../hooks/useEnforcementPoints';
import { RpcError } from '../rpc/client';
import type { ScreenProps } from './registry';
import styles from './launch-screen.module.css';

/**
 * 10.51 Launch — FR-M40-01/02/03/09, AC-38/39, MV2-T06.
 *
 * The workbench door into run initiation. It is registered at the Governor
 * tier, which is what makes it **absent** below that tier rather than
 * disabled: `visibleScreens` filters the registry, so a Flight Recorder user
 * has no Launch entry in the Loom Bar at all — not a greyed one, not an
 * empty state (banned pattern 30, X-28).
 *
 * Everything about what a run *is* lives in the sidecar. This screen asks
 * `run/preflight` what the run would do, renders the answer, and calls the
 * one entry point after a human confirms. `confirmable` and `missing` are
 * read, never computed here — the moment a surface decides for itself which
 * answers are required, two doors have two definitions of a run, which is
 * the thing M40 exists to prevent.
 *
 * The screen at its minimum. The full 10.51 — templates, per-run overrides,
 * content provenance, editor context — stays specified and POST-MVP.
 */

/** The control whose enforcement point this screen renders (MV1-T02). */
const LAUNCH_CONTROL = 'permission_policy';

type Phase =
  | { kind: 'idle' }
  | { kind: 'preflighting' }
  | { kind: 'ready'; preflight: RunPreflight }
  | { kind: 'starting'; preflight: RunPreflight }
  | { kind: 'started'; runId: string; branch: string; mode: string; authorisedBy: string; assurance: string }
  | { kind: 'cancelled'; runId: string }
  | { kind: 'error'; message: string };

function describe(error: unknown): string {
  if (error instanceof RpcError) return error.message;
  return error instanceof Error ? error.message : String(error);
}

export function LaunchScreen({ client, ready, workspaceDir }: ScreenProps) {
  const [intent, setIntent] = useState('');
  const [phase, setPhase] = useState<Phase>({ kind: 'idle' });
  const enforcement = useEnforcementPoints(ready ? client : undefined);

  async function preflight(event: React.FormEvent) {
    event.preventDefault();
    if (!intent.trim()) return;
    setPhase({ kind: 'preflighting' });
    try {
      const result = await client.request('run/preflight', {
        origin: 'ui',
        intent: intent.trim(),
        repo: workspaceDir ?? '.',
      });
      setPhase({ kind: 'ready', preflight: result.preflight });
    } catch (error) {
      setPhase({ kind: 'error', message: describe(error) });
    }
  }

  async function confirm(shown: Preflight) {
    if (phase.kind !== 'ready') return;
    const pending = phase.preflight;
    setPhase({ kind: 'starting', preflight: pending });
    try {
      // The preflight sent back is the one the sidecar produced, not the one
      // the dialog rendered: the human confirmed what they were shown, and
      // the server re-derives the branch and worktree from the run id and
      // refuses if they disagree. `shown` is the dialog's copy and is used
      // only to assert they are the same run.
      if (shown.runId !== pending.runId) {
        throw new Error('the confirmed preflight is not the one that was prepared');
      }
      const started = await client.request('run/start', {
        preflight: pending,
        confirmed: true,
      });
      setPhase({
        kind: 'started',
        runId: started.runId,
        branch: started.branch,
        mode: started.mode,
        authorisedBy: started.authorisedBy,
        assurance: started.assurance,
      });
    } catch (error) {
      setPhase({ kind: 'error', message: describe(error) });
    }
  }

  async function cancel() {
    if (phase.kind !== 'ready') {
      setPhase({ kind: 'idle' });
      return;
    }
    const pending = phase.preflight;
    try {
      await client.request('run/cancel', {
        preflight: pending,
        reason: 'cancelled at preflight',
      });
      setPhase({ kind: 'cancelled', runId: pending.runId });
    } catch (error) {
      // The run was never created, so the guarantee holds whatever happens
      // here; losing the note is not worth replacing the reassurance with an
      // error the reader can do nothing about.
      setPhase({ kind: 'cancelled', runId: pending.runId });
    }
  }

  if (phase.kind === 'ready' || phase.kind === 'starting' || phase.kind === 'preflighting') {
    return (
      <section className={styles.screen} aria-label="Launch">
        {/*
          `undefined` while the declaration is still being fetched, never
          `null`: EnforcementBadge refuses to render without a declaration,
          so passing the null of a query that has not answered yet would turn
          a slow fetch into a crash. The dialog renders no badge until it can
          render a true one.
        */}
        <PreflightDialog
          preflight={phase.kind === 'preflighting' ? undefined : toDialog(phase.preflight)}
          busy={phase.kind === 'starting'}
          declaration={enforcement.lookup(LAUNCH_CONTROL)}
          onConfirm={confirm}
          onCancel={cancel}
        />
      </section>
    );
  }

  return (
    <section className={styles.screen} aria-label="Launch">
      <header className={styles.header}>
        <h2>Start a run</h2>
        <p className={styles.muted}>
          Nothing is created until you confirm what the run will do.
        </p>
      </header>

      {phase.kind === 'error' && (
        <p className={styles.error} role="alert" data-testid="launch-error">
          {phase.message}
        </p>
      )}

      {phase.kind === 'started' && (
        <p className={styles.started} data-testid="launch-started">
          Run {phase.runId} started on {phase.branch} ({phase.mode}), authorised by{' '}
          {phase.authorisedBy} at assurance {phase.assurance}.
        </p>
      )}

      {phase.kind === 'cancelled' && (
        <p className={styles.muted} data-testid="launch-cancelled">
          Run {phase.runId} was cancelled at preflight. No worktree and no branch
          were created; the cancellation is recorded.
        </p>
      )}

      <form className={styles.form} onSubmit={preflight}>
        <label className={styles.label} htmlFor="launch-intent">
          What should this run do?
        </label>
        <textarea
          id="launch-intent"
          className={styles.intent}
          rows={3}
          value={intent}
          onChange={(event) => setIntent(event.target.value)}
          placeholder="Add an idempotency key to the payment submission endpoint"
          data-testid="launch-intent"
        />
        <button
          type="submit"
          className={styles.primary}
          disabled={!ready || !intent.trim()}
          data-testid="launch-preflight"
        >
          Preflight…
        </button>
      </form>
    </section>
  );
}

/**
 * The wire shape and the dialog's differ in two places the generator cannot
 * narrow: `adapters` values arrive as `unknown` from a JSON-Schema map, and
 * the two cost fields are optional on the wire while the dialog requires
 * them so that "absent" and "unknown" cannot be confused. Both narrowings
 * happen once, here — the dialog never has to decide what a missing field
 * means, which is how "$0.00" gets rendered for a run nobody priced.
 */
function toDialog(preflight: RunPreflight): Preflight {
  return {
    runId: preflight.runId,
    origin: preflight.origin,
    intent: preflight.intent,
    adapters: Object.fromEntries(
      Object.entries(preflight.adapters).map(([role, adapter]) => [role, String(adapter)]),
    ),
    repo: preflight.repo,
    baseBranch: preflight.baseBranch,
    branch: preflight.branch,
    worktree: preflight.worktree,
    estimateUsd: preflight.estimateUsd ?? null,
    costCeilingUsd: preflight.costCeilingUsd ?? null,
    gates: [...preflight.gates],
    mode: preflight.mode,
    confirmable: preflight.confirmable,
    missing: [...preflight.missing],
  };
}
