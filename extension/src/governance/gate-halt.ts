/**
 * Host-side handler for the sidecar's `gate/halt` notification (FR-M12-06;
 * F1 Workstream B task 11).
 *
 * Governance halted a hosted session: the halt is already durable in the
 * ledger (the sidecar recorded it before dispatching). The handler routes
 * the halt to the hosted-session registry, which owns the process kill,
 * and surfaces a warning either way — a halt the operator never saw would
 * be a silent governance act.
 */
import type { GateHaltNotification } from '../../../shared/ts/bus-types';
import type { HostedSessionRegistry } from './session-registry';

export interface GateHaltHandlerDeps {
  registry: HostedSessionRegistry;
  /** Visible warning channel (vscode.window.showWarningMessage in prod). */
  warn: (message: string) => void;
}

/** Narrow an untyped bus notification to the gate/halt shape. */
export function asGateHaltNotification(
  method: string,
  params: unknown,
): GateHaltNotification | undefined {
  if (method !== 'gate/halt' || typeof params !== 'object' || params === null) {
    return undefined;
  }
  const candidate = params as Partial<GateHaltNotification>;
  if (
    typeof candidate.sequence === 'number' &&
    typeof candidate.sessionId === 'string' &&
    typeof candidate.reason === 'string'
  ) {
    return candidate as GateHaltNotification;
  }
  return undefined;
}

/**
 * Handle one `gate/halt` notification. Returns true when the notification
 * was a well-formed halt (handled or not); false when it was something
 * else, so the caller's dispatch falls through.
 */
export function handleGateHaltNotification(
  method: string,
  params: unknown,
  deps: GateHaltHandlerDeps,
): boolean {
  const halt = asGateHaltNotification(method, params);
  if (!halt) {
    return false;
  }
  if (deps.registry.halt(halt.sessionId, halt.reason)) {
    deps.warn(
      `Governance halted hosted session '${halt.sessionId}' ` +
        `(ledger seq ${halt.sequence}): ${halt.reason}`,
    );
  } else {
    deps.warn(
      `Governance halt for hosted session '${halt.sessionId}' ` +
        `(ledger seq ${halt.sequence}) arrived, but no such session is running: ${halt.reason}`,
    );
  }
  return true;
}
