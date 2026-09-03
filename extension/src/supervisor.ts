import { spawn } from 'node:child_process';
import type { SidecarClient } from './sidecar';

/**
 * The supervisor's view of a sidecar client: the RPC seam plus lifecycle.
 * StdioSidecarClient satisfies this; tests inject fakes.
 */
export interface ManagedClient extends SidecarClient {
  start(): Promise<void>;
  kill(): void;
  readonly pid?: number;
  /** Fire-and-forget notification; optional so test fakes stay minimal. */
  notify?(method: string, params: unknown): void;
  on(event: 'exit', listener: (code: number | null, signal: string | null) => void): unknown;
  on(event: 'spawnError', listener: (error: Error) => void): unknown;
}

export type SupervisorState = 'stopped' | 'ready' | 'restarting' | 'failed';

export interface SupervisorDeps {
  clientFactory: () => ManagedClient;
  /** Kills the whole process tree; defaults to taskkill /T on Windows. */
  killTree?: (pid: number) => void;
  /** ms to wait for the graceful shutdown request before SIGTERM. */
  shutdownTimeoutMs?: number;
  /** ms to wait after SIGTERM before the tree kill. */
  termGraceMs?: number;
  /** FR-M3-06 heartbeat period; default 5_000. */
  heartbeatIntervalMs?: number;
  /** ms a heartbeat ping may take before the sidecar counts as dead. */
  pingTimeoutMs?: number;
  /** FR-M3-06 restart budget: max attempts inside the window. */
  maxRestarts?: number;
  /** FR-M3-06 restart window; default 300_000 (5 minutes). */
  restartWindowMs?: number;
  /** Actionable errors for the user (FR-M3-04); defaults to a no-op. */
  onError?: (message: string) => void;
  onStateChange?: (state: SupervisorState) => void;
}

/**
 * FR-M3-02: the Sidecar Supervisor owns the child lifecycle. stop() runs a
 * three-stage teardown: polite `shutdown` RPC → SIGTERM → tree kill
 * (taskkill /T /F on Windows, SIGKILL elsewhere). Extension deactivate() and
 * subscription disposal both route here, so there is no path that abandons
 * the child. (FR-M3-03's independent sidecar-side guard covers the case
 * where this process itself dies first.)
 *
 * FR-M3-02 also requires teardown on webview disposal when the webview is
 * the last consumer; the webview lands with the GUI workstreams and will
 * hold a reference counted against this supervisor.
 *
 * FR-M3-06: while running, a heartbeat pings the sidecar every
 * heartbeatIntervalMs (5 s). A dead or unresponsive sidecar is restarted
 * with exponential backoff, at most maxRestarts (3) times in
 * restartWindowMs (5 min); beyond that the supervisor enters the failed
 * state and requires user action.
 */
export class SidecarSupervisor {
  private client: ManagedClient | undefined;
  private stopping = false;
  private state: SupervisorState = 'stopped';
  private heartbeat: NodeJS.Timeout | undefined;
  private restartTimer: NodeJS.Timeout | undefined;
  private restartTimestamps: number[] = [];

  constructor(private readonly deps: SupervisorDeps) {}

  get currentState(): SupervisorState {
    return this.state;
  }

  get isRunning(): boolean {
    return this.state === 'ready';
  }

  /** Exposed for tests and the health/restart policy (FR-M3-06). */
  get currentClient(): ManagedClient | undefined {
    return this.client;
  }

  async start(): Promise<void> {
    if (this.client) {
      throw new Error('supervisor already started');
    }
    await this.spawnClient();
  }

  private async spawnClient(): Promise<void> {
    const client = this.deps.clientFactory();
    this.client = client;
    client.on('spawnError', (error: Error) => {
      this.deps.onError?.(error.message);
    });
    client.on('exit', (code, signal) => {
      if (!this.stopping) {
        this.handleUnexpectedExit(code, signal);
      }
    });
    try {
      await client.start();
    } catch (error) {
      this.client = undefined;
      this.deps.onError?.(error instanceof Error ? error.message : String(error));
      throw error;
    }
    this.setState('ready');
    this.startHeartbeat();
  }

  /**
   * Graceful teardown with escalation. Always resolves: teardown must never
   * throw out of deactivate().
   */
  async stop(): Promise<void> {
    this.stopHeartbeat();
    if (this.restartTimer) {
      clearTimeout(this.restartTimer);
      this.restartTimer = undefined;
    }
    const client = this.client;
    this.client = undefined;
    this.stopping = true;
    this.setState('stopped');
    if (!client) {
      this.stopping = false;
      return;
    }
    try {
      const exited = this.waitForExit(client);
      // Stage 1: polite shutdown request. Fire-and-forget: a wedged sidecar
      // must not block escalation, so we never await the response itself.
      void client
        .request('shutdown', { reason: 'extension deactivate' }, new AbortController().signal)
        .catch(() => undefined);
      if (await exited.within(this.deps.shutdownTimeoutMs ?? 5_000)) {
        return;
      }
      // Stage 2: SIGTERM (no-op on Windows, which is why stage 3 exists).
      client.kill();
      if (await exited.within(this.deps.termGraceMs ?? 2_000)) {
        return;
      }
      // Stage 3: kill the whole tree — a stuck sidecar must not outlive us.
      const pid = client.pid;
      if (pid !== undefined) {
        (this.deps.killTree ?? killProcessTree)(pid);
      }
      await exited.within(2_000);
    } finally {
      this.stopping = false;
    }
  }

  // -- FR-M3-06: heartbeat --------------------------------------------------

  private startHeartbeat(): void {
    this.stopHeartbeat();
    const interval = this.deps.heartbeatIntervalMs ?? 5_000;
    this.heartbeat = setInterval(() => {
      void this.beat();
    }, interval);
    this.heartbeat.unref?.();
  }

  private stopHeartbeat(): void {
    if (this.heartbeat) {
      clearInterval(this.heartbeat);
      this.heartbeat = undefined;
    }
  }

  private async beat(): Promise<void> {
    const client = this.client;
    if (!client || this.stopping || this.state !== 'ready') {
      return;
    }
    const timeoutMs = this.deps.pingTimeoutMs ?? 3_000;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), timeoutMs);
    try {
      await client.request('ping', {}, controller.signal);
    } catch {
      // Unresponsive: treat as dead and run the restart policy.
      client.kill();
      this.handleUnexpectedExit(null, 'heartbeat-timeout');
    } finally {
      clearTimeout(timeout);
    }
  }

  // -- FR-M3-06: bounded restart --------------------------------------------

  private handleUnexpectedExit(code: number | null, signal: string | null): void {
    this.stopHeartbeat();
    const now = Date.now();
    const windowMs = this.deps.restartWindowMs ?? 300_000;
    const maxRestarts = this.deps.maxRestarts ?? 3;
    this.restartTimestamps = this.restartTimestamps.filter((t) => now - t < windowMs);
    if (this.restartTimestamps.length >= maxRestarts) {
      this.client = undefined;
      this.setState('failed');
      this.deps.onError?.(
        `Meridian Core sidecar failed ${maxRestarts + 1} times within ` +
          `${Math.round(windowMs / 60_000)} minutes (last exit: code=${code} ` +
          `signal=${signal}) and will not restart again. Check the Meridian ` +
          'Loom output channel, then reload the window to retry.',
      );
      return;
    }
    this.restartTimestamps.push(now);
    const attempt = this.restartTimestamps.length;
    const backoffMs = 1_000 * 2 ** (attempt - 1);
    this.setState('restarting');
    this.deps.onError?.(
      `Meridian Core sidecar stopped unexpectedly (code=${code} signal=${signal}). ` +
        `Restarting (attempt ${attempt} of ${maxRestarts})…`,
    );
    this.restartTimer = setTimeout(() => {
      this.restartTimer = undefined;
      void this.spawnClient().catch(() => {
        // spawnClient already reported; run the budget check again so a
        // failing spawn consumes restart budget like a crash does.
        this.handleUnexpectedExit(null, 'spawn-failed');
      });
    }, backoffMs);
    this.restartTimer.unref?.();
  }

  private setState(state: SupervisorState): void {
    this.state = state;
    this.deps.onStateChange?.(state);
  }

  private waitForExit(client: ManagedClient): { within(ms: number): Promise<boolean> } {
    let resolveExit: (() => void) | undefined;
    const exitPromise = new Promise<void>((resolve) => {
      resolveExit = resolve;
    });
    client.on('exit', () => resolveExit?.());
    return {
      within(ms: number): Promise<boolean> {
        return Promise.race([
          exitPromise.then(() => true),
          new Promise<boolean>((resolve) => setTimeout(() => resolve(false), ms)),
        ]);
      },
    };
  }
}

/**
 * Kill a process and its children. Windows SIGTERM/SIGKILL via child.kill()
 * only target the direct child and TerminateProcess is unconditional there
 * anyway; taskkill /T is the reliable tree kill on win32. Async spawn keeps
 * the extension host thread clean (FR-M1-04).
 */
export function killProcessTree(pid: number): void {
  if (process.platform === 'win32') {
    const child = spawn('taskkill', ['/pid', String(pid), '/T', '/F'], {
      stdio: 'ignore',
    });
    child.on('error', () => undefined);
    child.unref();
  } else {
    try {
      process.kill(pid, 'SIGKILL');
    } catch {
      // already dead
    }
  }
}
