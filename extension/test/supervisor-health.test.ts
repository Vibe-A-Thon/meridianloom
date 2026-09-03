import { EventEmitter } from 'node:events';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { ManagedClient, SupervisorState } from '../src/supervisor';
import { SidecarSupervisor } from '../src/supervisor';

class FakeClient extends EventEmitter implements ManagedClient {
  readonly pid = Math.floor(Math.random() * 100000) + 1000;
  pings = 0;
  failPings = false;
  failStart = false;

  async start(): Promise<void> {
    if (this.failStart) {
      throw new Error('spawn failed');
    }
  }

  async request<T>(method: string): Promise<T> {
    if (method === 'ping') {
      this.pings += 1;
      if (this.failPings) {
        throw new Error('no answer');
      }
      return { pong: true } as T;
    }
    if (method === 'shutdown') {
      queueMicrotask(() => this.emit('exit', 0, null));
      return { ok: true } as T;
    }
    return {} as T;
  }

  kill(): void {
    queueMicrotask(() => this.emit('exit', null, 'SIGTERM'));
  }
}

describe('SidecarSupervisor health checks and restart policy (FR-M3-06)', () => {
  let clients: FakeClient[];
  let errors: string[];
  let states: SupervisorState[];
  let supervisor: SidecarSupervisor;

  beforeEach(() => {
    vi.useFakeTimers();
    clients = [];
    errors = [];
    states = [];
    supervisor = new SidecarSupervisor({
      clientFactory: () => {
        const client = new FakeClient();
        clients.push(client);
        return client;
      },
      onError: (message) => errors.push(message),
      onStateChange: (state) => states.push(state),
      heartbeatIntervalMs: 5_000,
      pingTimeoutMs: 500,
    });
  });

  afterEach(async () => {
    await supervisor.stop();
    vi.useRealTimers();
  });

  it('pings the sidecar every 5 seconds', async () => {
    await supervisor.start();
    expect(clients[0].pings).toBe(0);
    await vi.advanceTimersByTimeAsync(15_100);
    expect(clients[0].pings).toBe(3);
  });

  it('restarts with backoff when the sidecar dies unexpectedly', async () => {
    await supervisor.start();
    clients[0].emit('exit', 1, null);
    expect(supervisor.currentState).toBe('restarting');
    // Backoff for the first restart is 1 s.
    await vi.advanceTimersByTimeAsync(1_000);
    expect(clients).toHaveLength(2);
    expect(supervisor.currentState).toBe('ready');
    // The restarted client is supervised too.
    await vi.advanceTimersByTimeAsync(5_100);
    expect(clients[1].pings).toBe(1);
  });

  it('gives up after 3 restarts in 5 minutes with an actionable error', async () => {
    await supervisor.start();
    for (let crash = 0; crash < 4; crash += 1) {
      const current = clients[clients.length - 1];
      current.emit('exit', 1, null);
      await vi.advanceTimersByTimeAsync(8_000); // past any backoff
    }
    expect(clients).toHaveLength(4); // initial + 3 restarts, then refused
    expect(supervisor.currentState).toBe('failed');
    const finalError = errors[errors.length - 1];
    expect(finalError).toMatch(/failed 4 times within 5 minutes/);
    expect(finalError).toMatch(/reload the window/i);
  });

  it('resets the restart budget after the 5-minute window', async () => {
    await supervisor.start();
    clients[0].emit('exit', 1, null);
    await vi.advanceTimersByTimeAsync(1_000);
    expect(clients).toHaveLength(2);
    // Stable for more than the window: the earlier crash ages out.
    await vi.advanceTimersByTimeAsync(301_000);
    clients[1].emit('exit', 1, null);
    await vi.advanceTimersByTimeAsync(1_000);
    expect(clients).toHaveLength(3);
    expect(supervisor.currentState).toBe('ready');
  });

  it('an unresponsive heartbeat counts as a crash and restarts', async () => {
    await supervisor.start();
    clients[0].failPings = true;
    await vi.advanceTimersByTimeAsync(5_100);
    await vi.advanceTimersByTimeAsync(1_000); // backoff
    expect(clients).toHaveLength(2);
    expect(supervisor.currentState).toBe('ready');
  });

  it('stop() cancels a pending restart', async () => {
    await supervisor.start();
    clients[0].emit('exit', 1, null);
    expect(supervisor.currentState).toBe('restarting');
    await supervisor.stop();
    await vi.advanceTimersByTimeAsync(60_000);
    expect(clients).toHaveLength(1); // no restart fired
    expect(supervisor.currentState).toBe('stopped');
  });
});
