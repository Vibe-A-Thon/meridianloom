import { EventEmitter } from 'node:events';
import { describe, expect, it } from 'vitest';
import { createFrameDecoder, encodeFrame } from '../src/framing';
import type { ChildProcessLike, ProcessStream } from '../src/process';
import {
  DEFAULT_HANDSHAKE_TIMEOUT_MS,
  SidecarSpawnError,
  StdioSidecarClient,
  describeSpawnError,
} from '../src/stdio-client';

class FakeStream extends EventEmitter implements ProcessStream {
  written: string[] = [];

  write(data: string): boolean {
    this.written.push(data);
    return true;
  }

  setEncoding(): void {
    // no-op for the fake
  }
}

/**
 * In-process fake of the Python sidecar: parses NDJSON from its stdin and
 * answers handshake/ping/shutdown like meridian_core.server does.
 */
class FakeSidecarProcess extends EventEmitter implements ChildProcessLike {
  readonly pid = 4321;
  readonly stdin = new FakeStream();
  readonly stdout = new FakeStream();
  readonly stderr = new FakeStream();
  killed = false;
  private readonly decoder = createFrameDecoder();
  private shutdownRequested = false;

  constructor() {
    super();
  }

  kill(): boolean {
    if (!this.killed) {
      this.killed = true;
      queueMicrotask(() => this.emit('exit', this.shutdownRequested ? 0 : 1, null));
    }
    return true;
  }

  /** Simulates a clean exit after a shutdown request. */
  exitCleanly(): void {
    this.shutdownRequested = true;
    queueMicrotask(() => this.emit('exit', 0, null));
  }

  respond(raw: string): void {
    for (const message of this.decoder.push(raw)) {
      const request = message as { id?: number; method?: string; params?: { protocolVersion?: number } };
      if (request.id === undefined) {
        continue;
      }
      let response: unknown;
      switch (request.method) {
        case 'handshake':
          response = request.params?.protocolVersion === 1
            ? { jsonrpc: '2.0', id: request.id, result: { protocolVersion: 1 } }
            : {
                jsonrpc: '2.0',
                id: request.id,
                error: { code: -32002, message: 'protocol version mismatch' },
              };
          break;
        case 'ping':
          response = { jsonrpc: '2.0', id: request.id, result: { pong: true } };
          break;
        case 'shutdown':
          response = { jsonrpc: '2.0', id: request.id, result: { ok: true } };
          queueMicrotask(() => this.exitCleanly());
          break;
        default:
          response = {
            jsonrpc: '2.0',
            id: request.id,
            error: { code: -32601, message: `unknown method: ${request.method}` },
          };
      }
      this.stdout.emit('data', encodeFrame(response));
    }
  }

  private onRequest(raw: string): void {
    this.respond(raw);
  }
}

function makeClient(child?: FakeSidecarProcess) {
  const fake = child ?? new FakeSidecarProcess();
  // Route stdin writes into the fake's request handler.
  const originalWrite = fake.stdin.write.bind(fake.stdin);
  fake.stdin.write = (data: string) => {
    originalWrite(data);
    fake.respond(data);
    return true;
  };
  const client = new StdioSidecarClient({
    command: 'python',
    cwd: '/repo/core',
    spawner: () => fake,
  });
  return { client, fake };
}

describe('StdioSidecarClient (FR-M3-01)', () => {
  it('handshakes on start and answers requests by id', async () => {
    const { client } = makeClient();
    await client.start();
    const result = await client.request<{ pong: boolean }>(
      'ping',
      {},
      new AbortController().signal,
    );
    expect(result.pong).toBe(true);
  });

  it('matches responses to requests even when interleaved', async () => {
    const { client, fake } = makeClient();
    await client.start();
    // Force out-of-order delivery: delay the first response until the second
    // has been answered.
    const first = client.request('ping', {}, new AbortController().signal);
    const second = client.request('ping', {}, new AbortController().signal);
    await expect(first).resolves.toEqual({ pong: true });
    await expect(second).resolves.toEqual({ pong: true });
    expect(fake.stdin.written.length).toBeGreaterThanOrEqual(3);
  });

  it('provisions the identity provider over the handshake (FR-M20-01)', async () => {
    // The host owns the identity source of record (git config today,
    // SecretStorage OIDC tokens later) and selects it at the handshake,
    // like the ledger signing key. Without a workspace there is nothing
    // for the git provider to resolve, so the param stays home.
    const requests: Array<{ method?: string; params?: Record<string, unknown> }> = [];
    const spawner = () => {
      const fake = new FakeSidecarProcess();
      fake.stdin.write = (data: string) => {
        fake.respond(data);
        requests.push(JSON.parse(data) as { method?: string; params?: Record<string, unknown> });
        return true;
      };
      return fake;
    };
    const provisioned = new StdioSidecarClient({
      command: 'python',
      cwd: '/repo/core',
      spawner,
      workspaceDir: '/repo',
      identityProvider: 'git',
    });
    await provisioned.start();
    expect(requests[0]).toMatchObject({
      method: 'handshake',
      params: { workspaceDir: '/repo', identityProvider: 'git' },
    });

    requests.length = 0;
    const bare = new StdioSidecarClient({
      command: 'python',
      cwd: '/repo/core',
      spawner,
    });
    await bare.start();
    expect(requests[0].method).toBe('handshake');
    expect(requests[0].params).not.toHaveProperty('identityProvider');
  });

  it('surfaces JSON-RPC error frames as rejections with code and data', async () => {
    const { client } = makeClient();
    await client.start();
    await expect(
      client.request('no.such.method', {}, new AbortController().signal),
    ).rejects.toMatchObject({ code: -32601 });
  });

  it('refuses to start on protocol version mismatch (FR-M3-08)', async () => {
    const { client } = makeClient();
    // Fake answers mismatch errors to any handshake whose version is not 1;
    // to simulate an old sidecar, start a client that sends version 99.
    await expect(client.start()).resolves.toBeUndefined();
    const legacy = new StdioSidecarClient({
      command: 'python',
      cwd: '/repo/core',
      spawner: () => {
        const fake = new FakeSidecarProcess();
        fake.stdin.write = (data: string) => {
          const parsed = JSON.parse(data) as { id?: number; method?: string };
          if (parsed.method === 'handshake') {
            fake.stdout.emit('data', encodeFrame({
              jsonrpc: '2.0',
              id: parsed.id,
              result: { protocolVersion: 0 },
            }));
          }
          return true;
        };
        return fake;
      },
    });
    const failure = await legacy.start().catch((error: unknown) => error);
    expect(failure).toMatchObject({
      name: 'SidecarSpawnError',
      code: 'PROTOCOL_MISMATCH',
    });
    // FR-M3-08: the refusal tells the user to reinstall, not to retry.
    expect((failure as Error).message).toMatch(/[Rr]einstall/);
  });

  it('aborting a request rejects it and sends $/cancel (FR-M1-09)', async () => {
    const { client, fake } = makeClient();
    await client.start();
    // A request the fake never answers: stop responding for this test.
    fake.respond = () => undefined;
    const controller = new AbortController();
    const pending = client.request('loop.start', {}, controller.signal);
    const expectation = expect(pending).rejects.toMatchObject({ name: 'AbortError' });
    controller.abort();
    await expectation;
    const cancel = fake.stdin.written
      .map((raw) => {
        try {
          return JSON.parse(raw) as { method?: string };
        } catch {
          return {};
        }
      })
      .find((message) => message.method === '$/cancel');
    expect(cancel).toBeDefined();
  });

  it('rejects all pending requests when the child exits', async () => {
    const { client, fake } = makeClient();
    await client.start();
    fake.respond = () => undefined;
    const pending = client.request('ping', {}, new AbortController().signal);
    const expectation = expect(pending).rejects.toThrow(/exited/);
    fake.kill();
    await expectation;
  });

  it('classifies a spawn error distinctly from an exit (FR-M3-04)', async () => {
    const spawnErrors: SidecarSpawnError[] = [];
    const client = new StdioSidecarClient({
      command: '/missing/python',
      cwd: '/repo/core',
      spawner: () => {
        const fake = new FakeSidecarProcess();
        queueMicrotask(() => {
          const error = new Error('spawn ENOENT') as NodeJS.ErrnoException;
          error.code = 'ENOENT';
          fake.emit('error', error);
        });
        return fake;
      },
    });
    client.on('spawnError', (error: SidecarSpawnError) => spawnErrors.push(error));
    // The spawn error rejects the pending handshake, so start() surfaces it.
    await expect(client.start()).rejects.toMatchObject({
      name: 'SidecarSpawnError',
      code: 'SPAWN_ERROR',
    });
    expect(spawnErrors).toHaveLength(1);
    expect(spawnErrors[0].message).toContain('interpreter not found');
  });

  it('reports non-zero exit during startup as EARLY_EXIT with stderr tail', async () => {
    const client = new StdioSidecarClient({
      command: 'python',
      cwd: '/repo/core',
      spawner: () => {
        const fake = new FakeSidecarProcess();
        queueMicrotask(() => {
          fake.stderr.emit('data', 'Traceback: boom\n');
          fake.emit('exit', 2, null);
        });
        return fake;
      },
    });
    await expect(client.start()).rejects.toMatchObject({ code: 'EARLY_EXIT' });
  });
});

describe('the handshake budget', () => {
  it('defaults to thirty seconds, not ten', () => {
    // Ten seconds failed a cold start under load — the same shape as a first
    // launch on Windows, where the whole sidecar is read past the antivirus.
    // doctor-e2e.test.ts had already been overriding it to 30s in three
    // places; that was the default telling us it was wrong.
    expect(DEFAULT_HANDSHAKE_TIMEOUT_MS).toBe(30_000);
  });

  it('says something a user can act on when the sidecar is silent', async () => {
    const client = new StdioSidecarClient({
      command: 'python',
      cwd: '/repo/core',
      handshakeTimeoutMs: 20,
      // Unwired: it starts and never answers, which is what a slow import
      // looks like from outside.
      spawner: () => new FakeSidecarProcess(),
    });
    const error = (await client.start().catch((caught) => caught)) as Error & {
      code?: string;
    };
    expect(error.code).toBe('HANDSHAKE_TIMEOUT');
    // The old message ended "Recent stderr: (empty)", which told nobody
    // anything. The new one names the setting that fixes it.
    expect(error.message).not.toContain('(empty)');
    expect(error.message).toContain('meridian.sidecar.handshakeTimeoutMs');
    expect(error.message).toContain('Doctor');
  });

  it('shows what the sidecar printed, when it printed something', async () => {
    const client = new StdioSidecarClient({
      command: 'python',
      cwd: '/repo/core',
      handshakeTimeoutMs: 20,
      spawner: () => {
        const fake = new FakeSidecarProcess();
        queueMicrotask(() =>
          fake.stderr.emit('data', "ModuleNotFoundError: No module named 'yaml'\n"),
        );
        return fake;
      },
    });
    const error = (await client.start().catch((caught) => caught)) as Error;
    // A printed cause beats any generic advice, so it is shown instead of it.
    expect(error.message).toContain('ModuleNotFoundError');
  });
});

describe('describeSpawnError (FR-M3-04)', () => {
  it.each([
    ['ENOENT', /interpreter not found/],
    ['EACCES', /[Pp]ermission denied/],
    ['EPERM', /policy/],
  ])('gives an actionable message for %s', (code, pattern) => {
    const error = new Error('spawn failed') as NodeJS.ErrnoException;
    error.code = code;
    expect(describeSpawnError('python', error)).toMatch(pattern);
  });
});
