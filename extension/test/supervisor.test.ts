import { EventEmitter } from 'node:events';
import path from 'node:path';
import { describe, expect, it } from 'vitest';
import { resolveCoreDir } from '../src/layout';
import type { ManagedClient } from '../src/supervisor';
import { SidecarSupervisor } from '../src/supervisor';
import { StdioSidecarClient } from '../src/stdio-client';

class FakeClient extends EventEmitter implements ManagedClient {
  readonly pid = 5555;
  readonly requests: Array<{ method: string; params: unknown }> = [];
  ignoreShutdown = false;
  ignoreSigterm = false;
  sigtermCount = 0;
  startError: Error | undefined;

  async start(): Promise<void> {
    if (this.startError) {
      throw this.startError;
    }
  }

  request<T>(method: string, params: unknown): Promise<T> {
    this.requests.push({ method, params });
    if (method === 'shutdown') {
      if (!this.ignoreShutdown) {
        queueMicrotask(() => this.emit('exit', 0, null));
        return Promise.resolve({ ok: true } as T);
      }
      return new Promise<T>(() => undefined); // never answers
    }
    return Promise.resolve({} as T);
  }

  kill(): void {
    this.sigtermCount += 1;
    if (!this.ignoreSigterm) {
      queueMicrotask(() => this.emit('exit', null, 'SIGTERM'));
    }
  }
}

function makeSupervisor(fake: FakeClient, extra: Record<string, unknown> = {}) {
  const killedTrees: number[] = [];
  const errors: string[] = [];
  const supervisor = new SidecarSupervisor({
    clientFactory: () => fake,
    killTree: (pid: number) => {
      killedTrees.push(pid);
      queueMicrotask(() => fake.emit('exit', null, 'SIGKILL'));
    },
    shutdownTimeoutMs: 30,
    termGraceMs: 30,
    onError: (message: string) => errors.push(message),
    ...extra,
  });
  return { supervisor, killedTrees, errors };
}

describe('SidecarSupervisor teardown (FR-M3-02)', () => {
  it('stops gracefully via the shutdown RPC without any signal', async () => {
    const fake = new FakeClient();
    const { supervisor, killedTrees } = makeSupervisor(fake);
    await supervisor.start();
    await supervisor.stop();
    expect(fake.requests.map((r) => r.method)).toEqual(['shutdown']);
    expect(fake.sigtermCount).toBe(0);
    expect(killedTrees).toEqual([]);
    expect(supervisor.isRunning).toBe(false);
  });

  it('escalates to SIGTERM when the shutdown request is ignored', async () => {
    const fake = new FakeClient();
    fake.ignoreShutdown = true;
    const { supervisor, killedTrees } = makeSupervisor(fake);
    await supervisor.start();
    await supervisor.stop();
    expect(fake.sigtermCount).toBe(1);
    expect(killedTrees).toEqual([]);
  });

  it('escalates to a tree kill when SIGTERM is ignored', async () => {
    const fake = new FakeClient();
    fake.ignoreShutdown = true;
    fake.ignoreSigterm = true;
    const { supervisor, killedTrees } = makeSupervisor(fake);
    await supervisor.start();
    await supervisor.stop();
    expect(fake.sigtermCount).toBe(1);
    expect(killedTrees).toEqual([5555]);
  });

  it('never throws from stop(), even when nothing answers', async () => {
    const fake = new FakeClient();
    fake.ignoreShutdown = true;
    fake.ignoreSigterm = true;
    const { supervisor } = makeSupervisor(fake, {
      killTree: () => undefined, // even the tree kill does nothing
    });
    await supervisor.start();
    await expect(supervisor.stop()).resolves.toBeUndefined();
  });

  it('reports unexpected child death while running', async () => {
    const fake = new FakeClient();
    const { supervisor, errors } = makeSupervisor(fake);
    await supervisor.start();
    fake.emit('exit', 1, null);
    expect(errors.some((m) => m.includes('stopped unexpectedly'))).toBe(true);
  });

  it('does not report an expected stop as a failure', async () => {
    const fake = new FakeClient();
    const { supervisor, errors } = makeSupervisor(fake);
    await supervisor.start();
    await supervisor.stop();
    expect(errors).toEqual([]);
  });

  it('surfaces a start failure and rethrows', async () => {
    const fake = new FakeClient();
    fake.startError = new Error('interpreter not found');
    const { supervisor, errors } = makeSupervisor(fake);
    await expect(supervisor.start()).rejects.toThrow('interpreter not found');
    expect(errors).toEqual(['interpreter not found']);
    expect(supervisor.isRunning).toBe(false);
  });

  it('stop() with no client is a no-op', async () => {
    const { supervisor } = makeSupervisor(new FakeClient());
    await expect(supervisor.stop()).resolves.toBeUndefined();
  });
});

describe('resolveCoreDir', () => {
  it('finds the development core/ next to extension/', async () => {
    const extensionPath = path.resolve(__dirname, '..');
    await expect(resolveCoreDir(extensionPath)).resolves.toBe(
      path.resolve(extensionPath, '..', 'core'),
    );
  });

  it('throws an actionable error when the sidecar is missing', async () => {
    await expect(resolveCoreDir('/nonexistent/extension')).rejects.toThrow(/not found/);
  });
});

describe('SidecarSupervisor against the real sidecar (FR-M3-02)', () => {
  it('stop() leaves no running python process', { timeout: 30_000 }, async () => {
    const coreDir = path.resolve(__dirname, '..', '..', 'core');
    let pidAtStart: number | undefined;
    const supervisor = new SidecarSupervisor({
      clientFactory: () => {
        const client = new StdioSidecarClient({ command: 'python', cwd: coreDir });
        pidAtStart = undefined;
        return client;
      },
      shutdownTimeoutMs: 8_000,
    });
    await supervisor.start();
    pidAtStart = supervisor.currentClient?.pid;
    expect(pidAtStart).toBeGreaterThan(0);

    await supervisor.stop();

    // The graceful path must have worked: process is gone.
    const alive = await new Promise<boolean>((resolve) => {
      try {
        process.kill(pidAtStart!, 0);
        resolve(true);
      } catch {
        resolve(false);
      }
    });
    expect(alive).toBe(false);
    expect(supervisor.isRunning).toBe(false);
  });
});
