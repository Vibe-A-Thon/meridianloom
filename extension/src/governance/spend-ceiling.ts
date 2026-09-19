/**
 * Host-side handler for the sidecar's `spend/ceiling` notification
 * (FR-M39-02; D33; F1 Workstream F task 27).
 *
 * The sidecar owns the durable record: it wrote the spend_ceiling ledger
 * entry before dispatching. It also already split hosted from observed —
 * the notification only fires for a breach on something Meridian hosts.
 * This handler owns the wire-side truth:
 *
 *  - hosted session (registered in the HostedSessionRegistry): the session
 *    is marked pause-pending in the SpendCeilingPauseTracker. ACP has no
 *    pause primitive, so "pause at next checkpoint" is honest turn-boundary
 *    enforcement: the turn already in flight runs to its stop reason, and
 *    the NEXT turn is refused at the checkpoint gate (AcpClient.prompt's
 *    checkpointGate option; the steer controller checks the tracker too).
 *    Nothing is cancelled or killed mid-flight — that is the difference
 *    from gate.halt, which owns a process kill.
 *  - observed / not hosted: the notification names a session this host
 *    does not run — advisory only, no pause, no fake control (the same
 *    NOT_HOSTED honesty as steer, FR-M35-06).
 *  - unbound (no sessionId): the pause cannot be mapped to a session this
 *    host runs, so none is applied — surfaced, never faked.
 *
 * Resume: after the human clears or raises the ceiling, the host re-runs
 * the sidecar's spend/ceilingCheck; only a clean re-check releases the
 * pause (resumeAfterCeilingCleared). The sidecar stays the source of truth
 * for whether the breach still stands.
 */
import type { SpendCeilingNotification } from '../../../shared/ts/bus-types';
import type { HostedSessionRegistry } from './session-registry';

/** Narrow an untyped bus notification to the spend/ceiling shape. */
export function asSpendCeilingNotification(
  method: string,
  params: unknown,
): SpendCeilingNotification | undefined {
  if (method !== 'spend/ceiling' || typeof params !== 'object' || params === null) {
    return undefined;
  }
  const candidate = params as Partial<SpendCeilingNotification>;
  if (typeof candidate.sequence !== 'number' || candidate.action !== 'pauseAtCheckpoint') {
    return undefined;
  }
  if (candidate.sessionId != null && typeof candidate.sessionId !== 'string') {
    return undefined;
  }
  if (candidate.actorId != null && typeof candidate.actorId !== 'string') {
    return undefined;
  }
  return candidate as SpendCeilingNotification;
}

/** The durable host-side pause state for one hosted session. */
export interface SpendCeilingPause {
  sessionId: string;
  /** Sequence of the spend_ceiling ledger entry behind the pause. */
  sequence: number;
  spentUsd?: number;
  actorId?: string | null;
  /** ISO timestamp of when the pause was marked. */
  pausedAt: string;
}

/**
 * Pause-pending state per hosted session. The registry answers "is this
 * session hosted here"; the tracker answers "is it pause-pending" — kept
 * apart so an observed session can never acquire pause state (FR-M35-06).
 */
export class SpendCeilingPauseTracker {
  private readonly pauses = new Map<string, SpendCeilingPause>();

  /** Mark a hosted session pause-pending; true when newly paused. */
  pause(note: SpendCeilingNotification, now: Date = new Date()): boolean {
    const sessionId = note.sessionId;
    if (!sessionId || this.pauses.has(sessionId)) {
      return false;
    }
    this.pauses.set(sessionId, {
      sessionId,
      sequence: note.sequence,
      spentUsd: note.spentUsd,
      actorId: note.actorId ?? null,
      pausedAt: now.toISOString(),
    });
    return true;
  }

  /** Release a pause after the ceiling is cleared; true when one existed. */
  resume(sessionId: string): boolean {
    return this.pauses.delete(sessionId);
  }

  isPaused(sessionId: string): boolean {
    return this.pauses.has(sessionId);
  }

  get(sessionId: string): SpendCeilingPause | undefined {
    return this.pauses.get(sessionId);
  }

  ids(): string[] {
    return [...this.pauses.keys()];
  }
}

export const PAUSE_PENDING_CODE = 'PAUSE_PENDING';

/**
 * Structured refusal raised at the checkpoint gate when a new turn is
 * requested while the session is pause-pending. Mirrors NotHostedSessionError
 * so both governance refusals carry honest, machine-readable data.
 */
export class SpendCeilingPausePendingError extends Error {
  constructor(readonly pause: SpendCeilingPause) {
    super(
      `Hosted session '${pause.sessionId}' is pause-pending at a spend ceiling ` +
        `(ledger seq ${pause.sequence}` +
        (typeof pause.spentUsd === 'number' ? `, $${pause.spentUsd.toFixed(2)} spent` : '') +
        `): no new turn starts until the ceiling is cleared and spend/ceilingCheck ` +
        `re-runs clean. The in-flight turn was not touched.`,
    );
    this.name = 'SpendCeilingPausePendingError';
  }

  get data(): Record<string, unknown> {
    return {
      code: PAUSE_PENDING_CODE,
      sessionId: this.pause.sessionId,
      sequence: this.pause.sequence,
      spentUsd: this.pause.spentUsd,
      pausedAt: this.pause.pausedAt,
      hosted: true,
      remediation:
        'Clear or raise the budget ceiling (governance pack budgetCeilings), then re-run ' +
        'spend/ceilingCheck for the session — a clean re-check releases the pause.',
    };
  }
}

/** Throw when the session is pause-pending; a no-op otherwise. */
export function assertNotPausePending(tracker: SpendCeilingPauseTracker, sessionId: string): void {
  const pause = tracker.get(sessionId);
  if (pause) {
    throw new SpendCeilingPausePendingError(pause);
  }
}

export interface SpendCeilingHandlerDeps {
  registry: HostedSessionRegistry;
  tracker: SpendCeilingPauseTracker;
  /** Visible warning channel (vscode.window.showWarningMessage in prod). */
  warn: (message: string) => void;
  /** Optional audit channel (console/output channel in prod). */
  log?: (message: string) => void;
}

/**
 * Handle one `spend/ceiling` notification. Returns true when the
 * notification was a well-formed ceiling pause (handled or not); false when
 * it was something else, so the caller's dispatch falls through.
 */
export function handleSpendCeilingNotification(
  method: string,
  params: unknown,
  deps: SpendCeilingHandlerDeps,
): boolean {
  const note = asSpendCeilingNotification(method, params);
  if (!note) {
    return false;
  }
  const sessionId = note.sessionId ?? null;
  if (sessionId !== null && deps.registry.has(sessionId)) {
    const fresh = deps.tracker.pause(note);
    const spent =
      typeof note.spentUsd === 'number' ? `, $${note.spentUsd.toFixed(2)} spent` : '';
    deps.warn(
      `Spend ceiling breached for hosted session '${sessionId}' ` +
        `(ledger seq ${note.sequence}${spent}): pause-pending at the next checkpoint — ` +
        `the running turn finishes, no new turn starts until the ceiling is cleared` +
        (fresh ? '.' : ' (already pause-pending).'),
    );
    deps.log?.(
      `spend/ceiling seq ${note.sequence}: '${sessionId}' pause-pending ` +
        `(hosted, registered in this host)`,
    );
  } else if (sessionId !== null) {
    // Observed, not hosted — FR-M35-06: no pause, no fake control.
    deps.warn(
      `Spend ceiling breached for session '${sessionId}' (ledger seq ${note.sequence}), ` +
        `but this host does not run it — observed, not hosted: advisory only, ` +
        `no pause applied (FR-M35-06).`,
    );
    deps.log?.(
      `spend/ceiling seq ${note.sequence}: '${sessionId}' not hosted here — advisory only`,
    );
  } else {
    deps.warn(
      `Spend ceiling breached (ledger seq ${note.sequence}` +
        (note.actorId ? ` for actor '${note.actorId}'` : '') +
        `) but the notification names no session, and this host cannot bind it ` +
        `to a hosted session — no pause applied.`,
    );
    deps.log?.(
      `spend/ceiling seq ${note.sequence}: no sessionId; no hosted session bound — no pause`,
    );
  }
  return true;
}

/**
 * Resume path after the human acknowledges/clears the ceiling: re-run the
 * sidecar's spend/ceilingCheck for the session. Only a re-check whose
 * action is no longer 'paused_at_checkpoint' releases the pause — the
 * sidecar, not the host, decides whether the breach still stands.
 */
export async function resumeAfterCeilingCleared(
  sessionId: string,
  tracker: SpendCeilingPauseTracker,
  sidecar: { request(method: string, params: unknown): Promise<unknown> },
): Promise<{ resumed: boolean; action: string }> {
  const result = (await sidecar.request('spend/ceilingCheck', { sessionId })) as {
    action?: unknown;
  };
  const action = typeof result?.action === 'string' ? result.action : 'none';
  if (action === 'paused_at_checkpoint') {
    return { resumed: false, action };
  }
  tracker.resume(sessionId);
  return { resumed: true, action };
}
