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
  on(event: 'exit', listener: (code: number | null, signal: string | null) => void): unknown;
  on(event: 'spawnError', listener: (error: Error) => void): unknown;
}

export interface SupervisorDeps {
  clientFactory: () => ManagedClient;
  /** Kills the whole process tree; defaults to taskkill /T on Windows. */
  killTree?: (pid: number) => void;
  /** ms to wait for the graceful shutdown request before SIGTERM. */
  shutdownTimeoutMs?: number;
  /** ms to wait after SIGTERM before the tree kill. */
  termGraceMs?: number;
  /** Actionable errors for the user (FR-M3-04); defaults to a no-op. */
  onError?: (message: string) => void;
  onStderr?: (line: string) => void;
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
 */
export class SidecarSupervisor {
  private client: ManagedClient | undefined;
  private stopping = false;
  private running = false;

  constructor(private readonly deps: SupervisorDeps) {}

  get isRunning(): boolean {
    return this.running;
  }

  /** Exposed for tests and the health/restart policy (FR-M3-06). */
  get currentClient(): ManagedClient | undefined {
    return this.client;
  }

  async start(): Promise<void> {
    if (this.client) {
      throw new Error('supervisor already started');
    }
    const client = this.deps.clientFactory();
    this.client = client;
    client.on('spawnError', (error: Error) => {
      this.deps.onError?.(error.message);
    });
    client.on('exit', (code, signal) => {
      this.running = false;
      if (!this.stopping) {
        // Unexpected death. Restart policy lands with FR-M3-06; until then,
        // surface it so the failure is never silent.
        this.deps.onError?.(
          `Meridian Core sidecar stopped unexpectedly (code=${code} signal=${signal}). ` +
            'Run "Meridian Loom: Doctor" for diagnostics.',
        );
      }
    });
    try {
      await client.start();
    } catch (error) {
      this.client = undefined;
      this.deps.onError?.(error instanceof Error ? error.message : String(error));
      throw error;
    }
    this.running = true;
  }

  /**
   * Graceful teardown with escalation. Always resolves: teardown must never
   * throw out of deactivate().
   */
  async stop(): Promise<void> {
    const client = this.client;
    this.client = undefined;
    if (!client) {
      return;
    }
    this.stopping = true;
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
      this.running = false;
    }
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
