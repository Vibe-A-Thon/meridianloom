import { EventEmitter } from 'node:events';
import { describe, expect, it, vi } from 'vitest';
import { createFrameDecoder, encodeFrame } from '../src/framing';
import type { ChildProcessLike, ProcessStream, SpawnOptions } from '../src/process';
import {
  FORCED_OFF_ENV,
  SCRUBBED_ENV_PREFIXES,
  StdioSidecarClient,
  sidecarEnvironment,
} from '../src/stdio-client';

/**
 * Audit CLD-C01: LANGSMITH_ and LANGCHAIN_ variables in the editor's environment
 * used to reach the sidecar and upload loop state to a third-party cloud.
 */
describe('sidecarEnvironment', () => {
  it('removes every telemetry family, whatever the case', () => {
    const env = sidecarEnvironment({
      LANGSMITH_API_KEY: 'k',
      LANGSMITH_ENDPOINT: 'https://api.smith.langchain.com',
      LANGCHAIN_API_KEY: 'k2',
      LANGCHAIN_PROJECT: 'p',
      LANGGRAPH_API_URL: 'u',
      langsmith_project: 'lower',
      PATH: '/usr/bin',
    });
    expect(Object.keys(env).filter((k) => /^(langsmith|langchain|langgraph)_/i.test(k) && !(k in FORCED_OFF_ENV))).toEqual([]);
    expect(env.PATH).toBe('/usr/bin');
  });

  it('pins tracing off, so a library that defaults to on stays off', () => {
    const env = sidecarEnvironment({ LANGSMITH_TRACING: 'true', LANGCHAIN_TRACING_V2: 'true' });
    expect(env.LANGSMITH_TRACING).toBe('false');
    expect(env.LANGCHAIN_TRACING_V2).toBe('false');
    expect(env.OTEL_SDK_DISABLED).toBe('true');
  });

  it('a caller-supplied extra cannot turn tracing back on', () => {
    const env = sidecarEnvironment({}, { LANGSMITH_TRACING: 'true', LANGSMITH_API_KEY: 'k' });
    expect(env.LANGSMITH_TRACING).toBe('false');
    expect(env.LANGSMITH_API_KEY).toBeUndefined();
  });

  it('leaves everything else alone — scrubbing is not emptying', () => {
    const env = sidecarEnvironment(
      { PATH: '/bin', HOME: '/home/u', SystemRoot: 'C:\\Windows', MERIDIAN_PARENT_PID: '1' },
      { MERIDIAN_DEV_LICENCE_TRUST_FILE: '/t' },
    );
    expect(env).toMatchObject({
      PATH: '/bin', HOME: '/home/u', SystemRoot: 'C:\\Windows',
      MERIDIAN_PARENT_PID: '1', MERIDIAN_DEV_LICENCE_TRUST_FILE: '/t',
    });
  });

  it('covers the families the Python side scrubs', () => {
    expect([...SCRUBBED_ENV_PREFIXES]).toEqual(['LANGSMITH_', 'LANGCHAIN_', 'LANGGRAPH_']);
  });
});

class Pipe extends EventEmitter implements ProcessStream {
  written: string[] = [];
  write(data: string): boolean {
    this.written.push(data);
    return true;
  }
  setEncoding(): void {}
}

class FakeSidecar extends EventEmitter implements ChildProcessLike {
  readonly pid = 99;
  readonly stdin = new Pipe();
  readonly stdout = new Pipe();
  readonly stderr = new Pipe();
  private readonly decoder = createFrameDecoder();
  kill(): boolean {
    queueMicrotask(() => this.emit('exit', 0, null));
    return true;
  }
  constructor() {
    super();
    const original = this.stdin.write.bind(this.stdin);
    this.stdin.write = (data: string) => {
      original(data);
      for (const message of this.decoder.push(data)) {
        const request = message as { id?: number; method?: string };
        if (request.id === undefined) continue;
        const reply =
          request.method === 'handshake'
            ? { jsonrpc: '2.0', id: request.id, result: { protocolVersion: 1 } }
            : request.method === 'gate.status'
              ? {
                  jsonrpc: '2.0',
                  id: request.id,
                  error: {
                    code: -32006,
                    message: 'gate.status is a Meridian Loom Premium feature (governor).',
                    data: { feature: 'governor', licenceState: 'none' },
                  },
                }
              : { jsonrpc: '2.0', id: request.id, result: { pong: true } };
        this.stdout.emit('data', encodeFrame(reply));
      }
      return true;
    };
  }
}

describe('what the spawned sidecar receives', () => {
  it('has no telemetry variable even when the editor has them set', async () => {
    const before = { ...process.env };
    process.env.LANGSMITH_TRACING = 'true';
    process.env.LANGSMITH_API_KEY = 'lsv2_secret';
    process.env.LANGCHAIN_ENDPOINT = 'http://example.invalid';
    let captured: SpawnOptions | undefined;
    try {
      const client = new StdioSidecarClient({
        command: 'python',
        cwd: '/x',
        spawner: (options) => {
          captured = options;
          return new FakeSidecar();
        },
      });
      await client.start();
    } finally {
      for (const key of Object.keys(process.env)) if (!(key in before)) delete process.env[key];
      Object.assign(process.env, before);
    }
    const env = captured!.env as NodeJS.ProcessEnv;
    expect(env.LANGSMITH_API_KEY).toBeUndefined();
    expect(env.LANGCHAIN_ENDPOINT).toBeUndefined();
    expect(env.LANGSMITH_TRACING).toBe('false');
    expect(env.MERIDIAN_PARENT_PID).toBe(String(process.pid));
  });
});

describe('a Premium method refused for want of a licence', () => {
  it('rejects normally and tells the host why, once per refusal', async () => {
    const onLicenceRequired = vi.fn();
    const client = new StdioSidecarClient({
      command: 'python',
      cwd: '/x',
      spawner: () => new FakeSidecar(),
      onLicenceRequired,
    });
    await client.start();
    await expect(client.request('gate.status', {}, new AbortController().signal)).rejects.toMatchObject({
      code: -32006,
    });
    expect(onLicenceRequired).toHaveBeenCalledWith({ feature: 'governor', licenceState: 'none' });
  });

  it('a throwing callback cannot change the failure', async () => {
    const client = new StdioSidecarClient({
      command: 'python',
      cwd: '/x',
      spawner: () => new FakeSidecar(),
      onLicenceRequired: () => {
        throw new Error('ui exploded');
      },
    });
    await client.start();
    await expect(client.request('gate.status', {}, new AbortController().signal)).rejects.toMatchObject({
      code: -32006,
    });
  });

  it('other errors do not invoke the callback', async () => {
    const onLicenceRequired = vi.fn();
    const client = new StdioSidecarClient({
      command: 'python',
      cwd: '/x',
      spawner: () => new FakeSidecar(),
      onLicenceRequired,
    });
    await client.start();
    await client.request('ping', {}, new AbortController().signal);
    expect(onLicenceRequired).not.toHaveBeenCalled();
  });
});
